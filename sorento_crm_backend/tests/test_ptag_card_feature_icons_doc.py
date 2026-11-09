"""PRICETAG-UPGRADE-VARIANTS BE test 2: `doc_has_feature_icons` sees a card's feature_icons element.

Written test-FIRST. Plan S1 BE: also true when an accessories layer's `card.elements` has kind
`feature_icons`, so `design_media` sends the icon rules and signed asset urls.
"""
from __future__ import annotations

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.dealer_kit.asset_service import doc_has_feature_icons


def _acc_layer(elements, **extra):
    return {
        "id": "acc1", "type": "accessories", "x_mm": 1, "y_mm": 1, "width_mm": 71, "height_mm": 30,
        "z_index": 1,
        "props": {"kind": "accessories", "list": "upgrades", "card": {"width_mm": 71, "height_mm": 21.5, "elements": elements}, **extra},
    }


def _doc(*layers):
    return {"layers": list(layers), "width_mm": 85, "height_mm": 130}


def test_be2_true_for_an_accessories_card_with_a_feature_icons_element():
    elements = [
        {"id": "e1", "kind": "text", "field": "code", "x_mm": 17, "y_mm": 5.6},
        {"id": "e2", "kind": "feature_icons", "x_mm": 17, "y_mm": 15.2, "width_mm": 50, "height_mm": 5},
    ]
    assert doc_has_feature_icons(_doc(_acc_layer(elements))) is True


def test_be2_false_for_an_accessories_card_without_one():
    elements = [{"id": "e1", "kind": "text", "field": "code", "x_mm": 17, "y_mm": 5.6}]
    assert doc_has_feature_icons(_doc(_acc_layer(elements))) is False


def test_be2_false_for_an_accessories_layer_with_no_card():
    layer = _acc_layer([])
    layer["props"].pop("card")
    assert doc_has_feature_icons(_doc(layer)) is False


def test_be2_true_inside_a_tag_sheet_document_tag():
    elements = [{"id": "e2", "kind": "feature_icons", "x_mm": 1, "y_mm": 1, "width_mm": 10, "height_mm": 5}]
    doc = {"sheets": [{"tags": [{"layers": [_acc_layer(elements)]}]}]}
    assert doc_has_feature_icons(doc) is True


def test_be2_the_plain_feature_icons_layer_still_counts_and_empty_docs_do_not():
    layer = {"id": "fi", "type": "feature_icons", "x_mm": 0, "y_mm": 0, "width_mm": 5, "height_mm": 5, "z_index": 1, "props": {"kind": "feature_icons"}}
    assert doc_has_feature_icons(_doc(layer)) is True
    assert doc_has_feature_icons(None) is False
    assert doc_has_feature_icons({}) is False
