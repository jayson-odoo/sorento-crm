"""PORTAL-P4-REQUESTS S4 + S6 red tests: the STAFF routes of Sample Request and Sales Opportunity for a
salesperson (`view_own`, never `view`): only their own rows, every status; every staff write refused.
Staff (`view`) behave as before (control).
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import (  # noqa: F401
    SO_PORTAL,
    SO_STAFF,
    SR,
    SR_CREATE,
    SR_PORTAL,
    SR_PROCESS,
    SR_VIEW,
    scene,
    so_row,
    sr_row,
    world,
)


def _sr(api, w, **over):
    return s.ok(api.call("POST", SR_PORTAL, json=w.sr_body(**over)), 201).json()["id"]


def _so(api, w):
    return s.ok(api.call("POST", SO_PORTAL, json=w.so_body()), 201).json()["id"]


def test_p4_sr_staff_list_shows_every_status_of_their_own_rows_and_nothing_foreign(world):
    w = world
    draft = _sr(w.rep.portal, w)
    submitted = _sr(w.rep.portal, w)
    s.ok(w.rep.portal.call("POST", f"{SR_PORTAL}/{submitted}/submit"))
    cancelled = _sr(w.rep.portal, w)
    s.ok(w.rep.portal.call("POST", f"{SR_PORTAL}/{cancelled}/cancel"))
    foreign = _sr(w.other.portal, w)
    listed = s.ok(w.staff(w.rep.actor, "GET", SR)).json()
    got = {r["id"] for r in listed["data"]}
    assert got == {draft, submitted, cancelled}, f"foreign={foreign in got}; default open-only list hides draft/cancelled"
    portal_ids = {r["id"] for r in s.ok(w.rep.portal.call("GET", SR_PORTAL)).json()["data"]}
    assert got == portal_ids
    # an explicit status filter still narrows
    only = s.ok(w.staff(w.rep.actor, "GET", SR, params={"status": "cancelled"})).json()
    assert {r["id"] for r in only["data"]} == {cancelled}


def test_p4_sr_staff_user_default_list_is_unchanged_open_statuses_only(world):
    w = world
    draft = _sr(w.rep.portal, w)
    submitted = _sr(w.rep.portal, w)
    s.ok(w.rep.portal.call("POST", f"{SR_PORTAL}/{submitted}/submit"))
    staff = s.make_user(w.sc.db, perms=[SR_VIEW, SR_CREATE], name="ZZT Staff")
    got = {r["id"] for r in s.ok(w.staff(staff, "GET", SR)).json()["data"]}
    assert submitted in got and draft not in got


def test_p4_sr_staff_detail_foreign_is_404_own_is_200(world):
    w = world
    own, foreign = _sr(w.rep.portal, w), _sr(w.other.portal, w)
    assert s.ok(w.staff(w.rep.actor, "GET", f"{SR}/{own}")).json()["id"] == own
    r = w.staff(w.rep.actor, "GET", f"{SR}/{foreign}")
    assert r.status_code == 404, r.text
    s.not_a_missing_route(r)


def test_p4_sr_staff_write_routes_refuse_a_salesperson(world):
    w = world
    own = _sr(w.rep.portal, w)
    before = sr_row(w, own).status_id
    calls = [
        ("POST", SR, w.sr_body()),
        ("PUT", f"{SR}/{own}", w.sr_body()),
        ("POST", f"{SR}/{own}/submit", None),
        ("POST", f"{SR}/{own}/move", {"to": "cancelled"}),
        ("PUT", f"{SR}/{own}/internal", {"consignment_no": "C1", "po_no": "P1"}),
    ]
    for method, path, body in calls:
        r = w.staff(w.rep.actor, method, path, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        s.not_a_missing_route(r)
    assert sr_row(w, own).status_id == before
    from app.models.sample_request import SampleRequest

    assert w.sc.db.query(SampleRequest).filter(SampleRequest.contact_id == w.rep.contact.id).count() == 1


def test_p4_sr_staff_create_is_unchanged_for_a_create_holder(world):
    w = world
    staff = s.make_user(w.sc.db, perms=[SR_VIEW, SR_CREATE], name="ZZT Staff")
    r = w.staff(staff, "POST", SR, json=w.sr_body())
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "staff"


def test_p4_so_staff_list_and_detail_only_own_agents_rows(world):
    w = world
    own, foreign = _so(w.rep.portal, w), _so(w.other.portal, w)
    got = {r["id"] for r in s.ok(w.staff(w.rep.actor, "GET", SO_STAFF)).json()["data"]}
    assert got == {own}
    assert w.staff(w.rep.actor, "GET", f"{SO_STAFF}/{own}").status_code == 200
    r = w.staff(w.rep.actor, "GET", f"{SO_STAFF}/{foreign}")
    assert r.status_code == 404, r.text
    s.not_a_missing_route(r)


def test_p4_so_staff_write_routes_refuse_a_salesperson(world):
    w = world
    own = _so(w.rep.portal, w)
    title = so_row(w, own).title
    calls = [
        ("POST", SO_STAFF, w.so_body()),
        ("PATCH", f"{SO_STAFF}/{own}", {"title": "ZZT staff edit"}),
        ("DELETE", f"{SO_STAFF}/{own}", None),
        ("GET", f"{SO_STAFF}/agent-options", None),
        ("GET", f"{SO_STAFF}/{own}/sales-order-options", None),
    ]
    for method, path, body in calls:
        r = w.staff(w.rep.actor, method, path, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        s.not_a_missing_route(r)
    assert so_row(w, own).title == title


def test_p4_so_staff_writes_are_unchanged_for_a_view_holder(world):
    w = world
    staff = s.make_user(
        w.sc.db, perms=["sales.opportunities.view", "sales.opportunities.add", "sales.opportunities.edit"], name="ZZT Staff"
    )
    created = w.staff(staff, "POST", SO_STAFF, json=w.so_body(sales_agent_id=w.rep.agent.id))
    assert created.status_code == 201, created.text
    patched = w.staff(staff, "PATCH", f"{SO_STAFF}/{created.json()['id']}", json={"title": "ZZT staff edit"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "ZZT staff edit"
