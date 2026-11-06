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
    "line_status",
    "receipt_status",
    "spo_number",
)
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
    from app.models.procurement import PickingHeader, PickingLine, SPOAllocation

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
        elif isinstance(obj, PickingLine):
            if kind == "dirty" and not _changed(obj, PICKING_LINE_INPUTS):
                continue
            _, values = _history_values(obj, "spo_allocation_id", deleted=kind == "deleted")
            allocation_ids.update(str(v) for v in values if v)
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
    if shipment_ids:
        session.info.setdefault(_PENDING_KEY, set()).update(shipment_ids)


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
    pending = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return
    dispatch = session.info.get(_DISPATCH_KEY) or dispatch_recalc
    try:
        dispatch(sorted(pending))
    except Exception:  # noqa: BLE001 - the write already committed; the sweep catches up
        logger.warning("packing_list_recalc.dispatch_failed", exc_info=True)


def _after_rollback(session: Session) -> None:
    # A full rollback: nothing this transaction noted happened. (A savepoint rollback
    # leaves the set alone - one extra idempotent recompute is the cheaper mistake.)
    if not session.in_transaction():
        session.info.pop(_PENDING_KEY, None)


def register_packing_list_recalc_listeners() -> None:
    """Idempotent; called at API startup and in the RQ worker, like the audit listeners."""
    global _registered
    if _registered:
        return
    event.listen(Session, "after_flush", _collect)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    _registered = True


def pending_shipment_ids(session: Session) -> set[str]:
    """What the current transaction has noted so far (tests and diagnostics)."""
    return set(session.info.get(_PENDING_KEY) or ())


def mark_stale(session: Session, shipment_ids: Iterable[str]) -> None:
    """Note containers to recompute after this session's next commit, for a writer
    whose change the listener cannot see (raw SQL)."""
    ids = {str(s) for s in shipment_ids if s}
    if ids:
        session.info.setdefault(_PENDING_KEY, set()).update(ids)


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
            job_id = f"{JOB_ID_PREFIX}{shipment_id}"
            try:
                existing = Job.fetch(job_id, connection=redis_conn)
                if existing.get_status(refresh=False) in ("queued", "deferred", "scheduled"):
                    continue
            except NoSuchJobError:
                pass
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
