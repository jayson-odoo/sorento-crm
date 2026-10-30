"""PORTAL-P4-REQUESTS R2 (PAR-7): the Purchase Request / Sponsorship Form portal form reads two lookup sets
(`procurement_sales_type`, `procurement_sponsor_subject`) that `/api/v1/my-requests` must answer exactly as the portal
does, and refuse staff (`.view` holders), no session and no linked contact like the other my-requests routes.
Reuses the S0-B scene (tests/_portal_p4_support.py): Postgres, own seeded chain.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

PR_SF_SETS = ["procurement_sales_type", "procurement_sponsor_subject"]


def _seed_sets(db):
    """Own chain: the CI database has no lookup rows."""
    from app.models.lookup import LookupOption, LookupSet

    for key in PR_SF_SETS:
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


@pytest.mark.parametrize("key", PR_SF_SETS)
def test_pr_sf_lookup_set_answers_the_same_as_the_portal(scene, key):
    _seed_sets(scene.db)
    mine = scene.me.call("GET", f"/lookups/sets/{key}")
    s.not_a_missing_route(mine)
    theirs = s.ok(scene.portal.call("GET", f"/lookups/sets/{key}"))
    assert mine.status_code == theirs.status_code == 200, (mine.status_code, mine.text)
    assert mine.json() == theirs.json()
    assert {o["value"] for o in mine.json()["options"]} >= {"zzt_a", "zzt_b"}


@pytest.mark.parametrize("key", PR_SF_SETS)
def test_pr_sf_lookup_set_no_session_is_401(scene, key):
    s.ok(scene.me.requestor_options())
    bare = s.Api(scene.client, s.MY, {})
    resp = bare.call("GET", f"/lookups/sets/{key}")
    assert resp.status_code == 401, (resp.status_code, resp.text)


@pytest.mark.parametrize("key", PR_SF_SETS)
def test_pr_sf_lookup_set_staff_view_holder_is_403(scene, key):
    s.ok(scene.me.requestor_options())
    c, _portal = s.own_contact(scene)
    spec = s.SPECS["stock_inquiry"]
    staff = s.make_user(scene.db, perms=[spec.view, spec.view_own, spec.add], contact=c, name="ZZT Staff")
    resp = s.my_api(scene, staff).call("GET", f"/lookups/sets/{key}")
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)


@pytest.mark.parametrize("key", PR_SF_SETS)
def test_pr_sf_lookup_set_no_linked_contact_is_403(scene, key):
    s.ok(scene.me.requestor_options())
    spec = s.SPECS["stock_inquiry"]
    loner = s.make_user(scene.db, perms=s.sp_perms(spec), name="ZZT Loner")
    resp = s.my_api(scene, loner).call("GET", f"/lookups/sets/{key}")
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)
