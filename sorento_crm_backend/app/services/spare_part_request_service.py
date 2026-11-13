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
#: G5 (hand-test round): the requester may also edit while it waits for approval; that edit
#: restarts approval at the first level (`update`).
_REQUESTER_EDITABLE = (*_EDITABLE, INQUIRY_PENDING_APPROVAL)
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
    """The shared role-slug read, uncached: every list request then costs the same queries
    whatever an earlier one cached (the header list's bounded-query rule)."""
    from app.services.user_service import UserPermissionService

    if not user_id:
        return False
    slugs = UserPermissionService(db).get_user_role_slugs(str(user_id), use_cache=False)
    return bool(slugs & _ADMIN_ROLE_SLUGS)


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
    """G5: the requester, while Draft, Pending approval or Rejected."""
    return (
        inquiry.inquiry_type == KIND
        and inquiry.state in _REQUESTER_EDITABLE
        and is_requester(inquiry, user_id)
    )


def _can_edit_draft(inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    return can_edit(inquiry, user_id) and inquiry.state in _EDITABLE


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
    """Row photos: the requester while it is a draft or rejected, a decider while it is
    pending. A requester's photo change while pending would skip the approval restart a
    pending edit makes (G5), so it waits for the edit form's save."""
    if inquiry.inquiry_type != KIND:
        return False
    return _can_edit_draft(inquiry, user_id) or can_decide(db, inquiry, user_id)


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


def decidable_ids(
    db: Session, user_id: Optional[str], among: Optional[Set[str]] = None
) -> Set[str]:
    """The pending requests `user_id` may decide on now (their stage team holds the open
    stage), never their own. `among` narrows the read to those request ids."""
    from app.models.sla import ConversationSLATracking
    from app.services.sla_scope import open_tracker_scope

    if not user_id or among == set():
        return set()
    narrow = (
        [ConversationSLATracking.source_entity_id.in_(sorted(among))] if among is not None else []
    )
    trackers = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == KIND, *open_tracker_scope(), *narrow)
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
        .order_by(
            OrderInquiryRow.line_no.asc().nulls_last(),
            OrderInquiryRow.created_at,
            OrderInquiryRow.id,
        )
        .all()
    )


def _line_total(row: OrderInquiryRow) -> Decimal:
    return Decimal(row.qty or 0) * Decimal(row.unit_price or 0)


def request_total(db: Session, inquiry: OrderInquiry) -> str:
    """The request's amount: qty x unit price over its lines still standing, server-side."""
    rows = _rows(db, inquiry)
    return _num(sum((_line_total(r) for r in rows if r.state != INQUIRY_CANCELLED), _ZERO)) or "0"


def detail(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> Dict[str, Any]:
    from app.models.product import Product
    from app.services.project_service import resolve_user_names

    rows = _rows(db, inquiry)
    show_prices = prices_visible(db, inquiry, user_id)
    changes = photo_changes(db, [inquiry]).get(str(inquiry.id), {})
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
    total = request_total(db, inquiry)
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
                "unit_price": _num(row.unit_price) if show_prices else None,
                "total": (_num(_line_total(row)) or "0") if show_prices else None,
                "requested_qty": _num(row.requested_qty),
                "requested_unit_price": _num(row.requested_unit_price) if show_prices else None,
                "state": row.state,
                "ack_state": row.ack_state,
                "photo_changes": changes.get(str(row.id), _NO_PHOTO_CHANGE),
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
        "total": total if show_prices else None,
        "lines": lines,
    }


#: G3: the columns the request list sorts on server-side (the rest are not sortable).
_LIST_SORTS = (
    "inquiry_no",
    "state",
    "needed_by",
    "submitted_at",
    "line_count",
    "requested_by_name",
    "total",
)


def list_requests(
    db: Session,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
    states: Optional[List[str]] = None,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
) -> Dict[str, Any]:
    """G3: the spare part requests list. A requester sees their own (drafts included), a
    stage approver the pending ones they can decide, an admin every submitted one; a draft
    is never anyone's but its requester's."""
    from sqlalchemy import func, select

    from app.services.project_service import resolve_user_names

    uid = str(user_id)
    deciding = decidable_ids(db, uid)
    seen = [OrderInquiry.requested_by == uid]
    if deciding:
        seen.append(OrderInquiry.id.in_(sorted(deciding)))
    admin = is_admin(db, uid)
    if admin:
        seen.append(OrderInquiry.state != INQUIRY_DRAFT)
    line_count = (
        select(func.count(OrderInquiryRow.id))
        .where(
            OrderInquiryRow.order_inquiry_id == OrderInquiry.id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .correlate(OrderInquiry)
        .scalar_subquery()
    )
    from app.models.user import User

    live_rows = and_(
        OrderInquiryRow.order_inquiry_id == OrderInquiry.id,
        OrderInquiryRow.state != INQUIRY_CANCELLED,
    )
    # Sort keys only: the payload's total is still masked below (`price_visible_ids`).
    sort_columns = {
        "line_count": line_count,
        "total": (
            select(func.coalesce(func.sum(OrderInquiryRow.qty * func.coalesce(OrderInquiryRow.unit_price, 0)), 0))
            .where(live_rows)
            .correlate(OrderInquiry)
            .scalar_subquery()
        ),
        "requested_by_name": (
            select(func.lower(func.coalesce(User.name, User.email)))
            .where(User.id == OrderInquiry.requested_by)
            .correlate(OrderInquiry)
            .scalar_subquery()
        ),
    }
    q = db.query(OrderInquiry).filter(OrderInquiry.inquiry_type == KIND, or_(*seen))
    wanted = [s for s in (states or []) if s]
    if wanted:
        q = q.filter(OrderInquiry.state.in_(wanted))
    text = _text(query, 200)
    if text:
        like = f"%{text}%"
        q = q.filter(or_(OrderInquiry.inquiry_no.ilike(like), OrderInquiry.reason.ilike(like)))
    total = q.count()
    key = sort if sort in _LIST_SORTS else "submitted_at"
    column = sort_columns.get(key)
    if column is None:
        column = getattr(OrderInquiry, key)
    ordered = column.asc() if (direction or "desc").lower() == "asc" else column.desc()
    page = max(int(page or 1), 1)
    limit = max(int(limit or 50), 1)
    inquiries = (
        q.order_by(ordered.nulls_last(), OrderInquiry.raised_at.desc(), OrderInquiry.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    ids = [str(i.id) for i in inquiries]
    sums: Dict[str, tuple] = {}
    if ids:
        for inquiry_id, count, amount in (
            db.query(
                OrderInquiryRow.order_inquiry_id,
                func.count(OrderInquiryRow.id),
                func.sum(OrderInquiryRow.qty * func.coalesce(OrderInquiryRow.unit_price, 0)),
            )
            .filter(OrderInquiryRow.order_inquiry_id.in_(ids), OrderInquiryRow.state != INQUIRY_CANCELLED)
            .group_by(OrderInquiryRow.order_inquiry_id)
            .all()
        ):
            sums[str(inquiry_id)] = (int(count or 0), Decimal(amount or 0))
    names = resolve_user_names(db, {i.requested_by for i in inquiries if i.requested_by})
    visible = price_visible_ids(db, inquiries, uid)
    data = []
    for inquiry in inquiries:
        count, amount = sums.get(str(inquiry.id), (0, _ZERO))
        shown = str(inquiry.id) in visible
        data.append(
            {
                "id": str(inquiry.id),
                "inquiry_no": inquiry.inquiry_no,
                "state": inquiry.state,
                "currency": inquiry.currency,
                "requested_by": inquiry.requested_by,
                "requested_by_name": names.get(str(inquiry.requested_by)) if inquiry.requested_by else None,
                "needed_by": inquiry.needed_by,
                "line_count": count,
                "total": (_num(amount) or "0") if shown else None,
                "submitted_at": inquiry.submitted_at,
            }
        )
    return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}}


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
        # G1: the line's own description, the product's name when the form sends none.
        row.description = _text(line.get("description"), 4000) or product.product_name or product.description
        row.stock_location = location
        row.qty = qty if qty is not None else _ZERO
        row.unit_price = unit_price
        row.delivery_date = inquiry.needed_by
        row.state = INQUIRY_DRAFT
        row.line_no = index  # D3: the order the lines were entered in
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
    """R6 / G5: the requester edits a draft, rejected or pending request. An edit while
    pending restarts approval at the first level: the open levels are voided, the submitted
    values become the edited ones and 'submitted' is emitted again."""
    if not is_requester(inquiry, actor):
        raise _forbidden("Only the requester can edit this request.")
    if inquiry.state not in _REQUESTER_EDITABLE:
        raise _conflict("Only a draft, pending or rejected request can be edited.")
    restart = inquiry.state == INQUIRY_PENDING_APPROVAL
    if restart:
        inquiry = _lock(db, inquiry)
        if inquiry.state != INQUIRY_PENDING_APPROVAL:
            raise _conflict("This request was decided while you were editing it.")
    before = _snapshot(db, inquiry)
    _apply_header(inquiry, data)
    _replace_lines(db, inquiry, data.get("lines") or [])
    after = _snapshot(db, inquiry)
    if not restart:
        _audit_edit(db, inquiry, before, after, actor)
        db.flush()
        return inquiry
    rows = _validate_submit(db, inquiry)
    _audit_edit(db, inquiry, before, after, actor, restarted=True)
    _start_approval(db, inquiry, rows, actor, "Edited by the requester")
    return inquiry


_HEADER_LABELS = (
    ("currency", "Currency"),
    ("needed_by", "Needed by"),
    ("default_location", "Default location"),
    ("reason", "Reason"),
)
#: A line's audited fields. The price goes under the COST key `unit_cost` (it is the expected
#: supplier cost), so every History reader masks it like any cost.
_LINE_AUDIT_FIELDS = ("product", "description", "stock_location", "qty", "unit_cost")


def _snapshot(db: Session, inquiry: OrderInquiry) -> Dict[str, Any]:
    from app.utils.date_format import fmt_date

    db.flush()
    return {
        "currency": inquiry.currency,
        "needed_by": fmt_date(inquiry.needed_by) if inquiry.needed_by else None,
        "default_location": inquiry.default_location,
        "reason": inquiry.reason,
        "lines": {
            str(row.id): {
                "row_id": str(row.id),
                "item_code": row.item_code,
                "product": row.item_code,
                "description": row.description,
                "stock_location": row.stock_location,
                "qty": _plain(row.qty),
                "unit_cost": _plain(row.unit_price),
            }
            for row in _rows(db, inquiry)
        },
    }


def _audit_edit(
    db: Session, inquiry, before: Dict[str, Any], after: Dict[str, Any], actor, *, restarted: bool = False
) -> None:
    """R5: the requester's edit as History, old -> new per changed header field and line.
    Header changes are the entry's title; each changed line is one of its lines (the reader
    renders them). An edit that changes nothing writes nothing, unless it restarted
    approval (G5): that is always written, as "Edited, approval restarted"."""
    parts = [
        f"{label} {before[key] or 'not set'} → {after[key] or 'not set'}"
        for key, label in _HEADER_LABELS
        if before[key] != after[key]
    ]
    old_lines, new_lines = before["lines"], after["lines"]
    removed = [line for row_id, line in old_lines.items() if row_id not in new_lines]
    changed_old, changed_new = [], []
    for row_id, line in new_lines.items():
        prior = old_lines.get(row_id)
        if prior is None:
            changed_new.append({**line, "added": True})
            continue
        fields = [f for f in _LINE_AUDIT_FIELDS if prior.get(f) != line.get(f)]
        if fields:
            changed_old.append({"row_id": row_id, **{f: prior.get(f) for f in fields}})
            changed_new.append({"row_id": row_id, "item_code": line["item_code"], **{f: line.get(f) for f in fields}})
    if removed:
        codes = ", ".join(str(line["item_code"] or "a line") for line in removed)
        parts.append(f"removed {codes}")
    if not parts and not changed_new and not restarted:
        return
    title = "Edited, approval restarted" if restarted else "Edited"
    new = {**{k: after[k] for k, _ in _HEADER_LABELS}, "lines": changed_new}
    if restarted:
        new["approval_restarted"] = True
    _audit(
        db, inquiry, "SPR_EDITED",
        title + (f": {'; '.join(parts)}" if parts else ""),
        actor,
        old={**{k: before[k] for k, _ in _HEADER_LABELS}, "lines": changed_old},
        new=new,
    )


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


def _assert_has_stage(db: Session) -> None:
    if not _has_stage(db):
        raise AppException(
            status_code=422,
            message=(
                "No approval level is set up for spare part requests. Ask an admin to add one "
                "in Form SLA configuration."
            ),
            code="spr_no_approval_stage",
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
    _assert_has_stage(db)
    was_rejected = inquiry.state == INQUIRY_REJECTED
    _audit(
        db, inquiry, "SPR_SUBMITTED", "Resubmitted for approval" if was_rejected else "Submitted for approval",
        actor,
    )
    _start_approval(db, inquiry, rows, actor, "Submitted again")
    return inquiry


def _start_approval(
    db: Session, inquiry: OrderInquiry, rows: List[OrderInquiryRow], actor: str, void_reason: str
) -> None:
    """Pending approval at the first configured level, from the values as they stand now:
    the submit (A1) and the requester's edit while pending (G5) both go through here."""
    _assert_has_stage(db)
    for row in rows:
        row.requested_qty = row.qty
        row.requested_unit_price = row.unit_price
    inquiry.state = INQUIRY_PENDING_APPROVAL
    inquiry.submitted_at = datetime.utcnow()
    inquiry.reject_reason = None
    db.flush()
    # A stage left open by an earlier round never decides this one: approval starts again.
    _void_stages(db, inquiry, void_reason)
    _emit(db, inquiry, "submitted", actor)
    # Fail closed: a request no level is open on would wait for nobody.
    if not _open_stages(db, inquiry.id):
        raise AppException(
            status_code=422,
            message=(
                "The first approval level has no one to assign it to. Ask an admin to add "
                "members to its team in Form SLA configuration."
            ),
            code="spr_first_stage_not_started",
        )


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


def _lock(db: Session, inquiry: OrderInquiry) -> OrderInquiry:
    """The inquiry, re-read under SELECT ... FOR UPDATE: two decisions on one request take
    turns, and the second sees what the first did (security review B1)."""
    return (
        db.query(OrderInquiry)
        .filter(OrderInquiry.id == inquiry.id)
        .with_for_update()
        .populate_existing()
        .one()
    )


def _actor_stage(db: Session, inquiry: OrderInquiry, user_id: Optional[str]):
    """The open stage this user decides on: the oldest one whose team they sit on, or for an
    admin on no such team the oldest open stage. None when there is none."""
    stages = list(reversed(_open_stages(db, inquiry.id)))  # oldest first
    if not user_id or is_requester(inquiry, user_id):
        return None
    for tracker in stages:
        if _on_stage_team(db, tracker, user_id, inquiry.company_id):
            return tracker
    if stages and is_admin(db, user_id):
        return stages[0]
    return None


_STALE_DECISION = "This request was changed; reload to see the latest."


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None or value.tzinfo is None:
        return value
    from datetime import timezone

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _require_seen(inquiry: OrderInquiry, seen_submitted_at: Optional[datetime]) -> None:
    """S2: a decision names the submission the approver saw; an edit that restarted approval
    since then moved submitted_at, so the stale page is refused instead of approving unseen."""
    if seen_submitted_at is None:
        return
    if _naive_utc(seen_submitted_at) != _naive_utc(inquiry.submitted_at):
        raise _conflict(_STALE_DECISION, "SPARE_PART_REQUEST_STALE")


def _authorise(
    db: Session,
    inquiry: OrderInquiry,
    actor: str,
    verb: str,
    *,
    need_stage: bool,
    seen_submitted_at: Optional[datetime] = None,
):
    """Lock the request, name the stage the actor decides on, authorise, then check that
    stage is STILL open: a decision is bound to the stage it was authorised on, so a second
    approve racing the first cannot carry over to the next level (security review B1)."""
    inquiry = _lock(db, inquiry)
    _require_pending(inquiry, verb)
    _require_seen(inquiry, seen_submitted_at)
    stage = _actor_stage(db, inquiry, actor)
    if not can_decide(db, inquiry, actor):
        raise _forbidden("Only the current approver can decide on this request.")
    db.refresh(inquiry)
    _require_pending(inquiry, verb)
    if stage is not None:
        db.refresh(stage)
        if stage.is_resolved or stage.voided_at is not None:
            raise _conflict(
                "This approval level has already been decided.", "SPARE_PART_REQUEST_STAGE_DECIDED"
            )
    elif need_stage:
        raise _conflict(
            "No approval level is open on this request. Ask an admin to check its approval "
            "stages in Form SLA configuration.",
            "SPARE_PART_REQUEST_NO_OPEN_STAGE",
        )
    return inquiry, stage


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
    stay on the row; each change is a History entry. The price is audited under the COST key
    `unit_cost` (it is the expected supplier cost), so History masks it like any cost."""
    inquiry, _stage = _authorise(db, inquiry, actor, "changed", need_stage=False)
    row = _row_or_404(db, inquiry, row_id)
    changes = (
        ("qty", "qty", "Qty", _decimal(qty, "qty")),
        ("unit_price", "unit_cost", "Unit price", _decimal(unit_price, "unit_price")),
    )
    for field, audit_key, label, value in changes:
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
            old={"row_id": str(row.id), "item_code": row.item_code, audit_key: _plain(before)},
            new={"row_id": str(row.id), "item_code": row.item_code, audit_key: _plain(value)},
        )
    db.flush()
    return row


_NEXT_STAGE_CANNOT_START = (
    "The next approval level has no one to assign it to, so this approval was not recorded. "
    "Ask an admin to add members to its team in Form SLA configuration."
)


def _assert_no_unchained_level(db: Session, next_config) -> None:
    """Fail closed (C2): a configured level that would start on 'approved' and is not the
    chained next level never starts here (approval closes one level, it emits nothing), so
    the request cannot be finished while one exists."""
    from app.models.sla import FormSLAConfig

    for config in (
        db.query(FormSLAConfig)
        .filter(FormSLAConfig.source_entity_type == KIND, FormSLAConfig.is_active.is_(True))
        .all()
    ):
        starts_on = {t.strip() for t in str(config.start_event or "").split(",")}
        if "approved" in starts_on and (next_config is None or config.id != next_config.id):
            raise _conflict(
                "Another approval level is set to start on approval but is not linked as the "
                "next level, so this approval was not recorded. Ask an admin to check the "
                "approval levels in Form SLA configuration.",
                "SPARE_PART_REQUEST_UNCHAINED_LEVEL",
            )


def _assert_stage_can_start(db: Session, config, company_id: Optional[str]) -> None:
    """Fail closed (security review S2): the next level must have a team with someone on it
    before this level is closed, or the request would be raised on one level of sign-off."""
    from app.models.access import AccessAgent, TeamMember
    from app.services.user_service import AccessAgentService

    agent = db.query(AccessAgent).filter(AccessAgent.code == config.agent_code).first()
    resolved = (
        AccessAgentService(db).resolve_team_with_tier_fallback(
            str(agent.id), 1, team_set_code=config.team_set_code, company_id=company_id
        )
        if agent is not None
        else None
    )
    if not resolved or db.query(TeamMember.id).filter(TeamMember.team_id == resolved[0]).first() is None:
        raise _conflict(_NEXT_STAGE_CANNOT_START, "SPARE_PART_REQUEST_NEXT_STAGE")


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


def approve(
    db: Session,
    inquiry: OrderInquiry,
    actor: str,
    note: Optional[str] = None,
    *,
    seen_submitted_at: Optional[datetime] = None,
) -> OrderInquiry:
    """A6: approve the stage the actor decides on, and only that stage (parallel levels each
    decide their own, security review S1). The request is raised only when no level is left
    open AND the configured chain has no next level for this one (S2: finality comes from
    the chain, never from "nothing is open"); then lines with qty go to purchasing, lines at
    0 are cancelled."""
    from app.services.form_sla_service import FormSLAOrchestrator

    inquiry, stage = _authorise(
        db, inquiry, actor, "approved", need_stage=True, seen_submitted_at=seen_submitted_at
    )
    rows = [r for r in _rows(db, inquiry) if r.state != INQUIRY_CANCELLED]
    if not any(Decimal(r.qty or 0) > 0 for r in rows):
        raise _invalid("lines", "Every line is at 0. Reject the request instead.")
    orchestrator = FormSLAOrchestrator(db)
    next_config = orchestrator.next_stage_config(stage, "approved")
    if next_config is not None:
        _assert_stage_can_start(db, next_config, inquiry.company_id)
    _assert_no_unchained_level(db, next_config)
    note = _text(note)
    _audit(
        db, inquiry, "SPR_APPROVED", "Approved" + (f": {note}" if note else ""), actor,
        new={"note": note} if note else None,
    )
    db.flush()
    try:
        orchestrator.resolve_stage(
            stage, "approved", actor_user_id=actor, company_id=inquiry.company_id
        )
    except AppException:
        raise _conflict(_NEXT_STAGE_CANNOT_START, "SPARE_PART_REQUEST_NEXT_STAGE")
    inquiry = _lock(db, inquiry)
    # C3: a decision that landed while this level was being closed (a reject) wins.
    _require_pending(inquiry, "approved")
    still_open = _open_stages(db, inquiry.id)
    if next_config is not None and not any(
        t.team_set_code == next_config.team_set_code for t in still_open
    ):
        raise _conflict(_NEXT_STAGE_CANNOT_START, "SPARE_PART_REQUEST_NEXT_STAGE")
    if still_open:
        return inquiry  # the next (or a parallel) level decides; its team is told by the SLA machinery

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
    # History's "Raised" entry is this raise row (the same one every OI raise writes); no
    # second audit line for the same moment.
    db.flush()
    _notify_purchasing(db, inquiry, to_buy)
    return inquiry


def reject(
    db: Session,
    inquiry: OrderInquiry,
    actor: str,
    reason: Optional[str],
    *,
    seen_submitted_at: Optional[datetime] = None,
) -> OrderInquiry:
    """A5: rejected with a reason; the requester edits and resubmits from the first stage."""
    from app.services.form_sla_service import FormSLAOrchestrator

    inquiry, stage = _authorise(
        db, inquiry, actor, "rejected", need_stage=False, seen_submitted_at=seen_submitted_at
    )
    reason = _text(reason)
    if not reason:
        raise _invalid("reason", "Enter the reason for rejecting.")
    inquiry.state = INQUIRY_REJECTED
    inquiry.reject_reason = reason
    _audit(db, inquiry, "SPR_REJECTED", f"Rejected: {reason}", actor, new={"reason": reason})
    db.flush()
    if stage is not None:
        try:
            FormSLAOrchestrator(db).resolve_stage(
                stage, "rejected", actor_user_id=actor, company_id=inquiry.company_id
            )
        except AppException:
            logger.warning("spare part request %s: rejecting stage did not resolve", inquiry.id)
    # Every other level stops too: a rejected request goes back to its requester.
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
        # A clean slate: purchasing's earlier refusal was about the request as approved,
        # and the request is about to change and be approved again.
        row.state = INQUIRY_DRAFT
        row.ack_state = ACK_AWAITING
        row.rejected_by = None
        row.rejected_at = None
        row.rejected_reason = None
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


# ------------------------------------------------------------------ delete draft (G1)


def assert_deletable(db: Session, inquiry_id: str, user_id: Optional[str]) -> OrderInquiry:
    """Delete draft: the requester's own Draft or Rejected request, nothing else (404 not a
    spare part request, 403 not theirs, 409 once submitted). Checked when the countdown is
    parked and again when it commits."""
    inquiry = db.query(OrderInquiry).filter(OrderInquiry.id == str(inquiry_id)).first()
    if inquiry is None or inquiry.inquiry_type != KIND:
        raise AppException(404, "This spare part request no longer exists.", code="spr_not_found")
    if not is_requester(inquiry, user_id):
        raise _forbidden("Only the requester can delete this request.")
    if inquiry.state not in _EDITABLE:
        raise _conflict(
            "Only a draft or rejected request can be deleted.", "SPARE_PART_REQUEST_NOT_DRAFT"
        )
    return inquiry


def delete_draft(db: Session, inquiry_id: str, user_id: Optional[str]) -> None:
    """Hard delete: the header, its lines and the lines' photo links. Runs when the
    pending-action window lapses."""
    from app.services.entity_attachment_service import EntityAttachmentService
    from app.services.so_line_attachments import OI_ROW

    inquiry = assert_deletable(db, inquiry_id, user_id)
    links = EntityAttachmentService(db)
    for row in _rows(db, inquiry):
        links.delete_links_for_entity(OI_ROW.entity_type, str(row.id))
        db.delete(row)
    _void_stages(db, inquiry, "Deleted by the requester")
    db.flush()
    db.delete(inquiry)
    db.commit()


# ------------------------------------------------------------------ photo changes (G2)

_NO_PHOTO_CHANGE = {"added": 0, "removed": 0}


def photo_changes(db: Session, inquiries: Iterable[Any]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """`{inquiry_id: {row_id: {added, removed}}}`: photos added to / removed from each line
    since the request was last submitted (what the requester attached while drafting is the
    request itself, not a change). Read off the request's own History rows, in the order they
    were written, so no clock is compared with another."""
    from app.models.audit import AuditLog

    ids = {str(getattr(i, "id", i)) for i in inquiries if i is not None}
    if not ids:
        return {}
    audits = (
        db.query(AuditLog.entity_id, AuditLog.event, AuditLog.old_values, AuditLog.new_values)
        .filter(AuditLog.entity_type == AUDIT_ENTITY, AuditLog.entity_id.in_(sorted(ids)))
        .order_by(AuditLog.changed_at, AuditLog.id)
        .all()
    )
    out: Dict[str, Dict[str, Dict[str, int]]] = {}
    for entity_id, event, old, new in audits:
        key = str(entity_id)
        if event == "SPR_SUBMITTED" or (event == "SPR_EDITED" and (new or {}).get("approval_restarted")):
            out[key] = {}  # a restarted approval (G5) counts from the edit, like a submit
            continue
        if event == "SPR_REVISED":
            out.pop(key, None)
            continue
        if key not in out:
            continue  # not submitted yet: a drafting photo
        old, new = old or {}, new or {}
        if "attachment_added" in new:
            row_id, field = str(new.get("row_id") or ""), "added"
        elif "attachment_removed" in old:
            row_id, field = str(old.get("row_id") or ""), "removed"
        else:
            continue
        counts = out[key].setdefault(row_id, dict(_NO_PHOTO_CHANGE))
        counts[field] += 1
    return out


# ------------------------------------------------------------------ price visibility (G8)


def price_visible_ids(db: Session, inquiries, user_id: Optional[str]) -> Set[str]:
    """THE price rule (G8), for one request or a page of them: the ids of `inquiries` whose
    unit price (the expected supplier COST, crew ruling (b)) `user_id` may see. Its requester,
    anyone who can decide on it now (`can_decide`: a current stage team member, or an admin,
    while pending, never the requester), and an approver of record (browser pass R12: someone
    who approved, rejected or changed a line keeps seeing prices after their level closed)
    always see them; anyone else only with `products.cost.view` (`cost_access`, read off this
    request's own stamp). A fixed number of reads whatever the page size."""
    from app.models.audit import AuditLog
    from app.services.cost_access import cost_hidden

    wanted = [i for i in inquiries if i is not None]
    ids = {str(i.id) for i in wanted}
    if not cost_hidden():
        return ids
    if not user_id or not ids:
        return set()
    uid = str(user_id)
    shown = {str(i.id) for i in wanted if is_requester(i, uid)}
    rest = [i for i in wanted if str(i.id) not in shown]
    if not rest:
        return shown
    shown |= decidable_ids(db, uid, among={str(i.id) for i in rest})
    pending = {
        str(i.id)
        for i in rest
        if i.inquiry_type == KIND and i.state == INQUIRY_PENDING_APPROVAL
    }
    if pending - shown and is_admin(db, uid):
        shown |= pending
    left = {str(i.id) for i in rest} - shown
    if left:
        shown |= {
            str(entity_id)
            for (entity_id,) in db.query(AuditLog.entity_id)
            .filter(
                AuditLog.entity_type == AUDIT_ENTITY,
                AuditLog.entity_id.in_(sorted(left)),
                AuditLog.event.in_(_DECISION_EVENTS),
                AuditLog.user_id == uid,
            )
            .distinct()
            .all()
        }
    return shown


def prices_visible(db: Session, inquiry: OrderInquiry, user_id: Optional[str]) -> bool:
    """`price_visible_ids` for one request."""
    return str(inquiry.id) in price_visible_ids(db, [inquiry], user_id)


#: The approver's own moves on a request, as History records them.
_DECISION_EVENTS = ("SPR_APPROVED", "SPR_REJECTED", "SPR_LINE_CHANGED")


#: The worklist (Lines tab) row keys that carry a spare part request's price.
_ROW_PRICE_KEYS = ("unit_price", "line_total", "submitted_unit_price")


def mask_row_prices(db: Session, items: List[Dict[str, Any]], user_id: Optional[str]) -> None:
    """Null a spare part row's prices for a reader who may not see them (`price_visible_ids`),
    in place. One check for the whole page, never per row."""
    from app.services.cost_access import cost_hidden

    if not cost_hidden():
        return
    ids = {str(item.get("order_inquiry_id")) for item in items if item.get("inquiry_type") == KIND}
    if not ids:
        return
    inquiries = db.query(OrderInquiry).filter(OrderInquiry.id.in_(sorted(ids))).all()
    shown = price_visible_ids(db, inquiries, user_id)
    for item in items:
        if item.get("inquiry_type") == KIND and str(item.get("order_inquiry_id")) not in shown:
            for key in _ROW_PRICE_KEYS:
                item[key] = None
