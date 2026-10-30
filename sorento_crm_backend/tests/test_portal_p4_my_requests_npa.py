"""PORTAL-P4-REQUESTS S5 red tests: a salesperson's New Product Application written from the CRM through
/api/v1/my-requests, by the portal's own code (`public/portal_new_product_application.py`).

Paths and bodies are the portal router's (see tests/_portal_p4_npa_support.py). The `me` handle is the CRM
session; the `portal` handle is the same contact on the portal, and every rule is asserted as "me answers
what the portal answers".
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._npa_v4_support import install_storage, seed_attachment_type
from tests._portal_p4_npa_support import (  # noqa: F401
    ATT,
    KIND,
    NPA_CREATE,
    NPA_VIEW,
    NPA_VIEW_OWN,
    OWN,
    SUB,
    create,
    npa_row,
    scene,
    world,
)


def _mounted(w):
    s.ok(w.rep.me.call("GET", SUB))


def test_p4_npa_parity_create_and_list_equal_the_portal(world):
    w = world
    mine = create(w.rep.me, w)
    theirs = create(w.rep.portal, w)
    assert set(mine) == set(theirs)
    assert (mine["source"], mine["status"]) == (theirs["source"], theirs["status"]) == ("portal", "draft")
    assert s.shape(mine["application_no"]) == s.shape(theirs["application_no"])
    assert mine["application_no"].startswith("NPA-")
    row = npa_row(w, mine["id"])
    assert row.source == "portal"
    assert row.contact_id == w.rep.contact.id
    assert row.space_id == w.sc.space_id
    assert row.applicant_id == w.rep.actor.id  # the linked CRM user, not NULL
    assert mine["applicant_id"] == w.rep.actor.id

    listed_me = s.ok(w.rep.me.call("GET", SUB)).json()
    listed_portal = s.ok(w.rep.portal.call("GET", SUB)).json()
    assert {r["id"] for r in listed_me["data"]} == {r["id"] for r in listed_portal["data"]} == {mine["id"], theirs["id"]}
    assert set(listed_me) == set(listed_portal)


def test_p4_npa_detail_is_the_portal_shape_without_item_group_uom_or_price(world):
    w = world
    d = create(w.rep.me, w)
    got = s.ok(w.rep.me.call("GET", f"{SUB}/{d['id']}")).json()
    assert got == s.ok(w.rep.portal.call("GET", f"{SUB}/{d['id']}")).json()
    for line in got["lines"]:
        assert not {"opened_category_name", "opened_base_uom_name", "opened_list_price"} & set(line)


def _walk(api, w) -> list:
    """create -> update -> submit -> update refused -> submit again -> revise (no reason, reason) -> cancel -> cancel again."""
    out = []
    d = create(api, w)
    out.append(("create", d["status"]))
    r = api.call("PUT", f"{SUB}/{d['id']}", json=w.body(remark="ZZT changed"))
    out.append(("update", r.status_code, r.json().get("remark")))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("submit", r.status_code, r.json().get("status")))
    r = api.call("PUT", f"{SUB}/{d['id']}", json=w.body())
    out.append(("update_after_submit", r.status_code, r.json().get("code")))
    r = api.call("POST", f"{SUB}/{d['id']}/submit")
    out.append(("resubmit", r.status_code, r.json().get("code")))
    r = api.call("POST", f"{SUB}/{d['id']}/revise", json={"reason": ""})
    out.append(("revise_no_reason", r.status_code))
    r = api.call("POST", f"{SUB}/{d['id']}/revise", json={"reason": "ZZT wrong UOM"})
    out.append(("revise", r.status_code, r.json().get("status")))
    r = api.call("POST", f"{SUB}/{d['id']}/cancel")
    out.append(("cancel", r.status_code, r.json().get("status")))
    r = api.call("POST", f"{SUB}/{d['id']}/cancel")
    out.append(("cancel_again", r.status_code, r.json().get("code")))
    return out


def test_p4_npa_create_update_submit_revise_cancel_rules_match_the_portal(world):
    w = world
    mine, theirs = _walk(w.rep.me, w), _walk(w.rep.portal, w)
    assert mine == theirs
    assert [x[0] for x in mine] == [
        "create", "update", "submit", "update_after_submit", "resubmit",
        "revise_no_reason", "revise", "cancel", "cancel_again",
    ]
    assert ("submit", 200, "submitted") in mine
    assert ("update_after_submit", 422, "new_product_application_locked") in mine
    assert ("revise_no_reason", 422) in mine
    assert ("revise", 200, "draft") in mine  # the NPA's own move back to draft, not the portal revision engine
    assert ("cancel", 200, "cancelled") in mine
    assert mine[-1][1] != 200


def test_p4_npa_incomplete_submit_is_refused_like_the_portal_and_draft_stays_cancellable(world):
    w = world
    out = []
    for api in (w.rep.me, w.rep.portal):
        d = create(api, w, lines=[w.line(description=None)])
        r = api.call("POST", f"{SUB}/{d['id']}/submit")
        c = api.call("POST", f"{SUB}/{d['id']}/cancel")
        out.append((r.status_code, r.text, c.status_code, c.json().get("status")))
    assert out[0] == out[1]
    assert out[0][0] == 422 and "Product 1: enter the product type." in out[0][1]
    assert out[0][2:] == (200, "cancelled")


def test_p4_npa_start_from_an_own_responded_inquiry_and_refuse_a_foreign_one(world):
    w = world
    mine = w.inquiry(w.rep)
    unanswered = w.inquiry(w.rep, status="pending_purchasing")
    foreign = w.inquiry(w.other)

    picker = s.ok(w.rep.me.call("GET", f"{OWN}/inquiries")).json()
    assert picker == s.ok(w.rep.portal.call("GET", f"{OWN}/inquiries")).json()
    ids = {r["id"] for r in picker}
    assert mine.id in ids and unanswered.id not in ids and foreign.id not in ids

    pre = s.ok(w.rep.me.call("GET", f"{OWN}/prefill", params={"stock_inquiry_id": mine.id})).json()
    assert pre == s.ok(w.rep.portal.call("GET", f"{OWN}/prefill", params={"stock_inquiry_id": mine.id})).json()
    assert pre["customer_id"] is None and pre["lines"]

    for target in (foreign, unanswered):
        a = w.rep.me.call("GET", f"{OWN}/prefill", params={"stock_inquiry_id": target.id})
        b = w.rep.portal.call("GET", f"{OWN}/prefill", params={"stock_inquiry_id": target.id})
        assert b.status_code == 404
        assert (a.status_code, a.json()) == (b.status_code, b.json())

    made = s.ok(w.rep.me.call("POST", SUB, json=w.body(stock_inquiry_id=mine.id)), 201).json()
    assert npa_row(w, made["id"]).stock_inquiry_id == mine.id
    refused = w.rep.me.call("POST", SUB, json=w.body(stock_inquiry_id=foreign.id))
    twin = w.rep.portal.call("POST", SUB, json=w.body(stock_inquiry_id=foreign.id))
    assert refused.status_code == twin.status_code == 422
    assert refused.json() == twin.json()


def test_p4_npa_customer_picker_is_limited_to_the_agents_own_customers(world):
    w = world
    _mounted(w)
    mine = s.ok(w.rep.me.call("GET", f"{OWN}/customers")).json()
    assert [c["customer_id"] for c in mine] == [w.rep.mine.id]
    assert mine == s.ok(w.rep.portal.call("GET", f"{OWN}/customers")).json()
    assert w.other.mine.id not in str(mine)
    refused = w.rep.me.call("POST", SUB, json=w.body(customer_id=w.other.mine.id))
    twin = w.rep.portal.call("POST", SUB, json=w.body(customer_id=w.other.mine.id))
    assert refused.status_code == twin.status_code and refused.status_code >= 400
    assert refused.json() == twin.json()
    s.ok(w.rep.me.call("POST", SUB, json=w.body(customer_id=w.rep.mine.id)), 201)


def test_p4_npa_brand_lookup_equals_the_portal(world):
    w = world
    mine = s.ok(w.rep.me.call("GET", f"{OWN}/lookups/brands", params={"q": ""}))
    assert mine.json() == s.ok(w.rep.portal.call("GET", f"{OWN}/lookups/brands", params={"q": ""})).json()


def test_p4_npa_a_portal_raised_row_is_editable_and_movable_through_my_requests(world):
    w = world
    raised = create(w.rep.portal, w)  # raised on the portal, same contact
    r = s.ok(w.rep.me.call("PUT", f"{SUB}/{raised['id']}", json=w.body(remark="ZZT edited from the CRM")))
    assert r.json()["remark"] == "ZZT edited from the CRM"
    assert npa_row(w, raised["id"]).remark == "ZZT edited from the CRM"
    assert s.ok(w.rep.me.call("POST", f"{SUB}/{raised['id']}/submit")).json()["status"] == "submitted"
    assert s.ok(w.rep.me.call("POST", f"{SUB}/{raised['id']}/cancel")).json()["status"] == "cancelled"


def test_p4_npa_foreign_row_answers_what_the_portal_answers(world):
    w = world
    foreign = create(w.other.portal, w)["id"]
    create(w.rep.me, w)  # own row: the route is known to be mounted
    calls = {
        "get": ("GET", f"{SUB}/{foreign}", None),
        "put": ("PUT", f"{SUB}/{foreign}", w.body()),
        "submit": ("POST", f"{SUB}/{foreign}/submit", None),
        "revise": ("POST", f"{SUB}/{foreign}/revise", {"reason": "ZZT nope"}),
        "cancel": ("POST", f"{SUB}/{foreign}/cancel", None),
        "download": ("GET", f"{SUB}/{foreign}/download", None),
    }
    for name, (method, path, body) in calls.items():
        kw = {"json": body} if body is not None else {}
        mine = w.rep.me.call(method, path, **kw)
        theirs = w.rep.portal.call(method, path, **kw)
        s.not_a_missing_route(mine)
        assert theirs.status_code == 404, (name, theirs.status_code)
        assert (mine.status_code, mine.json()) == (theirs.status_code, theirs.json()), name
    assert s.ok(w.other.portal.call("GET", f"{SUB}/{foreign}")).json()["status"] == "draft"


# ------------------------------------------------------------------ uploads (the generic portal attachment routes)


@pytest.fixture
def store(monkeypatch, world):
    from app.models.resources import AttachmentType
    from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE

    db = world.sc.db
    seed_attachment_type(db)
    if not db.query(AttachmentType).filter(AttachmentType.code == PORTAL_ATTACHMENT_TYPE_CODE).first():
        db.add(AttachmentType(
            id=s.uid(), code=PORTAL_ATTACHMENT_TYPE_CODE, type_name="Portal Submission",
            allowed_extensions="jpg,jpeg,png,webp,pdf,txt", max_file_size_mb=10,
        ))
    db.commit()
    return install_storage(monkeypatch)


def _upload(api, sid, name="spec.pdf"):
    return api.call(
        "POST", ATT, data={"kind": KIND, "submission_id": sid}, files={"file": (name, b"%PDF-1.4 fake", "application/pdf")}
    )


def test_p4_npa_upload_list_and_remove_work_as_on_the_portal(world, store):
    w = world
    d = create(w.rep.me, w)
    up = _upload(w.rep.me, d["id"])
    assert up.status_code in (200, 201), up.text
    twin = _upload(w.rep.portal, create(w.rep.portal, w)["id"])
    assert set(up.json()) == set(twin.json())
    link = up.json()["link_id"]
    got = s.ok(w.rep.me.call("GET", f"{SUB}/{d['id']}")).json()
    assert [a["link_id"] for a in got["attachments"]] == [link]
    listed = s.ok(w.rep.me.call("GET", ATT, params={"kind": KIND, "submission_id": d["id"]})).json()
    assert [a["link_id"] for a in listed["items"]] == [link]
    rm = w.rep.me.call("DELETE", f"{ATT}/{link}")
    assert rm.status_code in (200, 204), rm.text
    assert s.ok(w.rep.me.call("GET", f"{SUB}/{d['id']}")).json()["attachments"] == []


def test_p4_npa_upload_is_locked_while_submitted_like_the_portal(world, store):
    w = world
    out = []
    for api in (w.rep.me, w.rep.portal):
        d = create(api, w)
        link = _upload(api, d["id"]).json()["link_id"]
        s.ok(api.call("POST", f"{SUB}/{d['id']}/submit"))
        up, rm = _upload(api, d["id"]), api.call("DELETE", f"{ATT}/{link}")
        out.append((up.status_code, rm.status_code))
    assert out[0] == out[1]
    assert all(code in (409, 422) for code in out[0])


def test_p4_npa_upload_to_a_foreign_row_is_refused_like_the_portal(world, store):
    w = world
    foreign = create(w.other.portal, w)["id"]
    own_link = _upload(w.other.portal, foreign).json()["link_id"]
    create(w.rep.me, w)
    mine = _upload(w.rep.me, foreign)
    theirs = _upload(w.rep.portal, foreign)
    assert theirs.status_code == 404
    assert mine.status_code == 404 and mine.json() == theirs.json()
    assert w.rep.me.call("GET", ATT, params={"kind": KIND, "submission_id": foreign}).status_code == 404
    assert w.rep.me.call("DELETE", f"{ATT}/{own_link}").status_code == 404


# ------------------------------------------------------------------ impersonation and gates


def test_p4_npa_impersonation_acts_as_the_salesperson(world):
    from app.models.impersonation import ImpersonationSession

    w = world
    admin = s.make_user(w.sc.db, roles=["admin"], name="ZZT Impersonating Admin")
    w.sc.db.add(ImpersonationSession(id=s.uid(), admin_user_id=admin.id, target_user_id=w.rep.actor.id))
    w.sc.db.commit()
    api = s.my_api(w.sc, admin, **{s.IMPERSONATE_HEADER: w.rep.actor.id})
    aid = create(api, w)["id"]
    row = npa_row(w, aid)
    assert (row.contact_id, row.applicant_id, row.source) == (w.rep.contact.id, w.rep.actor.id, "portal")
    rows = w.sc.audit(aid)
    assert rows, "no audit rows for the create"
    assert all(a.user_id == w.rep.actor.id for a in rows if a.user_id)
    assert any(a.real_user_id == admin.id for a in rows)
    s.ok(api.call("POST", f"{SUB}/{aid}/submit"))
    assert npa_row(w, aid).status == "submitted"


def test_p4_npa_gate_no_session_is_401(world):
    _mounted(world)
    assert s.Api(world.client, s.MY, {}).call("POST", SUB, json=world.body()).status_code == 401


def test_p4_npa_gate_no_linked_contact_is_403(world):
    w = world
    _mounted(w)
    loner = s.make_user(w.sc.db, perms=[NPA_VIEW_OWN, NPA_CREATE], name="ZZT Loner")
    for method, path in (("POST", SUB), ("GET", SUB), ("GET", f"{OWN}/customers"), ("GET", f"{OWN}/inquiries")):
        resp = s.my_api(w.sc, loner).call(method, path, **({"json": w.body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_npa_gate_staff_view_holder_is_403_even_with_a_contact(world):
    w = world
    _mounted(w)
    contact, portal = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=[NPA_VIEW, NPA_VIEW_OWN, NPA_CREATE], contact=contact, name="ZZT Staff")
    api = s.my_api(w.sc, staff)
    for method, path in (("POST", SUB), ("GET", SUB), ("GET", f"{OWN}/customers")):
        resp = api.call(method, path, **({"json": w.body()} if method == "POST" else {}))
        assert resp.status_code == 403, (path, resp.text)
        s.not_a_missing_route(resp)


def test_p4_npa_gate_create_needs_create_but_reading_own_works(world):
    w = world
    _mounted(w)
    contact, portal = s.own_contact(w.sc)
    reader = s.make_user(w.sc.db, perms=[NPA_VIEW_OWN], contact=contact, name="ZZT Reader")
    api = s.my_api(w.sc, reader)
    resp = api.call("POST", SUB, json=w.body())
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)
    assert api.call("GET", SUB).status_code in (200, 403)  # never a 404


def test_p4_npa_another_kinds_slug_does_not_open_this_kind(world):
    w = world
    _mounted(w)
    contact, portal = s.own_contact(w.sc)
    other_kind = s.make_user(
        w.sc.db, perms=["procurement.stock_inquiries.view_own", "procurement.stock_inquiries.add"], contact=contact, name="ZZT SI only"
    )
    resp = s.my_api(w.sc, other_kind).call("POST", SUB, json=w.body())
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


def test_p4_npa_bad_body_is_422(world):
    w = world
    _mounted(w)
    resp = w.rep.me.call("POST", SUB, json={"lines": "nope"})
    assert resp.status_code == 422, resp.text
    removed = w.rep.me.call("POST", SUB, json=w.body(lines=[w.line(cost_price="12.50")]))
    assert removed.status_code == 422, removed.text  # the applicant never writes cost
