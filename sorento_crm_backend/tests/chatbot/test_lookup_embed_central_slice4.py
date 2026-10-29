"""LOOKUP-EMBED-CENTRAL slice 4 red tests: lookup words in the store, PROMPT_SYNONYMS gone (AC-LEC-15..18).

Postgres only (blank_session); every row is seeded here. No network: httpx.Client.send is stubbed and records the
texts of every embeddings request. Vectors are tiny and padded to 1536.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/chatbot/test_lookup_embed_central_slice4.py -q -n 2

Script contract assumed (same as scripts/add_zh_category_synonyms.py): module `scripts/move_prompt_synonyms.py`
with `plan(db)` and `run(db, *, apply=False) -> {"plan": [...], "added": int}`; the caller commits.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import uuid

import httpx
import numpy as np
import pytest
from sqlalchemy import event

from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.models.product import ProductCategory
from app.services.chatbot.head import lookup_lists as ll
from app.services.company_scope import set_company_scope
from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
BACKEND = pathlib.Path(__file__).resolve().parents[2]


def pad(*head: float) -> list[float]:
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


class Transport:
    def __init__(self):
        self.requests: list[list[str]] = []

    def send(self, request):
        body = json.loads(request.content)
        texts = list(body["input"])
        self.requests.append(texts)
        vecs = [pad(1.0, (int(hashlib.md5(t.encode()).hexdigest()[:4], 16) % 97) / 10.0) for t in texts]
        return httpx.Response(200, json={"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}, request=request)

    def sent(self):
        return [t for r in self.requests for t in r]


@pytest.fixture
def transport(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)
    t = Transport()
    monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: t.send(request))
    return t


@pytest.fixture(autouse=True)
def fresh_lookup_cache(monkeypatch):
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})


def _setting(db):
    from app.models.user import SystemSetting

    row = SystemSetting(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} LEC4 Co", embedding_provider="openai", embedding_model=M3S,
        embedding_records_search_model=M3S,
    )
    db.add(row)
    db.flush()
    return row


def _category(db, name, *, synonyms=(), class_label=None, active=True, code=None):
    c = ProductCategory(
        id=str(uuid.uuid4()), category_code=code or f"ZZT4-{uuid.uuid4().hex[:6]}", category_name=name,
        class_label=class_label, search_synonyms=list(synonyms), is_active=active, is_searchable=True,
    )
    db.add(c)
    db.flush()
    return c


def _lookup_docs(db, active=None):
    db.expire_all()
    q = db.query(EmbeddingDocument).filter(EmbeddingDocument.source_type == "lookup_word")
    if active is not None:
        q = q.filter(EmbeddingDocument.is_active.is_(active))
    return {d.source_id: d for d in q.all()}


def _chunks(db, doc, *, current=True):
    db.expire_all()
    q = db.query(EmbeddingChunk).filter_by(document_id=doc.id)
    if current:
        q = q.filter(EmbeddingChunk.is_current.is_(True))
    return q.all()


def _sync(db, **kw):
    from app.services.chatbot.head import lookup_word_store

    return lookup_word_store.sync_lookup_words(db, **kw)


def _row_texts(db, list_name, key):
    rows = ll.load_rows(db, include_salespeople=True, include_customers=True)
    (row,) = [r for r in rows if r.list_name == list_name and str(r.key) == str(key)]
    return row.texts


# ================================================================== AC-LEC-15
def test_ac_lec_15_the_source_constant():
    from app.services.chatbot.head import lookup_word_store

    assert lookup_word_store.LOOKUP_SOURCE == "lookup_word"


def test_ac_lec_15_sync_makes_one_document_per_row_with_one_chunk_per_text(db, transport):
    from app.models.resources import AttachmentType

    _setting(db)
    c1 = _category(db, "ZZT4 Alpha Closet", synonyms=["zzt4 alpha word"], class_label="Water Closet")
    c2 = _category(db, "ZZT4 Beta Basin", synonyms=["zzt4 beta word"])
    db.add(AttachmentType(id=str(uuid.uuid4()), code="ZZT4-PHOTO", type_name="ZZT4 Photo", allowed_extensions="jpg"))
    db.flush()

    result = _sync(db)

    docs = _lookup_docs(db, active=True)
    for cat in (c1, c2):
        doc = docs[f"category:{cat.id}"]
        texts = _row_texts(db, "category", cat.id)
        assert doc.company_id is None and doc.title == cat.category_name
        assert doc.body_text == "\n".join(texts)
        assert re.fullmatch(r"[0-9a-f]{64}", doc.source_hash)
        chunks = _chunks(db, doc)
        assert sorted(c.chunk_text for c in chunks) == sorted(texts)
        assert {c.model_name for c in chunks} == {M3S}
    assert any(sid.startswith("file_type:") for sid in docs), sorted(docs)
    assert {"sales_channel:dealer", "sales_channel:project"} <= set(docs)
    assert result.created == len(docs) and result.embedded > 0


def test_ac_lec_15_five_rows_sharing_a_text_cost_one_embed_of_it(db, transport):
    _setting(db)
    cats = [_category(db, f"ZZT4 Shared {n}", synonyms=["zzt4 shared word"]) for n in range(5)]
    _sync(db)
    assert transport.sent().count("zzt4 shared word") == 1
    docs = _lookup_docs(db, active=True)
    for cat in cats:
        assert "zzt4 shared word" in [c.chunk_text for c in _chunks(db, docs[f"category:{cat.id}"])]


# ================================================================== AC-LEC-16
def test_ac_lec_16_a_second_sync_with_no_change_embeds_nothing(db, transport):
    _setting(db)
    _category(db, "ZZT4 Stable", synonyms=["zzt4 stable word"])
    _sync(db)
    sent = len(transport.requests)
    again = _sync(db)
    assert len(transport.requests) == sent
    assert (again.created, again.updated, again.retired, again.embedded) == (0, 0, 0, 0)


def test_ac_lec_16_a_changed_synonym_rebuilds_only_that_document(db, transport):
    _setting(db)
    changed = _category(db, "ZZT4 Changed", synonyms=["zzt4 old word"])
    other = _category(db, "ZZT4 Other", synonyms=["zzt4 other word"])
    _sync(db)
    docs = _lookup_docs(db)
    other_ids = {c.id for c in _chunks(db, docs[f"category:{other.id}"])}
    before = len(transport.sent())

    changed.search_synonyms = ["zzt4 new word"]
    db.flush()
    result = _sync(db)

    docs = _lookup_docs(db)
    assert result.updated == 1 and result.created == 0 and result.retired == 0
    assert transport.sent()[before:] == ["zzt4 new word"]
    assert {c.id for c in _chunks(db, docs[f"category:{other.id}"])} == other_ids
    texts = [c.chunk_text for c in _chunks(db, docs[f"category:{changed.id}"])]
    assert "zzt4 new word" in texts and "zzt4 old word" not in texts


@pytest.mark.parametrize("how", ["delete", "deactivate"])
def test_ac_lec_16_a_category_that_goes_away_retires_its_document(db, transport, how):
    _setting(db)
    gone = _category(db, "ZZT4 Gone", synonyms=["zzt4 gone word"])
    keep = _category(db, "ZZT4 Kept", synonyms=["zzt4 kept word"])
    _sync(db)
    if how == "delete":
        db.delete(gone)
    else:
        gone.is_active = False
    db.flush()
    result = _sync(db)
    docs = _lookup_docs(db)
    doc = docs[f"category:{gone.id}"]
    assert result.retired == 1
    assert doc.is_active is False and _chunks(db, doc) == []
    assert docs[f"category:{keep.id}"].is_active is True


def test_ac_lec_16_a_new_category_is_picked_up(db, transport):
    _setting(db)
    _category(db, "ZZT4 First", synonyms=["zzt4 first word"])
    _sync(db)
    fresh = _category(db, "ZZT4 Fresh", synonyms=["zzt4 fresh word"])
    result = _sync(db)
    assert result.created == 1
    assert f"category:{fresh.id}" in _lookup_docs(db, active=True)
    assert "zzt4 fresh word" in transport.sent()


# ================================================================== AC-LEC-17
def test_ac_lec_17_load_lookup_vectors_fills_the_cache_with_one_select_and_no_embed(db, transport):
    from app.services.chatbot.head import lookup_word_store

    _setting(db)
    cat = _category(db, "ZZT4 Cached", synonyms=["zzt4 cached word"])
    _sync(db)
    texts = _row_texts(db, "category", cat.id)
    ll._cache.clear()
    sent_before = len(transport.requests)
    selects: list[str] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        if "embedding_chunks" in statement and statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", grab)
    try:
        loaded = lookup_word_store.load_lookup_vectors(db, M3S)
    finally:
        event.remove(bind, "before_cursor_execute", grab)

    assert len(selects) == 1, selects
    assert len(transport.requests) == sent_before, "load_lookup_vectors called the provider"
    assert loaded >= len(texts)
    for t in texts:
        vec = np.asarray(ll._cache[ll._key(t, M3S)])
        assert vec.shape == (1536,) and abs(float(np.linalg.norm(vec)) - 1.0) < 1e-3


def test_ac_lec_17_the_shared_vector_file_is_gone():
    for name in ("_shared_path", "_read_shared", "_write_shared", "_lock_shared"):
        assert not hasattr(ll, name), name
    source = (BACKEND / "app" / "services" / "chatbot" / "head" / "lookup_lists.py").read_text()
    assert "CHATBOT_LOOKUP_VECTOR_DIR" not in source


def test_ac_lec_17_write_back_turns_a_fresh_vector_into_chunks_of_every_active_document_with_the_text(db):
    from app.services.chatbot.head import lookup_word_store

    _setting(db)
    a = _category(db, "ZZT4 Wb A", synonyms=["zzt4 turn word"])
    b = _category(db, "ZZT4 Wb B", synonyms=["zzt4 turn word"])
    off = _category(db, "ZZT4 Wb Off", synonyms=["zzt4 turn word"], active=False)
    _sync(db, embed=False)  # documents exist, no vectors yet
    docs = _lookup_docs(db, active=True)
    assert f"category:{off.id}" not in docs

    written = lookup_word_store.write_back(db, M3S, {"zzt4 turn word": pad(1.0, 0.5)})

    assert written == 2
    for cat in (a, b):
        chunks = [c for c in _chunks(db, docs[f"category:{cat.id}"]) if c.chunk_text == "zzt4 turn word"]
        assert len(chunks) == 1 and chunks[0].model_name == M3S


# ================================================================== AC-LEC-18
def test_ac_lec_18_prompt_synonyms_are_gone_from_lookup_lists():
    assert not hasattr(ll, "PROMPT_SYNONYMS")
    assert not hasattr(ll, "_with_synonyms")


def test_ac_lec_18_a_class_label_row_carries_the_synonyms_of_its_categories(db):
    _category(db, "ZZT4 WC One", class_label="Water Closet", synonyms=["zzt4 tandas a"])
    _category(db, "ZZT4 WC Two", class_label="Water Closet", synonyms=["zzt4 tandas b"])
    _category(db, "ZZT4 Tap One", class_label="Tap", synonyms=["zzt4 tap word"])
    rows = ll.load_rows(db)
    (wc,) = [r for r in rows if r.list_name == "category" and str(r.key) == "type:water closet"]
    assert {"Water Closet", "zzt4 tandas a", "zzt4 tandas b"} <= set(wc.texts)
    assert "zzt4 tap word" not in wc.texts
    # the former dictionary words are no longer injected from code
    assert "mangkuk tandas" not in wc.texts


def _script():
    path = BACKEND / "scripts" / "move_prompt_synonyms.py"
    assert path.exists(), f"missing {path}"
    spec = importlib.util.spec_from_file_location("move_prompt_synonyms", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synonyms(db, cat):
    db.expire_all()
    return list(db.get(ProductCategory, cat.id).search_synonyms or [])


def test_ac_lec_18_the_script_dry_run_lists_a_missing_word_and_writes_nothing(db):
    script = _script()
    a = _category(db, "ZZT4 WC A", class_label="Water Closet", synonyms=["tandas"])
    b = _category(db, "ZZT4 WC B", class_label="Water Closet", synonyms=[])
    result = script.run(db, apply=False)
    assert "mangkuk tandas" in json.dumps(result["plan"], default=str)
    assert _synonyms(db, a) == ["tandas"] and _synonyms(db, b) == []


def test_ac_lec_18_the_script_apply_adds_the_word_to_every_active_class_category_and_is_idempotent(db):
    script = _script()
    a = _category(db, "ZZT4 WC A", class_label="Water Closet", synonyms=["tandas"])
    b = _category(db, "ZZT4 WC B", class_label="Water Closet", synonyms=[])
    off = _category(db, "ZZT4 WC Off", class_label="Water Closet", synonyms=[], active=False)
    other = _category(db, "ZZT4 Tap", class_label="Tap", synonyms=[])
    first = script.run(db, apply=True)
    assert first["added"] > 0
    for cat in (a, b):
        assert "mangkuk tandas" in _synonyms(db, cat)
    assert _synonyms(db, a).count("tandas") == 1
    assert "mangkuk tandas" not in _synonyms(db, off) and "mangkuk tandas" not in _synonyms(db, other)
    second = script.run(db, apply=True)
    assert second["added"] == 0
    assert _synonyms(db, b).count("mangkuk tandas") == 1


# ================================================================== task + scheduler
def test_scheduler_registers_a_lookup_words_sync_handler():
    from app.scheduler import task_scheduler
    from app.services.scheduled_task_service import TASK_HANDLERS

    task_scheduler.register_task_handlers()
    assert "lookup_words_sync" in TASK_HANDLERS


def test_embed_missing_lookup_words_task_runs_the_sync(db, monkeypatch):
    import app.database as database
    from app.services.chatbot.head import lookup_word_store
    from app.tasks import chat_turns

    calls: list = []
    monkeypatch.setattr(lookup_word_store, "sync_lookup_words", lambda session, **kw: calls.append(kw))
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    chat_turns.embed_missing_lookup_words()
    assert len(calls) == 1
