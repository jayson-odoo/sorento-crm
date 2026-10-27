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
- conversations: contacts linked to their agents' customers (the portal Conversations rule).
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

    if not project_id:
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
