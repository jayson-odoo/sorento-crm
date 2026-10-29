"""Who is asking: the one asker rule (CA-3 owner hand test round).

`documentation/plans/chatbot/PLAN-chat-analytics-ca3-chat-dataset-10oct.md`, "one asker rule" and
"Ruling 10 Oct 2026 (owner override, crew)". For a WhatsApp contact the first match of:

    salesperson  an ACTIVE, not trashed CRM user is linked (`users.respond_contact_id`) and holds
                 the role with slug `salesperson`
    staff        any other ACTIVE, not trashed linked user, or an ACTIVE office access type
    salesperson  `sales_agents.contact_id` (reached only when the contact has no active user)
    dealer       a `respond_contact_customers` link
    unclassified none of the above

ONE definition, exposed twice: `sql_expr` for the chat dataset (computed at query time from the
links as they are now, so linking a contact reclassifies its history) and `classify` for the
route, which runs the same expression for one contact. `is_staff_user` (an active user holding
a staff role), not this classification, decides chatbot document access (V1-DOC-SCOPE);
`is_salesperson_user` (the role arm alone) decides whether a `salesperson` asker keeps the chat
report's relaxed scope (`chat_report.asker_of`, V1-CHATREPORT-REVOKE).
Core code: it never imports the chatbot package (tests/chatbot/test_import_boundary.py).
"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

ASKERS = ("dealer", "salesperson", "staff", "unclassified")

#: The office access type names, as `contact_customer_scope._OFFICE_ACCESS_TYPE_RE` reads them.
_OFFICE_SQL = r"^(sorento|cabana|mocha) office$"


def _salesperson_user_clauses(contact_id: Any) -> list:
    """WHERE clauses (over `users`, `user_role_assignments`, `user_roles`) for an ACTIVE, not
    trashed user linked to `contact_id` that holds the non-trashed role slug `salesperson`."""
    from app.models.user import User, UserRole, UserRoleAssignment

    users, roles, assigned = User.__table__, UserRole.__table__, UserRoleAssignment.__table__
    return [
        users.c.respond_contact_id == contact_id,
        users.c.status == "ACTIVE",
        users.c.is_trashed.is_(False),
        assigned.c.user_id == users.c.id,
        assigned.c.role_id == roles.c.id,
        roles.c.slug == "salesperson",
        roles.c.is_trashed.is_(False),
    ]


def salesperson_user_name(contact_respond_id_column: Any) -> Any:
    """The name of the role-salesperson user behind a fact's contact (NULL when there is none)."""
    from app.models.access import RespondContact
    from app.models.user import User

    rc = RespondContact.__table__
    return (
        sa.select(User.__table__.c.name)
        .where(rc.c.respond_io_id == contact_respond_id_column, *_salesperson_user_clauses(rc.c.id))
        .order_by(User.__table__.c.name)
        .limit(1)
        .scalar_subquery()
    )


def _word_for(contact_id: Any) -> Any:
    """CASE over an INTERNAL `respond_contacts.id` expression."""
    from app.models.access import ContactAccessType, RespondContactCustomer, respond_contact_access_types
    from app.models.sales_agent import SalesAgent
    from app.models.user import User

    users = User.__table__
    # A live user only: a trashed or not ACTIVE user's link says nothing about who asks.
    live = [users.c.respond_contact_id == contact_id, users.c.status == "ACTIVE", users.c.is_trashed.is_(False)]
    user_linked = sa.exists().where(*live)
    salesperson_user = sa.exists().where(*_salesperson_user_clauses(contact_id))
    kinds = ContactAccessType.__table__
    held = respond_contact_access_types
    office = sa.exists().where(
        sa.and_(
            held.c.contact_id == contact_id,
            held.c.access_type_code == kinds.c.code,
            kinds.c.is_active.is_(True),
            sa.func.lower(
                sa.func.regexp_replace(sa.func.trim(sa.func.coalesce(kinds.c.name, "")), r"\s+", " ", "g")
            ).op("~")(_OFFICE_SQL),
        )
    )
    agent = sa.exists().where(SalesAgent.__table__.c.contact_id == contact_id)
    dealer = sa.exists().where(RespondContactCustomer.__table__.c.contact_id == contact_id)
    return sa.case(
        (salesperson_user, "salesperson"),
        (sa.or_(user_linked, office), "staff"),
        (agent, "salesperson"),
        (dealer, "dealer"),
        else_="unclassified",
    )


def is_staff_user(db: Session, contact_id: str) -> bool:
    """True when an ACTIVE, not trashed CRM user linked to the contact (INTERNAL
    `respond_contacts.id`) holds at least one not trashed role outside
    `user_service.NON_STAFF_ROLE_SLUGS` (portal_user, guest): the people lookups' own staff
    definition (`user_service._holds_staff_role`), whatever the role. This, not `classify`,
    decides chatbot document access (V1-DOC-SCOPE, owner ruling 16 Oct 2026): deactivating or
    trashing the user revokes it, and a dealer's portal login, a user with no live role, an
    integration (act-as) user or a `sales_agents.contact_id` link (master data) grants nothing."""
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.services.user_service import NON_STAFF_ROLE_SLUGS

    users, roles, assigned = User.__table__, UserRole.__table__, UserRoleAssignment.__table__
    held = sa.exists().where(
        users.c.respond_contact_id == str(contact_id),
        users.c.status == "ACTIVE",
        users.c.is_trashed.is_(False),
        users.c.is_integration.is_(False),
        assigned.c.user_id == users.c.id,
        assigned.c.role_id == roles.c.id,
        roles.c.slug.notin_(NON_STAFF_ROLE_SLUGS),
        roles.c.is_trashed.is_(False),
    )
    return bool(db.execute(sa.select(held)).scalar())


def is_salesperson_user(db: Session, contact_id: str) -> bool:
    """True when an ACTIVE, not trashed CRM user linked to the contact (INTERNAL
    `respond_contacts.id`) holds the not trashed role `salesperson`: the role arm alone.
    `chat_report.asker_of` reads it so a `salesperson` asker keeps the chat report's relaxed
    scope only while such a user is live (V1-CHATREPORT-REVOKE): deactivating or trashing the
    user revokes it, and a `sales_agents.contact_id` link (master data) grants nothing.
    Document access is `is_staff_user`."""
    return bool(db.execute(sa.select(sa.exists().where(*_salesperson_user_clauses(str(contact_id))))).scalar())


def own_book(db: Session, contact_id: str) -> set[str] | None:
    """The customer ids of a contact's own book (INTERNAL `respond_contacts.id`): the customers
    whose card agent is a `sales_agents` row linked to the contact. None when the contact has no
    agent link."""
    from app.models.base import company_scope
    from app.models.order import Customer
    from app.models.sales_agent import SalesAgent

    with company_scope(db, None):
        agent_ids = [str(i) for (i,) in db.query(SalesAgent.id).filter(SalesAgent.contact_id == str(contact_id)).all()]
        if not agent_ids:
            return None
        return {str(i) for (i,) in db.query(Customer.id).filter(Customer.sales_agent_id.in_(agent_ids)).all()}


def may_ask_sales_ranking(db: Session, contact_id: str | None, *, granted: bool) -> tuple[str, set[str] | None]:
    """THE rule for who may run the sales ranking (the report-ask tool), shared by the route and
    the chatbot seams: `granted` (the `sales_orders.sales_report` reveal) or a LIVE salesperson
    user (`is_salesperson_user`) with a non-empty `own_book`. Returns `(decision, book)`:
    `granted`, `salesperson_book` or `not_granted`; `book` is the salesperson's customer set
    (None when the contact is not a live salesperson user or has no agent link), whatever the
    decision, because a granted salesperson with `mine` is narrowed to it too."""
    book = own_book(db, contact_id) if contact_id and is_salesperson_user(db, str(contact_id)) else None
    if granted:
        return "granted", book
    return ("salesperson_book" if book else "not_granted"), book


def pending_delivery_open(db: Session, contact_id: str | None) -> bool:
    """Owner 29 Oct (REPORT-OUTSTANDING-SUMMARY, as before #1922): pending delivery needs no reveal, for a contact the
    company knows: office staff (every customer) or a contact linked to customers (only its own, the route's
    `enforce_customer_scope`). An unlinked, non-staff contact gets nothing without the Outstanding reveal. INTERNAL
    `respond_contacts.id`; False for none (fail closed)."""
    if not contact_id:
        return False
    from app.services import contact_customer_scope as scope_mod

    return scope_mod.is_office_staff(db, str(contact_id)) or scope_mod.contact_customer_scope(db, str(contact_id)).enforced


def classify(db: Session, contact_id: str) -> str:
    """The asker word of one contact (INTERNAL `respond_contacts.id`)."""
    return db.execute(sa.select(_word_for(sa.literal(str(contact_id))))).scalar_one()


def sql_expr(contact_respond_id_column: Any) -> Any:
    """A scalar SQL expression over a fact's `contact_respond_id`: the contact's asker word,
    `unclassified` when no `respond_contacts` row carries that Respond.io id."""
    from app.models.access import RespondContact

    rc = RespondContact.__table__
    inner = (
        sa.select(_word_for(rc.c.id))
        .where(rc.c.respond_io_id == contact_respond_id_column)
        .limit(1)
        .scalar_subquery()
    )
    return sa.func.coalesce(inner, "unclassified")
