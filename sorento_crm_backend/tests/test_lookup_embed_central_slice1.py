"""LOOKUP-EMBED-CENTRAL slice 1 red tests (AC-LEC-1..4): embedder setting + one embed_texts.

Postgres only (blank_session). No network: the HTTP layer is stubbed at httpx.Client.send.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_slice1.py -q -n 2
"""
from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path

import httpx
import pytest

from tests._pg_fixture import TEST_PREFIX, blank_session

BASE = "/api/v1/user-management/settings"
EMBEDDER_KEY = "chatbot_lookup_embedder"
APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _setting(db, **cols):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} LEC Co", **cols)
    db.add(row)
    db.commit()
    return row


def _label(db, provider, model):
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    v = AIPromptVersion(id=str(uuid.uuid4()), name=EMBEDDER_KEY, version=1, type="text", template="x", variables=[])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(name=EMBEDDER_KEY, label="production", version_id=v.id, provider=provider, model=model))
    db.commit()


# ---------------------------------------------------------------- AC-LEC-1 (API)

@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"{TEST_PREFIX}-lec-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} LEC",
        avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    who = {"id": user.id, "email": user.email}

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    try:
        yield TestClient(app)
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture(autouse=False)
def admin(monkeypatch, client):
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})


def test_ac_lec_1_settings_get_has_embedding_fields(client, admin, db):
    _setting(
        db,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        embedding_records_search_model="text-embedding-3-small",
        embedding_backfill_rpm=20,
    )
    resp = client.get(f"{BASE}/")
    assert resp.status_code == 200, resp.text
    s = resp.json()["settings"]
    assert s["embedding_provider"] == "gemini"
    assert s["embedding_model"] == "gemini-embedding-001"
    assert s["embedding_records_search_model"] == "text-embedding-3-small"
    assert s["embedding_backfill_rpm"] == 20


def test_ac_lec_1_settings_put_persists_provider_model_rpm(client, admin, db):
    from app.models.user import SystemSetting

    _setting(db)
    resp = client.put(
        f"{BASE}/general",
        json={"embedding_provider": "gemini", "embedding_model": "gemini-embedding-001", "embedding_backfill_rpm": 45},
    )
    assert resp.status_code == 200, resp.text
    db.expire_all()
    row = db.query(SystemSetting).first()
    assert (row.embedding_provider, row.embedding_model, row.embedding_backfill_rpm) == (
        "gemini",
        "gemini-embedding-001",
        45,
    )
    got = client.get(f"{BASE}/").json()["settings"]
    assert got["embedding_provider"] == "gemini"
    assert got["embedding_model"] == "gemini-embedding-001"
    assert got["embedding_backfill_rpm"] == 45


def test_ac_lec_1_settings_put_never_changes_records_search_model(client, admin, db):
    from app.models.user import SystemSetting

    _setting(db, embedding_records_search_model="text-embedding-3-small")
    resp = client.put(
        f"{BASE}/general",
        json={"embedding_provider": "openai", "embedding_records_search_model": "zzt-hijack"},
    )
    assert resp.status_code in (200, 422), resp.text
    db.expire_all()
    row = db.query(SystemSetting).first()
    assert row.embedding_records_search_model == "text-embedding-3-small"
    if resp.status_code == 200:
        assert row.embedding_provider == "openai"


# ---------------------------------------------------------------- AC-LEC-3

def test_ac_lec_3_setting_wins_over_label(db):
    from app.services.embedding_settings import resolve_embedder

    _setting(db, embedding_provider="openai", embedding_model="text-embedding-3-large")
    _label(db, "gemini", "gemini-embedding-001")
    assert resolve_embedder(db) == ("openai", "text-embedding-3-large")


def test_ac_lec_3_empty_setting_falls_back_to_label(db):
    from app.services.embedding_settings import resolve_embedder

    _setting(db, embedding_provider=None, embedding_model=None)
    _label(db, "gemini", "gemini-embedding-001")
    assert resolve_embedder(db) == ("gemini", "gemini-embedding-001")


def test_ac_lec_3_neither_gives_openai_default(db):
    from app.services.embedding_settings import resolve_embedder

    _setting(db)
    assert resolve_embedder(db) == ("openai", "text-embedding-3-small")


def test_ac_lec_3_records_search_model_returns_column(db):
    from app.services.embedding_settings import records_search_model

    _setting(db, embedding_records_search_model="text-embedding-3-small")
    assert records_search_model(db) == "text-embedding-3-small"


@pytest.mark.parametrize(
    "chosen, expect",
    [
        (("gemini", "gemini-embedding-zzt"), ("gemini_embedder", "gemini-embedding-zzt")),
        (("openai", "text-embedding-3-small"), ("provider_embedder", None)),
    ],
)
def test_ac_lec_3_lookup_lists_embedder_follows_resolve_embedder(db, monkeypatch, chosen, expect):
    """No production label is seeded, so only resolve_embedder can make the gemini case choose gemini."""
    from app.services import embedding_settings, llm_provider
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.chatbot.head import lookup_lists

    calls: list[tuple] = []
    monkeypatch.setattr(lookup_lists, "EMBED", lookup_lists.USE_PROVIDER)
    monkeypatch.setattr(embedding_settings, "resolve_embedder", lambda _db: chosen)
    if hasattr(lookup_lists, "resolve_embedder"):
        monkeypatch.setattr(lookup_lists, "resolve_embedder", lambda _db: chosen)
    monkeypatch.setattr(AIAssistantConfigService, "get", lambda self: object())
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda cfg, provider: "zzt-key")
    sentinel = object()

    def fake_gemini(key, model):
        calls.append(("gemini_embedder", model))
        return sentinel

    def fake_openai(key, *a, **k):
        calls.append(("provider_embedder", None))
        return sentinel

    monkeypatch.setattr(lookup_lists, "gemini_embedder", fake_gemini)
    monkeypatch.setattr(lookup_lists, "provider_embedder", fake_openai)

    assert lookup_lists.embedder(db) is sentinel
    assert calls == [expect]


# ---------------------------------------------------------------- AC-LEC-4

class _Recorder:
    def __init__(self, dims=1536, scale=2.0):
        self.requests: list[httpx.Request] = []
        self.dims = dims
        self.scale = scale

    def send(self, client_self, request, **kwargs):
        self.requests.append(request)
        body = json.loads(request.content)
        url = str(request.url)
        if "batchEmbedContents" in url:
            data = {"embeddings": [{"values": [self.scale] * self.dims} for _ in body["requests"]]}
        else:
            inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
            data = {"data": [{"index": i, "embedding": [self.scale] * self.dims} for i, _ in enumerate(inputs)]}
        return httpx.Response(200, json=data, request=request)


@pytest.fixture
def http(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: rec.send(self, request, **kw))
    return rec


def test_ac_lec_4_gemini_batches_100_and_asks_1536(http):
    from app.services import embedding_client

    texts = [f"zzt text {i}" for i in range(250)]
    out = embedding_client.embed_texts(texts, "gemini", "gemini-embedding-001", api_key="zzt-key")
    assert len(out) == 250
    assert len(http.requests) == 3
    sizes = []
    for r in http.requests:
        assert "batchEmbedContents" in str(r.url)
        body = json.loads(r.content)
        sizes.append(len(body["requests"]))
        assert all(item["outputDimensionality"] == 1536 for item in body["requests"])
    assert sizes == [100, 100, 50]


def test_ac_lec_4_returns_unit_vectors_1536(http):
    from app.services import embedding_client

    for provider, model in (("gemini", "gemini-embedding-001"), ("openai", "text-embedding-3-small")):
        out = embedding_client.embed_texts(["a", "b"], provider, model, api_key="zzt-key")
        assert len(out) == 2
        for v in out:
            assert len(v) == 1536
            assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_ac_lec_4_wrong_dimension_raises(monkeypatch):
    from app.services import embedding_client

    rec = _Recorder(dims=3072)
    monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: rec.send(self, request, **kw))
    with pytest.raises(embedding_client.EmbeddingDimensionError):
        embedding_client.embed_texts(["a"], "gemini", "gemini-embedding-001", api_key="zzt-key")


def test_ac_lec_4_openai_posts_to_embeddings_endpoint(http):
    from app.services import embedding_client

    embedding_client.embed_texts(["a", "b", "c"], "openai", "text-embedding-3-small", api_key="zzt-key")
    assert http.requests, "no HTTP request was made"
    req = http.requests[0]
    assert req.method == "POST"
    assert str(req.url).rstrip("/").endswith("/embeddings")
    body = json.loads(req.content)
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["a", "b", "c"]


def test_ac_lec_4_only_embedding_client_calls_an_embeddings_endpoint():
    needles = ("batchEmbedContents", ":embedContent", "/v1/embeddings", "openai_embeddings_url")
    # config.py only DEFINES the openai_embeddings_url setting; it posts nothing.
    allowed = {APP / "services" / "embedding_client.py", APP / "config.py"}
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        hit = [n for n in needles if n in text]
        if hit:
            offenders.append(f"{path.relative_to(APP.parent)}: {', '.join(hit)}")
    assert not offenders, "embeddings endpoint called outside embedding_client.py:\n" + "\n".join(offenders)
