"""PRICETAG-COMBO-RENDER K2 / AC-A2, A3, A6: the `slots` a tag row carries.

Written test-FIRST. `slots` does not exist on a tag row, on the preview product or on the
response models yet; every case is red as a missing key.

Decisions where the plan is open:
* Unpicked upgrades come back in `slots["upgrades"]` with `chosen` False; a picked one has True.
* A picked upgrade is a resolved line part whose role is "Upgrade" (what the form writes); it
  is in `upgrades` only, never in `fixed` or in a group.
* The preview product without `combo_id` answers `slots: null` (key present).
* Without a combo on the line, `groups` lists the distinct roles of the line's parts; only
  role and picks are asserted for that case (the plan leaves `size` open).
"""
from __future__ import annotations

import os

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session
from tests.test_price_tag_combo_preview import PRODUCT_URL, api  # noqa: F401  (fixture)
from tests.test_price_tag_combo_tag_data import crm  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)


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


def _slots(row):
    assert "slots" in row, "the tag row has no `slots` key"
    return row["slots"]


# --------------------------------------------------------------------------- S1


def test_s1_three_picks_come_back_in_pick_order(db):
    s = shapes.s1(db)
    o = s["options"]  # codes 1862, 1863, 1871, 1880, 1892 in combo order
    row, _ = _row(db, s, shapes.pick_parts(s["group"], o[1], o[0], o[2]))
    slots = _slots(row)
    assert slots["fixed"] == []
    (group,) = slots["groups"]
    assert group["role"] == "Kitchen tap"
    assert group["size"] == 5
    assert shapes.codes(group["picks"]) == ["SRTKT1863SS", "SRTKT1862SS", "SRTKT1871SS"]


def test_s1_pick_rows_are_part_rows_with_the_products_own_data(db):
    s = shapes.s1(db)
    o = s["options"]
    row, _ = _row(db, s, shapes.pick_parts(s["group"], o[1]))
    (pick,) = _slots(row)["groups"][0]["picks"]
    assert pick["product_id"] == o[1].id
    assert pick["code"] == "SRTKT1863SS"
    assert float(pick["list_price"]) == 200.0
    assert {"images", "price_tag_description", "sell_price", "currency"} <= set(pick)


def test_s1_the_upgrade_is_listed_unpicked(db):
    s = shapes.s1(db)
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][0]))
    (upgrade,) = _slots(row)["upgrades"]
    assert upgrade["code"] == "SRTKT71SS"
    assert upgrade["chosen"] is False
    assert float(upgrade["list_price"]) == 600.0


def test_s1_an_open_upgrade_row_does_not_become_a_group_or_a_fixed_part(db):
    s = shapes.s1(db)
    parts = shapes.pick_parts(s["group"], s["options"][0]) + [
        {"product_id": None, "role": "Upgrade", "candidates": [s["upgrade"].id]}
    ]
    row, _ = _row(db, s, parts)
    slots = _slots(row)
    assert [g["role"] for g in slots["groups"]] == ["Kitchen tap"]
    assert slots["fixed"] == []
    assert slots["upgrades"][0]["chosen"] is False


def test_s1_a_group_left_open_reads_the_tags_choice(db):
    s = shapes.s1(db)
    o = s["options"]
    parts = [{"product_id": None, "role": "Kitchen tap", "candidates": [x.id for x in o[:2]]}]
    row, request = _row(db, s, parts)
    tag = request.lines[0].tags[0]
    tag.choices = {"Kitchen tap": o[1].id}
    db.flush()
    db.expire_all()
    (row,) = [r for r in seed.rows(db, request) if r["tag_id"] == tag.id]
    assert shapes.codes(_slots(row)["groups"][0]["picks"]) == ["SRTKT1863SS"]


# --------------------------------------------------------------------------- S2


def test_s2_one_fixed_part_and_no_groups(db):
    s = shapes.s2(db)
    row, _ = _row(db, s, shapes.fixed_parts(*s["fixed"]))
    slots = _slots(row)
    assert shapes.codes(slots["fixed"]) == ["SRTWT7449-BL"]
    assert slots["groups"] == []
    assert slots["upgrades"] == []


# --------------------------------------------------------------------------- S3


def test_s3_two_picks(db):
    s = shapes.s3(db)
    bl, rg = s["options"]
    row, _ = _row(db, s, shapes.pick_parts(s["group"], rg, bl))
    (group,) = _slots(row)["groups"]
    assert group["role"] == "Tap colour"
    assert group["size"] == 2
    assert shapes.codes(group["picks"]) == ["SRTWT7449-RG", "SRTWT7449-BL"]


def test_s3_one_pick_of_two(db):
    s = shapes.s3(db)
    row, _ = _row(db, s, shapes.pick_parts(s["group"], s["options"][1]))
    assert shapes.codes(_slots(row)["groups"][0]["picks"]) == ["SRTWT7449-RG"]


# --------------------------------------------------------------------------- S4


def test_s4_two_fixed_parts_in_sort_order_and_nothing_to_pick(db):
    s = shapes.s4(db)
    row, _ = _row(db, s, shapes.fixed_parts(*s["fixed"]))
    slots = _slots(row)
    assert shapes.codes(slots["fixed"]) == ["SRTMCB8083-BL", "SRTWT6203-GM"]
    assert slots["groups"] == []
    assert slots["upgrades"] == []


# --------------------------------------------------------------------------- S5


def test_s5_the_picked_upgrade_is_chosen_and_in_no_other_list(db):
    s = shapes.s1(db, "ZZT S5")
    parts = shapes.pick_parts(s["group"], s["options"][0], s["options"][2]) + [
        shapes.upgrade_part(s["upgrade"])
    ]
    row, _ = _row(db, s, parts)
    slots = _slots(row)
    (upgrade,) = slots["upgrades"]
    assert upgrade["code"] == "SRTKT71SS"
    assert upgrade["chosen"] is True
    assert slots["fixed"] == []
    assert shapes.codes(slots["groups"][0]["picks"]) == ["SRTKT1862SS", "SRTKT1871SS"]


# --------------------------------------------------------------------------- none


def test_a_line_with_no_parts_and_no_combo_has_null_slots(db):
    host = shapes.prod(db, "SRTKS7061")
    request = seed.submit_one(db, host)
    db.flush()
    row = seed.rows(db, request)[0]
    assert "slots" in row
    assert row["slots"] is None


def test_without_a_combo_the_distinct_roles_of_the_parts_are_the_groups(db):
    s = shapes.s3(db)
    request = seed.submit_one(
        db, s["host"], None, shapes.pick_parts("Finish", *s["options"])
    )
    db.flush()
    slots = _slots(seed.rows(db, request)[0])
    assert [g["role"] for g in slots["groups"]] == ["Finish"]
    assert shapes.codes(slots["groups"][0]["picks"]) == ["SRTWT7449-BL", "SRTWT7449-RG"]


# --------------------------------------------------------------------------- preview (AC-A6)


def test_preview_fills_every_group_with_all_its_options_in_combo_order(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s1(db)
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    out = tag_data_service.with_preview_combo(db, s["host"], data, s["combo"].id)
    slots = out["slots"]
    assert slots["fixed"] == []
    (group,) = slots["groups"]
    assert group["role"] == "Kitchen tap" and group["size"] == 5
    assert shapes.codes(group["picks"]) == shapes.S1_OPTIONS
    assert shapes.codes(slots["upgrades"]) == ["SRTKT71SS"]


def test_preview_lists_the_combos_fixed_parts(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s4(db)
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    out = tag_data_service.with_preview_combo(db, s["host"], data, s["combo"].id)
    assert shapes.codes(out["slots"]["fixed"]) == ["SRTMCB8083-BL", "SRTWT6203-GM"]
    assert out["slots"]["groups"] == []


def test_preview_s2_and_s3(db):
    from app.services.dealer_kit import tag_data_service

    one = shapes.s2(db)
    two = shapes.s3(db)
    viewer = tag_data_service.staff_viewer()
    data = tag_data_service.product_tag_data(db, one["host"], viewer, None)
    first = tag_data_service.with_preview_combo(db, one["host"], data, one["combo"].id)
    second = tag_data_service.with_preview_combo(db, one["host"], data, two["combo"].id)
    assert shapes.codes(first["slots"]["fixed"]) == ["SRTWT7449-BL"]
    assert shapes.codes(second["slots"]["groups"][0]["picks"]) == ["SRTWT7449-BL", "SRTWT7449-RG"]


def test_preview_without_a_combo_has_null_slots(db):
    from app.services.dealer_kit import tag_data_service

    s = shapes.s1(db)
    data = tag_data_service.product_tag_data(db, s["host"], tag_data_service.staff_viewer(), None)
    out = tag_data_service.with_preview_combo(db, s["host"], data, None)
    assert "slots" in out
    assert out["slots"] is None


# --------------------------------------------------------------------------- routes keep `slots`


def test_the_preview_route_keeps_slots_in_its_response(api):  # noqa: F811
    client, db, _ = api
    s = shapes.s1(db)
    db.commit()
    response = client.get(PRODUCT_URL.format(id=s["host"].id), params={"combo_id": s["combo"].id})
    assert response.status_code == 200, response.text
    slots = response.json()["slots"]
    assert slots is not None, "response_model dropped `slots`"
    assert shapes.codes(slots["groups"][0]["picks"]) == shapes.S1_OPTIONS
    assert slots["groups"][0]["size"] == 5
    assert shapes.codes(slots["upgrades"]) == ["SRTKT71SS"]


def test_the_preview_route_without_a_combo_answers_null_slots(api):  # noqa: F811
    client, db, _ = api
    s = shapes.s1(db)
    db.commit()
    body = client.get(PRODUCT_URL.format(id=s["host"].id)).json()
    assert "slots" in body and body["slots"] is None


def test_the_resolve_prices_route_keeps_slots_in_its_response(crm):  # noqa: F811
    client, db = crm
    s = shapes.s1(db)
    parts = shapes.pick_parts(s["group"], s["options"][1], s["options"][0])
    request = seed.submit_one(db, s["host"], s["combo"], parts)
    db.commit()
    response = client.post(
        f"/api/v1/dealer-kit/price-tag-requests/{request.id}/resolve-prices", json=None
    )
    assert response.status_code == 200, response.text
    (row,) = response.json()
    slots = row["slots"]
    assert slots is not None, "response_model dropped `slots`"
    assert shapes.codes(slots["groups"][0]["picks"]) == ["SRTKT1863SS", "SRTKT1862SS"]
    assert slots["upgrades"][0]["chosen"] is False
