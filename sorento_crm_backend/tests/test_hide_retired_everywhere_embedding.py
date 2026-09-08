"""RED tests for AC-E3 (PLAN-hide-retired-everywhere) - the embedding trio.

UAC: documentation/plans/autocount/hide-retired-everywhere-acceptance-criteria.md
PLAN: documentation/plans/autocount/PLAN-hide-retired-everywhere.md

Separate file from `test_hide_retired_everywhere.py` because this AC needs a DIFFERENT
substrate: `embedding_worker.process_embedding_queue_item` opens its OWN `SessionLocal()`
- a fresh connection - so a scratch-schema (`blank_session`) fixture would be invisible to
it (schema_translate_map only rewrites statements on the connection it was built for). This
suite instead follows `test_rag_company_scope.py`'s pattern: a real `SessionLocal()` session
inside a rolled-back SAVEPOINT, `SessionLocal` monkeypatched to hand the worker THIS SAME
session (with its own `.close()` neutralised so the worker's `finally: db.close()` cannot
end the test's session), so the worker's queries execute against the seeded rows without
committing anything to the shared database.

Per R9 (PLAN section 2): retiring a line fires `after_update` same as any other edit, so
without this fix the worker re-embeds the row's now-stale text and reactivates its
document - the retirement marker never reaches the vector store. The fix is entirely on
the CONSUMER side (`embedding_worker.process_embedding_queue_item` +
`embedding_backfill_service`); `embedding_change_listener.py` needs no change.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from app.database import SessionLocal
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument, EmbeddingQueue
from app.models.procurement import SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure

from tests._pg_fixture import blank_session

MARKER = "zzt-hide-everywhere-emb"


def _u() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def db():
    session = SessionLocal()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _product(db) -> Product:
    cat = ProductCategory(id=_u(), category_code=f"ZZT-{_u()[:8]}", category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=f"ZZT{_u()[:6]}", uom_name="Unit")
    db.add_all([cat, uom])
    db.flush()
    row = Product(
        id=_u(), product_code=f"ZZT-{_u()[:8]}", product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
    )
    db.add(row)
    db.flush()
    return row


def _alloc(db, product, *, retired: bool, received: int = 0) -> SPOAllocation:
    row = SPOAllocation(
        id=_u(), spo_number=f"ZZT-SPO-{_u()[:8]}", product_id=product.id,
        allocated_quantity=10, quantity_received=received,
        line_status="closed" if retired else "open",
        retired_at=_now() if retired else None,
    )
    db.add(row)
    db.flush()
    return row


def _seed_document(db, source_id: str) -> EmbeddingDocument:
    doc = EmbeddingDocument(
        id=_u(), source_type="spo_allocation", source_id=source_id,
        source_key=source_id, title="stale SPO text", body_text="stale body text",
        source_hash="stalehash", is_active=True,
    )
    db.add(doc)
    db.flush()
    db.add(EmbeddingChunk(
        id=_u(), document_id=doc.id, source_type="spo_allocation", source_id=source_id,
        chunk_index=0, chunk_text="stale body text", chunk_hash="stalehash",
        embedding=[0.0] * 1536, model_name="test-model", model_version="v1",
        embedding_provider="test", source_hash="stalehash", is_current=True,
    ))
    db.flush()
    return doc


def _pending_queue_row(db, source_id: str) -> EmbeddingQueue:
    row = EmbeddingQueue(
        id=_u(), source_type="spo_allocation", source_id=source_id,
        event_type="spo_allocation.updated", event_version=1, payload={},
        status="pending", retry_count=0, available_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


# =================================================================================== #
# AC-E3, first half: retiring a line deactivates its document instead of re-embedding it
# =================================================================================== #


class TestAcE3WorkerDeactivatesInsteadOfReembedding:
    def test_a_hidden_spo_allocation_deactivates_its_existing_document_without_reembedding(
        self, db, monkeypatch
    ):
        from app.services import embedding_worker

        product = _product(db)
        hidden = _alloc(db, product, retired=True, received=0)
        doc = _seed_document(db, hidden.id)
        queue_row = _pending_queue_row(db, hidden.id)

        # The worker opens its OWN `SessionLocal()` - hand it THIS test's session (same
        # connection, same seeded/uncommitted rows) instead, and neutralise its
        # `finally: db.close()` so the worker cannot end this test's session out from
        # under it.
        monkeypatch.setattr(embedding_worker, "SessionLocal", lambda: db)
        db.close = lambda: None  # type: ignore[method-assign]

        embedding_worker.process_embedding_queue_item(queue_row.id)

        db.expire_all()
        refreshed_doc = (
            db.query(EmbeddingDocument).filter(EmbeddingDocument.id == doc.id).one()
        )
        assert refreshed_doc.is_active is False, refreshed_doc.is_active
        # No re-embed happened: still exactly the one stale chunk this test seeded.
        chunk_count = (
            db.query(EmbeddingChunk).filter(EmbeddingChunk.document_id == doc.id).count()
        )
        assert chunk_count == 1, chunk_count
        refreshed_queue = (
            db.query(EmbeddingQueue).filter(EmbeddingQueue.id == queue_row.id).one()
        )
        assert refreshed_queue.status == "completed", refreshed_queue.status

    def test_a_retired_line_carrying_a_receipt_is_not_treated_as_hidden(self, db):
        """R2, at the decision point the worker actually reads: a retired line with a
        receipt is NOT hidden, so the worker's early-exit must not fire for it and the
        ordinary re-embed path runs instead."""
        from app.services.embedding_worker import _spo_allocation_hidden

        product = _product(db)
        visible = _alloc(db, product, retired=False)
        hidden = _alloc(db, product, retired=True, received=0)
        retired_with_receipt = _alloc(db, product, retired=True, received=4)

        assert _spo_allocation_hidden(db, visible.id) is False
        assert _spo_allocation_hidden(db, hidden.id) is True
        assert _spo_allocation_hidden(db, retired_with_receipt.id) is False


# =================================================================================== #
# AC-E15 (round 2, extended round 3): the deactivation is reversible, both ways
#
# Round 2: a later push un-retires a line (clears `retired_at`) - its body is
# byte-identical to the original, so `source_hash` is unchanged and the worker's
# hash-skip branch is the ONLY place that can repair `is_active`. Round 3: the SAME gap
# has a second path the round-2 ruling did not name - a retired line that later takes a
# receipt (`quantity_received` 0 -> 5) becomes visible under R2 WITHOUT `retired_at`
# ever clearing, and the canonical body does not read `quantity_received` either, so the
# hash is unchanged there too. Both round trips are pinned; per the captain's steer, the
# assertion in both is on the skip branch re-activating, never on any body-content
# difference - there deliberately isn't one.
# =================================================================================== #


class TestAcE15DeactivationIsReversible:
    def _embed_while_visible(self, db, embedding_worker, alloc) -> EmbeddingDocument:
        """The FIRST drain, while the row is visible - the ordinary (non-skip) path
        builds a REAL canonical body and a REAL `source_hash`, so the round trip's later
        hash match is genuine rather than engineered by a hand-seeded stand-in."""
        q = _pending_queue_row(db, alloc.id)
        embedding_worker.process_embedding_queue_item(q.id)
        db.expire_all()
        return (
            db.query(EmbeddingDocument)
            .filter(
                EmbeddingDocument.source_type == "spo_allocation",
                EmbeddingDocument.source_id == alloc.id,
            )
            .one()
        )

    def _retire_and_drain(self, db, embedding_worker, alloc) -> None:
        alloc.retired_at = _now()
        alloc.line_status = "closed"
        db.flush()
        q = _pending_queue_row(db, alloc.id)
        embedding_worker.process_embedding_queue_item(q.id)
        db.expire_all()

    def _rigged(self, db, monkeypatch):
        """`SessionLocal` handed the test's own session (same connection, seeded rows
        visible), its `.close()` neutralised, and the real embed provider call replaced
        with deterministic dummy vectors - see the module docstring."""
        from app.services import embedding_worker

        monkeypatch.setattr(embedding_worker, "SessionLocal", lambda: db)
        db.close = lambda: None  # type: ignore[method-assign]
        monkeypatch.setattr(
            embedding_worker, "_embed_text_chunks",
            lambda chunks: [[0.0] * 1536 for _ in chunks],
        )
        return embedding_worker

    def test_un_retiring_reactivates_the_document(self, db, monkeypatch):
        embedding_worker = self._rigged(db, monkeypatch)
        product = _product(db)
        alloc = _alloc(db, product, retired=False)

        doc = self._embed_while_visible(db, embedding_worker, alloc)
        assert doc.is_active is True  # sanity: the ordinary path activates it

        self._retire_and_drain(db, embedding_worker, alloc)
        db.refresh(doc)
        assert doc.is_active is False  # sanity: pinned by the deactivation test too

        # A later push un-retires it - the leftover sweep no longer names it retired.
        alloc.retired_at = None
        alloc.line_status = "open"
        db.flush()
        q = _pending_queue_row(db, alloc.id)
        embedding_worker.process_embedding_queue_item(q.id)

        db.expire_all()
        db.refresh(doc)
        assert doc.is_active is True, doc.is_active

    def test_a_receipt_landing_reactivates_the_document_under_r2(self, db, monkeypatch):
        embedding_worker = self._rigged(db, monkeypatch)
        product = _product(db)
        alloc = _alloc(db, product, retired=False)

        doc = self._embed_while_visible(db, embedding_worker, alloc)

        self._retire_and_drain(db, embedding_worker, alloc)
        db.refresh(doc)
        assert doc.is_active is False  # sanity

        # R2's own path: a goods-received note lands - `quantity_received` 0 -> 5,
        # `retired_at` is NEVER touched.
        alloc.quantity_received = 5
        db.flush()
        q = _pending_queue_row(db, alloc.id)
        embedding_worker.process_embedding_queue_item(q.id)

        db.expire_all()
        db.refresh(doc)
        assert doc.is_active is True, doc.is_active


# =================================================================================== #
# AC-E3, second half: embedding_backfill_service skips hidden rows
#
# `_fetch_rows` reads `self.db` directly - no separate `SessionLocal()`, unlike
# `process_embedding_queue_item` above - so this half uses `blank_session()` (an empty
# scratch schema) rather than the live-DB fixture: the live `spo_allocations` table holds
# ~80,000 real rows ordered by `created_at ASC`, and a freshly-seeded row would sort behind
# every one of them, past any limit small enough for a test to page through quickly.
# =================================================================================== #


class TestAcE3BackfillSkipsHiddenRows:
    def test_spo_allocation_backfill_omits_hidden_rows(self):
        from app.services.embedding_backfill_service import EmbeddingBackfillService

        with blank_session() as db:
            product = _product(db)
            visible = _alloc(db, product, retired=False)
            hidden = _alloc(db, product, retired=True, received=0)
            retired_with_receipt = _alloc(db, product, retired=True, received=3)
            db.commit()

            rows = EmbeddingBackfillService(db)._fetch_rows(
                source="spo_allocation", limit=1000, offset=0
            )
            ids = {str(r["id"]) for r in rows}
            assert visible.id in ids, ids
            assert retired_with_receipt.id in ids, ids
            assert hidden.id not in ids, ids
