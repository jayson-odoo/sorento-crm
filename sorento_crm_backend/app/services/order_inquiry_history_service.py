"""STANDARD-HISTORY wave 1: one order inquiry's History tab.

Read-only. One newest-first list of what happened to an OI's rows, merged from rows that
already exist; nothing is written. Same event shape as the SO History drawer
(`planning_history_service.py`): each event lists the lines it touched, so a batch press
(the 9-row Unconfirm on OI-2611-0019) is ONE event that names every row.

Sources (scout: `documentation/plans/audit/SCOUT-standard-history-10nov.md`):

- raises: `order_inquiry_raises`, with the rows created around each raise;
- Confirm / Unconfirm presses: the one `audit_logs` row per press
  (`ProjectOrderInquiryService.acknowledge_rows` / `unacknowledge_rows`). A press can span
  several OIs and is filed under its first row only, so it is found through
  `new_values.row_ids` and narrowed to THIS OI's rows - another OI's rows never leave here;
- row cancellations: `OI_ROW_CANCELLED` audit rows;
- links and released links: `order_inquiry_links`, `order_inquiry_released_links`;
- rejections: the row's own `rejected_*` columns;
- reserve events: `order_inquiry_reserve_events`.

UAC: `documentation/plans/audit/standard-history-10nov-acceptance-criteria.md` AC-SH-B1 to B6.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import Text, or_
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OI_RAISE_RECONFIRMED,
    OrderInquiryLink,
    OrderInquiryRaise,
    OrderInquiryReleasedLink,
    OrderInquiryReserveEvent,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.services.project_service import resolve_user_names

#: Both spellings, as `planning_history_service._ROW_AUDIT_TYPES`.
_ROW_AUDIT_TYPES = ("project_order_inquiry_rows", "order_inquiry_rows")
#: Rows created this close to a raise were raised by it (`planning_history_service._WINDOW`).
_RAISE_WINDOW = timedelta(seconds=5)
AUTOMATIC = "Automatic"

_ACK_LABEL = {
    ACK_AWAITING: "To confirm",
    ACK_ACKNOWLEDGED: "Confirmed",
    ACK_CHANGED: "Changed",
    ACK_REJECTED: "Rejected",
}
_CAUSE_LABEL = {
    "so_line_removed": "Line removed from the SO",
    "qty_reduced": "Quantity reduced",
}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _qty(value: Any) -> Any:
    if value is None:
        return None
    number = float(value)
    return int(number) if number == int(number) else number


def _lines_word(count: int) -> str:
    return f"{count} line" if count == 1 else f"{count} lines"


def _second(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(microsecond=0) if value else None


class _Rows:
    """This OI's rows (cancelled ones included: they are history too)."""

    def __init__(self, db: Session, inquiry_id: str):
        self.by_id: Dict[str, OrderInquiryRow] = {
            str(row.id): row
            for row in db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.order_inquiry_id == inquiry_id)
            .all()
        }
        line_ids = {row.so_line_id for row in self.by_id.values() if row.so_line_id}
        self.line_no: Dict[str, Any] = {}
        if line_ids:
            self.line_no = {
                str(line.id): line.line_no
                for line in db.query(ProjectSalesOrderLine)
                .filter(ProjectSalesOrderLine.id.in_(list(line_ids)))
                .all()
            }

    @property
    def ids(self) -> List[str]:
        return list(self.by_id)

    def line(self, row_id: str, change: str, qty: Any = None) -> dict:
        row = self.by_id[row_id]
        return {
            "row_id": row_id,
            "so_line_no": self.line_no.get(str(row.so_line_id)) if row.so_line_id else None,
            "item_code": row.item_code,
            "qty": _qty(row.qty if qty is None else qty),
            "change": change,
        }


def history(db: Session, inquiry_id: str) -> List[dict]:
    rows = _Rows(db, inquiry_id)
    events: List[dict] = []
    events += _raises(db, inquiry_id, rows)
    if rows.ids:
        events += _presses(db, rows)
        events += _links(db, rows)
        events += _released(db, rows)
        events += _rejections(rows)
        events += _reserve(db, rows)
    names = resolve_user_names(db, {e["_actor_id"] for e in events if e.get("_actor_id")})
    for event in events:
        actor_id = event.pop("_actor_id", None)
        if event.get("actor") is None:
            event["actor"] = names.get(actor_id)
        event["lines"].sort(key=lambda l: (l["so_line_no"] is None, l["so_line_no"] or 0, l["item_code"] or ""))
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return events


def _event(event_id: str, kind: str, at, actor_id, title: str, lines, actor=None) -> dict:
    return {
        "id": event_id,
        "kind": kind,
        "at": _iso(at),
        "actor": actor,
        "_actor_id": actor_id,
        "title": title,
        "lines": list(lines),
    }


def _raises(db: Session, inquiry_id: str, rows: _Rows) -> List[dict]:
    out = []
    for raise_ in (
        db.query(OrderInquiryRaise).filter(OrderInquiryRaise.order_inquiry_id == inquiry_id).all()
    ):
        raised = [
            rows.line(row_id, "Raised")
            for row_id, row in rows.by_id.items()
            if row.created_at
            and raise_.raised_at
            and abs(row.created_at - raise_.raised_at) <= _RAISE_WINDOW
        ]
        verb = "Reconfirmed" if raise_.kind == OI_RAISE_RECONFIRMED else "Raised"
        title = f"{verb} {_lines_word(len(raised))}" if raised else verb
        out.append(
            _event(f"raise-{raise_.id}", raise_.kind, raise_.raised_at, raise_.raised_by, title, raised)
        )
    return out


def _presses(db: Session, rows: _Rows) -> List[dict]:
    """Confirm / Unconfirm presses and row cancellations, from `audit_logs`."""
    ids = rows.ids
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type.in_(_ROW_AUDIT_TYPES))
        .filter(
            or_(
                AuditLog.entity_id.in_(ids),
                AuditLog.new_values["row_ids"].has_any(array(ids, type_=Text)),
            )
        )
        .all()
    )
    out = []
    for audit in audits:
        new = audit.new_values or {}
        if audit.event == "OI_ROW_CANCELLED":
            row_id = str(audit.entity_id)
            if row_id not in rows.by_id:
                continue
            cause = new.get("cause")
            change = _CAUSE_LABEL.get(cause, "Cancelled") if cause else "Cancelled"
            out.append(
                _event(
                    f"audit-{audit.id}", "cancelled", audit.changed_at, audit.user_id,
                    "Cancelled 1 line", [rows.line(row_id, change, new.get("qty"))],
                )
            )
            continue
        new_state = new.get("ack_state")
        # Only the one-row-per-press writes carry `row_ids` (`acknowledge_rows` /
        # `unacknowledge_rows`); anything else on these entity types is not a press.
        if "row_ids" not in new:
            continue
        if new_state == ACK_ACKNOWLEDGED:
            kind, verb = "confirmed", "Confirmed"
        elif new_state == ACK_AWAITING:
            kind, verb = "unconfirmed", "Unconfirmed"
        else:
            continue
        prior = {
            str(entry.get("id")): entry.get("ack_state")
            for entry in ((audit.old_values or {}).get("rows") or [])
            if isinstance(entry, dict)
        }
        touched = [str(row_id) for row_id in new.get("row_ids") or []]
        mine = [row_id for row_id in touched if row_id in rows.by_id]
        if not mine:
            continue
        after = _ACK_LABEL.get(new_state, new_state)
        lines = [
            rows.line(row_id, f"{_ACK_LABEL.get(prior.get(row_id), 'To confirm')} -> {after}")
            for row_id in mine
        ]
        out.append(
            _event(
                f"audit-{audit.id}", kind, audit.changed_at, audit.user_id,
                f"{verb} {_lines_word(len(lines))}", lines,
            )
        )
    return out


def _grouped(items: Iterable[Tuple[tuple, Any]]) -> Dict[tuple, list]:
    groups: Dict[tuple, list] = defaultdict(list)
    for key, item in items:
        groups[key].append(item)
    return groups


def _links(db: Session, rows: _Rows) -> List[dict]:
    """Links made in one go (same document, same person or automatic, same second) are one
    event."""
    links = db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id.in_(rows.ids)).all()
    groups = _grouped(
        ((link.document, link.linked_by, bool(link.auto), _second(link.linked_at)), link)
        for link in links
    )
    out = []
    for (document, linked_by, auto, _), members in groups.items():
        first = min(members, key=lambda l: (l.linked_at, str(l.id)))
        target = document or "Stock"
        lines = [
            rows.line(str(l.row_id), f"Linked {_qty(l.qty)} to {target}", l.qty) for l in members
        ]
        out.append(
            _event(
                f"link-{first.id}", "linked", first.linked_at, None if auto else linked_by,
                f"{target} linked to {_lines_word(len(lines))}", lines,
                actor=AUTOMATIC if auto or not linked_by else None,
            )
        )
    return out


def _released(db: Session, rows: _Rows) -> List[dict]:
    released = (
        db.query(OrderInquiryReleasedLink)
        .filter(OrderInquiryReleasedLink.row_id.in_(rows.ids))
        .all()
    )
    groups = _grouped(
        ((link.document, link.released_by, _second(link.released_at)), link) for link in released
    )
    out = []
    for (document, released_by, _), members in groups.items():
        first = min(members, key=lambda l: (l.released_at, str(l.id)))
        target = document or "Stock"
        lines = [
            rows.line(str(l.row_id), f"Released {_qty(l.qty)} from {target}", l.qty)
            for l in members
        ]
        out.append(
            _event(
                f"released-{first.id}", "unlinked", first.released_at, released_by,
                f"{target} released from {_lines_word(len(lines))}", lines,
            )
        )
    return out


def _rejections(rows: _Rows) -> List[dict]:
    groups = _grouped(
        ((row.rejected_by, _second(row.rejected_at)), (row_id, row))
        for row_id, row in rows.by_id.items()
        if row.rejected_at
    )
    out = []
    for (rejected_by, _), members in groups.items():
        first_id, first = min(members, key=lambda m: (m[1].rejected_at, m[0]))
        lines = [
            rows.line(
                row_id,
                f"Rejected: {row.rejected_reason}" if row.rejected_reason else "Rejected",
            )
            for row_id, row in members
        ]
        out.append(
            _event(
                f"rejected-{first_id}", "rejected", first.rejected_at, rejected_by,
                f"Rejected {_lines_word(len(lines))}", lines,
            )
        )
    return out


def _reserve(db: Session, rows: _Rows) -> List[dict]:
    pairs = (
        db.query(OrderInquiryReserveEvent, OrderInquiryReserveRequestRow.row_id)
        .join(
            OrderInquiryReserveRequestRow,
            OrderInquiryReserveRequestRow.id == OrderInquiryReserveEvent.reserve_request_row_id,
        )
        .filter(OrderInquiryReserveRequestRow.row_id.in_(rows.ids))
        .all()
    )
    groups = _grouped(
        ((event.kind, event.actor_id, _second(event.created_at)), (event, str(row_id)))
        for event, row_id in pairs
    )
    out = []
    for (kind, actor_id, _), members in groups.items():
        first, _row = min(members, key=lambda m: (m[0].created_at, str(m[0].id)))
        verb = (kind or "").capitalize() or "Reserve"
        lines = [
            rows.line(row_id, f"{verb} {_qty(event.qty)}", event.qty) for event, row_id in members
        ]
        out.append(
            _event(
                f"reserve-{first.id}", kind, first.created_at, actor_id,
                f"{verb} {_lines_word(len(lines))}", lines,
            )
        )
    return out
