"""PRICETAG-COMBO-RENDER fix round 1 (B1, L1): `slots` on a pinned tag.

A pinned tag keeps the data of the pin (r9). The only thing read fresh is the tag's own pick of a
group left open, exactly like `combo.picked`: it re-chooses among the candidates the pin holds and
never re-reads master data.
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


def _open_group(db, s, count=2):
    """An S1 line whose tap group is left open between the first `count` options; pinned by the first read."""
    parts = [{"product_id": None, "role": "Kitchen tap", "candidates": [x.id for x in s["options"][:count]]}]
    request = seed.submit_one(db, s["host"], s["combo"], parts)
    db.flush()
    seed.rows(db, request)  # pins the tag
    return request, request.lines[0].tags[0]


def _reread(db, request, tag):
    db.expire_all()
    (row,) = [r for r in seed.rows(db, request) if r["tag_id"] == tag.id]
    return row


def test_a_choice_made_after_the_pin_keeps_the_pinned_position_data(db):
    s = shapes.s1(db)
    request, tag = _open_group(db, s)
    pinned_price = s["options"][1].list_price
    tag.choices = {"Kitchen tap": s["options"][1].id}
    s["options"][1].list_price = D("999.00")
    db.flush()
    row = _reread(db, request, tag)
    (pick,) = row["slots"]["groups"][0]["picks"]
    assert pick["code"] == "SRTKT1863SS"
    assert pick["list_price"] == pinned_price, "the pin is not rebuilt from master data"


def test_changing_the_choice_swaps_the_pick_among_the_pinned_candidates(db):
    s = shapes.s1(db)
    request, tag = _open_group(db, s)
    tag.choices = {"Kitchen tap": s["options"][0].id}
    db.flush()
    assert shapes.codes(_reread(db, request, tag)["slots"]["groups"][0]["picks"]) == ["SRTKT1862SS"]
    tag.choices = {"Kitchen tap": s["options"][1].id}
    db.flush()
    assert shapes.codes(_reread(db, request, tag)["slots"]["groups"][0]["picks"]) == ["SRTKT1863SS"]


def test_a_list_price_request_prints_no_offer_on_a_position(db):
    s = shapes.s1(db)
    promo = seed.promotion(db, [(s["options"][0], "50.00")])
    parts = shapes.pick_parts(s["group"], s["options"][0])
    request = seed.submit_one(db, s["host"], s["combo"], parts, price_mode="list", promotion_id=promo.id)
    db.flush()
    row = seed.rows(db, request)[0]
    assert row["slots"]["groups"][0]["picks"][0]["sell_price"] is None
    request = seed.submit_one(db, s["host"], s["combo"], parts, price_mode="selling", promotion_id=promo.id)
    db.flush()
    assert seed.rows(db, request)[0]["slots"]["groups"][0]["picks"][0]["sell_price"] == D("50.00")


# --------------------------------------------------------------------------- S6: main


def test_slots_carry_the_main_products_own_data(db):
    s = shapes.s1(db, list_price=D("2600.00"))
    row = seed.rows(db, seed.submit_one(db, s["host"], s["combo"], shapes.pick_parts(s["group"], s["options"][0])))[0]
    main = row["slots"]["main"]
    assert main["code"] == "SRTKS7061"
    assert main["list_price"] == D("2000.00"), "the host's own list price, not the combo's 2600"
    assert row["list_price"] == D("2600.00")


def test_the_pinned_main_keeps_its_pinned_value(db):
    s = shapes.s1(db)
    request = seed.submit_one(db, s["host"], s["combo"], shapes.pick_parts(s["group"], s["options"][0]))
    db.flush()
    seed.rows(db, request)
    s["host"].list_price = D("1.00")
    db.flush()
    db.expire_all()
    assert seed.rows(db, request)[0]["slots"]["main"]["list_price"] == D("2000.00")


def test_the_preview_carries_main(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s1(db)
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    out = tag_data_service.with_preview_combo(db, s["host"], data, s["combo"].id)
    assert out["slots"]["main"]["code"] == "SRTKS7061"


def test_re_choosing_the_upgrade_after_the_pin_leaves_exactly_one_chosen(db):
    s = shapes.s1(db)
    s["upgrade2"] = shapes.prod(db, "SRTKT72SS", list_price="650.00")
    combo = seed.combo(
        db, s["host"], "ZZT S1 two ups",
        parts=[{"product": s["options"][0], "group": s["group"]}, {"product": s["upgrade"], "is_upgrade": True},
               {"product": s["upgrade2"], "is_upgrade": True}],
    )
    parts = shapes.pick_parts(s["group"], s["options"][0]) + [
        {"product_id": None, "role": "Upgrade", "candidates": [s["upgrade"].id, s["upgrade2"].id]}
    ]
    request = seed.submit_one(db, s["host"], combo, parts)
    db.flush()
    tag = request.lines[0].tags[0]
    tag.choices = {"Upgrade": s["upgrade"].id}
    db.flush()
    seed.rows(db, request)  # pins with the first upgrade chosen
    first = _reread(db, request, tag)["slots"]["upgrades"]
    assert [u["chosen"] for u in first] == [True, False]
    tag.choices = {"Upgrade": s["upgrade2"].id}
    db.flush()
    second = _reread(db, request, tag)["slots"]["upgrades"]
    assert [u["code"] for u in second if u["chosen"]] == ["SRTKT72SS"]


def test_the_preview_prints_what_the_tag_prints_for_a_combo_with_no_price(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s3(db)
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    assert data["list_price"] is not None, "the host has a list price of its own"
    out = tag_data_service.with_preview_combo(db, s["host"], data, s["combo"].id)
    assert out["list_price"] is None and out["offer_price"] is None


def test_the_preview_shows_the_combos_stored_prices(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s3(db, list_price=D("900.00"), sell_price=D("800.00"))
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    out = tag_data_service.with_preview_combo(db, s["host"], data, s["combo"].id)
    assert (out["list_price"], out["offer_price"]) == (D("900.00"), D("800.00"))
