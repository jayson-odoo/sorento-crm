"""WA-COMPLAINT-INTAKE D-8 red tests: the dealer keeps its dealer bot.

UAC: documentation/plans/chatbot/wa-complaint-intake-acceptance-criteria.md row D-8. Once the WhatsApp
assistant creates a dealer's own CRM user (role `portal_user` only, D-3), that contact must still run
in the agent as a CONTACT principal (`agent/access.py` `linked_active_user` / `build_context`): today's
dealer tools, knowledge audience (access codes) and scope, exactly as an unlinked dealer. A linked
user with ANY staff role (e.g. `salesperson` + `portal_user`) stays a user principal, unchanged.

Postgres only, through the blank schema; every test seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.services import reference_seed
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_contact, seed_user

SUBMIT = "ideation.ideas.submit"


@pytest.fixture()
def db():
    with blank_session() as session:
        reference_seed.seed_roles(session)
        # As D-1 leaves it: portal_user holds the submit slug and nothing else.
        portal = session.query(UserRole).filter(UserRole.slug == "portal_user").one()
        perm = session.query(UserPermission).filter(UserPermission.slug == SUBMIT).first()
        if perm is None:
            perm = UserPermission(id=str(uuid.uuid4()), slug=SUBMIT, name=SUBMIT)
            session.add(perm)
            session.flush()
        session.add(UserRolePermission(id=str(uuid.uuid4()), role_id=portal.id, permission_id=perm.id))
        session.flush()
        yield session


def _with_roles(db, contact_pk: str, *role_slugs: str) -> str:
    user_id = seed_user(db, contact_pk=contact_pk)
    for slug in role_slugs:
        role = db.query(UserRole).filter(UserRole.slug == slug).one()
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user_id, role_id=role.id))
    db.flush()
    return user_id


def _give_codes(db, contact_pk: str, *codes: str) -> None:
    from app.models.access import ContactAccessType, respond_contact_access_types

    for code in codes:
        if db.get(ContactAccessType, code) is None:
            db.add(ContactAccessType(code=code, name=f"ZZT {code}", is_active=True))
    db.flush()
    for code in codes:
        db.execute(respond_contact_access_types.insert().values(contact_id=contact_pk, access_type_code=code))
    db.flush()


@pytest.mark.parametrize("roles", [("portal_user",), ("guest",), ("portal_user", "guest")])
def test_D8_a_contact_linked_to_an_all_non_staff_user_stays_a_contact_principal(db, roles):
    from app.services.chatbot.agent.access import build_context, eligible_contact

    dealer = seed_contact(db)
    _give_codes(db, dealer["pk"], "dealer")
    _with_roles(db, dealer["pk"], *roles)
    # The same dealer with no CRM user at all: what the linked one must look like.
    unlinked = seed_contact(db)
    _give_codes(db, unlinked["pk"], "dealer")

    assert eligible_contact(db, dealer["respond_id"])[2] is None
    ctx = build_context(db, dealer["respond_id"])
    baseline = build_context(db, unlinked["respond_id"])

    assert ctx.principal == "contact"
    assert ctx.user_id == "" and ctx.user_name == ""
    assert ctx.contact_pk == dealer["pk"]
    assert ctx.access_codes == frozenset({"dealer"}), "the knowledge audience is the contact's own codes"
    assert ctx.tool_names == baseline.tool_names, "today's dealer tools, as an unlinked dealer"
    assert ctx.arg_permissions == ()


def test_D8_a_contact_linked_to_a_salesperson_portal_user_is_still_a_user_principal(db):
    from app.services.chatbot.agent.access import build_context, eligible_contact

    contact = seed_contact(db)
    user_id = _with_roles(db, contact["pk"], "salesperson", "portal_user")

    _, user, refusal = eligible_contact(db, contact["respond_id"])
    ctx = build_context(db, contact["respond_id"])

    assert refusal is None and str(user.id) == user_id
    assert ctx.principal == "user"
    assert ctx.user_id == user_id
    assert ctx.access_codes == frozenset()
