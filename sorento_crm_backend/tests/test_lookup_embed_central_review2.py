"""LOOKUP-EMBED-CENTRAL review fix round 2, core side (G-1 .. G-6). Red before the fixes.
Postgres only (blank_session); rows seeded here; provider calls stubbed; Redis faked; no network.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_review2.py -q -n 2
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from tests._external_auth import external_permissions_granted
from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"
VIEW = "master_data.lookup_sets.view"
SETS = "/api/v1/master-data/lookup-sets"
SETTINGS = "/api/v1/user-management/settings"
EDIT_SETTINGS = "user_management.settings.edit"
SETTINGS_UPDATE = "system.settings.update"


def pad(*head):
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def allow():
    return set()


@pytest.fixture
def scope():
    return {"value": None}


@pytest.fixture
def client(db, allow, scope, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user = User(
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-r2-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} R2", avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    who = {"id": user.id, "email": user.email}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)

    def _db():
        yield db

    def _scope():
        set_company_scope(db, scope["value"])
        return scope["value"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app)
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key, apply_company_scope):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture
def provider(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)
    real = httpx.Client.send
    seen: list = []

    def send(self, request, **kw):
        if request.url.host == "testserver":
            return real(self, request, **kw)
        body = json.loads(request.content)
        texts = list(body.get("input") or [])
        seen.append((body.get("model"), texts))
        return httpx.Response(200, json={"data": [{"index": i, "embedding": pad(1.0)} for i, _ in enumerate(texts)]}, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    return seen


def _setting(db, **cols):
    from app.models.user import SystemSetting

    base = dict(embedding_provider="gemini", embedding_model=GEM, embedding_records_search_model=M3S, embedding_backfill_rpm=20)
    base.update(cols)
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} R2 Co", **base)
    db.add(row)
    db.flush()
    return row


def _doc(db, source_type, n, *, failures=None, body=None):
    from app.models.embeddings import EmbeddingDocument

    d = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type=source_type, source_id=f"zzt-r2-{source_type}-{n}-{uuid.uuid4().hex[:5]}",
        source_key=f"K{n}", title=f"T{n}", body_text=body or f"zzt r2 body {n}",
        metadata_json={"embed_failures": failures} if failures else {}, source_hash="h", is_active=True,
    )
    db.add(d)
    db.flush()
    return d


def _failures(db, doc, model):
    from app.models.embeddings import EmbeddingDocument

    db.expire_all()
    return int(((db.get(EmbeddingDocument, doc.id).metadata_json or {}).get("embed_failures") or {}).get(model) or 0)


# ================================================================== G-1: keyword ranking over the capability text
def _assistant(db):
    from app.services import ai_assistant_service as svc

    owner = [c for c in vars(svc).values() if isinstance(c, type) and "_rag_select_tools" in vars(c)]
    cls = owner[0]
    inst = cls.__new__(cls)
    inst.db = db
    return svc, cls, inst


@pytest.mark.parametrize("query", ["stock for SRT-123", "how many units of SRT-123 do we have"])
def test_g1_the_assistant_picks_the_stock_balance_tool_from_the_capability_text_without_embedding(db, monkeypatch, query):
    from app.services import embedding_client, embedding_settings
    from app.services.mcp_tool_capability_service import build_capability_documents

    svc, cls, inst = _assistant(db)
    names = sorted({d.source_key for d in build_capability_documents(include_planned=False)})
    assert "crm_inventory_stock_balance_list" in names, "the real seed lost the stock balance tool"

    def boom(*a, **k):
        raise AssertionError("an embed call was made")

    monkeypatch.setattr(embedding_client, "embed_texts", boom)
    monkeypatch.setattr(embedding_settings, "embed_search_texts", boom)
    monkeypatch.setattr(cls, "_embed_query", boom, raising=False)
    selected, _sources = inst._rag_select_tools(standalone_query=query, enabled_tools=names, top_k=1)
    assert [c["tool_name"] for c in selected] == ["crm_inventory_stock_balance_list"], selected


# ================================================================== G-2 / G-4: brand targets and orphan status
def _brand_world(db):
    from app.models.company import Company
    from app.models.lookup import LookupOption, LookupSet
    from app.models.product import Brand
    from app.services.company_scope import set_company_scope

    set_company_scope(db, None)
    a = Company(id=str(uuid.uuid4()), name="ZZT R2 A", code=f"R2A{uuid.uuid4().hex[:5]}")
    b = Company(id=str(uuid.uuid4()), name="ZZT R2 B", code=f"R2B{uuid.uuid4().hex[:5]}")
    db.add_all([a, b])
    db.flush()
    db.add_all([
        Brand(id=str(uuid.uuid4()), brand_code="ZZT-R2-A", brand_name="ZZT R2 A Brand", company_id=a.id),
        Brand(id=str(uuid.uuid4()), brand_code="ZZT-R2-B", brand_name="ZZT R2 B Brand", company_id=b.id),
        Brand(id=str(uuid.uuid4()), brand_code="ZZT-R2-NULL", brand_name="ZZT R2 Null Brand", company_id=None),
    ])
    db.flush()
    from sqlalchemy import text as _t

    # the insert stamps a default company on a company-less row; clear it so the row really is company-less
    db.execute(_t("UPDATE brands SET company_id = NULL WHERE brand_code = 'ZZT-R2-NULL'"))
    s = LookupSet(id=str(uuid.uuid4()), set_key="brand_alias", name="ZZT R2 brand aliases", is_active=True)
    db.add(s)
    db.flush()
    for value in ("ZZT-R2-A", "ZZT-R2-B", "ZZT-R2-NOWHERE"):
        db.add(LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=value, label=value, is_active=True))
    db.flush()
    return a, b, s


def test_g2_orphan_status_is_computed_from_all_brand_codes_not_the_callers_scope(client, db, allow, scope):
    allow.add(VIEW)
    a, _b, s = _brand_world(db)
    scope["value"] = frozenset({a.id})
    flags = {o["value"]: o["orphaned"] for o in client.get(f"{SETS}/{s.id}/options").json()["data"]}
    assert flags == {"ZZT-R2-A": False, "ZZT-R2-B": False, "ZZT-R2-NOWHERE": True}


def test_g2_the_picker_lists_only_the_callers_company(client, db, allow, scope):
    allow.add(VIEW)
    a, _b, s = _brand_world(db)
    scope["value"] = frozenset({a.id})
    values = {t["value"] for t in client.get(f"{SETS}/{s.id}/alias-targets").json()}
    assert "ZZT-R2-A" in values and "ZZT-R2-B" not in values


def test_g4_a_company_less_brand_follows_the_standard_orm_filter(client, db, allow, scope):
    """Brand is a CompanyScopedMixin model without __company_shared__, so the standard filter does not show a
    NULL-company brand to a scope that names companies; the picker must not add it back."""
    from app.models.product import Brand

    assert getattr(Brand, "__company_shared__", False) is False
    allow.add(VIEW)
    a, _b, s = _brand_world(db)
    scope["value"] = frozenset({a.id})
    values = {t["value"] for t in client.get(f"{SETS}/{s.id}/alias-targets").json()}
    assert "ZZT-R2-NULL" not in values


# ================================================================== G-3: the label fallback obeys the model pattern
def _label(db, provider, model):
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    v = AIPromptVersion(id=str(uuid.uuid4()), name="chatbot_lookup_embedder", version=1, type="text", template="x", variables=[])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(name="chatbot_lookup_embedder", label="production", version_id=v.id, provider=provider, model=model))
    db.commit()


def test_g3_a_label_model_that_fails_the_pattern_gives_the_default(db):
    from app.services.embedding_settings import resolve_embedder

    _setting(db, embedding_provider=None, embedding_model=None)
    _label(db, "gemini", "bad:model")
    assert resolve_embedder(db) == ("openai", M3S)


def test_g3_a_valid_label_model_is_still_used(db):
    from app.services.embedding_settings import resolve_embedder

    _setting(db, embedding_provider=None, embedding_model=None)
    _label(db, "gemini", GEM)
    assert resolve_embedder(db) == ("gemini", GEM)


def test_g3_the_lec_0001_upgrade_does_not_copy_a_label_model_that_fails_the_pattern(db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "lec_0001_embedding_setting.py"
    spec = importlib.util.spec_from_file_location("_lec_0001_r2", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _setting(db, embedding_provider=None, embedding_model=None, embedding_records_search_model=None)
    _label(db, "gemini", "bad:model")
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        m.upgrade()
    row = db.execute(text("SELECT embedding_provider, embedding_model FROM system_settings")).one()
    assert tuple(row) == (None, None)


# ================================================================== G-5: which failures count, singles, clearing
@pytest.mark.parametrize(
    "status, body",
    [
        pytest.param(400, '{"error": {"status": "API_KEY_INVALID", "message": "API key not valid"}}', id="400-api-key-invalid"),
        pytest.param(400, '{"error": {"status": "FAILED_PRECONDITION", "message": "billing"}}', id="400-failed-precondition"),
        pytest.param(404, '{"error": {"message": "model not found"}}', id="404"),
    ],
)
def test_g5_key_billing_and_unknown_model_errors_stop_the_run_without_counting(db, monkeypatch, status, body):
    from app.services import embedding_client, embedding_settings
    from app.services.embedding_backfill_service import backfill_records

    docs = [_doc(db, "promotion", n) for n in range(3)]
    db.commit()

    def boom(session, texts, model, **kw):
        raise embedding_client.EmbeddingHTTPError(f"Embedding call failed ({status}): {body}", status)

    monkeypatch.setattr(embedding_settings, "embed_for_model", boom)
    try:
        backfill_records(db, GEM, sleep=lambda s: None)
    except Exception:  # noqa: BLE001
        pass
    assert [_failures(db, d, GEM) for d in docs] == [0, 0, 0]


def test_g5_a_400_on_a_batch_is_retried_one_document_at_a_time_and_only_the_bad_one_counts(db, monkeypatch):
    from app.models.embeddings import EmbeddingChunk
    from app.services import embedding_client, embedding_settings
    from app.services.embedding_backfill_service import backfill_records

    good1, bad, good2 = _doc(db, "promotion", 1), _doc(db, "promotion", 2, body="zzt r2 BAD input"), _doc(db, "promotion", 3)
    db.commit()

    def picky(session, texts, model, **kw):
        if any("BAD" in t for t in texts):
            raise embedding_client.EmbeddingHTTPError("Embedding call failed (400): input too long", 400)
        return [pad(1.0) for _ in texts]

    monkeypatch.setattr(embedding_settings, "embed_for_model", picky)
    backfill_records(db, GEM, sleep=lambda s: None)
    assert _failures(db, bad, GEM) == 1
    assert _failures(db, good1, GEM) == 0 and _failures(db, good2, GEM) == 0
    db.expire_all()
    have = {c.source_id for c in db.query(EmbeddingChunk).filter_by(model_name=GEM, is_current=True)}
    assert {good1.source_id, good2.source_id} <= have and bad.source_id not in have


def test_g5_a_settings_model_change_clears_the_new_models_failure_counts(client, db, allow, monkeypatch):
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: MagicMock(id="j"))
    allow.add(EDIT_SETTINGS)
    _setting(db, embedding_provider="openai", embedding_model=M3S)
    stuck = _doc(db, "promotion", 1, failures={GEM: 3})
    db.commit()
    assert client.put(f"{SETTINGS}/general", json={"embedding_provider": "gemini", "embedding_model": GEM}).status_code == 200
    assert _failures(db, stuck, GEM) == 0


# ================================================================== G-6
def test_g6_rag_search_refuses_a_source_outside_the_keep_set_before_embedding(db, provider):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_external_api_user
    from app.main import app
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    _setting(db, embedding_provider="openai", embedding_model=M3S)
    set_company_scope(db, None)

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_external_api_user] = lambda: {"id": str(uuid.uuid4()), "email": "zzt@api.test"}
    app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(db, None)
    try:
        with external_permissions_granted():
            resp = TestClient(app).post("/api/v1/external/rag/search", json={"query": "an order", "source_type": "order", "top_k": 5})
    finally:
        for dep in (get_db, get_external_api_user, apply_company_scope):
            app.dependency_overrides.pop(dep, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
    assert provider == [], "the query was embedded for a source nothing can answer"


class _FakeEngine:
    def __init__(self, statements, fail_on=None):
        self.statements, self.fail_on = statements, fail_on

    def connect(self):
        outer = self

        class _Conn:
            def execution_options(self, **kw):
                return self

            def execute(self, stmt, *a, **k):
                text = str(stmt)
                outer.statements.append(text)
                if outer.fail_on and outer.fail_on in text:
                    raise RuntimeError("zzt ddl failed")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Conn()


@pytest.mark.parametrize("fail_on", [None, "CREATE INDEX"])
def test_g6_the_guard_puts_maintenance_work_mem_back_even_when_the_build_fails(db, monkeypatch, fail_on):
    import app.database as database
    from app.models.embeddings import EmbeddingChunk
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db)
    d = _doc(db, "promotion", 1)
    db.add(EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=d.id, source_type=d.source_type, source_id=d.source_id, chunk_index=0,
        chunk_text="t", chunk_hash="h", embedding=pad(1.0), model_name=GEM, model_version="1", embedding_provider="gemini",
        source_hash="h", is_current=True,
    ))
    db.flush()
    statements: list[str] = []
    monkeypatch.setattr(database, "engine", _FakeEngine(statements, fail_on))
    try:
        apply_search_model_guard(db, GEM)
    except Exception:  # noqa: BLE001
        pass
    mem = [s for s in statements if "maintenance_work_mem" in s]
    assert len(mem) >= 2 and "512MB" in mem[0], statements
    assert "RESET" in mem[-1].upper() or "512MB" not in mem[-1], "maintenance_work_mem was left raised"


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False, **kw):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def setnx(self, key, value):
        return bool(self.set(key, value, nx=True))

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def expire(self, key, seconds):
        return key in self.store

    def exists(self, key):
        return int(key in self.store)

    def eval(self, script, numkeys, *args):  # a compare-and-delete script
        key, token = args[0], args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


def test_g6_a_job_finishing_does_not_clear_the_running_flag_of_another_job(db, monkeypatch):
    from app.services import queue_service
    from app.tasks import embedding_backfill as task

    fake = _FakeRedis()
    monkeypatch.setattr(queue_service, "redis_conn", fake)
    monkeypatch.setattr(task, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    _setting(db)
    key = task.RECORDS_BACKFILL_RUNNING_KEY
    seen = {}

    from app.services import embedding_backfill_service as svc

    state = {"outer": True}

    def fake_backfill(session, model, **kw):
        if state["outer"]:
            state["outer"] = False
            task.run_records_backfill(GEM)  # job B starts and finishes while job A is running
            seen["flag_after_b"] = fake.get(key)
        return svc.BackfillResult(embedded=0, failed=0, remaining=0, complete=True)

    monkeypatch.setattr(svc, "backfill_records", fake_backfill)
    monkeypatch.setattr(svc, "apply_search_model_guard", lambda session, model: False)
    task.run_records_backfill(GEM)
    assert seen["flag_after_b"], "job B finishing cleared the running flag while job A was still running"
    assert fake.get(key) is None, "the last job to finish left the flag up"
