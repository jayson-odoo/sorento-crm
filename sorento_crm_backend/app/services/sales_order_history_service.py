"""STANDARD-HISTORY wave 2: one sales order's History tab.

Read-only. The planning History (`planning_history_service`: revisions, refused Confirms,
AutoCount updates, handover emails) plus what the order inquiries of the project SO did to its
rows (`order_inquiry_history_service`: Confirm / Unconfirm presses, cancellations), the line
splits and the status changes, all in the wave 1 event shape (`schemas/order_inquiry_history.py`),
newest first. The OIs of one SO are read as one set of rows, so a press that spanned two of
them is ONE event naming every row.

UAC: `documentation/plans/audit/standard-history-10nov-acceptance-criteria.md` AC-SH-W2-1 to W2-5.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.planning_change import PlanningChangeBatch
from app.models.project_so import OrderInquiry, ProjectSalesOrder
from app.services import order_inquiry_history_service as oi_history
from app.services import planning_history_service as planning
from app.services.history_common import iso
from app.services.project_service import resolve_user_names

_CAUSE_LABEL = {
    "so_line_removed": "Line removed from the SO",
    "qty_reduced": "Quantity reduced",
    "undecided_change": "Cancelled, change not decided",
}


def history_for_project_so(db: Session, pso_id: str) -> List[dict]:
    return _history(db, [str(pso_id)])


def history_for_so(db: Session, so_id: str) -> List[dict]:
    """Every project SO whose core order is `so_id` (none: an empty history)."""
    ids = [str(i) for (i,) in db.query(ProjectSalesOrder.id).filter(ProjectSalesOrder.so_id == so_id).all()]
    return _history(db, ids) if ids else []


def _lines_word(count: int) -> str:
    return f"{count} line" if count == 1 else f"{count} lines"


def _num(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return str(int(number)) if number == number.to_integral_value() else format(number.normalize(), "f")


def _label(value: Optional[str]) -> str:
    return (value or "").replace("_", " ").capitalize()


def _entry(index: int, event_id: str, so_line_no, item_code, qty, change: str) -> dict:
    # No OI row stands behind these lines, so the key is the event's own, never a UUID.
    return {
        "row_id": f"{event_id}:{index}",
        "so_line_no": so_line_no,
        "item_code": item_code,
        "qty": qty,
        "change": change.replace(" -> ", " → "),
    }


def _history(db: Session, pso_ids: Sequence[str]) -> List[dict]:
    ids = list(pso_ids)
    events: List[dict] = []
    events += _planning(db, ids)
    events += _presses(db, ids)
    events += _splits(db, ids)
    events += _status(db, ids)
    names = resolve_user_names(db, {e["_actor_id"] for e in events if e.get("_actor_id")})
    for event in events:
        actor_id = event.pop("_actor_id", None)
        if event.get("actor") is None:
            event["actor"] = names.get(actor_id)
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return events


def _event(event_id, kind, at, actor_id, title, lines, actor=None) -> dict:
    return {
        "id": event_id, "kind": kind, "at": iso(at) if hasattr(at, "isoformat") else at,
        "actor": actor, "_actor_id": actor_id, "title": title, "lines": list(lines),
    }


def _planning(db: Session, ids: List[str]) -> List[dict]:
    out: List[dict] = []
    batch_ids = set()
    for source in planning.history(db, ids):
        kind = source["kind"]
        event_id = f"plan-{source['id']}"
        if kind == "revision_confirmed":
            lines = [_revision_line(i, event_id, l) for i, l in enumerate(source["lines"])]
            title = f"Plan confirmed, revision {source['revision_no']}"
            if source.get("reissued_unchanged"):
                title += ", no change"
        elif kind == "confirm_refused":
            lines = [
                _entry(i, event_id, l.get("so_line_no"), l.get("item_code"), None,
                       ": ".join(p for p in (l.get("reason"), l.get("change")) if p) or "Refused")
                for i, l in enumerate(source["lines"])
            ]
            title = f"Confirm refused: {source['reason']}" if source.get("reason") else "Confirm refused"
        elif kind == "autocount_update":
            lines = [
                _entry(i, event_id, l.get("so_line_no"), l.get("item_code"), None, l.get("change") or "Changed")
                for i, l in enumerate(source["lines"])
            ]
            count = len(lines)
            title = f"AutoCount update: {_lines_word(count)} changed"
            batch_ids.add(source["id"].split(":")[0])
        elif kind == "email_sent":
            lines = [
                _entry(i, event_id, None, l.get("item_code"), None, l.get("remark") or "")
                for i, l in enumerate(source["lines"])
            ]
            title = "Handover email sent"
        else:
            continue  # `oi_cancelled`: the OI read gives those
        event = _event(event_id, kind, source["at"], None, title, lines, actor=source.get("actor"))
        event["_batch_id"] = source["id"].split(":")[0] if kind == "autocount_update" else None
        out.append(event)
    # An AutoCount update is the doing of whoever applied it, else of whoever uploaded it.
    if batch_ids:
        applied = {
            str(b.id): b.applied_by
            for b in db.query(PlanningChangeBatch).filter(PlanningChangeBatch.id.in_(list(batch_ids))).all()
            if b.applied_by
        }
        names = resolve_user_names(db, set(applied.values()))
        for event in out:
            who = names.get(applied.get(event.pop("_batch_id", None)))
            if who:
                event["actor"] = who
    for event in out:
        event.pop("_batch_id", None)
    return out


def _revision_line(index: int, event_id: str, line: dict) -> dict:
    action = line.get("action")
    if action == "reduced":
        change = f"Qty {line.get('previous_qty')} -> {line.get('qty')}"
    elif action == "cancelled":
        change = _CAUSE_LABEL.get(line.get("cause"), line.get("change") or "Cancelled")
    elif action == "order_back":
        change = "Order back"
    else:
        change = "Ordered"
    return _entry(index, event_id, line.get("so_line_no"), line.get("item_code"), line.get("qty"), change)


def _presses(db: Session, ids: List[str]) -> List[dict]:
    inquiry_ids = [
        str(i) for (i,) in db.query(OrderInquiry.id).filter(OrderInquiry.project_sales_order_id.in_(ids)).all()
    ]
    if not inquiry_ids:
        return []
    rows = oi_history._Rows(db, inquiry_ids)
    return oi_history._presses(db, rows) if rows.ids else []


def _splits(db: Session, ids: List[str]) -> List[dict]:
    out = []
    for audit in (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "project_so_line_splits",
            AuditLog.root_entity_type == "project_sales_orders",
            AuditLog.root_entity_id.in_(ids),
        )
        .all()
    ):
        new = audit.new_values or {}
        line_no = new.get("line_no")
        parts = [
            _num(s.get("qty")) + (" cancelled" if s.get("is_cancel") else "")
            for s in new.get("splits") or []
            if isinstance(s, dict)
        ]
        base = _num(new.get("base_qty")) if new.get("base_qty") is not None else None
        if parts:
            change = f"{base} → {' + '.join(parts)}" if base is not None else " + ".join(parts)
            title = f"Split line {line_no}: {change}"
        else:
            change = "Split removed"
            title = f"Split removed on line {line_no}"
        event_id = f"audit-{audit.id}"
        out.append(
            _event(event_id, "line_split", audit.changed_at, audit.user_id, title,
                   [_entry(0, event_id, line_no, None, None, change)])
        )
    return out


def _status(db: Session, ids: List[str]) -> List[dict]:
    out = []
    for audit in (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "project_sales_orders",
            AuditLog.action == "UPDATE",
            AuditLog.entity_id.in_(ids),
        )
        .all()
    ):
        new = audit.new_values or {}
        if "status" not in new:
            continue
        old = (audit.old_values or {}).get("status")
        title = f"Status: {_label(old)} → {_label(new['status'])}" if old else f"Status: {_label(new['status'])}"
        out.append(_event(f"audit-{audit.id}", "status_changed", audit.changed_at, audit.user_id, title, []))
    return out
