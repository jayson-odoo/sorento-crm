"""PORTAL-P4-REQUESTS R1 red tests (form parity rework): the portal's own SubmissionForm runs inside the
CRM page over an injected client, so `/api/v1/my-requests` must answer the portal's lookup / profile /
ai-extract routes with the SAME paths and bodies. Today they live only on the portal router
(`app/api/v1/public/portal.py` /me, /lookups/*; `app/api/v1/public/ai_extract.py`) and 404 on my-requests.

Flows reuse the S0-B scene (tests/_portal_p4_support.py): Postgres, own seeded chain, a real Bearer
session for the salesperson and a real PortalToken for the same contact.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)
from tests._pg_fixture import unique_code

SET_KEYS = [
    "complaints_customer_type",
    "complaints_within_warranty",
    "complaints_defects_discovered",
    "complaints_complaint_type",
]
LOOKUPS = [
    ("/lookups/products", {"q": "ZZT", "limit": 20}),
    ("/lookups/debtors", {"q": "ZZT", "limit": 20}),
    ("/lookups/debtors", {"q": "ZZT", "limit": 20, "kind": "complaint"}),
    ("/lookups/delivery-orders", {"q": "", "limit": 20}),
    ("/lookups/projects", {"q": "ZZT", "limit": 20}),
    *[(f"/lookups/sets/{k}", None) for k in SET_KEYS],
]


def _seed_product(db):
    from decimal import Decimal

    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    cat = ProductCategory(id=s.uid(), category_code=unique_code("ZZTC"), category_name="ZZT Cat")
    brand = Brand(id=s.uid(), brand_code=unique_code("ZZTB"), brand_name="ZZT Brand")
    uom = UnitOfMeasure(id=s.uid(), uom_code=unique_code("ZZTU"), uom_name="Each")
    db.add_all([cat, brand, uom])
    db.flush()
    p = Product(
        id=s.uid(), product_code=unique_code("ZZT-LKP"), product_name="ZZT Lookup Tap",
        category_id=cat.id, brand_id=brand.id, base_uom_id=uom.id, list_price=Decimal("50.00"), is_active=True,
    )
    db.add(p)
    db.commit()
    return p


def _seed_lookup_sets(db):
    """Own chain: the portal 404s a whitelisted set that has no row, so seed any that are missing."""
    from app.models.lookup import LookupOption, LookupSet

    for key in SET_KEYS:
        if db.query(LookupSet).filter(LookupSet.set_key == key).first():
            continue
        ls = LookupSet(id=s.uid(), set_key=key, name=f"ZZT {key}", is_active=True)
        db.add(ls)
        db.flush()
        db.add_all([
            LookupOption(set_id=ls.id, value="zzt_a", label="ZZT A", sort_order=1, is_active=True),
            LookupOption(set_id=ls.id, value="zzt_b", label="ZZT B", sort_order=2, is_active=True),
        ])
    db.commit()


def _mounted(sc):
    """The salesperson is allowed and the my-requests router is up: guards every refusal below against a bare 404."""
    s.ok(sc.me.requestor_options())


def test_me_equals_the_portal_me(scene):
    mine = scene.me.call("GET", "/me")
    s.not_a_missing_route(mine)
    theirs = s.ok(scene.portal.call("GET", "/me"))
    assert mine.status_code == 200, (mine.status_code, mine.text)
    a, b = mine.json(), theirs.json()
    for key in ("contact_id", "space_id", "name", "phone_number", "requires_registered_project"):
        assert a.get(key) == b.get(key), key
    assert a["contact_id"] == scene.contact.id


@pytest.mark.parametrize("path,params", LOOKUPS, ids=[p for p, _ in LOOKUPS][:0] or None)
def test_lookup_answers_the_same_as_the_portal(scene, path, params):
    _seed_product(scene.db)
    _seed_lookup_sets(scene.db)
    mine = scene.me.call("GET", path, params=params)
    s.not_a_missing_route(mine)
    theirs = s.ok(scene.portal.call("GET", path, params=params))
    assert mine.status_code == theirs.status_code == 200, (mine.status_code, mine.text)
    assert mine.json() == theirs.json()


def test_product_lookup_finds_a_seeded_product_through_my_requests(scene):
    prod = _seed_product(scene.db)
    mine = scene.me.call("GET", "/lookups/products", params={"q": prod.product_code, "limit": 20})
    s.not_a_missing_route(mine)
    assert mine.status_code == 200, mine.text
    assert [i["product_code"] for i in mine.json()] == [prod.product_code]
    assert mine.json() == s.ok(scene.portal.call("GET", "/lookups/products", params={"q": prod.product_code, "limit": 20})).json()


def test_lookup_set_outside_the_whitelist_is_refused_like_the_portal(scene):
    mine = scene.me.call("GET", "/lookups/sets/not_a_portal_set")
    s.not_a_missing_route(mine)
    theirs = scene.portal.call("GET", "/lookups/sets/not_a_portal_set")
    assert theirs.status_code == 403
    assert mine.status_code == 403 and mine.json() == theirs.json()


def test_ai_extract_schema_equals_the_portal(scene):
    mine = scene.me.call("GET", "/ai-extract/schema", params={"form_key": "portal.stock_inquiry"})
    s.not_a_missing_route(mine)
    theirs = scene.portal.call("GET", "/ai-extract/schema", params={"form_key": "portal.stock_inquiry"})
    assert mine.status_code == theirs.status_code, (mine.status_code, mine.text, theirs.status_code, theirs.text)
    assert mine.json() == theirs.json()


def test_ai_extract_with_no_file_is_the_same_422_as_the_portal(scene):
    mine = scene.me.call("POST", "/ai-extract", data={"form_key": "portal.stock_inquiry"})
    s.not_a_missing_route(mine)
    theirs = scene.portal.call("POST", "/ai-extract", data={"form_key": "portal.stock_inquiry"})
    assert theirs.status_code == 422
    assert mine.status_code == 422


ROUTES = [("GET", "/me"), ("GET", "/lookups/products"), ("GET", "/lookups/debtors"),
          ("GET", "/lookups/delivery-orders"), ("GET", "/lookups/projects"),
          ("GET", "/lookups/sets/complaints_customer_type"), ("GET", "/ai-extract/schema")]


@pytest.mark.parametrize("method,path", ROUTES)
def test_no_session_is_401(scene, method, path):
    _mounted(scene)
    bare = s.Api(scene.client, s.MY, {})
    resp = bare.call(method, path, params={"form_key": "portal.stock_inquiry"} if "ai-extract" in path else None)
    assert resp.status_code == 401, (resp.status_code, resp.text)


@pytest.mark.parametrize("method,path", ROUTES)
def test_staff_view_holder_is_403_even_with_a_contact(scene, method, path):
    _mounted(scene)
    c, _portal = s.own_contact(scene)
    spec = s.SPECS["stock_inquiry"]
    staff = s.make_user(scene.db, perms=[spec.view, spec.view_own, spec.add], contact=c, name="ZZT Staff")
    resp = s.my_api(scene, staff).call(method, path, params={"form_key": "portal.stock_inquiry"} if "ai-extract" in path else None)
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)


@pytest.mark.parametrize("method,path", ROUTES)
def test_no_linked_contact_is_403(scene, method, path):
    _mounted(scene)
    spec = s.SPECS["stock_inquiry"]
    loner = s.make_user(scene.db, perms=s.sp_perms(spec), name="ZZT Loner")
    resp = s.my_api(scene, loner).call(method, path, params={"form_key": "portal.stock_inquiry"} if "ai-extract" in path else None)
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)


def test_staff_edit_of_root_cause_resolution_technical_response_is_no_salesperson_side_revision(scene):
    """The adapter does not track the three staff-only fields, and a staff edit writes no portal_form_revisions row."""
    from app.models.complaint_master_data import ComplaintResolution, ComplaintRootCause
    from app.services.portal_revision_service import get_adapter

    adapter = get_adapter("complaint")
    assert adapter is not None
    tracked = set(adapter.snapshot_form_fields) | set(adapter.snapshot_extra_fields)
    for staff_only in ("root_cause_id", "root_cause", "resolution_id", "resolution", "technical_team_response"):
        assert staff_only not in tracked, staff_only
    assert "technical_team_response" in adapter.invalidated_on_revise  # cleared on a revise, never a diff line

    spec = s.SPECS["complaint"]
    sid = s._id(scene.portal.create(spec.kind, spec.body(scene)))
    s.ok(scene.portal.submit(spec.kind, sid))
    before = [(r.kind, r.revision_no, r.version_no) for r in scene.revisions(spec.kind, sid)]
    assert [k for k, _, _ in before] == ["original"]

    rc = ComplaintRootCause(id=s.uid(), name=unique_code("ZZT root"), is_active=True)
    rs = ComplaintResolution(id=s.uid(), name=unique_code("ZZT resolution"), is_active=True)
    scene.db.add_all([rc, rs])
    scene.db.commit()
    s.ok(scene.staff_call("PUT", f"{s.CX}/{sid}", json={
        "root_cause_id": rc.id, "resolution_id": rs.id, "technical_team_response": "ZZT staff wrote this",
    }))
    row = scene.row(spec, sid)
    assert row.root_cause_id == rc.id and row.resolution_id == rs.id
    assert row.technical_team_response == "ZZT staff wrote this"

    assert [(r.kind, r.revision_no, r.version_no) for r in scene.revisions(spec.kind, sid)] == before
    assert scene.row(spec, sid).revision_no in (0, None)
    # the salesperson's own view of the revision history shows no change either
    items = s.ok(scene.portal.revisions(spec.kind, sid)).json()["items"]
    assert [i["kind"] for i in items] == ["original"]
