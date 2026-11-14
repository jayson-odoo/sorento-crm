"""PRICETAG-DESIGNER-FEEDBACK B2: the backend layer schemas accept the new props.

UAC: documentation/plans/dealer-kit/pricetag-designer-feedback-b-acceptance-criteria.md AC-5.1,
AC-7.6, AC-8.1.

- The strict Spec icons layer doc (`FeatureIconsLayerPropsDoc`, extra=forbid) accepts `columns` and
  `rows` ('auto' | 1..4) and `hiddenIconIds` (a list of asset id strings); other values are refused.
- The accessories box has no strict layer doc in `app/schemas/price_tag.py` (its design is a free
  object checked by `app/schemas/accessory_template.py`): a saved design carrying `rows` and
  `columns` keeps them.

Pure pydantic, no database. Written test-FIRST.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.accessory_template import AccessoryTemplateCreate
from app.schemas.price_tag import FeatureIconsLayerPropsDoc, TagLayerDoc

BASE = {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 2, "align": "left"}


def _layer(props: dict) -> dict:
    return {
        "id": "fi", "type": "feature_icons", "x_mm": 0, "y_mm": 0, "width_mm": 40, "height_mm": 10,
        "z_index": 1, "props": props,
    }


@pytest.mark.parametrize("value", ["auto", 1, 2, 3, 4])
def test_feature_icons_accepts_columns_and_rows(value):
    doc = FeatureIconsLayerPropsDoc.model_validate({**BASE, "columns": value, "rows": value})
    assert doc.model_dump()["columns"] == value
    assert doc.model_dump()["rows"] == value


def test_feature_icons_accepts_hidden_icon_ids():
    doc = FeatureIconsLayerPropsDoc.model_validate({**BASE, "hiddenIconIds": ["asset-1", "asset-2"]})
    assert doc.model_dump()["hiddenIconIds"] == ["asset-1", "asset-2"]


def test_feature_icons_new_props_are_optional():
    doc = FeatureIconsLayerPropsDoc.model_validate(BASE).model_dump()
    assert doc.get("columns") in (None, "auto")
    assert doc.get("rows") in (None, "auto")
    assert doc.get("hiddenIconIds") in (None, [])


def test_a_whole_layer_with_the_new_props_validates():
    layer = TagLayerDoc.model_validate(
        _layer({**BASE, "columns": 2, "rows": "auto", "hiddenIconIds": ["asset-1"]})
    )
    assert layer.props.model_dump()["hiddenIconIds"] == ["asset-1"]


@pytest.mark.parametrize(
    "extra",
    [
        {"columns": 5},
        {"rows": 0},
        {"rows": "two"},
        {"hiddenIconIds": "asset-1"},
        {"hiddenIconIds": [1, 2]},
    ],
)
def test_feature_icons_refuses_bad_values(extra):
    # Guard: valid values must be accepted first, or this would pass on today's extra=forbid.
    FeatureIconsLayerPropsDoc.model_validate({**BASE, "columns": 2, "rows": 2, "hiddenIconIds": []})
    with pytest.raises(ValidationError):
        FeatureIconsLayerPropsDoc.model_validate({**BASE, **extra})


def test_feature_icons_still_forbids_unknown_props():
    with pytest.raises(ValidationError):
        FeatureIconsLayerPropsDoc.model_validate({**BASE, "notAProp": 1})


def test_a_saved_accessories_design_keeps_rows_and_columns():
    design = {"card": {"width_mm": 30, "height_mm": 20, "elements": []}, "columns": "auto", "rows": 2}
    saved = AccessoryTemplateCreate.model_validate({"name": "ZZT grid", "design": design})
    assert saved.design["rows"] == 2
    assert saved.design["columns"] == "auto"
