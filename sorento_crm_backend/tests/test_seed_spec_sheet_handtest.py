"""The spec sheet hand-test seed's accessory rows read Accessory 1 and 2.

Parts are 0-based everywhere: `subjectPart` indexes the page's accessories
(`project_spec_sheet_service.py`, `accessories[part]`) and `show_when.part` indexes the line's
parts (`lib/dealer-kit/product-block.ts` `layerShownFor`). The seed used to write 1 and 2, so its
rows were Accessory 2 and 3 and a page with ONE accessory printed none (crew finding, 11 Nov).
Pure: no database.
"""
from __future__ import annotations

from scripts import seed_spec_sheet_handtest as seed


def _accessory_layers():
    layers = seed._docs()[("spec_page", "Item with accessories")]
    return [layer for layer in layers if "subjectPart" in layer["props"]]


def test_the_accessory_rows_point_at_the_first_and_second_accessory():
    parts = sorted({layer["props"]["subjectPart"] for layer in _accessory_layers()})
    assert parts == [0, 1]


def test_each_row_shows_only_when_its_own_accessory_is_there():
    for layer in _accessory_layers():
        assert layer["show_when"] == {"part": layer["props"]["subjectPart"]}


def test_the_single_item_template_has_no_accessory_rows():
    layers = seed._docs()[("spec_page", "Single item")]
    assert not [layer for layer in layers if "subjectPart" in layer["props"]]


def test_a_template_made_by_the_old_seed_shifts_to_parts_0_and_1_once():
    old = [
        {"id": "ht-20", "props": {"subjectPart": 1}, "show_when": {"part": 1}},
        {"id": "ht-23", "props": {"subjectPart": 2}, "show_when": {"part": 2}},
        # A designer's own layer, not the seed's: never touched.
        {"id": "user-1", "props": {"subjectPart": 1}, "show_when": {"part": 1}},
    ]
    assert seed.shift_accessory_parts(old) == 2
    assert [l["props"]["subjectPart"] for l in old] == [0, 1, 1]
    assert [l["show_when"]["part"] for l in old] == [0, 1, 1]
    # Second run: already fixed, nothing changes.
    assert seed.shift_accessory_parts(old) == 0
