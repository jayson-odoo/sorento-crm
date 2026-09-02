"""Saved decisions on the planning board (S4 of `PLAN-scm-fulfilment-feedback-2sep.md`).

One row per board contribution, in `projects.so_supply_decision_drafts`. Three readers and
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
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.project_so import SOSupplyDecisionDraft
from app.models.user import User
from app.services.error_handler import AppException

#: `${sales_order_id}|${line_no}|${item_code}|${bucket_key}` - `_Row.key` in
#: `project_fulfilment_board_service.py`, rebuilt by `standingsFor` on the frontend.
KEY_PARTS = 4

#: (core sales order id, line number, item code). The bucket is NOT part of it: see the
#: model's docstring - it moves with the board's granularity, and the same saved line has
#: to be found at day, week and month.
LineKey = Tuple[str, int, str]


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
        return sales_order_id, int(line_no), item_code, bucket_key
    except ValueError:
        raise _bad_key(key) from None


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


def save_draft(
    db: Session,
    key: str,
    *,
    decision: Dict[str, Any],
    proposed: Optional[Dict[str, Any]],
    actor_user_id: str,
) -> Dict[str, Any]:
    """Upsert the decision saved on one line, and re-stamp who saved it (AC-4.5).

    One row per line, replaced rather than added to: drafts are SHARED (R-F), so a second
    planner saving over the first must leave the board with one answer, named after the
    newer saver.
    """
    sales_order_id, line_no, item_code, bucket_key = parse_contribution_key(key)
    row = _row_for(db, (sales_order_id, line_no, item_code))
    if row is None:
        row = SOSupplyDecisionDraft(
            id=str(uuid.uuid4()),
            sales_order_id=sales_order_id,
            line_no=line_no,
            item_code=item_code,
            bucket_key=bucket_key,
        )
        db.add(row)
    row.bucket_key = bucket_key
    row.decision = decision
    row.proposed_snapshot = proposed
    row.saved_by = actor_user_id
    row.saved_at = datetime.utcnow()
    db.flush()
    return {
        "decision": row.decision,
        "saved_by": _saver_name(db, row.saved_by),
        "saved_at": row.saved_at,
        # Just saved against the suggestion the planner was looking at, so nothing about it
        # can have moved yet. The board recomputes it on every read.
        "stale": False,
    }


def remove_draft(db: Session, key: str) -> None:
    """Undo (AC-4.3). A line nobody saved is a 404: there is nothing to undo."""
    sales_order_id, line_no, item_code, _bucket = parse_contribution_key(key)
    row = _row_for(db, (sales_order_id, line_no, item_code))
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
    """Every saved decision on these CORE sales orders, keyed by line.

    One query for the whole board, like every other per-board read here, with the saver's
    NAME resolved in it - the pill's popover renders a person, never an id.
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
        (
            str(row.sales_order_id),
            int(row.line_no),
            row.item_code,
        ): {
            "decision": row.decision,
            "saved_by": name or "",
            "saved_at": row.saved_at,
            "proposed_snapshot": row.proposed_snapshot,
        }
        for row, name in rows
    }


def delete_drafts_for_lines(
    db: Session, sales_order_id: Optional[str], lines: Sequence[Tuple[int, str]]
) -> int:
    """Drop the drafts a confirmation has just promoted, in ITS transaction.

    `lines` is `(line_no, item_code)` per confirmed line. Matched on the line rather than
    on the order as a whole, because a confirmation may cover a SUBSET of an order's lines
    (13.4) and the ones the planner deliberately left undecided keep what they saved.
    """
    if not sales_order_id or not lines:
        return 0
    deleted = 0
    for line_no, item_code in set(lines):
        if line_no is None or not item_code:
            continue
        row = _row_for(db, (str(sales_order_id), int(line_no), item_code))
        if row is not None:
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


def is_stale(snapshot: Optional[Dict[str, Any]], proposed: Optional[Dict[str, Any]]) -> bool:
    """Has the engine re-suggested this line since it was saved (AC-4.4)?

    Compared on the COMPOSITION and nothing else - each component's kind, quantity and
    location, in order. The reason sentence beside a component is prose the engine rewords
    (it names the pile it drew from, and that pile's numbers move on every goods receipt),
    so comparing it would put "Suggestion changed" on a line whose suggestion is word for
    word the same set of quantities.

    A draft with NO snapshot is never stale: nothing was written down to compare, and a
    warning with no evidence behind it is worse than no warning.
    """
    if snapshot is None:
        return False
    return _signature(snapshot) != _signature(proposed)


def _signature(proposed: Optional[Dict[str, Any]]) -> Optional[List[Tuple[Any, ...]]]:
    if not isinstance(proposed, dict):
        return None
    components = proposed.get("components")
    if not isinstance(components, list):
        return None
    return [
        (
            component.get("kind"),
            component.get("qty"),
            component.get("location"),
        )
        for component in components
        if isinstance(component, dict)
    ]


def _row_for(db: Session, line: LineKey) -> Optional[SOSupplyDecisionDraft]:
    sales_order_id, line_no, item_code = line
    return (
        db.query(SOSupplyDecisionDraft)
        .filter(
            SOSupplyDecisionDraft.sales_order_id == sales_order_id,
            SOSupplyDecisionDraft.line_no == line_no,
            SOSupplyDecisionDraft.item_code == item_code,
        )
        .one_or_none()
    )


def _saver_name(db: Session, user_id: Optional[str]) -> str:
    if not user_id:
        return ""
    return db.query(User.name).filter(User.id == user_id).scalar() or ""
