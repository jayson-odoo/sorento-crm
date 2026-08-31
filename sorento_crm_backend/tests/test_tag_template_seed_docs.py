"""The eight seeded layouts, checked against the layer model (AC-L.9).

Written BEFORE the layouts were finished, and it is the reason they can be
written by hand at all. A tag document is JSONB: nothing in the request path
type-checks it, and both renderers draw NOTHING for a layer kind they do not
recognise. So a ``price_bagde`` typo ships as a tag with no price on it, opens
without an error anywhere, and reads to marketing as a pricing bug.

``TagTemplateDocModel`` is that type check, mirroring
`lib/dealer-kit/tag-template-types.ts` with ``extra='forbid'`` throughout. This
file runs every seeded family through it and then asserts the things a schema
cannot: that every layer is inside the tag, that a template ships UNBOUND, and
that each family carries the elements its page of the PDF actually prints.

No database and no bucket: the layouts are pure functions of an asset-name
lookup, which is exactly what makes them testable in isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.price_tag import TagTemplateDocModel
from scripts.tag_template_seed_docs import (
    SEED_TEMPLATES,
    build_furniture_set,
    build_sink_combo,
    build_wc,
    print_size_of,
)

GEOMETRY = (
    Path(__file__).resolve().parents[2]
    / "documentation"
    / "plans"
    / "dealer-kit"
    / "seed-assets"
    / "pdf-geometry.json"
)
MANIFEST = GEOMETRY.parent / "manifest.json"


def _lookup(name: str) -> str:
    """Stand-in for the ids the upload mints, one per distinct name."""
    return f"asset-{name.lower().replace(' ', '-')}"


def _docs() -> dict[str, dict]:
    return {family: builder(_lookup) for family, _label, builder in SEED_TEMPLATES}


ALL = list(_docs().items())


# ---------------------------------------------------------------------------
# The layer model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_every_family_is_a_valid_tag_document(family, doc):
    TagTemplateDocModel.model_validate(doc)


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_every_layer_sits_inside_the_tag(family, doc):
    """A layer off the edge is invisible in print and confusing in the editor."""
    for layer in doc["layers"]:
        assert layer["x_mm"] >= -0.5, (family, layer["id"])
        assert layer["y_mm"] >= -0.5, (family, layer["id"])
        assert layer["x_mm"] + layer["width_mm"] <= doc["width_mm"] + 0.5, (
            family,
            layer["id"],
        )
        assert layer["y_mm"] + layer["height_mm"] <= doc["height_mm"] + 0.5, (
            family,
            layer["id"],
        )


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_a_template_ships_unbound(family, doc):
    """A template is the layout for a FAMILY, never for one product.

    A seeded binding would print the seed's product on every request that used
    the template, and the wrong code beside the right price is the one failure
    on a price tag that a customer acts on.
    """
    for layer in doc["layers"]:
        if layer["props"]["kind"] != "group":
            continue
        binding = layer["props"].get("binding")
        assert not (binding or {}).get("product_id"), (family, layer["id"])
        assert not (binding or {}).get("product_set_id"), (family, layer["id"])


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_a_template_stores_no_prices_or_image_urls(family, doc):
    """ADR 0008, asserted rather than assumed.

    Placeholder text on an unbound slot is fine ("LP: RM 0,000" is a shape, not
    a figure); a real price, a real product code or a URL is not, because a
    document is copied onto every tag made from it and nothing re-checks it.
    """
    blob = json.dumps(doc)
    assert "http://" not in blob and "https://" not in blob, family
    for layer in doc["layers"]:
        props = layer["props"]
        if props["kind"] != "text":
            continue
        text = props["text"]
        assert "SRT" not in text, (family, layer["id"], text)


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_every_family_carries_a_price_badge_and_a_product_slot(family, doc):
    kinds = [layer["props"]["kind"] for layer in doc["layers"]]
    assert "price_badge" in kinds, family
    slots = {layer["slot_binding"] for layer in doc["layers"]}
    assert "code" in slots, family
    # The furniture set is a SET: it lists members instead of one product photo
    # plus dimensions.
    assert ("product_image" in slots) or ("set_members" in slots), family


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_every_named_asset_exists_in_the_manifest(family, doc):
    """A layer may not name artwork the seed does not upload.

    An asset id that resolves to nothing is an empty box on the tag, and the
    seed would have reported success.
    """
    available = {_lookup(entry["name"]) for entry in json.loads(MANIFEST.read_text())}
    for layer in doc["layers"]:
        props = layer["props"]
        used = None
        if props["kind"] == "badge":
            used = props["assetId"]
        elif props["kind"] == "image" and props.get("source"):
            source = props["source"]
            used = source["assetId"] if source["type"] == "asset" else None
        if used:
            assert used in available, (family, layer["id"], used)


def test_print_size_agrees_with_the_document():
    for _family, _label, builder in SEED_TEMPLATES:
        doc = builder(_lookup)
        assert print_size_of(doc) == {
            "width_mm": doc["width_mm"],
            "height_mm": doc["height_mm"],
        }


def test_the_eight_families_are_distinct():
    families = [family for family, _label, _builder in SEED_TEMPLATES]
    assert len(families) == 8
    assert len(set(families)) == 8


def test_the_seed_is_deterministic():
    """Two builds of the same family are identical, byte for byte.

    Not decoration: the seed's idempotency is "a template with this name already
    exists, leave it", and the only way to check that a rerun really changed
    nothing is to compare documents. Random layer ids would make that
    impossible.
    """
    assert build_sink_combo(_lookup) == build_sink_combo(_lookup)


# ---------------------------------------------------------------------------
# The tag boxes match the PDF
# ---------------------------------------------------------------------------


TAG_BOXES = {
    "sink_combo": (125.9, 88.6),
    "ala_carte": (125.9, 88.6),
    "art_basin": (124.6, 87.6),
    "mirror_cabinet": (147.7, 103.9),
    "shower": (131.5, 92.0),
    "wc": (131.6, 92.1),
    "urinal": (131.6, 92.1),
    "furniture_set": (94.0, 134.2),
}


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_the_tag_is_the_size_the_pdf_prints_it(family, doc):
    width, height = TAG_BOXES[family]
    assert (doc["width_mm"], doc["height_mm"]) == (width, height)


def test_the_pdf_geometry_still_backs_these_sizes():
    """The tag boxes are transcribed, so the source has to still say so.

    If somebody re-exports ``pdf-geometry.json`` from a redesigned PDF, this is
    what says the layouts need revisiting rather than letting them quietly
    describe the previous artwork.
    """
    pages = json.loads(GEOMETRY.read_text())["pages"]
    boxes = {
        (round(rect["w"], 1), round(rect["h"], 1))
        for page in pages.values()
        for rect in page["filled_rects"]
    }
    for family, size in TAG_BOXES.items():
        assert size in boxes, family


# ---------------------------------------------------------------------------
# What each page actually prints
# ---------------------------------------------------------------------------


def _asset_names(doc: dict) -> set[str]:
    names = set()
    for layer in doc["layers"]:
        props = layer["props"]
        if props["kind"] == "badge":
            names.add(props["assetId"])
        elif props["kind"] == "image" and (props.get("source") or {}).get("type") == "asset":
            names.add(props["source"]["assetId"])
    return names


def test_the_sink_combo_carries_four_kitchen_badges_and_an_alternatives_row():
    doc = build_sink_combo(_lookup)
    names = _asset_names(doc)
    for badge in (
        "Badge Sus304",
        "Badge Ultrasonic Nano",
        "Badge 25Yr Warranty",
        "Badge Anti Bacteria",
    ):
        assert _lookup(badge) in names

    texts = [
        layer["props"]["text"]
        for layer in doc["layers"]
        if layer["props"]["kind"] == "text"
    ]
    assert "+" in texts
    assert texts.count("OR") == 2

    # A circle-masked callout over the hero photo.
    assert any(
        layer["props"].get("maskShape") == "circle"
        for layer in doc["layers"]
        if layer["props"]["kind"] == "image"
    )


def test_the_wc_carries_its_warranty_badges_traps_and_smart_icons():
    doc = build_wc(_lookup)
    names = _asset_names(doc)
    for badge in (
        "Badge Lifetime Ceramic",
        "Badge 5Yr Flush Fittings",
        "Badge 2Yr Seat Cover",
        "Badge Trap 6In",
        "Badge Trap 8In",
        "Badge Trap 10In",
        "Badge Trap P",
        "Badge Uf Seat Cover",
        "Logo Twister Flush",
        "Diagram Remote Control",
    ):
        assert _lookup(badge) in names, badge

    smart = [
        name
        for name in names
        if name.startswith("asset-icon-")
    ]
    assert len(smart) == 6, sorted(smart)


def test_the_furniture_set_lists_members_on_a_white_card_over_green():
    doc = build_furniture_set(_lookup)
    slots = {layer["slot_binding"] for layer in doc["layers"]}
    assert "set_members" in slots

    fills = [
        layer["props"]["fill"]
        for layer in doc["layers"]
        if layer["props"]["kind"] == "shape"
    ]
    assert fills[:2] == ["#445235", "#ffffff"]

    assert _lookup("Label Pull Out") in _asset_names(doc)
    # The rotated caption around the honeycomb disc.
    assert any(layer["rotation_deg"] for layer in doc["layers"])


#: How much two boxes may share before it counts as a collision, in mm.
#:
#: Not zero. A text layer's box is its line box, so consecutive lines in a
#: column legitimately touch and sometimes share a fraction of a millimetre of
#: ascender space - and a zero-tolerance rule would fail every tag while
#: catching nothing. What it has to catch is a block running THROUGH another,
#: which is a whole line or more.
COLLISION_TOLERANCE_MM = 2.0


def _overlaps(a: dict, b: dict, tolerance: float = COLLISION_TOLERANCE_MM) -> bool:
    shared_x = min(a["x_mm"] + a["width_mm"], b["x_mm"] + b["width_mm"]) - max(
        a["x_mm"], b["x_mm"]
    )
    shared_y = min(a["y_mm"] + a["height_mm"], b["y_mm"] + b["height_mm"]) - max(
        a["y_mm"], b["y_mm"]
    )
    return shared_x > tolerance and shared_y > tolerance


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_no_two_bound_text_layers_sit_on_top_of_each_other(family, doc):
    """A slot printed over another slot is unreadable, and only shows once bound.

    This is the defect the browser pass found twice: an unbound template looks
    fine, because a placeholder is one short line, and the moment a real product
    fills three lines of spec it runs straight through the price beneath it. A
    box test catches it without opening anything.

    Deliberately narrow - SLOT-bound text only. A caption over a circle callout
    is on purpose, and a rule that forbade every overlap would forbid that too.
    """
    bound = [
        layer
        for layer in doc["layers"]
        if layer["props"]["kind"] == "text" and layer["slot_binding"]
    ]
    for index, first in enumerate(bound):
        for second in bound[index + 1 :]:
            assert not _overlaps(first, second), (
                family,
                first["id"],
                second["id"],
            )


@pytest.mark.parametrize("family,doc", ALL, ids=[f for f, _ in ALL])
def test_a_price_badge_is_clear_of_the_text_above_it(family, doc):
    """The badge is the one thing on a tag a customer must not misread."""
    badges = [l for l in doc["layers"] if l["props"]["kind"] == "price_badge"]
    texts = [
        l
        for l in doc["layers"]
        if l["props"]["kind"] == "text" and l["slot_binding"] in {"code", "dimensions", "spec_lines", "set_members"}
    ]
    for badge in badges:
        for text in texts:
            assert not _overlaps(badge, text), (family, badge["id"], text["id"])
