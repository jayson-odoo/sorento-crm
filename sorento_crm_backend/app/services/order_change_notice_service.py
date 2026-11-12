"""Order Change Notice service (OCN-ORDER-CHANGE-NOTICE): every rule of the form.

The OCN is the existing `projects.order_change_notices` row, raised by hand (`source = crm`) or
drafted from a sales order amendment (`source = amendment`), and run through the purchase
request's approval chain. The template is the new product application
(`new_product_application_service`): each move is a module function `fn(db, row, *, actor, ...)`
that checks who may act and what state allows it, writes the row, flushes and returns the SLA
event name; the router commits, then `notify` emits that event (best effort).

The chain's own rules are NOT here: they are `app.services.approval_chain_rules`, the same
functions the purchase request calls (plan "Shared once, never copied"). This module adds only
what is the OCN's: who may act, its status checks, its form fields and lines, and its notices.

Statuses (the purchase request's values): draft -> submitted / resubmitted -> (approval
pending) -> approved / rejected -> processed_by_cs ("Done"), and voided. Revise takes an
approved or rejected notice back to draft with the next revision number.

Plan: documentation/plans/procurement/PLAN-ocn-order-change-notice-12nov.md.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.project_so import OrderChangeNotice, OrderChangeNoticeLine, OrderChangeType
from app.services import approval_chain_rules as rules
from app.services import submission_status
from app.services.error_handler import AppException, handle_not_found

logger = logging.getLogger(__name__)

ENTITY = "order_change_notice"
NOUN = "order change notice"

VIEW = "procurement.order_change_notices.view"
VIEW_OWN = "procurement.order_change_notices.view_own"
CREATE = "procurement.order_change_notices.create"
EDIT = "procurement.order_change_notices.edit"
DELETE = "procurement.order_change_notices.delete"
APPROVE = "procurement.order_change_notices.approve"
#: Customer service's Done, apart from `.edit` (security review M3: the PR's `process` grants it).
PROCESS = "procurement.order_change_notices.process"
REPORT = "procurement.order_change_notices.report"

DRAFT = "draft"
SUBMITTED = submission_status.SUBMITTED
RESUBMITTED = submission_status.RESUBMITTED
APPROVED = "approved"
REJECTED = "rejected"
DONE = "processed_by_cs"
VOIDED = "voided"

STATUS_LABELS = {
    DRAFT: "Draft",
    SUBMITTED: "Submitted",
    RESUBMITTED: submission_status.APPEALED_LABEL,
    APPROVED: "Approved",
    REJECTED: "Rejected",
    DONE: "Done",
    VOIDED: "Voided",
}

#: Statuses the raiser edits in; everything else is locked (an approved one is revised first).
EDITABLE = (DRAFT, REJECTED)
AWAITING_REVIEW = submission_status.AWAITING_REVIEW
#: Revise takes these back to draft (UAC B8).
REVISABLE = (APPROVED, REJECTED)

SOURCE_CRM = "crm"
SOURCE_AMENDMENT = "amendment"

#: Numbering (plan "Shared once"): one rule, `OCN{yy}-` and 4 digits, yearly, per company.
NUMBERING_DOC_TYPE = "order_change_notice"
#: The number when no rule is configured at all: the delta service's original fallback.
_FALLBACK_PREFIX = "OCN-"
_FALLBACK_DIGITS = 6

#: The moves the form SLA config listens to (the purchase request chain's event names).
SLA_EVENTS = ("submit", "send_for_approval", "reject_submitted", "approved", "approval_rejected", "resolved")

HEADER_TEXT = ("customer_name", "customer_po_no", "so_no_text", "description")
#: An amendment-born notice shows these read-only (UAC E4); an edit leaves them alone.
AMENDMENT_LINKS = ("project_id", "project_sales_order_id", "purchase_order_id")

#: Risk order, low to high, for the list sort.
RISK_ORDER = {"low": 1, "high": 2, "highest": 3}
#: Lifecycle order for the list sort.
STATUS_ORDER = {DRAFT: 1, SUBMITTED: 2, RESUBMITTED: 3, APPROVED: 4, REJECTED: 5, DONE: 6, VOIDED: 7}


@dataclass
class Actor:
    user_id: Optional[str] = None
    can_view_all: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_approve: bool = False
    can_process: bool = False
    can_delete: bool = False
    #: `.view_own` without the view-all grants: the notices they raised or are named on.
    own_only: bool = False


#: The grants that see every notice: viewing all, and the people who act on others' notices
#: (an editor, an approver, customer service). Ownership never stands in for these.
VIEW_ALL_SLUGS = frozenset({VIEW, EDIT, APPROVE, PROCESS})


def actor_from_slugs(user_id: Optional[str], slugs: Iterable[str]) -> Actor:
    s = set(slugs)
    can_view_all = bool(s & VIEW_ALL_SLUGS)
    return Actor(
        user_id=str(user_id) if user_id else None,
        can_view_all=can_view_all,
        can_create=CREATE in s,
        can_edit=EDIT in s,
        can_approve=APPROVE in s,
        can_process=PROCESS in s,
        can_delete=DELETE in s,
        own_only=VIEW_OWN in s and not can_view_all,
    )


def actor_for_user(db: Session, user_id: Optional[str]) -> Actor:
    from app.services.user_service import UserPermissionService

    slugs = UserPermissionService(db).get_user_permission_slugs(str(user_id)) if user_id else set()
    return actor_from_slugs(user_id, slugs)


# ------------------------------------------------------------------ small helpers


def today_malaysia() -> date:
    """The notice's date is the Malaysia calendar day (a server day is the UTC one)."""
    from app.services.certificate_service import today_malaysia as _today

    return _today()


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _forbidden(message: str) -> AppException:
    return AppException(status_code=403, message=message, code="FORBIDDEN")


def _conflict(message: str, code: str = "ORDER_CHANGE_NOTICE_ILLEGAL_MOVE") -> AppException:
    return AppException(status_code=409, message=message, code=code)


def _invalid(field: str, message: str) -> AppException:
    return AppException(
        status_code=422, message=message, code="VALIDATION_ERROR", details={"field": field}
    )


def _invalid_reason(message: str) -> AppException:
    """The chain rules' refusal for a missing reason, as this form answers it (422)."""
    return _invalid("reason", message)


def _label(row: OrderChangeNotice) -> str:
    return STATUS_LABELS.get(row.status or "", (row.status or "").replace("_", " ")).lower()


def _status(row: OrderChangeNotice) -> str:
    return (row.status or "").strip().lower()


def _display_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    from app.models.user import User

    if not user_id:
        return None
    user = db.query(User.name, User.email).filter(User.id == str(user_id)).first()
    if user is None:
        return None
    return (user.name or "").strip() or user.email or None


# ------------------------------------------------------------------ numbering (shared)


def next_ocn_number(db: Session, company_id: Optional[str]) -> str:
    """The next notice number of `company_id`: the one numbering function, used by the sales
    order amendment draft (`ProjectSODeltaService._next_ocn_number`) and by this service."""
    from app.services.numbering_service import NumberingService

    # Each company has its own rule row (seeded per company by migration ocn_0001, like the
    # purchase request's); an install without one falls back to the shared unscoped rule.
    company = str(company_id) if company_id else None
    configured = NumberingService(db).get_next_number(
        NUMBERING_DOC_TYPE, company_id=company, commit_rule=False
    )
    if configured:
        return configured
    highest = 0
    query = db.query(OrderChangeNotice.ocn_number).filter(
        OrderChangeNotice.ocn_number.like(f"{_FALLBACK_PREFIX}%")
    )
    if company:
        query = query.filter(OrderChangeNotice.company_id == company)
    for (number,) in query.all():
        tail = (number or "")[len(_FALLBACK_PREFIX):]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{_FALLBACK_PREFIX}{highest + 1:0{_FALLBACK_DIGITS}d}"


# ------------------------------------------------------------------ loading and visibility


def find(db: Session, ocn_id: Any, *, for_update: bool = False) -> Optional[OrderChangeNotice]:
    """The notice in the caller's company scope, or None (another company's reads as missing)."""
    if not _is_uuid(ocn_id):
        return None
    query = db.query(OrderChangeNotice).filter(OrderChangeNotice.id == str(ocn_id))
    if for_update:
        query = query.with_for_update(of=OrderChangeNotice)
    return query.first()


def get_for(db: Session, ocn_id: Any, *, for_update: bool = False) -> OrderChangeNotice:
    row = find(db, ocn_id, for_update=for_update)
    if row is None:
        raise handle_not_found("Order change notice", str(ocn_id))
    return row


def is_mine(row: OrderChangeNotice, actor: Actor) -> bool:
    """Raised it, or named on it as sales or customer service in charge."""
    uid = actor.user_id
    return bool(uid) and uid in {
        str(row.created_by or ""),
        str(row.sales_in_charge_user_id or ""),
        str(row.cs_in_charge_user_id or ""),
    }


def can_view(actor: Actor) -> bool:
    return actor.can_view_all or actor.own_only


def assert_can_view(row: OrderChangeNotice, actor: Actor) -> None:
    """Who may read this notice. A grant is always needed: `.view` (or a grant that acts on
    others' notices) sees every notice; `.view_own` sees the ones they raised or are named on,
    and another's reads as not found. Being the raiser or named never stands in for a grant
    (security review M2)."""
    if actor.can_view_all:
        return
    if actor.own_only:
        if is_mine(row, actor):
            return
        raise handle_not_found("Order change notice", str(row.id))
    raise _forbidden("You do not have access to this order change notice.")


def reader_for(db: Session, ocn_id: Any, user_id: Optional[str]) -> OrderChangeNotice:
    """The ONE reader check for every surface of a notice (detail, Conversation, SLA tab,
    History): load it in the caller's company, build their actor, apply `assert_can_view`.
    404 when it is not in their company (or not theirs under view_own), 403 without a grant."""
    actor = actor_for_user(db, user_id)
    if not can_view(actor):
        raise _forbidden("You do not have access to order change notices.")
    row = get_for(db, ocn_id)
    assert_can_view(row, actor)
    return row


def _visible(query, actor: Actor):
    if actor.can_view_all:
        return query
    uid = str(actor.user_id or "")
    return query.filter(
        or_(
            OrderChangeNotice.created_by == uid,
            OrderChangeNotice.sales_in_charge_user_id == uid,
            OrderChangeNotice.cs_in_charge_user_id == uid,
        )
    )


def _is_raiser(row: OrderChangeNotice, actor: Actor) -> bool:
    return bool(actor.user_id) and str(row.created_by or "") == actor.user_id


# ------------------------------------------------------------------ the form


def _ref_exists(db: Session, model, ref_id: Any) -> bool:
    # A query, not db.get: the company filter applies to queries, so another company's row
    # reads as missing.
    return _is_uuid(ref_id) and db.query(model.id).filter(model.id == str(ref_id)).first() is not None


def _active_type(db: Session, type_id: Any) -> Optional[OrderChangeType]:
    if not _is_uuid(type_id):
        return None
    row = db.query(OrderChangeType).filter(OrderChangeType.id == str(type_id)).first()
    return row if row is not None and row.is_active else None


def _check_refs(db: Session, data: Dict[str, Any], *, current_project_id: Optional[str] = None) -> None:
    from app.models.order import Customer
    from app.models.product import Product
    from app.models.projects import Project
    from app.models.user import User

    type_id = data.get("change_type_id")
    if type_id is not None and _active_type(db, type_id) is None:
        raise _invalid("change_type_id", "Choose one of the listed change types.")
    if data.get("customer_id") is not None and not _ref_exists(db, Customer, data["customer_id"]):
        raise _invalid("customer_id", "That customer is not in the debtor list.")
    if data.get("project_id") is not None:
        if not _ref_exists(db, Project, data["project_id"]):
            raise _invalid("project_id", "That project does not exist.")
        # A notice links a project, never a registration still waiting for approval (as the PR).
        from app.services.project_service import assert_linkable_project

        assert_linkable_project(
            db, data["project_id"], current_project_id, code="order_change_notice_project_not_approved"
        )
    for field, word in (("sales_in_charge_user_id", "sales"), ("cs_in_charge_user_id", "customer service")):
        value = data.get(field)
        if value is not None and db.query(User.id).filter(User.id == str(value)).first() is None:
            raise _invalid(field, f"Choose the {word} in charge from the list.")
    lines = data.get("lines") or []
    wanted = {str(line.get("product_id")) for line in lines if _is_uuid(line.get("product_id"))}
    # One query for every line (the company filter applies), not one per line.
    known = {str(i) for (i,) in db.query(Product.id).filter(Product.id.in_(wanted)).all()} if wanted else set()
    for index, line in enumerate(lines, start=1):
        if not line.get("product_id"):
            raise _invalid("lines", f"Line {index}: choose a product from the catalogue.")
        if str(line["product_id"]) not in known:
            raise _invalid("lines", f"Line {index}: that product is not in the catalogue.")


def _apply(db: Session, row: OrderChangeNotice, data: Dict[str, Any]) -> None:
    """Check every reference first, then assign: no query runs between the assignments, so
    a new notice is inserted whole (one CREATE in its History, no UPDATE of its own fields)."""
    data = dict(data)
    if row.source == SOURCE_AMENDMENT or (row.id is not None and linked_amendment(db, row) is not None):
        # UAC E4: the project, sales order and PO links came from the amendment (born from it,
        # or picked by it), so they stay.
        for key in AMENDMENT_LINKS:
            data.pop(key, None)
    _check_refs(db, data, current_project_id=row.project_id)
    with db.no_autoflush:
        for key in ("change_type_id", "customer_id", "project_id", "sales_in_charge_user_id",
                    "cs_in_charge_user_id"):
            if key in data:
                setattr(row, key, str(data[key]) if data[key] else None)
        if "ocn_date" in data:
            row.ocn_date = data["ocn_date"] or None
        for key in HEADER_TEXT:
            if key in data:
                setattr(row, key, _clean(data[key]))
        if "lines" in data:
            _apply_lines(row, data["lines"] or [])


def _apply_lines(row: OrderChangeNotice, body: List[Dict[str, Any]]) -> None:
    """The lines as sent, in the order sent (the old ones go). Quantities are never capped by
    stock (UAC A6)."""
    row.lines = [
        OrderChangeNoticeLine(
            position=position,
            product_id=str(line["product_id"]),
            qty_before=line.get("qty_before"),
            qty_after=line.get("qty_after"),
            date_before=line.get("date_before"),
            date_after=line.get("date_after"),
            delivered_qty=line.get("delivered_qty"),
            remark=_clean(line.get("remark")),
        )
        for position, line in enumerate(body, start=1)
    ]


def _acting_company(db: Session) -> str:
    from app.api.v1.projects._common import acting_company_id

    return acting_company_id(db)


def create_draft(
    db: Session, *, actor: Actor, data: Dict[str, Any], source: str = SOURCE_CRM
) -> OrderChangeNotice:
    if not actor.can_create:
        raise _forbidden("You cannot raise order change notices.")
    company_id = _acting_company(db)
    number = next_ocn_number(db, company_id)
    row = OrderChangeNotice(
        company_id=company_id,
        ocn_number=number,
        status=DRAFT,
        source=source,
        created_by=actor.user_id,
        ocn_date=today_malaysia(),
        revision_no=0,
    )
    _apply(db, row, data)
    db.add(row)
    db.flush()
    return row


def _assert_may_edit(row: OrderChangeNotice, actor: Actor, verb: str) -> None:
    """The raiser edits their own notice while they hold `.create`; `.edit` edits any."""
    if not ((_is_raiser(row, actor) and actor.can_create) or actor.can_edit):
        raise _forbidden(f"Only the raiser or an order change notice editor can {verb} this notice.")


def update(db: Session, row: OrderChangeNotice, *, actor: Actor, data: Dict[str, Any]) -> None:
    _assert_may_edit(row, actor, "edit")
    if _status(row) not in EDITABLE:
        if _status(row) == APPROVED:
            raise _conflict(
                "This order change notice is approved, so it is locked. Revise it to change it.",
                "ORDER_CHANGE_NOTICE_LOCKED",
            )
        raise _conflict(f"A {_label(row)} order change notice cannot be changed.", "ORDER_CHANGE_NOTICE_LOCKED")
    _apply(db, row, data)
    db.flush()


# ------------------------------------------------------------------ moves


def _require_project_setting(db: Session) -> bool:
    from app.models.user import SystemSetting

    setting = db.query(SystemSetting).first()
    return bool(getattr(setting, "order_change_notice_require_project", False)) if setting else False


def carries_change_rows(row: OrderChangeNotice) -> bool:
    """An amendment-born notice whose change table has rows: the table is its line items."""
    return row.source == SOURCE_AMENDMENT and bool((row.change_table_json or {}).get("rows"))


def validate_submit(db: Session, row: OrderChangeNotice) -> None:
    """The one Submit rule set (the form mirrors it): the type of change; the customer and the
    customer PO, and at least one line, unless the notice carries an amendment's change rows;
    the project when the setting asks for it."""
    if row.change_type_id is None or _active_type(db, row.change_type_id) is None:
        raise _invalid("change_type_id", "Choose the type of change.")
    from_amendment = carries_change_rows(row)
    if not from_amendment:
        if not (row.customer_name or "").strip() and row.customer_id is None:
            raise _invalid("customer_name", "Enter the customer name.")
        if not (row.customer_po_no or "").strip():
            raise _invalid("customer_po_no", "Enter the customer PO no.")
        if not row.lines:
            raise _invalid("lines", "Add at least one line item.")
    if row.project_id is None and _require_project_setting(db):
        raise _invalid("project_id", "Choose the project before you submit.")


def submit(db: Session, row: OrderChangeNotice, *, actor: Actor) -> str:
    """Draft -> Submitted, or Rejected -> Resubmitted (the raiser amends and sends it again)."""
    _assert_may_edit(row, actor, "submit")
    rules.refuse_if_voided(row, "submitted", noun=NOUN)
    if _status(row) not in EDITABLE:
        raise _conflict(f"A {_label(row)} order change notice cannot be submitted.")
    validate_submit(db, row)
    was_rejected = _status(row) == REJECTED
    row.status = submission_status.status_on_submit(was_rejected=was_rejected)
    row.submitted_at = datetime.utcnow()
    if was_rejected:
        # A fresh submission: the reviewers see no old rejection on it.
        row.approval_status = None
        row.approval_comments = None
        row.approved_at = None
        row.approved_by = None
        row.approver_id = None
        row.rejected_by_id = None
    db.flush()
    return "submit"


def send_for_approval(db: Session, row: OrderChangeNotice, *, actor: Actor) -> Optional[str]:
    """Submitted -> approval pending. None when it already was (no second approval stage)."""
    if not actor.can_edit:
        raise _forbidden("You cannot send order change notices for approval.")
    rules.refuse_if_voided(row, "sent for approval", noun=NOUN)
    if _status(row) not in AWAITING_REVIEW:
        raise _conflict(f"Only a submitted order change notice can be sent for approval, not a {_label(row)} one.")
    already_pending = rules.apply_send_for_approval(
        row,
        requested_by_user_id=actor.user_id,
        rejected_message="This order change notice was rejected. Its raiser edits and submits it again.",
        noun=NOUN,
    )
    db.flush()
    return None if already_pending else "send_for_approval"


def reject_submitted(db: Session, row: OrderChangeNotice, *, actor: Actor, reason: Optional[str]) -> str:
    """Send back: a submitted notice goes back to its raiser with the reason."""
    if not actor.can_edit:
        raise _forbidden("You cannot send order change notices back.")
    if not (reason or "").strip():
        raise _invalid("reason", "Enter the reason for sending it back.")
    rules.refuse_if_voided(row, "rejected", noun=NOUN)
    if _status(row) not in AWAITING_REVIEW:
        raise _conflict(f"Only a submitted order change notice can be sent back, not a {_label(row)} one.")
    rules.apply_reject_submitted(
        db,
        row,
        reason=reason,
        actor_user_id=actor.user_id,
        actor_display_name=_display_name(db, actor.user_id),
        noun=NOUN,
        invalid=_invalid_reason,
    )
    db.flush()
    return "reject_submitted"


def decide(
    db: Session, row: OrderChangeNotice, *, actor: Actor, action: str, comments: Optional[str]
) -> str:
    """The approval decision. Approve stamps the approver; reject needs remarks."""
    if not actor.can_approve:
        raise _forbidden("You cannot approve or reject order change notices.")
    rules.assert_decidable(row, noun=NOUN)
    stored = rules.decision_comments(action, comments, invalid=_invalid_reason)
    rules.apply_decision(
        row,
        action,
        approved_by=_display_name(db, actor.user_id) or "",
        approval_comments=stored,
        rejected_by_id=rules.existing_user_id(db, actor.user_id),
        noun=NOUN,
    )
    row.approver_id = rules.existing_user_id(db, actor.user_id) if action == APPROVED else None
    db.flush()
    return "approved" if action == APPROVED else "approval_rejected"


def mark_done(
    db: Session, row: OrderChangeNotice, *, actor: Actor, cs_comment: Optional[str] = None
) -> Optional[str]:
    """Customer service: an approved notice is Done, with an optional comment."""
    if not actor.can_process:
        raise _forbidden("You cannot mark order change notices done.")
    if _status(row) == DONE:
        return None  # already done: nothing moves, nothing is emitted
    if not rules.can_finalize(row):
        raise _conflict(f"Only an approved order change notice can be marked done, not a {_label(row)} one.")
    row.status = DONE
    row.cs_comment = _clean(cs_comment)
    db.flush()
    return "resolved"


def void(db: Session, row: OrderChangeNotice, *, actor: Actor, reason: Optional[str]) -> str:
    """Void from any open status. The open stages are voided, never resolved (UAC B7)."""
    _assert_may_edit(row, actor, "void")
    text = rules.void_reason(reason, invalid=_invalid_reason)
    rules.apply_void(row, reason=text, actor_user_id=actor.user_id, noun=NOUN)
    _void_sla(db, row, f"Voided: {text}", void_reason="voided")
    db.flush()
    return "voided"


def revise(db: Session, row: OrderChangeNotice, *, actor: Actor, reason: Optional[str]) -> None:
    """Approved or rejected -> draft with the next revision number (UAC B8). The approval stamp
    is cleared and the open stages are voided; nothing is emitted, so the next Submit starts
    the chain again."""
    if not (actor.can_edit or actor.can_approve):
        raise _forbidden("You cannot revise order change notices.")
    rules.refuse_if_voided(row, "revised", noun=NOUN)
    if _status(row) not in REVISABLE:
        raise _conflict(
            f"Only an approved or rejected order change notice can be revised, not a {_label(row)} one.",
            "ORDER_CHANGE_NOTICE_NOT_REVISABLE",
        )
    text = _clean(reason)
    if not text:
        raise _invalid("reason", "Say what changed, and why.")
    _back_to_draft(db, row, text)
    return None


def _back_to_draft(db: Session, row: OrderChangeNotice, reason: str) -> None:
    """Revise's writes, shared with an amendment that picks an approved notice: back to draft at
    the next revision, the approval stamp cleared, the open stages voided (audited by the row
    listener, like every write)."""
    row.status = DRAFT
    row.revision_no = (row.revision_no or 0) + 1
    row.approval_status = None
    row.approved_at = None
    row.approved_by = None
    row.approver_id = None
    row.approval_comments = None
    row.rejected_by_id = None
    row.requested_approval_by_user_id = None
    _void_sla(db, row, f"Revised: {reason}", void_reason="withdrawn")
    db.flush()


# ------------------------------------------------------------------ SLA and notices


def _void_sla(db: Session, row: OrderChangeNotice, reason: str, *, void_reason: str) -> None:
    """The open stages stop (voided, never resolved), in the move's own transaction. Who held
    them is kept on the instance for the notice that goes out after the commit."""
    row._sla_voided_to = set()  # noqa: SLF001
    from app.services.form_sla_service import FormSLAOrchestrator

    voided = FormSLAOrchestrator(db).void_active_for_source(
        ENTITY, str(row.id), reason=reason, void_reason=void_reason
    )
    for tracker in voided:
        for user_id in (tracker.assigned_to_id, getattr(tracker, "_voided_handled_by_id", None)):
            if user_id:
                row._sla_voided_to.add(str(user_id))  # noqa: SLF001


def _emit_sla(db: Session, row: OrderChangeNotice, event: str, actor_id: Optional[str]) -> None:
    """Drive the form SLA stages. Errors never undo the committed move."""
    try:
        from app.services.form_sla_service import emit_form_event

        emit_form_event(
            db,
            ENTITY,
            str(row.id),
            event,
            actor_user_id=actor_id,
            # The notice's own company routes its stages.
            company_id=str(row.company_id) if row.company_id else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("order change notice SLA event failed: %s %s (%s)", event, row.id, exc)
        if not db.is_active:
            db.rollback()


def notify(db: Session, row: OrderChangeNotice, event: Optional[str], actor_id: Optional[str] = None) -> None:
    """Call AFTER the move commits. The started stage tells its assignee (the SLA engine); a
    void tells whoever held the stages it stopped. Best effort: never undoes the move."""
    if event in SLA_EVENTS:
        _emit_sla(db, row, event, actor_id)
    elif event == "voided":
        from app.services.form_void_notify import notify_form_voided_in_app

        notify_form_voided_in_app(
            db,
            source_entity_type=ENTITY,
            source_entity_id=str(row.id),
            entity_number=row.ocn_number,
            actor_user_id=actor_id,
            user_ids=getattr(row, "_sla_voided_to", None) or set(),
        )
    if event in RAISER_NOTICES:
        _tell_raiser(db, row, event, actor_id)


#: What the raiser is told, in-app, after each move that is theirs to know (review M3): a send
#: back or a rejection is theirs to amend and submit again.
RAISER_NOTICES = {
    "reject_submitted": "was sent back to you",
    "approval_rejected": "was rejected",
    "approved": "was approved",
    "resolved": "is done",
    "voided": "was voided",
}


def _tell_raiser(db: Session, row: OrderChangeNotice, event: str, actor_id: Optional[str]) -> None:
    """An in-app notice to the raiser (never to whoever made the move). Best effort: a failure
    is logged and never undoes the committed move."""
    raiser = str(row.created_by or "")
    if not raiser or raiser == str(actor_id or ""):
        return
    title = f"Order change notice {row.ocn_number} {RAISER_NOTICES[event]}"
    reason = row.approval_comments if event in ("reject_submitted", "approval_rejected") else (
        row.void_reason if event == "voided" else None
    )
    try:
        from app.services.notification_service import NotificationService

        NotificationService(db).create_with_channel_preferences(
            user_id=raiser,
            type=f"order_change_notice_{event}",
            title=title,
            body=f"{title}. Reason: {reason}" if reason else title,
            data={"link": f"/procurement-management/order-change-notices/{row.id}", "ocn_number": row.ocn_number},
            source_entity_type=ENTITY,
            source_entity_id=str(row.id),
            dedup_key=f"{row.id}:{event}:{row.revision_no or 0}",
            event_type=f"order_change_notice_{event}",
            send_in_app=True,
            send_email=False,
            send_whatsapp=False,
            send_web_push=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("order change notice raiser notice not sent: %s %s (%s)", event, row.id, exc)
        if not db.is_active:
            db.rollback()


def finish(db: Session, row: OrderChangeNotice, event: Optional[str], actor_id: Optional[str]) -> Dict[str, Any]:
    """Commit, then tell whoever now has to act, then answer with the fresh record."""
    db.commit()
    if event:
        notify(db, row, event, actor_id=actor_id)
        db.commit()
    db.refresh(row)
    return serialize_detail(db, row)


def run_move(db: Session, ocn_id: str, user_id: Optional[str], fn, **kw) -> Dict[str, Any]:
    """Load (row lock), check the reader, move, commit, notify: one move, whole."""
    try:
        row = get_for(db, ocn_id, for_update=True)
        actor = actor_for_user(db, user_id)
        assert_can_view(row, actor)
        event = fn(db, row, actor=actor, **kw)
        return finish(db, row, event, actor.user_id)
    except Exception:
        db.rollback()
        raise


class ChainRunner:
    """The purchase request service's chain method names and signatures, over the notice, so
    `form_actions._declare_approval_chain` declares the `ocn.*` deferred actions exactly as
    it declares `pr.*` (same columns, same runners). Each runs one whole move."""

    def __init__(self, db: Session):
        self.db = db

    def decide_approval(
        self,
        ocn_id: str,
        *,
        action: str,
        approved_by: Optional[str] = None,
        approval_comments: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ):
        return run_move(self.db, ocn_id, actor_user_id, decide, action=action, comments=approval_comments)

    def set_pending_approval(self, ocn_id: str, requested_by_user_id: Optional[str] = None):
        return run_move(self.db, ocn_id, requested_by_user_id, send_for_approval)

    def reject_submitted(
        self, ocn_id: str, rejection_reason: Optional[str] = None, actor_user_id: Optional[str] = None
    ):
        return run_move(self.db, ocn_id, actor_user_id, reject_submitted, reason=rejection_reason)

    def _finalize_request(
        self,
        ocn_id: str,
        new_status: str,
        *,
        note: Optional[str] = None,
        respond_user_id: Optional[str] = None,
        crm_sender_user_id: Optional[str] = None,
    ):
        if new_status != DONE:
            raise _conflict(f"An order change notice cannot be finalized as {new_status!r}.")
        return run_move(self.db, ocn_id, crm_sender_user_id, mark_done, cs_comment=note)

    def void_request(
        self,
        ocn_id: str,
        *,
        void_reason: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        respond_user_id: Optional[str] = None,
    ):
        return run_move(self.db, ocn_id, actor_user_id, void, reason=void_reason)


# ------------------------------------------------------------------ reads


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _num(value) -> Optional[str]:
    return None if value is None else format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)


def _user_names(db: Session, ids: Iterable[Any]) -> Dict[str, str]:
    from app.models.user import User

    wanted = {str(i) for i in ids if i}
    if not wanted:
        return {}
    rows = db.query(User.id, User.name, User.email).filter(User.id.in_(wanted)).all()
    return {str(r.id): ((r.name or "").strip() or r.email or "") for r in rows}


def _project_titles(db: Session, ids: Iterable[Any]) -> Dict[str, str]:
    from app.models.projects import Project

    wanted = {str(i) for i in ids if i}
    if not wanted:
        return {}
    return {str(pid): title for pid, title in db.query(Project.id, Project.title).filter(Project.id.in_(wanted)).all()}


def serialize_summary(
    row: OrderChangeNotice, names: Dict[str, str], titles: Dict[str, str]
) -> Dict[str, Any]:
    kind = row.change_type
    return {
        "id": str(row.id),
        "ocn_number": row.ocn_number,
        "ocn_date": _iso(row.ocn_date),
        "status": row.status,
        "status_label": ocn_status_word(row),
        "approval_status": row.approval_status,
        "revision_no": row.revision_no or 0,
        "source": row.source,
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "customer_name": row.customer_name,
        "customer_po_no": row.customer_po_no,
        "so_no_text": row.so_no_text,
        "change_type_id": str(row.change_type_id) if row.change_type_id else None,
        "change_type_name": kind.name if kind else None,
        "risk_level": kind.risk_level if kind else None,
        "project_id": str(row.project_id) if row.project_id else None,
        "project_title": titles.get(str(row.project_id)) if row.project_id else None,
        "sales_in_charge_user_id": row.sales_in_charge_user_id,
        "sales_in_charge_name": names.get(str(row.sales_in_charge_user_id or "")) or None,
        "cs_in_charge_user_id": row.cs_in_charge_user_id,
        "cs_in_charge_name": names.get(str(row.cs_in_charge_user_id or "")) or None,
        "created_at": _iso(row.created_at),
    }


def linked_amendment(db: Session, row: OrderChangeNotice):
    """The sales order amendment that carries this notice, if any (one at most)."""
    from app.models.project_so import SOAmendment

    return db.query(SOAmendment).filter(SOAmendment.ocn_id == row.id).first()


def _amendment_refs(db: Session, row: OrderChangeNotice) -> Dict[str, Any]:
    """The sales order, PO and amendment a notice belongs to, by number (never an id on screen;
    the ids only build the links)."""
    from app.models.project_so import ProjectSalesOrder
    from app.models.projects import ProjectPurchaseOrder

    so = (
        db.query(ProjectSalesOrder.provisional_ref, ProjectSalesOrder.autocount_doc_no)
        .filter(ProjectSalesOrder.id == row.project_sales_order_id)
        .first()
        if row.project_sales_order_id
        else None
    )
    po = (
        db.query(ProjectPurchaseOrder.po_number).filter(ProjectPurchaseOrder.id == row.purchase_order_id).first()
        if row.purchase_order_id
        else None
    )
    amendment = linked_amendment(db, row) if row.id is not None else None
    return {
        "so_ref": (so.autocount_doc_no or so.provisional_ref) if so else None,
        "po_number": po.po_number if po else None,
        "amendment_id": str(amendment.id) if amendment else None,
        "amendment_status": amendment.status if amendment else None,
        "amendment_sales_order_id": str(amendment.project_sales_order_id) if amendment else None,
    }


def serialize_detail(db: Session, row: OrderChangeNotice) -> Dict[str, Any]:
    from app.models.product import Product

    people = (
        row.sales_in_charge_user_id, row.cs_in_charge_user_id, row.created_by, row.approver_id,
        row.rejected_by_id, row.requested_approval_by_user_id, row.voided_by,
    )
    names = _user_names(db, people)
    titles = _project_titles(db, [row.project_id])
    out = serialize_summary(row, names, titles)
    products = {
        str(pid): (code, name)
        for pid, code, name in db.query(Product.id, Product.product_code, Product.product_name)
        .filter(Product.id.in_([str(line.product_id) for line in row.lines] or ["00000000-0000-0000-0000-000000000000"]))
        .all()
    }
    kind = row.change_type
    out.update(
        {
            "guide_text": kind.guide_text if kind else None,
            "description": row.description,
            "cs_comment": row.cs_comment,
            "reason": row.reason,
            "project_sales_order_id": str(row.project_sales_order_id) if row.project_sales_order_id else None,
            "purchase_order_id": str(row.purchase_order_id) if row.purchase_order_id else None,
            "change_table_json": row.change_table_json,
            **_amendment_refs(db, row),
            "created_by": row.created_by,
            "created_by_name": names.get(str(row.created_by or "")) or None,
            "submitted_at": _iso(row.submitted_at),
            "approver_id": row.approver_id,
            "approver_name": names.get(str(row.approver_id or "")) or None,
            "approved_at": _iso(row.approved_at),
            "approved_by": row.approved_by,
            "approval_comments": row.approval_comments,
            "rejected_by_id": row.rejected_by_id,
            "rejected_by_name": names.get(str(row.rejected_by_id or "")) or None,
            "requested_approval_by_user_id": row.requested_approval_by_user_id,
            "voided_by": row.voided_by,
            "voided_by_name": names.get(str(row.voided_by or "")) or None,
            "voided_at": _iso(row.voided_at),
            "void_reason": row.void_reason,
            "lines": [
                {
                    "id": str(line.id),
                    "position": line.position,
                    "product_id": str(line.product_id),
                    "product_code": products.get(str(line.product_id), (None, None))[0],
                    "product_name": products.get(str(line.product_id), (None, None))[1],
                    "qty_before": _num(line.qty_before),
                    "qty_after": _num(line.qty_after),
                    "date_before": _iso(line.date_before),
                    "date_after": _iso(line.date_after),
                    "delivered_qty": _num(line.delivered_qty),
                    "remark": line.remark,
                }
                for line in row.lines
            ],
        }
    )
    return out


def _type_column(column):
    return select(column).where(OrderChangeType.id == OrderChangeNotice.change_type_id).scalar_subquery()


def _sorts() -> Dict[str, Any]:
    from app.models.projects import Project
    from app.models.user import User

    return {
        "ocn_number": OrderChangeNotice.ocn_number,
        "ocn_date": OrderChangeNotice.ocn_date,
        "customer_name": OrderChangeNotice.customer_name,
        "customer_po_no": OrderChangeNotice.customer_po_no,
        "change_type_name": _type_column(OrderChangeType.name),
        # By severity, low to high, not by label.
        "risk_level": _type_column(
            case(
                *[(func.lower(OrderChangeType.risk_level) == k, v) for k, v in RISK_ORDER.items()],
                else_=None,
            )
        ),
        "project_title": select(Project.title).where(Project.id == OrderChangeNotice.project_id).scalar_subquery(),
        "sales_in_charge_name": select(func.coalesce(User.name, User.email))
        .where(User.id == OrderChangeNotice.sales_in_charge_user_id)
        .scalar_subquery(),
        # By lifecycle, not by label.
        "status": case(
            *[(OrderChangeNotice.status == k, v) for k, v in STATUS_ORDER.items()], else_=None
        ),
        "created_at": OrderChangeNotice.created_at,
    }


#: The list's "Pending approval" filter value: a submitted notice waiting on its approver (the
#: word the rows show), which is not a stored status of its own.
PENDING_APPROVAL = "pending_approval"


def status_filter_clause(statuses: List[str]):
    """The status filter as one OR: stored statuses, plus Pending approval when it is chosen.
    A submitted notice waiting on approval reads Pending approval, so Submitted leaves it out."""
    awaiting = OrderChangeNotice.status.in_(AWAITING_REVIEW)
    pending = OrderChangeNotice.approval_status == "pending"
    clauses = []
    plain = [s for s in statuses if s != PENDING_APPROVAL]
    awaiting_chosen = [s for s in plain if s in AWAITING_REVIEW]
    others = [s for s in plain if s not in AWAITING_REVIEW]
    if others:
        clauses.append(OrderChangeNotice.status.in_(others))
    if awaiting_chosen:
        clauses.append(
            and_(
                OrderChangeNotice.status.in_(awaiting_chosen),
                or_(OrderChangeNotice.approval_status.is_(None), OrderChangeNotice.approval_status != "pending"),
            )
        )
    if PENDING_APPROVAL in statuses:
        clauses.append(and_(awaiting, pending))
    return or_(*clauses) if clauses else OrderChangeNotice.id.is_(None)


def list_for(
    db: Session,
    *,
    actor: Actor,
    statuses: Optional[List[str]] = None,
    change_type_ids: Optional[List[str]] = None,
    risk_levels: Optional[List[str]] = None,
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    sort: Optional[str] = None,
    direction: str = "desc",
) -> Dict[str, Any]:
    query = _visible(db.query(OrderChangeNotice), actor)
    if statuses:
        query = query.filter(status_filter_clause(statuses))
    if change_type_ids:
        query = query.filter(OrderChangeNotice.change_type_id.in_(change_type_ids))
    if risk_levels:
        lowered = [r.strip().lower() for r in risk_levels if r and r.strip()]
        query = query.filter(
            OrderChangeNotice.change_type_id.in_(
                select(OrderChangeType.id).where(func.lower(OrderChangeType.risk_level).in_(lowered))
            )
        )
    text = (q or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            or_(
                OrderChangeNotice.ocn_number.ilike(like),
                OrderChangeNotice.customer_name.ilike(like),
                OrderChangeNotice.customer_po_no.ilike(like),
                OrderChangeNotice.so_no_text.ilike(like),
            )
        )
    total = query.count()
    column = _sorts().get(sort or "", OrderChangeNotice.created_at)
    ordered = column.asc() if direction == "asc" else column.desc()
    tie = OrderChangeNotice.ocn_number.asc() if direction == "asc" else OrderChangeNotice.ocn_number.desc()
    rows = query.order_by(ordered.nulls_last(), tie).offset((page - 1) * limit).limit(limit).all()
    names = _user_names(db, [r.sales_in_charge_user_id for r in rows] + [r.cs_in_charge_user_id for r in rows])
    titles = _project_titles(db, [r.project_id for r in rows])
    return {
        "data": [serialize_summary(r, names, titles) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
    }


def list_for_project(
    db: Session, project_id: str, *, actor: Actor, linkable: bool = False
) -> List[Dict[str, Any]]:
    """The project page's panel: that project's notices, newest first. `linkable` keeps only
    the ones an amendment may pick (`linkable_clause`, the same predicate the pick enforces)."""
    query = _visible(db.query(OrderChangeNotice), actor).filter(OrderChangeNotice.project_id == project_id)
    if linkable:
        query = query.filter(linkable_clause())
    rows = (
        query
        .order_by(OrderChangeNotice.created_at.desc().nulls_last(), OrderChangeNotice.ocn_number.desc())
        .all()
    )
    names = _user_names(db, [r.sales_in_charge_user_id for r in rows])
    titles = _project_titles(db, [project_id])
    return [serialize_summary(r, names, titles) for r in rows]


def change_types(db: Session) -> List[Dict[str, Any]]:
    """The active change types, in list order, for the form's picker."""
    rows = (
        db.query(OrderChangeType)
        .filter(OrderChangeType.is_active.is_(True))
        .order_by(OrderChangeType.position, OrderChangeType.name)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "risk_level": r.risk_level,
            "guide_text": r.guide_text,
            "is_active": bool(r.is_active),
        }
        for r in rows
    ]


# ------------------------------------------------------------------ amendment link (UAC E2)


#: A notice an amendment may take (lead ruling, security H1): not waiting on an approver, not
#: closed. Picking an approved one revises it back to draft, so its new change is approved again.
LINKABLE_STATUSES = (DRAFT, SUBMITTED, RESUBMITTED, REJECTED, APPROVED)


def linkable_clause():
    """The ONE linkable predicate, as SQL: an open status, no approval pending, and no amendment
    links it yet. `assert_linkable` and the project list's `linkable=true` both use it."""
    from app.models.project_so import SOAmendment

    return and_(
        OrderChangeNotice.status.in_(LINKABLE_STATUSES),
        or_(OrderChangeNotice.approval_status.is_(None), OrderChangeNotice.approval_status != "pending"),
        ~exists().where(SOAmendment.ocn_id == OrderChangeNotice.id),
    )


def assert_linkable(
    db: Session, ocn_id: str, *, project_id: Optional[str], actor: Actor
) -> OrderChangeNotice:
    """An existing notice an amendment may take: one the author can see, of the same project,
    passing `linkable_clause`. The row is locked for the rest of the transaction, so two
    amendments cannot link it at once (the partial unique index on so_amendments.ocn_id is the
    backstop). An approved notice goes back to draft at the next revision before the change
    table is put on it, so publishing waits for a fresh approval of this change."""
    row = find(db, ocn_id, for_update=True)
    if row is None:
        raise _invalid("ocn_id", "That order change notice does not exist.")
    assert_can_view(row, actor)
    if str(row.project_id or "") != str(project_id or ""):
        raise _invalid("ocn_id", "That order change notice belongs to another project.")
    if db.query(OrderChangeNotice.id).filter(OrderChangeNotice.id == row.id, linkable_clause()).first() is None:
        raise _conflict(
            f"A {ocn_status_word(row).lower()} or already linked order change notice cannot be picked.",
            "ORDER_CHANGE_NOTICE_NOT_LINKABLE",
        )
    if _status(row) == APPROVED:
        _back_to_draft(db, row, "Picked for a sales order amendment: the change needs approval.")
    return row


def ocn_status_word(row: OrderChangeNotice) -> str:
    """The status in plain words (a submitted notice waiting on its approver reads Pending
    approval), the same words the screens use."""
    if _status(row) in AWAITING_REVIEW and (row.approval_status or "") == "pending":
        return "Pending approval"
    return STATUS_LABELS.get(_status(row), _status(row))


def is_approved(row: Optional[OrderChangeNotice]) -> bool:
    """What publishing an amendment needs (UAC E3): approved, and not voided since."""
    return (
        row is not None
        and (row.approval_status or "").strip().lower() == APPROVED
        and _status(row) != VOIDED
    )
