"""PROJECT-QUOTE-LINE-TOOLS AC-7: the live line verdict says "below default price" by the SAME
rule the save stores `is_discounted` by (series selling price where the series names the
product or set, else the list price; no default = never below).

Red-first: written before the implementation. Rows are seeded on a blank Postgres schema;
prices are invented.
"""
from __future__ import annotations

from .test_project_series_product_routes import BASE, _quotation
from .test_series_brand_scope import _series, world  # noqa: F401
from .test_set_quote_line import (  # noqa: F401  (api is a fixture)
    _api_quotation,
    _api_series,
    _catalogue,
    _set,
    api,
)

VERDICT = f"{BASE}/quotation-line-verdict"


def _price(w, series_id, product_id, price, pct=None):
    r = w.client.patch(
        f"{BASE}/config/series/{series_id}/products/{product_id}",
        json={"selling_price": price, "max_discount_pct": pct},
    )
    assert r.status_code == 200, r.text


def _judge(w, **params):
    r = w.client.get(VERDICT, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_below_the_series_price_is_discounted_and_at_it_is_not(world):
    s = _series(world, world.a.id, [world.parent.id])
    # Series price 1200 over a list price of 1000: the series price is the default.
    _price(world, s["id"], world.a1.id, "1200.00", "20")
    below = _judge(world, series_id=s["id"], product_id=world.a1.id, unit_price="1100.00")
    at = _judge(world, series_id=s["id"], product_id=world.a1.id, unit_price="1200.00")
    assert below["is_discounted"] is True
    # Above the minimum price (960), so only the default-price fact is true.
    assert below["is_below_floor"] is False
    assert at["is_discounted"] is False


def test_with_no_series_row_the_list_price_is_the_default(world):
    below = _judge(world, product_id=world.a1.id, unit_price="999.99")
    at = _judge(world, product_id=world.a1.id, unit_price="1000.00")
    assert below["is_discounted"] is True
    assert at["is_discounted"] is False


def test_no_price_typed_yet_is_not_discounted(world):
    assert _judge(world, product_id=world.a1.id)["is_discounted"] is False
    # Mid-keystroke garbage is "no price yet" for the verdict, never an error.
    assert _judge(world, product_id=world.a1.id, unit_price="1,2")["is_discounted"] is False


def test_a_set_with_no_price_basis_and_no_series_row_is_never_discounted(api):
    # products.list_price is NOT NULL, so "no default" only happens on a set whose parts
    # contribute no price and that carries no override, judged with no series row.
    client, db, company_id, _user_id, _project = api
    category, uom = _catalogue(db)
    bare = _set(db, company_id, category, uom, parts=[])
    db.commit()
    r = client.get(VERDICT, params={"product_set_id": bare.id, "unit_price": "0"})
    assert r.status_code == 200, r.text
    assert r.json()["is_discounted"] is False


def test_live_verdict_matches_what_the_save_stores(world):
    s = _series(world, world.a.id, [world.parent.id])
    _price(world, s["id"], world.a1.id, "1200.00", "20")
    q = _quotation(world.client, world.project.id)
    world.client.put(f"{BASE}/quotations/{q['id']}", json={"series_id": s["id"]})
    version_id = q["current_version_id"]
    for price, expected in (("1100.00", True), ("1200.00", False)):
        saved = world.client.post(
            f"{BASE}/quotation-versions/{version_id}/lines",
            json={"product_id": world.a1.id, "unit_price": price, "quantity": "1"},
        )
        assert saved.status_code in (200, 201), saved.text
        live = world.client.get(
            f"{BASE}/quotations/{q['id']}/line-verdict",
            params={"product_id": world.a1.id, "unit_price": price},
        ).json()
        assert saved.json()["is_discounted"] is expected
        assert live["is_discounted"] is expected


def test_a_set_is_judged_against_its_series_set_row(api):
    client, db, company_id, _user_id, project = api
    category, uom = _catalogue(db)
    listed = _set(db, company_id, category, uom)
    db.commit()
    series = _api_series(client, "Default")
    client.patch(
        f"{BASE}/config/series/{series['id']}/sets/{listed.id}",
        json={"selling_price": "1000.00", "max_discount_pct": "10.00"},
    )
    quotation = _api_quotation(client, project.id)
    client.put(f"{BASE}/quotations/{quotation['id']}", json={"series_id": series["id"]})

    def judge(price):
        r = client.get(
            f"{BASE}/quotations/{quotation['id']}/line-verdict",
            params={"product_set_id": listed.id, "unit_price": price},
        )
        assert r.status_code == 200, r.text
        return r.json()

    assert judge("950.00")["is_discounted"] is True
    assert judge("950.00")["is_below_floor"] is False
    assert judge("1000.00")["is_discounted"] is False
