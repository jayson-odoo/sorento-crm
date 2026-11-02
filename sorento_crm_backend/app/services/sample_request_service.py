"""Sample request service (SR-CORE): create, edit a draft, submit, move, list, print.

The staff router and the portal router both call this module, so every rule lives once.
Ownership and permission are decided here from an `Actor`, never in the routers:

- owner = `salesperson_id == actor.user_id` (staff) or `contact_id == actor.contact_id` (portal);
- `can_process` (`projects.sample_requests.process`) moves a request along and fills the
  internal fields; the owner may only submit and cancel a Draft / Submitted request.

The legal moves are the edges of the `sample_request` status graph (card rule 10), so an
admin who edits the graph changes them; the permission rules are by status KEY.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Brand, Product
from app.models.projects import Project
from app.models.sample_request import SampleRequest, SampleRequestLine
from app.models.status import Status, StatusTransition
from app.models.user import SystemSetting, User
from app.services.error_handler import AppException, handle_not_found
from app.utils.multi_value import multi_values
from app.services.pdf_render import today_in_malaysia

ENTITY = "sample_request"

DRAFT = "draft"
SUBMITTED = "submitted"
PROCESSING = "processing"
CUSTOMER_CONFIRMED = "customer_confirmed"
DELIVERED = "delivered"
CANCELLED = "cancelled"

#: What the coordinator queue shows until a filter says otherwise (AC-SR-51).
DEFAULT_OPEN = (SUBMITTED, PROCESSING, CUSTOMER_CONFIRMED)

#: PS-SAMPLE-TRACKING rule 1: the two stages, by status KEY. Draft, Cancelled and any key an
#: admin adds sit outside both. The graph itself is unchanged (owner Q2 a, 2 Nov).
STAGE_PROCESSING = "processing"
STAGE_DELIVERY = "delivery"
STAGES = {
    SUBMITTED: STAGE_PROCESSING,
    PROCESSING: STAGE_PROCESSING,
    CUSTOMER_CONFIRMED: STAGE_PROCESSING,
    DELIVERED: STAGE_DELIVERY,
}
#: Where the team may still change its date answer (after Start processing, before Delivered).
DATE_ANSWER_OPEN = (PROCESSING, CUSTOMER_CONFIRMED)


def stage_for(key: Optional[str]) -> Optional[str]:
    return STAGES.get(key or "")


def stage_keys(stages: Iterable[str]) -> List[str]:
    wanted = set(stages)
    return [key for key, stage in STAGES.items() if stage in wanted]

HEADER_TEXT = (
    "customer_name",
    "project_title",
    "scope_note",
    "ship_to_name",
    "ship_to_address",
    "site_contact_name",
    "site_contact_phone",
    "site_contact_note",
    "purpose",
    "board_label",
)
#: NOT NULL columns: an explicit null in a payload means "leave as is".
HEADER_NOT_NULL = ("loan_value", "loan_unit", "goods_from")


@dataclass
class Actor:
    user_id: Optional[str] = None
    contact_id: Optional[str] = None
    can_process: bool = False
    can_view_all: bool = False
    #: `.view_own` without `.view` (PORTAL-P2-ONLY-THEIRS): their own rows, the ones raised
    #: from the portal by their own contact included, and anything else is not found.
    own_only: bool = False
    own_contact_id: Optional[str] = None


# ------------------------------------------------------------------ small helpers


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _forbidden(message: str = "You do not have access to this sample request.") -> AppException:
    return AppException(status_code=403, message=message, code="FORBIDDEN")


def _incomplete(field: str, message: str) -> AppException:
    return AppException(
        status_code=422,
        message=message,
        code="SAMPLE_REQUEST_INCOMPLETE",
        details={"field": field},
    )


def is_owner(req: SampleRequest, actor: Actor) -> bool:
    if actor.contact_id is not None:
        return req.contact_id is not None and str(req.contact_id) == str(actor.contact_id)
    return actor.user_id is not None and req.salesperson_id == actor.user_id


def can_view(req: SampleRequest, actor: Actor) -> bool:
    if actor.can_view_all or is_owner(req, actor):
        return True
    return bool(
        actor.own_contact_id and req.contact_id and str(req.contact_id) == actor.own_contact_id
    )


def assert_can_view(req: SampleRequest, actor: Actor) -> None:
    if not can_view(req, actor):
        if actor.own_only:
            raise handle_not_found("Sample request", req.id)
        raise _forbidden()


def require_project_flag(db: Session) -> bool:
    row = db.query(SystemSetting).first()
    return bool(getattr(row, "sample_request_require_project", False))


def _statuses(db: Session) -> Dict[str, Status]:
    rows = (
        db.query(Status)
        .filter(Status.entity_type == ENTITY, Status.scope_id.is_(None))
        .all()
    )
    if not rows:
        raise AppException(
            status_code=500,
            message="The sample request status graph has not been set up.",
            code="SAMPLE_REQUEST_GRAPH_MISSING",
        )
    return {s.key: s for s in rows}


def status_key(db: Session, req: SampleRequest) -> Optional[str]:
    if req.status_id is None:
        return None
    row = db.query(Status.key).filter(Status.id == req.status_id).first()
    return row[0] if row else None


def _set_status(db: Session, req: SampleRequest, key: str) -> None:
    req.status_id = _statuses(db)[key].id
    db.flush()


def _edge_exists(db: Session, frm: Optional[str], to: str) -> bool:
    statuses = _statuses(db)
    if frm not in statuses or to not in statuses:
        return False
    return (
        db.query(StatusTransition.id)
        .filter(
            StatusTransition.entity_type == ENTITY,
            StatusTransition.from_status_id == statuses[frm].id,
            StatusTransition.to_status_id == statuses[to].id,
        )
        .first()
        is not None
    )


def illegal_move(frm: Optional[str], to: str) -> AppException:
    return AppException(
        status_code=409,
        message=f"A sample request cannot move from {frm or 'no status'} to {to}.",
        code="SAMPLE_REQUEST_ILLEGAL_MOVE",
    )


# ------------------------------------------------------------------ validation


def _check_products(
    db: Session, lines: Iterable[Dict[str, Any]], kept: frozenset = frozenset()
) -> None:
    """Every product must exist and be active (AC-SR-10). Ids already on
    the request (`kept`) are accepted even if they went inactive since; only NEW ids must
    be active."""
    wanted: set[str] = set()
    for line in lines:
        value = line.get("product_id")
        if value is None:
            continue
        if not _is_uuid(value):
            raise _product_invalid()
        wanted.add(str(value))
    if not wanted:
        return
    found = {
        str(pid)
        for (pid,) in db.query(Product.id)
        .filter(
            Product.id.in_(wanted),
            or_(Product.is_active.is_(True), Product.id.in_(list(kept) or [None])),
        )
        .all()
    }
    if wanted - found:
        raise _product_invalid()


def _product_invalid() -> AppException:
    return AppException(
        status_code=422,
        message="Every line needs a product from the product list, and it has to be active.",
        code="SAMPLE_REQUEST_PRODUCT_INVALID",
        details={"field": "lines"},
    )


def _check_refs(db: Session, data: Dict[str, Any]) -> None:
    from app.models.order import Customer

    cid = data.get("customer_id")
    if cid and (
        not _is_uuid(cid) or db.query(Customer.id).filter(Customer.id == cid).first() is None
    ):
        raise AppException(
            status_code=422,
            message="That customer was not found.",
            code="SAMPLE_REQUEST_CUSTOMER_INVALID",
            details={"field": "customer_id"},
        )
    pid = data.get("project_id")
    from app.services.project_service import approved_projects

    # A portal registration waiting for approval is not a project yet (PROJECT-REG-PORTAL R4).
    if pid and (
        not _is_uuid(pid)
        or approved_projects(db.query(Project.id).filter(Project.id == pid)).first() is None
    ):
        raise AppException(
            status_code=422,
            message="That project was not found.",
            code="SAMPLE_REQUEST_PROJECT_INVALID",
            details={"field": "project_id"},
        )


def assert_portal_project_allowed(db: Session, *, contact, project_id: Optional[str]) -> None:
    """A project picked in the portal must be one `projects_for_contact` returns (AC-SR-42)."""
    if not project_id:
        return
    from app.models.base import company_scope
    from app.services.sponsorship_link_service import contact_company_ids

    company_ids = contact_company_ids(db, contact=contact)
    allowed = False
    if company_ids and _is_uuid(project_id):
        with company_scope(db, frozenset(company_ids)):
            from app.services.project_service import approved_projects

            allowed = (
                approved_projects(
                    db.query(Project.id).filter(
                        Project.id == project_id, Project.company_id.in_(company_ids)
                    )
                ).first()
                is not None
            )
    if not allowed:
        raise AppException(
            status_code=422,
            message="Pick one of your own projects.",
            code="SAMPLE_REQUEST_PROJECT_NOT_ALLOWED",
            details={"field": "project_id"},
        )


def portal_customers(db: Session, contact_id: str, q: str = "") -> List[Dict[str, Any]]:
    """The debtors a portal contact may pick: their `debtors-for-agent` that carry a customer
    id. The portal picker lists exactly this and `assert_portal_customer_allowed` accepts
    exactly this, so a picked debtor can never be refused on submit."""
    from app.services.price_tag_request_service import PriceTagRequestService

    needle = (q or "").strip().lower()
    rows = []
    for d in PriceTagRequestService.lookup_debtors_for_agent(db, str(contact_id)):
        if not d.get("customer_id"):
            continue
        code = d.get("customer_code") or d.get("debtor_code") or ""
        name = d.get("customer_name") or d.get("debtor_name") or ""
        if needle and needle not in code.lower() and needle not in name.lower():
            continue
        rows.append({"customer_id": str(d["customer_id"]), "customer_code": code, "debtor_name": name})
    return rows


def assert_portal_customer_allowed(db: Session, *, contact_id: str, customer_id: Optional[str]) -> None:
    """A debtor picked in the portal must be one of `portal_customers` (the set the picker
    lists); anything else is refused. A typed name needs no check."""
    if not customer_id:
        return
    allowed = {row["customer_id"] for row in portal_customers(db, contact_id)}
    if str(customer_id) not in allowed:
        raise AppException(
            status_code=422,
            message="Pick one of your own customers, or type the customer name.",
            code="SAMPLE_REQUEST_CUSTOMER_INVALID",
            details={"field": "customer_id"},
        )


def validate_submit(db: Session, req: SampleRequest) -> None:
    """The refusals of AC-SR-02/03/06/21/22, in the contract's order."""
    require_project = require_project_flag(db)

    if not (req.customer_id or _clean(req.customer_name)):
        raise _incomplete("customer_id", "Pick the customer, or type the customer name.")
    if require_project:
        if not req.project_id:
            raise _incomplete("project_id", "Pick the project.")
    elif not (req.project_id or _clean(req.project_title)):
        raise _incomplete("project_id", "Pick the project, or type the project title.")
    if not req.delivery_date:
        raise _incomplete("delivery_date", "Enter the Request Delivery Date.")
    if not req.delivery_mode:
        raise _incomplete("delivery_mode", "Choose a delivery mode.")
    if not _clean(req.ship_to_name):
        raise _incomplete("ship_to_name", "Enter the ship-to name.")
    if not req.lines and not req.board_mounting:
        raise _incomplete("lines", "Add at least one item.")
    if req.board_mounting and not _clean(req.board_label):
        raise _incomplete("board_label", "Enter the board label.")

def _source_invalid() -> AppException:
    return AppException(
        status_code=422,
        message="That quotation is not one of this project's.",
        code="SAMPLE_REQUEST_QUOTATION_INVALID",
        details={"field": "quotation_document_id"},
    )


def _check_source(db: Session, req: SampleRequest) -> None:
    """The recorded source quotation (SFQ-13) must be the request's own project's, and its issue
    that document's. Checked on the FINAL header, so moving a request to another project without
    clearing the source is refused rather than leaving it pointing at a stranger's quotation."""
    from app.models.projects import ProjectQuotationDocument, ProjectQuotationIssue

    doc_id, issue_id = req.quotation_document_id, req.quotation_issue_id
    if not doc_id and not issue_id:
        return
    if not doc_id or not _is_uuid(doc_id) or (issue_id and not _is_uuid(issue_id)):
        raise _source_invalid()
    doc = db.query(ProjectQuotationDocument.project_id).filter(
        ProjectQuotationDocument.id == doc_id
    ).first()
    if doc is None or not req.project_id or str(doc.project_id) != str(req.project_id):
        raise _source_invalid()
    if issue_id and (
        db.query(ProjectQuotationIssue.id)
        .filter(ProjectQuotationIssue.id == issue_id, ProjectQuotationIssue.document_id == doc_id)
        .first()
        is None
    ):
        raise _source_invalid()


def _check_on_quotation(
    db: Session, req: SampleRequest, product_ids: List[str], kept: frozenset = frozenset()
) -> None:
    """A request with a source quotation carries only that quotation's products (owner, 30 Oct:
    "Sample requests should take the product from the quotation"). Products the request already
    holds (`kept`) may stay, as in `_check_products`: a never-issued quotation that later drops a
    product must not lock the draft that holds it."""
    allowed = quotation_product_ids(db, req.quotation_document_id, req.quotation_issue_id)
    if any(pid not in allowed and pid not in kept for pid in product_ids):
        raise AppException(
            status_code=422,
            message="Every item must be a product on the project's quotation.",
            code="SAMPLE_REQUEST_PRODUCT_NOT_ON_QUOTATION",
            details={"field": "lines"},
        )


# ------------------------------------------------------------------ writes


def _apply(db: Session, req: SampleRequest, data: Dict[str, Any]) -> None:
    """Copy a (partial) payload onto the header and replace the lines when given."""
    data = dict(data)
    lines = data.pop("lines", None)

    _check_refs(db, data)
    line_dicts: List[Dict[str, Any]] = [dict(line) for line in (lines or [])]
    kept = frozenset(str(line.product_id) for line in (req.lines or []) if line.product_id)
    _check_products(db, line_dicts, kept)

    for field in HEADER_TEXT:
        if field in data:
            setattr(req, field, _clean(data[field]))
    for field in (
        "customer_id",
        "project_id",
        "delivery_mode",
        "quotation_document_id",
        "quotation_issue_id",
    ):
        if field in data:
            setattr(req, field, data[field] or None)
    _check_source(db, req)
    if req.quotation_document_id and (
        lines is not None or "quotation_document_id" in data or "quotation_issue_id" in data
    ):
        _check_on_quotation(
            db,
            req,
            [str(line["product_id"]) for line in line_dicts]
            if lines is not None
            else [str(line.product_id) for line in (req.lines or [])],
            kept,
        )
    for field in HEADER_NOT_NULL:
        if data.get(field) is not None:
            setattr(req, field, data[field])
    for field in ("board_mounting",):
        if field in data:
            setattr(req, field, bool(data[field]))
    if "delivery_date" in data:
        req.delivery_date = data["delivery_date"]

    if lines is not None:
        req.lines = [
            SampleRequestLine(
                line_no=index,
                product_id=line["product_id"],
                qty=line.get("qty") or 1,
                remark=_clean(line.get("remark")),
            )
            for index, line in enumerate(line_dicts, start=1)
        ]
    db.flush()


def create_draft(
    db: Session,
    *,
    salesperson_id: Optional[str],
    data: Dict[str, Any],
    source: str,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
) -> SampleRequest:
    req = SampleRequest(
        source=source,
        salesperson_id=salesperson_id,
        contact_id=contact_id,
        space_id=space_id,
        request_date=today_in_malaysia(),
        status_id=_statuses(db)[DRAFT].id,
        loan_value=2,
        loan_unit="months",
        goods_from="either",
        board_mounting=False,
    )
    _apply(db, req, data)
    db.add(req)
    db.flush()
    return req


def update_draft(db: Session, req: SampleRequest, *, actor: Actor, data: Dict[str, Any]) -> None:
    if not is_owner(req, actor):
        raise _forbidden("Only the person who raised this request can edit it.")
    if status_key(db, req) != DRAFT:
        raise AppException(
            status_code=409,
            message="A submitted request cannot be edited. Cancel it and raise a new one.",
            code="SAMPLE_REQUEST_NOT_EDITABLE",
        )
    _apply(db, req, data)


def assert_deletable(db: Session, request_id: str, user_id: Optional[str]) -> SampleRequest:
    """Delete draft: the owner's own Draft, nothing else (403 not yours, 409 not a draft)."""
    req = get_for(db, request_id)
    if not is_owner(req, Actor(user_id=user_id)):
        raise _forbidden("Only the person who raised this request can delete it.")
    if status_key(db, req) != DRAFT:
        raise AppException(
            status_code=409,
            message="Only a draft can be deleted. Cancel a submitted request instead.",
            code="SAMPLE_REQUEST_NOT_DRAFT",
        )
    return req


def delete_draft(db: Session, request_id: str, user_id: Optional[str]) -> None:
    """Hard delete (the lines go with it). Runs when the pending-action window lapses."""
    db.delete(assert_deletable(db, request_id, user_id))
    db.commit()


def update_internal(
    db: Session, req: SampleRequest, *, actor: Actor, consignment_no: Optional[str], po_no: Optional[str]
) -> None:
    if not actor.can_process:
        raise _forbidden("Only the coordinator can fill the internal fields.")
    if status_key(db, req) == CANCELLED:
        raise AppException(
            status_code=409,
            message="A cancelled request cannot be changed.",
            code="SAMPLE_REQUEST_CANCELLED",
        )
    # A linked consignment owns the number (PS-SAMPLE-TRACKING); free text is for the rest.
    if not req.consignment_order_id:
        req.consignment_no = _clean(consignment_no)
    req.po_no = _clean(po_no)
    db.flush()


def _record(
    db: Session,
    req: SampleRequest,
    *,
    actor: Actor,
    label: str,
    template: str = "sample_request_moved",
) -> None:
    """One project activity row per move, when the request has a project (AC-SR-34)."""
    if not req.project_id:
        return
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if project is None:
        return
    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template=template,
        payload={"request_id": str(req.id), "request_no": req.request_no, "status": label},
        actor_id=actor.user_id,
        body_text=f"Sample request {req.request_no}: {label}",
    )


def _label(db: Session, key: str) -> str:
    return _statuses(db)[key].label


def submit(db: Session, req: SampleRequest, *, actor: Actor) -> None:
    if not is_owner(req, actor):
        raise _forbidden("Only the person who raised this request can submit it.")
    frm = status_key(db, req)
    if frm != DRAFT or not _edge_exists(db, frm, SUBMITTED):
        raise illegal_move(frm, SUBMITTED)
    validate_submit(db, req)
    _set_status(db, req, SUBMITTED)
    req.submitted_at = datetime.utcnow()
    db.flush()
    _record(db, req, actor=actor, label=_label(db, SUBMITTED))


def _date_error(code: str, field: str, message: str) -> AppException:
    return AppException(status_code=422, message=message, code=code, details={"field": field})


def _apply_date_answer(
    req: SampleRequest,
    *,
    actor: Actor,
    feasible: Optional[bool],
    proposed: Optional[date],
    note: Optional[str],
) -> None:
    """Rule 2: Yes, or No with a proposed date (today or later). One-way: the salesperson
    sees it, nothing waits for them (owner Q1 a)."""
    if feasible is None:
        raise _date_error(
            "SAMPLE_REQUEST_DATE_ANSWER_REQUIRED",
            "date_feasible",
            "Say whether the requested delivery date can be met.",
        )
    if feasible:
        proposed = None
    elif proposed is None:
        raise _date_error(
            "SAMPLE_REQUEST_PROPOSED_DATE_REQUIRED",
            "proposed_delivery_date",
            "Enter the date the sample team can deliver.",
        )
    elif proposed < today_in_malaysia():
        raise _date_error(
            "SAMPLE_REQUEST_PROPOSED_DATE_PAST",
            "proposed_delivery_date",
            "The proposed date cannot be in the past.",
        )
    req.date_feasible = bool(feasible)
    req.proposed_delivery_date = proposed
    req.date_note = _clean(note)
    req.date_answered_at = datetime.utcnow()
    req.date_answered_by = actor.user_id


def _answer_label(req: SampleRequest) -> str:
    if req.date_feasible:
        return "the sample team can meet the requested date"
    return f"the sample team proposes {req.proposed_delivery_date:%d %b %Y}"


def answer_date(
    db: Session,
    req: SampleRequest,
    *,
    actor: Actor,
    feasible: Optional[bool],
    proposed: Optional[date],
    note: Optional[str],
) -> None:
    """Change the date answer while the request is in Stage 1, after Start processing."""
    if not actor.can_process:
        raise _forbidden("Only the sample team can answer the delivery date.")
    if status_key(db, req) not in DATE_ANSWER_OPEN:
        raise AppException(
            status_code=409,
            message="The delivery date can be answered only while the request is being processed.",
            code="SAMPLE_REQUEST_DATE_ANSWER_CLOSED",
        )
    _apply_date_answer(req, actor=actor, feasible=feasible, proposed=proposed, note=note)
    db.flush()
    _record(db, req, actor=actor, label=_answer_label(req), template="sample_request_date_answered")


def _add_loan(start: date, value: int, unit: str) -> date:
    return start + (relativedelta(months=value) if unit == "months" else relativedelta(days=value))


def move(
    db: Session,
    req: SampleRequest,
    *,
    actor: Actor,
    to: str,
    on: Optional[date] = None,
    reason: Optional[str] = None,
    date_feasible: Optional[bool] = None,
    proposed_delivery_date: Optional[date] = None,
    date_note: Optional[str] = None,
) -> None:
    frm = status_key(db, req)
    if to == CANCELLED and frm in (DRAFT, SUBMITTED):
        allowed = actor.can_process or is_owner(req, actor)
    else:
        allowed = actor.can_process
    if not allowed:
        raise _forbidden("You cannot make this move.")

    # Draft -> Submitted is `submit`, which carries the validation.
    if to == SUBMITTED or not _edge_exists(db, frm, to):
        raise illegal_move(frm, to)

    if to == DELIVERED and req.consignment_order_id:
        raise AppException(
            status_code=409,
            message="This request is delivered by its linked consignment, not by hand.",
            code="SAMPLE_REQUEST_DELIVERED_BY_CONSIGNMENT",
        )

    reason = _clean(reason)
    if to in (CUSTOMER_CONFIRMED, DELIVERED) and on is None:
        raise AppException(
            status_code=422,
            message="Enter the date.",
            code="SAMPLE_REQUEST_DATE_REQUIRED",
            details={"field": "date"},
        )
    if to == CANCELLED and frm == PROCESSING and not reason:
        raise AppException(
            status_code=422,
            message="Enter the reason for cancelling.",
            code="SAMPLE_REQUEST_REASON_REQUIRED",
            details={"field": "reason"},
        )

    # Rule 2: Start processing carries the date answer (submit already requires the date).
    if to == PROCESSING:
        _apply_date_answer(
            req,
            actor=actor,
            feasible=date_feasible,
            proposed=proposed_delivery_date,
            note=date_note,
        )

    _set_status(db, req, to)
    if to == CUSTOMER_CONFIRMED:
        req.confirmed_at = on
    elif to == DELIVERED:
        req.delivered_at = on
        req.return_due = _add_loan(on, req.loan_value, req.loan_unit)
    elif to == CANCELLED:
        req.cancelled_at = datetime.utcnow()
        req.cancel_reason = reason
    db.flush()
    _record(db, req, actor=actor, label=_label(db, to))


# ------------------------------------------------------------------ Stage 2: the consignment

#: Where the sample team may link (or change) the consignment: after Start processing.
CONSIGNMENT_OPEN = (PROCESSING, CUSTOMER_CONFIRMED, DELIVERED)
CONSIGNMENT_CANCELLED = "cancelled"


DELIVERED_BY_TRACKING = "tracking"
DELIVERED_BY_CONSIGNMENT = "consignment"


def consignment_delivery(db: Session, cg) -> Optional[tuple]:
    """THE delivery source: (date, where it came from), or None for a voided / vanished CG.

    Owner, 2 Nov: "The sample delivery document is the consignment." Its delivered date is
    the Overall Tracking `actual_delivery_date` of the `orders` row the tracking import keeps
    under the CG's number (crew b: 375 CGs since 29 Apr carry one, 0-46 days after the CG,
    never before), else the CG's own date (its goods leave at issue, CONSIGN-DELIVERED-FIX).
    The number is matched exactly (case aside) inside the CG's company: it is AutoCount's own
    DocNo on both sides, never a guess."""
    if cg is None or cg.status == CONSIGNMENT_CANCELLED:
        return None
    from app.models.order import Order

    tracked = (
        db.query(Order.actual_delivery_date)
        .filter(
            Order.company_id == cg.company_id,
            func.lower(Order.order_number) == (cg.so_number or "").lower(),
            Order.deleted_at.is_(None),
            Order.is_cancelled.is_(False),
            Order.actual_delivery_date.isnot(None),
        )
        .order_by(Order.actual_delivery_date.asc())
        .first()
    )
    if tracked is not None:
        on = tracked[0]
        return (on.date() if isinstance(on, datetime) else on, DELIVERED_BY_TRACKING)
    if cg.order_date is None:
        return None
    return (cg.order_date, DELIVERED_BY_CONSIGNMENT)


def _consignment_query(db: Session, company_id: str):
    from app.models.order import DOC_TYPE_CONSIGNMENT, SalesOrder

    return db.query(SalesOrder).filter(
        SalesOrder.company_id == company_id,
        SalesOrder.doc_type == DOC_TYPE_CONSIGNMENT,
    )


def _linked_consignment(db: Session, req: SampleRequest):
    if not req.consignment_order_id:
        return None
    from app.models.order import SalesOrder

    return db.query(SalesOrder).filter(SalesOrder.id == req.consignment_order_id).first()


def _deliver_by(db: Session, req: SampleRequest, on: date, *, actor_id: Optional[str], no: str) -> None:
    """Delivered from the consignment: the graph edge is not asked, the CG is the fact."""
    changed = status_key(db, req) != DELIVERED or req.delivered_at != on
    _set_status(db, req, DELIVERED)
    req.delivered_at = on
    req.return_due = _add_loan(on, req.loan_value, req.loan_unit)
    db.flush()
    if changed:
        _record(
            db, req, actor=Actor(user_id=actor_id), label=f"{_label(db, DELIVERED)} by {no}"
        )


def _undeliver(db: Session, req: SampleRequest, *, actor_id: Optional[str], why: str) -> None:
    """Back to the last Stage 1 step it reached (owner Q4 a)."""
    if status_key(db, req) != DELIVERED:
        return
    back = CUSTOMER_CONFIRMED if req.confirmed_at else PROCESSING
    _set_status(db, req, back)
    req.delivered_at = None
    req.return_due = None
    db.flush()
    _record(db, req, actor=Actor(user_id=actor_id), label=f"{_label(db, back)} ({why})")


def search_consignments(
    db: Session, req: SampleRequest, *, actor: Actor, q: str = "", limit: int = 20
) -> List[Dict[str, Any]]:
    """The live consignments of the request's company the sample team can pick from."""
    if not actor.can_process:
        raise _forbidden("Only the sample team can link a consignment.")
    from app.models.order import SalesOrder

    query = _consignment_query(db, req.company_id).filter(
        SalesOrder.status != CONSIGNMENT_CANCELLED
    )
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        query = query.filter(
            or_(
                SalesOrder.so_number.ilike(like),
                SalesOrder.debtor_name.ilike(like),
                SalesOrder.debtor_code.ilike(like),
            )
        )
    rows = (
        query.order_by(SalesOrder.order_date.desc().nulls_last(), SalesOrder.so_number.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "so_number": r.so_number,
            "debtor_code": r.debtor_code,
            "debtor_name": r.debtor_name,
            "order_date": r.order_date,
        }
        for r in rows
    ]


def link_consignment(
    db: Session, req: SampleRequest, *, actor: Actor, consignment_order_id: Optional[str]
) -> None:
    """Link (or, with None, unlink) the consignment that delivers the request."""
    if not actor.can_process:
        raise _forbidden("Only the sample team can link a consignment.")
    if status_key(db, req) not in CONSIGNMENT_OPEN:
        raise AppException(
            status_code=409,
            message="A consignment can be linked once the request is being processed.",
            code="SAMPLE_REQUEST_CONSIGNMENT_CLOSED",
        )
    if consignment_order_id is None:
        if req.consignment_order_id:
            req.consignment_order_id = None
            req.consignment_no = None
            _undeliver(db, req, actor_id=actor.user_id, why="consignment unlinked")
        db.flush()
        return

    from app.models.order import SalesOrder

    cg = (
        _consignment_query(db, req.company_id)
        .filter(SalesOrder.id == consignment_order_id)
        .first()
        if _is_uuid(consignment_order_id)
        else None
    )
    delivery = consignment_delivery(db, cg)
    if delivery is None:
        raise AppException(
            status_code=422,
            message="Choose a live AutoCount consignment of this company.",
            code="SAMPLE_REQUEST_CONSIGNMENT_INVALID",
            details={"field": "consignment_order_id"},
        )
    req.consignment_order_id = cg.id
    req.consignment_no = cg.so_number
    _deliver_by(db, req, delivery[0], actor_id=actor.user_id, no=cg.so_number)


def _resync(db: Session, req: SampleRequest, cg) -> None:
    if status_key(db, req) == CANCELLED:
        return
    delivery = consignment_delivery(db, cg)
    if delivery is None:
        _undeliver(db, req, actor_id=None, why=f"{cg.so_number} voided")
    else:
        _deliver_by(db, req, delivery[0], actor_id=None, no=cg.so_number)


def sync_consignment(db: Session, company_id: str, so_number: str) -> int:
    """Re-read every request linked to this CG after the consignment ingest wrote it: a voided
    or vanished CG undoes the delivery, a live (or restored) one delivers. Returns how many
    requests it looked at. Called by `AutocountCancelIngestService._project_consignment`."""
    from app.models.order import SalesOrder

    cg = _consignment_query(db, company_id).filter(SalesOrder.so_number == so_number).first()
    if cg is None:
        return 0
    reqs = db.query(SampleRequest).filter(SampleRequest.consignment_order_id == cg.id).all()
    for req in reqs:
        _resync(db, req, cg)
    return len(reqs)


def sync_tracked_orders(db: Session, orders: Iterable[Any]) -> int:
    """After the order tracking import wrote `orders`, refresh the delivered date of every
    request whose linked CG carries one of those numbers (a tracking date that lands after the
    link replaces the CG date). Returns how many requests it looked at."""
    from app.models.order import SalesOrder

    keys = {
        (str(o.company_id), (o.order_number or "").lower())
        for o in orders
        if getattr(o, "order_number", None) and getattr(o, "company_id", None)
    }
    if not keys:
        return 0
    numbers = {number for _, number in keys}
    linked = (
        db.query(SampleRequest, SalesOrder)
        .join(SalesOrder, SalesOrder.id == SampleRequest.consignment_order_id)
        .filter(func.lower(SalesOrder.so_number).in_(numbers))
        .all()
    )
    count = 0
    for req, cg in linked:
        if (str(cg.company_id), (cg.so_number or "").lower()) not in keys:
            continue
        _resync(db, req, cg)
        count += 1
    return count


# ------------------------------------------------------------------ reads


def get_for(db: Session, request_id: str, *, contact_id: Optional[str] = None) -> SampleRequest:
    q = db.query(SampleRequest).filter(SampleRequest.id == request_id)
    if contact_id is not None:
        q = q.filter(SampleRequest.contact_id == contact_id)
    req = q.first() if _is_uuid(request_id) else None
    if req is None:
        raise handle_not_found("Sample request", request_id)
    return req


def _folded(column):
    return func.upper(func.regexp_replace(column, "[^A-Za-z0-9]", "", "g"))


def search_products(
    db: Session, q: str, limit: int = 20, product_ids: Optional[set] = None
) -> List[Dict[str, Any]]:
    """Active products whose code (dashes, spaces, case ignored) or name matches. The
    search only LISTS products; a person always picks one (card rule 5).

    ``product_ids`` (a request's source quotation, SFQ-27) narrows the search to those products,
    and an empty search then lists them all so a phone user can pick without typing."""
    text = (q or "").strip()
    if not text and product_ids is None:
        return []
    query = (
        db.query(Product, Brand.brand_name)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .filter(Product.is_active.is_(True))
    )
    if product_ids is not None:
        query = query.filter(Product.id.in_(list(product_ids) or [None]))
        limit = max(limit, len(product_ids))
    if text:
        clauses = [Product.product_name.ilike(f"%{text}%")]
        folded = "".join(ch for ch in text if ch.isalnum()).upper()
        if folded:
            clauses.append(_folded(Product.product_code).like(f"%{folded}%"))
        query = query.filter(or_(*clauses))
    rows = query.order_by(Product.product_code).limit(limit).all()
    return [
        {
            "id": p.id,
            "product_code": p.product_code,
            "product_name": p.product_name,
            "brand_name": brand_name,
        }
        for p, brand_name in rows
    ]


# ------------------------------------------------------------------ quotation pre-fill


def quotation_label(document_no: str, issue_no: Optional[int]) -> str:
    """How a source quotation reads to a person: `<document no> (R2)` or `(not issued)`."""
    return f"{document_no} (R{issue_no})" if issue_no else f"{document_no} (not issued)"


def _quotation_items(
    db: Session, document_id: str, issue_id: Optional[str]
) -> List[tuple]:
    """Every item of one quotation document, in quotation order, as ``(product id or None, what a
    person would recognise the line by)``: the versions its ``issue_id`` holds, or each scope's
    current version when it was never issued; a set line gives its frozen parts."""
    from app.models.projects import (
        ProjectQuotation,
        ProjectQuotationIssueScope,
        ProjectQuotationLine,
        ProjectQuotationVersion,
    )

    if issue_id:
        version_ids = [
            v
            for (v,) in db.query(ProjectQuotationIssueScope.version_id)
            .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationIssueScope.quotation_id)
            .filter(ProjectQuotationIssueScope.issue_id == issue_id)
            .order_by(ProjectQuotation.sort_order, ProjectQuotation.created_at)
            .all()
        ]
    else:
        current = (
            db.query(
                ProjectQuotationVersion.quotation_id,
                func.max(ProjectQuotationVersion.version_no).label("no"),
            )
            .group_by(ProjectQuotationVersion.quotation_id)
            .subquery()
        )
        version_ids = [
            v
            for (v,) in db.query(ProjectQuotationVersion.id)
            .join(ProjectQuotation, ProjectQuotation.id == ProjectQuotationVersion.quotation_id)
            .join(
                current,
                (current.c.quotation_id == ProjectQuotationVersion.quotation_id)
                & (current.c.no == ProjectQuotationVersion.version_no),
            )
            .filter(ProjectQuotation.document_id == document_id)
            .order_by(ProjectQuotation.sort_order, ProjectQuotation.created_at)
            .all()
        ]
    if not version_ids:
        return []

    position = {str(v): i for i, v in enumerate(version_ids)}
    quote_lines = sorted(
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id.in_(version_ids))
        .all(),
        key=lambda l: (position[str(l.version_id)], l.sort_order, l.created_at),
    )
    # (product id or None, what a person would recognise the line by)
    wanted: List[tuple] = []
    for line in quote_lines:
        if line.product_id:
            wanted.append((str(line.product_id), line.product_code_snapshot))
        elif line.set_parts_snapshot:
            for part in line.set_parts_snapshot:
                wanted.append((part.get("product_id"), part.get("product_code")))
        else:
            text = line.description_snapshot or line.product_code_snapshot or ""
            wanted.append((None, " ".join(text.split())))
    return wanted


def quotation_product_ids(db: Session, document_id: str, issue_id: Optional[str]) -> set:
    """The catalogue products a sample request with this source may carry (SFQ-28)."""
    return {
        str(pid) for pid, _ in _quotation_items(db, document_id, issue_id) if pid and _is_uuid(pid)
    }


def source_quotation(
    db: Session, document_id: Optional[str], issue_id: Optional[str]
) -> Optional[str]:
    """The project of a source quotation named by a client (search filter), after checking the
    issue is that document's; None when no source is named. 422 when it does not hold."""
    from app.models.projects import ProjectQuotationDocument, ProjectQuotationIssue

    if not document_id and not issue_id:
        return None
    if not document_id or not _is_uuid(document_id) or (issue_id and not _is_uuid(issue_id)):
        raise _source_invalid()
    project_id = (
        db.query(ProjectQuotationDocument.project_id)
        .filter(ProjectQuotationDocument.id == document_id)
        .scalar()
    )
    if project_id is None:
        raise _source_invalid()
    if issue_id and (
        db.query(ProjectQuotationIssue.id)
        .filter(ProjectQuotationIssue.id == issue_id, ProjectQuotationIssue.document_id == document_id)
        .first()
        is None
    ):
        raise _source_invalid()
    return str(project_id)


def quotation_prefill(
    db: Session, project_id: Optional[str], document_id: Optional[str] = None
) -> Dict[str, Any]:
    """The rows a new sample request starts with (SAMPLE-FROM-QUOTE, SFQ-1..9).

    One quotation document: the one asked for, else the most recently issued, else the newest.
    An issued document gives the lines of the version each scope had IN its latest issue (what
    the customer holds, not the working copy); a never-issued one gives each scope's current
    version. A set line gives its frozen parts. Each product once, in quotation order; a line
    with no product, or an inactive one, is reported in `skipped` instead. No prices.
    """
    from app.models.projects import ProjectQuotationDocument, ProjectQuotationIssue

    _check_refs(db, {"project_id": project_id})
    result: Dict[str, Any] = {
        "documents": [],
        "document_id": None,
        "issue_id": None,
        "lines": [],
        "skipped": [],
    }
    if not project_id:
        return result

    docs = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project_id)
        .all()
    )
    latest: Dict[str, Any] = {}
    if docs:
        for issue in (
            db.query(ProjectQuotationIssue)
            .filter(ProjectQuotationIssue.document_id.in_([d.id for d in docs]))
            .order_by(ProjectQuotationIssue.issue_no)
            .all()
        ):
            latest[str(issue.document_id)] = issue
    # Newest first; the document number breaks a tie (documents made in one transaction share a
    # timestamp, and numbers only grow).
    issued = sorted(
        (d for d in docs if str(d.id) in latest),
        key=lambda d: (latest[str(d.id)].issued_at, d.document_no),
        reverse=True,
    )
    drafts = sorted(
        (d for d in docs if str(d.id) not in latest),
        key=lambda d: (d.created_at, d.document_no),
        reverse=True,
    )
    ordered = issued + drafts
    result["documents"] = [
        {
            "id": d.id,
            "document_no": d.document_no,
            "issue_id": latest[str(d.id)].id if str(d.id) in latest else None,
            "issue_no": latest[str(d.id)].issue_no if str(d.id) in latest else None,
            "label": quotation_label(
                d.document_no, latest[str(d.id)].issue_no if str(d.id) in latest else None
            ),
        }
        for d in ordered
    ]
    if document_id:
        chosen = next((d for d in ordered if str(d.id) == str(document_id)), None)
        if chosen is None:
            raise _source_invalid()
    elif ordered:
        chosen = ordered[0]
    else:
        return result
    issue = latest.get(str(chosen.id))
    result["document_id"] = chosen.id
    result["issue_id"] = issue.id if issue else None

    wanted = _quotation_items(db, chosen.id, issue.id if issue else None)
    if not wanted:
        return result

    ids = {pid for pid, _ in wanted if pid and _is_uuid(pid)}
    products = {
        str(p.id): (p, brand_name)
        for p, brand_name in db.query(Product, Brand.brand_name)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .filter(Product.id.in_(ids or [None]))
        .all()
    }
    seen: set = set()
    for pid, described in wanted:
        found = products.get(str(pid)) if pid else None
        if found is None:
            result["skipped"].append({"reason": "no_product", "description": described or ""})
            continue
        if pid in seen:
            continue
        seen.add(pid)
        product, brand_name = found
        if not product.is_active:
            result["skipped"].append({"reason": "inactive", "description": product.product_code})
            continue
        result["lines"].append(
            {
                "product_id": product.id,
                "product_code": product.product_code,
                "product_name": product.product_name,
                "brand_name": brand_name,
            }
        )
    return result


LIST_SORTS = {
    "request_no": SampleRequest.request_no,
    "request_date": SampleRequest.request_date,
    # The Delivery date column shows the team's proposed date when it has one (rule 3), so it
    # sorts by that.
    "delivery_date": func.coalesce(SampleRequest.proposed_delivery_date, SampleRequest.delivery_date),
    "submitted_at": SampleRequest.submitted_at,
    # The debtor's name when there is one, else the typed name (set in `list_for`).
    "customer_name": None,
    "ship_to_name": SampleRequest.ship_to_name,
    # Every column of the list sorts (PORTAL-P4-REQUESTS P4-23): each orders by what it shows.
    "status": select(Status.sort_order).where(Status.id == SampleRequest.status_id).scalar_subquery(),
    "project_name": func.coalesce(
        select(Project.title).where(Project.id == SampleRequest.project_id).scalar_subquery(),
        SampleRequest.project_title,
    ),
    "delivery_mode": SampleRequest.delivery_mode,
    "salesperson_name": select(User.name).where(User.id == SampleRequest.salesperson_id).scalar_subquery(),
}


def list_for(
    db: Session,
    *,
    actor: Actor,
    statuses: Optional[List[str]] = None,
    stages: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    salesperson_id: Optional[str | Sequence[str]] = None,
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    sort: Optional[str] = None,
    direction: str = "asc",
) -> Dict[str, Any]:
    """One page of list rows. `contact_id` is the portal's own-rows filter; staff without
    `.view` see only the rows they own."""
    from app.models.order import Customer

    query = db.query(SampleRequest).outerjoin(Customer, Customer.id == SampleRequest.customer_id)
    if contact_id is not None:
        query = query.filter(SampleRequest.contact_id == contact_id)
    elif not actor.can_view_all:
        mine = SampleRequest.salesperson_id == actor.user_id
        if actor.own_contact_id:
            mine = or_(mine, SampleRequest.contact_id == actor.own_contact_id)
        query = query.filter(mine)
    if project_id:
        query = query.filter(SampleRequest.project_id == project_id)
    salespeople = multi_values(salesperson_id)
    if salespeople:
        query = query.filter(SampleRequest.salesperson_id.in_(salespeople))
    if statuses:
        ids = [s.id for k, s in _statuses(db).items() if k in statuses]
        query = query.filter(SampleRequest.status_id.in_(ids))
    if stages:
        keys = stage_keys(stages)
        ids = [s.id for k, s in _statuses(db).items() if k in keys]
        query = query.filter(SampleRequest.status_id.in_(ids))
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        query = (
            query.outerjoin(Project, Project.id == SampleRequest.project_id)
            .filter(
                or_(
                    SampleRequest.request_no.ilike(like),
                    SampleRequest.customer_name.ilike(like),
                    SampleRequest.project_title.ilike(like),
                    SampleRequest.ship_to_name.ilike(like),
                    Customer.customer_name.ilike(like),
                    Customer.customer_code.ilike(like),
                    Project.title.ilike(like),
                    Project.project_code.ilike(like),
                )
            )
        )

    total = query.with_entities(func.count(SampleRequest.id)).scalar() or 0

    column = LIST_SORTS.get(sort or "")
    if sort == "customer_name":
        column = func.coalesce(Customer.customer_name, SampleRequest.customer_name)
    if column is not None:
        ordered = column.desc() if direction == "desc" else column.asc()
        query = query.order_by(ordered.nulls_last(), SampleRequest.request_no.asc())
    else:
        # The needed date, soonest first.
        query = query.order_by(
            LIST_SORTS["delivery_date"].asc().nulls_last(),
            SampleRequest.request_no.asc(),
        )
    rows = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "data": serialize_rows(db, rows),
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def _names(db: Session, reqs: List[SampleRequest]) -> Dict[str, Dict[str, Any]]:
    from app.models.order import Customer

    cust_ids = {r.customer_id for r in reqs if r.customer_id}
    proj_ids = {r.project_id for r in reqs if r.project_id}
    user_ids = {r.salesperson_id for r in reqs if r.salesperson_id}
    customers = (
        {c.id: c for c in db.query(Customer).filter(Customer.id.in_(cust_ids)).all()}
        if cust_ids
        else {}
    )
    projects = (
        {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        if proj_ids
        else {}
    )
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    )
    labels = {s.id: (s.key, s.label) for s in _statuses(db).values()}
    return {"customers": customers, "projects": projects, "users": users, "labels": labels}


def _row_common(req: SampleRequest, ctx: Dict[str, Any]) -> Dict[str, Any]:
    customer = ctx["customers"].get(req.customer_id) if req.customer_id else None
    project = ctx["projects"].get(req.project_id) if req.project_id else None
    user = ctx["users"].get(req.salesperson_id) if req.salesperson_id else None
    key, label = ctx["labels"].get(req.status_id, (None, None))
    return {
        "id": req.id,
        "request_no": req.request_no,
        "status": key,
        "status_label": label,
        "request_date": req.request_date,
        "submitted_at": req.submitted_at,
        "delivery_date": req.delivery_date,
        "delivery_mode": req.delivery_mode,
        "customer_name": customer.customer_name if customer else req.customer_name,
        "customer_code": customer.customer_code if customer else None,
        "project_id": req.project_id,
        "project_name": project.title if project else req.project_title,
        "ship_to_name": req.ship_to_name,
        "salesperson_name": (user.name if user else None),
        "board_mounting": bool(req.board_mounting),
        "stage": stage_for(key),
        "date_feasible": req.date_feasible,
        "proposed_delivery_date": req.proposed_delivery_date,
    }


def serialize_rows(db: Session, reqs: List[SampleRequest]) -> List[Dict[str, Any]]:
    """List rows. NEVER the site contact phone or the ship-to address (AC-SR-54)."""
    if not reqs:
        return []
    ctx = _names(db, reqs)
    counts = dict(
        db.query(SampleRequestLine.request_id, func.count(SampleRequestLine.id))
        .filter(SampleRequestLine.request_id.in_([r.id for r in reqs]))
        .group_by(SampleRequestLine.request_id)
        .all()
    )
    out = []
    for req in reqs:
        row = _row_common(req, ctx)
        row["line_count"] = int(counts.get(req.id, 0))
        out.append(row)
    return out


def _source_ref(db: Session, req: SampleRequest) -> Optional[str]:
    from app.models.projects import ProjectQuotationDocument, ProjectQuotationIssue

    if not req.quotation_document_id:
        return None
    doc_no = (
        db.query(ProjectQuotationDocument.document_no)
        .filter(ProjectQuotationDocument.id == req.quotation_document_id)
        .scalar()
    )
    if doc_no is None:
        return None
    issue_no = (
        db.query(ProjectQuotationIssue.issue_no)
        .filter(ProjectQuotationIssue.id == req.quotation_issue_id)
        .scalar()
        if req.quotation_issue_id
        else None
    )
    return quotation_label(doc_no, issue_no)


def _consignment_block(db: Session, req: SampleRequest) -> Optional[Dict[str, Any]]:
    cg = _linked_consignment(db, req)
    if cg is None:
        return None
    delivery = consignment_delivery(db, cg)
    return {
        "id": cg.id,
        "so_number": cg.so_number,
        "order_date": cg.order_date,
        "status": cg.status,
        "delivered_on": delivery[0] if delivery else None,
        "delivered_source": delivery[1] if delivery else None,
    }


def _user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    return db.query(User.name).filter(User.id == user_id).scalar()


def serialize_detail(db: Session, req: SampleRequest) -> Dict[str, Any]:
    ctx = _names(db, [req])
    project = ctx["projects"].get(req.project_id) if req.project_id else None
    row = _row_common(req, ctx)

    line_rows = (
        db.query(SampleRequestLine, Product, Brand.brand_name)
        .join(Product, Product.id == SampleRequestLine.product_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .filter(SampleRequestLine.request_id == req.id)
        .order_by(SampleRequestLine.line_no)
        .all()
    )
    lines = [
        {
            "id": line.id,
            "line_no": line.line_no,
            "product_id": line.product_id,
            "product_code": product.product_code,
            "product_name": product.product_name,
            "brand_name": brand_name,
            "product_active": bool(product.is_active),
            "qty": line.qty,
            "remark": line.remark,
        }
        for line, product, brand_name in line_rows
    ]
    row.update(
        {
            "source": req.source,
            "salesperson_id": req.salesperson_id,
            "customer_id": req.customer_id,
            "project_title": req.project_title,
            "project_code": project.project_code if project else None,
            "quotation_document_id": req.quotation_document_id,
            "quotation_issue_id": req.quotation_issue_id,
            "quotation_ref": _source_ref(db, req),
            "scope_note": req.scope_note,
            "ship_to_address": req.ship_to_address,
            "site_contact_name": req.site_contact_name,
            "site_contact_phone": req.site_contact_phone,
            "site_contact_note": req.site_contact_note,
            "loan_value": req.loan_value,
            "loan_unit": req.loan_unit,
            "goods_from": req.goods_from,
            "purpose": req.purpose,
            "board_label": req.board_label,
            "confirmed_at": req.confirmed_at,
            "delivered_at": req.delivered_at,
            "return_due": req.return_due,
            "cancelled_at": req.cancelled_at,
            "cancel_reason": req.cancel_reason,
            "consignment": _consignment_block(db, req),
            "date_note": req.date_note,
            "date_answered_at": req.date_answered_at,
            "date_answered_by_name": _user_name(db, req.date_answered_by),
            "consignment_no": req.consignment_no,
            "po_no": req.po_no,
            "created_at": req.created_at,
            "updated_at": req.updated_at,
            "lines": lines,
        }
    )
    return row


def render_pdf(db: Session, req: SampleRequest) -> bytes:
    from app.services.pdf_render import PDFRenderingUnavailable, render_html
    from app.services.sample_request_pdf_service import build_html

    try:
        return render_html(build_html(serialize_detail(db, req)))
    except PDFRenderingUnavailable as exc:
        raise AppException(status_code=503, message=str(exc), code="PDF_UNAVAILABLE")
