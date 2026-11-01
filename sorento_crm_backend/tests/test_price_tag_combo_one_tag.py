"""PRICETAG-COMBO: one tag per combo line, and the missing-picture warning.

UAC: `documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md`
(AC-3.1 to AC-3.4, AC-7.1).

Written test-FIRST (PRINCIPLES.md Phase 2). Today a line with open choice groups mints
one tag per combination whether or not it has a `combo_id`; AC-3.1 stops that for lines
WITH a combo. AC-3.3 and AC-3.4 pin behaviour that must survive the change, so they pass
today on purpose and go red if the rule is applied too widely.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestTag
from app.services.price_tag_request_service import PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

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


def _basin_tap_combo(db, *, basins=3, taps=2):
    host = seed.product(db, "ZZCHOST", list_price="1000.00")
    basin_products = [seed.product(db, f"ZZCB{i}", list_price="100.00") for i in range(basins)]
    tap_products = [seed.product(db, f"ZZCT{i}", list_price="50.00") for i in range(taps)]
    specs = [{"product": p, "group": "Basin"} for p in basin_products]
    specs += [{"product": p, "group": "Tap"} for p in tap_products]
    cb = seed.combo(db, host, "ZZT many choices", parts=specs)
    return host, cb, basin_products, tap_products


def _open_parts(basin_products, tap_products):
    return [
        {"role": "Basin", "candidates": [p.id for p in basin_products]},
        {"role": "Tap", "candidates": [p.id for p in tap_products]},
    ]


def _tags(request):
    return sorted(request.lines[0].tags, key=lambda t: (t.sort_order or 0, t.id))


# --------------------------------------------------------------------------- AC-3.1


def test_ac_3_1_a_combo_line_with_two_open_groups_mints_one_tag_with_empty_choices(db):
    host, cb, basins, taps = _basin_tap_combo(db, basins=3, taps=2)
    request = seed.submit_one(db, host, cb, _open_parts(basins, taps))
    db.flush()

    tags = _tags(request)
    assert len(tags) == 1, "3 x 2 combinations must not mint 6 tags on a combo line"
    assert tags[0].choices == {}


def test_ac_3_1_a_combo_line_with_one_open_group_mints_one_tag(db):
    host, cb, basins, taps = _basin_tap_combo(db, basins=4, taps=1)
    request = seed.submit_one(
        db, host, cb, [{"role": "Basin", "candidates": [p.id for p in basins]}]
    )
    db.flush()
    tags = _tags(request)
    assert len(tags) == 1
    assert tags[0].choices == {}
    assert tags[0].quantity == 1


def test_ac_3_1_the_one_tag_carries_the_lines_quantity(db):
    host, cb, basins, taps = _basin_tap_combo(db)
    request = seed.submit_one(db, host, cb, _open_parts(basins, taps), quantity=5)
    db.flush()
    (tag,) = _tags(request)
    assert tag.quantity == 5


def test_ac_3_1_the_resolver_answers_one_row_listing_every_option(db):
    host, cb, basins, taps = _basin_tap_combo(db, basins=3, taps=2)
    request = seed.submit_one(db, host, cb, _open_parts(basins, taps))
    db.flush()
    rows = seed.rows(db, request)
    assert len(rows) == 1
    assert [len(g["options"]) for g in rows[0]["combo"]["choices"]] == [3, 2]
    assert not any(o["picked"] for g in rows[0]["combo"]["choices"] for o in g["options"])


# --------------------------------------------------------------------------- AC-3.2


def test_ac_3_2_a_dealer_pick_resolves_that_part_and_the_tag_shows_only_it(db):
    host, cb, basins, taps = _basin_tap_combo(db, basins=3, taps=2)
    request = seed.submit_one(
        db,
        host,
        cb,
        [
            {"product_id": basins[1].id, "role": "Basin"},
            {"role": "Tap", "candidates": [p.id for p in taps]},
        ],
    )
    db.flush()
    assert len(_tags(request)) == 1
    (row,) = seed.rows(db, request)
    assert [p["code"] for p in row["own_parts"]] == [basins[1].product_code]
    picked = {
        o["product_id"]: o["picked"]
        for g in row["combo"]["choices"]
        if g["role"] == "Basin"
        for o in g["options"]
    }
    assert picked == {basins[0].id: False, basins[1].id: True, basins[2].id: False}
    assert row["list_price"] == Decimal("1100.00"), "host 1000 + the picked basin 100"


# --------------------------------------------------------------------------- AC-3.3


def test_ac_3_3_a_line_with_open_groups_and_no_combo_id_keeps_one_tag_per_combination(db):
    """Pinned on purpose: passes today and must keep passing."""
    host, cb, basins, taps = _basin_tap_combo(db, basins=3, taps=2)
    request = seed.submit_one(db, host, None, _open_parts(basins, taps))
    db.flush()
    assert request.lines[0].combo_id is None
    tags = _tags(request)
    assert len(tags) == 6
    assert all(set(t.choices) == {"Basin", "Tap"} for t in tags)


# --------------------------------------------------------------------------- AC-3.4


def _legacy_split(db, request, basins):
    """Re-create the tag set a request in flight already holds: one tag per basin."""
    line = request.lines[0]
    for tag in list(line.tags):
        db.delete(tag)
    db.flush()
    db.expire(line, ["tags"])
    made = []
    for index, basin in enumerate(basins):
        tag = PriceTagRequestTag(
            line_id=line.id,
            sort_order=index,
            quantity=3 + index,
            choices={"Basin": basin.id},
            marketing_price_override=Decimal("123.00") if index == 0 else None,
            marketing_override_reason="ZZT hand split" if index == 0 else None,
        )
        db.add(tag)
        made.append(tag)
    db.flush()
    return sorted((t.id, t.sort_order, t.quantity, tuple(t.choices.items())) for t in made)


def test_ac_3_4_a_surviving_combo_line_keeps_its_one_per_combination_tags_on_save(db):
    host = seed.product(db, "ZZCHOST", list_price="1000.00")
    basins = [seed.product(db, f"ZZCB{i}", list_price="100.00") for i in range(2)]
    cb = seed.combo(db, host, "ZZT split", parts=[{"product": p, "group": "Basin"} for p in basins])
    line = seed.line_dict(host, cb, [{"role": "Basin", "candidates": [p.id for p in basins]}])
    request = seed.submit(db, [line])
    before = _legacy_split(db, request, basins)

    PriceTagRequestService.replace_lines(db, request, [{**line, "remarks": "ZZT typo fix"}])
    db.flush()

    after = sorted(
        (t.id, t.sort_order, t.quantity, tuple(t.choices.items())) for t in _tags(request)
    )
    assert after == before, "ids, order, quantity and choices survive; nothing collapses"
    first = next(t for t in _tags(request) if t.sort_order == 0)
    assert first.marketing_price_override == Decimal("123.00")
    assert first.marketing_override_reason == "ZZT hand split", "the override rides along with its tag"


def test_ac_3_4_a_new_style_single_tag_is_kept_on_save_with_the_same_id(db):
    host, cb, basins, taps = _basin_tap_combo(db)
    line = seed.line_dict(host, cb, _open_parts(basins, taps))
    request = seed.submit(db, [line])
    (before,) = _tags(request)

    PriceTagRequestService.replace_lines(db, request, [{**line, "remarks": "ZZT typo fix"}])
    db.flush()

    (after,) = _tags(request)
    assert after.id == before.id
    assert after.choices == {}


# --------------------------------------------------------------------------- AC-7.1


def _guarded_host(db):
    from app.models.product import ProductCategory

    host = seed.product(db, "ZZCGUARD", list_price="1000.00")
    category = db.query(ProductCategory).filter(ProductCategory.id == host.category_id).one()
    category.class_label = "Bathroom Furniture"
    db.flush()
    return host


def _warning(db, **combo_fields):
    host = _guarded_host(db)
    mirror = seed.product(db, "ZZCMIR", list_price="200.00")
    cb = seed.combo(db, host, "ZZT warn", parts=[{"product": mirror}], **combo_fields)
    request = seed.submit_one(db, host, cb, [{"product_id": mirror.id}])
    db.flush()
    assert request.status == "new", "submit still succeeds"
    return request.lines[0].package_warning


def _names(text, *words):
    return any(w in (text or "").lower() for w in words)


def test_ac_7_1_a_combo_with_no_picture_and_no_description_warns_naming_both(db):
    warning = _warning(db)
    assert warning, "a warning is stamped"
    assert _names(warning, "description")
    assert _names(warning, "picture", "photo", "image")


def test_ac_7_1_a_combo_with_a_description_but_no_picture_names_only_the_picture(db):
    warning = _warning(db, description="Cabinet and mirror")
    assert warning
    assert _names(warning, "picture", "photo", "image")
    assert not _names(warning, "description")


def test_ac_7_1_a_combo_with_a_picture_but_no_description_names_only_the_description(db):
    host = _guarded_host(db)
    mirror = seed.product(db, "ZZCMIR", list_price="200.00")
    cover = r9.seed_product_photo(db, host)
    cb = seed.combo(
        db, host, "ZZT warn", parts=[{"product": mirror}], image_attachment_id=cover.id
    )
    request = seed.submit_one(db, host, cb, [{"product_id": mirror.id}])
    db.flush()
    warning = request.lines[0].package_warning
    assert warning
    assert _names(warning, "description")
    assert not _names(warning, "picture", "photo", "image")


def test_ac_7_1_a_complete_combo_adds_no_warning(db):
    host = _guarded_host(db)
    mirror = seed.product(db, "ZZCMIR", list_price="200.00")
    cover = r9.seed_product_photo(db, host)
    cb = seed.combo(
        db,
        host,
        "ZZT complete",
        parts=[{"product": mirror}],
        description="Cabinet and mirror",
        image_attachment_id=cover.id,
    )
    request = seed.submit_one(db, host, cb, [{"product_id": mirror.id}])
    db.flush()
    assert request.lines[0].package_warning is None
