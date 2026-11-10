"""COMBO-SETTINGS-UX owner round 1 (10 Nov 18:2x, crew ruling): a choice group with ONE part is a
FIXED part everywhere (CARD-pricetag-combo-render-04nov.md:134 "one option resolves on the spot").
A choice is a group of 2+ parts. Synthetic data only.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace as NS

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.dealer_kit.pricing import combo_prices
from app.services.dealer_kit.template_needs import combo_shape

from tests import _ptag_combo_seed as seed
from tests.test_pricetag_combo_format_browser_fixes import STAFF_PREVIEW
from tests.test_product_tag_templates import _template, env  # noqa: F401


def _p(pid, group=None, *, upgrade=False, sell=None):
    return NS(part_product_id=pid, choice_group=group, is_upgrade=upgrade, sell_price=sell, topup_amount=None)


def test_combo_shape_counts_a_one_part_group_as_fixed():
    combo = NS(parts=[_p("a"), _p("b", "Test"), _p("c", "TAP"), _p("d", "TAP"), _p("u", upgrade=True)])
    assert combo_shape(combo) == {"fixed": 2, "groups": [{"role": "TAP", "size": 2}], "upgrades": 1}


def test_a_one_part_group_never_sets_the_sell_price():
    alone = _p("b", "Test", sell=Decimal("50"))
    no_combo_price = NS(list_price=Decimal("880"), sell_price=None, parts=[_p("a"), alone])
    # Not an open priced choice (nothing to pick), and its own price is not a pick's price.
    assert combo_prices(no_combo_price, set()) == (Decimal("880"), None, False)
    assert combo_prices(no_combo_price, {"b"}) == (Decimal("880"), None, False)
    with_combo_price = NS(list_price=Decimal("880"), sell_price=Decimal("700"), parts=[_p("a"), alone])
    assert combo_prices(with_combo_price, {"b"}) == (Decimal("880"), Decimal("700.00"), True)


def test_a_real_choice_still_prices_by_its_pick():
    combo = NS(
        list_price=Decimal("880"),
        sell_price=None,
        parts=[_p("c", "TAP", sell=Decimal("899")), _p("d", "TAP", sell=Decimal("1099"))],
    )
    assert combo_prices(combo, {"d"}) == (Decimal("880"), Decimal("1099.00"), True)
    assert combo_prices(combo, set()) == (Decimal("880"), None, True)


def _world(db):
    host = seed.product(db, "ZZOPGH", list_price="1000.00")
    fixed = seed.product(db, "ZZOPGF", list_price="100.00")
    alone = seed.product(db, "ZZOPGA", list_price="60.00")
    tap1 = seed.product(db, "ZZOPGT1", list_price="300.00")
    tap2 = seed.product(db, "ZZOPGT2", list_price="400.00")
    cb = seed.combo(
        db, host, "ZZT one part group",
        parts=[
            {"product": fixed},
            {"product": alone, "group": "Test", "sell_price": Decimal("50")},
            {"product": tap1, "group": "TAP"},
            {"product": tap2, "group": "TAP"},
        ],
    )
    template_id = _template(db, "OPG")
    from app.models.dealer_kit import ComboTagTemplate

    db.add(ComboTagTemplate(combo_id=cb.id, template_id=template_id))
    db.flush()
    return host, cb, template_id, fixed, alone, tap1


def test_tag_preview_places_a_one_part_group_with_the_fixed_parts(env):  # noqa: F811
    db, c, _ = env
    host, cb, template_id, fixed, alone, tap1 = _world(db)
    body = {
        "price_mode": "list",
        "lines": [
            {
                "key": "k", "line_type": "product", "product_id": host.id, "combo_id": cb.id,
                "tag_template_id": template_id, "price_type": "selling",
                "parts": [
                    {"product_id": fixed.id},
                    {"product_id": alone.id, "role": "Test"},
                    {"product_id": tap1.id, "role": "TAP"},
                ],
            }
        ],
    }
    res = c.post(STAFF_PREVIEW, json=body)
    assert res.status_code == 200, res.text
    (line,) = res.json()["lines"]
    assert [p["product_id"] for p in line["slots"]["fixed"]] == [fixed.id, alone.id]
    assert [g["role"] for g in line["slots"]["groups"]] == ["TAP"]
    assert [g["role"] for g in line["combo"]["choices"]] == ["TAP"]


def test_product_tag_data_preview_combo_places_a_one_part_group_with_the_fixed_parts(env):  # noqa: F811
    db, c, _ = env
    host, cb, _template_id, fixed, alone, _tap1 = _world(db)
    res = c.get(f"/api/v1/dealer-kit/products/{host.id}/tag-data", params={"combo_id": cb.id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert [p["product_id"] for p in body["slots"]["fixed"]] == [fixed.id, alone.id]
    assert [g["role"] for g in body["slots"]["groups"]] == ["TAP"]
    assert [g["role"] for g in body["combo"]["choices"]] == ["TAP"]
