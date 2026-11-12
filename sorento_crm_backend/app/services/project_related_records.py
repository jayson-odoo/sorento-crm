"""The records linked to a project (PROJECT-RELATED-RECORDS).

Five record types carry a nullable `project_id`: stock inquiries, complaints, purchase
requests, sponsorship forms (the same table as purchase requests) and new product
applications. The project page lists them in one grid (`list_related_records`), and every
type lets a person set or change the link at any time (`set_record_project`, owner D2).

A type is ONE `register_related_type` call (AC-D1): its label, the `own_scope` access kind
that decides who may see its rows, its model and a `select` of the nine labelled columns.
The list function adds the project filter itself, so a type's `select` never has to.

Contract: documentation/plans/project-sales/CONTRACT-project-related-records.md (5, 6, 3).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy import Date, Numeric, String, case, cast, func, literal, null, or_, select, union_all
from sqlalchemy.orm import Session

from app.services import own_scope
from app.services.own_scope import Me

#: The grid's sort keys -> the union column they order by ("type" orders by the label).
SORT_KEYS = ("type", "number", "status", "approval", "date", "raised_by", "subject", "value")
_SORT_COLUMN = {
    "number": "number",
    "status": "status",
    "approval": "approval_status",
    "date": "date",
    "raised_by": "raised_by",
    "subject": "subject",
    "value": "value",
}


@dataclass(frozen=True)
class RelatedType:
    kind: str
    label: str
    #: The key `own_scope.request_access` reads (`REQUEST_KINDS` / `MODULE_REQUEST_KINDS`).
    access_kind: str
    #: The SQLAlchemy model; it carries `project_id`.
    model: Any
    #: (me, access) -> a select of kind, id, number, status, approval_status, date, raised_by,
    #: subject, value. With access "own" it narrows to the viewer's own rows.
    select: Callable[[Me, str], Any]


RELATED_TYPES: "OrderedDict[str, RelatedType]" = OrderedDict()


def register_related_type(rt: RelatedType) -> None:
    RELATED_TYPES[rt.kind] = rt


# ------------------------------------------------------------------ the five types


def _own(select_, access: str, clause):
    return select_.where(clause) if access == "own" else select_


def _stock_inquiry_select(me: Me, access: str):
    from app.models.procurement import StockInquiry as M

    return _own(
        select(
            literal("stock_inquiry", String).label("kind"),
            M.id.label("id"),
            M.inquiry_number.label("number"),
            M.status.label("status"),
            cast(null(), String).label("approval_status"),
            cast(M.created_at, Date).label("date"),
            M.salesperson.label("raised_by"),
            M.item_description.label("subject"),
            cast(null(), Numeric).label("value"),
        ),
        access,
        own_scope.request_clause(M, me),
    )


def _complaint_select(me: Me, access: str):
    from app.models.complaints import Complaint as M

    return _own(
        select(
            literal("complaint", String).label("kind"),
            M.id.label("id"),
            M.complaint_number.label("number"),
            M.status.label("status"),
            cast(null(), String).label("approval_status"),
            cast(M.complaint_date, Date).label("date"),
            M.salesperson.label("raised_by"),
            M.defect_description.label("subject"),
            cast(null(), Numeric).label("value"),
        ),
        access,
        own_scope.request_clause(M, me),
    )


def _request_select(kind: str, subject_column: str):
    def build(me: Me, access: str):
        from app.models.procurement import PurchaseRequestHeader as M

        return _own(
            select(
                literal(kind, String).label("kind"),
                M.id.label("id"),
                M.request_number.label("number"),
                M.status.label("status"),
                M.approval_status.label("approval_status"),
                cast(M.request_date, Date).label("date"),
                M.requested_by.label("raised_by"),
                getattr(M, subject_column).label("subject"),
                M.total_project_value.label("value"),
            ).where(M.request_type == kind),
            access,
            own_scope.request_clause(M, me),
        )

    return build


def _npa_select(me: Me, access: str):
    from app.models.new_product_application import NewProductApplication as M
    from app.models.user import User

    applicant = select(User.name).where(User.id == M.applicant_id).correlate(M).scalar_subquery()
    return _own(
        select(
            literal("new_product_application", String).label("kind"),
            M.id.label("id"),
            M.application_no.label("number"),
            M.status.label("status"),
            cast(null(), String).label("approval_status"),
            cast(func.coalesce(M.submitted_at, M.created_at), Date).label("date"),
            applicant.label("raised_by"),
            M.remark.label("subject"),
            M.cost_price.label("value"),
        ),
        access,
        own_scope.npa_clause(me),
    )


def _register_builtin_types() -> None:
    from app.models.complaints import Complaint
    from app.models.new_product_application import NewProductApplication
    from app.models.procurement import PurchaseRequestHeader, StockInquiry

    for rt in (
        RelatedType("stock_inquiry", "Stock Inquiry", "stock_inquiry", StockInquiry, _stock_inquiry_select),
        RelatedType("complaint", "Complaint", "complaint", Complaint, _complaint_select),
        RelatedType(
            "purchase_request", "Purchase request", "purchase_request", PurchaseRequestHeader,
            _request_select("purchase_request", "project_title"),
        ),
        RelatedType(
            "sponsorship_form", "Sponsorship form", "sponsorship_form", PurchaseRequestHeader,
            _request_select("sponsorship_form", "purpose"),
        ),
        RelatedType(
            "new_product_application", "New product application", "new_product_application",
            NewProductApplication, _npa_select,
        ),
    ):
        register_related_type(rt)


_register_builtin_types()


# ------------------------------------------------------------------ the list


def visible_types(perms: Iterable[str]) -> List[tuple]:
    """`(RelatedType, access)` for every type the viewer may see, in registry order."""
    slugs = set(perms or ())
    out = []
    for rt in list(RELATED_TYPES.values()):
        access = own_scope.request_access(slugs, rt.access_kind)
        if access is not None:
            out.append((rt, access))
    return out


def _linked(rt: RelatedType, me: Me, access: str, project_id: str):
    return rt.select(me, access).where(rt.model.project_id == str(project_id))


def list_related_records(
    db: Session,
    *,
    project_id: str,
    perms: Iterable[str],
    me: Me,
    types: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    query: Optional[str] = None,
    sort: str = "date",
    direction: str = "desc",
    page: int = 1,
    limit: int = 25,
) -> Dict[str, Any]:
    """One UNION ALL of the visible types' linked rows, filtered, sorted and paged in SQL.

    `type_counts` ignores the type, status and search filters (the tab badge); a type the
    viewer may not see is absent from the rows, `type_counts` and `types` alike.
    """
    visible = visible_types(perms)
    labels = {rt.kind: rt.label for rt, _ in visible}
    types_out = [{"kind": rt.kind, "label": rt.label} for rt, _ in visible]
    empty = {
        "data": [],
        "pagination": {"total": 0, "page": page, "limit": limit},
        "empty": True,
        "type_counts": {},
        "types": types_out,
    }
    if not visible:
        return empty

    every = union_all(*[_linked(rt, me, access, project_id) for rt, access in visible]).subquery("related")
    type_counts = {
        kind: int(n)
        for kind, n in db.execute(select(every.c.kind, func.count()).group_by(every.c.kind)).all()
    }

    wanted = [(rt, access) for rt, access in visible if not types or rt.kind in set(types)]
    if not wanted:
        return {**empty, "type_counts": type_counts}
    rows = union_all(*[_linked(rt, me, access, project_id) for rt, access in wanted]).subquery("rows")
    conditions = []
    if statuses:
        conditions.append(rows.c.status.in_(list(statuses)))
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        conditions.append(
            or_(rows.c.number.ilike(like), rows.c.subject.ilike(like), rows.c.raised_by.ilike(like))
        )

    total = db.execute(select(func.count()).select_from(rows).where(*conditions)).scalar() or 0
    if sort == "type":
        key = case(labels, value=rows.c.kind, else_=rows.c.kind)
    else:
        key = rows.c[_SORT_COLUMN[sort]]
    ordered = key.asc() if direction == "asc" else key.desc()
    tie = rows.c.number.asc() if direction == "asc" else rows.c.number.desc()
    result = db.execute(
        select(rows)
        .where(*conditions)
        .order_by(ordered.nulls_last(), tie.nulls_last(), rows.c.id)
        .offset((page - 1) * limit)
        .limit(limit)
    ).mappings().all()
    data = [
        {
            "kind": r["kind"],
            "id": str(r["id"]),
            "number": r["number"],
            "status": r["status"],
            "approval_status": r["approval_status"],
            "date": r["date"],
            "raised_by": r["raised_by"],
            "subject": r["subject"],
            "value": r["value"],
        }
        for r in result
    ]
    return {
        "data": data,
        "pagination": {"total": int(total), "page": page, "limit": limit},
        "empty": not data,
        "type_counts": type_counts,
        "types": types_out,
    }


# ------------------------------------------------------------------ set the link (D2)

#: The EXISTING permission that lets a person edit a record of each kind (no new slug).
EDIT_PERMISSION = {
    "stock_inquiry": "procurement.stock_inquiries.edit",
    "complaint": "complaint_management.complaints.edit",
    "purchase_request": "procurement.purchase_requests.edit",
    "sponsorship_form": "procurement.sponsorship_forms.edit",
    "new_product_application": "procurement.new_product_applications.create",
}

_RECORD_WORD = {
    "stock_inquiry": "Stock Inquiry",
    "complaint": "Complaint",
    "purchase_request": "Request",
    "sponsorship_form": "Request",
    "new_product_application": "New product application",
}


def assert_can_set_project(db: Session, kind: str, user_id: str) -> None:
    """403 unless the user holds the kind's edit permission (admin and superadmin do)."""
    from app.services.error_handler import AppException
    from app.services.user_service import UserPermissionService

    slug = EDIT_PERMISSION[kind]
    if not UserPermissionService(db).check_user_has_permission(user_id, slug):
        raise AppException(status_code=403, message=f"Permission required: {slug}", code="FORBIDDEN")


def get_record(db: Session, kind: str, record_id: str):
    """The record of `kind`, or 404. A sponsorship form is not a purchase request."""
    import uuid

    from app.services.error_handler import handle_not_found

    model = RELATED_TYPES[kind].model
    try:
        uuid.UUID(str(record_id))
    except (TypeError, ValueError):
        raise handle_not_found(_RECORD_WORD.get(kind, "Record"), record_id)
    q = db.query(model).filter(model.id == str(record_id))
    if hasattr(model, "request_type"):
        q = q.filter(model.request_type == kind)
    row = q.first()
    if row is None:
        raise handle_not_found(_RECORD_WORD.get(kind, "Record"), record_id)
    return row


def set_record_project(
    db: Session, *, kind: str, record_id: str, project_id: Optional[str], actor: Optional[str]
):
    """Set (or clear) a record's project at any status, closed and approved included (D2).

    Writes only `project_id`: status and approval never move, and the change reaches the
    record's History through the existing audit listeners (old -> new). The project must be
    an approved one (`assert_linkable_project`); re-saving the current link is not a change.
    `actor` is the user id the History names when no request has stamped one (the review
    script).
    """
    from app.audit_context import AuditActor, actor_scope, get_actor
    from app.services.project_service import assert_linkable_project

    row = get_record(db, kind, record_id)
    project_id = str(project_id) if project_id else None
    assert_linkable_project(db, project_id, row.project_id, code=f"{kind}_project_not_approved")
    if str(row.project_id or "") == str(project_id or ""):
        return row
    row.project_id = project_id
    if actor and get_actor(db) is None:
        with actor_scope(AuditActor(actor_type="user", user_id=str(actor), real_user_id=str(actor)), db=db):
            db.flush()
    else:
        db.flush()
    return row
