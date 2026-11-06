"""Packing list recompute on input change (PACKING-LIST-RECALC, 6 Nov 2026).

A packing list's stored line figures (`spo_allocated_quantity`, `quantity_received`,
`line_status`) and its header `shipment_status` are written by ONE function,
`InboundShipmentService.refresh_shipment_line_statuses`. Its inputs are the
`spo_allocations` rows linked to the container (`inbound_shipment_id`) and the
approved GRN picks that reach those rows (`PickingLine` / `PickingHeader`).

Before this module every writer of those inputs had to remember to call the
refresh. One did not (the AutoCount shipping-order push linking a container inside
`ShippingOrderIngestService._write_row`), so YMMU7738143 kept a stale status until
somebody opened its page, whose GET used to recompute and write.

Here, instead of every writer remembering: a session listener notes, at flush, the
containers whose inputs changed (old AND new container of a re-linked allocation),
and after the commit lands queues one recompute per container on `scm_recalc`
(job id `pl-recalc-<shipment id>`, skipped while one is already waiting, so a
burst of writes costs one recompute). The recompute is idempotent; a duplicate
run writes nothing new. When Redis cannot be reached the recompute runs inline on
a fresh session, so a missing queue degrades to "slower", never to "stale".
The scheduler's open-container sweep (`nightly_refresh_open_containers`, now
hourly) is the safety net for anything that writes around the ORM.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Iterable, Optional

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

QUEUE = "scm_recalc"
JOB_ID_PREFIX = "pl-recalc-"

_PENDING_KEY = "packing_list_recalc_pending"
_DISPATCH_KEY = "packing_list_recalc_dispatch"

#: `SPOAllocation` columns `compute_shipment_line_figures` reads, directly or
#: through `get_received_quantities_by_product` / `_floor_by_stated_received` /
#: `spo_supply.visible_line_clauses`.
ALLOCATION_INPUTS = (
    "inbound_shipment_id",
    "product_id",
    "allocated_quantity",
    "quantity_received",
    "stated_received",
    "qty_cancelled",
    "retired_at",
    "spo_number",
)
#: `InboundShipmentLine` columns the recompute reads (`quantity_shipped`, the product,
#: the container, and `created_at`, the apportion order). The recompute itself writes
#: only `spo_allocated_quantity` / `quantity_received` / `line_status` / `company_id`,
#: none of which is here, so it never queues itself.
SHIPMENT_LINE_INPUTS = ("quantity_shipped", "product_id", "shipment_id", "created_at")
#: `InboundShipment` columns the recompute reads: the rollup starts from the stored
#: header status, and the line self-heal follows the header's company. The recompute's
#: own header write is excluded (`recomputing`), so it never queues itself.
SHIPMENT_INPUTS = ("shipment_status", "company_id")

_RECOMPUTING_KEY = "packing_list_recalc_recomputing"
WATERMARK_KEY = "pl-recalc:sweep-watermark"
#: GRN header columns that decide whether its picks count (approved goods receipts)
#: and which SPO an allocation-less pick is matched to.
PICKING_HEADER_INPUTS = ("picking_status", "picking_type", "spo_number")
PICKING_LINE_INPUTS = ("spo_allocation_id", "quantity_picked", "product_id", "picking_header_id")

_registered = False


def _spo_key_expr(column):
    """The normalised SPO number the received reader matches on
    (`packing_lists.get_packing_list`'s `norm_expr`): trimmed, `/` and `\\` as `.`."""
    return func.replace(func.replace(func.trim(column), "/", "."), "\\", ".")


def _spo_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().replace("/", ".").replace("\\", ".")
    return key or None


def _history_values(obj, column: str, *, deleted: bool = False) -> tuple[bool, list]:
    """(changed, every value the column held in this flush: deleted + added + unchanged).

    An instance expired by an earlier commit and then modified carries no history
    for the columns it did not touch, so a live row's current value is read back
    (a plain SELECT on the flush's connection). A deleted row cannot be read back;
    the sweep covers the rare expired-and-deleted case."""
    history = inspect(obj).attrs[column].history
    values = list(history.deleted or ()) + list(history.added or ()) + list(history.unchanged or ())
    if not values and not deleted:
        try:
            values = [getattr(obj, column)]
        except Exception:  # noqa: BLE001 - best effort; the sweep is the backstop
            values = []
    return history.has_changes(), values


def _changed(obj, columns: Iterable[str]) -> bool:
    state = inspect(obj)
    return any(state.attrs[c].history.has_changes() for c in columns)


def _collect(session: Session, _flush_context) -> None:
    """after_flush: note which containers' inputs this flush changed.

    Runs after the SQL went out but before the history is reset, so an
    allocation moved from container A to B names both."""
    from app.models.procurement import (
        InboundShipment,
        InboundShipmentLine,
        PickingHeader,
        PickingLine,
        SPOAllocation,
    )

    shipment_ids: set[str] = set()
    allocation_ids: set[str] = set()
    spo_keys: set[str] = set()
    header_ids: set[str] = set()

    def _objects():
        for obj in session.new:
            yield obj, "new"
        for obj in session.dirty:
            yield obj, "dirty"
        for obj in session.deleted:
            yield obj, "deleted"

    for obj, kind in _objects():
        if isinstance(obj, SPOAllocation):
            if kind == "dirty" and not _changed(obj, ALLOCATION_INPUTS):
                continue
            _, values = _history_values(obj, "inbound_shipment_id", deleted=kind == "deleted")
            shipment_ids.update(str(v) for v in values if v)
        elif isinstance(obj, InboundShipment):
            if kind != "dirty" or not _changed(obj, SHIPMENT_INPUTS):
                continue  # a new header has no lines yet; a deleted one has nothing left
            if obj.id and str(obj.id) not in session.info.get(_RECOMPUTING_KEY, ()):
                shipment_ids.add(str(obj.id))
        elif isinstance(obj, InboundShipmentLine):
            if kind == "dirty" and not _changed(obj, SHIPMENT_LINE_INPUTS):
                continue
            _, values = _history_values(obj, "shipment_id", deleted=kind == "deleted")
            shipment_ids.update(str(v) for v in values if v)
        elif isinstance(obj, PickingLine):
            if kind == "dirty" and not _changed(obj, PICKING_LINE_INPUTS):
                continue
            _, values = _history_values(obj, "spo_allocation_id", deleted=kind == "deleted")
            allocation_ids.update(str(v) for v in values if v)
            if not values or any(v is None for v in values):
                # A pick with no allocation (now or before this flush) counts through
                # its header's SPO number (the received reader's orphan match); only
                # then is the header read.
                _, headers = _history_values(obj, "picking_header_id", deleted=kind == "deleted")
                header_ids.update(str(v) for v in headers if v)
        elif isinstance(obj, PickingHeader):
            if kind == "dirty" and not _changed(obj, PICKING_HEADER_INPUTS):
                continue
            if obj.id:
                header_ids.add(str(obj.id))
            _, values = _history_values(obj, "spo_number", deleted=kind == "deleted")
            spo_keys.update(k for k in (_spo_key(v) for v in values) if k)

    if allocation_ids or spo_keys or header_ids:
        shipment_ids.update(
            _resolve(session, allocation_ids=allocation_ids, spo_keys=spo_keys, header_ids=header_ids)
        )
    _note(session, shipment_ids)


def _before_flush(session: Session, _flush_context, _instances) -> None:
    """The OLD container of an allocation (or the old allocation of a pick) whose
    instance was expired by an earlier commit before being re-pointed: such an
    instance carries no `history.deleted`, so after the flush the old value is gone.
    Read it here, before the UPDATE goes out. One SELECT per such flush, only for
    re-pointed rows with no loaded old value."""
    from app.models.procurement import PickingLine, SPOAllocation

    unknown_alloc: set[str] = set()
    unknown_pick: set[str] = set()
    for obj in session.dirty:
        if isinstance(obj, SPOAllocation):
            column, bucket = "inbound_shipment_id", unknown_alloc
        elif isinstance(obj, PickingLine):
            column, bucket = "spo_allocation_id", unknown_pick
        else:
            continue
        history = inspect(obj).attrs[column].history
        if history.added and not history.deleted and not history.unchanged and obj.id:
            bucket.add(str(obj.id))
    if not unknown_alloc and not unknown_pick:
        return
    alloc = SPOAllocation.__table__
    conn = session.connection()
    old: set[str] = set()
    if unknown_alloc:
        old.update(
            str(r[0])
            for r in conn.execute(
                select(alloc.c.inbound_shipment_id).where(
                    alloc.c.id.in_(sorted(unknown_alloc)), alloc.c.inbound_shipment_id.isnot(None)
                )
            )
        )
    if unknown_pick:
        picks = PickingLine.__table__
        old.update(
            str(r[0])
            for r in conn.execute(
                select(alloc.c.inbound_shipment_id)
                .select_from(picks.join(alloc, alloc.c.id == picks.c.spo_allocation_id))
                .where(picks.c.id.in_(sorted(unknown_pick)), alloc.c.inbound_shipment_id.isnot(None))
            )
        )
    _note(session, old)


def _current_transaction(session: Session):
    """The innermost transaction in progress: a SAVEPOINT if one is open, else the root."""
    return session.get_nested_transaction() or session.get_transaction()


def _note(session: Session, shipment_ids: Iterable[str]) -> None:
    """Record containers against the CURRENT transaction level, so a savepoint that
    rolls back takes its own notes with it and a savepoint release does not fire."""
    ids = {str(s) for s in shipment_ids if s}
    if not ids:
        return
    transaction = _current_transaction(session)
    if transaction is None:
        return
    buckets = session.info.setdefault(_PENDING_KEY, {})
    buckets.setdefault(transaction, set()).update(ids)


def _resolve(session: Session, *, allocation_ids: set, spo_keys: set, header_ids: set) -> set[str]:
    """Containers reached through GRN rows: the allocation a pick hangs off, the SPO
    number a GRN header names (the received reader's orphan match), and every
    allocation the header's own picks point at. Core statements on the flush's own
    connection: no ORM event, no company auto-filter, nothing re-flushed."""
    from app.models.procurement import PickingHeader, PickingLine, SPOAllocation

    alloc = SPOAllocation.__table__
    conn = session.connection()
    found: set[str] = set()
    if header_ids:
        picks = PickingLine.__table__
        allocation_ids = set(allocation_ids) | {
            str(r[0])
            for r in conn.execute(
                select(picks.c.spo_allocation_id).where(
                    picks.c.picking_header_id.in_(sorted(header_ids)),
                    picks.c.spo_allocation_id.isnot(None),
                )
            )
        }
        headers = PickingHeader.__table__
        spo_keys = set(spo_keys) | {
            k
            for k in (
                _spo_key(r[0])
                for r in conn.execute(
                    select(headers.c.spo_number).where(headers.c.id.in_(sorted(header_ids)))
                )
            )
            if k
        }
    if allocation_ids:
        found.update(
            str(r[0])
            for r in conn.execute(
                select(alloc.c.inbound_shipment_id).where(
                    alloc.c.id.in_(sorted(allocation_ids)),
                    alloc.c.inbound_shipment_id.isnot(None),
                )
            )
        )
    if spo_keys:
        found.update(
            str(r[0])
            for r in conn.execute(
                select(alloc.c.inbound_shipment_id)
                .where(
                    _spo_key_expr(alloc.c.spo_number).in_(sorted(spo_keys)),
                    alloc.c.inbound_shipment_id.isnot(None),
                )
                .distinct()
            )
        )
    return found


def _after_commit(session: Session) -> None:
    """Dispatch only on the OUTERMOST commit. `SessionTransaction.commit()` fires
    `after_commit` on a SAVEPOINT release too, and the AutoCount ingest wraps every
    record in one: firing there queued the recompute while the route's own transaction
    was still open, so the job could read the old rows (and the inline fallback could
    wait on its own caller's row lock). Same per-level scheme as
    `product_spec_change_listener`: a release folds its notes into the parent level."""
    buckets = session.info.get(_PENDING_KEY)
    if not buckets:
        return
    transaction = _current_transaction(session)
    notes = buckets.pop(transaction, None) if transaction is not None else None
    if transaction is not None and transaction.parent is not None:
        if notes:
            buckets.setdefault(transaction.parent, set()).update(notes)
        return
    # The outermost commit. Any bucket left for another level belongs to a level that
    # ended without its own commit: dropped, never fired.
    session.info.pop(_PENDING_KEY, None)
    if not notes:
        return
    dispatch = session.info.get(_DISPATCH_KEY) or dispatch_recalc
    try:
        dispatch(sorted(notes))
    except Exception:  # noqa: BLE001 - the write already committed; the sweep catches up
        logger.warning("packing_list_recalc.dispatch_failed", exc_info=True)


def _after_rollback(session: Session) -> None:
    """A rollback drops only the level it ends; the outermost one drops everything."""
    buckets = session.info.get(_PENDING_KEY)
    if not buckets:
        return
    transaction = _current_transaction(session)
    if transaction is None:
        return
    buckets.pop(transaction, None)
    if transaction.parent is None or not buckets:
        session.info.pop(_PENDING_KEY, None)


def register_packing_list_recalc_listeners() -> None:
    """Idempotent; called at API startup and in the RQ worker, like the audit listeners."""
    global _registered
    if _registered:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_flush", _collect)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    _registered = True


def pending_shipment_ids(session: Session) -> set[str]:
    """What the open transaction (every level) has noted so far (tests, diagnostics)."""
    buckets = session.info.get(_PENDING_KEY) or {}
    return {sid for ids in buckets.values() for sid in ids}


def mark_stale(session: Session, shipment_ids: Iterable[str]) -> None:
    """Note containers to recompute after this session's outermost commit, for a
    writer the listener cannot see (a bulk `query.delete()` / raw SQL)."""
    _note(session, shipment_ids)


@contextmanager
def recomputing(session: Session, shipment_id: str):
    """While the recompute writes a header's status, that write is not an input
    change: without this, every status the recompute moved would queue one more
    (no-op) run of itself."""
    active = session.info.setdefault(_RECOMPUTING_KEY, set())
    active.add(str(shipment_id))
    try:
        yield
    finally:
        active.discard(str(shipment_id))


# --------------------------------------------------------------------- the sweep
def changed_shipment_ids(db: Session, since) -> set[str]:
    """Containers whose inputs were written at or after `since`: the header itself, its
    lines, the allocations linked to it, and GRN picks / headers reaching it (through
    the pick's allocation, or the header's SPO number for an allocation-less pick).
    Inserts count through `coalesce(updated_at, created_at)`. A row hard-deleted
    around the ORM leaves nothing to read; such a writer calls `mark_stale`."""
    from sqlalchemy import or_

    from app.models.procurement import (
        InboundShipment,
        InboundShipmentLine,
        PickingHeader,
        PickingLine,
        SPOAllocation,
    )

    shipments = InboundShipment.__table__
    lines = InboundShipmentLine.__table__
    alloc = SPOAllocation.__table__
    picks = PickingLine.__table__
    headers = PickingHeader.__table__

    def _touched(table):
        return func.coalesce(table.c.updated_at, table.c.created_at) >= since

    statements = [
        select(shipments.c.id).where(shipments.c.updated_at >= since),
        select(lines.c.shipment_id).where(_touched(lines)),
        select(alloc.c.inbound_shipment_id).where(
            _touched(alloc), alloc.c.inbound_shipment_id.isnot(None)
        ),
        select(alloc.c.inbound_shipment_id)
        .select_from(picks.join(alloc, alloc.c.id == picks.c.spo_allocation_id))
        .where(
            or_(_touched(picks), picks.c.picking_header_id.in_(
                select(headers.c.id).where(headers.c.updated_at >= since)
            )),
            alloc.c.inbound_shipment_id.isnot(None),
        ),
        select(alloc.c.inbound_shipment_id).where(
            alloc.c.inbound_shipment_id.isnot(None),
            _spo_key_expr(alloc.c.spo_number).in_(
                select(_spo_key_expr(headers.c.spo_number)).where(
                    headers.c.updated_at >= since, headers.c.spo_number.isnot(None)
                )
            ),
        ),
    ]
    conn = db.connection()
    found: set[str] = set()
    for statement in statements:
        found.update(str(r[0]) for r in conn.execute(statement.distinct()) if r[0])
    return found


def read_watermark():
    """When the last sweep started (naive, DB clock), or None when unknown."""
    from datetime import datetime

    try:
        from app.services.queue_service import redis_conn

        raw = redis_conn.get(WATERMARK_KEY)
        return datetime.fromisoformat(raw.decode()) if raw else None
    except Exception:  # noqa: BLE001 - unknown watermark = the fallback window
        logger.warning("packing_list_recalc.watermark_read_failed", exc_info=True)
        return None


def write_watermark(value) -> None:
    try:
        from app.services.queue_service import redis_conn

        redis_conn.set(WATERMARK_KEY, value.isoformat())
    except Exception:  # noqa: BLE001 - the next sweep falls back to its window
        logger.warning("packing_list_recalc.watermark_write_failed", exc_info=True)


def db_now(db: Session):
    """The clock `func.now()` stamps `updated_at` with, as a naive timestamp."""
    return db.execute(select(func.localtimestamp())).scalar()


# --------------------------------------------------------------------- dispatch
def dispatch_recalc(shipment_ids: Iterable[str]) -> None:
    """Queue one recompute per container on `scm_recalc`, skipping a container whose
    job is still waiting (burst de-dupe: the waiting job will read the newest
    figures when it runs). A container whose job is already RUNNING is queued again,
    since that run may have read the figures before this write landed."""
    ids = [str(s) for s in shipment_ids if s]
    if not ids:
        return
    try:
        from rq import Queue
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        from app.services.queue_service import redis_conn

        queue = Queue("scm_recalc", connection=redis_conn)
        for shipment_id in ids:
            base = f"{JOB_ID_PREFIX}{shipment_id}"
            # The job id, then one re-run id for writes landing while it runs. Re-using
            # a RUNNING job's id would overwrite its hash, and the worker deletes that
            # hash when the run ends (result_ttl=0): the re-queued id would then be
            # skipped at dequeue. A waiting job at either id already covers this write.
            job_id = None
            waiting = False
            for candidate in (base, f"{base}-rerun"):
                try:
                    status = Job.fetch(candidate, connection=redis_conn).get_status(refresh=False)
                except NoSuchJobError:
                    job_id = candidate
                    break
                if status in ("queued", "deferred", "scheduled"):
                    waiting = True
                    break
                if status != "started":
                    job_id = candidate
                    break
            if waiting:
                continue
            if job_id is None:  # both running: a one-off id, never lost
                job_id = f"{base}-{uuid.uuid4().hex[:12]}"
            queue.enqueue(
                "app.tasks.packing_list_recalc_tasks.recalc_packing_list_job",
                shipment_id,
                job_id=job_id,
                result_ttl=0,
                failure_ttl=7 * 24 * 3600,
                job_timeout=300,
            )
    except Exception:  # noqa: BLE001 - Redis down: do it now rather than not at all
        logger.warning("packing_list_recalc.enqueue_failed; recomputing inline", exc_info=True)
        recalc_inline(ids)


def recalc_inline(shipment_ids: Iterable[str]) -> None:
    """Recompute on a fresh, all-companies session (never the caller's: this runs
    from inside its after_commit)."""
    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    try:
        set_company_scope(db, None)
        for shipment_id in shipment_ids:
            recalc_packing_list(db, shipment_id, trigger="inline")
    finally:
        db.close()


def recalc_packing_list(db: Session, shipment_id: str, *, trigger: str = "input_change") -> bool:
    """The one idempotent recompute for one packing list. Returns False when it failed
    (logged, rolled back) so a sweep can carry on with the next one."""
    from app.services.procurement_service import InboundShipmentService

    try:
        InboundShipmentService(db).refresh_shipment_line_statuses(
            str(shipment_id), trigger=trigger
        )
        return True
    except Exception:  # noqa: BLE001 - one bad container must not stop the caller
        db.rollback()
        logger.exception("packing_list_recalc.failed shipment=%s", shipment_id)
        return False
