"""The SO book's own reaction to the plan (`documentation/plans/scm/PLAN-so-book-diff-
replanning.md` section 2).

A batch is born, best-effort, right after `outstanding_import_service.apply()` writes a
re-uploaded book: one row per PLANNED line the upload changed, what the line's active
decision holds today, the facts the suggestion rule used, and a suggested reaction the
planner already knows from the fulfilment board. Nothing is written to the plan until
`apply()` in this module runs, and that only touches the rows the planner accepted.

Kept ignorant of `outstanding_import_service`'s own internals beyond the `Diff` it hands
over - the same separation `project_so_ingest_service` keeps from the SCM import today - and
called from that module's `apply()`, never the reverse.

**`release` returns the WHOLE line to the board** (captain, 19 August 2026, PLAN section 6):
excluded from the new revision exactly like a `replan` row, so its Reserve hold is gone on
the next read AND its incoming/Buy parts are not carried either - they are re-proposed when
the line is next confirmed. `_check_line` permits no partial cover (a line named in a
`ConfirmLine` must sum to exactly its open quantity), so a "keep Buy, drop only Reserve"
composition has no seam without touching `project_supply_service.py`'s validation itself; a
real partial-cover seam is a follow-up, not this slice. AC-R08: release touches no Order
Inquiry row (a reserve is not a purchase) - existing rows are left exactly as
`refresh_for_decision` will find and revise them on the line's next confirmation.

Two further deliberate simplifications, flagged here because a future slice will want them
fixed properly rather than rediscovered by reading a bug report:

* **`replan` on `qty_up`** excludes the WHOLE line from the new revision (same as `advanced`)
  rather than freezing the existing covered quantity and running only the delta through the
  ladder - the same missing "partial confirm" seam.
* **`DATE_AND_QTY_CHANGED`** (both moved in one upload) is classified by DATE first: this
  build's own tie-break, because the section-0 table has no combined row and the two single
  changes disagree on suggestion.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.planning_change import (
    PLANNING_CHANGE_STATE_APPLIED,
    PLANNING_CHANGE_STATE_FAILED,
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.product import Product
from app.models.project_so import (
    ALLOC_SOURCE_OTHER_LOCATION,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    IV_ORDER,
    IV_RESERVE_AND_ORDER,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import Project
from app.models.scm import ItemClassification
from app.models.user import User
from app.services.error_handler import AppException
from app.services.scm.front_planning_engine import BORROW, BUY, RESERVE, TIMELY_SPO, qty_text
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    QTY_CHANGED,
    Diff,
)
from app.services.project_so_delta_service import RESERVE_WINDOW_DAYS

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed stored figure is data, not a crash
        return _ZERO


def _json_safe(value: Any) -> Any:
    """A board contribution carries raw `date`/`Decimal` values (it is normally serialized
    through a pydantic response model, not read as a plain dict); round-tripping through
    `json` here is what makes it storable in a JSONB column."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ============================================================================
# The rule table (section 0), pure. AC-R12 pins one test per row against this.
# ============================================================================


def suggest(kind: str, held: Optional[dict], facts: dict) -> Tuple[str, str]:
    """`(verb, why)` for one changed planned line. No I/O, no clock, no database.

    `kind`/`held`/`facts` are the wire shapes (`PlanningChangeKind`,
    `PlanningChangeHeld | None`, `PlanningChangeFacts`) as plain dicts.
    """
    days_moved = facts.get("days_moved") or 0
    window = facts.get("within_reserve_window") or {}
    window_days = window.get("window_days", RESERVE_WINDOW_DAYS)
    dealer = facts.get("dealer_hot_selling") or {}
    discontinued = bool(facts.get("discontinued"))
    buy_actioned = facts.get("buy_actioned") or {}

    # AC-R03: no active decision holds this line, whatever changed on the book. It simply
    # enters the board at its new date/quantity; no hold or OI row exists to touch.
    if held is None:
        if kind == "added":
            return (
                "replan",
                "New line on the book; nothing was ever held for it, so it simply enters "
                "the board at its new date.",
            )
        return (
            "replan",
            "No decision holds this line yet, so it simply enters the board at its new "
            "date and quantity.",
        )

    reserve = held.get("reserve") or []
    has_reserve = bool(reserve)
    locations = ", ".join(
        sorted({r.get("location") for r in reserve if r.get("location")})
    )

    if kind == "closed":
        return (
            "retire",
            "The line is closed in the book; the reserve and the remaining Buy are "
            "released, and an already-actioned inquiry row is kept with a note rather "
            "than retired.",
        )
    if kind == "advanced":
        plural = "" if abs(days_moved) == 1 else "s"
        return (
            "replan",
            f"Advanced {abs(days_moved)} day{plural}; the line runs the ladder again at "
            "the new date now, and the fresh proposal shows in the row and on the board.",
        )
    if kind == "qty_up":
        return (
            "replan",
            "Quantity increased; the existing components stay held, and only the extra "
            "quantity runs the ladder.",
        )
    if kind == "qty_down":
        return (
            "reduce",
            "Quantity decreased; the reserve stays, the Buy is reduced for the drop, and "
            "the inquiry row is cancelled for the drop.",
        )

    # kind == "delayed" from here.
    if has_reserve:
        if discontinued:
            return (
                "keep",
                "Discontinued: it cannot be bought again, so the reserve is kept "
                "whatever the size of the delay.",
            )
        if dealer.get("value"):
            where = ", ".join(dealer.get("where") or []) or locations
            return (
                "release",
                f"Dealer hot-selling at {where}: retail needs the pool stock now, so "
                "the reserve is released back to the pool whatever the size of the "
                "delay - back on the board.",
            )
        if window.get("value"):
            return (
                "keep",
                f"New date is {days_moved} days out and inside the {window_days}-day "
                "reserve window; the reserve stays put rather than being released and "
                "re-taken.",
            )
        return (
            "release",
            f"New date is {days_moved} days out, beyond the {window_days}-day reserve "
            f"window; the reserve is released back to {locations or 'its location'} "
            "rather than sitting idle for months - back on the board.",
        )

    # No reserve: only Buy (or nothing measurable) is held.
    if buy_actioned.get("value"):
        po_number = buy_actioned.get("po_number")
        po_text = f" ({po_number})" if po_number else ""
        return (
            "keep",
            f"The Buy this line holds is already a placed purchase order{po_text}; "
            "nothing in the plan changes, and the inquiry row notes the delay.",
        )
    return (
        "keep",
        "Only a Buy is held and purchasing has not actioned it yet; the Buy stands and "
        "the inquiry row is updated to DELAY with the previous date.",
    )


def _map_kind(c) -> str:
    if c.kind == CLOSED:
        return "closed"
    if c.kind == ADDED:
        return "added"
    if c.kind == QTY_CHANGED:
        return "qty_up" if c.qty_delta > 0 else "qty_down"
    days = c.days_moved or 0
    if c.kind == DATE_MOVED:
        return "advanced" if days < 0 else "delayed"
    # DATE_AND_QTY_CHANGED: date first (see module docstring).
    if days:
        return "advanced" if days < 0 else "delayed"
    return "qty_up" if c.qty_delta > 0 else "qty_down"


def _from_to(c) -> Tuple[dict, dict]:
    before = c.before
    after = c.after
    from_ = {
        "required_date": before.required_date.isoformat()
        if before and before.required_date
        else None,
        "qty": qty_text(_dec(before.qty)) if before else None,
        "status": "open" if before else None,
    }
    if c.kind == CLOSED:
        to_ = {"required_date": None, "qty": None, "status": "closed"}
    else:
        to_ = {
            "required_date": after.required_date.isoformat()
            if after and after.required_date
            else None,
            "qty": qty_text(_dec(after.qty)) if after else None,
            "status": "open" if after else None,
        }
    return from_, to_


def _board_link(so_number: str, item_code: str, when: Optional[date]) -> str:
    when_part = when.isoformat() if when else ""
    return f"/project-sales/fulfilment-planning?orders={so_number}&cell={item_code}|{when_part}"


# ============================================================================
# Building a batch
# ============================================================================


def build_batch(
    db: Session,
    diff: Diff,
    *,
    applied_line_ids: Dict[int, str],
    order_ids: Dict[str, str],
    actor: Optional[str],
    import_job_id: Optional[str],
    file_name: Optional[str],
) -> Optional[PlanningChangeBatch]:
    """One row per PLANNED line the upload changed (AC-R01). `None` when nothing planned
    changed - the caller shows nothing for such an upload.

    `applied_line_ids` / `order_ids` are `outstanding_import_service.apply()`'s own local
    state, passed in because an ADDED change's `row_ref` is a source ROW NUMBER, not a
    line id, and by the time this runs the write has already happened.
    """
    from app.services.project_fulfilment_board_service import FulfilmentBoardService
    from app.services.project_supply_service import ProjectSupplyService

    changed = [c for c in diff.changes if c.kind not in ("unchanged",)]
    if not changed:
        return None

    core_line_ids = {applied_line_ids.get(id(c)) for c in changed}
    core_line_ids.discard(None)
    project_lines_by_core: Dict[str, ProjectSalesOrderLine] = {}
    if core_line_ids:
        for pl in (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(list(core_line_ids)))
            .all()
        ):
            project_lines_by_core[str(pl.core_sales_order_line_id)] = pl

    order_core_ids = {v for v in order_ids.values() if v}
    pso_by_core_so: Dict[str, ProjectSalesOrder] = {}
    if order_core_ids:
        for pso in (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id.in_(list(order_core_ids)))
            .all()
        ):
            pso_by_core_so[str(pso.so_id)] = pso

    entries: List[dict] = []
    for c in changed:
        core_line_id = applied_line_ids.get(id(c))
        if not core_line_id:
            continue
        if c.kind == ADDED:
            core_so_id = order_ids.get(c.doc_number)
            pso = pso_by_core_so.get(str(core_so_id)) if core_so_id else None
            if pso is None:
                continue
            entries.append(
                {"change": c, "core_line_id": core_line_id, "project_line": None, "order": pso}
            )
            continue
        project_line = project_lines_by_core.get(core_line_id)
        if project_line is None:
            continue
        pso = (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == project_line.project_sales_order_id)
            .one_or_none()
        )
        if pso is None:
            continue
        entries.append(
            {
                "change": c,
                "core_line_id": core_line_id,
                "project_line": project_line,
                "order": pso,
            }
        )

    if not entries:
        return None

    core_line_ids_all = [e["core_line_id"] for e in entries]
    product_by_core: Dict[str, Optional[str]] = {}
    for cid, pid in (
        db.query(SalesOrderLine.id, SalesOrderLine.product_id)
        .filter(SalesOrderLine.id.in_(core_line_ids_all))
        .all()
    ):
        product_by_core[str(cid)] = str(pid) if pid else None

    for e in entries:
        e["product_id"] = product_by_core.get(e["core_line_id"])

    product_ids = {e["product_id"] for e in entries if e["product_id"]}
    dealer_where, project_where = _hot_selling_evidence(db, product_ids)
    discontinued_ids = _discontinued_products(db, product_ids)
    product_names = _product_names(db, product_ids)

    by_order: Dict[str, List[dict]] = defaultdict(list)
    for e in entries:
        by_order[str(e["order"].id)].append(e)

    batch = PlanningChangeBatch(
        import_job_id=import_job_id,
        upload_file_name=file_name,
        created_by=actor,
        order_count=len(by_order),
        line_count=len(entries),
    )
    db.add(batch)
    db.flush()

    supply = ProjectSupplyService(db)
    board_cache: Dict[str, dict] = {}

    for pso_id, group in by_order.items():
        order = group[0]["order"]
        active_decision = supply.active_decision(pso_id)
        latest_decision = supply.latest_decision(pso_id)
        revision_no = (
            active_decision.revision_no
            if active_decision
            else (latest_decision.revision_no if latest_decision else 0)
        )
        frozen = supply.frozen_lines_of(active_decision)
        so_number = _so_number(order)
        for e in group:
            row = _build_row(
                db,
                batch,
                order,
                e,
                frozen,
                revision_no,
                dealer_where,
                project_where,
                discontinued_ids,
                product_names,
                board_cache,
                so_number,
            )
            db.add(row)
    db.flush()
    return batch


def _so_number(order: ProjectSalesOrder) -> str:
    return order.autocount_doc_no or order.provisional_ref or str(order.id)


def _hot_selling_evidence(
    db: Session, product_ids: set
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Dealer / project hot-selling evidence: locations holding ABC A on that demand class.

    A lightweight standalone read rather than `ProjectSupplyService._classification` (which
    another slice is actively editing for wording/evidence): same predicate, same columns.
    """
    if not product_ids:
        return {}, {}
    rows = (
        db.query(
            ItemClassification.product_id,
            ItemClassification.abc_class_retail,
            ItemClassification.abc_class_project,
            Warehouse.warehouse_code,
        )
        .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
        .filter(
            ItemClassification.product_id.in_(list(product_ids)),
            Warehouse.is_active.is_(True),
            Warehouse.counts_as_available.is_(True),
        )
        .all()
    )
    dealer_where: Dict[str, List[str]] = {}
    project_where: Dict[str, List[str]] = {}
    for pid, abc_retail, abc_project, code in rows:
        pid = str(pid)
        if (abc_retail or "").upper() == "A":
            dealer_where.setdefault(pid, []).append(code or "")
        if (abc_project or "").upper() == "A":
            project_where.setdefault(pid, []).append(code or "")
    for codes in dealer_where.values():
        codes.sort()
    for codes in project_where.values():
        codes.sort()
    return dealer_where, project_where


def _discontinued_products(db: Session, product_ids: set) -> set:
    if not product_ids:
        return set()
    rows = (
        db.query(Product.id)
        .filter(Product.id.in_(list(product_ids)), Product.is_discontinued.is_(True))
        .all()
    )
    return {str(r[0]) for r in rows}


def _product_names(db: Session, product_ids: set) -> Dict[str, str]:
    if not product_ids:
        return {}
    rows = db.query(Product.id, Product.product_name).filter(Product.id.in_(list(product_ids))).all()
    return {str(pid): name for pid, name in rows}


def _held_from_frozen(frozen_entry: dict, revision_no: int) -> dict:
    components = frozen_entry.get("components") or []
    reserve = [
        {
            "location": c.get("source_location"),
            "warehouse_id": c.get("source_warehouse_id"),
            "qty": c.get("qty"),
        }
        for c in components
        if c.get("kind") == RESERVE
    ]
    borrow = [
        {
            "location": c.get("source_location"),
            "warehouse_id": c.get("source_warehouse_id"),
            "qty": c.get("qty"),
            "source": c.get("source"),
        }
        for c in components
        if c.get("kind") == BORROW
    ]
    buy_qty = sum((_dec(c.get("qty")) for c in components if c.get("kind") == BUY), _ZERO)
    timely_qty = sum(
        (_dec(c.get("qty")) for c in components if c.get("kind") == TIMELY_SPO), _ZERO
    )
    return {
        "reserve": reserve,
        "borrow": borrow,
        "buy_qty": qty_text(buy_qty),
        "timely_spo_qty": qty_text(timely_qty),
        "revision_no": revision_no,
    }


def _inquiry_rows_and_buy_actioned(
    db: Session, project_line_id: Optional[str]
) -> Tuple[List[dict], dict]:
    if not project_line_id:
        return [], {"value": False, "po_number": None}
    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == project_line_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(OrderInquiryRow.created_at.desc())
        .all()
    )
    out = [
        {
            "id": str(r.id),
            "verb": r.verb,
            "qty": qty_text(_dec(r.qty)),
            "state": r.state,
        }
        for r in rows
    ]
    actioned_buy = next(
        (
            r
            for r in rows
            if r.state == INQUIRY_ACTIONED and r.verb in (IV_ORDER, IV_RESERVE_AND_ORDER)
        ),
        None,
    )
    return out, {
        "value": actioned_buy is not None,
        "po_number": actioned_buy.spo_ref if actioned_buy else None,
    }


def _proposal_for(
    db: Session, board_cache: Dict[str, dict], so_number: str, core_line_id: str,
    project_line_id: Optional[str],
) -> Optional[dict]:
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    board = board_cache.get(so_number)
    if board is None:
        try:
            board = FulfilmentBoardService(db).build([so_number], granularity="week")
        except Exception:  # noqa: BLE001 - a proposal is a nicety, never a build blocker
            logger.exception("planning change proposal build failed for %s", so_number)
            board = {}
        board_cache[so_number] = board
    for cell in board.get("cells", []) or []:
        for contribution in cell.get("contributions", []) or []:
            if contribution.get("line_id") == core_line_id or (
                project_line_id and contribution.get("project_line_id") == project_line_id
            ):
                return contribution
    return None


def _build_row(
    db: Session,
    batch: PlanningChangeBatch,
    order: ProjectSalesOrder,
    entry: dict,
    frozen: Dict[str, dict],
    revision_no: int,
    dealer_where: Dict[str, List[str]],
    project_where: Dict[str, List[str]],
    discontinued_ids: set,
    product_names: Dict[str, str],
    board_cache: Dict[str, dict],
    so_number: str,
) -> PlanningChangeRow:
    c = entry["change"]
    project_line: Optional[ProjectSalesOrderLine] = entry["project_line"]
    product_id = entry.get("product_id")
    kind = _map_kind(c)
    from_json, to_json = _from_to(c)
    days_moved = c.days_moved

    project_line_id = str(project_line.id) if project_line else None
    frozen_entry = frozen.get(project_line_id) if project_line_id else None
    held = _held_from_frozen(frozen_entry, revision_no) if frozen_entry else None

    new_date = _as_date(to_json.get("required_date")) or _as_date(from_json.get("required_date"))
    old_date = _as_date(from_json.get("required_date"))
    window_end = None
    if old_date:
        from datetime import timedelta

        window_end = old_date + timedelta(days=RESERVE_WINDOW_DAYS)
    within_window = bool(days_moved is not None and abs(days_moved) <= RESERVE_WINDOW_DAYS)

    inquiry_rows, buy_actioned = _inquiry_rows_and_buy_actioned(db, project_line_id)

    facts = {
        "dealer_hot_selling": {
            "value": bool(product_id and product_id in dealer_where),
            "where": dealer_where.get(product_id, []) if product_id else [],
        },
        "project_hot_selling": {
            "value": bool(product_id and product_id in project_where),
            "where": project_where.get(product_id, []) if product_id else [],
        },
        "discontinued": bool(product_id and product_id in discontinued_ids),
        "days_moved": days_moved or 0,
        "within_reserve_window": {
            "value": within_window,
            "window_days": RESERVE_WINDOW_DAYS,
            "new_date": new_date.isoformat() if new_date else None,
            "window_end": window_end.isoformat() if window_end else None,
        },
        "buy_actioned": buy_actioned,
    }

    suggested, why = suggest(kind, held, facts)

    proposal = None
    if suggested == "replan" and project_line_id:
        proposal = _json_safe(
            _proposal_for(db, board_cache, so_number, entry["core_line_id"], project_line_id)
        )

    board_link = _board_link(so_number, c.item_code, new_date or old_date)

    return PlanningChangeRow(
        batch_id=batch.id,
        project_sales_order_id=str(order.id),
        project_line_id=project_line_id,
        core_line_id=entry["core_line_id"],
        line_no=(project_line.line_no if project_line else None),
        item_code=c.item_code,
        product_name=product_names.get(product_id) if product_id else None,
        kind=kind,
        from_json=from_json,
        to_json=to_json,
        days_moved=days_moved,
        held_json=held,
        facts_json=facts,
        inquiry_rows_json=inquiry_rows,
        suggested=suggested,
        why=why,
        proposal_json=proposal,
        decision=(None if held is None else "accept"),
        applied_state=PLANNING_CHANGE_STATE_PENDING,
        board_link=board_link,
    )


# ============================================================================
# Reading a batch back
# ============================================================================


def _user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    row = db.query(User.name).filter(User.id == user_id).first()
    return row[0] if row else None


def _exc_message(exc: Exception) -> str:
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        return str(exc.detail.get("message") or exc.detail)
    return str(exc)


def _batch_or_404(db: Session, batch_id: str) -> PlanningChangeBatch:
    batch = (
        db.query(PlanningChangeBatch).filter(PlanningChangeBatch.id == batch_id).one_or_none()
    )
    if batch is None:
        raise AppException(
            status_code=404,
            message="This planning change batch could not be found.",
            code="planning_change_batch_not_found",
        )
    return batch


def _source_out(batch: PlanningChangeBatch) -> dict:
    return {
        "upload_id": str(batch.import_job_id) if batch.import_job_id else str(batch.id),
        "file_name": batch.upload_file_name or "",
        "kind": batch.source_kind,
        "import_job_id": str(batch.import_job_id) if batch.import_job_id else None,
    }


def _row_is_superseded(db: Session, row: PlanningChangeRow) -> bool:
    from app.services.project_supply_service import ProjectSupplyService

    if not row.held_json:
        return False
    snapshot_rev = row.held_json.get("revision_no")
    if snapshot_rev is None:
        return False
    supply = ProjectSupplyService(db)
    pso_id = str(row.project_sales_order_id)
    active = supply.active_decision(pso_id)
    latest = supply.latest_decision(pso_id)
    current = active.revision_no if active else (latest.revision_no if latest else 0)
    return current != snapshot_rev


def row_out(db: Session, row: PlanningChangeRow) -> dict:
    applied_state = row.applied_state
    if applied_state == PLANNING_CHANGE_STATE_PENDING and _row_is_superseded(db, row):
        applied_state = PLANNING_CHANGE_STATE_SUPERSEDED
    return {
        "id": str(row.id),
        "line_no": row.line_no or 0,
        "item_code": row.item_code or "",
        "product_name": row.product_name,
        "kind": row.kind,
        "from": row.from_json or {},
        "to": row.to_json or {},
        "days_moved": row.days_moved,
        "held": row.held_json,
        "facts": row.facts_json,
        "suggested": row.suggested,
        "why": row.why,
        "proposal": row.proposal_json,
        "inquiry_rows": row.inquiry_rows_json or [],
        "decision": row.decision,
        "applied_state": applied_state,
        "applied_reason": row.applied_reason,
        "board_link": row.board_link,
    }


def _order_labels(db: Session, order: ProjectSalesOrder) -> Tuple[Optional[str], Optional[str]]:
    customer_name = None
    project_label = None
    if order.project_id:
        row = db.query(Project.title).filter(Project.id == order.project_id).first()
        project_label = row[0] if row else None
    if order.so_id:
        row = db.query(SalesOrder.customer_id).filter(SalesOrder.id == order.so_id).first()
        if row and row[0]:
            cust = db.query(Customer.customer_name).filter(Customer.id == row[0]).first()
            customer_name = cust[0] if cust else None
    return customer_name, project_label


def get_batch(db: Session, batch_id: str) -> dict:
    from app.services.project_supply_service import ProjectSupplyService

    batch = _batch_or_404(db, batch_id)
    rows = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch.id)
        .order_by(PlanningChangeRow.created_at.asc())
        .all()
    )
    by_order: Dict[str, List[PlanningChangeRow]] = defaultdict(list)
    for r in rows:
        by_order[str(r.project_sales_order_id)].append(r)

    orders_map: Dict[str, ProjectSalesOrder] = {}
    if by_order:
        for o in (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id.in_(list(by_order.keys())))
            .all()
        ):
            orders_map[str(o.id)] = o

    supply = ProjectSupplyService(db)
    orders_out = []
    for pso_id, order_rows in by_order.items():
        order = orders_map.get(pso_id)
        if order is None:
            continue
        active = supply.active_decision(pso_id)
        latest = supply.latest_decision(pso_id)
        revision_no = active.revision_no if active else (latest.revision_no if latest else 0)
        customer_name, project_label = _order_labels(db, order)
        orders_out.append(
            {
                "project_sales_order_id": pso_id,
                "so_number": _so_number(order),
                "customer_name": customer_name,
                "project_label": project_label,
                "revision_no": revision_no,
                "rows": [row_out(db, r) for r in order_rows],
                "is_adopted": bool(order.so_id) and order.project_id is None,
                "core_sales_order_id": str(order.so_id) if order.so_id else None,
                "project_id": str(order.project_id) if order.project_id else None,
            }
        )

    return {
        "id": str(batch.id),
        "created_at": batch.created_at,
        "created_by_name": _user_name(db, batch.created_by),
        "source": _source_out(batch),
        "applied_at": batch.applied_at,
        "applied_by_name": _user_name(db, batch.applied_by) if batch.applied_by else None,
        "result": batch.result_json,
        "orders": orders_out,
    }


def _summary_out(db: Session, batch: PlanningChangeBatch) -> dict:
    rows = (
        db.query(PlanningChangeRow.applied_state)
        .filter(PlanningChangeRow.batch_id == batch.id)
        .all()
    )
    pending = sum(1 for (s,) in rows if s == PLANNING_CHANGE_STATE_PENDING)
    failed = sum(1 for (s,) in rows if s == PLANNING_CHANGE_STATE_FAILED)
    return {
        "id": str(batch.id),
        "created_at": batch.created_at,
        "created_by_name": _user_name(db, batch.created_by),
        "source": _source_out(batch),
        "order_count": batch.order_count,
        "line_count": batch.line_count,
        "pending_count": pending,
        "failed_count": failed,
        "applied_at": batch.applied_at,
        "applied_by_name": _user_name(db, batch.applied_by) if batch.applied_by else None,
    }


def list_batches(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    query: Optional[str] = None,
    state: Optional[str] = None,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
) -> dict:
    q = db.query(PlanningChangeBatch)
    if state == "pending":
        q = q.filter(PlanningChangeBatch.applied_at.is_(None))
    elif state == "applied":
        q = q.filter(PlanningChangeBatch.applied_at.isnot(None))
    needle = (query or "").strip()
    if needle:
        q = q.filter(PlanningChangeBatch.upload_file_name.ilike(f"%{needle}%"))
    q = q.order_by(
        PlanningChangeBatch.created_at.asc()
        if (direction or "desc") == "asc"
        else PlanningChangeBatch.created_at.desc()
    )
    total = q.count()
    offset = max(page - 1, 0) * max(limit, 1)
    batches = q.offset(offset).limit(limit).all()
    return {
        "data": [_summary_out(db, b) for b in batches],
        "total": total,
        "page": page,
        "limit": limit,
    }


def set_row_decision(
    db: Session, batch_id: str, row_id: str, decision: Optional[str]
) -> dict:
    batch = _batch_or_404(db, batch_id)
    if batch.applied_at is not None:
        raise AppException(
            status_code=409,
            message="This batch has already been applied.",
            code="planning_change_batch_applied",
        )
    row = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.id == row_id, PlanningChangeRow.batch_id == batch.id)
        .one_or_none()
    )
    if row is None:
        raise AppException(
            status_code=404,
            message="This row could not be found.",
            code="planning_change_row_not_found",
        )
    if row.held_json is None and decision is not None:
        raise AppException(
            status_code=422,
            message=(
                "This row has no active decision to act on; it enters the board on its "
                "own."
            ),
            code="planning_change_row_no_decision",
        )
    if decision == "accept" and _row_is_superseded(db, row):
        raise AppException(
            status_code=409,
            message=(
                "The board confirmed a newer revision on this line since this batch was "
                "built."
            ),
            code="planning_change_row_superseded",
        )
    row.decision = decision
    db.flush()
    return row_out(db, row)


# ============================================================================
# Apply
# ============================================================================


def _confirm_payload(project_line_id: str, frozen_entry: dict) -> dict:
    components = frozen_entry.get("components") or []
    reserve = [
        {"warehouse_id": c.get("source_warehouse_id"), "qty": _dec(c.get("qty"))}
        for c in components
        if c.get("kind") == RESERVE and c.get("source_warehouse_id")
    ]
    borrow = [
        {
            "source": c.get("source") or ALLOC_SOURCE_OTHER_LOCATION,
            "warehouse_id": c.get("source_warehouse_id"),
            "donor_project_id": c.get("donor_project_id"),
            "qty": _dec(c.get("qty")),
            "reason": c.get("cs_reason") or "",
        }
        for c in components
        if c.get("kind") == BORROW and c.get("source_warehouse_id")
    ]
    buy_qty = sum((_dec(c.get("qty")) for c in components if c.get("kind") == BUY), _ZERO)
    timely_qty = sum(
        (_dec(c.get("qty")) for c in components if c.get("kind") == TIMELY_SPO), _ZERO
    )
    return {
        "project_line_id": project_line_id,
        "timely_spo_qty": timely_qty,
        "reserve": reserve,
        "borrow": borrow,
        "buy_qty": buy_qty,
        "buy_reason": frozen_entry.get("buy_reason"),
        "amend_reason": frozen_entry.get("amend_reason"),
    }


def _released_reserve(held: Optional[dict]) -> dict:
    """What AC-R06's `released` result names: the location(s) and quantity a `release` row
    gave up. Read off the row's own frozen `held_json` (what it said at build time), never a
    `ConfirmLine` - the line is excluded from the new revision entirely (module docstring)."""
    reserve = (held or {}).get("reserve") or []
    qty = sum((_dec(r.get("qty")) for r in reserve), _ZERO)
    locations = sorted({r.get("location") for r in reserve if r.get("location")})
    return {"location": ", ".join(locations) or None, "qty": qty_text(qty)}


def _confirm_payload_reduce(project_line_id: str, frozen_entry: dict, new_qty: Decimal) -> dict:
    """AC-R08's "Reduce": the drop comes off Buy first, then Reserve, then Borrow."""
    payload = _confirm_payload(project_line_id, frozen_entry)
    reserve_total = sum((c["qty"] for c in payload["reserve"]), _ZERO)
    borrow_total = sum((c["qty"] for c in payload["borrow"]), _ZERO)
    total = payload["timely_spo_qty"] + reserve_total + borrow_total + payload["buy_qty"]
    drop = total - new_qty
    if drop < _ZERO:
        drop = _ZERO

    take = min(drop, payload["buy_qty"])
    payload["buy_qty"] -= take
    drop -= take

    if drop > _ZERO and payload["reserve"]:
        kept = []
        for c in sorted(payload["reserve"], key=lambda item: -item["qty"]):
            if drop > _ZERO:
                take = min(drop, c["qty"])
                c["qty"] -= take
                drop -= take
            if c["qty"] > _ZERO:
                kept.append(c)
        payload["reserve"] = kept

    if drop > _ZERO and payload["borrow"]:
        kept = []
        for c in sorted(payload["borrow"], key=lambda item: -item["qty"]):
            if drop > _ZERO:
                take = min(drop, c["qty"])
                c["qty"] -= take
                drop -= take
            if c["qty"] > _ZERO:
                kept.append(c)
        payload["borrow"] = kept

    return payload


def _to_confirm_line(payload: dict):
    from app.schemas.project_supply import (
        ConfirmBorrowComponent,
        ConfirmLine,
        ConfirmReserveComponent,
    )

    return ConfirmLine(
        project_line_id=payload["project_line_id"],
        timely_spo_qty=payload["timely_spo_qty"],
        reserve=[
            ConfirmReserveComponent(warehouse_id=c["warehouse_id"], qty=c["qty"])
            for c in payload["reserve"]
        ],
        borrow=[
            ConfirmBorrowComponent(
                source=c["source"],
                warehouse_id=c["warehouse_id"],
                donor_project_id=c.get("donor_project_id"),
                qty=c["qty"],
                reason=c.get("reason") or "",
            )
            for c in payload["borrow"]
        ],
        buy_qty=payload["buy_qty"],
        buy_reason=payload.get("buy_reason"),
        amend_reason=payload.get("amend_reason"),
    )


def _oi_demand_rows(
    db: Session, live_rows: Sequence[PlanningChangeRow]
) -> Tuple[List[dict], Dict[str, int]]:
    from app.services.project_order_inquiry_engine import (
        CHANGE_DATE_EARLIER,
        CHANGE_DATE_LATER,
        CHANGE_QTY_DECREASE,
    )

    core_ids = [r.core_line_id for r in live_rows if r.core_line_id]
    product_by_core: Dict[str, Optional[str]] = {}
    if core_ids:
        for cid, pid in (
            db.query(SalesOrderLine.id, SalesOrderLine.product_id)
            .filter(SalesOrderLine.id.in_(core_ids))
            .all()
        ):
            product_by_core[str(cid)] = str(pid) if pid else None

    out: List[dict] = []
    counts: Dict[str, int] = {}
    for r in live_rows:
        if not r.project_line_id:
            continue
        # AC-R08: a Release is not a purchasing instruction - the reserve simply frees.
        if r.suggested == "release":
            continue
        held = r.held_json or {}
        location = None
        reserve = held.get("reserve") or []
        if reserve:
            location = reserve[0].get("location")
        product_id = product_by_core.get(r.core_line_id or "")

        if r.kind in ("delayed", "advanced"):
            qty = _dec((r.to_json or {}).get("qty"))
            if qty <= _ZERO:
                continue
            from_date = (r.from_json or {}).get("required_date")
            out.append(
                {
                    "line_id": r.project_line_id,
                    "product_id": product_id,
                    "item_code": r.item_code,
                    "qty": qty,
                    "delivery_date": _as_date((r.to_json or {}).get("required_date")),
                    "stock_location": location,
                    "change": CHANGE_DATE_LATER if r.kind == "delayed" else CHANGE_DATE_EARLIER,
                    "note": f"Was {from_date}" if from_date else "No previous delivery date",
                }
            )
            counts["DELAY" if r.kind == "delayed" else "ADVANCE"] = (
                counts.get("DELAY" if r.kind == "delayed" else "ADVANCE", 0) + 1
            )
        elif r.kind == "qty_down":
            from_qty = _dec((r.from_json or {}).get("qty"))
            to_qty = _dec((r.to_json or {}).get("qty"))
            drop = from_qty - to_qty
            if drop <= _ZERO:
                continue
            out.append(
                {
                    "line_id": r.project_line_id,
                    "product_id": product_id,
                    "item_code": r.item_code,
                    "qty": drop,
                    "delivery_date": _as_date((r.to_json or {}).get("required_date")),
                    "stock_location": location,
                    "change": CHANGE_QTY_DECREASE,
                    "note": f"Was {qty_text(from_qty)}, now {qty_text(to_qty)}",
                }
            )
            counts["CANCEL_BALANCE"] = counts.get("CANCEL_BALANCE", 0) + 1
    return out, counts


def _retire_inquiry_rows(db: Session, project_line_id: Optional[str], reason: str) -> int:
    if not project_line_id:
        return 0
    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == project_line_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    count = 0
    for row in rows:
        note = f"{row.note}\n{reason}" if row.note else reason
        if row.state == INQUIRY_ACTIONED:
            row.note = note
        else:
            row.state = INQUIRY_CANCELLED
            row.note = note
            count += 1
    return count


def _notify_purchasing(
    db: Session, order: ProjectSalesOrder, so_number: str, batch: PlanningChangeBatch
) -> bool:
    """AC-R09: purchasing told once per order, by a batch link. Best-effort - Apply has
    already written the plan and Order Inquiry changes by the time this runs."""
    try:
        from app.services.notification_service import NotificationService
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        user_ids = ProjectOrderInquiryService(db)._purchasing_user_ids()
        if not user_ids:
            return False
        service = NotificationService(db)
        for user_id in user_ids:
            service.create_with_channel_preferences(
                user_id=str(user_id),
                type="project_order_inquiry_raised",
                title=f"Planning change applied - {so_number}",
                body=f"The SO book moved lines on {so_number}; review what changed.",
                data={"planning_change_batch_id": str(batch.id), "so_number": so_number},
                source_entity_type="planning_change_batch",
                source_entity_id=str(batch.id),
                dedup_key=f"{batch.id}:{order.id}:planning_change_applied",
                event_type="project_order_inquiry_raised",
                send_in_app=True,
                send_email=False,
            )
        return True
    except Exception:  # noqa: BLE001 - a notify failure must not undo a written plan
        logger.exception("planning change purchasing notify failed for order %s", order.id)
        return False


def _apply_one_order(
    db: Session,
    supply,
    order: ProjectSalesOrder,
    order_rows: Sequence[PlanningChangeRow],
    actor: Optional[str],
    batch: PlanningChangeBatch,
) -> dict:
    from app.schemas.project_supply import ConfirmSupplyBody
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    pso_id = str(order.id)
    so_number = _so_number(order)
    active_decision = supply.active_decision(pso_id)
    latest_decision = supply.latest_decision(pso_id)
    current_revision = (
        active_decision.revision_no
        if active_decision
        else (latest_decision.revision_no if latest_decision else 0)
    )
    frozen = supply.frozen_lines_of(active_decision)

    accepted = [
        r
        for r in order_rows
        if r.decision == "accept" and r.applied_state == PLANNING_CHANGE_STATE_PENDING
    ]
    empty_result = {
        "revised": False,
        "revision_no": current_revision,
        "lines_replanned": 0,
        "inquiry_counts": {},
        "notified": False,
    }
    if not accepted:
        return empty_result

    live: List[PlanningChangeRow] = []
    for r in accepted:
        snapshot_rev = (r.held_json or {}).get("revision_no")
        if snapshot_rev is not None and snapshot_rev != current_revision:
            r.applied_state = PLANNING_CHANGE_STATE_SUPERSEDED
            r.applied_reason = (
                "The board confirmed a newer revision on this line after this batch was "
                "built."
            )
        else:
            live.append(r)
    if not live:
        return empty_result

    by_line_id = {r.project_line_id: r for r in live if r.project_line_id}
    confirm_lines: List[dict] = []
    replanned = 0
    retired = 0
    for line_id, frozen_entry in frozen.items():
        row = by_line_id.get(line_id)
        if row is None:
            confirm_lines.append(_confirm_payload(line_id, frozen_entry))
            continue
        if row.suggested in ("replan", "release"):
            # AC-R06 (release): the WHOLE line returns to the board, not just the reserve
            # portion - `_check_line` permits no partial cover (module docstring). Its
            # Reserve hold is gone the moment it is absent from this revision; its
            # incoming/Buy parts are simply re-proposed when the line is next confirmed.
            replanned += 1
            continue
        if row.suggested == "retire":
            retired += 1
            _retire_inquiry_rows(
                db, line_id, "The line was closed by a planning change batch."
            )
            continue
        if row.suggested == "reduce":
            new_qty = _dec((row.to_json or {}).get("qty"))
            confirm_lines.append(_confirm_payload_reduce(line_id, frozen_entry, new_qty))
            continue
        confirm_lines.append(_confirm_payload(line_id, frozen_entry))  # keep

    revised = False
    revision_no = current_revision
    if confirm_lines:
        body = ConfirmSupplyBody(lines=[_to_confirm_line(p) for p in confirm_lines])
        result = supply.confirm(order, body, actor_user_id=actor)
        revision_no = result["revision_no"]
        revised = True
    elif active_decision is not None and (replanned or retired):
        supply.supersede_for_material_change(
            order,
            "Every covered line moved to Replan or Retire in a planning change batch.",
        )
        revised = True

    demand_rows, inquiry_counts = _oi_demand_rows(db, live)
    if demand_rows:
        ProjectOrderInquiryService(db).derive_for_book_change(
            order, demand_rows, batch_id=str(batch.id), actor_user_id=actor
        )

    for r in live:
        r.applied_state = PLANNING_CHANGE_STATE_APPLIED
        if r.suggested == "release":
            r.result_json = {
                "board_link": r.board_link,
                "released": _released_reserve(r.held_json),
                "back_on_board": True,
            }
        else:
            r.result_json = {"board_link": r.board_link}

    notified = _notify_purchasing(db, order, so_number, batch)

    return {
        "revised": revised,
        "revision_no": revision_no,
        "lines_replanned": replanned,
        "inquiry_counts": inquiry_counts,
        "notified": notified,
    }


def apply(db: Session, batch_id: str, actor: Optional[str]) -> dict:
    """AC-R05: one new revision per affected order, atomic per order. Applying twice is a
    no-op (`already_applied`)."""
    from app.services.project_supply_service import ProjectSupplyService

    batch = _batch_or_404(db, batch_id)
    rows = db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == batch.id).all()

    pso_ids = sorted({str(r.project_sales_order_id) for r in rows})
    orders_map: Dict[str, ProjectSalesOrder] = {}
    if pso_ids:
        for o in db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id.in_(pso_ids)).all():
            orders_map[str(o.id)] = o

    def so_number_of(pso_id: str) -> str:
        order = orders_map.get(pso_id)
        return _so_number(order) if order else pso_id

    if batch.applied_at is not None:
        applied_orders = sorted(
            {
                so_number_of(str(r.project_sales_order_id))
                for r in rows
                if r.applied_state == PLANNING_CHANGE_STATE_APPLIED
            }
        )
        return {"applied_orders": applied_orders, "failed_orders": [], "already_applied": True}

    by_order: Dict[str, List[PlanningChangeRow]] = defaultdict(list)
    for r in rows:
        by_order[str(r.project_sales_order_id)].append(r)

    supply = ProjectSupplyService(db)

    applied_orders: List[str] = []
    failed_orders: List[dict] = []
    orders_revised: List[dict] = []
    inquiry_counts: Dict[str, int] = {}
    lines_replanned = 0
    purchasing_notified = False

    for pso_id, order_rows in by_order.items():
        order = orders_map.get(pso_id)
        so_number = so_number_of(pso_id)
        if order is None:
            reason = "This sales order no longer exists."
            for r in order_rows:
                if r.decision == "accept" and r.applied_state == PLANNING_CHANGE_STATE_PENDING:
                    r.applied_state = PLANNING_CHANGE_STATE_FAILED
                    r.applied_reason = reason
            failed_orders.append({"so_number": so_number, "reason": reason})
            continue

        savepoint = db.begin_nested()
        try:
            outcome = _apply_one_order(db, supply, order, order_rows, actor, batch)
            savepoint.commit()
        except Exception as exc:  # noqa: BLE001 - one order's failure must not sink the rest
            savepoint.rollback()
            reason = _exc_message(exc)
            logger.exception("planning change apply failed for order %s", so_number)
            for r in order_rows:
                if r.decision == "accept" and r.applied_state == PLANNING_CHANGE_STATE_PENDING:
                    r.applied_state = PLANNING_CHANGE_STATE_FAILED
                    r.applied_reason = reason
            failed_orders.append({"so_number": so_number, "reason": reason})
            continue

        applied_orders.append(so_number)
        if outcome["revised"]:
            orders_revised.append({"so_number": so_number, "revision_no": outcome["revision_no"]})
        lines_replanned += outcome["lines_replanned"]
        for verb, count in outcome["inquiry_counts"].items():
            inquiry_counts[verb] = inquiry_counts.get(verb, 0) + count
        purchasing_notified = purchasing_notified or outcome["notified"]

    batch.applied_at = datetime.utcnow()
    batch.applied_by = actor
    batch.result_json = {
        "orders_revised": orders_revised,
        "orders_failed": failed_orders,
        "inquiry_rows_changed": [
            {"verb": verb, "count": count} for verb, count in inquiry_counts.items()
        ],
        "lines_replanned": lines_replanned,
        "purchasing_notified": purchasing_notified,
    }
    db.flush()

    return {
        "applied_orders": applied_orders,
        "failed_orders": failed_orders,
        "already_applied": False,
    }
