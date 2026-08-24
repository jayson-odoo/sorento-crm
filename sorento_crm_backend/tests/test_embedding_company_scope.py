"""Embedding company-scope tests (multi-company data isolation, Part B).

Two layers:
  - Pure unit (always run, no DB): the vector-search company predicate builder
    (``_embedding_company_filter``) across the four scope states, and the listener
    payload copy (``build_queue_payload`` carries the source's company_id - AC-I5).
  - Live-DB integration (skippable via SKIP_LIVE_DB_TESTS=1): a scoped vector
    search over real ``embedding_documents`` / ``embedding_chunks`` returns only
    in-scope + shared (null-company) rows, never another company's (AC-I4).

The live layer runs inside a nested transaction that is ALWAYS rolled back and
uses a throwaway ``source_type`` marker + two throwaway company ids, so it never
touches real embeddings and needs no unscoped DELETE.
"""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.models.base import UNSET, set_company_scope
from app.services.embedding_change_listener import build_queue_payload
from app.services.embedding_service import _embedding_company_filter


def _compile(expr) -> str:
    if expr is None:
        return "<none>"
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class _FakeDB:
    """Minimal stand-in exposing only ``.info`` - enough for get/set_company_scope."""

    def __init__(self) -> None:
        self.info: dict = {}


# --- AC-I4 predicate builder (four-state) --------------------------------------
def _db_with_scope(scope) -> _FakeDB:
    db = _FakeDB()
    if scope is not UNSET:
        set_company_scope(db, scope)
    return db


def test_company_filter_none_adds_nothing():
    assert _embedding_company_filter(_db_with_scope(None)) is None


def test_company_filter_unset_is_false():
    sql = _compile(_embedding_company_filter(_db_with_scope(UNSET))).lower()
    assert "false" in sql
    assert "in ()" not in sql


def test_company_filter_empty_frozenset_is_false():
    sql = _compile(_embedding_company_filter(_db_with_scope(frozenset()))).lower()
    assert "false" in sql
    assert "in ()" not in sql


def test_company_filter_frozenset_is_null_or_in():
    cid = str(uuid.uuid4())
    sql = _compile(_embedding_company_filter(_db_with_scope(frozenset({cid})))).lower()
    # Shared (null) knowledge stays visible AND the in-scope companies are matched.
    assert "is null" in sql
    assert "company_id in" in sql
    assert cid.replace("-", "") in sql.replace("-", "")


# --- AC-I5 listener copies company_id into the queue payload --------------------
def test_queue_payload_carries_company_id():
    cid = str(uuid.uuid4())
    payload = build_queue_payload("promotion", "src-1", "promotion.created", cid)
    assert payload["company_id"] == cid
    assert payload["source_type"] == "promotion"
    assert payload["source_id"] == "src-1"


def test_queue_payload_company_id_none_when_source_company_less():
    payload = build_queue_payload("form", "src-2", "form.updated", None)
    assert payload["company_id"] is None


# --- AC-I4 live scoped vector search -------------------------------------------
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


@pytest.fixture()
def db():
    from app.database import SessionLocal

    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def emb_data(db):
    """Two companies (A, B) + one embedding doc/chunk each, plus a shared
    (null-company) doc/chunk. Unique throwaway source_type isolates the rows."""
    from app.models.company import Company
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    suffix = uuid.uuid4().hex[:8]
    source_type = f"zzemb_{suffix}"
    company_a = Company(id=str(uuid.uuid4()), name=f"ZZEMB A {suffix}", code=f"EA{suffix}")
    company_b = Company(id=str(uuid.uuid4()), name=f"ZZEMB B {suffix}", code=f"EB{suffix}")
    db.add_all([company_a, company_b])
    db.flush()
    a, b = company_a.id, company_b.id

    vec = [0.1] * 1536
    for tag, company_id in (("a", a), ("b", b), ("shared", None)):
        source_id = f"{source_type}:{tag}"
        doc = EmbeddingDocument(
            source_type=source_type,
            source_id=source_id,
            source_key=source_id,
            title=f"ZZEMB {tag}",
            body_text=f"ZZEMB body {tag}",
            metadata_json={},
            visibility_scope="internal",
            source_hash=hashlib.sha256(source_id.encode()).hexdigest(),
            company_id=company_id,
            is_active=True,
        )
        db.add(doc)
        db.flush()
        db.add(
            EmbeddingChunk(
                document_id=doc.id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=0,
                chunk_text=f"ZZEMB chunk {tag}",
                chunk_hash=hashlib.sha256(f"chunk-{tag}".encode()).hexdigest(),
                embedding=vec,
                model_name="zzemb-model",
                model_version="v1",
                embedding_provider="test",
                source_hash=doc.source_hash,
                metadata_json={},
                company_id=company_id,
                is_current=True,
            )
        )
    db.flush()
    return {"a": a, "b": b, "source_type": source_type, "vec": vec}


def _search(db, emb_data, scope):
    from app.models.base import company_scope
    from app.services.embedding_service import EmbeddingReadService

    with company_scope(db, scope):
        rows = EmbeddingReadService(db).search_current(
            emb_data["vec"], top_k=10, source_type=emb_data["source_type"]
        )
    return {chunk.company_id for chunk, _doc, _sim in rows}


def test_scoped_search_returns_in_scope_plus_shared_only(db, emb_data):
    got = _search(db, emb_data, frozenset({emb_data["a"]}))
    assert emb_data["a"] in got
    assert None in got  # shared knowledge still visible
    assert emb_data["b"] not in got  # AC-I4: another company's rows must not leak


def test_none_scope_search_returns_all(db, emb_data):
    got = _search(db, emb_data, None)
    assert got == {emb_data["a"], emb_data["b"], None}


def test_unset_scope_search_returns_zero(db, emb_data):
    got = _search(db, emb_data, UNSET)
    assert got == set()
