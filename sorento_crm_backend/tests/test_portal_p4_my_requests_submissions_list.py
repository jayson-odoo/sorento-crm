"""PORTAL-P4-REQUESTS L1 red tests (hand test 3, owner a25895124 Q1 a): the portal's generic
list `GET /api/v1/public/portal/submissions?type=<kind>&q=` also on `/api/v1/my-requests`, same
body, only the caller's own contact's rows; the four own-kind lists are already reachable there.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)
from tests import _portal_p4_npa_support as npa
from tests import _portal_p4_pt_support as pt
from tests import _portal_p4_sr_so_support as srso

LIST = "/submissions"
KINDS = ("stock_inquiry", "complaint")


def _ids(resp) -> list:
    return [r["id"] for r in resp.json()["items"]]


def _seed(sc, kind):
    spec = s.SPECS[kind]
    mine = s.ok(sc.me.create(kind, spec.body(sc))).json()
    mine2 = s.ok(sc.me.create(kind, spec.body(sc))).json()
    theirs = s.ok(sc.other_portal.create(kind, spec.body(sc, contact=sc.other_contact))).json()
    return mine, mine2, theirs


@pytest.mark.parametrize("kind", KINDS)
def test_l1_my_list_is_the_portal_list_of_the_own_contact(scene, kind):
    mine, mine2, theirs = _seed(scene, kind)
    got = scene.me.call("GET", LIST, params={"type": kind})
    assert got.status_code == 200, got.text
    ids = _ids(got)
    assert set(ids) == {mine["id"], mine2["id"]}
    assert theirs["id"] not in ids
    via_portal = s.ok(scene.portal.call("GET", LIST, params={"type": kind}))
    assert got.json() == via_portal.json()  # ids, numbers, statuses, order, shape
    assert set(got.json()) == {"items"}


@pytest.mark.parametrize("kind", KINDS)
def test_l1_q_search_filters_like_the_portal(scene, kind):
    mine, mine2, _ = _seed(scene, kind)
    tag = mine["product_code"] if "product_code" in mine else None
    if tag is None:
        tag = s.ok(scene.me.get(kind, mine["id"])).json().get("product_code")
    assert tag, "the created row exposes the product code the q search matches"
    got = scene.me.call("GET", LIST, params={"type": kind, "q": tag})
    assert got.status_code == 200, got.text
    assert _ids(got) == [mine["id"]]
    assert got.json() == s.ok(scene.portal.call("GET", LIST, params={"type": kind, "q": tag})).json()
    none = scene.me.call("GET", LIST, params={"type": kind, "q": "zzt-no-such-text-anywhere"})
    assert none.status_code == 200 and none.json()["items"] == []


def test_l1_no_session_is_401(scene):
    s.ok(scene.me.create("stock_inquiry", s.SPECS["stock_inquiry"].body(scene)))
    resp = s.Api(scene.client, s.MY, {}).call("GET", LIST, params={"type": "stock_inquiry"})
    assert resp.status_code == 401, resp.text


def test_l1_staff_view_holder_is_403(scene):
    spec = s.SPECS["stock_inquiry"]
    c, _ = s.own_contact(scene)
    staff = s.make_user(scene.db, perms=[spec.view, spec.view_own], contact=c, name="ZZT Staff")
    resp = s.my_api(scene, staff).call("GET", LIST, params={"type": "stock_inquiry"})
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


def test_l1_no_linked_contact_is_403(scene):
    spec = s.SPECS["stock_inquiry"]
    loner = s.make_user(scene.db, perms=s.sp_perms(spec), name="ZZT Loner")
    resp = s.my_api(scene, loner).call("GET", LIST, params={"type": "stock_inquiry"})
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


def test_l1_another_kinds_slug_does_not_open_this_kind(scene):
    c, _ = s.own_contact(scene)
    only_si = s.make_user(scene.db, perms=s.sp_perms(s.SPECS["stock_inquiry"]), contact=c, name="ZZT SI only")
    api = s.my_api(scene, only_si)
    assert api.call("GET", LIST, params={"type": "stock_inquiry"}).status_code == 200
    resp = api.call("GET", LIST, params={"type": "complaint"})
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


@pytest.mark.parametrize("kind", ["customer_asks", "nope"])
def test_l1_a_kind_outside_the_request_kinds_is_not_served(scene, kind):
    s.ok(scene.me.create("stock_inquiry", s.SPECS["stock_inquiry"].body(scene)))
    resp = scene.me.call("GET", LIST, params={"type": kind})
    assert resp.status_code in (404, 422), resp.text
    s.not_a_missing_route(resp)


def test_l1_missing_type_is_422(scene):
    s.ok(scene.me.create("stock_inquiry", s.SPECS["stock_inquiry"].body(scene)))
    resp = scene.me.call("GET", LIST)
    assert resp.status_code == 422, resp.text


# ----- the four own-kind lists are already served on my-requests (pins; green today)


def test_l1_own_kind_sample_request_list_reachable(srso_world):
    w = srso_world
    s.ok(w.rep.me.call("POST", srso.SR_PORTAL, json=w.sr_body()), 201)
    got = s.ok(w.rep.me.call("GET", srso.SR_PORTAL)).json()
    assert got == s.ok(w.rep.portal.call("GET", srso.SR_PORTAL)).json() and len(got["data"]) == 1


def test_l1_own_kind_sales_opportunity_list_reachable(srso_world):
    w = srso_world
    s.ok(w.rep.me.call("POST", srso.SO_PORTAL, json=w.so_body()), 201)
    got = s.ok(w.rep.me.call("GET", srso.SO_PORTAL)).json()
    assert got == s.ok(w.rep.portal.call("GET", srso.SO_PORTAL)).json() and len(got["items"]) == 1


def test_l1_own_kind_npa_list_reachable(npa_world):
    w = npa_world
    npa.create(w.rep.me, w)
    got = s.ok(w.rep.me.call("GET", npa.SUB)).json()
    assert got == s.ok(w.rep.portal.call("GET", npa.SUB)).json() and len(got["data"]) == 1


def test_l1_own_kind_price_tag_list_reachable(pt_world):
    w = pt_world
    pt.create(w.rep.me, w)
    got = s.ok(w.rep.me.call("GET", pt.SUB)).json()
    assert got == s.ok(w.rep.portal.call("GET", pt.SUB)).json()


srso_world = srso.world
npa_world = npa.world
pt_world = pt.world


def test_l1_project_registration_type_fails_closed_404(scene):
    resp = scene.me.call("GET", LIST, params={"type": "project_registration"})
    assert resp.status_code == 404, resp.text


@pytest.mark.parametrize("raw", [" Complaint ", "COMPLAINT", "Complaint"])
def test_l1_type_is_normalised_like_the_portal(scene, raw):
    mine, mine2, theirs = _seed(scene, "complaint")
    plain = scene.me.call("GET", LIST, params={"type": "complaint"})
    got = scene.me.call("GET", LIST, params={"type": raw})
    assert got.status_code == 200, got.text
    assert got.json() == plain.json()
    assert set(_ids(got)) == {mine["id"], mine2["id"]}
    assert theirs["id"] not in _ids(got)
