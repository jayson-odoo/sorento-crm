"""PRICING-UX-FIXES (UAC A1-A5, B1-B6): live line verdict without a saved quotation, the
owner's two series rulings (Q1 exclusion, Q2 price-only floor).

Red-first: written before the implementation. Every row is seeded on a blank Postgres schema;
prices are invented.
"""
from __future__ import annotations

from decimal import Decimal

from .test_project_series_product_routes import BASE, _client, _quotation
from .test_series_brand_scope import _rows, _series, world  # noqa: F401

VERDICT = f"{BASE}/quotation-line-verdict"


def _price(w, series_id, product_id, price, pct=None):
    r = w.client.patch(
        f"{BASE}/config/series/{series_id}/products/{product_id}",
        json={"selling_price": price, "max_discount_pct": pct},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------- A: verdict with no quotation (new scope)


def test_a1_verdict_by_series_flags_below_minimum_price_without_a_quotation(world):
    s = _series(world, world.a.id, [world.parent.id])
    _price(world, s["id"], world.a1.id, "1000.00", "10")
    r = world.client.get(
        VERDICT,
        params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "800.00"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_below_floor"] is True
    assert body["is_non_standard"] is False
    assert Decimal(body["floor_value"]) == Decimal("900.00")

    ok = world.client.get(
        VERDICT,
        params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "950.00"},
    ).json()
    assert ok["is_below_floor"] is False


def test_a2_verdict_by_series_flags_a_product_outside_the_series(world):
    s = _series(world, world.a.id, [world.parent.id])
    body = world.client.get(
        VERDICT, params={"series_id": s["id"], "product_id": world.b1.id, "unit_price": "1"}
    ).json()
    assert body["is_non_standard"] is True


def test_a3_with_no_series_nothing_is_non_standard(world):
    body = world.client.get(
        VERDICT, params={"product_id": world.b1.id, "unit_price": "1"}
    ).json()
    assert body["is_non_standard"] is False


def test_a3b_half_typed_price_is_not_an_error(world):
    s = _series(world, world.a.id, [world.parent.id])
    r = world.client.get(
        VERDICT, params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "12."}
    )
    assert r.status_code == 200, r.text


def test_a4_verdict_needs_project_read_permission(world):
    from app.services.user_service import UserPermissionService

    from .test_project_series_product_routes import _user

    # A second client re-patches the permission check; the world's own patch is put back after.
    client, world_patch = _client(world.db, _user(world.db), slugs=["projects.types.view"])
    try:
        r = client.get(VERDICT, params={"product_id": world.a1.id})
        assert r.status_code == 403, r.text
    finally:
        UserPermissionService.check_user_has_permission = world_patch[0]
        UserPermissionService.get_user_permission_slugs = world_patch[1]


def test_a5_own_scope_guard_lets_a_view_own_user_ask(world):
    from app.api.v1.projects import _own_scope

    assert _own_scope.classify("GET", "/api/v1/project-sales/quotation-line-verdict") == "open"


def test_a6_saved_quotation_route_still_answers(world):
    s = _series(world, world.a.id, [world.parent.id])
    _price(world, s["id"], world.a1.id, "1000.00", "10")
    q = _quotation(world.client, world.project.id)
    world.client.put(f"{BASE}/quotations/{q['id']}", json={"series_id": s["id"]})
    body = world.client.get(
        f"{BASE}/quotations/{q['id']}/line-verdict",
        params={"product_id": world.a1.id, "unit_price": "800.00"},
    ).json()
    assert body["is_below_floor"] is True


# ------------------------------------------------- Q2: a price with no max discount


def test_q2_price_only_floor_is_the_selling_price():
    from app.services.project_pricing_service import series_floor

    assert series_floor(Decimal("220.00"), None) == Decimal("220.00")
    assert series_floor(Decimal("220.00"), Decimal("6")) == Decimal("206.80")
    assert series_floor(None, Decimal("6")) is None


def test_q2_price_only_row_shows_a_floor_and_a_line_below_it_is_flagged(world):
    s = _series(world, world.a.id, [world.parent.id])
    row = _price(world, s["id"], world.a1.id, "1000.00", None)
    assert Decimal(row["derived_floor"]) == Decimal("1000.00")
    assert Decimal(_rows(world, s["id"])["ZZT-A-1"]["derived_floor"]) == Decimal("1000.00")
    body = world.client.get(
        VERDICT,
        params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "999.99"},
    ).json()
    assert body["is_below_floor"] is True
    assert Decimal(body["floor_value"]) == Decimal("1000.00")


# ------------------------------------------------- Q1: remove an in-scope product = exclusion


def test_q1_removing_an_in_scope_product_drops_it_from_the_series(world):
    s = _series(world, world.a.id, [world.parent.id])
    assert "ZZT-A-1" in _rows(world, s["id"])
    r = world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.a1.id}")
    assert r.status_code == 204, r.text
    assert "ZZT-A-1" not in _rows(world, s["id"])
    assert "ZZT-A-2" in _rows(world, s["id"])  # the rest of the scope is untouched
    body = world.client.get(
        VERDICT, params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "1"}
    ).json()
    assert body["is_non_standard"] is True


def test_q1_a_removed_priced_product_no_longer_prices(world):
    s = _series(world, world.a.id, [world.parent.id])
    _price(world, s["id"], world.a1.id, "1000.00", "10")
    world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.a1.id}")
    body = world.client.get(
        VERDICT,
        params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "800.00"},
    ).json()
    assert body["floor_level"] != "series"
    listed = world.client.get(f"{BASE}/config/series?include_inactive=true").json()["data"]
    mine = next(row for row in listed if row["id"] == s["id"])
    assert "ZZT-A-1" not in (mine.get("product_codes") or [])


def test_q1_a_removed_product_can_be_added_back_by_pricing_it(world):
    s = _series(world, world.a.id, [world.parent.id])
    world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.a1.id}")
    row = _price(world, s["id"], world.a1.id, "500.00", "5")
    assert row["product_code"] == "ZZT-A-1"
    assert "ZZT-A-1" in _rows(world, s["id"])
    body = world.client.get(
        VERDICT, params={"series_id": s["id"], "product_id": world.a1.id, "unit_price": "1"}
    ).json()
    assert body["is_non_standard"] is False


def test_q1_a_removed_product_can_be_added_back_by_code(world):
    s = _series(world, world.a.id, [world.parent.id])
    world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.a1.id}")
    r = world.client.post(
        f"{BASE}/config/series/{s['id']}/products",
        json={"codes": ["ZZT-A-1"], "mode": "append"},
    )
    assert r.status_code == 200, r.text
    assert "ZZT-A-1" in _rows(world, s["id"])


def test_q1_an_import_does_not_undo_an_exclusion_it_does_not_name(world):
    s = _series(world, world.a.id, [world.parent.id])
    world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.a1.id}")
    world.client.post(
        f"{BASE}/config/series/{s['id']}/products",
        json={"codes": ["ZZT-A-2"], "mode": "append"},
    )
    assert "ZZT-A-1" not in _rows(world, s["id"])


def test_q1_removing_a_named_out_of_scope_product_still_deletes_it(world):
    s = _series(world, world.a.id, [world.parent.id])
    world.client.post(
        f"{BASE}/config/series/{s['id']}/products",
        json={"codes": ["ZZT-B-1"], "mode": "append"},
    )
    assert "ZZT-B-1" in _rows(world, s["id"])
    r = world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.b1.id}")
    assert r.status_code == 204, r.text
    assert "ZZT-B-1" not in _rows(world, s["id"])


def test_q1_removing_a_product_the_series_never_had_is_404(world):
    s = _series(world, world.a.id, [world.parent.id])
    r = world.client.delete(f"{BASE}/config/series/{s['id']}/products/{world.b1.id}")
    assert r.status_code == 404, r.text
