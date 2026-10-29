"""LOOKUP-EMBED-CENTRAL slice 3 red tests: dual write, backfill job, search-model guard (AC-LEC-8, 13, 14).

Postgres only (blank_session), every row seeded here. No network: the one embeddings transport
(httpx.Client.send) is stubbed and records which model each request asked for (OpenAI: body["model"],
Gemini: the model in the URL path). Vectors are tiny and padded to 1536.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_slice3.py -q -n 2
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime

import httpx
import pytest

from app.models.embeddings import EmbeddingChunk, EmbeddingDocument, EmbeddingQueue
from app.services.company_scope import set_company_scope
from app.services.embedding_change_listener import register_embedding_change_listeners
from tests._pg_fixture import TEST_PREFIX, blank_session

register_embedding_change_listeners()

M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"
BASE = "/api/v1/user-management/settings"


def pad(*head: float) -> list[float]:
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


class Transport:
    """Stub of httpx.Client.send. `fail_models` answer HTTP 500; every request is recorded."""

    def __init__(self, fail_models=()):
        self.fail_models = set(fail_models)
        self.requests: list[tuple[str, list[str]]] = []  # (model, texts)

    def send(self, request):
        body = json.loads(request.content)
        url = str(request.url)
        if "batchEmbedContents" in url:
            model = re.search(r"/models/([^:/]+):batchEmbedContents", url).group(1)
            texts = ["".join(p.get("text", "") for p in r["content"]["parts"]) for r in body["requests"]]
        else:
            model = body["model"]
            texts = list(body["input"])
        self.requests.append((model, texts))
        if model in self.fail_models:
            return httpx.Response(500, json={"error": "zzt provider down"}, request=request)
        vecs = [pad(1.0, 0.1 * (i % 7)) for i, _ in enumerate(texts)]
        if "batchEmbedContents" in url:
            return httpx.Response(200, json={"embeddings": [{"values": v} for v in vecs]}, request=request)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}, request=request)

    def models(self):
        return [m for m, _ in self.requests]

    def texts_for(self, model):
        return [t for m, ts in self.requests if m == model for t in ts]


@pytest.fixture
def transport(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", "zzt-gemini", raising=False)

    def make(fail_models=()):
        t = Transport(fail_models)
        monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: t.send(request))
        return t

    return make


# ------------------------------------------------------------------ seed helpers
def _setting(db, *, model=None, provider=None, search=M3S, rpm=20):
    from app.models.user import SystemSetting

    row = SystemSetting(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} LEC3 Co", embedding_provider=provider, embedding_model=model,
        embedding_records_search_model=search, embedding_backfill_rpm=rpm,
    )
    db.add(row)
    db.flush()
    return row


def _doc(db, n, *, source_type="promotion", active=True, text=None, failures=None):
    meta = {"embed_failures": failures} if failures else {}
    d = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type=source_type, source_id=f"zzt-lec3-{source_type}-{n}-{uuid.uuid4().hex[:6]}",
        source_key=f"K{n}", title=f"T{n}", body_text=text or f"zzt lec3 body {source_type} {n}",
        metadata_json=meta, source_hash="h", is_active=active,
    )
    db.add(d)
    db.flush()
    return d


def _chunk(db, doc, model, *, current=True):
    c = EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=doc.id, source_type=doc.source_type, source_id=doc.source_id,
        chunk_index=0, chunk_text=doc.body_text, chunk_hash="h", embedding=pad(1.0), model_name=model,
        model_version="1", embedding_provider="gemini" if model == GEM else "openai", source_hash="h",
        is_current=current,
    )
    db.add(c)
    db.flush()
    return c


def _current(db, doc, model):
    db.expire_all()
    return (
        db.query(EmbeddingChunk)
        .filter_by(source_type=doc.source_type, source_id=doc.source_id, model_name=model, is_current=True)
        .all()
    )


def _norm_failed(item):
    if isinstance(item, dict):
        return item["source_type"], item["source_id"], item["failures"]
    if isinstance(item, (tuple, list)):
        return tuple(item[:3])
    return item.source_type, item.source_id, item.failures


# ================================================================== AC-LEC-8 (dual write)
@pytest.fixture
def worker(db, monkeypatch):
    from app.services import embedding_worker

    monkeypatch.setattr(embedding_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    return embedding_worker


def _promotion_item(db):
    from app.models.marketing import Promotion

    promo = Promotion(description="ZZT LEC3 dual write", start_date=date(2026, 10, 1), end_date=date(2026, 12, 1), is_active=True)
    db.add(promo)
    db.flush()
    now = datetime.utcnow()
    item = EmbeddingQueue(
        id=str(uuid.uuid4()), source_type="promotion", source_id=str(promo.id), event_type="promotion.updated",
        event_version=1, payload={}, status="pending", retry_count=0, available_at=now, created_at=now,
    )
    db.add(item)
    db.flush()
    return promo, item


def _chunks_of(db, source_id):
    db.expire_all()
    return db.query(EmbeddingChunk).filter_by(source_type="promotion", source_id=str(source_id), is_current=True).all()


def test_ac_lec_8_write_models_lists_setting_model_first_then_a_different_search_model(db):
    from app.services.embedding_settings import write_models

    _setting(db, provider="gemini", model=GEM, search=M3S)
    assert write_models(db) == [GEM, M3S]


def test_ac_lec_8_write_models_is_one_model_when_both_are_equal(db):
    from app.services.embedding_settings import write_models

    _setting(db, provider="openai", model=M3S, search=M3S)
    assert write_models(db) == [M3S]


def test_ac_lec_8_worker_writes_one_current_chunk_per_model(db, worker, transport):
    _setting(db, provider="gemini", model=GEM, search=M3S)
    promo, item = _promotion_item(db)
    t = transport()
    worker.process_embedding_queue_item(item.id)
    assert sorted(c.model_name for c in _chunks_of(db, promo.id)) == sorted([GEM, M3S])
    assert sorted(t.models()) == sorted([GEM, M3S]), t.models()  # one embed call per model


def test_ac_lec_8_worker_writes_one_model_when_setting_and_search_model_are_equal(db, worker, transport):
    _setting(db, provider="openai", model=M3S, search=M3S)
    promo, item = _promotion_item(db)
    t = transport()
    worker.process_embedding_queue_item(item.id)
    assert [c.model_name for c in _chunks_of(db, promo.id)] == [M3S]
    assert t.models() == [M3S]


def test_ac_lec_8_a_failing_gemini_embed_does_not_block_the_search_model_chunk(db, worker, transport):
    _setting(db, provider="gemini", model=GEM, search=M3S)
    promo, item = _promotion_item(db)
    transport(fail_models=[GEM])
    worker.process_embedding_queue_item(item.id)
    assert [c.model_name for c in _chunks_of(db, promo.id)] == [M3S]


# ================================================================== AC-LEC-13 (backfill)
def _backfill(db, model, **kw):
    from app.services.embedding_backfill_service import backfill_records

    sleeps: list[float] = []
    kw.setdefault("sleep", sleeps.append)
    result = backfill_records(db, model, **kw)
    return result, sleeps


def test_ac_lec_13_embeds_only_active_keep_set_documents_without_a_current_chunk(db, transport):
    done = _doc(db, 1)
    _chunk(db, done, GEM)
    todo = _doc(db, 2, source_type="certificate")
    inactive = _doc(db, 3, active=False)
    dropped = _doc(db, 4, source_type="order")
    stale = _doc(db, 5)
    _chunk(db, stale, GEM, current=False)  # only a superseded chunk: still needs one
    _chunk(db, _doc(db, 6), M3S)  # a chunk of ANOTHER model does not count as done for GEM
    t = transport()
    result, _ = _backfill(db, GEM)
    sent = t.texts_for(GEM)
    assert todo.body_text in sent and stale.body_text in sent
    assert done.body_text not in sent and inactive.body_text not in sent and dropped.body_text not in sent
    assert len(_current(db, todo, GEM)) == 1
    assert _current(db, dropped, GEM) == [] and _current(db, inactive, GEM) == []
    assert result.remaining == 0 and result.complete is True


def test_ac_lec_13_250_texts_go_in_3_requests_with_a_pause_of_60_over_rpm(db, transport):
    for n in range(250):
        _doc(db, n)
    t = transport()
    result, sleeps = _backfill(db, M3S, rpm=20, batch_size=100)
    assert [len(ts) for _m, ts in t.requests] == [100, 100, 50]
    assert sleeps and set(sleeps) == {3.0} and len(sleeps) in (2, 3), sleeps
    assert result.embedded == 250 and result.remaining == 0 and result.complete is True


def test_ac_lec_13_rpm_defaults_to_the_setting(db, transport):
    _setting(db, rpm=30)
    for n in range(120):
        _doc(db, n)
    transport()
    _result, sleeps = _backfill(db, M3S)
    assert sleeps and set(sleeps) == {2.0}, sleeps


def test_ac_lec_13_a_rerun_embeds_nothing_new(db, transport):
    for n in range(5):
        _doc(db, n)
    t = transport()
    _backfill(db, GEM)
    first = len(t.requests)
    result, _ = _backfill(db, GEM)
    assert len(t.requests) == first
    assert result.embedded == 0 and result.remaining == 0 and result.complete is True


def test_ac_lec_13_a_failing_request_counts_per_document_and_three_failures_mark_it_failed(db, transport):
    from app.services.embedding_backfill_service import failed_documents

    a, b = _doc(db, 1), _doc(db, 2)
    t = transport(fail_models=[GEM])
    for run in (1, 2):
        _backfill(db, GEM)
        db.expire_all()
        assert db.get(EmbeddingDocument, a.id).metadata_json["embed_failures"][GEM] == run
        assert failed_documents(db, GEM) == []
    result, _ = _backfill(db, GEM)
    db.expire_all()
    assert db.get(EmbeddingDocument, b.id).metadata_json["embed_failures"][GEM] == 3
    listed = {_norm_failed(i) for i in failed_documents(db, GEM)}
    assert listed == {("promotion", a.source_id, 3), ("promotion", b.source_id, 3)}
    before = len(t.requests)
    again, _ = _backfill(db, GEM)
    assert len(t.requests) == before, "a document that failed 3 times was retried"
    assert again.remaining == 0 and again.embedded == 0


def test_ac_lec_13_failures_are_kept_per_model(db, transport):
    d = _doc(db, 1, failures={GEM: 3})
    t = transport()
    _backfill(db, GEM)
    assert t.texts_for(GEM) == []  # failed for GEM: skipped
    _backfill(db, M3S)
    assert d.body_text in t.texts_for(M3S)  # not failed for 3-small


def test_ac_lec_13_should_stop_between_requests_leaves_the_rest_remaining(db, transport):
    for n in range(250):
        _doc(db, n)
    t = transport()
    result, _ = _backfill(db, M3S, batch_size=100, should_stop=lambda: len(t.requests) >= 1)
    assert len(t.requests) == 1
    assert result.remaining == 150 and result.complete is False


def test_ac_lec_13_dropped_sources_are_never_touched(db, transport):
    o = _doc(db, 1, source_type="order")
    c = _doc(db, 2, source_type="customer")
    t = transport()
    result, _ = _backfill(db, M3S)
    assert t.requests == [] and result.remaining == 0
    assert _current(db, o, M3S) == [] and _current(db, c, M3S) == []


# ================================================================== AC-LEC-14 (guard)
@pytest.fixture
def ddl_spy(monkeypatch):
    """The guard builds the model's indexes with CONCURRENTLY DDL, which cannot run in a test transaction:
    index_ddl is replaced by a recorder returning no statements."""
    from app.services import embedding_indexes

    calls: list[str] = []

    def spy(model):
        calls.append(model)
        return []

    monkeypatch.setattr(embedding_indexes, "index_ddl", spy)
    return calls


def _search_model(db):
    from app.models.user import SystemSetting

    db.expire_all()
    return db.query(SystemSetting).first().embedding_records_search_model


def test_ac_lec_14_guard_waits_while_a_keep_set_document_lacks_the_model(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db, provider="gemini", model=GEM, search=M3S)
    _chunk(db, _doc(db, 1), GEM)
    _doc(db, 2)  # no gemini chunk
    _doc(db, 3, source_type="order")  # dropped source: never blocks
    _doc(db, 4, active=False)  # inactive: never blocks
    assert apply_search_model_guard(db, GEM) is False
    assert _search_model(db) == M3S
    assert ddl_spy == []


def test_ac_lec_14_guard_flips_when_every_document_has_the_model_and_builds_the_indexes(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db, provider="gemini", model=GEM, search=M3S)
    _chunk(db, _doc(db, 1), GEM)
    _chunk(db, _doc(db, 2, source_type="form"), GEM)
    assert apply_search_model_guard(db, GEM) is True
    assert _search_model(db) == GEM
    assert ddl_spy == [GEM]


def test_ac_lec_14_a_failed_document_does_not_block_the_flip_and_is_listed(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard, failed_documents

    _setting(db, provider="gemini", model=GEM, search=M3S)
    _chunk(db, _doc(db, 1), GEM)
    bad = _doc(db, 2, failures={GEM: 3})
    assert apply_search_model_guard(db, GEM) is True
    assert _search_model(db) == GEM
    assert [_norm_failed(i) for i in failed_documents(db, GEM)] == [("promotion", bad.source_id, 3)]


def test_ac_lec_14_a_document_with_fewer_than_three_failures_still_blocks(db, ddl_spy):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db, provider="gemini", model=GEM, search=M3S)
    _doc(db, 1, failures={GEM: 2})
    assert apply_search_model_guard(db, GEM) is False
    assert _search_model(db) == M3S


def test_ac_lec_14_switching_back_embeds_only_documents_without_a_current_chunk_of_the_old_model(db, ddl_spy, transport):
    from app.services.embedding_backfill_service import apply_search_model_guard

    _setting(db, provider="gemini", model=GEM, search=M3S)
    have_both = _doc(db, 1)
    _chunk(db, have_both, GEM)
    _chunk(db, have_both, M3S)
    gem_only = _doc(db, 2)
    _chunk(db, gem_only, GEM)
    assert apply_search_model_guard(db, GEM) is True  # flipped to gemini
    from app.models.user import SystemSetting

    db.query(SystemSetting).update({"embedding_provider": "openai", "embedding_model": M3S})
    db.flush()
    t = transport()
    result, _ = _backfill(db, M3S)
    assert t.texts_for(M3S) == [gem_only.body_text]
    assert result.embedded == 1 and result.complete is True
    assert apply_search_model_guard(db, M3S) is True
    assert _search_model(db) == M3S


# ================================================================== task + settings PUT
def test_ac_lec_14_run_records_backfill_uses_the_setting_model_then_the_guard(db, ddl_spy, transport, monkeypatch):
    import app.database as database
    from app.tasks import embedding_backfill

    _setting(db, provider="gemini", model=GEM, search=M3S)
    docs = [_doc(db, n) for n in range(3)]
    t = transport()
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(embedding_backfill, "SessionLocal", lambda: db, raising=False)
    monkeypatch.setattr(db, "close", lambda: None)
    embedding_backfill.run_records_backfill()
    assert set(t.models()) == {GEM}
    assert all(len(_current(db, d, GEM)) == 1 for d in docs)
    assert _search_model(db) == GEM
    assert ddl_spy == [GEM]


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-lec3-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} LEC3", avatar_storage_provider="s3",
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


@pytest.fixture
def enqueued(monkeypatch, client):
    from app.services import queue_service
    from app.services.user_service import UserPermissionService
    from app.api.v1.user_management import settings as settings_api

    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    calls: list[tuple] = []

    class _Job:
        id = "zzt-job"

    def fake(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake)
    monkeypatch.setattr(settings_api, "enqueue_job", fake, raising=False)
    return calls


def test_ac_lec_13_changing_the_embedding_model_in_settings_enqueues_the_backfill_once(db, client, enqueued):
    from app.tasks.embedding_backfill import run_records_backfill

    _setting(db, provider="openai", model=M3S)
    resp = client.put(f"{BASE}/general", json={"embedding_provider": "gemini", "embedding_model": GEM})
    assert resp.status_code == 200, resp.text
    assert len(enqueued) == 1, enqueued
    func, _args, kwargs = enqueued[0]
    assert func is run_records_backfill
    assert kwargs.get("queue_name", "imports") == "imports"


def test_ac_lec_13_saving_the_same_model_enqueues_nothing(db, client, enqueued):
    _setting(db, provider="gemini", model=GEM)
    resp = client.put(f"{BASE}/general", json={"embedding_provider": "gemini", "embedding_model": GEM})
    assert resp.status_code == 200, resp.text
    assert enqueued == []
