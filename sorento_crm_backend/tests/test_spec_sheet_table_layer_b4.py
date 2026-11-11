"""SPEC-SHEET-DESIGNER-PARITY B4: the backend accepts a `table` layer, in a spec sheet page edit
and in the tag template document schema. Written test-FIRST. Postgres only.
"""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain  # noqa: F401  (helper, not a test)
from .test_project_spec_sheets_v2 import _make

_SIDE = {"color": "#000000", "width_mm": 0.2}


def _cell(text: str) -> dict:
    return {"text": text, "padding_mm": 1, "border": {k: _SIDE for k in ("top", "right", "bottom", "left")}}


def _table_layer(layer_id: str = "tbl") -> dict:
    return {
        "id": layer_id,
        "type": "table",
        "x_mm": 1,
        "y_mm": 1,
        "width_mm": 60,
        "height_mm": 20,
        "rotation_deg": 0,
        "z_index": 0,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {
            "kind": "table",
            "columns": [{"width_mm": 30}, {"width_mm": 30}],
            "rows": [{"height_mm": 6}, {"height_mm": 6}],
            "cells": [
                [_cell("REF"), {**_cell("{{doc.ref}}"), "fill": "#eeeeee", "colSpan": 1}],
                [_cell("A"), _cell("B")],
            ],
            "fontFamily": "DM Sans",
            "fontSize": 10,
            "color": "#000000",
            "align": "left",
            "verticalAlign": "middle",
        },
    }


def test_a_spec_sheet_page_edit_with_a_table_layer_saves():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        spec.save_page_edit(db, sheet, c["basin"].id, [_table_layer()])
        saved = sheet.page_edits[c["basin"].id]["layers"]
        assert [layer["type"] for layer in saved] == ["table"]
        assert saved[0]["props"]["cells"][0][1]["text"] == "{{doc.ref}}"


def test_the_tag_template_document_schema_accepts_a_table_layer():
    from app.schemas.price_tag import TagTemplateDocModel

    doc = TagTemplateDocModel.model_validate(
        {"width_mm": 80, "height_mm": 60, "layers": [_table_layer()]}
    )
    assert doc.layers[0].type == "table"
    assert doc.layers[0].props.kind == "table"
