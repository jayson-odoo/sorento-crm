"""Model change listeners to enqueue embedding events for key entities."""
from __future__ import annotations

import threading
import weakref
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable

from sqlalchemy import event

from app.models.embeddings import EmbeddingQueue
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.procurement import InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine
from app.models.product import ProductAttachment
from app.models.order import Order, OrderStatus, OrderLine


_REGISTERED = False
_SUPPRESSED = threading.local()


def _suppressed_set() -> set[str]:
    s = getattr(_SUPPRESSED, "types", None)
    if s is None:
        s = set()
        _SUPPRESSED.types = s
    return s


@contextmanager
def suppress_embedding_events(*source_types: str):
    """Skip per-row enqueue for given source_types within this thread/context."""
    s = _suppressed_set()
    added = [t for t in source_types if t not in s]
    s.update(added)
    try:
        yield
    finally:
        for t in added:
            s.discard(t)


def bulk_enqueue_embedding_events(
    bind,
    source_type: str,
    source_ids: Iterable[str],
    event_type: str | None = None,
) -> int:
    """Single multi-row INSERT into embedding_queue. `bind` is a Session or Connection."""
    event_type = event_type or f"{source_type}.updated"
    ids = [str(i) for i in source_ids if i is not None]
    if not ids:
        return 0
    now = datetime.utcnow()
    rows = []
    for sid in ids:
        rows.append({
            "id": str(uuid.uuid4()),
            "source_type": source_type,
            "source_id": sid,
            "event_type": event_type,
            "event_version": 1,
            "payload": {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "event_version": 1,
                "occurred_at": now.isoformat(),
                "source_type": source_type,
                "source_id": sid,
                "changed_fields": ["bulk_enqueue"],
                "triggered_by": "system",
            },
            "status": "pending",
            "retry_count": 0,
            "available_at": now,
            "created_at": now,
        })
    bind.execute(EmbeddingQueue.__table__.insert(), rows)
    return len(rows)


_eq_table_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _embedding_queue_exists(bind) -> bool:
    """Whether `embedding_queue` exists on this bind. The change listeners fire on
    every tracked write; a sqlite test bind with a subset schema lacks the table
    and would raise "no such table" on unrelated tests. Prod always has it."""
    if bind is None:
        return False
    # Keyed by the engine OBJECT via a weak map, never by id(engine):
    # CPython recycles id() once an object is collected, so a short-lived
    # engine (every sqlite test file makes its own, each with a different
    # subset schema) could land on a dead engine's address and inherit its
    # cached answer. Measured: 60 engines produced only 23 distinct ids.
    # A weak map drops the entry when the engine dies, so no reuse.
    key = bind.engine if hasattr(bind, "engine") else bind
    cached = _eq_table_cache.get(key)
    if cached is None:
        from sqlalchemy import inspect as _sa_inspect

        try:
            cached = _sa_inspect(bind).has_table("embedding_queue")
        except Exception:
            cached = False
        _eq_table_cache[key] = cached
    return cached


def _queue_from_mapper(connection, source_type: str, source_id: str, event_type: str) -> None:
    if source_type in _suppressed_set():
        return
    if not _embedding_queue_exists(connection):
        return  # subset schema (e.g. sqlite tests) — nothing to enqueue into
    connection.execute(
        EmbeddingQueue.__table__.insert().values(
            id=str(uuid.uuid4()),
            source_type=source_type,
            source_id=str(source_id),
            event_type=event_type,
            event_version=1,
            payload={
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "event_version": 1,
                "occurred_at": datetime.utcnow().isoformat(),
                "source_type": source_type,
                "source_id": str(source_id),
                "changed_fields": ["model_change_listener"],
                "triggered_by": "system",
            },
            status="pending",
            retry_count=0,
            available_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
    )


def _attach_listeners(model, source_type: str) -> None:
    @event.listens_for(model, "after_insert")
    def _after_insert(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.created")

    @event.listens_for(model, "after_update")
    def _after_update(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.updated")

    @event.listens_for(model, "after_delete")
    def _after_delete(_mapper, connection, target):
        _queue_from_mapper(connection, source_type, target.id, f"{source_type}.deleted")


def register_embedding_change_listeners() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _attach_listeners(Promotion, "promotion")
    _attach_listeners(PromotionProduct, "promotion_product")
    _attach_listeners(InboundShipment, "inbound_shipment")
    _attach_listeners(InboundShipmentLine, "inbound_shipment_line")
    _attach_listeners(SPOAllocation, "spo_allocation")
    _attach_listeners(PickingHeader, "picking_header")
    _attach_listeners(PickingLine, "picking_line")
    _attach_listeners(ProductAttachment, "product_attachment")
    _attach_listeners(PromotionAttachment, "promotion_attachment")
    _attach_listeners(Order, "order")
    _attach_listeners(OrderStatus, "order_status")
    _attach_listeners(OrderLine, "order_line")
    # TCK-2026-000026
    from app.models.order import Customer, Transporter
    _attach_listeners(Customer, "customer")
    _attach_listeners(Transporter, "transporter")
    _REGISTERED = True
