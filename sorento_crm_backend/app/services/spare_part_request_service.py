"""Spare part request: an Order Inquiry of type `spare_part_request`, approved before purchasing
sees it (SPARE-PART-ORDER-REQUEST).

Plan: documentation/plans/purchasing/PLAN-spare-part-order-request-12nov.md ("Build contract").
UAC: documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md.

One record: the request IS an `OrderInquiry` (no sales order), its lines are `OrderInquiryRow`s
with the verb REPLENISH. Before final approval the header is `draft` / `pending_approval` /
`rejected` and every row is `draft`, which keeps it out of every purchasing read. Approval runs
on the Form SLA stages configured for `spare_part_request` (`FormSLAOrchestrator`); who may
decide is the current stage's team (or an admin), never the requester. Final approval raises
the inquiry and tells purchasing once, through the order inquiry notification queue.

Every move is written to the OI's own History (`log_audit` on `project_order_inquiries`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import and_, false, or_, true
from sqlalchemy.orm import Session

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    INQUIRY_DRAFT,
    INQUIRY_PENDING_APPROVAL,
    INQUIRY_PRE_APPROVAL_STATES,
    INQUIRY_RAISED,
    INQUIRY_REJECTED,
    INQUIRY_TYPE_SPARE_PART,
    IV_REPLENISH,
    OI_RAISE_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRaise,
    OrderInquiryRow,
)
from app.services.audit_service import log_audit
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

KIND = INQUIRY_TYPE_SPARE_PART
AUDIT_ENTITY = "project_order_inquiries"
CREATE_PERMISSION = "procurement.spare_part_requests.create"
_ADMIN_ROLE_SLUGS = frozenset({"admin", "superadmin"})
_EDITABLE = (INQUIRY_DRAFT, INQUIRY_REJECTED)
_ZERO = Decimal("0")


# ------------------------------------------------------------------ errors


def _forbidden(message: str) -> AppException:
    return AppException(status_code=403, message=message, code="FORBIDDEN")


def _conflict(message: str, code: str = "SPARE_PART_REQUEST_ILLEGAL_MOVE") -> AppException:
    return AppException(status_code=409, message=message, code=code)


def _invalid(field: str, message: str) -> AppException:
    return AppException(
        status_code=422, message=message, code="VALIDATION_ERROR", details={"field": field}
    )


# ------------------------------------------------------------------ parsing


def _decimal(value: Any, field: str) -> Optional[Decimal]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise _invalid(field, f"{field.replace('_', ' ').capitalize()} must be a number.")
    if not number.is_finite():
        raise _invalid(field, f"{field.replace('_', ' ').capitalize()} must be a number.")
    if number < 0:
        raise _invalid(field, f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    return number


def _date(value: Any, field: str) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise _invalid(field, "Enter a valid date.")


def _text(value: Any, limit: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    out = str(value).strip()
    if not out:
        return None
    return out[:limit] if limit else out


def _num(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _plain(value: Optional[Decimal]) -> Any:
    """A number as the History tab reads it (int when whole)."""
    if value is None:
        return None
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


# ------------------------------------------------------------------ who


def is_admin(db: Session, user_id: Optional[str]) -> bool:
    """One read every call, never the 30 s RBAC cache: every list request then costs the
    same queries whatever was cached before it (the header list's bounded-query rule)."""
    from app.models.user import UserRole, UserRoleAssignment

    if not user_id:
        return False
    return (
        db.query(UserRoleAssignment.id)
        .join(UserRole, UserRole.id == UserRoleAssignment.role_id)
        .filter(UserRoleAssignment.user_id == str(user_id), UserRole.slug.in_(_ADMIN_ROLE_SLUGS))
        .first()
        is not None
    )


def is_requester(inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    return bool(user_id) and str(inquiry.requested_by or "") == str(user_id)


def _open_stages(db: Session, inquiry_id: str) -> list:
    from app.services.form_sla_service import FormSLAOrchestrator

    return FormSLAOrchestrator(db).active_trackers_for_source(KIND, str(inquiry_id))


def _on_stage_team(db: Session, tracker, user_id: str, company_id: Optional[str]) -> bool:
    from app.services.user_service import AccessAgentService

    if not tracker.agent_id:
        return False
    tier = AccessAgentService(db).get_user_tier_in_team_set(
        str(tracker.agent_id),
        str(user_id),
        team_set_code=tracker.team_set_code,
        company_id=tracker.company_id or company_id,
    )
    return tier is not None


def can_decide(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    """A2: a member of the CURRENT stage's team, or an admin; never the requester, and only
    while the request is pending approval."""
    if inquiry.inquiry_type != KIND or inquiry.state != INQUIRY_PENDING_APPROVAL:
        return False
    if not user_id or is_requester(inquiry, user_id):
        return False
    if is_admin(db, user_id):
        return True
    return any(
        _on_stage_team(db, tracker, user_id, inquiry.company_id)
        for tracker in _open_stages(db, inquiry.id)
    )


def can_edit(inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    return (
        inquiry.inquiry_type == KIND
        and inquiry.state in _EDITABLE
        and is_requester(inquiry, user_id)
    )


def _taken_on(db: Session, inquiry: OrderInquiry) -> bool:
    """Purchasing has started on it: a row acknowledged (or acknowledged and since changed),
    or any document linked to a row."""
    acknowledged = (
        db.query(OrderInquiryRow.id)
        .filter(
            OrderInquiryRow.order_inquiry_id == inquiry.id,
            or_(
                OrderInquiryRow.ack_state.in_((ACK_ACKNOWLEDGED, ACK_CHANGED)),
                OrderInquiryRow.acknowledged_at.isnot(None),
            ),
        )
        .first()
    )
    if acknowledged is not None:
        return True
    linked = (
        db.query(OrderInquiryLink.id)
        .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
        .filter(OrderInquiryRow.order_inquiry_id == inquiry.id)
        .first()
    )
    return linked is not None


def can_revise(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    return (
        inquiry.inquiry_type == KIND
        and inquiry.state == INQUIRY_RAISED
        and is_requester(inquiry, user_id)
        and not _taken_on(db, inquiry)
    )


def can_write_photos(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    """Row photos: the requester while it is theirs to edit, a decider while it is pending."""
    if inquiry.inquiry_type != KIND:
        return False
    return can_edit(inquiry, user_id) or can_decide(db, inquiry, user_id)


def assert_can_write_row_photos(db: Session, row_id: str, user_id: Optional[str]) -> OrderInquiryRow:
    """The row photo write rule (contract "Visibility and permissions"): the requester while
    the request is theirs to edit, the current approver while it is pending; 403 for anyone
    else, purchasing included. Shared by the upload / delete routes and the deferred delete."""
    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == str(row_id)).first()
    inquiry = (
        db.query(OrderInquiry).filter(OrderInquiry.id == row.order_inquiry_id).first()
        if row is not None
        else None
    )
    if row is None or inquiry is None:
        raise AppException(
            404, "That order inquiry row no longer exists.", code="order_inquiry_row_not_found"
        )
    if not can_write_photos(db, inquiry, user_id):
        raise _forbidden("You cannot change the photos on this line now.")
    return row


def decidable_ids(db: Session, user_id: Optional[str]) -> Set[str]:
    """The pending requests `user_id` may decide on now (their stage team holds the open
    stage), never their own."""
    from app.models.sla import ConversationSLATracking
    from app.services.sla_scope import open_tracker_scope

    if not user_id:
        return set()
    trackers = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == KIND, *open_tracker_scope())
        .all()
    )
    if not trackers:
        return set()
    ids = {str(t.source_entity_id) for t in trackers}
    pending = {
        str(row.id): row
        for row in db.query(OrderInquiry.id, OrderInquiry.requested_by, OrderInquiry.company_id)
        .filter(OrderInquiry.id.in_(ids), OrderInquiry.state == INQUIRY_PENDING_APPROVAL)
        .all()
    }
    member: Dict[tuple, bool] = {}
    out: Set[str] = set()
    for tracker in trackers:
        inquiry_id = str(tracker.source_entity_id)
        row = pending.get(inquiry_id)
        if row is None or str(row.requested_by or "") == str(user_id):
            continue
        key = (str(tracker.agent_id), tracker.team_set_code, tracker.company_id or row.company_id)
        if key not in member:
            member[key] = _on_stage_team(db, tracker, user_id, row.company_id)
        if member[key]:
            out.add(inquiry_id)
    return out


def visibility_clause(db: Session, user_id: Optional[str], *, has_view: bool):
    """Which headers a list shows this user (P1). An admin sees every one. Anyone else sees
    a pre-approval request only when it is theirs or they can decide on it; a holder of the
    projects view grant sees every other inquiry too, a requester with only the create grant
    sees nothing but their own spare part requests."""
    if is_admin(db, user_id):
        return true()
    related = [OrderInquiry.requested_by == str(user_id)] if user_id else []
    deciding = decidable_ids(db, user_id)
    if deciding:
        related.append(OrderInquiry.id.in_(sorted(deciding)))
    mine = or_(*related) if related else false()
    if has_view:
        return or_(OrderInquiry.state.notin_(INQUIRY_PRE_APPROVAL_STATES), mine)
    return and_(OrderInquiry.inquiry_type == KIND, mine)


def can_view(db: Session, inquiry: OrderInquiry, user_id: Optional[str], *, has_view: bool) -> bool:
    if is_admin(db, user_id) or is_requester(inquiry, user_id):
        return True
    if inquiry.inquiry_type == KIND and can_decide(db, inquiry, user_id):
        return True
    return has_view and inquiry.state not in INQUIRY_PRE_APPROVAL_STATES


# ------------------------------------------------------------------ reads


def get(db: Session, inquiry_id: str) -> OrderInquiry:
    inquiry = (
        db.query(OrderInquiry)
        .filter(OrderInquiry.id == str(inquiry_id), OrderInquiry.inquiry_type == KIND)
        .first()
    )
    if inquiry is None:
        raise AppException(404, "This spare part request no longer exists.", code="spr_not_found")
    return inquiry


def _rows(db: Session, inquiry: OrderInquiry) -> List[OrderInquiryRow]:
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.order_inquiry_id == inquiry.id)
        .order_by(OrderInquiryRow.created_at, OrderInquiryRow.id)
        .all()
    )


def _line_total(row: OrderInquiryRow) -> Decimal:
    return Decimal(row.qty or 0) * Decimal(row.unit_price or 0)


def detail(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> Dict[str, Any]:
    from app.models.product import Product
    from app.services.project_service import resolve_user_names

    rows = _rows(db, inquiry)
    names = resolve_user_names(
        db, {u for u in (inquiry.requested_by, inquiry.approved_by) if u}
    )
    product_ids = {str(r.product_id) for r in rows if r.product_id}
    products = {
        str(p.id): p
        for p in (
            db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
        )
    }
    total = sum((_line_total(r) for r in rows if r.state != INQUIRY_CANCELLED), _ZERO)
    lines = []
    for row in rows:
        product = products.get(str(row.product_id)) if row.product_id else None
        lines.append(
            {
                "id": str(row.id),
                "product_id": str(row.product_id) if row.product_id else None,
                "product_name": product.product_name if product else None,
                "item_code": row.item_code,
                "description": row.description,
                "stock_location": row.stock_location,
                "qty": _num(row.qty) or "0",
                "unit_price": _num(row.unit_price),
                "total": _num(_line_total(row)) or "0",
                "requested_qty": _num(row.requested_qty),
                "requested_unit_price": _num(row.requested_unit_price),
                "state": row.state,
                "ack_state": row.ack_state,
            }
        )
    return {
        "id": str(inquiry.id),
        "inquiry_no": inquiry.inquiry_no,
        "inquiry_type": inquiry.inquiry_type,
        "state": inquiry.state,
        "currency": inquiry.currency,
        "needed_by": inquiry.needed_by,
        "default_location": inquiry.default_location,
        "reason": inquiry.reason,
        "requested_by": inquiry.requested_by,
        "requested_by_name": names.get(str(inquiry.requested_by)) if inquiry.requested_by else None,
        "submitted_at": inquiry.submitted_at,
        "approved_at": inquiry.approved_at,
        "approved_by": inquiry.approved_by,
        "approved_by_name": names.get(str(inquiry.approved_by)) if inquiry.approved_by else None,
        "reject_reason": inquiry.reject_reason,
        "can_decide": can_decide(db, inquiry, user_id),
        "can_edit": can_edit(inquiry, user_id),
        "can_revise": can_revise(db, inquiry, user_id),
        "total": _num(total) or "0",
        "lines": lines,
    }


# ------------------------------------------------------------------ writes


def _company_id(db: Session) -> Optional[str]:
    from app.models.base import get_company_scope
    from app.services.company_scope import resolve_write_company_id

    return resolve_write_company_id(get_company_scope(db))


def _audit(
    db: Session,
    inquiry: OrderInquiry,
    event: str,
    description: str,
    user_id: Optional[str],
    *,
    old: Optional[dict] = None,
    new: Optional[dict] = None,
) -> None:
    log_audit(
        db,
        AUDIT_ENTITY,
        str(inquiry.id),
        "EVENT",
        event=event,
        description=description,
        old_values=old,
        new_values=new,
        user_id=user_id,
        company_id=inquiry.company_id,
    )


def _apply_header(inquiry: OrderInquiry, data: Dict[str, Any]) -> None:
    currency = _text(data.get("currency"))
    if currency is not None and len(currency) != 3:
        raise _invalid("currency", "Choose a currency.")
    inquiry.currency = currency.upper() if currency else None
    inquiry.needed_by = _date(data.get("needed_by"), "needed_by")
    inquiry.default_location = _text(data.get("default_location"), 80)
    inquiry.reason = _text(data.get("reason"))


def _product(db: Session, product_id: Any, index: int):
    from app.models.product import Product

    if not product_id:
        raise _invalid("lines", f"Line {index}: choose a product from the catalogue.")
    product = db.query(Product).filter(Product.id == str(product_id)).first()
    if product is None:
        raise _invalid("lines", f"Line {index}: that product is not in the catalogue.")
    return product


def _replace_lines(db: Session, inquiry: OrderInquiry, lines: Iterable[Dict[str, Any]]) -> None:
    """The form's lines replace the request's: a line naming an existing row id updates that
    row in place (its photos stay with it), every other line is a new row, and a row the form
    no longer lists is removed with its photos."""
    from app.services.entity_attachment_service import EntityAttachmentService
    from app.services.so_line_attachments import OI_ROW

    existing = {str(r.id): r for r in _rows(db, inquiry)}
    kept: Set[str] = set()
    for index, line in enumerate(lines or [], start=1):
        if not isinstance(line, dict):
            raise _invalid("lines", f"Line {index} is not a line.")
        product = _product(db, line.get("product_id"), index)
        qty = _decimal(line.get("qty"), "qty")
        unit_price = _decimal(line.get("unit_price"), "unit_price")
        location = _text(line.get("stock_location"), 80) or inquiry.default_location
        row = existing.get(str(line.get("id") or ""))
        if row is None:
            row = OrderInquiryRow(
                company_id=inquiry.company_id,
                order_inquiry_id=inquiry.id,
                verb=IV_REPLENISH,
                state=INQUIRY_DRAFT,
                ack_state=ACK_AWAITING,
            )
            db.add(row)
        if row.id:
            kept.add(str(row.id))
        row.product_id = str(product.id)
        row.item_code = product.product_code
        row.description = product.product_name or product.description
        row.stock_location = location
        row.qty = qty if qty is not None else _ZERO
        row.unit_price = unit_price
        row.delivery_date = inquiry.needed_by
        row.state = INQUIRY_DRAFT
    for row_id, row in existing.items():
        if row_id not in kept:
            EntityAttachmentService(db).delete_links_for_entity(OI_ROW.entity_type, row_id)
            db.delete(row)
    db.flush()


def create(db: Session, data: Dict[str, Any], actor: str) -> OrderInquiry:
    """R1: a Draft request with an OI number from the same series."""
    inquiry = OrderInquiry(
        company_id=_company_id(db),
        inquiry_type=KIND,
        state=INQUIRY_DRAFT,
        requested_by=str(actor),
        raised_by=str(actor),
    )
    _apply_header(inquiry, data)
    db.add(inquiry)
    db.flush()
    _replace_lines(db, inquiry, data.get("lines") or [])
    _audit(db, inquiry, "SPR_CREATED", "Created as draft", actor)
    db.flush()
    return inquiry


def update(db: Session, inquiry: OrderInquiry, data: Dict[str, Any], actor: str) -> OrderInquiry:
    """R6: the requester edits a draft or rejected request."""
    if not is_requester(inquiry, actor):
        raise _forbidden("Only the requester can edit this request.")
    if inquiry.state not in _EDITABLE:
        raise _conflict("Only a draft or rejected request can be edited.")
    _apply_header(inquiry, data)
    _replace_lines(db, inquiry, data.get("lines") or [])
    _audit(db, inquiry, "SPR_EDITED", "Edited", actor)
    db.flush()
    return inquiry


def _validate_submit(db: Session, inquiry: OrderInquiry) -> List[OrderInquiryRow]:
    if not inquiry.currency:
        raise _invalid("currency", "Choose the currency.")
    rows = [r for r in _rows(db, inquiry) if r.state != INQUIRY_CANCELLED]
    if not rows:
        raise _invalid("lines", "Add at least one line.")
    for index, row in enumerate(rows, start=1):
        if row.qty is None or Decimal(row.qty) <= 0:
            raise _invalid("lines", f"Line {index}: enter a quantity above 0.")
        if row.unit_price is not None and Decimal(row.unit_price) < 0:
            raise _invalid("lines", f"Line {index}: the unit price cannot be negative.")
        if not row.stock_location:
            raise _invalid("lines", f"Line {index}: choose a location.")
    return rows


def _has_stage(db: Session) -> bool:
    from app.models.sla import FormSLAConfig

    return (
        db.query(FormSLAConfig.id)
        .filter(FormSLAConfig.source_entity_type == KIND, FormSLAConfig.is_active.is_(True))
        .first()
        is not None
    )


def _emit(db: Session, inquiry: OrderInquiry, event: str, actor: Optional[str]) -> None:
    from app.services.form_sla_service import FormSLAOrchestrator

    FormSLAOrchestrator(db).emit_event(
        KIND, str(inquiry.id), event, actor_user_id=actor, company_id=inquiry.company_id
    )


def _void_stages(db: Session, inquiry: OrderInquiry, reason: str) -> None:
    from app.services.form_sla_service import FormSLAOrchestrator

    FormSLAOrchestrator(db).void_active_for_source(
        KIND, str(inquiry.id), reason=reason, void_reason="revised"
    )


def submit(db: Session, inquiry: OrderInquiry, actor: str) -> OrderInquiry:
    """R5 / A1: Draft or Rejected -> Pending approval at the first configured stage."""
    if not is_requester(inquiry, actor):
        raise _forbidden("Only the requester can submit this request.")
    if inquiry.state not in _EDITABLE:
        raise _conflict("Only a draft or rejected request can be submitted.")
    rows = _validate_submit(db, inquiry)
    if not _has_stage(db):
        raise AppException(
            status_code=422,
            message=(
                "No approval stage is set up for spare part requests. Ask an admin to add one "
                "in Form SLA configuration."
            ),
            code="spr_no_approval_stage",
        )
    for row in rows:
        row.requested_qty = row.qty
        row.requested_unit_price = row.unit_price
    was_rejected = inquiry.state == INQUIRY_REJECTED
    inquiry.state = INQUIRY_PENDING_APPROVAL
    inquiry.submitted_at = datetime.utcnow()
    inquiry.reject_reason = None
    _audit(
        db, inquiry, "SPR_SUBMITTED", "Resubmitted for approval" if was_rejected else "Submitted for approval",
        actor,
    )
    db.flush()
    # A stage left open by an earlier round never decides this one: approval starts again.
    _void_stages(db, inquiry, "Submitted again")
    _emit(db, inquiry, "submitted", actor)
    return inquiry


def _row_or_404(db: Session, inquiry: OrderInquiry, row_id: Any) -> OrderInquiryRow:
    row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.id == str(row_id), OrderInquiryRow.order_inquiry_id == inquiry.id)
        .first()
    )
    if row is None:
        raise AppException(404, "That line is not on this request.", code="spr_line_not_found")
    return row


def _require_pending(inquiry: OrderInquiry, verb: str) -> None:
    if inquiry.state != INQUIRY_PENDING_APPROVAL:
        raise _conflict(f"Only a request pending approval can be {verb}.")


def edit_line(
    db: Session,
    inquiry: OrderInquiry,
    row_id: Any,
    actor: str,
    *,
    qty: Any = None,
    unit_price: Any = None,
) -> OrderInquiryRow:
    """A3: the approver changes a line's qty (0 allowed) or unit price. The submitted values
    stay on the row; each change is a History entry."""
    _require_pending(inquiry, "changed")
    if not can_decide(db, inquiry, actor):
        raise _forbidden("Only the current approver can change this request.")
    row = _row_or_404(db, inquiry, row_id)
    changes = (
        ("qty", "Qty", _decimal(qty, "qty")),
        ("unit_price", "Unit price", _decimal(unit_price, "unit_price")),
    )
    for field, label, value in changes:
        if value is None:
            continue
        before = getattr(row, field)
        if before is not None and Decimal(before) == value:
            continue
        setattr(row, field, value)
        _audit(
            db, inquiry, "SPR_LINE_CHANGED",
            f"{label} of {row.item_code or 'a line'} changed",
            actor,
            old={"row_id": str(row.id), "item_code": row.item_code, field: _plain(before)},
            new={"row_id": str(row.id), "item_code": row.item_code, field: _plain(value)},
        )
    db.flush()
    return row


def _notify_purchasing(db: Session, inquiry: OrderInquiry, rows: List[OrderInquiryRow]) -> None:
    """P2: the existing "Order inquiry" notice, once, after the approval commits."""
    from app.services.project_order_inquiry_service import (
        ProjectOrderInquiryService,
        queue_purchasing_notification,
    )

    user_ids = ProjectOrderInquiryService(db)._purchasing_user_ids()  # noqa: SLF001
    if not user_ids:
        return
    count = len(rows)
    stamp = inquiry.approved_at.isoformat() if inquiry.approved_at else ""
    queue_purchasing_notification(
        db,
        {
            "user_ids": [str(u) for u in user_ids],
            "title": f"Order inquiry {inquiry.inquiry_no}",
            "body": f"Spare part request: {count} line{'' if count == 1 else 's'} to buy.",
            "data": {
                "order_inquiry_id": str(inquiry.id),
                "inquiry_type": KIND,
                "row_count": count,
                "to_buy": count,
            },
            "inquiry_id": str(inquiry.id),
            "source_entity_type": "order_inquiry",
            "source_entity_id": str(inquiry.id),
            "dedup_key": f"{inquiry.id}:spare_part_raised:{stamp}",
        },
    )


def approve(db: Session, inquiry: OrderInquiry, actor: str, note: Optional[str] = None) -> OrderInquiry:
    """A6: approve the current stage. A further stage keeps it pending; the last one raises
    it: lines with qty go to purchasing, lines at 0 are cancelled."""
    _require_pending(inquiry, "approved")
    if not can_decide(db, inquiry, actor):
        raise _forbidden("Only the current approver can approve this request.")
    rows = [r for r in _rows(db, inquiry) if r.state != INQUIRY_CANCELLED]
    if not any(Decimal(r.qty or 0) > 0 for r in rows):
        raise _invalid("lines", "Every line is at 0. Reject the request instead.")
    note = _text(note)
    _audit(
        db, inquiry, "SPR_APPROVED", "Approved" + (f": {note}" if note else ""), actor,
        new={"note": note} if note else None,
    )
    db.flush()
    _emit(db, inquiry, "approved", actor)
    db.refresh(inquiry)
    if _open_stages(db, inquiry.id):
        return inquiry  # the next stage's team is told by the SLA machinery

    from app.services.project_order_inquiry_service import _record_cancel

    now = datetime.utcnow()
    inquiry.state = INQUIRY_RAISED
    inquiry.approved_at = now
    inquiry.approved_by = str(actor)
    inquiry.raised_at = now
    to_buy: List[OrderInquiryRow] = []
    for row in rows:
        if Decimal(row.qty or 0) > 0:
            row.state = INQUIRY_RAISED
            to_buy.append(row)
        else:
            row.state = INQUIRY_CANCELLED
            _record_cancel(db, row, "zero_at_approval", actor_user_id=str(actor))
    db.add(
        OrderInquiryRaise(
            company_id=inquiry.company_id,
            order_inquiry_id=inquiry.id,
            kind=OI_RAISE_RAISED,
            raised_by=str(actor),
            raised_at=now,
        )
    )
    _audit(
        db, inquiry, "SPR_RAISED",
        f"Raised to purchasing: {len(to_buy)} line{'' if len(to_buy) == 1 else 's'}", actor,
    )
    db.flush()
    _notify_purchasing(db, inquiry, to_buy)
    return inquiry


def reject(db: Session, inquiry: OrderInquiry, actor: str, reason: Optional[str]) -> OrderInquiry:
    """A5: rejected with a reason; the requester edits and resubmits from the first stage."""
    _require_pending(inquiry, "rejected")
    if not can_decide(db, inquiry, actor):
        raise _forbidden("Only the current approver can reject this request.")
    reason = _text(reason)
    if not reason:
        raise _invalid("reason", "Enter the reason for rejecting.")
    inquiry.state = INQUIRY_REJECTED
    inquiry.reject_reason = reason
    _audit(db, inquiry, "SPR_REJECTED", f"Rejected: {reason}", actor, new={"reason": reason})
    db.flush()
    _emit(db, inquiry, "rejected", actor)
    # A stage that does not resolve on 'rejected' must not stay open on a rejected request.
    _void_stages(db, inquiry, "Rejected")
    db.flush()
    return inquiry


def revise(db: Session, inquiry: OrderInquiry, actor: str) -> OrderInquiry:
    """V1 / V2: back to Draft until purchasing has acknowledged a line or linked a document."""
    if not is_requester(inquiry, actor):
        raise _forbidden("Only the requester can revise this request.")
    if inquiry.state != INQUIRY_RAISED:
        raise _conflict("Only an approved request can be revised.")
    if _taken_on(db, inquiry):
        raise _conflict(
            "Purchasing has already started on this request, so it can no longer be revised.",
            "SPARE_PART_REQUEST_TAKEN_ON",
        )
    inquiry.state = INQUIRY_DRAFT
    inquiry.submitted_at = None
    inquiry.approved_at = None
    inquiry.approved_by = None
    inquiry.reject_reason = None
    for row in _rows(db, inquiry):
        row.state = INQUIRY_DRAFT
        row.ack_state = ACK_AWAITING
        row.acknowledged_by = None
        row.acknowledged_at = None
        row.ack_override = None
        row.ack_override_by = None
        row.ack_override_at = None
        row.actioned_by = None
        row.actioned_at = None
    _void_stages(db, inquiry, "Revised by the requester")
    _audit(db, inquiry, "SPR_REVISED", "Revised: back to draft", actor)
    db.flush()
    return inquiry
