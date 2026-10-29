"""LOOKUP-EMBED-CENTRAL slice 5 red tests, chatbot doorway (AC-LEC-20, 21, 22): GET lookup-words, POST try, POST
embed-missing under /api/v1/system/chatbot/lookup-words. Lives in tests/chatbot because it reaches chatbot code.

Postgres only (blank_session); all rows seeded here; the embeddings transport (httpx.Client.send) and the job queue
are stubbed; no network.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/chatbot/test_lookup_embed_central_slice5_lookup_api.py -q -n 2
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot.head import lookup_lists as ll
from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
VIEW = "master_data.lookup_sets.view"
EDIT = "master_data.lookup_sets.edit"
BASE = "/api/v1/system/chatbot/lookup-words"


def pad(*head):
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def allow():
    return set()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})


@pytest.fixture
def client(db, allow, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User
    from app.services.user_service import UserPermissionService

    user = User(
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-s5l-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} S5L", avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    who = {"id": user.id, "email": user.email}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)

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


class Transport:
    """Texts mentioning closet / toilet share axis 0 (the same meaning); anything else gets an axis of its own."""

    def __init__(self, fail=False):
        self.fail = fail
        self.requests: list[list[str]] = []

    def vec(self, t):
        low = t.lower()
        if "closet" in low or "toilet" in low:
            return pad(1.0)
        v = [0.0] * 1536
        v[1 + int(abs(hash(low)) % 1500)] = 1.0
        return v

    def send(self, request):
        body = json.loads(request.content)
        texts = list(body["input"])
        self.requests.append(texts)
        if self.fail:
            return httpx.Response(500, json={"error": "zzt down"}, request=request)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": self.vec(t)} for i, t in enumerate(texts)]}, request=request)


@pytest.fixture
def transport(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)

    def make(fail=False):
        t = Transport(fail)
        real_send = httpx.Client.send

        def send(self, request, **kw):
            # The TestClient is an httpx client too: only provider calls are stubbed.
            if request.url.host == "testserver":
                return real_send(self, request, **kw)
            return t.send(request)

        monkeypatch.setattr(httpx.Client, "send", send)
        return t

    return make


def _setting(db):
    from app.models.user import SystemSetting

    row = SystemSetting(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} S5L Co", embedding_provider="openai", embedding_model=M3S,
        embedding_records_search_model=M3S,
    )
    db.add(row)
    db.flush()


def _category(db, name, *, code, class_label=None, synonyms=()):
    from app.models.product import ProductCategory

    c = ProductCategory(
        id=str(uuid.uuid4()), category_code=code, category_name=name, class_label=class_label,
        search_synonyms=list(synonyms), is_active=True, is_searchable=True,
    )
    db.add(c)
    db.flush()
    return c


def _stored_vector(db, text, model=M3S):
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    d = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type="lookup_word", source_id=f"category:zzt-{uuid.uuid4().hex[:6]}", title=text,
        body_text=text, source_hash="h", is_active=True,
    )
    db.add(d)
    db.flush()
    db.add(EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=d.id, source_type="lookup_word", source_id=d.source_id, chunk_index=0,
        chunk_text=text, chunk_hash="h", embedding=pad(1.0), model_name=model, model_version="1",
        embedding_provider="openai", source_hash="h", is_current=True,
    ))
    db.flush()


def _words(client, list_name="category"):
    resp = client.get(BASE, params={"list": list_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------------ AC-LEC-20 list
def test_ac_lec_20_lookup_words_need_the_view_permission(client, allow):
    assert client.get(BASE, params={"list": "category"}).status_code == 403
    allow.add(EDIT)
    assert client.get(BASE, params={"list": "category"}).status_code == 403


def test_ac_lec_20_rows_carry_words_with_their_homes_and_vector_status(client, db, allow):
    allow.add(VIEW)
    _setting(db)
    cat = _category(db, "ZZT5 Closet", code="ZZT5-CL", class_label="ZZT5 Class", synonyms=["zzt5 alias word"])
    _stored_vector(db, "ZZT5 Closet")
    body = _words(client)
    assert body["list"] == "category"
    (row,) = [r for r in body["rows"] if r["key"] == str(cat.id)]
    assert row["label"] == "ZZT5 Closet"
    words = {(w["text"], w["home"]): w["has_vector"] for w in row["words"]}
    assert words[("ZZT5 Closet", "label")] is True
    assert words[("ZZT5-CL", "code")] is False
    assert words[("ZZT5 Class", "class")] is False
    assert words[("zzt5 alias word", "alias_column")] is False


def test_ac_lec_20_file_type_words_name_the_description_and_the_alias_set(client, db, allow):
    from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
    from app.models.resources import AttachmentType

    allow.add(VIEW)
    _setting(db)
    db.add(AttachmentType(
        id=str(uuid.uuid4()), code="ZZT5-PH", type_name="ZZT5 Photo", description="zzt5 gambar, zzt5 foto",
        allowed_extensions="jpg",
    ))
    s = LookupSet(id=str(uuid.uuid4()), set_key="attachment_type_alias", name="ZZT aliases", is_active=True)
    o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value="ZZT5 Photo", label="ZZT5 Photo", is_active=True)
    db.add_all([s, o])
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword="zzt5 imej"))
    db.flush()
    (row,) = [r for r in _words(client, "file_type")["rows"] if r["label"] == "ZZT5 Photo"]
    homes = {w["text"]: w["home"] for w in row["words"]}
    assert homes["ZZT5 Photo"] == "label" and homes["zzt5 gambar"] == "description" and homes["zzt5 imej"] == "alias_set"


def test_ac_lec_20_an_unknown_list_is_422(client, allow):
    allow.add(VIEW)
    assert client.get(BASE, params={"list": "zzt5_nope"}).status_code == 422


@pytest.mark.parametrize("name", ["category", "spec", "file_type", "brand", "promotion_kind", "location", "salesperson", "customer", "sales_channel"])
def test_ac_lec_20_every_named_list_is_accepted(client, db, allow, name):
    allow.add(VIEW)
    _setting(db)
    assert _words(client, name)["list"] == name


def test_ac_lec_20_a_customer_of_another_company_is_not_listed_for_a_scoped_user(client, db, allow):
    from app.models.company import Company
    from app.models.order import Customer
    from app.services.company_scope import set_company_scope

    allow.add(VIEW)
    _setting(db)
    set_company_scope(db, None)
    a = Company(id=str(uuid.uuid4()), name="ZZT5 A", code=f"Z5A{uuid.uuid4().hex[:5]}")
    b = Company(id=str(uuid.uuid4()), name="ZZT5 B", code=f"Z5B{uuid.uuid4().hex[:5]}")
    db.add_all([a, b])
    db.flush()
    db.add_all([
        Customer(id=str(uuid.uuid4()), customer_code="ZZT5CA", customer_name="ZZT5 Own Customer", company_id=a.id, is_active=True),
        Customer(id=str(uuid.uuid4()), customer_code="ZZT5CB", customer_name="ZZT5 Other Customer", company_id=b.id, is_active=True),
    ])
    db.flush()
    set_company_scope(db, frozenset({a.id}))
    labels = [r["label"] for r in _words(client, "customer")["rows"]]
    assert "ZZT5 Own Customer" in labels and "ZZT5 Other Customer" not in labels


# ------------------------------------------------------------------ AC-LEC-21 try
def _try(client, phrase):
    return client.post(f"{BASE}/try", json={"phrase": phrase})


def test_ac_lec_21_try_needs_the_view_permission(client):
    assert _try(client, "closet").status_code == 403


def test_ac_lec_21_an_empty_phrase_is_422(client, allow):
    allow.add(VIEW)
    assert _try(client, "   ").status_code == 422


def test_ac_lec_21_a_meaning_only_phrase_resolves_by_the_vector_signal(client, db, allow, transport):
    allow.add(VIEW)
    _setting(db)
    cat = _category(db, "ZZT5 Closet", code="ZZT5-CL")
    _category(db, "ZZT5 Kettle", code="ZZT5-KT")
    t = transport()
    resp = _try(client, "zzt5 toilet bowl")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] in {"resolved", "ambiguous", "unresolved"}
    assert 1 <= len(body["candidates"]) <= 8
    cand = [c for c in body["candidates"] if c["key"] == str(cat.id)][0]
    assert cand["list"] == "category" and cand["label"] == "ZZT5 Closet"
    assert set(cand["spelling"]) == {"score", "text", "home"}
    assert set(cand["vector"]) == {"score", "text", "home"}
    assert cand["vector"]["score"] == pytest.approx(1.0, abs=0.01) and cand["vector"]["text"] == "ZZT5 Closet"
    assert cand["vector"]["home"] == "label"
    assert set(cand["floors"]) == {"spell", "partial", "meaning"}
    assert isinstance(cand["partial"], (int, float, bool)) and isinstance(cand["signal"], str)
    assert cand["passed"] is True
    assert body["verdict"] == "resolved"
    assert [r for r in t.requests if "zzt5 toilet bowl" in r], "the phrase was not embedded"


def test_ac_lec_21_the_phrase_is_embedded_once(client, db, allow, transport):
    allow.add(VIEW)
    _setting(db)
    _category(db, "ZZT5 Closet", code="ZZT5-CL")
    t = transport()
    _try(client, "zzt5 toilet bowl")
    assert sum(r.count("zzt5 toilet bowl") for r in t.requests) == 1


def test_ac_lec_21_a_spelling_match_scores_in_the_spelling_cell(client, db, allow, transport):
    allow.add(VIEW)
    _setting(db)
    cat = _category(db, "ZZT5 Closet", code="ZZT5-CL")
    transport()
    body = _try(client, "ZZT5 Closet").json()
    cand = [c for c in body["candidates"] if c["key"] == str(cat.id)][0]
    assert cand["spelling"]["score"] >= cand["floors"]["spell"] and cand["spelling"]["text"] == "ZZT5 Closet"
    assert cand["passed"] is True


def test_ac_lec_21_without_a_working_embedder_the_vector_cell_is_null(client, db, allow, transport):
    allow.add(VIEW)
    _setting(db)
    cat = _category(db, "ZZT5 Closet", code="ZZT5-CL")
    transport(fail=True)
    body = _try(client, "ZZT5 Closet").json()
    cand = [c for c in body["candidates"] if c["key"] == str(cat.id)][0]
    assert cand["vector"] is None and cand["spelling"]["score"] > 0


# ------------------------------------------------------------------ AC-LEC-22 embed-missing
@pytest.fixture
def jobs(monkeypatch):
    from app.services import queue_service

    calls: list = []

    class _Job:
        id = "zzt-job-2"

    monkeypatch.setattr(queue_service, "enqueue_job", lambda func, *a, **k: calls.append((func, a, k)) or _Job())
    return calls


def test_ac_lec_22_embed_missing_needs_the_edit_permission(client, allow, jobs):
    allow.add(VIEW)
    assert client.post(f"{BASE}/embed-missing").status_code == 403
    assert jobs == []


def test_ac_lec_22_embed_missing_enqueues_the_sync_and_returns_the_job_id(client, allow, jobs):
    from app.tasks.chat_turns import embed_missing_lookup_words

    allow.add(EDIT)
    resp = client.post(f"{BASE}/embed-missing")
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"job_id": "zzt-job-2"}
    assert len(jobs) == 1 and jobs[0][0] is embed_missing_lookup_words
