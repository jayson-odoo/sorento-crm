"""PRICETAG-COMBO-RENDER K4 / AC-B1, AC-B2: what a template needs and whether a combo fits.

Written test-FIRST. `app.services.dealer_kit.template_needs` does not exist yet; the module
is imported inside each test so every case is red as a ModuleNotFoundError of its own.

Decisions where the plan is open (simplest reading):
* `needs["groups"]` is indexed by group: a template that only uses group 2 (index 1) has
  `groups == [0, n]`. A group nobody reads is 0 and is skipped by the fit check.
* A layer reading `subjectSlot` of kind `main` adds nothing; legacy `subjectPart` is ignored.
* The reason words use singular for 1: "Needs 1 fixed part", plural otherwise ("(s)" in the plan).
* When several things are short, the first reason is fixed, then groups, then upgrades.
* An upgrade ticked on a grouped part counts as an upgrade, not as an option of the group.
"""
from __future__ import annotations

import os

import pytest

from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)


def _mod():
    from app.services.dealer_kit import template_needs

    return template_needs


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _layer(layer_id: str, slot=None, *, kind="text", part=None, children=None):
    props = {"kind": kind}
    if slot is not None:
        props["subjectSlot"] = slot
    if part is not None:
        props["subjectPart"] = part
    if children is not None:
        props["children"] = children
    return {
        "id": layer_id,
        "type": kind,
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 10,
        "height_mm": 10,
        "z_index": 1,
        "props": props,
    }


def _doc(*layers):
    return {"layers": list(layers), "width_mm": 105, "height_mm": 148}


MAIN = {"kind": "main"}


def _fixed(i):
    return {"kind": "fixed", "index": i}


def _pick(g, i):
    return {"kind": "pick", "group": g, "index": i}


def _up(i):
    return {"kind": "upgrade", "index": i}


# --------------------------------------------------------------------------- template_needs


def test_a_doc_with_no_slots_needs_nothing():
    needs = _mod().template_needs(_doc(_layer("a"), _layer("b", part=1)))
    assert needs == {"fixed": 0, "groups": [], "upgrades": 0}


def test_main_only_needs_nothing():
    assert _mod().template_needs(_doc(_layer("a", MAIN))) == {"fixed": 0, "groups": [], "upgrades": 0}


def test_fixed_is_the_highest_index_plus_one():
    needs = _mod().template_needs(_doc(_layer("a", _fixed(0)), _layer("b", _fixed(2), kind="image")))
    assert needs["fixed"] == 3


def test_picks_count_per_group_by_highest_index_plus_one():
    doc = _doc(_layer("a", _pick(0, 0)), _layer("b", _pick(0, 2)), _layer("c", _pick(1, 1)))
    assert _mod().template_needs(doc)["groups"] == [3, 2]


def test_a_group_nobody_reads_is_zero():
    assert _mod().template_needs(_doc(_layer("a", _pick(1, 0))))["groups"] == [0, 1]


def test_upgrades_are_the_highest_index_plus_one():
    needs = _mod().template_needs(_doc(_layer("a", _up(0)), _layer("b", _up(1))))
    assert needs["upgrades"] == 2


def test_a_layer_inside_a_group_layer_is_walked():
    group = _layer("g", kind="group", children=["c1"])
    child = _layer("c1", _pick(0, 3), kind="product_slot")
    assert _mod().template_needs(_doc(group, child))["groups"] == [4]


def test_every_layer_kind_that_can_carry_a_slot_counts():
    doc = _doc(
        _layer("t", _fixed(0), kind="text"),
        _layer("i", _fixed(1), kind="image"),
        _layer("p", _fixed(2), kind="product_slot"),
        _layer("b", _fixed(3), kind="price_badge"),
        _layer("c", _fixed(4), kind="barcode"),
    )
    assert _mod().template_needs(doc)["fixed"] == 5


# --------------------------------------------------------------------------- combo_shape


def test_combo_shape_s1(db):
    s = shapes.s1(db)
    db.refresh(s["combo"])
    assert _mod().combo_shape(s["combo"]) == {
        "fixed": 0,
        "groups": [{"role": "Kitchen tap", "size": 5}],
        "upgrades": 1,
    }


def test_combo_shape_s2(db):
    s = shapes.s2(db)
    db.refresh(s["combo"])
    assert _mod().combo_shape(s["combo"]) == {"fixed": 1, "groups": [], "upgrades": 0}


def test_combo_shape_s3(db):
    s = shapes.s3(db)
    db.refresh(s["combo"])
    assert _mod().combo_shape(s["combo"]) == {
        "fixed": 0,
        "groups": [{"role": "Tap colour", "size": 2}],
        "upgrades": 0,
    }


def test_combo_shape_s4(db):
    s = shapes.s4(db)
    db.refresh(s["combo"])
    assert _mod().combo_shape(s["combo"]) == {"fixed": 2, "groups": [], "upgrades": 0}


def test_combo_shape_s5_is_the_same_combo_as_s1(db):
    s = shapes.s1(db, "ZZT S5")
    db.refresh(s["combo"])
    assert _mod().combo_shape(s["combo"])["upgrades"] == 1


def test_a_grouped_part_ticked_upgrade_is_an_upgrade_not_an_option(db):
    from tests import _ptag_combo_seed as seed

    host = shapes.prod(db, "SRTKS7061")
    one = shapes.prod(db, "SRTKT1862SS")
    two = shapes.prod(db, "SRTKT71SS")
    combo = seed.combo(
        db,
        host,
        "ZZT mixed",
        parts=[{"product": one, "group": "Kitchen tap"}, {"product": two, "group": "Kitchen tap", "is_upgrade": True}],
    )
    db.refresh(combo)
    assert _mod().combo_shape(combo) == {
        "fixed": 0,
        "groups": [{"role": "Kitchen tap", "size": 1}],
        "upgrades": 1,
    }


# --------------------------------------------------------------------------- fit_reason


def _shape(db, builder):
    s = builder(db)
    db.refresh(s["combo"])
    return _mod().combo_shape(s["combo"])


def test_s1_needing_three_of_five_fits_and_the_upgrade_fits(db):
    shape = _shape(db, shapes.s1)
    needs = {"fixed": 0, "groups": [3], "upgrades": 1}
    assert _mod().fit_reason(needs, shape) is None


def test_s1_needing_all_five_fits_and_six_does_not(db):
    shape = _shape(db, shapes.s1)
    assert _mod().fit_reason({"fixed": 0, "groups": [5], "upgrades": 0}, shape) is None
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [6], "upgrades": 0}, shape)
        == "Needs 6 from Kitchen tap; this combo has 5"
    )


def test_s1_fixed_part_need_does_not_fit(db):
    shape = _shape(db, shapes.s1)
    assert (
        _mod().fit_reason({"fixed": 1, "groups": [], "upgrades": 0}, shape)
        == "Needs 1 fixed part; this combo has 0"
    )


def test_s2_one_fixed_fits_two_does_not(db):
    shape = _shape(db, shapes.s2)
    assert _mod().fit_reason({"fixed": 1, "groups": [], "upgrades": 0}, shape) is None
    assert (
        _mod().fit_reason({"fixed": 2, "groups": [], "upgrades": 0}, shape)
        == "Needs 2 fixed parts; this combo has 1"
    )


def test_s2_has_no_choice_group(db):
    shape = _shape(db, shapes.s2)
    assert (
        _mod().fit_reason({"fixed": 1, "groups": [1], "upgrades": 0}, shape)
        == "Needs a choice group; this combo has none"
    )


def test_s3_needing_three_of_two_options_names_the_shortfall(db):
    shape = _shape(db, shapes.s3)
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [3], "upgrades": 0}, shape)
        == "Needs 3 from Tap colour; this combo has 2"
    )


def test_s3_one_or_two_picks_fit(db):
    shape = _shape(db, shapes.s3)
    assert _mod().fit_reason({"fixed": 0, "groups": [1], "upgrades": 0}, shape) is None
    assert _mod().fit_reason({"fixed": 0, "groups": [2], "upgrades": 0}, shape) is None


def test_s3_second_group_that_does_not_exist(db):
    shape = _shape(db, shapes.s3)
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [0, 1], "upgrades": 0}, shape)
        == "Needs choice group 2; this combo has 1"
    )


def test_s4_two_fixed_fits_three_does_not(db):
    shape = _shape(db, shapes.s4)
    assert _mod().fit_reason({"fixed": 2, "groups": [], "upgrades": 0}, shape) is None
    assert (
        _mod().fit_reason({"fixed": 3, "groups": [], "upgrades": 0}, shape)
        == "Needs 3 fixed parts; this combo has 2"
    )


def test_s5_upgrade_need_fits_one_upgrade_but_not_two(db):
    shape = _shape(db, shapes.s1)
    assert _mod().fit_reason({"fixed": 0, "groups": [1], "upgrades": 1}, shape) is None
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [1], "upgrades": 2}, shape)
        == "Needs 2 upgrades; this combo has 1"
    )


def test_upgrade_need_on_a_combo_with_no_upgrade(db):
    shape = _shape(db, shapes.s4)
    assert (
        _mod().fit_reason({"fixed": 2, "groups": [], "upgrades": 1}, shape)
        == "Needs 1 upgrade; this combo has 0"
    )


def test_a_template_needing_nothing_fits_every_shape_without_fixed_parts(db):
    for builder in (shapes.s1, shapes.s3):
        shape = _shape(db, builder)
        assert _mod().fit_reason({"fixed": 0, "groups": [], "upgrades": 0}, shape) is None


def test_m1_a_template_must_print_every_fixed_part(db):
    """Fixed parts are always in the box: fewer fixed positions than the combo has does not fit."""
    shape = _shape(db, shapes.s4)
    assert (
        _mod().fit_reason({"fixed": 1, "groups": [], "upgrades": 0}, shape)
        == "Prints 1 of this combo's 2 fixed parts"
    )
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [], "upgrades": 0}, shape)
        == "Prints 0 of this combo's 2 fixed parts"
    )


def test_r2_a_picks_template_on_a_combo_with_fixed_parts_and_no_group_names_the_group(db):
    """Choice groups are checked before fixed parts, so the gap shown is the group, not '0 of N'."""
    shape = _shape(db, shapes.s4)
    assert (
        _mod().fit_reason({"fixed": 0, "groups": [2], "upgrades": 0}, shape)
        == "Needs a choice group; this combo has none"
    )
