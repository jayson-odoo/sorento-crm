"""ptag_0010_badge_textcolor: the B1 code review data migration.

Rewrites a stored list_only, unboxed price_badge layer's retired '#ffffff'
textColor default to '#000000' - see the migration's own module docstring.
Loaded by FILENAME PATTERN, the same idiom `test_price_tag_data_pin.py` uses
for `ptag_0008_pins_versions`, since a revision filename cannot be imported by
module path (it starts with a digit/label).
"""
from __future__ import annotations

import glob
import importlib.util
from pathlib import Path


def _load_migration():
    matches = sorted(
        glob.glob(
            str(
                Path(__file__).resolve().parent.parent
                / "alembic"
                / "versions"
                / "*badge_textcolor*.py"
            )
        )
    )
    assert matches, "no alembic revision matching '*badge_textcolor*.py'"
    spec = importlib.util.spec_from_file_location(
        f"migration_{Path(matches[-1]).stem}", matches[-1]
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _price_badge_layer(**overrides) -> dict:
    props = {
        "kind": "price_badge",
        "variant": "list_only",
        "fill": "#d32f2f",
        "textColor": "#ffffff",
        "cornerRadius": 2,
        "showNett": True,
        **overrides,
    }
    return {"id": "badge1", "type": "price_badge", "props": props}


# --------------------------------------------------------------------------- #
# fix_template_doc - the tag TEMPLATE library's own flat `layers` array.
# --------------------------------------------------------------------------- #
def test_fix_template_doc_rewrites_the_retired_default_to_black():
    mod = _load_migration()
    doc = {"layers": [_price_badge_layer()], "width_mm": 85, "height_mm": 40}

    changed = mod.fix_template_doc(doc)

    assert changed is True
    assert doc["layers"][0]["props"]["textColor"] == "#000000"


def test_fix_template_doc_leaves_a_boxed_badge_alone():
    """showBox=True is the promo-style callout - already white-on-red by
    design, and D22 never touched that branch in the first place."""
    mod = _load_migration()
    doc = {"layers": [_price_badge_layer(showBox=True)]}

    changed = mod.fix_template_doc(doc)

    assert changed is False
    assert doc["layers"][0]["props"]["textColor"] == "#ffffff"


def test_fix_template_doc_leaves_promo_and_other_colours_alone():
    mod = _load_migration()
    doc = {
        "layers": [
            _price_badge_layer(variant="promo"),
            _price_badge_layer(textColor="#333333"),
        ]
    }

    changed = mod.fix_template_doc(doc)

    assert changed is False
    assert doc["layers"][0]["props"]["textColor"] == "#ffffff"
    assert doc["layers"][1]["props"]["textColor"] == "#333333"


def test_fix_template_doc_is_idempotent_on_a_second_run():
    mod = _load_migration()
    doc = {"layers": [_price_badge_layer()]}

    mod.fix_template_doc(doc)
    changed_again = mod.fix_template_doc(doc)

    assert changed_again is False
    assert doc["layers"][0]["props"]["textColor"] == "#000000"


# --------------------------------------------------------------------------- #
# fix_tag_sheet_doc - the PRICE TAG REQUEST design doc, nested under sheets/tags.
# --------------------------------------------------------------------------- #
def test_fix_tag_sheet_doc_rewrites_a_placed_tags_layers():
    mod = _load_migration()
    doc = {
        "kind": "tag_sheet",
        "sheets": [
            {
                "id": "sheet-1",
                "tags": [
                    {
                        "id": "tag-1-c0",
                        "request_tag_id": "tag-1",
                        "layers": [_price_badge_layer()],
                    }
                ],
            }
        ],
    }

    changed = mod.fix_tag_sheet_doc(doc)

    assert changed is True
    assert doc["sheets"][0]["tags"][0]["layers"][0]["props"]["textColor"] == "#000000"


def test_fix_tag_sheet_doc_ignores_a_catalogue_page_doc():
    """`page`/`page_version` hold catalogue pages too - `kind` is the only
    discriminator, and a catalogue doc's own layers must never be touched."""
    mod = _load_migration()
    doc = {"kind": "catalogue", "layers": [_price_badge_layer()]}

    assert mod.fix_tag_sheet_doc(doc) is False


def test_fix_tag_sheet_doc_handles_several_sheets_and_placements():
    mod = _load_migration()
    doc = {
        "kind": "tag_sheet",
        "sheets": [
            {
                "id": "sheet-1",
                "tags": [
                    {"id": "tag-1-c0", "request_tag_id": "tag-1", "layers": [_price_badge_layer()]},
                    {"id": "tag-1-c1", "request_tag_id": "tag-1", "layers": [_price_badge_layer()]},
                ],
            },
            {
                "id": "sheet-2",
                "tags": [
                    {
                        "id": "tag-2-c0",
                        "request_tag_id": "tag-2",
                        "layers": [_price_badge_layer(textColor="#111111")],
                    }
                ],
            },
        ],
    }

    changed = mod.fix_tag_sheet_doc(doc)

    assert changed is True
    assert doc["sheets"][0]["tags"][0]["layers"][0]["props"]["textColor"] == "#000000"
    assert doc["sheets"][0]["tags"][1]["layers"][0]["props"]["textColor"] == "#000000"
    # A deliberately different colour on the second sheet is untouched.
    assert doc["sheets"][1]["tags"][0]["layers"][0]["props"]["textColor"] == "#111111"
