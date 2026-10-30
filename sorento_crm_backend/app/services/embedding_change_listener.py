"""Model change listeners to enqueue embedding events for key entities."""
from __future__ import annotations

import threading
import weakref
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import event, select

from app.models.certificate import Certificate
from app.models.embeddings import EmbeddingQueue
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.procurement import InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine
from app.models.product import Product, ProductAttachment
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


# Columns each source type's embedding is built from (embedding_worker._canonical_for_source:
# title, source_key, body and metadata), plus company_id, which the queue payload carries.
# SQLAlchemy fires after_update for every flushed object, also when no value changed, and an
# update that touches none of these cannot change the embedding, so it queues nothing.
# spo_allocation also lists retired_at and quantity_received: they decide whether the worker
# hides the line (embedding_worker._spo_allocation_hidden). A type missing here queues on
# every update.
EMBEDDED_FIELDS: dict[str, tuple[str, ...]] = {
    "product": ("product_code", "product_name", "category_id", "brand_id", "description", "item_type", "company_id"),
    "promotion": ("description", "start_date", "end_date", "access_levels", "company_id"),
    "promotion_product": ("promotion_id", "product_id", "promo_selling_price", "discount_percent", "company_id"),
    "promotion_attachment": ("promotion_id", "attachment_id", "is_primary", "sort_order", "company_id"),
    "product_attachment": ("product_id", "attachment_id", "is_primary", "sort_order", "access_levels", "company_id"),
    "inbound_shipment": (
        "shipment_number", "shipment_status", "shipment_date", "estimated_arrival_date", "notes",
        "supplier_id", "access_levels", "company_id",
    ),
    "inbound_shipment_line": ("shipment_id", "product_id", "quantity_shipped", "line_status", "batch_number", "company_id"),
    "spo_allocation": (
        "spo_number", "inbound_shipment_id", "product_id", "allocated_quantity", "receipt_status",
        "warehouse_id", "storage_zone_id", "retired_at", "quantity_received", "company_id",
    ),
    "picking_header": (
        "picking_number", "spo_number", "picking_status", "inspection_status", "notes", "picking_type", "company_id",
    ),
    "picking_line": (
        "picking_header_id", "product_id", "quantity_expected", "quantity_picked", "picked_condition",
        "spo_allocation_id", "company_id",
    ),
    "certificate": ("scheme", "certificate_number", "certifying_body", "issuer", "title", "status", "company_id"),
    "order": (
        "order_number", "debtor_name", "salesman", "order_type", "transporter", "remarks",
        "order_status_id", "is_cancelled", "company_id",
    ),
    "order_status": ("status_code", "status_name", "description", "sequence", "is_final_status"),
    "order_line": ("order_id", "product_id", "warehouse_id", "quantity", "unit_price", "line_sequence", "company_id"),
    "customer": ("customer_code", "customer_name", "country", "company_id"),
    "transporter": ("code", "name", "company_id"),
}


def embedded_fields_changed(target, source_type: str) -> bool:
    """Whether a pending flush of `target` changes anything its embedding is built from.

    Unchanged when every embedded attribute's history is empty: SQLAlchemy records no change
    for a column set to the value it already had. A type without a field list counts as
    changed, so a new tracked type keeps queueing until it gets one.
    """
    from sqlalchemy import inspect as sa_inspect

    fields = EMBEDDED_FIELDS.get(source_type)
    if fields is None:
        return True
    state = sa_inspect(target)
    attrs = state.attrs
    return any(name in attrs and attrs[name].history.has_changes() for name in fields)


# last_error on a pending row retired because a newer row of the same source covers it.
SUPERSEDED_ERROR = "dedup: superseded"


def pending_queue_ids(
    bind, source_type: str, source_ids: Iterable[str], *, lock: str | None = "share"
) -> dict[str, str]:
    """source_id -> id of a pending, never-failed embedding_queue row that covers it.

    The rows found are row-locked until the caller's transaction ends (`lock="share"`, or
    `"update"` for a caller that rewrites the row). That is what makes skipping an insert safe:
    the worker claims a row with FOR UPDATE NOWAIT, so it cannot claim (and read the source)
    while a transaction that relied on the row is still open, and an enqueuer that finds the
    row already claimed waits for that claim, re-reads it as `processing` and inserts its own.
    Row locks live in the tuple, not the shared lock table, so a 10k-row import can hold them.

    A row that already failed (`retry_count > 0`) does not cover a new change: it waits out a
    backoff and is one failure nearer dead_letter, which the new change must not inherit.
    """
    ids = sorted({str(i) for i in source_ids})
    if not ids:
        return {}
    table = EmbeddingQueue.__table__
    query = (
        select(table.c.source_id, table.c.id)
        .where(
            table.c.status == "pending",
            table.c.retry_count == 0,
            table.c.source_type == source_type,
            table.c.source_id.in_(ids),
        )
        .order_by(table.c.id)
    )
    if lock == "share":
        query = query.with_for_update(read=True)
    elif lock == "update":
        query = query.with_for_update()
    return {str(r.source_id): str(r.id) for r in bind.execute(query).all()}


def enqueue_pending(bind, rows: list[dict]) -> list[dict]:
    """Insert embedding_queue rows, skipping every source that already has a pending row.

    A pending row has not been claimed by the worker yet (it sets `processing` before it reads
    the source), so the row already waiting will embed the latest state; a second is pure
    duplicate work. Race-safe through the row locks `pending_queue_ids` takes. Two enqueuers
    that both find nothing pending can each insert one row; that duplicate is harmless (the
    first claim supersedes it). Returns the rows inserted.
    """
    from app.services.embedding_settings import RECORD_KEEP_SET

    by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row["source_type"] not in RECORD_KEEP_SET:
            continue  # LOOKUP-EMBED-CENTRAL: only the keep set is embedded
        by_key[(row["source_type"], str(row["source_id"]))] = row
    if not by_key:
        return []
    by_type: dict[str, list[str]] = {}
    for source_type, source_id in by_key:
        by_type.setdefault(source_type, []).append(source_id)
    for source_type, ids in by_type.items():
        for source_id in pending_queue_ids(bind, source_type, ids):
            by_key.pop((source_type, source_id), None)
    fresh = list(by_key.values())
    if fresh:
        bind.execute(EmbeddingQueue.__table__.insert(), fresh)
    return fresh


def bulk_enqueue_embedding_events(
    bind,
    source_type: str,
    source_ids: Iterable[str],
    event_type: str | None = None,
) -> int:
    """Queue many sources of one type in one INSERT. `bind` is a Session or Connection.

    Sources that already have a pending row are skipped. Returns the rows inserted.
    """
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
    return len(enqueue_pending(bind, rows))


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


def build_queue_payload(
    source_type: str,
    source_id: str,
    event_type: str,
    company_id=None,
) -> dict:
    """Queue-row JSON payload for a model-change event.

    ``company_id`` (the source entity's company, multi-company isolation) is
    threaded through so the embedding worker can stamp fresh document/chunk rows
    even before it re-loads the source - AC-I5: a fresh embedding must never be
    company-less when its source has a company. Extracted (from the inline dict
    ``_queue_from_mapper`` used to build) so it is unit-testable without a DB.
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": datetime.utcnow().isoformat(),
        "source_type": source_type,
        "source_id": str(source_id),
        "company_id": str(company_id) if company_id is not None else None,
        "changed_fields": ["model_change_listener"],
        "triggered_by": "system",
    }


def _queue_from_mapper(
    connection, source_type: str, source_id: str, event_type: str, company_id=None
) -> None:
    if source_type in _suppressed_set():
        return
    if not _embedding_queue_exists(connection):
        return  # subset schema (e.g. sqlite tests) - nothing to enqueue into
    now = datetime.utcnow()
    enqueue_pending(
        connection,
        [
            {
                "id": str(uuid.uuid4()),
                "source_type": source_type,
                "source_id": str(source_id),
                "event_type": event_type,
                "event_version": 1,
                "payload": build_queue_payload(source_type, source_id, event_type, company_id),
                "status": "pending",
                "retry_count": 0,
                "available_at": now,
                "created_at": now,
            }
        ],
    )


def _attach_listeners(model, source_type: str) -> None:
    @event.listens_for(model, "after_insert")
    def _after_insert(_mapper, connection, target):
        _queue_from_mapper(
            connection, source_type, target.id, f"{source_type}.created",
            getattr(target, "company_id", None),
        )

    @event.listens_for(model, "after_update")
    def _after_update(_mapper, connection, target):
        if not embedded_fields_changed(target, source_type):
            return
        _queue_from_mapper(
            connection, source_type, target.id, f"{source_type}.updated",
            getattr(target, "company_id", None),
        )

    @event.listens_for(model, "after_delete")
    def _after_delete(_mapper, connection, target):
        _queue_from_mapper(
            connection, source_type, target.id, f"{source_type}.deleted",
            getattr(target, "company_id", None),
        )


def _attach_project_listeners() -> None:
    """Projects (PROJECT-REG-PORTAL D9).

    Only what is embedded queues an event: the title and the developer on the project, and
    the state and mukim on its sales profile. Every other write (a staleness stamp, an
    activity touch) rebuilt an embedding that could not have changed.

    A portal registration is not a project until it is approved (R4): nothing is queued for
    a draft, pending or rejected row, and Approve queues the first embedding.
    """
    from sqlalchemy import inspect as sa_inspect, select

    from app.models.projects import Project, ProjectSalesProfile

    from app.models.projects import APPROVAL_APPROVED

    def _changed(target, *names: str) -> bool:
        state = sa_inspect(target)
        return any(state.attrs[name].history.has_changes() for name in names)

    def _approved(approval_state) -> bool:
        return approval_state in (None, APPROVAL_APPROVED)

    @event.listens_for(Project, "after_insert")
    def _project_inserted(_mapper, connection, target):
        if _approved(target.approval_state):
            _queue_from_mapper(connection, "project", target.id, "project.created", target.company_id)

    @event.listens_for(Project, "after_update")
    def _project_updated(_mapper, connection, target):
        if _approved(target.approval_state) and _changed(
            target, "title", "developer_party_id", "approval_state"
        ):
            _queue_from_mapper(connection, "project", target.id, "project.updated", target.company_id)

    @event.listens_for(Project, "after_delete")
    def _project_deleted(_mapper, connection, target):
        if _approved(target.approval_state):
            _queue_from_mapper(connection, "project", target.id, "project.deleted", target.company_id)

    def _queue_parent(connection, target) -> None:
        table = Project.__table__
        row = connection.execute(
            select(table.c.company_id, table.c.approval_state).where(table.c.id == target.project_id)
        ).first()
        if row is None or not _approved(row.approval_state):
            return
        _queue_from_mapper(connection, "project", target.project_id, "project.updated", row.company_id)

    @event.listens_for(ProjectSalesProfile, "after_insert")
    def _profile_inserted(_mapper, connection, target):
        if target.state or target.mukim:
            _queue_parent(connection, target)

    @event.listens_for(ProjectSalesProfile, "after_update")
    def _profile_updated(_mapper, connection, target):
        if _changed(target, "state", "mukim"):
            _queue_parent(connection, target)


def _attach_product_spec_listeners() -> None:
    """`product_spec` (LOOKUP-EMBED-CENTRAL): a specification row with rendered text is what a product is
    searched by. Queued when the row is inserted with text or its text changes to a non-empty value; the
    queue source id is the product id."""
    from sqlalchemy import inspect as sa_inspect

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    def _queue(connection, target, event_type: str) -> None:
        company_id = connection.execute(
            select(Product.__table__.c.company_id).where(Product.__table__.c.id == target.product_id)
        ).scalar()
        _queue_from_mapper(connection, "product_spec", target.product_id, event_type, company_id)

    @event.listens_for(ProductSpecifications, "after_insert")
    def _spec_inserted(_mapper, connection, target):
        if (target.rendered_text or "").strip():
            _queue(connection, target, "product_spec.created")

    @event.listens_for(ProductSpecifications, "after_update")
    def _spec_updated(_mapper, connection, target):
        if not sa_inspect(target).attrs.rendered_text.history.has_changes():
            return
        if (target.rendered_text or "").strip():
            _queue(connection, target, "product_spec.updated")


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
    _attach_listeners(Product, "product")
    _attach_listeners(PromotionAttachment, "promotion_attachment")
    _attach_listeners(Certificate, "certificate")
    _attach_listeners(Order, "order")
    _attach_listeners(OrderStatus, "order_status")
    _attach_listeners(OrderLine, "order_line")
    # TCK-2026-000026
    from app.models.order import Customer, Transporter
    _attach_listeners(Customer, "customer")
    _attach_listeners(Transporter, "transporter")
    _attach_project_listeners()
    _attach_product_spec_listeners()
    _REGISTERED = True
