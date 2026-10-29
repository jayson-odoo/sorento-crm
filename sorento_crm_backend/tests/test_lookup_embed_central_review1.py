"""LOOKUP-EMBED-CENTRAL review fix round 1, core side (F-1, F-2, F-4 .. F-10, F-12, F-13). Red before the fixes.

Postgres only (blank_session); every row seeded here; provider calls stubbed at httpx.Client.send (the TestClient is an
httpx client, so calls to `testserver` pass through); Redis and the job queue patched; no network.
The chatbot-side items (F-3, F-11) are in tests/chatbot/test_lookup_embed_central_review1_chatbot.py.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_review1.py -q -n 2
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import event

from tests._external_auth import external_permissions_granted
from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"
VIEW = "master_data.lookup_sets.view"
EDIT = "master_data.lookup_sets.edit"
SETTINGS_UPDATE = "system.settings.update"
SETS = "/api/v1/master-data/lookup-sets"
SETTINGS = "/api/v1/user-management/settings"
EDIT_SETTINGS = "user_management.settings.edit"


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
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-r1-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} R1", avatar_storage_provider="s3",
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
    """Stub every non-TestClient httpx call; returns the list of (model, texts) requests."""
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", "zzt-gemini", raising=False)
    real = httpx.Client.send
    seen: list = []

    def send(self, request, **kw):
        if request.url.host == "testserver":
            return real(self, request, **kw)
        body = json.loads(request.content)
        url = str(request.url)
        if "batchEmbedContents" in url:
            texts = ["".join(p.get("text", "") for p in r["content"]["parts"]) for r in body["requests"]]
            seen.append((GEM, texts))
            return httpx.Response(200, json={"embeddings": [{"values": pad(1.0)} for _ in texts]}, request=request)
        texts = list(body["input"])
        seen.append((body["model"], texts))
        return httpx.Response(200, json={"data": [{"index": i, "embedding": pad(1.0)} for i, _ in enumerate(texts)]}, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    return seen


def _setting(db, **cols):
    from app.models.user import SystemSetting

    base = dict(embedding_provider="gemini", embedding_model=GEM, embedding_records_search_model=M3S, embedding_backfill_rpm=20)
    base.update(cols)
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} R1 Co", **base)
    db.add(row)
    db.flush()
    return row


def _doc(db, source_type, n, *, failures=None, company_id=None, body=None):
    from app.models.embeddings import EmbeddingDocument

    d = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type=source_type, source_id=f"zzt-r1-{source_type}-{n}-{uuid.uuid4().hex[:5]}",
        source_key=f"K{n}", title=f"T{n}", body_text=body or f"zzt r1 body {source_type} {n}",
        metadata_json={"embed_failures": failures} if failures else {}, source_hash="h", is_active=True, company_id=company_id,
    )
    db.add(d)
    db.flush()
    return d


def _chunk(db, doc, model, vec=None):
    from app.models.embeddings import EmbeddingChunk

    c = EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=doc.id, source_type=doc.source_type, source_id=doc.source_id, chunk_index=0,
        chunk_text=doc.body_text, chunk_hash="h", embedding=vec or pad(1.0), model_name=model, model_version="1",
        embedding_provider="gemini" if model == GEM else "openai", source_hash="h", is_current=True, company_id=doc.company_id,
    )
    db.add(c)
    db.flush()
    return c


def _failures(db, doc, model):
    db.expire_all()
    from app.models.embeddings import EmbeddingDocument

    return int(((db.get(EmbeddingDocument, doc.id).metadata_json or {}).get("embed_failures") or {}).get(model) or 0)


# ================================================================== F-1: lookup_word is never a record source
def test_f1_search_current_returns_nothing_outside_the_keep_set(db):
    from app.services.company_scope import set_company_scope
    from app.services.embedding_service import EmbeddingReadService

    set_company_scope(db, None)
    for source_type in ("lookup_word", "order", "customer", "mcp_tool"):
        _chunk(db, _doc(db, source_type, 1), M3S)
        assert EmbeddingReadService(db).search_current(pad(1.0), top_k=5, source_type=source_type) == [], source_type


def test_f1_search_current_still_serves_a_keep_set_source(db):
    from app.services.company_scope import set_company_scope
    from app.services.embedding_service import EmbeddingReadService

    set_company_scope(db, None)
    _chunk(db, _doc(db, "promotion", 1), M3S)
    assert len(EmbeddingReadService(db).search_current(pad(1.0), top_k=5, source_type="promotion")) == 1


def test_f1_external_rag_search_for_lookup_word_returns_no_rows_to_a_scoped_api_key(db, provider, monkeypatch):
    """The reviewer's exploit: a dealer-scoped API key asks /external/rag/search for source_type lookup_word; the
    company-less lookup chunks (customer / salesperson / location words of every company) used to be 'shared'."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_external_api_user
    from app.main import app
    from app.models.company import Company
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    _setting(db, embedding_provider="openai", embedding_model=M3S)
    set_company_scope(db, None)
    dealer = Company(id=str(uuid.uuid4()), name="ZZT R1 Dealer", code=f"R1D{uuid.uuid4().hex[:5]}")
    db.add(dealer)
    db.flush()
    other_customer_word = _doc(db, "lookup_word", 1, company_id=None, body="zzt other company customer")
    _chunk(db, other_customer_word, M3S)

    def _db():
        yield db

    def _scope():
        set_company_scope(db, frozenset({dealer.id}))
        return frozenset({dealer.id})

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_external_api_user] = lambda: {"id": str(uuid.uuid4()), "email": "zzt@api.test"}
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        with external_permissions_granted():
            resp = TestClient(app).post(
                "/api/v1/external/rag/search", json={"query": "customer", "source_type": "lookup_word", "top_k": 10}
            )
    finally:
        for dep in (get_db, get_external_api_user, apply_company_scope):
            app.dependency_overrides.pop(dep, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


# ================================================================== F-2: no tool RAG
def test_f2_tool_search_returns_an_empty_candidate_list_without_an_error_or_an_embed(db, provider, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_external_api_user
    from app.main import app
    from app.services.company_scope import set_company_scope

    _setting(db, embedding_provider="openai", embedding_model=M3S)
    set_company_scope(db, None)
    _chunk(db, _doc(db, "mcp_tool", 1), M3S)  # an old tool vector must not be served

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_external_api_user] = lambda: {"id": str(uuid.uuid4()), "email": "zzt@api.test"}
    try:
        with external_permissions_granted():
            resp = TestClient(app).post("/api/v1/external/rag/tool-search", json={"query": "stock of a tap", "top_k": 3})
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_external_api_user, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
    assert provider == [], "the tool search embedded a query it can no longer use"


def test_f2_the_assistant_agent_route_skips_tool_rag(db, monkeypatch):
    from app.services import ai_assistant_service as svc

    owner = [c for c in vars(svc).values() if isinstance(c, type) and "_rag_select_tools" in vars(c)]
    assert owner, "no class carries _rag_select_tools"
    cls = owner[0]
    instance = cls.__new__(cls)
    instance.db = db

    def boom(*a, **k):
        raise AssertionError("tool RAG ran")

    monkeypatch.setattr(cls, "_embed_query", boom, raising=False)
    monkeypatch.setattr(svc.EmbeddingReadService, "search_tool_candidates", boom)
    selected, sources = instance._rag_select_tools(standalone_query="stock of a tap", enabled_tools=["a_tool"], top_k=1)
    assert isinstance(selected, list) and isinstance(sources, list)


# ================================================================== F-4: which failures count; what the guard demands
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(("http", 401), id="401"),
        pytest.param(("http", 403), id="403"),
        pytest.param(("http", 429), id="429"),
        pytest.param(("http", 500), id="500"),
        pytest.param(("http", 503), id="503"),
        pytest.param(("plain", "No Gemini API key is configured."), id="missing-key"),
    ],
)
def test_f4_auth_rate_limit_server_and_missing_key_errors_do_not_count_against_documents(db, monkeypatch, error):
    from app.services import embedding_client, embedding_settings
    from app.services.embedding_backfill_service import backfill_records

    docs = [_doc(db, "promotion", n) for n in range(3)]
    db.commit()  # the run rolls back on a failed request; seeded rows must be committed to the test savepoint
    kind, detail = error

    def boom(session, texts, model, **kw):
        if kind == "http":
            raise embedding_client.EmbeddingHTTPError(f"zzt {detail}", detail)
        raise RuntimeError(detail)

    monkeypatch.setattr(embedding_settings, "embed_for_model", boom)
    try:
        backfill_records(db, GEM, sleep=lambda s: None)
    except Exception:  # noqa: BLE001 - a run may stop by raising or by returning; only the counts matter
        pass
    assert [_failures(db, d, GEM) for d in docs] == [0, 0, 0]


def test_f4_a_per_document_error_still_counts(db, monkeypatch):
    from app.services import embedding_client, embedding_settings
    from app.services.embedding_backfill_service import backfill_records

    doc = _doc(db, "promotion", 1)
    db.commit()

    def bad_input(session, texts, model, **kw):
        raise embedding_client.EmbeddingHTTPError("zzt 400 input too long", 400)

    monkeypatch.setattr(embedding_settings, "embed_for_model", bad_input)
    backfill_records(db, GEM, sleep=lambda s: None)
    assert _failures(db, doc, GEM) == 1


@pytest.fixture
def ddl_spy(monkeypatch):
    from app.services import embedding_indexes

    calls: list[str] = []
    monkeypatch.setattr(embedding_indexes, "index_ddl", lambda model: calls.append(model) or [])
    return calls


def _search_model(db):
    from app.models.user import SystemSetting

    db.expire_all()
    return db.query(SystemSetting).first().embedding_records_search_model


def test_f4_the_guard_refuses_when_the_target_model_has_no_current_chunk_at_all(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db)
    _doc(db, "promotion", 1, failures={GEM: 3})
    _doc(db, "promotion", 2, failures={GEM: 3})
    assert apply_search_model_guard(db, GEM) is False
    assert _search_model(db) == M3S


def test_f4_the_guard_refuses_when_failed_documents_are_one_percent_or_more(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db)
    for n in range(98):
        _chunk(db, _doc(db, "promotion", n), GEM)
    _doc(db, "promotion", 998, failures={GEM: 3})
    _doc(db, "promotion", 999, failures={GEM: 3})
    assert apply_search_model_guard(db, GEM) is False
    assert _search_model(db) == M3S


def test_f4_the_guard_flips_with_failed_documents_under_one_percent(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db)
    for n in range(200):
        _chunk(db, _doc(db, "promotion", n), GEM)
    _doc(db, "promotion", 998, failures={GEM: 3})
    assert apply_search_model_guard(db, GEM) is True
    assert _search_model(db) == GEM


def test_f4_the_guard_refuses_when_the_setting_moved_to_another_model_meanwhile(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db, embedding_provider="openai", embedding_model=M3S)  # switched back while the job ran
    for n in range(5):
        _chunk(db, _doc(db, "promotion", n), GEM)
    assert apply_search_model_guard(db, GEM) is False
    assert _search_model(db) == M3S


def test_f4_records_backfill_needs_system_settings_update_not_just_lookup_sets_edit(client, allow, monkeypatch):
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: MagicMock(id="j"))
    monkeypatch.setattr(queue_service, "redis_conn", MagicMock())
    url = "/api/v1/system/embeddings/records-backfill"
    allow.add(EDIT)
    assert client.post(url, json={"action": "start"}).status_code == 403
    allow.add(SETTINGS_UPDATE)
    assert client.post(url, json={"action": "start"}).status_code == 202


# ================================================================== F-5: iterative scan on the resolver reads
def _sql_seen(db, fn):
    seen: list[str] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", grab)
    try:
        fn()
    finally:
        event.remove(bind, "before_cursor_execute", grab)
    return seen


@pytest.fixture
def resolver_embed(monkeypatch):
    import app.services.embedding_settings as embedding_settings
    import app.services.entity_resolver as er

    monkeypatch.setattr(er, "_SEARCH_SEAMS", {})
    monkeypatch.setattr(embedding_settings, "embed_search_texts", lambda texts, model, **kw: [pad(1.0) for _ in texts])
    return er


def test_f5_tier3_narrowed_to_a_non_hot_source_sets_the_iterative_scan(db, resolver_embed):
    from app.services.company_scope import set_company_scope

    set_company_scope(db, None)
    seen = _sql_seen(db, lambda: resolver_embed._tier3_embedding_lookup(db, f"zzt promo {uuid.uuid4().hex}", frozenset({"promotion"})))
    assert any("iterative_scan" in s for s in seen), "no SET LOCAL hnsw.iterative_scan before the narrowed read"


def test_f5_rag_phrase_narrowed_to_a_non_hot_source_sets_the_iterative_scan(db, resolver_embed):
    from app.services.company_scope import set_company_scope

    set_company_scope(db, None)
    seen = _sql_seen(db, lambda: resolver_embed._rag_resolve_phrase(db, f"zzt promo {uuid.uuid4().hex}", frozenset({"promotion"})))
    assert any("iterative_scan" in s for s in seen)


def test_f5_a_read_of_hot_sources_only_does_not_need_it(db, resolver_embed):
    from app.services.company_scope import set_company_scope

    set_company_scope(db, None)
    seen = _sql_seen(db, lambda: resolver_embed._tier3_embedding_lookup(db, f"zzt spec {uuid.uuid4().hex}", frozenset({"product"})))
    assert not any("iterative_scan" in s for s in seen)


# ================================================================== F-6 / F-12: settings PUT
def test_f6_a_failed_enqueue_is_logged_and_the_save_still_returns_200(client, db, allow, monkeypatch):
    from app.api.v1.user_management import settings as settings_api
    from app.models.user import SystemSetting
    from app.services import queue_service

    allow.add(EDIT_SETTINGS)
    _setting(db, embedding_provider="openai", embedding_model=M3S)

    def boom(*a, **k):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(queue_service, "enqueue_job", boom)
    monkeypatch.setattr(settings_api, "enqueue_job", boom, raising=False)
    resp = client.put(f"{SETTINGS}/general", json={"embedding_provider": "gemini", "embedding_model": GEM})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(SystemSetting).first().embedding_model == GEM


@pytest.mark.parametrize("bad", ["bad model!", "x" * 129, "a/b", "m\n", ""])
def test_f12_an_embedding_model_outside_the_allowed_pattern_is_422(client, db, allow, bad):
    allow.add(EDIT_SETTINGS)
    _setting(db)
    assert client.put(f"{SETTINGS}/general", json={"embedding_model": bad}).status_code == 422


def test_f12_a_well_formed_model_name_is_accepted(client, db, allow, monkeypatch):
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: MagicMock(id="j"))
    allow.add(EDIT_SETTINGS)
    _setting(db)
    assert client.put(f"{SETTINGS}/general", json={"embedding_model": "text-embedding-3-large.v2_x"}).status_code == 200


# ================================================================== F-7: the script matches types by name or code
def _script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "move_prompt_synonyms.py"
    spec = importlib.util.spec_from_file_location("move_prompt_synonyms_r1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_f7_an_entry_with_no_attachment_type_is_listed_unmatched_and_creates_no_option(db):
    from app.models.lookup import LookupOption

    script = _script()
    result = script.run(db, apply=True)
    assert db.query(LookupOption).count() == 0
    assert "unmatched" in json.dumps(result, default=str).lower()


def test_f7_a_type_is_matched_by_its_code_and_the_words_land_on_its_option(db):
    from app.models.lookup import LookupOption, LookupOptionKeyword
    from app.models.resources import AttachmentType

    db.add(AttachmentType(id=str(uuid.uuid4()), code="photo", type_name="Product Photos", allowed_extensions="jpg"))
    db.flush()
    _script().run(db, apply=True)
    db.expire_all()
    options = db.query(LookupOption).all()
    assert {o.value for o in options} <= {"Product Photos", "photo"} and options, [o.value for o in options]
    words = {k.keyword for k in db.query(LookupOptionKeyword).all()}
    assert {"gambar", "foto"} <= words


# ================================================================== F-8: alias targets offer code and name
def _alias_set(db, set_key):
    from app.models.lookup import LookupSet

    s = LookupSet(id=str(uuid.uuid4()), set_key=set_key, name=f"ZZT {set_key}", is_active=True)
    db.add(s)
    db.flush()
    return s


def test_f8_attachment_type_targets_offer_both_the_code_and_the_name(client, db, allow):
    from app.models.resources import AttachmentType

    allow.add(VIEW)
    db.add(AttachmentType(id=str(uuid.uuid4()), code="ZZT-R1-PH", type_name="ZZT R1 Photo", allowed_extensions="jpg"))
    s = _alias_set(db, "attachment_type_alias")
    values = {t["value"] for t in client.get(f"{SETS}/{s.id}/alias-targets").json()}
    assert {"ZZT-R1-PH", "ZZT R1 Photo"} <= values


def test_f8_an_option_keyed_by_the_code_or_the_name_is_not_orphaned(client, db, allow):
    from app.models.lookup import LookupOption
    from app.models.resources import AttachmentType

    allow.add(VIEW)
    db.add(AttachmentType(id=str(uuid.uuid4()), code="ZZT-R1-DR", type_name="ZZT R1 Drawing", allowed_extensions="pdf"))
    s = _alias_set(db, "attachment_type_alias")
    for value in ("ZZT-R1-DR", "ZZT R1 Drawing", "ZZT R1 Gone"):
        db.add(LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=value, label=value, is_active=True))
    db.flush()
    flags = {o["value"]: o["orphaned"] for o in client.get(f"{SETS}/{s.id}/options").json()["data"]}
    assert flags == {"ZZT-R1-DR": False, "ZZT R1 Drawing": False, "ZZT R1 Gone": True}


# ================================================================== F-9: counts in SQL
def test_f9_overview_does_not_load_document_metadata_to_count_remaining_and_failed(client, db, allow):
    allow.add(VIEW)
    _setting(db)
    for n in range(3):
        _doc(db, "promotion", n, failures={GEM: 3} if n == 0 else None)
    body = None
    seen = _sql_seen(db, lambda: None)
    seen = _sql_seen(db, lambda: client.get("/api/v1/system/embeddings/overview"))
    body = client.get("/api/v1/system/embeddings/overview").json()
    assert body["guard"]["failed"] == 1 and body["guard"]["remaining"] == 2
    loading = [s for s in seen if s.lstrip().upper().startswith("SELECT") and "embedding_documents.metadata" in s]
    assert loading == [], "a per-document metadata load is still counting remaining / failed"


# ================================================================== F-10: alias targets of brands follow the caller's scope
def test_f10_brand_alias_targets_list_only_the_callers_scope(client, db, allow, scope):
    from app.models.company import Company
    from app.models.product import Brand
    from app.services.company_scope import set_company_scope

    allow.add(VIEW)
    set_company_scope(db, None)
    a = Company(id=str(uuid.uuid4()), name="ZZT R1 A", code=f"R1A{uuid.uuid4().hex[:5]}")
    b = Company(id=str(uuid.uuid4()), name="ZZT R1 B", code=f"R1B{uuid.uuid4().hex[:5]}")
    db.add_all([a, b])
    db.flush()
    db.add_all([
        Brand(id=str(uuid.uuid4()), brand_code="ZZT-R1-OWN", brand_name="ZZT R1 Own", company_id=a.id),
        Brand(id=str(uuid.uuid4()), brand_code="ZZT-R1-OTHER", brand_name="ZZT R1 Other", company_id=b.id),
    ])
    s = _alias_set(db, "brand_alias")
    scope["value"] = frozenset({a.id})
    values = {t["value"] for t in client.get(f"{SETS}/{s.id}/alias-targets").json()}
    assert "ZZT-R1-OWN" in values and "ZZT-R1-OTHER" not in values


# ================================================================== F-13 (BE nits)
def test_f13_external_rag_search_checks_the_search_models_provider_key_and_reports_that_model(db, provider, monkeypatch):
    """A gemini search model needs no OpenAI key, and the response names the model that was searched."""
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.database import get_db
    from app.dependencies import get_external_api_user
    from app.main import app
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    _setting(db, embedding_provider="gemini", embedding_model=GEM, embedding_records_search_model=GEM)
    set_company_scope(db, None)
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_external_api_user] = lambda: {"id": str(uuid.uuid4()), "email": "zzt@api.test"}
    app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(db, None)
    try:
        with external_permissions_granted():
            resp = TestClient(app).post("/api/v1/external/rag/search", json={"query": "toilet", "top_k": 3})
    finally:
        for dep in (get_db, get_external_api_user, apply_company_scope):
            app.dependency_overrides.pop(dep, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["model"] == GEM


def test_f13_the_guards_index_build_raises_maintenance_work_mem_for_its_session(db, monkeypatch):
    from app.services import embedding_indexes
    import app.database as database
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db)
    _chunk(db, _doc(db, "promotion", 1), GEM)
    statements: list[str] = []

    class _Conn:
        def execution_options(self, **kw):
            return self

        def execute(self, stmt, *a, **k):
            statements.append(str(stmt))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(database, "engine", _Engine())
    assert apply_search_model_guard(db, GEM) is True
    ddl = [s for s in statements if "CREATE INDEX" in s.upper()]
    assert ddl, statements
    first_ddl = statements.index(ddl[0])
    assert any("maintenance_work_mem" in s and "512MB" in s for s in statements[:first_ddl]), statements


def test_f13_the_lookup_set_api_says_whether_a_set_is_an_alias_set(client, db, allow):
    allow.add(VIEW)
    alias = _alias_set(db, "brand_alias")
    plain = _alias_set(db, "zzt_r1_plain")
    assert client.get(f"{SETS}/{alias.id}").json()["alias_set"] is True
    assert client.get(f"{SETS}/{plain.id}").json()["alias_set"] is False
    listed = {s["id"]: s.get("alias_set") for s in client.get(SETS).json()["data"]}
    assert listed[alias.id] is True and listed[plain.id] is False
