"""PO-LINK-HISTORY: when and how a purchase-order line got its S/O link.

The S/O a PO line is raised for is `purchase_order_lines.from_so_line_ref`, written only by
the AutoCount PO ingest, and the line table is audit-skipped (`__audit_skip__`: the sync
writes thousands of line rows a day). So the ingest writes ONE explicit audit EVENT per link
change instead (`record_changes`), and nothing on a re-push that changes nothing. The PO
detail reads the latest one per line back (`latest_by_line`) for the S/O cell's popover,
and the PO History tab reads them through the audit trail (they roll up to the PO header).

AutoCount never says WHO moved a link, so the row carries the ingest's own actor (the
integration) and nothing more. Plan: documentation/plans/procurement/PLAN-po-link-history-04nov.md.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.product import Product
from app.services import audit_service
from app.services.scm import order_link_service

#: A link change the AutoCount PO sync wrote (old and new ref, either may be None).
EVENT_CHANGE = "scm.po_line.book_so_change"
#: The backfill's "first seen" row for a line linked before history began. Its time is an
#: upper bound (the line's earliest AutoCount claim, else its created_at), not the moment.
EVENT_SEEN = "scm.po_line.book_so_seen"

_ENTITY = "purchase_order_lines"
_ROOT = "purchase_orders"


def _label(ref: Optional[str], number: Optional[str]) -> str:
    if not ref:
        return "none"
    # Never the ref itself: it is a machine key.
    return number or "an S/O not held here"


def record_changes(
    db: Session,
    changes: Sequence[tuple[Any, Optional[str], Optional[str]]],
    *,
    purchase_order_id: str,
) -> None:
    """One EVENT row per `(line, old_ref, new_ref)` whose two refs differ.

    Called by the ingest inside the record's savepoint, so a record that fails leaves no
    event behind. ONE sales-order lookup for the whole batch, never one per line.
    """
    moved = [(line, old, new) for line, old, new in changes if (old or None) != (new or None)]
    if not moved:
        return
    numbers = order_link_service.book_so_numbers_by_ref(
        db, [ref for _, old, new in moved for ref in (old, new) if ref]
    )
    # By id, not `line.product`: a line this sync just created has no product loaded.
    codes = dict(
        db.query(Product.id, Product.product_code)
        .filter(Product.id.in_({str(line.product_id) for line, _, _ in moved if line.product_id}))
        .all()
    )
    for line, old, new in moved:
        old_no = numbers.get(old) if old else None
        new_no = numbers.get(new) if new else None
        item = codes.get(str(line.product_id)) or "Line"
        audit_service.log_audit(
            db,
            _ENTITY,
            str(line.id),
            "EVENT",
            event=EVENT_CHANGE,
            old_values={"from_so_line_ref": old or None, "so_number": old_no},
            new_values={"from_so_line_ref": new or None, "so_number": new_no},
            description=f"{item}: S/O {_label(old, old_no)} → {_label(new, new_no)}",
            company_id=str(line.company_id) if line.company_id else None,
            root_entity_type=_ROOT,
            root_entity_id=str(purchase_order_id),
            skip_flush=True,
        )


def latest_by_line(db: Session, line_ids: Iterable[str]) -> dict[str, dict]:
    """Line id -> its latest S/O link event, as the PO detail serves it (`book_so_link`).

    Two reads for the whole order: the latest event per line, and one lookup resolving the
    previous refs to sales-order numbers NOW (an order pushed after the change still names).
    """
    ids = [str(i) for i in line_ids]
    if not ids:
        return {}
    rows = (
        db.query(AuditLog.entity_id, AuditLog.event, AuditLog.changed_at, AuditLog.old_values)
        .filter(
            AuditLog.entity_type == _ENTITY,
            AuditLog.entity_id.in_(ids),
            AuditLog.event.in_((EVENT_CHANGE, EVENT_SEEN)),
        )
        .distinct(AuditLog.entity_id)
        .order_by(AuditLog.entity_id, AuditLog.changed_at.desc(), AuditLog.id.desc())
        .all()
    )
    previous = {
        str(r.entity_id): (r.old_values or {}).get("from_so_line_ref")
        for r in rows
        if r.event == EVENT_CHANGE
    }
    numbers = order_link_service.book_so_numbers_by_ref(db, [p for p in previous.values() if p])
    out: dict[str, dict] = {}
    for r in rows:
        line_id = str(r.entity_id)
        if r.event == EVENT_SEEN:
            # Earlier history was never recorded: whether it had a previous S/O is unknown.
            out[line_id] = {
                "changed_at": r.changed_at.isoformat(),
                "estimated": True,
                "previous_linked": None,
                "previous_so_number": None,
            }
            continue
        prev = previous.get(line_id)
        out[line_id] = {
            "changed_at": r.changed_at.isoformat(),
            "estimated": False,
            "previous_linked": bool(prev),
            "previous_so_number": numbers.get(prev) if prev else None,
        }
    return out


__all__ = ["EVENT_CHANGE", "EVENT_SEEN", "latest_by_line", "record_changes"]
