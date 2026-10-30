"""PORTAL-P4-REQUESTS S0-B red tests: who may use /api/v1/my-requests, and for what.

Gates: no session 401; no linked contact 403; staff `.view` holder 403; missing `.add` 403 on
create; another kind's slug does not open this kind; kinds outside the four 404; bad body 422.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

SI, CX = s.SPECS["stock_inquiry"], s.SPECS["complaint"]


def _mounted(sc):
    """The route exists and the caller is allowed: guards every refusal below against a bare 404."""
    s.ok(sc.me.create("stock_inquiry", SI.body(sc)))


def test_no_session_is_401(scene):
    _mounted(scene)
    bare = s.Api(scene.client, s.MY, {})
    resp = bare.create("stock_inquiry", SI.body(scene))
    assert resp.status_code == 401, resp.text
    assert bare.requestor_options().status_code == 401


@pytest.mark.parametrize("kind", s.KINDS)
def test_no_linked_contact_is_403(scene, kind):
    _mounted(scene)
    spec = s.SPECS[kind]
    loner = s.make_user(scene.db, perms=s.sp_perms(spec), name="ZZT Loner")
    api = s.my_api(scene, loner)
    for resp in (api.create(kind, spec.body(scene)), api.requestor_options()):
        assert resp.status_code == 403, resp.text
        s.not_a_missing_route(resp)


@pytest.mark.parametrize("kind", s.KINDS)
def test_staff_view_holder_is_403_even_with_a_contact(scene, kind):
    _mounted(scene)
    spec = s.SPECS[kind]
    c, portal = s.own_contact(scene)
    staff = s.make_user(scene.db, perms=[spec.view, spec.view_own, spec.add], contact=c, name="ZZT Staff")
    api = s.my_api(scene, staff)
    resp = api.create(kind, spec.body(scene, contact=c))
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)
    sid = s.ok(portal.create(kind, spec.body(scene, contact=c))).json()["id"]
    assert api.get(kind, sid).status_code == 403
    assert api.submit(kind, sid).status_code == 403


@pytest.mark.parametrize("kind", s.KINDS)
def test_create_without_add_is_403_but_reading_own_works(scene, kind):
    _mounted(scene)
    spec = s.SPECS[kind]
    c, portal = s.own_contact(scene)
    reader = s.make_user(scene.db, perms=[spec.view_own], contact=c, name="ZZT Reader")
    api = s.my_api(scene, reader)
    resp = api.create(kind, spec.body(scene, contact=c))
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)
    sid = s.ok(portal.create(kind, spec.body(scene, contact=c))).json()["id"]
    assert api.get(kind, sid).status_code == 200


def test_another_kinds_slugs_do_not_open_this_kind(scene):
    _mounted(scene)
    c, _ = s.own_contact(scene)
    only_si = s.make_user(scene.db, perms=s.sp_perms(SI), contact=c, name="ZZT SI only")
    api = s.my_api(scene, only_si)
    s.ok(api.create("stock_inquiry", SI.body(scene, contact=c)))
    resp = api.create("complaint", CX.body(scene))
    assert resp.status_code == 403, resp.text
    s.not_a_missing_route(resp)


@pytest.mark.parametrize("kind", ["customer_asks", "conversation", "project_registration", "nope"])
def test_kinds_outside_the_four_are_404(scene, kind):
    _mounted(scene)
    c, _ = s.own_contact(scene)
    everything = s.make_user(
        scene.db, perms=s.sp_perms(*s.SPECS.values()) + ["projects.sample_requests.view_own"],
        contact=c, name="ZZT Everything",
    )
    api = s.my_api(scene, everything)
    resp = api.create(kind, {"fields": {}})
    assert resp.status_code == 404, resp.text
    s.not_a_missing_route(resp)  # a domain 404, not an unmounted path
    assert api.get(kind, s.uid()).status_code == 404


def test_bad_body_is_422(scene):
    _mounted(scene)
    resp = scene.me.call("POST", "/submissions/stock_inquiry", json={"nope": 1})
    assert resp.status_code == 422, resp.text
    resp = scene.me.revise("stock_inquiry", s.uid(), reason="x")
    assert resp.status_code in (404, 409, 422), resp.text
    s.not_a_missing_route(resp)
