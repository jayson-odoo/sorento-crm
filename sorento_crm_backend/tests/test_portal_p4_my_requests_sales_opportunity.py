"""PORTAL-P4-REQUESTS S6 red tests: a salesperson's Sales Opportunity written from the CRM through
/api/v1/my-requests, by the portal's own code (`public/portal_sales_opportunity.py`).

Paths and bodies are the portal router's: /sales-opportunities[/{id}], /sales-opportunities/meta,
/sales-opportunities/customer-options. No draft, no submit.
"""
from __future__ import annotations

from app.models.order import Customer
from app.models.status import Status
from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import (  # noqa: F401
    SO_ADD,
    SO_EDIT,
    SO_PORTAL,
    SO_VIEW,
    SO_VIEW_OWN,
    scene,
    so_row,
    world,
)


def _create(api, w, **over):
    return s.ok(api.call("POST", SO_PORTAL, json=w.so_body(**over)), 201).json()


def _stage(w, key) -> str:
    return w.sc.db.query(Status).filter(Status.entity_type == "sales_opportunity", Status.key == key).one().id


def test_p4_so_create_parity_and_stamps(world):
    w = world
    mine = _create(w.rep.me, w)
    theirs = _create(w.rep.portal, w)
    assert set(mine) == set(theirs)
    assert (mine["source"], mine["stage_key"]) == (theirs["source"], theirs["stage_key"]) == ("portal", "new")
    assert mine["created_by_contact_id"] == w.rep.contact.id
    assert mine["sales_agent_id"] == w.rep.agent.id
    assert so_row(w, mine["id"]).source == "portal"
    listed = s.ok(w.rep.me.call("GET", SO_PORTAL)).json()
    assert {i["id"] for i in listed["items"]} == {mine["id"], theirs["id"]}
    assert set(listed["items"][0]) == set(s.ok(w.rep.portal.call("GET", SO_PORTAL)).json()["items"][0])


def test_p4_so_a_prospect_gets_the_portals_default_agent_and_the_body_agent_is_ignored(world):
    w = world
    second = w.person("Second", agent_code=f"ZZA-Z-{s.uid()[:6]}".upper())
    # link the second agent to the rep's contact too (multi-agent contact): the default is the first by code
    second.agent.contact_id = w.rep.contact.id
    w.sc.db.commit()
    got = _create(w.rep.me, w, sales_agent_id=w.other.agent.id)
    twin = _create(w.rep.portal, w)
    assert got["sales_agent_id"] == twin["sales_agent_id"] == w.rep.agent.id  # ZZA-A-... sorts first
    assert so_row(w, got["id"]).sales_agent_id == w.rep.agent.id
    # a customer of the second linked agent goes to that agent, as the portal does
    mine2 = _create(w.rep.me, w, prospect_name=None, customer_id=second.mine.id)
    assert mine2["sales_agent_id"] == second.agent.id


def test_p4_so_customer_without_an_agent_or_of_another_agent_is_refused_like_the_portal(world):
    w = world
    loose = Customer(id=s.uid(), company_id=w.company_id, customer_code=f"ZZT-{s.uid()[:6]}", customer_name="ZZT loose")
    w.sc.db.add(loose)
    w.sc.db.commit()
    for customer_id in (w.other.mine.id, loose.id):
        a = w.rep.me.call("POST", SO_PORTAL, json=w.so_body(prospect_name=None, customer_id=customer_id))
        b = w.rep.portal.call("POST", SO_PORTAL, json=w.so_body(prospect_name=None, customer_id=customer_id))
        s.not_a_missing_route(a)
        assert a.status_code == b.status_code == 422, (a.text, b.text)
        assert a.json().get("code") == b.json().get("code") == "CUSTOMER_NOT_YOURS"


def test_p4_so_customer_picker_is_limited_to_the_agents_customers(world):
    w = world
    s.ok(w.rep.me.call("GET", SO_PORTAL))
    got = s.ok(w.rep.me.call("GET", f"{SO_PORTAL}/customer-options", params={"q": "ZZT"})).json()
    ids = {i["customer_id"] for i in got["items"]}
    assert w.rep.mine.id in ids and w.other.mine.id not in ids
    assert got == s.ok(w.rep.portal.call("GET", f"{SO_PORTAL}/customer-options", params={"q": "ZZT"})).json()
    assert s.ok(w.rep.me.call("GET", f"{SO_PORTAL}/meta")).json() == s.ok(w.rep.portal.call("GET", f"{SO_PORTAL}/meta")).json()


def test_p4_so_update_stage_and_lost_reason_like_the_portal(world):
    w = world
    a, b = _create(w.rep.me, w), _create(w.rep.portal, w)
    q = _stage(w, "qualified")
    out = []
    for api, oid in ((w.rep.me, a["id"]), (w.rep.portal, b["id"])):
        r1 = api.call("PATCH", f"{SO_PORTAL}/{oid}", json={"status_id": q, "title": "ZZT renamed"})
        lost_no_reason = api.call("PATCH", f"{SO_PORTAL}/{oid}", json={"status_id": _stage(w, "lost")})
        lost = api.call("PATCH", f"{SO_PORTAL}/{oid}", json={"status_id": _stage(w, "lost"), "lost_reason": "no_response"})
        out.append((r1.status_code, r1.json().get("stage_key"), r1.json().get("title"),
                    lost_no_reason.status_code, lost.status_code, lost.json().get("outcome")))
    assert out[0] == out[1]
    assert out[0][:3] == (200, "qualified", "ZZT renamed") and out[0][3] == 422 and out[0][4:] == (200, "lost")
    assert so_row(w, a["id"]).outcome == "lost"


def test_p4_so_foreign_row_answers_what_the_portal_answers(world):
    w = world
    foreign = _create(w.other.portal, w)["id"]
    _create(w.rep.me, w)
    for method, body in (("GET", None), ("PATCH", {"title": "ZZT hijack"})):
        kw = {"json": body} if body else {}
        mine = w.rep.me.call(method, f"{SO_PORTAL}/{foreign}", **kw)
        theirs = w.rep.portal.call(method, f"{SO_PORTAL}/{foreign}", **kw)
        s.not_a_missing_route(mine)
        assert theirs.status_code == 404
        assert (mine.status_code, mine.json()) == (theirs.status_code, theirs.json())
    assert so_row(w, foreign).title != "ZZT hijack"


def test_p4_so_impersonation_acts_as_the_salesperson(world):
    from app.models.impersonation import ImpersonationSession

    w = world
    admin = s.make_user(w.sc.db, roles=["admin"], name="ZZT Impersonating Admin")
    w.sc.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=w.rep.actor.id))
    w.sc.db.commit()
    api = s.my_api(w.sc, admin, **{s.IMPERSONATE_HEADER: w.rep.actor.id})
    created = _create(api, w)
    assert created["sales_agent_id"] == w.rep.agent.id
    assert created["created_by_contact_id"] == w.rep.contact.id
    rows = w.sc.audit(created["id"])
    assert rows and any(a.real_user_id == admin.id for a in rows)


def test_p4_so_gates(world):
    w = world
    s.ok(w.rep.me.call("GET", SO_PORTAL))  # mounted and allowed
    # no session
    assert s.Api(w.client, s.MY, {}).call("POST", SO_PORTAL, json=w.so_body()).status_code == 401
    # no linked contact
    loner = s.make_user(w.sc.db, perms=[SO_VIEW_OWN, SO_ADD, SO_EDIT], name="ZZT Loner")
    r = s.my_api(w.sc, loner).call("POST", SO_PORTAL, json=w.so_body())
    assert r.status_code == 403, r.text
    s.not_a_missing_route(r)
    # a staff .view holder (even with a contact and the agent link)
    contact, _ = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=[SO_VIEW, SO_VIEW_OWN, SO_ADD], contact=contact, name="ZZT Staff")
    r = s.my_api(w.sc, staff).call("POST", SO_PORTAL, json=w.so_body())
    assert r.status_code == 403, r.text
    s.not_a_missing_route(r)
    # create needs .add; update needs .edit
    reader = s.make_user(w.sc.db, perms=[SO_VIEW_OWN], contact=contact if False else s.own_contact(w.sc)[0], name="ZZT Reader")
    r = s.my_api(w.sc, reader).call("POST", SO_PORTAL, json=w.so_body())
    assert r.status_code == 403, r.text
    s.not_a_missing_route(r)
    # bad body
    assert w.rep.me.call("POST", SO_PORTAL, json={"title": ""}).status_code == 422
