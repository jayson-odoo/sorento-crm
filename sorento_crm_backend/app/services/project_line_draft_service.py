"""Saved decisions on the planning board (S4 of `PLAN-scm-fulfilment-feedback-2sep.md`).

One row per CORE SALES ORDER LINE, in `projects.so_supply_decision_drafts` - addressed from
outside by the board's contribution key, and identified inside by the line that key resolves
to (C2, code review round 4: none of the key's own four parts survives a re-upload that
renumbers the order, a partly-mirrored order, or a change of granularity). Three readers and
they are deliberately the only three:

  * the two routes, `PUT` / `DELETE .../fulfilment-planning/lines/{key}/draft`;
  * `FulfilmentBoardService.build`, which stamps what is saved back onto the board;
  * `ProjectSupplyService._write_decision`, which deletes the drafts a confirmation
    promotes, inside the confirmation's own transaction.

The draft's decision is OPAQUE here. The confirmation is posted from the board's own body
(`confirmLinesFor` composes every line it sends, whether from the saved decision or from the
engine's suggestion), so nothing on the server reads inside this JSON - it is stored, handed
back, and deleted when the line it belongs to is confirmed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import (
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecisionDraft,
)
from app.models.user import User
from app.services.error_handler import AppException
from app.services.project_supply_service import _open_of
from app.services.scm.demand import is_open_demand
from app.services.scm.front_planning_engine import qty_text

#: `${sales_order_id}|${line_no}|${item_code}|${bucket_key}` - `_Row.key` in
#: `project_fulfilment_board_service.py`, rebuilt by `standingsFor` on the frontend.
KEY_PARTS = 4

#: Column lengths the model actually carries (`item_code` `String(100)`, `bucket_key`
#: `String(32)`): a key naming something longer than the column can hold is refused before
#: it ever reaches an INSERT, rather than surfacing as a raw truncation/DB error (S3).
ITEM_CODE_MAX = 100
BUCKET_KEY_MAX = 32

#: The CORE sales order line a draft belongs to (C2, code review round 4). None of the
#: contribution key's own four parts is durable - `line_no` is positional whenever the
#: order's lines are not all mirrored, and `bucket_key` moves with the board's granularity
#: - so the row the board, the mirror and the confirmation all agree on is the identity.
LineKey = str


def parse_contribution_key(key: str) -> Tuple[str, int, str, str]:
    """The four parts of a board contribution key, or a 422.

    A key the server cannot read is refused rather than stored: a row saved under a key no
    board will ever rebuild is invisible for ever, which reads to the planner as a save
    that silently did nothing.
    """
    parts = (key or "").split("|")
    if len(parts) != KEY_PARTS or not all(part.strip() for part in parts):
        raise _bad_key(key)
    sales_order_id, line_no, item_code, bucket_key = (part.strip() for part in parts)
    try:
        uuid.UUID(sales_order_id)
    except (ValueError, AttributeError, TypeError):
        raise _bad_key(key) from None
    try:
        line_no_int = int(line_no)
    except ValueError:
        raise _bad_key(key) from None
    if len(item_code) > ITEM_CODE_MAX or len(bucket_key) > BUCKET_KEY_MAX:
        raise _bad_key(key)
    return sales_order_id, line_no_int, item_code, bucket_key


def _bad_key(key: str) -> AppException:
    return AppException(
        status_code=422,
        message=(
            "That is not a planning board line. A line is addressed by its own "
            "contribution key, and this one could not be read: "
            f"'{key}'."
        ),
        code="board_contribution_key_invalid",
    )


def _bad_line(key: str) -> AppException:
    """S3, captain ruling: a key naming a line that does not exist is a 422, not a row.

    Covers every way a syntactically-valid key can still name nothing: an order outside the
    caller's company scope, an order with no such line, or a UUID that names something other
    than a sales order at all. One message either way - the planner did not ask which of
    those it was, only that the save did not happen.
    """
    return AppException(
        status_code=422,
        message=(
            "That sales order line does not exist, or this company cannot see it. "
            f"Nothing was saved for '{key}'."
        ),
        code="board_contribution_line_not_found",
    )


def _resolve_core_line(db: Session, sales_order_id: str, line_no: int, item_code: str) -> SalesOrderLine:
    """The core line a contribution key names, or a 422 (S3).

    `SalesOrder` and `SalesOrderLine` are `CompanyScopedMixin`, so the queries below are
    already narrowed to the caller's own company by the session's `do_orm_execute` scope
    filter - an order that belongs to another company reads back as "no such order", the
    same as one that never existed.

    Mirrors `FulfilmentBoardService._line_numbers`: a line number per core line, because the
    core table has none. Derived per order by (required date nulls last, item code, line
    id), the same deterministic rule adoption uses to number the mirror - so a key the board
    handed out and a key resolved here name the same line. Where a mirror line exists for
    EVERY line of the order and numbers them distinctly, its numbers win.

    The SET of lines numbered is the board's own `_demand_rows` set - `SalesOrder.status ==
    "open"`, `SalesOrder.demand_class == "project"`, `is_open_demand()` on the line - never
    every line the order has ever carried. A save against SO391698 line 10 read back
    "line not found" without this: the order carries lines this board never counted (closed,
    non-project, or already covered), so numbering ALL of them landed line 10 on a different
    row than the one the board's own ordinal gave the same product its date.
    """
    order = (
        db.query(SalesOrder.id)
        .filter(
            SalesOrder.id == sales_order_id,
            SalesOrder.status == "open",
            SalesOrder.demand_class == "project",
        )
        .one_or_none()
    )
    if order is None:
        raise _bad_line(f"{sales_order_id}|{line_no}|{item_code}")

    lines = (
        db.query(SalesOrderLine, Product.product_code)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .filter(SalesOrderLine.sales_order_id == sales_order_id, is_open_demand())
        .all()
    )
    if not lines:
        raise _bad_line(f"{sales_order_id}|{line_no}|{item_code}")

    line_ids = [str(line.id) for line, _code in lines]
    # S3 (fix round 5): scoped to the record that HOLDS the core order
    # (`ProjectSalesOrder.so_id.isnot(None)`), the SAME scope `FulfilmentBoardService.
    # _mirror_addressing` numbers the board's own contribution keys against. Unscoped, a
    # core line an AUTHORED PSO also happens to reference (a different subject entirely -
    # see `_mirror_addressing`'s own docstring) could win this dict and number the line
    # differently than the key the board just handed out.
    mirrored: Dict[str, int] = dict(
        db.query(
            ProjectSalesOrderLine.core_sales_order_line_id,
            ProjectSalesOrderLine.line_no,
        )
        .join(
            ProjectSalesOrder,
            ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
        )
        .filter(
            ProjectSalesOrderLine.core_sales_order_line_id.in_(line_ids),
            ProjectSalesOrder.so_id.isnot(None),
        )
        .all()
    )
    ordered = sorted(
        lines,
        key=lambda pair: (
            pair[0].required_date is None,
            pair[0].required_date or date.min,
            pair[1] or "",
            str(pair[0].id),
        ),
    )
    derived: Dict[str, int] = {
        str(line.id): index for index, (line, _code) in enumerate(ordered, start=1)
    }
    numbers = [mirrored.get(line.id) for line, _code in lines]
    if all(number is not None for number in numbers) and len(set(numbers)) == len(numbers):
        derived = {str(line.id): int(mirrored[line.id]) for line, _code in lines}

    for line, product_code in lines:
        if derived.get(str(line.id)) == line_no and product_code == item_code:
            return line
    raise _bad_line(f"{sales_order_id}|{line_no}|{item_code}")


def _line_snapshot(line: SalesOrderLine) -> Dict[str, Any]:
    """The LINE's own facts at save time (S1, code review round 3, captain ruling).

    `open_qty` and `required_date` - never the proposal: the proposal depends on which
    orders share the board, its granularity and its window, so a snapshot of it flipped
    stale falsely the moment a planner opened a different view of the same line.
    """
    return {
        "open_qty": qty_text(_open_of(line)),
        "required_date": line.required_date.isoformat() if line.required_date else None,
    }


def save_draft(
    db: Session,
    key: str,
    *,
    decision: Dict[str, Any],
    actor_user_id: str,
) -> Dict[str, Any]:
    """Upsert the decision saved on one line, and re-stamp who saved it (AC-4.5).

    One row per line, replaced rather than added to: drafts are SHARED (R-F), so a second
    planner saving over the first must leave the board with one answer, named after the
    newer saver.

    S3 (captain ruling): refused with a 422 unless the key names a real line under the
    caller's own company - `_resolve_core_line` is what makes that true, and its own return
    doubles as the LINE this save's `line_snapshot` is taken off (S1).
    """
    sales_order_id, line_no, item_code, bucket_key = parse_contribution_key(key)
    core_line = _resolve_core_line(db, sales_order_id, line_no, item_code)
    row = _row_for(db, str(core_line.id), company_id=core_line.company_id)
    if row is None:
        row = SOSupplyDecisionDraft(
            id=str(uuid.uuid4()),
            core_line_id=str(core_line.id),
            sales_order_id=sales_order_id,
        )
        db.add(row)
    # Re-stamped on every save, because all three move: the board renumbers a line when an
    # earlier one's date changes, an item code follows the line's product, and the bucket
    # follows the granularity the save was made under. They are what this draft was CALLED,
    # never what it is.
    row.line_no = line_no
    row.item_code = item_code
    row.bucket_key = bucket_key
    row.decision = decision
    row.line_snapshot = _line_snapshot(core_line)
    row.saved_by = actor_user_id
    row.saved_at = datetime.utcnow()
    db.flush()
    return {
        "decision": row.decision,
        "saved_by": _saver_name(db, row.saved_by),
        "saved_at": row.saved_at,
        # Just saved against the line's own facts as they stand right now, so nothing about
        # it can have moved yet. The board recomputes it on every read.
        "stale": False,
    }


def remove_draft(db: Session, key: str) -> None:
    """Undo (AC-4.3). A line nobody saved is a 404: there is nothing to undo.

    Resolved through the CORE line, the same way the save is (C2), so an Undo made after
    the board renumbered the line still removes the draft that line actually carries. A key
    naming no line at all is that same 404 rather than the save's 422: this route's whole
    contract is "there is nothing saved here", which is true either way, and the client
    already treats it as "already gone".
    """
    sales_order_id, line_no, item_code, _bucket = parse_contribution_key(key)
    try:
        core_line = _resolve_core_line(db, sales_order_id, line_no, item_code)
    except AppException:
        core_line = None
    row = None if core_line is None else _row_for(db, str(core_line.id))
    if row is None:
        raise AppException(
            status_code=404,
            message="There is no saved decision on that line.",
            code="board_line_draft_not_found",
        )
    db.delete(row)
    db.flush()


def drafts_for_orders(
    db: Session, sales_order_ids: Iterable[str]
) -> Dict[LineKey, Dict[str, Any]]:
    """Every saved decision on these CORE sales orders, keyed by CORE LINE id.

    One query for the whole board, like every other per-board read here, with the saver's
    NAME resolved in it - the pill's popover renders a person, never an id.

    Read by sales order (one indexed predicate for the whole board) and keyed by the line
    (C2): the board stamps a draft onto the row whose `line_id` matches, never onto the row
    that happens to carry the number the save was made under.
    """
    ids = [str(order_id) for order_id in sales_order_ids if order_id]
    if not ids:
        return {}
    rows = (
        db.query(SOSupplyDecisionDraft, User.name)
        .outerjoin(User, User.id == SOSupplyDecisionDraft.saved_by)
        .filter(SOSupplyDecisionDraft.sales_order_id.in_(ids))
        .all()
    )
    return {
        str(row.core_line_id): {
            "decision": row.decision,
            "saved_by": name or "",
            "saved_at": row.saved_at,
            "line_snapshot": row.line_snapshot,
        }
        for row, name in rows
    }


def delete_drafts_for_lines(
    db: Session,
    core_line_ids: Iterable[Optional[str]],
    *,
    company_id: Optional[str] = None,
) -> int:
    """Drop the drafts a confirmation has just promoted, in ITS transaction.

    Addressed by the CORE sales order line of each confirmed line (C2), which the mirror
    carries as `core_sales_order_line_id`. It used to be the mirror's own `(line_no,
    item_code)`, and on an order the board numbers POSITIONALLY - any order whose lines are
    not all mirrored - the two numberings disagree, so nothing matched and the draft
    survived its own confirmation.

    Per line rather than per order, because a confirmation may cover a SUBSET of an order's
    lines (13.4) and the ones the planner deliberately left undecided keep what they saved.
    """
    ids = {str(line_id) for line_id in core_line_ids if line_id}
    if not ids:
        return 0
    deleted = 0
    for core_line_id in ids:
        row = _row_for(db, core_line_id, company_id=company_id)
        if row is not None:
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


def is_stale(
    snapshot: Optional[Dict[str, Any]],
    open_qty: Decimal,
    required_date: Optional[date],
) -> bool:
    """Has this LINE's own facts moved since it was saved (AC-4.4, S1 captain ruling)?

    Judged on the line's own outstanding quantity and required date - NEVER on the
    proposal. The proposal depends on which orders share the board, its granularity and its
    window (`_allocate` draws the shared piles in board order), so comparing PROPOSED
    snapshots flipped `stale` falsely the moment a planner opened a different view of the
    exact same line, and silently dropped it from Confirm. A contribution with no proposal
    at all is never stale on that account, because this predicate never looks at one.

    A draft with NO snapshot is never stale: nothing was written down to compare, and a
    warning with no evidence behind it is worse than no warning.
    """
    if snapshot is None or not isinstance(snapshot, dict):
        return False
    current_qty = qty_text(open_qty)
    current_date = required_date.isoformat() if required_date else None
    return snapshot.get("open_qty") != current_qty or snapshot.get("required_date") != current_date


def _row_for(
    db: Session, core_line_id: LineKey, *, company_id: Optional[str] = None
) -> Optional[SOSupplyDecisionDraft]:
    """The one draft row for a CORE sales order line, or `None`.

    `company_id`, when the caller already has it, is an EXPLICIT predicate on top of the
    session's own scope filter (N2, code review round 3): the all-companies principal (no
    `EXTERNAL_API_KEY_ACT_AS_USER_ID`) reads with no company predicate at all, and while the
    line here is already pinned to one company through its own FK, a caller that has already
    resolved it is better placed to say which company than a query left to find out the hard
    way.
    """
    query = db.query(SOSupplyDecisionDraft).filter(
        SOSupplyDecisionDraft.core_line_id == str(core_line_id),
    )
    if company_id:
        query = query.filter(SOSupplyDecisionDraft.company_id == company_id)
    return query.one_or_none()


def _saver_name(db: Session, user_id: Optional[str]) -> str:
    if not user_id:
        return ""
    return db.query(User.name).filter(User.id == user_id).scalar() or ""
