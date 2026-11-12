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
    #: The record's own page, "{id}" filled in (the assistant's row link); "" = no link.
    screen_path: str = ""
    #: The `value` column is a cost price (`products.cost.view`, SUPPLIER-COST-ACCESS): shown only
    #: to a reader who may see cost, null for everyone else, sorting included.
    value_is_cost: bool = False


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


def _order_change_notice_select(me: Me, access: str):
    from app.models.project_so import OrderChangeNotice as M
    from app.models.user import User
    from app.services import order_change_notice_service as ocn

    raiser = select(User.name).where(User.id == M.created_by).correlate(M).scalar_subquery()
    return _own(
        select(
            literal("order_change_notice", String).label("kind"),
            M.id.label("id"),
            M.ocn_number.label("number"),
            M.status.label("status"),
            M.approval_status.label("approval_status"),
            cast(M.ocn_date, Date).label("date"),
            raiser.label("raised_by"),
            M.description.label("subject"),
            cast(null(), Numeric).label("value"),
        ),
        access,
        ocn.own_clause(me.user_id),
    )


def _register_builtin_types() -> None:
    from app.models.complaints import Complaint
    from app.models.new_product_application import NewProductApplication
    from app.models.procurement import PurchaseRequestHeader, StockInquiry
    from app.models.project_so import OrderChangeNotice

    for rt in (
        RelatedType(
            "stock_inquiry", "Stock Inquiry", "stock_inquiry", StockInquiry, _stock_inquiry_select,
            "/procurement-management/stock-inquiries/{id}",
        ),
        RelatedType(
            "complaint", "Complaint", "complaint", Complaint, _complaint_select,
            "/complaint-management/complaints/{id}",
        ),
        RelatedType(
            "purchase_request", "Purchase request", "purchase_request", PurchaseRequestHeader,
            _request_select("purchase_request", "project_title"),
            "/procurement-management/purchase-requests/{id}",
        ),
        RelatedType(
            "sponsorship_form", "Sponsorship form", "sponsorship_form", PurchaseRequestHeader,
            _request_select("sponsorship_form", "purpose"),
            "/procurement-management/sponsorship-forms/{id}",
        ),
        RelatedType(
            "new_product_application", "New product application", "new_product_application",
            NewProductApplication, _npa_select,
            "/procurement-management/new-product-applications/{id}",
            value_is_cost=True,
        ),
        RelatedType(
            "order_change_notice", "Order change notice", "order_change_notice",
            OrderChangeNotice, _order_change_notice_select,
            "/procurement-management/order-change-notices/{id}",
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


def _value(rows, visible, cost_visible: bool):
    """The value column as this reader may see it: a cost value (`value_is_cost`) is null without
    `products.cost.view`, for the sort as well as the cell."""
    hidden = [rt.kind for rt, _ in visible if rt.value_is_cost]
    if cost_visible or not hidden:
        return rows.c.value
    return case((rows.c.kind.in_(hidden), null()), else_=rows.c.value)


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
    cost_visible: bool = False,
) -> Dict[str, Any]:
    """One UNION ALL of the visible types' linked rows, filtered, sorted and paged in SQL.

    `type_counts` ignores the type, status and search filters (the tab badge); a type the
    viewer may not see is absent from the rows, `type_counts` and `types` alike. `statuses`
    are the raw statuses of those rows (the Status filter's options), also unfiltered. A cost
    value (an NPA's cost price) is null unless `cost_visible` (`cost_access.can_view_cost`).
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
        "statuses": [],
    }
    if not visible:
        return empty

    # One pass over every visible linked row: the per-type counts (the tab badge) and the
    # statuses the Status filter offers, both with no filter applied.
    every = union_all(*[_linked(rt, me, access, project_id) for rt, access in visible]).subquery("related")
    type_counts: Dict[str, int] = {}
    status_set = set()
    for kind, status, n in db.execute(
        select(every.c.kind, every.c.status, func.count()).group_by(every.c.kind, every.c.status)
    ).all():
        type_counts[kind] = type_counts.get(kind, 0) + int(n)
        if status:
            status_set.add(status)
    statuses_out = sorted(status_set)

    wanted = [(rt, access) for rt, access in visible if not types or rt.kind in set(types)]
    if not wanted:
        return {**empty, "type_counts": type_counts, "statuses": statuses_out}
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
    value = _value(rows, wanted, cost_visible)
    if sort == "type":
        key = case(labels, value=rows.c.kind, else_=rows.c.kind)
    elif sort == "value":
        key = value
    else:
        key = rows.c[_SORT_COLUMN[sort]]
    ordered = key.asc() if direction == "asc" else key.desc()
    tie = rows.c.number.asc() if direction == "asc" else rows.c.number.desc()
    result = db.execute(
        select(*[c for c in rows.c if c.key != "value"], value.label("value"))
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
        "statuses": statuses_out,
    }


# ------------------------------------------------------------------ the assistant


def assistant_rows(db: Session, user_id: str, own_only: bool, _date_from, _date_to, *, limit: int) -> List[dict]:
    """The assistant's `project_related_record` rows (PROJECT-RELATED-RECORDS AC-E1): every record
    linked to a project this user may read, under the same per-type rules as the Related tab, with
    the project's code and title so "what is linked to PS26-0001" filters on them. `own_only` =
    the user holds only `projects.projects.view_own`: their own projects (`own_scope.project_clause`).
    Newest first; no date window (a project's records span years)."""
    from app.models.base import get_company_scope
    from app.models.projects import Project
    from app.services.company_scope import build_company_predicate
    from app.services.cost_access import can_view_cost
    from app.services.user_service import UserPermissionService

    me = own_scope.me(db, user_id)
    visible = visible_types(UserPermissionService(db).get_user_permission_slugs(user_id))
    if not visible:
        return []
    company = build_company_predicate(Project, get_company_scope(db))
    selects = []
    for rt, access in visible:
        sel = (
            rt.select(me, access)
            .join(Project, Project.id == rt.model.project_id)
            .add_columns(Project.project_code.label("project_code"), Project.title.label("project_title"))
        )
        if company is not None:
            sel = sel.where(company)
        if own_only:
            sel = sel.where(own_scope.project_clause(me))
        selects.append(sel)
    rows = union_all(*selects).subquery("linked")
    value = _value(rows, visible, can_view_cost(db, user_id))
    result = db.execute(
        select(*[c for c in rows.c if c.key != "value"], value.label("value"))
        .order_by(rows.c.date.desc().nulls_last(), rows.c.number, rows.c.id)
        .limit(limit)
    ).mappings().all()
    types = {rt.kind: rt for rt, _ in visible}
    out = []
    for r in result:
        rt = types.get(r["kind"])
        out.append({
            "id": str(r["id"]),
            "path": rt.screen_path.format(id=r["id"]) if rt and rt.screen_path else "",
            "type": rt.label if rt else r["kind"],
            "number": r["number"],
            "status": r["status"],
            "approval_status": r["approval_status"],
            "date": r["date"],
            "raised_by": r["raised_by"],
            "subject": r["subject"],
            "value": r["value"],
            "project_code": r["project_code"],
            "project_title": r["project_title"],
        })
    return out


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


def assert_can_set_project(db: Session, kinds, user_id: str, record=None) -> None:
    """403 unless the user holds the edit permission of one of `kinds` (a kind, or the kinds a
    route serves before it knows which one the row is, so a refusal never says whether the row
    exists). An NPA is also the applicant's to edit (`new_product_application_service.update`),
    or an admin's: pass the loaded `record` for that half."""
    from app.services.error_handler import AppException
    from app.services.user_service import UserPermissionService

    kinds = (kinds,) if isinstance(kinds, str) else tuple(kinds)
    service = UserPermissionService(db)
    if not any(service.check_user_has_permission(user_id, EDIT_PERMISSION[k]) for k in kinds):
        slug = " or ".join(EDIT_PERMISSION[k] for k in kinds)
        raise AppException(status_code=403, message=f"Permission required: {slug}", code="FORBIDDEN")
    if record is not None and kinds == ("new_product_application",):
        from app.services import new_product_application_service as npa

        admin = service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}
        if not admin and not npa.is_owner(record, npa.Actor(user_id=str(user_id))):
            raise AppException(
                status_code=403,
                message="Only the applicant can change this application's project.",
                code="FORBIDDEN",
            )


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
