"""PORTAL-P4-REQUESTS S8: green pins - a salesperson's home stays /my-requests (a redirect route).

The "favourite" portal form is a browser-local star (localStorage `sorento.portalDefaultTab.<contact_id>`);
nothing server side stores it, so the backend home is the Stock Inquiry staff list and the favourite is
applied client side. Every other principal keeps today's home (green pins). Postgres only, rows seeded here.
"""
from __future__ import annotations

import pytest

from tests._pg_fixture import blank_session
from tests.test_portal_p3_role_menu import _chain, _home, _slug, _user

@pytest.mark.parametrize("roles", [["salesperson"], ["salesperson", "portal_user"]])
def test_s8_salesperson_home_stays_my_requests(roles):
    # /my-requests is a pure redirect route now; the favourite star is browser-local (owner P3 Q1).
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, roles, contact=contact)
        assert _home(db, user) == "/my-requests"


def test_s8_contact_without_crm_user_keeps_the_portal_home():
    with blank_session() as db:
        _, contact = _chain(db)
        slug = _slug(db, contact)
        user = _user(db, ["portal_user"], contact=contact)
        assert _home(db, user) == f"/portal/c/{slug}"


def test_s8_mixed_salesperson_plus_staff_role_keeps_todays_home():
    with blank_session() as db:
        _, contact = _chain(db)
        slug = _slug(db, contact)
        user = _user(db, ["salesperson", "purchasing"], contact=contact)
        assert _home(db, user) == f"/portal/c/{slug}"


def test_s8_staff_lands_on_crm_root():
    with blank_session() as db:
        user = _user(db, ["purchasing"])
        assert _home(db, user) == "/"
