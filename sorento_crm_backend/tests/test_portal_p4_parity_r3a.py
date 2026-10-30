"""PORTAL-P4-REQUESTS R3a (PAR-6, PAR-7): Sample Request, New Product Application and Sales Opportunity.

The portal's own form runs inside the CRM page over `/api/v1/my-requests`, so:
  PAR-6  the SAME body POSTed through the portal and through my-requests (same salesperson contact) stores the
         same row (ids, numbers, timestamps and creator-ish columns excluded);
  PAR-7  every lookup those three forms call answers my-requests exactly as the portal, and refuses a staff
         `.view` holder (403), no session (401) and a user with no linked contact (403).

These routes already exist (no new BE route in R3a), so these are parity PINS and may be green from the start.
Postgres only (blank_session via the S0-B scene), every row seeded here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import DateTime, inspect

from tests import _portal_p4_npa_support as npa
from tests import _portal_p4_sr_so_support as srso
from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

# --------------------------------------------------------------------------- #
# Worlds (the shared `world` fixtures are name-clashing, so build both here)   #
# --------------------------------------------------------------------------- #


@pytest.fixture
def sr_so(scene):  # noqa: F811
    from app.services import project_seed_service
    from app.services.sales import sales_seed_service
    from tests._sample_request_seed import make_product

    db = scene.db
    project_seed_service.run(db, company_id=s.SORENTO)
    sales_seed_service.run(db)
    product = make_product(db)
    db.flush()
    w = srso.World(sc=scene, rep=None, other=None, product=product, company_id=s.SORENTO)
    w.rep = w.person("Rep", agent_code=f"ZZA-A-{s.uid()[:6]}".upper())
    w.other = w.person("Other", agent_code=f"ZZA-B-{s.uid()[:6]}".upper())
    db.commit()
    return w


@pytest.fixture
def npa_w(scene):  # noqa: F811
    w = npa.World(sc=scene, rep=None, other=None, company_id=s.SORENTO)
    w.rep = w.person("Rep")
    w.other = w.person("Other")
    scene.db.commit()
    return w


# --------------------------------------------------------------------------- #
# PAR-6: same body, same stored row                                            #
# --------------------------------------------------------------------------- #

#: columns that legitimately differ between two rows created by two calls
_SKIP_NAMES = {
    "id", "opportunity_no", "request_no", "application_no", "created_by_user_id", "updated_by", "created_by",
    "updated_by_user_id",
}


def _stored(db, model, row_id, *, skip=()) -> dict:
    db.expire_all()
    row = db.query(model).filter(model.id == row_id).one()
    out = {}
    for col in inspect(model).columns:
        if col.key in _SKIP_NAMES or col.key in skip or isinstance(col.type, DateTime):
            continue
        out[col.key] = getattr(row, col.key)
    return out


def _lines(db, model, parent_col, parent_id, *, skip=()) -> list:
    db.expire_all()
    rows = db.query(model).filter(getattr(model, parent_col) == parent_id).all()
    out = []
    for row in rows:
        item = {}
        for col in inspect(model).columns:
            if col.key in _SKIP_NAMES or col.key in skip or col.key == parent_col or isinstance(col.type, DateTime):
                continue
            item[col.key] = getattr(row, col.key)
        out.append(item)
    return sorted(out, key=lambda d: (str(d.get("sort_order", d.get("line_no", ""))), str(d)))


def test_par6_sample_request_same_body_stores_the_same_row(sr_so):
    from app.models.sample_request import SampleRequest, SampleRequestLine

    w = sr_so
    body = w.sr_body()
    assert body.get("lines"), "full_payload must carry lines for this pin to mean something"
    mine = s.ok(w.rep.me.call("POST", srso.SR_PORTAL, json=body), 201).json()
    theirs = s.ok(w.rep.portal.call("POST", srso.SR_PORTAL, json=body), 201).json()
    assert mine["id"] != theirs["id"]
    db = w.sc.db
    assert _stored(db, SampleRequest, mine["id"]) == _stored(db, SampleRequest, theirs["id"])
    assert _lines(db, SampleRequestLine, "request_id", mine["id"]) == _lines(db, SampleRequestLine, "request_id", theirs["id"])
    assert len(_lines(db, SampleRequestLine, "request_id", mine["id"])) == len(body["lines"])
    assert set(mine) == set(theirs)


def test_par6_new_product_application_same_body_stores_the_same_row(npa_w):
    from app.models.new_product_application import NewProductApplication, NewProductApplicationLine

    w = npa_w
    body = w.body(lines=[w.line(brand_id=None), w.line(description="ZZT second", expected_qty="3")])
    mine = s.ok(w.rep.me.call("POST", npa.SUB, json=body), 201).json()
    theirs = s.ok(w.rep.portal.call("POST", npa.SUB, json=body), 201).json()
    assert mine["id"] != theirs["id"]
    db = w.sc.db
    assert _stored(db, NewProductApplication, mine["id"]) == _stored(db, NewProductApplication, theirs["id"])
    a = _lines(db, NewProductApplicationLine, "application_id", mine["id"])
    b = _lines(db, NewProductApplicationLine, "application_id", theirs["id"])
    assert a == b and len(a) == 2
    assert set(mine) == set(theirs)


# The amount as the portal form sends it: a typed string, or the lines' total as "toFixed(2)", or the empty string
# when no line is priced and nothing was typed. Lines: qty a number, unit_price a number (or null when blank).
_SO_CASES = {
    "typed_amount_with_priced_line": {"expected_amount": "1234.50", "lines": [{"qty": 2, "unit_price": 10.5}]},
    "lines_total_amount": {"expected_amount": "21.00", "lines": [{"qty": 2, "unit_price": 10.5}]},
    "unpriced_line": {"expected_amount": "500", "lines": [{"qty": 3, "unit_price": None}]},
    "blank_amount_no_lines": {"expected_amount": "", "lines": []},
    "zero_amount_no_lines": {"expected_amount": "0", "lines": []},
}


@pytest.mark.parametrize("case", sorted(_SO_CASES))
def test_par6_sales_opportunity_same_body_stores_the_same_row(sr_so, case):
    from app.models.sales import SalesOpportunity, SalesOpportunityLine

    w = sr_so
    spec = _SO_CASES[case]
    body = w.so_body(expected_amount=spec["expected_amount"], prospect_name=None, customer_id=w.rep.mine.id)
    body["lines"] = [{"product_id": w.product.id, **ln} for ln in spec["lines"]]
    mine = w.rep.me.call("POST", srso.SO_PORTAL, json=body)
    theirs = w.rep.portal.call("POST", srso.SO_PORTAL, json=body)
    s.not_a_missing_route(mine)
    # Whatever the portal answers for this body, my-requests answers the same (status and error body).
    assert mine.status_code == theirs.status_code, (mine.status_code, mine.text, theirs.status_code, theirs.text)
    if theirs.status_code >= 400:
        assert mine.json() == theirs.json()
        # The blank amount is refused by both (the portal form blocks it client side, so it never sends one).
        assert case == "blank_amount_no_lines" and theirs.status_code == 422, (case, theirs.status_code, theirs.text)
        return
    assert theirs.status_code == 201, theirs.text
    db = w.sc.db
    a, b = mine.json(), theirs.json()
    assert a["id"] != b["id"]
    assert _stored(db, SalesOpportunity, a["id"]) == _stored(db, SalesOpportunity, b["id"])
    assert _lines(db, SalesOpportunityLine, "opportunity_id", a["id"]) == _lines(db, SalesOpportunityLine, "opportunity_id", b["id"])
    assert len(_lines(db, SalesOpportunityLine, "opportunity_id", a["id"])) == len(spec["lines"])
    assert (a["expected_amount"], a["stage_key"], a["source"]) == (b["expected_amount"], b["stage_key"], b["source"])


# --------------------------------------------------------------------------- #
# PAR-7: every lookup the three portal forms call                              #
# --------------------------------------------------------------------------- #

SR_LOOKUPS = [
    ("/sample-request/customers", {"q": "ZZT"}),
    ("/sample-request/products", {"q": "ZZT"}),
    ("/lookups/projects", {"q": "ZZT", "limit": 20}),
]
NPA_LOOKUPS = [
    ("/new-product-application/customers", {"q": "ZZT"}),
    ("/new-product-application/inquiries", None),
    ("/new-product-application/lookups/brands", {"q": ""}),
]
SO_LOOKUPS = [
    ("/sales-opportunities/customer-options", {"q": "ZZT"}),
    ("/sales-opportunities/meta", None),
    ("/lookups/products", {"q": "ZZT", "limit": 20}),
]
SR_PERMS = [srso.SR_VIEW, srso.SR_VIEW_OWN, srso.SR_CREATE]
NPA_PERMS = [npa.NPA_VIEW, npa.NPA_VIEW_OWN, npa.NPA_CREATE]
SO_PERMS = [srso.SO_VIEW, srso.SO_VIEW_OWN, srso.SO_ADD]
REP = {"sr": [srso.SR_VIEW_OWN, srso.SR_CREATE], "npa": [npa.NPA_VIEW_OWN, npa.NPA_CREATE], "so": [srso.SO_VIEW_OWN, srso.SO_ADD, srso.SO_EDIT]}
STAFF = {"sr": SR_PERMS, "npa": NPA_PERMS, "so": SO_PERMS}

_ALL = (
    [("sr", p, q) for p, q in SR_LOOKUPS]
    + [("npa", p, q) for p, q in NPA_LOOKUPS]
    + [("so", p, q) for p, q in SO_LOOKUPS]
)
_IDS = [f"{k}:{p}" for k, p, _ in _ALL]


@pytest.fixture
def lk(request, scene):  # noqa: F811
    """The right world for the form the case belongs to."""
    kind = request.node.callspec.params["kind"]
    if kind == "npa":
        return request.getfixturevalue("npa_w")
    return request.getfixturevalue("sr_so")


@pytest.mark.parametrize("kind,path,params", _ALL, ids=_IDS)
def test_par7_lookup_answers_the_same_as_the_portal(lk, kind, path, params):
    w = lk
    mine = w.rep.me.call("GET", path, params=params)
    s.not_a_missing_route(mine)
    theirs = s.ok(w.rep.portal.call("GET", path, params=params))
    assert mine.status_code == theirs.status_code == 200, (mine.status_code, mine.text)
    assert mine.json() == theirs.json()


@pytest.mark.parametrize("kind,path,params", _ALL, ids=_IDS)
def test_par7_lookup_no_session_is_401(lk, kind, path, params):
    w = lk
    s.ok(w.rep.me.call("GET", path, params=params))
    resp = s.Api(w.sc.client, s.MY, {}).call("GET", path, params=params)
    assert resp.status_code == 401, (resp.status_code, resp.text)


@pytest.mark.parametrize("kind,path,params", _ALL, ids=_IDS)
def test_par7_lookup_staff_view_holder_is_403(lk, kind, path, params):
    w = lk
    s.ok(w.rep.me.call("GET", path, params=params))
    c, _portal = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=STAFF[kind], contact=c, name="ZZT Staff")
    resp = s.my_api(w.sc, staff).call("GET", path, params=params)
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)


@pytest.mark.parametrize("kind,path,params", _ALL, ids=_IDS)
def test_par7_lookup_no_linked_contact_is_403(lk, kind, path, params):
    w = lk
    s.ok(w.rep.me.call("GET", path, params=params))
    loner = s.make_user(w.sc.db, perms=REP[kind], name="ZZT Loner")
    resp = s.my_api(w.sc, loner).call("GET", path, params=params)
    s.not_a_missing_route(resp)
    assert resp.status_code == 403, (resp.status_code, resp.text)
