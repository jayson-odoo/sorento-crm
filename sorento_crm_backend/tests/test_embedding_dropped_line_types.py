"""EMBED-DROP-LINE-TYPES: order_line / picking_line / inbound_shipment_line are no longer embedded.

Plan: documentation/plans/chatbot/PLAN-embed-drop-line-types-27oct.md

No in-app reader uses these three types (entity_resolver excludes them as noise; fuzzy_resolver,
project search and tool search read other types) and no n8n workflow calls the only path that
could return them. Their text is UUIDs and quantities. They were also the noisiest sources in
embedding_queue. Every test runs in a blank scratch schema.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.embeddings import EmbeddingDocument, EmbeddingQueue
from app.models.order import Order
from app.services.embedding_change_listener import (
    DROPPED_SOURCE_TYPES,
    EMBEDDED_FIELDS,
    register_embedding_change_listeners,
)
from tests._pg_fixture import blank_session

register_embedding_change_listeners()

DROPPED = ("inbound_shipment_line", "order_line", "picking_line")


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _doc(db, source_type, *, active=True):
    doc = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type=source_type, source_id=str(uuid.uuid4()),
        title="t", body_text="b", source_hash="h", is_active=active,
    )
    db.add(doc)
    db.flush()
    return doc


def _queue_row(db, source_type, source_id=None, status="pending"):
    now = datetime.utcnow()
    row = EmbeddingQueue(
        id=str(uuid.uuid4()), source_type=source_type, source_id=source_id or str(uuid.uuid4()),
        event_type=f"{source_type}.updated", event_version=1, payload={},
        status=status, retry_count=0, available_at=now, created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def test_the_three_line_types_are_dropped():
    assert DROPPED_SOURCE_TYPES == frozenset(DROPPED)
    assert not set(DROPPED) & set(EMBEDDED_FIELDS)


def test_writing_an_order_line_queues_nothing(db):
    from tests.test_order_field_ownership import _line_fixture

    order = Order(order_number=f"ZZT-EDL-{uuid.uuid4().hex[:6]}", order_date=date(2026, 10, 1))
    db.add(order)
    db.flush()
    _, _, line = _line_fixture(db, order)
    line.quantity = 99
    db.flush()
    assert db.query(EmbeddingQueue).filter(EmbeddingQueue.source_type == "order_line").count() == 0


def test_backfill_all_no_longer_covers_the_line_types(db):
    from app.services.embedding_backfill_service import EmbeddingBackfillService

    result = EmbeddingBackfillService(db).run(source="all", dry_run=True)
    covered = {r["source"] for r in result["sources"]}
    assert covered and not covered & set(DROPPED)


@pytest.mark.parametrize("source", DROPPED)
def test_backfill_api_refuses_a_line_type(source):
    from app.api.v1.system import embeddings

    pattern = next(
        p.default.metadata[0].pattern if hasattr(p.default, "metadata") and p.default.metadata else None
        for p in __import__("inspect").signature(embeddings.backfill_embeddings).parameters.values()
        if p.name == "source"
    )
    import re

    assert pattern is not None
    assert re.fullmatch(pattern, source) is None
    assert re.fullmatch(pattern, "order") is not None


def test_worker_skips_a_queued_line_row_and_deactivates_its_document(db, monkeypatch):
    """A row queued before the deploy (or by the old colour during the overlap) must not
    re-embed, and must not leave the line's document searchable."""
    from app.services import embedding_worker

    monkeypatch.setattr(embedding_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(
        embedding_worker, "_canonical_for_source",
        lambda *a, **k: pytest.fail("a dropped type must not be rebuilt"),
    )
    doc = _doc(db, "order_line")
    row = _queue_row(db, "order_line", doc.source_id)

    result = embedding_worker.process_embedding_queue_item(row.id)

    assert result["status"] == "skipped"
    db.expire_all()
    assert db.get(EmbeddingQueue, row.id).status == "skipped"
    assert db.get(EmbeddingDocument, doc.id).is_active is False


def test_retire_deactivates_line_documents_and_skips_their_pending_rows(db):
    from app.services.embedding_service import retire_dropped_embedding_types

    line_docs = [_doc(db, t) for t in DROPPED for _ in range(2)]
    kept_doc = _doc(db, "order")
    line_rows = [_queue_row(db, t) for t in DROPPED]
    kept_row = _queue_row(db, "order")
    done_row = _queue_row(db, "order_line", status="completed")

    result = retire_dropped_embedding_types(db, batch_size=2, max_batches=50)

    assert result == {"documents_deactivated": 6, "queue_rows_skipped": 3, "done": True}
    db.expire_all()
    assert all(db.get(EmbeddingDocument, d.id).is_active is False for d in line_docs)
    assert db.get(EmbeddingDocument, kept_doc.id).is_active is True
    assert all(db.get(EmbeddingQueue, r.id).status == "skipped" for r in line_rows)
    assert db.get(EmbeddingQueue, kept_row.id).status == "pending"
    assert db.get(EmbeddingQueue, done_row.id).status == "completed"


def test_retire_is_resumable_and_then_a_no_op(db):
    from app.services.embedding_service import retire_dropped_embedding_types

    for _ in range(5):
        _doc(db, "picking_line")
    first = retire_dropped_embedding_types(db, batch_size=2, max_batches=1)
    assert (first["documents_deactivated"], first["done"]) == (2, False)
    second = retire_dropped_embedding_types(db, batch_size=2, max_batches=50)
    assert (second["documents_deactivated"], second["done"]) == (3, True)
    assert retire_dropped_embedding_types(db, batch_size=2, max_batches=50) == {
        "documents_deactivated": 0, "queue_rows_skipped": 0, "done": True,
    }


def test_prune_task_runs_the_retire_step_until_it_is_done(db, monkeypatch):
    from app.scheduler import task_scheduler
    from app.services import embedding_queue_indexes as eqi
    from app.services import embedding_service

    calls = []
    monkeypatch.setattr(eqi, "missing_indexes", lambda conn: [])
    monkeypatch.setattr(task_scheduler, "_DROPPED_TYPES_RETIRED", False)
    outcomes = iter([{"done": False}, {"done": True}])
    monkeypatch.setattr(
        embedding_service, "retire_dropped_embedding_types",
        lambda db, **k: calls.append(k) or next(outcomes),
    )
    for _ in range(3):
        task_scheduler._handler_embedding_queue_prune(db, None)
    assert len(calls) == 2  # the third run skips it: nothing left to retire
