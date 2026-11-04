"""PRICETAG-COMBO-RENDER K8 / AC-D1 to D3: a combo line's price is stored or nothing, never a sum.

Written test-FIRST. Today a combo with no stored price falls back to the sum of the parts.

Decisions where the plan is open:
* The line-pricing lookup answers `list_price: null` for a combo with no stored list price,
  so `LinePricingRow.list_price` must become optional (it is a bare `float` today).
* A typed (manual) line price still wins the sell side, on tag data and in the lookup.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session
from tests.test_price_tag_combo_tag_data import crm  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

D = Decimal


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )


def _row(db, s, parts, **kwargs):
    request = seed.submit_one(db, s["host"], s["combo"], parts, **kwargs)
    db.flush()
    return seed.rows(db, request)[0], request


def _pricing(db, s, part_ids, **extra):
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    line = {
        "key": "L1",
        "product_id": s["host"].id,
        "part_product_ids": part_ids,
        "candidate_product_ids": [],
        "combo_id": s["combo"].id,
        **extra,
    }
    (priced,) = line_pricing(db, lines=[line], viewer=tag_data_service.staff_viewer())
    return priced


# --------------------------------------------------------------------------- tag data


def test_s3_no_stored_price_prints_nothing_on_an_lp_line(db):
    s = shapes.s3(db)
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][0]), price_mode="list")
    assert row["list_price"] is None
    assert row["sell_price"] is None


def test_s3_no_stored_price_prints_nothing_on_an_sp_line(db):
    s = shapes.s3(db)
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][0]), price_mode="selling")
    assert row["list_price"] is None
    assert row["sell_price"] is None


def test_s4_fixed_parts_only_is_not_summed_either(db):
    s = shapes.s4(db)
    row, _ = _row(db, s, shapes.fixed_parts(*s["fixed"]))
    assert row["list_price"] is None
    assert row["sell_price"] is None


def test_s1_with_the_upgrade_picked_and_no_stored_price_prints_nothing(db):
    s = shapes.s1(db, "ZZT S5")
    parts = shapes.pick_parts(s["group"], s["options"][0]) + [shapes.upgrade_part(s["upgrade"])]
    row, _ = _row(db, s, parts)
    assert row["list_price"] is None
    assert row["sell_price"] is None


def test_a_typed_price_prints_on_a_combo_with_no_stored_price(db):
    s = shapes.s3(db)
    row, _ = _row(
        db,
        s,
        shapes.pick_parts(s["group"], s["options"][0]),
        price_mode="selling",
        manual_sell_price="1234.00",
    )
    assert row["sell_price"] == D("1234.00")
    assert row["list_price"] is None


def test_the_stored_combo_list_and_sell_price_print(db):
    s = shapes.s3(db, list_price=D("900.00"), sell_price=D("800.00"))
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][0]), price_mode="selling")
    assert row["list_price"] == D("900.00")
    assert row["sell_price"] == D("800.00")


def test_a_stored_list_price_alone_leaves_the_sell_price_empty(db):
    s = shapes.s3(db, list_price=D("900.00"))
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][0]), price_mode="selling")
    assert row["list_price"] == D("900.00")
    assert row["sell_price"] is None


def test_the_picked_options_own_price_still_decides(db):
    from app.models.product_combo import ProductComboPart

    s = shapes.s3(db, list_price=D("900.00"))
    black, rose = s["options"]
    part = (
        db.query(ProductComboPart)
        .filter(ProductComboPart.combo_id == s["combo"].id, ProductComboPart.part_product_id == rose.id)
        .one()
    )
    part.sell_price = D("750.00")
    db.flush()
    db.expire(s["combo"], ["parts"])
    row, _ = _row(db, s, shapes.pick_parts(s["group"], rose), price_mode="selling")
    assert row["sell_price"] == D("750.00")
    other, _ = _row(db, s, shapes.pick_parts(s["group"], black), price_mode="selling")
    assert other["sell_price"] is None, "the other option has no price of its own and the combo has none"


def test_a_picked_upgrade_adds_its_topup_to_a_stored_price(db):
    s = shapes.s1(db, "ZZT S5", list_price=D("3000.00"), sell_price=D("2500.00"))
    parts = shapes.pick_parts(s["group"], s["options"][0]) + [shapes.upgrade_part(s["upgrade"])]
    row, _ = _row(db, s, parts, price_mode="selling")
    assert row["sell_price"] == D("2650.00")


def test_a_line_without_a_combo_still_sums_its_parts(db):
    s = shapes.s3(db)
    request = seed.submit_one(
        db, s["host"], None, shapes.pick_parts(s["group"], s["options"][0]), price_mode="list"
    )
    db.flush()
    row = seed.rows(db, request)[0]
    assert row["list_price"] == D("650.00")  # 500 host + 150 part
    assert row["sell_price"] == D("650.00")


# --------------------------------------------------------------------------- line pricing lookup


def test_lookup_no_stored_price_answers_nothing_for_list_and_sell(db):
    s = shapes.s3(db)
    priced = _pricing(db, s, [s["options"][0].id])
    assert priced["list_price"] is None
    assert priced["sell_price"] is None


def test_lookup_typed_price_still_wins(db):
    s = shapes.s3(db)
    priced = _pricing(db, s, [s["options"][0].id], manual_sell_price="1234.00")
    assert D(str(priced["sell_price"])) == D("1234.00")
    assert priced["list_price"] is None


def test_lookup_stored_prices_are_answered(db):
    s = shapes.s3(db, list_price=D("900.00"), sell_price=D("800.00"))
    priced = _pricing(db, s, [s["options"][0].id])
    assert D(str(priced["list_price"])) == D("900.00")
    assert D(str(priced["sell_price"])) == D("800.00")


def test_lookup_fixed_only_combo_is_not_summed(db):
    s = shapes.s4(db)
    priced = _pricing(db, s, [item.id for item in s["fixed"]])
    assert priced["list_price"] is None
    assert priced["sell_price"] is None


def test_lookup_without_a_combo_id_still_sums(db):
    s = shapes.s3(db)
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    (priced,) = line_pricing(
        db,
        lines=[
            {
                "key": "L1",
                "product_id": s["host"].id,
                "part_product_ids": [s["options"][0].id],
                "candidate_product_ids": [],
            }
        ],
        viewer=tag_data_service.staff_viewer(),
    )
    assert D(str(priced["list_price"])) == D("650.00")


def test_the_crm_line_pricing_route_answers_null_list_price_for_an_unpriced_combo(crm):  # noqa: F811
    client, db = crm
    s = shapes.s3(db)
    db.commit()
    response = client.post(
        "/api/v1/dealer-kit/price-tag-requests/line-pricing",
        json={
            "lines": [
                {
                    "key": "L1",
                    "product_id": s["host"].id,
                    "part_product_ids": [s["options"][0].id],
                    "candidate_product_ids": [],
                    "combo_id": s["combo"].id,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    (priced,) = response.json()
    assert priced["list_price"] is None
    assert priced["sell_price"] is None
