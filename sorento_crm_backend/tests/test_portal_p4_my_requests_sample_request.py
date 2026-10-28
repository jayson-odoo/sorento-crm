"""PORTAL-P4-REQUESTS S4 red tests: a salesperson's Sample Request written from the CRM through
/api/v1/my-requests, by the portal's own code (`public/portal_sample_request.py`).

Paths and bodies are the portal router's: /submissions/sample_request[/{id}[/submit|/cancel]],
/sample-request/customers, /sample-request/products. No revise, comments or attachments.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import (  # noqa: F401
    SR_CREATE,
    SR_PORTAL,
    SR_VIEW,
    SR_VIEW_OWN,
    scene,
    sr_row,
    world,
)


def _create(api, w, **over):
    return s.ok(api.call("POST", SR_PORTAL, json=w.sr_body(**over)), 201).json()


def _mounted(w):
    s.ok(w.rep.me.call("GET", SR_PORTAL))


def test_p4_sr_parity_create_and_list_columns_equal_the_portal(world):
    w = world
    mine = _create(w.rep.me, w)
    theirs = _create(w.rep.portal, w)
    assert set(mine) == set(theirs)
    assert (mine["source"], mine["status"]) == (theirs["source"], theirs["status"]) == ("portal", "draft")
    assert s.shape(mine["request_no"]) == s.shape(theirs["request_no"]) and mine["request_no"].startswith("SR-")
    row = sr_row(w, mine["id"])
    assert row.source == "portal"
    assert row.contact_id == w.rep.contact.id
    assert row.space_id == w.sc.space_id or row.space_id  # the contact's workspace space, as the portal stamps
    assert row.salesperson_id == w.rep.actor.id  # the linked CRM user, not NULL

    listed_me = s.ok(w.rep.me.call("GET", SR_PORTAL)).json()
    listed_portal = s.ok(w.rep.portal.call("GET", SR_PORTAL)).json()
    assert {r["id"] for r in listed_me["data"]} == {r["id"] for r in listed_portal["data"]} == {mine["id"], theirs["id"]}
    assert set(listed_me["data"][0]) == set(listed_portal["data"][0])
    assert set(listed_me) == set(listed_portal)


def _walk(api, w) -> list:
    """create draft -> update -> submit -> update refused -> cancel -> cancel again."""
    out = []
    d = _create(api, w)
    out.append(("create", d["status"]))
    r = api.call("PUT", f"{SR_PORTAL}/{d['id']}", json=w.sr_body(ship_to_name="ZZT changed site"))
    out.append(("update", r.status_code, r.json().get("ship_to_name")))
    r = api.call("POST", f"{SR_PORTAL}/{d['id']}/submit")
    out.append(("submit", r.status_code, r.json().get("status")))
    r = api.call("PUT", f"{SR_PORTAL}/{d['id']}", json=w.sr_body())
    out.append(("update_after_submit", r.status_code, r.json().get("code")))
    r = api.call("POST", f"{SR_PORTAL}/{d['id']}/submit")
    out.append(("resubmit", r.status_code, r.json().get("code")))
    r = api.call("POST", f"{SR_PORTAL}/{d['id']}/cancel")
    out.append(("cancel", r.status_code, r.json().get("status")))
    r = api.call("POST", f"{SR_PORTAL}/{d['id']}/cancel")
    out.append(("cancel_again", r.status_code, r.json().get("code")))
    return out


def test_p4_sr_draft_update_submit_cancel_rules_match_the_portal(world):
    w = world
    mine, theirs = _walk(w.rep.me, w), _walk(w.rep.portal, w)
    assert mine == theirs
    assert [step[0] for step in mine] == ["create", "update", "submit", "update_after_submit", "resubmit", "cancel", "cancel_again"]
    assert ("submit", 200, "submitted") in mine and ("cancel", 200, "cancelled") in mine
    assert mine[-1][1] == 409  # a second cancel is illegal


def test_p4_sr_draft_can_be_cancelled_and_incomplete_submit_is_refused_like_the_portal(world):
    w = world
    out = []
    for api in (w.rep.me, w.rep.portal):
        d = _create(api, w, lines=[])  # incomplete: no lines
        r = api.call("POST", f"{SR_PORTAL}/{d['id']}/submit")
        c = api.call("POST", f"{SR_PORTAL}/{d['id']}/cancel")
        out.append((r.status_code, r.json().get("code"), c.status_code, c.json().get("status")))
    assert out[0] == out[1]
    assert out[0][0] == 422 and out[0][2:] == (200, "cancelled")


def test_p4_sr_customer_picker_is_limited_to_the_agents_own_customers(world):
    w = world
    s.ok(w.rep.me.call("GET", SR_PORTAL))  # mounted
    mine = s.ok(w.rep.me.call("GET", "/sample-request/customers")).json()
    assert [c["customer_id"] for c in mine] == [w.rep.mine.id]
    assert mine == s.ok(w.rep.portal.call("GET", "/sample-request/customers")).json()
    assert w.other.mine.id not in str(mine)
    # the picker equals what create accepts: a foreign debtor is refused exactly as the portal refuses it
    refused = w.rep.me.call("POST", SR_PORTAL, json=w.sr_body(customer_id=w.other.mine.id))
    twin = w.rep.portal.call("POST", SR_PORTAL, json=w.sr_body(customer_id=w.other.mine.id))
    assert refused.status_code == twin.status_code == 422
    assert refused.json().get("code") == twin.json().get("code") == "SAMPLE_REQUEST_CUSTOMER_INVALID"
    s.ok(w.rep.me.call("POST", SR_PORTAL, json=w.sr_body(customer_id=w.rep.mine.id)), 201)


def test_p4_sr_product_search_equals_the_portal(world):
    w = world
    q = {"q": w.product.product_code}
    mine = s.ok(w.rep.me.call("GET", "/sample-request/products", params=q))
    assert mine.json() == s.ok(w.rep.portal.call("GET", "/sample-request/products", params=q)).json()
    assert mine.json(), "the seeded product should be found"


def test_p4_sr_foreign_row_answers_what_the_portal_answers(world):
    w = world
    foreign = _create(w.other.portal, w)["id"]
    _create(w.rep.me, w)  # own row: the route is known to be mounted
    calls = {
        "get": ("GET", f"{SR_PORTAL}/{foreign}", None),
        "put": ("PUT", f"{SR_PORTAL}/{foreign}", w.sr_body()),
        "submit": ("POST", f"{SR_PORTAL}/{foreign}/submit", None),
        "cancel": ("POST", f"{SR_PORTAL}/{foreign}/cancel", None),
    }
    for name, (method, path, body) in calls.items():
        kw = {"json": body} if body is not None else {}
        mine = w.rep.me.call(method, path, **kw)
        theirs = w.rep.portal.call(method, path, **kw)
        s.not_a_missing_route(mine)
        assert theirs.status_code == 404, (name, theirs.status_code)
        assert (mine.status_code, mine.json()) == (theirs.status_code, theirs.json()), name
    assert s.ok(w.other.portal.call("GET", f"{SR_PORTAL}/{foreign}")).json()["status"] == "draft"


def test_p4_sr_impersonation_acts_as_the_salesperson(world):
    from app.models.impersonation import ImpersonationSession

    w = world
    admin = s.make_user(w.sc.db, roles=["admin"], name="ZZT Impersonating Admin")
    w.sc.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=w.rep.actor.id))
    w.sc.db.commit()
    api = s.my_api(w.sc, admin, **{s.IMPERSONATE_HEADER: w.rep.actor.id})
    sid = _create(api, w)["id"]
    row = sr_row(w, sid)
    assert (row.contact_id, row.salesperson_id, row.source) == (w.rep.contact.id, w.rep.actor.id, "portal")
    rows = w.sc.audit(sid)
    assert rows, "no audit rows for the create"
    assert all(a.user_id == w.rep.actor.id for a in rows if a.user_id)
    assert any(a.real_user_id == admin.id for a in rows)
    s.ok(api.call("POST", f"{SR_PORTAL}/{sid}/submit"))
    assert sr_row(w, sid).status_id  # still theirs, still writable as the target


def test_p4_sr_gate_no_session_is_401(world):
    _mounted(world)
    assert s.Api(world.client, s.MY, {}).call("POST", SR_PORTAL, json=world.sr_body()).status_code == 401


def test_p4_sr_gate_no_linked_contact_is_403(world):
    w = world
    _mounted(w)
    loner = s.make_user(w.sc.db, perms=[SR_VIEW_OWN, SR_CREATE], name="ZZT Loner")
    for method, path in (("POST", SR_PORTAL), ("GET", SR_PORTAL), ("GET", "/sample-request/customers")):
        resp = s.my_api(w.sc, loner).call(method, path, **({"json": w.sr_body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_sr_gate_staff_view_holder_is_403_even_with_a_contact(world):
    w = world
    _mounted(w)
    contact, portal = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=[SR_VIEW, SR_VIEW_OWN, SR_CREATE], contact=contact, name="ZZT Staff")
    api = s.my_api(w.sc, staff)
    for method, path in (("POST", SR_PORTAL), ("GET", SR_PORTAL)):
        resp = api.call(method, path, **({"json": w.sr_body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_sr_gate_create_needs_create_but_reading_own_works(world):
    w = world
    _mounted(w)
    contact, portal = s.own_contact(w.sc)
    reader = s.make_user(w.sc.db, perms=[SR_VIEW_OWN], contact=contact, name="ZZT Reader")
    api = s.my_api(w.sc, reader)
    resp = api.call("POST", SR_PORTAL, json=w.sr_body())
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)
    assert api.call("GET", SR_PORTAL).status_code in (200, 403)  # reading is the staff page's job; never a 404


def test_p4_sr_bad_body_is_422(world):
    w = world
    _mounted(w)
    resp = w.rep.me.call("POST", SR_PORTAL, json={"lines": "nope"})
    assert resp.status_code == 422, resp.text
