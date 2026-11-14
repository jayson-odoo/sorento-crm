"""WA-COMPLAINT-INTAKE round 6 (should-fix 2, review 3): ONE non-staff rule.

A dealer's own CRM user (role `portal_user` only, created by the WhatsApp assistant) is not staff, and a
trashed staff role makes no one staff. `user_service.holds_staff_role` / `only_non_staff_roles` is the
rule; `contact_grant._is_staff` and `contact_asker.is_staff_user` read it.

Postgres only, through the blank schema; every test seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest

# Import order (R7 S2): `writes` first. Importing `contact_grant` cold loops through
# writes -> contact_tags -> contact_grant and fails with an ImportError when this file runs alone.
import app.main  # noqa: F401  register every model and the app's listeners
from app.services.chatbot.agent import writes  # noqa: F401
from app.models.user import User, UserRole, UserRoleAssignment
from app.services import reference_seed
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact


@pytest.fixture()
def db():
    with blank_session() as session:
        reference_seed.seed_roles(session)
        yield session


def _trashed_staff_role(db) -> str:
    role = UserRole(id=str(uuid.uuid4()), slug=unique_code("staff").lower(), name=unique_code("Staff"),
                    is_trashed=True)
    db.add(role)
    db.flush()
    return role.slug


def _user(db, contact_pk: str, phone: str, *role_slugs: str) -> str:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('u').lower()}@zzt.test", name="ZZT User",
                status="ACTIVE", contact_number=phone, respond_contact_id=contact_pk)
    db.add(user)
    db.flush()
    for slug in role_slugs:
        role = db.query(UserRole).filter(UserRole.slug == slug).one()
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    db.flush()
    return user.id


def _phone() -> str:
    return "601" + str(uuid.uuid4().int % 10**9).zfill(9)


CASES = {
    "portal_user_only": (("portal_user",), False),
    "portal_user_and_a_trashed_staff_role": (("portal_user", "TRASHED"), False),
    "salesperson": (("salesperson",), True),
    "salesperson_and_portal_user": (("salesperson", "portal_user"), True),
}


def _roles(db, names):
    return [_trashed_staff_role(db) if n == "TRASHED" else n for n in names]


@pytest.mark.parametrize("case", sorted(CASES))
def test_contact_grant_is_staff_follows_the_one_rule(db, case):
    from app.services.chatbot.agent.contact_grant import _is_staff

    names, staff = CASES[case]
    contact = seed_contact(db)
    phone = _phone()
    _user(db, contact["pk"], phone, *_roles(db, names))
    assert _is_staff(db, "+" + phone, contact["pk"]) is staff
    # By phone alone (no contact row yet), the same answer.
    assert _is_staff(db, "+" + phone, None) is staff


@pytest.mark.parametrize("case", sorted(CASES))
def test_contact_asker_is_staff_user_follows_the_one_rule(db, case):
    from app.services.contact_asker import is_staff_user

    names, staff = CASES[case]
    contact = seed_contact(db)
    _user(db, contact["pk"], _phone(), *_roles(db, names))
    assert is_staff_user(db, contact["pk"]) is staff
