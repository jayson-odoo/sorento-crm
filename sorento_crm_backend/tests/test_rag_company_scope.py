"""RAG / embedding company-scope end-to-end - AC-I4/I5 (owned-entity framing).

Complements the predicate/payload unit coverage in ``test_embedding_company_scope``
with two live-DB, entity-level assertions:

  - AC-I5: mutating an OWNED entity (a Promotion) enqueues an embedding-queue row
    whose payload carries the ENTITY's ``company_id`` - via the real
    ``after_insert`` change listener + the multi-company auto-stamp, not the raw
    ``build_queue_payload`` helper. This is the source-company that the embedding
    worker later stamps onto ``embedding_documents`` / ``embedding_chunks``.
  - AC-I4: a Mocha-scoped semantic search over ``embedding_chunks`` returns only
    the in-scope company's rows (plus shared/null-company knowledge), never a
    Sorento entity's chunk.

The full worker round-trip (queue -> embed -> pgvector doc) is exercised
manually / by the worker's own path; here the producer side (I5) and the reader
side (I4) are pinned independently. Runs inside a rolled-back SAVEPOINT with a
``zzrag`` marker + throwaway companies, so nothing persists.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.services.company_scope import register_company_scope_listeners
from app.services.embedding_change_listener import register_embedding_change_listeners

register_company_scope_listeners()
register_embedding_change_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def mocha(db: Session) -> str:
    suffix = uuid.uuid4().hex[:8]
    c = Company(id=str(uuid.uuid4()), name=f"ZZRAG Mocha {suffix}", code=f"ZRG{suffix}")
    db.add(c)
    db.flush()
    return c.id


# --------------------------------------------------------------------------- #
# AC-I5 - owned-entity mutation enqueues an embedding row carrying company_id  #
# --------------------------------------------------------------------------- #
def test_promotion_insert_enqueues_embedding_with_source_company(db, mocha):
    from app.models.marketing import Promotion

    today = date.today()
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=f"ZZRAG promo {uuid.uuid4().hex[:8]}",
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=30),
        is_active=True,
        access_levels=["dealer"],
    )
    # Auto-stamp fills company_id = Mocha from the active scope; the after_insert
    # embedding listener then copies THAT company onto the queue payload.
    with company_scope(db, frozenset({mocha})):
        db.add(promo)
        db.flush()

    assert str(promo.company_id) == mocha  # auto-stamped

    row = db.execute(
        text(
            "SELECT payload ->> 'company_id' AS cid, source_type "
            "FROM embedding_queue WHERE source_id = :sid AND source_type = 'promotion' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"sid": str(promo.id)},
    ).first()
    assert row is not None, "owned-entity insert must enqueue an embedding event"
    assert row[0] == mocha  # AC-I5: payload carries the source entity's company


# --------------------------------------------------------------------------- #
# AC-I4 - a scoped semantic search never returns another company's chunk        #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def emb_rows(db, mocha):
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    suffix = uuid.uuid4().hex[:8]
    source_type = f"zzrag_{suffix}"
    vec = [0.05] * 1536
    for tag, cid in (("sorento", SORENTO), ("mocha", mocha), ("shared", None)):
        sid = f"{source_type}:{tag}"
        doc = EmbeddingDocument(
            source_type=source_type, source_id=sid, source_key=sid,
            title=f"ZZRAG {tag}", body_text=f"ZZRAG body {tag}", metadata_json={},
            visibility_scope="internal",
            source_hash=hashlib.sha256(sid.encode()).hexdigest(),
            company_id=cid, is_active=True,
        )
        db.add(doc)
        db.flush()
        db.add(EmbeddingChunk(
            document_id=doc.id, source_type=source_type, source_id=sid, chunk_index=0,
            chunk_text=f"ZZRAG chunk {tag}",
            chunk_hash=hashlib.sha256(f"c-{tag}".encode()).hexdigest(),
            embedding=vec, model_name="zzrag", model_version="v1", embedding_provider="test",
            source_hash=doc.source_hash, metadata_json={}, company_id=cid, is_current=True,
        ))
    db.flush()
    return {"source_type": source_type, "vec": vec}


def test_mocha_scoped_search_excludes_sorento_entity(db, mocha, emb_rows):
    from app.services.embedding_service import EmbeddingReadService

    with company_scope(db, frozenset({mocha})):
        rows = EmbeddingReadService(db).search_current(
            emb_rows["vec"], top_k=10, source_type=emb_rows["source_type"]
        )
    companies = {str(c.company_id) if c.company_id is not None else None for c, _d, _s in rows}
    assert mocha in companies          # own company visible
    assert None in companies           # shared knowledge visible
    assert SORENTO not in companies    # AC-I4: another company's entity never leaks
