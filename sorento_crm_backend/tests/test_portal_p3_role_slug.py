"""PORTAL-P3-ROLE-MENU round 3, T7: sign-in leaves a salesperson's contact with its portal slug,
so `GET /users/me` never has to mint it. Staff paths are unchanged (no slug minted for them)."""
from __future__ import annotations

from tests._pg_fixture import blank_session
from tests.test_portal_p3_role_menu import _chain, _home, _user


def test_t7_home_path_for_a_salesperson_leaves_the_contact_with_a_slug():
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, ["salesperson", "portal_user"], contact=contact)
        assert (contact.portal_slug or "") == ""  # seeded without one
        assert _home(db, user) == "/my-requests"
        db.refresh(contact)
        assert (contact.portal_slug or "").strip() != ""


def test_t7_staff_with_a_contact_gets_no_slug_minted_by_home_path():
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, ["admin"], contact=contact)
        assert _home(db, user) == "/"
        db.refresh(contact)
        assert (contact.portal_slug or "") == ""
