"""PORTAL-P4-REQUESTS R3b (PAR-6, PAR-7): Price Tag Request.

The portal's own PriceTagRequestForm runs inside the CRM page over `/api/v1/my-requests`, so:
  PAR-6  the SAME body the portal form sends (customer = `debtor_code ?? customer_code` of the debtors-for-agent
         row, `print_by='self'`, lines as `payloadLines()` builds them) POSTed through the portal and through
         my-requests (same salesperson contact) stores the same row + lines (ids, numbers, timestamps and
         creator-ish columns excluded);
  PAR-7  every lookup the price tag form calls answers my-requests exactly as the portal, and refuses a staff `.view`
         holder (403), no session (401) and a user with no linked contact (403).

The routes already exist on my-requests (`register_price_tag_routes`, no new BE route in R3b), so these are parity
PINS and may be green from the start. Postgres only (blank_session via the S0-B scene), every row seeded here.
The form's lookups are `debtors-for-agent`, `price-tag-items`, `product-combos/{id}`, `line-pricing` (POST); there
is no `lookups/promotions` route on the price tag router (the form no longer calls one, D1).
"""
from __future__ import annotations

import pytest
from sqlalchemy import DateTime, inspect

from tests import _portal_p4_support as s
from tests._portal_p4_pt_support import (  # noqa: F401
    LOOK,
    PT_CREATE,
    PT_VIEW,
    PT_VIEW_OWN,
    SUB,
    pt_row,
    scene,
    world,
)

_SKIP = {
    "id", "doc_number", "created_by_user_id", "updated_by", "created_by", "updated_by_user_id",
    "request_id", "created_by_contact_id",
}


def _cols(row, model, *, extra_skip=()) -> dict:
    out = {}
    for col in inspect(model).columns:
        if col.key in _SKIP or col.key in extra_skip or isinstance(col.type, DateTime):
            continue
        out[col.key] = getattr(row, col.key)
    return out


def _portal_form_body(w, *, line_extra=None) -> dict:
    """What PriceTagRequestForm.handleSaveDraft sends: the first debtors-for-agent row picked, print_by 'self'."""
    debtors = s.ok(w.rep.portal.call("GET", f"{LOOK}/debtors-for-agent")).json()
    pick = debtors[0]
    code = pick.get("debtor_code") or pick.get("customer_code") or ""
    name = pick.get("debtor_name") or pick.get("customer_name") or code
    assert code, "the picked debtor must carry a code the form can send"
    return {
        "debtor_code": code,
        "debtor_name": name,
        "needed_by_date": "2030-01-15",
        "notes": "ZZT portal form note",
        "price_mode": "list",
        "print_by": "self",
        "lines": [{
            "line_type": "product", "product_id": w.product.id, "quantity": 3,
            "included_accessories": None, "remarks": "ZZT line remark",
            **(line_extra or {}),
        }],
    }


def test_par6_same_portal_form_body_stores_the_same_row_and_lines(world):
    from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

    w = world
    body = _portal_form_body(w)
    assert body["debtor_code"] in {c.customer_code for c in w.rep.customers}
    mine = s.ok(w.rep.me.call("POST", SUB, json=body), 201).json()
    theirs = s.ok(w.rep.portal.call("POST", SUB, json=body), 201).json()
    assert mine["id"] != theirs["id"]
    a, b = pt_row(w, mine["id"]), pt_row(w, theirs["id"])
    assert _cols(a, PriceTagRequest) == _cols(b, PriceTagRequest)
    assert a.debtor_code == body["debtor_code"] and a.print_by == "self"
    assert a.portal_draft_at is not None and a.contact_id == w.rep.contact.id
    la = [_cols(x, PriceTagRequestLine, extra_skip=("request_id",)) for x in a.lines]
    lb = [_cols(x, PriceTagRequestLine, extra_skip=("request_id",)) for x in b.lines]
    assert la == lb and len(la) == 1
    assert (la[0]["quantity"], la[0]["remarks"]) == (3, "ZZT line remark")
    assert set(mine) == set(theirs)


def test_par6_a_blank_draft_as_the_form_saves_it_is_the_same_row(world):
    """Save draft validates nothing (D48a): no customer, no lines, still print_by 'self'."""
    from app.models.price_tag import PriceTagRequest

    w = world
    body = {"debtor_code": None, "debtor_name": None, "needed_by_date": None, "notes": None,
            "price_mode": "list", "print_by": "self", "lines": []}
    mine = s.ok(w.rep.me.call("POST", SUB, json=body), 201).json()
    theirs = s.ok(w.rep.portal.call("POST", SUB, json=body), 201).json()
    assert _cols(pt_row(w, mine["id"]), PriceTagRequest) == _cols(pt_row(w, theirs["id"]), PriceTagRequest)
    assert pt_row(w, mine["id"]).print_by == "self"


def test_par6_save_over_an_open_draft_is_the_same_through_both(world):
    from app.models.price_tag import PriceTagRequest

    w = world
    body = _portal_form_body(w)
    ids = {}
    for name, api in (("me", w.rep.me), ("portal", w.rep.portal)):
        rid = s.ok(api.call("POST", SUB, json=body), 201).json()["id"]
        s.ok(api.call("PUT", f"{SUB}/{rid}", json={**body, "notes": "ZZT second save", "price_mode": "list"}))
        ids[name] = rid
    a, b = pt_row(w, ids["me"]), pt_row(w, ids["portal"])
    assert _cols(a, PriceTagRequest) == _cols(b, PriceTagRequest) and a.notes == "ZZT second save"


# --------------------------------------------------------------------------- #
# PAR-7: every lookup the price tag form calls                                #
# --------------------------------------------------------------------------- #


def _lookups(w):
    return [
        ("GET", f"{LOOK}/debtors-for-agent", {"params": {"q": ""}}),
        ("GET", f"{LOOK}/debtors-for-agent", {"params": {"q": w.rep.customers[0].customer_code}}),
        ("GET", f"{LOOK}/price-tag-items", {"params": {"q": w.product.product_code}}),
        ("GET", f"{LOOK}/product-combos/{w.product.id}", {}),
        ("POST", f"{LOOK}/line-pricing", {"json": {"lines": [
            {"key": "k1", "product_id": w.product.id, "part_product_ids": [], "candidate_product_ids": []}]}}),
    ]


def test_par7_lookups_answer_the_same_as_the_portal(world):
    w = world
    for method, path, kw in _lookups(w):
        mine = w.rep.me.call(method, path, **kw)
        s.not_a_missing_route(mine)
        theirs = s.ok(w.rep.portal.call(method, path, **kw))
        assert mine.status_code == theirs.status_code == 200, (path, mine.status_code, mine.text)
        assert mine.json() == theirs.json(), path
    items = s.ok(w.rep.me.call("GET", f"{LOOK}/price-tag-items", params={"q": w.product.product_code})).json()
    assert any(i["id"] == w.product.id for i in items)


def test_par7_lookups_no_session_is_401(world):
    w = world
    s.ok(w.rep.me.call("GET", f"{LOOK}/debtors-for-agent"))
    for method, path, kw in _lookups(w):
        resp = s.Api(w.sc.client, s.MY, {}).call(method, path, **kw)
        assert resp.status_code == 401, (path, resp.status_code, resp.text)


def test_par7_lookups_staff_view_holder_is_403(world):
    w = world
    s.ok(w.rep.me.call("GET", f"{LOOK}/debtors-for-agent"))
    contact, _portal = s.own_contact(w.sc)
    staff = s.make_user(w.sc.db, perms=[PT_VIEW, PT_VIEW_OWN, PT_CREATE], contact=contact, name="ZZT Staff")
    for method, path, kw in _lookups(w):
        resp = s.my_api(w.sc, staff).call(method, path, **kw)
        s.not_a_missing_route(resp)
        assert resp.status_code == 403, (path, resp.status_code, resp.text)


def test_par7_lookups_no_linked_contact_is_403(world):
    w = world
    s.ok(w.rep.me.call("GET", f"{LOOK}/debtors-for-agent"))
    loner = s.make_user(w.sc.db, perms=[PT_VIEW_OWN, PT_CREATE], name="ZZT Loner")
    for method, path, kw in _lookups(w):
        resp = s.my_api(w.sc, loner).call(method, path, **kw)
        s.not_a_missing_route(resp)
        assert resp.status_code == 403, (path, resp.status_code, resp.text)
