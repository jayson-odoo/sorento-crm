"""SCM S5 - producing and working the Plan Exception batch (UAC Group D).

The engine next door is pure; this is everything that touches a table: reading the position
either side of a restatement, reading the item's four signals, finding the supply already
placed, freezing the batch, and recording a decision.

**Before and after come from the SAME engine, either side of the write.** `snapshot` is
called once before `outstanding_import_service.apply` writes and once after it commits, and
both calls go through `CoverageService.network_positions` - the identical arithmetic the
Summary Order Report and the coverage panel use. The alternative was to reconstruct the old
position by inverting the diff's deltas, which is a second implementation of netting whose
only job is to agree with the first. It would not, eventually, and the disagreement would
surface as a before-column nobody could reproduce.

**A batch is produced by an UPLOAD, not by a plan run.** Exceptions exist because a purchase
order is already out with a supplier, and that is true whether or not anybody has ever run
the planner - so `run_id` is nullable and the batch stands on its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.scm import PlanException, PlanExceptionBatch
from app.services.error_handler import AppException
from app.services.scm.coverage_service import CoverageService
from app.services.scm.plan_exception_engine import (
    ItemReading,
    PlacedSupply,
    Position,
    RankedAction,
    classify,
    rank_actions,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

logger = logging.getLogger(__name__)

# Every action a decision may name. The route validates against the exception's OWN proposed
# actions, so this is only the outer bound.
ACTION_CODES = (
    "relink_so",
    "change_location",
    "release_to_pool",
    "split",
    "push_eta",
    "keep_and_pool",
    "accept",
)

_QTY_EPSILON = 0.0005


def _now() -> datetime:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


def _today() -> date:
    return _now().date()


# --------------------------------------------------------------------------- #
# positions, either side of the write
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Snapshot:
    """One product's position and the dated points behind it, for one side of the diff."""

    position: Position
    points: list[dict]


def snapshot(db: Session, product_ids: Sequence[str]) -> dict[str, Snapshot]:
    """Dated network position per product, plus the points a reviewer will be shown.

    Called on BOTH sides of the restatement so the before and after columns are the same
    arithmetic. Batched: one set of event queries for the whole affected set, not one per
    product, because a restatement can touch hundreds.
    """
    pids = [str(p) for p in product_ids]
    if not pids:
        return {}

    svc = CoverageService(db)
    positions = svc.network_positions(pids)
    demand_locations = _demand_locations(db, pids)
    first_need = _first_need_at(db, pids)

    out: dict[str, Snapshot] = {}
    for pid in pids:
        np = positions.get(pid)
        if np is None:
            continue
        out[pid] = Snapshot(
            position=Position(
                shortfall_at=np.shortfall_at,
                shortfall_qty=float(np.shortfall or 0.0),
                # What nothing committed will consume. `closing_balance` is the dated balance
                # at the horizon, so a positive one is stock that survives every commitment
                # in the window - which is the only surplus worth raising, since a balance
                # that dips and recovers is just timing.
                surplus_qty=max(0.0, float(np.closing_balance or 0.0)),
                first_need_at=first_need.get(pid),
                demand_warehouse_ids=tuple(demand_locations.get(pid, ())),
            ),
            points=[],
        )
    return out


def _first_need_at(db: Session, product_ids: Sequence[str]) -> dict[str, date]:
    """When each product's earliest OPEN committed demand falls due.

    The SAME predicates the dated engine nets on (`CoverageService._demand_events_many`):
    open order, open line, still outstanding. Reading a different definition of "committed"
    here would let this screen call an order early that the timeline beside it never counted.
    """
    pids = [str(p) for p in product_ids]
    if not pids:
        return {}
    rows = (
        db.query(SalesOrderLine.product_id, func.min(SalesOrderLine.required_date))
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id.in_(pids),
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
            SalesOrderLine.required_date.isnot(None),
        )
        .group_by(SalesOrderLine.product_id)
        .all()
    )
    return {str(pid): when for pid, when in rows if when is not None}


def _demand_locations(db: Session, product_ids: Sequence[str]) -> dict[str, list[str]]:
    """Which warehouses each product's open committed demand now ships from."""
    pids = [str(p) for p in product_ids]
    if not pids:
        return {}
    rows = (
        db.query(SalesOrderLine.product_id, SalesOrderLine.warehouse_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id.in_(pids),
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
            SalesOrderLine.warehouse_id.isnot(None),
        )
        .distinct()
        .all()
    )
    out: dict[str, list[str]] = {}
    for pid, wid in rows:
        out.setdefault(str(pid), []).append(str(wid))
    return out


# --------------------------------------------------------------------------- #
# the supply already placed
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _PlacedLine:
    supply: PlacedSupply
    po_number: Optional[str]


def _placed_supply(db: Session, product_ids: Sequence[str]) -> dict[str, list[_PlacedLine]]:
    """Open purchase-order lines per product: the orders an exception can be ABOUT.

    Only lines still outstanding (`qty_ordered > qty_received`) on a non-draft order, because
    an exception proposes changing an order that is really with a supplier. A draft is not
    placed, and amending it is ordinary editing rather than a decision anybody has to record.
    """
    pids = [str(p) for p in product_ids]
    if not pids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT pol.product_id::text AS pid,
                   pol.purchase_order_id::text AS po_id,
                   po.po_number AS po_number,
                   pol.warehouse_id::text AS warehouse_id,
                   COALESCE(pol.expected_date, po.expected_date) AS expected_date,
                   (COALESCE(pol.qty_ordered, 0) - COALESCE(pol.qty_received, 0)) AS qty
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON po.id = pol.purchase_order_id
            WHERE pol.product_id::text = ANY(:pids)
              AND pol.line_status = 'open'
              -- Placed, not drafted. `draft_recommendation` is a plan the engine
              -- staged and nobody has sent; amending it is ordinary editing, not a
              -- decision anybody has to record.
              AND po.status NOT IN ('draft', 'draft_recommendation')
              AND COALESCE(pol.qty_ordered, 0) > COALESCE(pol.qty_received, 0)
            """
        ),
        {"pids": pids},
    ).mappings().all()

    svc = CoverageService(db)
    out: dict[str, list[_PlacedLine]] = {}
    for r in rows:
        wid = r["warehouse_id"]
        pool_ids: tuple[str, ...] = ()
        if wid:
            pool = svc.pool_for_location(wid)
            if pool:
                pool_ids = tuple(str(w.id) for w in svc.pool_members(pool))
        out.setdefault(r["pid"], []).append(
            _PlacedLine(
                supply=PlacedSupply(
                    purchase_order_id=r["po_id"],
                    expected_date=r["expected_date"],
                    qty=float(r["qty"] or 0.0),
                    warehouse_id=wid,
                    pool_warehouse_ids=pool_ids,
                ),
                po_number=r["po_number"],
            )
        )
    return out


# --------------------------------------------------------------------------- #
# the item's reading (AC-D9) - four signals that already exist
# --------------------------------------------------------------------------- #

_READING_SOURCES = {
    "lifecycle": "products.is_discontinued",
    "velocity": "scm.item_classification",
    "business": "market_segments.demand_class",
    "last_po": "purchase_orders.issue_date",
}


def _readings(db: Session, product_ids: Sequence[str]) -> dict[str, ItemReading]:
    """Lifecycle, velocity, business class and last purchase date, per product.

    None of it is newly computed - all four already exist - and a signal genuinely absent
    stays None rather than being defaulted, because a default would silently change which
    action is proposed first.
    """
    pids = [str(p) for p in product_ids]
    if not pids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT p.id::text AS pid,
                   p.is_discontinued AS is_discontinued,
                   ic.abc_class AS abc_class,
                   ic.xyz_class AS xyz_class,
                   (SELECT MAX(po.issue_date)
                      FROM purchase_order_lines pol
                      JOIN purchase_orders po ON po.id = pol.purchase_order_id
                     WHERE pol.product_id = p.id) AS last_po_date
            FROM products p
            LEFT JOIN LATERAL (
                SELECT abc_class, xyz_class
                  FROM scm.item_classification c
                 WHERE c.product_id = p.id
                 ORDER BY c.computed_at DESC NULLS LAST
                 LIMIT 1
            ) ic ON true
            WHERE p.id::text = ANY(:pids)
            """
        ),
        {"pids": pids},
    ).mappings().all()

    demand_class = _demand_classes(db, pids)
    return {
        r["pid"]: ItemReading(
            is_discontinued=bool(r["is_discontinued"]),
            abc_class=r["abc_class"],
            xyz_class=r["xyz_class"],
            demand_class=demand_class.get(r["pid"]),
            last_po_date=r["last_po_date"],
        )
        for r in rows
    }


def _demand_classes(db: Session, product_ids: Sequence[str]) -> dict[str, str]:
    """The demand class the product's own committed demand carries.

    Read off the sales orders rather than a product column because the class is a property of
    who is buying it, not of the item: the same SKU is a project line for one customer and a
    retail line for another. The most common class over open demand wins, which is what
    "how this item reads" means for an item selling both ways.
    """
    rows = db.execute(
        text(
            """
            SELECT sol.product_id::text AS pid, so.order_type AS demand_class,
                   count(*) AS n
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            WHERE sol.product_id::text = ANY(:pids)
              AND sol.line_status = 'open'
              AND so.order_type IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 3 DESC
            """
        ),
        {"pids": [str(p) for p in product_ids]},
    ).mappings().all()
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(r["pid"], r["demand_class"])  # first per product = most common
    return out


def _reading_json(item: ItemReading) -> dict:
    """The reading as the screen shows it: a value AND the field it came from (AC-D12)."""
    velocity = (
        f"{item.abc_class} / {item.xyz_class}"
        if item.abc_class and item.xyz_class
        else (item.abc_class or item.xyz_class)
    )
    return {
        "lifecycle": {
            "value": "Discontinued" if item.is_discontinued else "Active",
            "source": _READING_SOURCES["lifecycle"],
        },
        "velocity": {"value": velocity, "source": _READING_SOURCES["velocity"]},
        "business": {
            "value": item.demand_class.title() if item.demand_class else None,
            "source": _READING_SOURCES["business"],
        },
        "last_po": {
            "value": item.last_po_date.isoformat() if item.last_po_date else None,
            "source": _READING_SOURCES["last_po"],
        },
    }


def _actions_json(actions: Iterable[RankedAction], candidate: Optional[dict]) -> list[dict]:
    out = []
    for a in actions:
        row = {
            "code": a.code,
            "rank": a.rank,
            "rationale": a.rationale,
            "candidate_so_number": None,
            "candidate_need_by": None,
            "candidate_warehouse_code": None,
        }
        if candidate and a.code in ("relink_so", "change_location"):
            row.update(candidate)
        out.append(row)
    return out


def _timeline_json(before: Snapshot, after: Snapshot) -> dict:
    """Before and after, frozen (AC-D4).

    Frozen rather than recomputed on read: the order book moves daily, so a timeline rebuilt
    when somebody opens the row is a different position wearing the same date, and the
    reviewer would be approving against numbers the engine never saw.
    """
    return {
        "before_points": before.points,
        "after_points": after.points,
        "before_shortfall_at": before.position.shortfall_at.isoformat()
        if before.position.shortfall_at
        else None,
        "after_shortfall_at": after.position.shortfall_at.isoformat()
        if after.position.shortfall_at
        else None,
        "before_shortfall_qty": before.position.shortfall_qty or None,
        "after_shortfall_qty": after.position.shortfall_qty or None,
    }


# --------------------------------------------------------------------------- #
# generating the batch
# --------------------------------------------------------------------------- #

def generate_batch(
    db: Session,
    *,
    before: dict[str, Snapshot],
    after: dict[str, Snapshot],
    delta_count: int,
    source_documents: Optional[Sequence[str]] = None,
    run_id: Optional[str] = None,
    actor: Optional[str] = None,
    last_upload_at: Optional[datetime] = None,
) -> PlanExceptionBatch:
    """Diff the restated plan against supply already placed, and freeze what disagrees.

    `delta_count` is the UPLOAD's own figure and is carried through unchanged (AC-D2b). It is
    deliberately not recounted from the exceptions: the reduction between the two is what the
    screen exists to show, and recounting would make them agree by construction.

    A batch row is written even when nothing disagrees. "This upload produced no exceptions"
    is a real answer and the screen has to be able to state it; no row at all is
    indistinguishable from an upload that was never confirmed.
    """
    pids = list(after.keys())
    placed = _placed_supply(db, pids)
    readings = _readings(db, pids)
    today = _today()

    batch = PlanExceptionBatch(
        run_id=run_id,
        as_of=today,
        generated_at=_now(),
        last_upload_at=last_upload_at or _now(),
        delta_count=int(delta_count),
        source_documents=list(source_documents or []),
        created_by=actor,
    )
    db.add(batch)
    db.flush()

    for pid in pids:
        after_snap = after[pid]
        before_snap = before.get(pid) or Snapshot(position=Position(), points=[])
        item = readings.get(pid, ItemReading())
        for line in placed.get(pid, []):
            finding = classify(before_snap.position, after_snap.position, line.supply)
            if finding is None or finding.quantity <= _QTY_EPSILON:
                continue
            actions = rank_actions(
                finding.exception_type, item, has_candidate_order=False
            )
            db.add(
                PlanException(
                    batch_id=batch.id,
                    product_id=pid,
                    warehouse_id=line.supply.warehouse_id,
                    pool_code=None,
                    exception_type=finding.exception_type,
                    quantity=finding.quantity,
                    purchase_order_id=line.supply.purchase_order_id,
                    po_expected_date=line.supply.expected_date,
                    timeline_json=_timeline_json(before_snap, after_snap),
                    reading_json=_reading_json(item),
                    actions_json=_actions_json(actions, None),
                    status="open",
                )
            )
    db.flush()
    return batch


# --------------------------------------------------------------------------- #
# reading and deciding
# --------------------------------------------------------------------------- #

def latest_batch(db: Session, run_id: Optional[str] = None) -> Optional[PlanExceptionBatch]:
    q = db.query(PlanExceptionBatch)
    if run_id:
        q = q.filter(PlanExceptionBatch.run_id == run_id)
    return q.order_by(PlanExceptionBatch.generated_at.desc()).first()


def report(db: Session, *, run_id: Optional[str] = None, status: Optional[str] = None) -> dict:
    """One batch, whole. Reads what the batch wrote and computes nothing.

    A GET that recomputed would give two people different answers to the same question
    minutes apart, and the reviewer's decision is against the frozen figures.
    """
    batch = latest_batch(db, run_id)
    if batch is None:
        # Not an error. An install where nothing has been re-uploaded yet genuinely has no
        # batch, and the screen states that rather than failing.
        return {
            "run_id": run_id,
            "as_of": None,
            "generated_at": None,
            "last_upload_at": None,
            "counts": {
                "delta_count": 0,
                "exception_count": 0,
                "open_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
            },
            "rows": [],
        }

    q = db.query(PlanException).filter(PlanException.batch_id == batch.id)
    rows = q.all()
    codes = _product_codes(db, [r.product_id for r in rows])
    warehouses = _warehouse_codes(db, [r.warehouse_id for r in rows if r.warehouse_id])
    po_numbers = _po_numbers(db, [r.purchase_order_id for r in rows if r.purchase_order_id])
    actors = _actor_names(db, [r.decided_by for r in rows if r.decided_by])

    visible = [r for r in rows if status is None or r.status == status]
    # Open first, then the type that can miss a customer date, then product code. The SERVER
    # owns this: a client free to re-sort could disagree with the urgency beside the row.
    order = {"shortfall_earlier": 0, "supply_wrong_location": 1, "supply_early": 2,
             "supply_surplus": 3}
    visible.sort(
        key=lambda r: (
            0 if r.status == "open" else 1,
            order.get(r.exception_type, 9),
            codes.get(str(r.product_id), ("", ""))[0],
        )
    )

    return {
        "run_id": str(batch.run_id) if batch.run_id else None,
        "as_of": batch.as_of.isoformat() if batch.as_of else None,
        "generated_at": batch.generated_at.isoformat() if batch.generated_at else None,
        "last_upload_at": batch.last_upload_at.isoformat() if batch.last_upload_at else None,
        "counts": {
            "delta_count": int(batch.delta_count or 0),
            "exception_count": len(rows),
            "open_count": sum(1 for r in rows if r.status == "open"),
            "approved_count": sum(1 for r in rows if r.status == "approved"),
            "rejected_count": sum(1 for r in rows if r.status == "rejected"),
        },
        "rows": [
            _row_out(r, codes, warehouses, po_numbers, actors) for r in visible
        ],
    }


def _row_out(r: PlanException, codes, warehouses, po_numbers, actors) -> dict:
    code, name = codes.get(str(r.product_id), (None, None))
    return {
        "exception_id": str(r.id),
        "exception_type": r.exception_type,
        "product_code": code,
        "product_name": name,
        "uom": None,
        "warehouse_code": warehouses.get(str(r.warehouse_id)) if r.warehouse_id else None,
        "pool_code": r.pool_code,
        "po_number": po_numbers.get(str(r.purchase_order_id)) if r.purchase_order_id else None,
        "po_expected_date": r.po_expected_date.isoformat() if r.po_expected_date else None,
        "quantity": float(r.quantity or 0.0),
        "timeline": r.timeline_json or {},
        "reading": r.reading_json or {},
        "actions": r.actions_json or [],
        "status": r.status,
        "decided_by": actors.get(str(r.decided_by)) if r.decided_by else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "decided_action": r.decided_action,
        "decision_reason": r.decision_reason,
    }


def _product_codes(db: Session, ids) -> dict[str, tuple[str, Optional[str]]]:
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    rows = db.query(Product.id, Product.product_code, Product.product_name).filter(
        Product.id.in_(ids)
    ).all()
    return {str(r[0]): (r[1], r[2]) for r in rows}


def _warehouse_codes(db: Session, ids) -> dict[str, str]:
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id::text AS id, warehouse_code FROM warehouses WHERE id::text = ANY(:ids)"),
        {"ids": ids},
    ).mappings().all()
    return {r["id"]: r["warehouse_code"] for r in rows}


def _po_numbers(db: Session, ids) -> dict[str, str]:
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id::text AS id, po_number FROM purchase_orders WHERE id::text = ANY(:ids)"),
        {"ids": ids},
    ).mappings().all()
    return {r["id"]: r["po_number"] for r in rows}


def _actor_names(db: Session, ids) -> dict[str, str]:
    """Human names, never user ids: the name is rendered beside the row."""
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    rows = db.execute(
        text(
            "SELECT id::text AS id, COALESCE(NULLIF(TRIM(name), ''), email) AS label "
            "FROM users WHERE id::text = ANY(:ids)"
        ),
        {"ids": ids},
    ).mappings().all()
    return {r["id"]: r["label"] for r in rows}


def decide(
    db: Session,
    exception_id: str,
    *,
    status: str,
    action_code: Optional[str] = None,
    reason: Optional[str] = None,
    split_qty: Optional[float] = None,
    actor: Optional[str] = None,
) -> PlanException:
    """Approve or reject one exception (AC-D6).

    The validation lives here rather than in the route because the UI must not be the only
    thing enforcing it:

      * approving names an action the ENGINE proposed for THIS exception - approving one it
        never proposed is not a decision about this exception,
      * rejecting requires a reason,
      * a split moves a part, strictly inside the quantity, because the remainder stays on
        the original line and the two must sum to it (AC-D11b),
      * an already-decided exception is a 409: re-deciding is a different operation, and
        silently overwriting loses who decided what.

    Approving a reallocation writes THIS row and nothing else. No placed purchase order is
    amended (AC-D7).
    """
    row = db.query(PlanException).filter(PlanException.id == exception_id).one_or_none()
    if row is None:
        raise AppException(404, "That exception does not exist.")
    if row.status != "open":
        raise AppException(409, "That exception has already been decided.")
    if status not in ("approved", "rejected"):
        raise AppException(422, "A decision is either approved or rejected.")

    if status == "rejected":
        if not (reason or "").strip():
            raise AppException(422, "A reason is required to reject an exception.")
        row.status = "rejected"
        row.decided_action = None
        row.decision_reason = reason.strip()
    else:
        proposed = {a.get("code") for a in (row.actions_json or [])}
        if action_code not in proposed:
            raise AppException(
                422, "Approving needs one of the actions proposed for this exception."
            )
        if action_code == "split":
            qty = float(split_qty or 0.0)
            whole = float(row.quantity or 0.0)
            if qty <= 0 or qty >= whole:
                raise AppException(
                    422,
                    "A split moves part of the line: the quantity must be above 0 and below "
                    f"{whole:g}.",
                )
            row.split_qty = qty
        row.status = "approved"
        row.decided_action = action_code
        row.decision_reason = (reason or "").strip() or None

    row.decided_by = actor
    row.decided_at = _now()
    db.flush()
    return row
