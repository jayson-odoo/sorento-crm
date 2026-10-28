"""Own-records read scope ("only theirs", PORTAL-P2-ONLY-THEIRS).

A user is LIMITED in a module when they hold its ``view_own`` and not its ``view``.
Admin and superadmin are never limited: ``get_user_permission_slugs`` hands them every
slug, ``view`` included. A user holding both behaves as ``view``. Nobody else is touched.

"Me" is the user id, the WhatsApp contact the user is linked to
(``users.respond_contact_id``) and the active sales agents linked to that contact, the
same agent rule the portal answers by (``sales.portal_agent.agents_for_contact``). A user
with no linked contact has no agents, so only the rows keyed on their user id are theirs.

One filter per model, each a plain SQL clause so lists filter in the query and a detail
read asks the same question for one id:

- projects: owner, approved collaborator, or a portal registration by their contact;
- opportunities: the sales agent is one of theirs;
- sample requests: the salesperson is them, or the portal contact is theirs;
- new product applications: the applicant is them, or the portal contact is theirs;
- conversations: contacts linked to their agents' customers (the portal Conversations rule);
- the four request forms (PORTAL-P4-REQUESTS, ``REQUEST_KINDS``): the row's ``contact_id`` is
  their contact, the portal's own rule. A requestor named on someone else's row does not count,
  and the space is not matched;
- sample requests and opportunities as MY REQUESTS forms (``MODULE_REQUEST_KINDS``): the module
  rule above, so the staff page shows exactly what the portal shows them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

PROJECTS_VIEW = "projects.projects.view"
PROJECTS_VIEW_OWN = "projects.projects.view_own"
OPPORTUNITIES_VIEW = "sales.opportunities.view"
OPPORTUNITIES_VIEW_OWN = "sales.opportunities.view_own"
SAMPLE_REQUESTS_VIEW = "projects.sample_requests.view"
SAMPLE_REQUESTS_VIEW_OWN = "projects.sample_requests.view_own"
NPA_VIEW = "procurement.new_product_applications.view"
NPA_VIEW_OWN = "procurement.new_product_applications.view_own"
CONVERSATIONS_VIEW = "sla_management.conversations.view"
CONVERSATIONS_VIEW_OWN = "sla_management.conversations.view_own"

#: Request form kind -> (view, view_own). Purchase requests and sponsorship forms share one
#: table and one staff router; the row's ``request_type`` is its kind.
REQUEST_KINDS = {
    "stock_inquiry": ("procurement.stock_inquiries.view", "procurement.stock_inquiries.view_own"),
    "complaint": (
        "complaint_management.complaints.view",
        "complaint_management.complaints.view_own",
    ),
    "purchase_request": (
        "procurement.purchase_requests.view",
        "procurement.purchase_requests.view_own",
    ),
    "sponsorship_form": (
        "procurement.sponsorship_forms.view",
        "procurement.sponsorship_forms.view_own",
    ),
}


#: The MY REQUESTS forms with a staff router of their own that a salesperson writes through that
#: form's own portal router (PORTAL-P4-REQUESTS S4, S6): kind -> (view, view_own). Their rows are
#: theirs by the module rule (``sample_request_clause``, ``opportunity_clause``), which already
#: narrows the staff reads (PORTAL-P2-ONLY-THEIRS).
MODULE_REQUEST_KINDS = {
    "sample_request": (SAMPLE_REQUESTS_VIEW, SAMPLE_REQUESTS_VIEW_OWN),
    "sales_opportunity": (OPPORTUNITIES_VIEW, OPPORTUNITIES_VIEW_OWN),
}


def is_limited(perms: Iterable[str], view: str, view_own: str) -> bool:
    slugs = set(perms or ())
    return view_own in slugs and view not in slugs


def user_is_limited(db: Session, user_id: str, view: str, view_own: str) -> bool:
    from app.services.user_service import UserPermissionService

    return is_limited(UserPermissionService(db).get_user_permission_slugs(user_id), view, view_own)


@dataclass(frozen=True)
class Me:
    user_id: str
    contact_id: Optional[str]
    agent_ids: Tuple[str, ...]


def me(db: Session, user_id: str) -> Me:
    from app.models.user import User
    from app.services.sales.portal_agent import agents_for_contact

    contact_id = db.query(User.respond_contact_id).filter(User.id == str(user_id)).scalar()
    agents = agents_for_contact(db, contact_id) if contact_id else []
    return Me(
        user_id=str(user_id),
        contact_id=str(contact_id) if contact_id else None,
        agent_ids=tuple(str(a.id) for a in agents),
    )


# ------------------------------------------------------------------ projects


def project_clause(m: Me):
    from app.models.projects import Project, ProjectCollaborator, ProjectSalesProfile

    conditions = [
        Project.owner_user_id == m.user_id,
        Project.id.in_(
            select(ProjectCollaborator.project_id).where(ProjectCollaborator.user_id == m.user_id)
        ),
    ]
    if m.contact_id:
        conditions.append(
            Project.id.in_(
                select(ProjectSalesProfile.project_id).where(
                    ProjectSalesProfile.contact_id == m.contact_id
                )
            )
        )
    return or_(*conditions)


def project_in_scope(db: Session, m: Me, project_id: Optional[str]) -> bool:
    from app.models.projects import Project

    import uuid

    try:
        uuid.UUID(str(project_id))
    except (TypeError, ValueError):
        # Never compared to the uuid column: the cast error would abort the transaction.
        return False
    return (
        db.query(Project.id).filter(Project.id == str(project_id), project_clause(m)).first()
        is not None
    )


# ------------------------------------------------------------------ the other modules


def opportunity_clause(m: Me):
    from app.models.sales import SalesOpportunity

    if not m.agent_ids:
        return false()
    return SalesOpportunity.sales_agent_id.in_(list(m.agent_ids))


def sample_request_clause(m: Me):
    from app.models.sample_request import SampleRequest

    conditions = [SampleRequest.salesperson_id == m.user_id]
    if m.contact_id:
        conditions.append(SampleRequest.contact_id == m.contact_id)
    return or_(*conditions)


def npa_clause(m: Me):
    from app.models.new_product_application import NewProductApplication

    conditions = [NewProductApplication.applicant_id == m.user_id]
    if m.contact_id:
        conditions.append(NewProductApplication.contact_id == m.contact_id)
    return or_(*conditions)


def conversation_contact_ids(m: Me):
    """``respond_contacts.id`` of every contact linked to one of their agents' customers,
    as a subquery; empty without agents."""
    from app.services.portal_conversation_service import agent_contact_ids

    return agent_contact_ids(list(m.agent_ids))


# ------------------------------------------------------------------ request forms


def request_access(perms: Iterable[str], kind: str) -> Optional[str]:
    """``"all"`` with the kind's ``view``, ``"own"`` with only its ``view_own``, else None.
    ``kind`` is one of ``REQUEST_KINDS`` or ``MODULE_REQUEST_KINDS``."""
    view, view_own = REQUEST_KINDS.get(kind) or MODULE_REQUEST_KINDS[kind]
    slugs = set(perms or ())
    if view in slugs:
        return "all"
    return "own" if view_own in slugs else None


def _request_model(kind: str):
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry

    if kind == "stock_inquiry":
        return StockInquiry
    if kind == "complaint":
        return Complaint
    return PurchaseRequestHeader


def request_clause(model, m: Me):
    """Rows of a request form that are theirs: submitted by their contact. No contact, none."""
    if not m.contact_id:
        return false()
    return model.contact_id == m.contact_id


def request_in_scope(db: Session, kind: str, row_id: Optional[str], m: Me) -> bool:
    """Is this row of ``kind`` theirs? A sponsorship form is not a purchase request."""
    import uuid

    try:
        uuid.UUID(str(row_id))
    except (TypeError, ValueError):
        # Never compared to the uuid column: the cast error would abort the transaction.
        return False
    model = _request_model(kind)
    q = db.query(model.id).filter(model.id == str(row_id), request_clause(model, m))
    if model.__tablename__ == "purchase_requests":
        q = q.filter(model.request_type == kind)
    return q.first() is not None


def module_row_in_scope(db: Session, kind: str, row_id: Optional[str], m: Me) -> bool:
    """Is this row of a ``MODULE_REQUEST_KINDS`` kind theirs, by that module's rule?"""
    import uuid

    from app.models.sales import SalesOpportunity
    from app.models.sample_request import SampleRequest

    try:
        uuid.UUID(str(row_id))
    except (TypeError, ValueError):
        # Never compared to the uuid column: the cast error would abort the transaction.
        return False
    if kind == "sample_request":
        model, clause = SampleRequest, sample_request_clause(m)
    else:
        model, clause = SalesOpportunity, opportunity_clause(m)
    return db.query(model.id).filter(model.id == str(row_id), clause).first() is not None


# ------------------------------------------------------------------ deferred actions

#: Deferred actions on project-sales records that the router guard refuses a limited user on
#: the route itself (sales-order line files). Fulfilment planning's undo confirm is not here:
#: it follows its own permission slug (owner ruling Q2, 27 Oct).
_PROJECT_ACTIONS_REFUSED = frozenset({"sales_order_line_attachment.delete"})


def assert_pending_action_allowed(
    db: Session, action_key: str, entity_id: str, actor_id: Optional[str]
) -> None:
    """A deferred action is a write that never passes the record's own routes, so the
    "only theirs" rule is repeated here: at park time and again when the window lapses."""
    from app.services.error_handler import AppException, handle_not_found

    if not actor_id:
        return
    if action_key == "sales_opportunity.delete":
        if not user_is_limited(db, actor_id, OPPORTUNITIES_VIEW, OPPORTUNITIES_VIEW_OWN):
            return
        import uuid

        from app.models.sales import SalesOpportunity

        try:
            uuid.UUID(str(entity_id))
        except (TypeError, ValueError):
            raise handle_not_found("Sales Opportunity", entity_id)
        found = (
            db.query(SalesOpportunity.id)
            .filter(SalesOpportunity.id == str(entity_id), opportunity_clause(me(db, actor_id)))
            .first()
        )
        if found is None:
            raise handle_not_found("Sales Opportunity", entity_id)
    elif action_key in _PROJECT_ACTIONS_REFUSED:
        if user_is_limited(db, actor_id, PROJECTS_VIEW, PROJECTS_VIEW_OWN):
            raise AppException(
                status_code=403,
                message="Not available with access to your own records only.",
                code="FORBIDDEN",
            )
