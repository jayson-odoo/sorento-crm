"""NPA-FROM-SI portal surface, red-first: current codes, the reuse suggestion without another
salesperson's application (Q4 (a)), the stock inquiry's ask + own applications, the prefill.

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md. Fixture: the NEW-PRODUCT-APP
portal suite's.
"""
from __future__ import annotations

from datetime import datetime

from app.main import app  # noqa: F401  MUST be first app import (circular import)
from app.models.base import company_scope

from ._sample_request_seed import MARKER, make_product, uid
from .test_portal_new_product_application import (  # noqa: F401  (fixture by import)
    BASE,
    NPA,
    PORTAL,
    _as,
    _create,
    _inquiry,
    _line,
    portal,
)

PRIVATE_KEYS = {"application_id", "application_no", "customer_name", "project_name", "expected_qty"}


def _seed_created(p, sources, *, contact=None, inquiry=None):
    """A completed application whose ONE new product code was linked."""
    from app.models.new_product_application import (
        NewProductApplication,
        NewProductApplicationLine,
        NewProductApplicationSource,
    )

    with company_scope(p.db, frozenset({p.company_id})):
        newp = make_product(p.db)
        app_row = NewProductApplication(
            status="completed",
            source="portal" if contact else "staff",
            contact_id=contact,
            stock_inquiry_id=inquiry.id if inquiry else None,
            customer_name=f"{MARKER} SECRET CUSTOMER",
            project_name=f"{MARKER} SECRET PROJECT",
            new_product_id=newp.id,
            new_code_at=datetime.utcnow(),
        )
        app_row.lines.append(NewProductApplicationLine(line_no=1, description="mirror 600 x 900"))
        app_row.sources = [
            NewProductApplicationSource(id=uid(), product_id=pid, position=i)
            for i, pid in enumerate(sources, start=1)
        ]
        p.db.add(app_row)
        p.db.flush()
    return app_row, newp


def test_portal_product_search_lists_my_companys_products_only(portal):
    p = portal
    res = _as(p, p.granted).get(f"{NPA}/products", params={"q": p.product.product_code})
    assert res.status_code == 200, res.text
    assert [r["id"] for r in res.json()] == [p.product.id]
    assert _as(p, p.granted).get(f"{NPA}/products", params={"q": p.foreign.product_code}).json() == []


def test_portal_product_codes_round_trip(portal):
    p = portal
    d = _create(p, current_product_ids=[p.product.id])
    assert [c["id"] for c in d["current_products"]] == [p.product.id]


def test_portal_cannot_name_another_companys_product(portal):
    p = portal
    res = _as(p, p.granted).post(
        BASE, json={"stock_inquiry_id": p.mine.id, "current_product_ids": [p.foreign.id], "lines": [_line(p)]}
    )
    assert res.status_code == 422


def test_portal_suggestion_names_the_code_but_not_the_other_application(portal):
    p = portal
    _row, newp = _seed_created(p, [p.product.id])
    res = _as(p, p.granted).get(f"{NPA}/reuse-suggestions", params={"product_ids": p.product.id})
    assert res.status_code == 200, res.text
    [s] = res.json()
    assert s["product_code"] == newp.product_code
    assert s["description"] == "mirror 600 x 900"
    assert not (PRIVATE_KEYS & set(s))
    assert "SECRET" not in res.text


def test_portal_detail_suggestions_are_portal_shaped(portal):
    p = portal
    _seed_created(p, [p.product.id])
    d = _create(p, current_product_ids=[p.product.id])
    detail = _as(p, p.granted).get(f"{BASE}/{d['id']}").json()
    [s] = detail["suggestions"]
    assert not (PRIVATE_KEYS & set(s))
    assert "SECRET" not in str(detail["suggestions"])


def test_portal_cannot_link_the_new_code(portal):
    p = portal
    d = _create(p)
    res = _as(p, p.granted).post(f"{BASE}/{d['id']}/new-code/link", json={"product_id": p.product.id})
    assert res.status_code in (404, 405)


def test_portal_inquiry_shows_the_ask_and_only_my_own_applications(portal):
    p = portal
    p.mine.npa_requested = True
    p.db.flush()
    mine = _create(p)
    # Another contact's application on the same inquiry never shows.
    _seed_created(p, [p.product.id], contact=p.granted_b, inquiry=p.mine)
    res = _as(p, p.granted).get(f"{PORTAL}/submissions/stock_inquiry/{p.mine.id}")
    assert res.status_code == 200, res.text
    body = res.json()
    body = body.get("data", body)
    assert body["npa_requested"] is True
    assert [a["id"] for a in body["new_product_applications"]] == [mine["id"]]
    assert body["new_product_applications"][0]["created_codes"] == []


def test_portal_inquiry_lists_the_code_created(portal):
    p = portal
    row, newp = _seed_created(p, [p.product.id], contact=p.granted, inquiry=p.mine)
    body = _as(p, p.granted).get(f"{PORTAL}/submissions/stock_inquiry/{p.mine.id}").json()
    body = body.get("data", body)
    [a] = body["new_product_applications"]
    assert a["application_no"] == row.application_no
    assert a["created_codes"][0]["product_code"] == newp.product_code
    assert a["created_codes"][0]["current_codes"] == [p.product.product_code]


def test_portal_prefill_picks_the_exact_current_code(portal):
    p = portal
    si = _inquiry(p.db, p.granted, product_code=f" {p.product.product_code.lower()} ")
    body = _as(p, p.granted).get(f"{NPA}/prefill", params={"stock_inquiry_id": si.id}).json()
    assert body["current_product_ids"] == [p.product.id]


def test_portal_new_code_facts_show_the_supplier_only(portal):
    p = portal
    row, _newp = _seed_created(p, [p.product.id], contact=p.granted, inquiry=p.mine)
    detail = _as(p, p.granted).get(f"{BASE}/{row.id}").json()
    assert set(detail["new_product_facts"]) == {"opened_supplier_name"}
