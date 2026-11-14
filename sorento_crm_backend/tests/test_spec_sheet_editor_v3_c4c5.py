"""SPEC-SHEET-PARITY-B2 v3 editor (UAC `spec-sheet-editor-v3-14nov-acceptance-criteria.md`), C4 + C5:
the new optional table props `headerRow` / `uppercase` and the text layer prop `uppercase` are
accepted by every save path (the template doc schema forbids unknown props, so it must name them),
and the PowerPoint builder prints a header row bold on a light shade (the cell's own fill wins) and
ALL CAPS text in capitals. Written test-FIRST. Postgres only (`blank_session`), every chain seeded.

Contract pinned for the coder:
- `TableLayerPropsDoc.headerRow: Optional[bool]`, `TableLayerPropsDoc.uppercase: Optional[bool]`,
  `TextLayerPropsDoc.uppercase: Optional[bool]`; absent = off; unknown keys are still refused.
- The print page's layout export (`window.__tagSheetLayout`) carries `headerRow` / `uppercase` on a
  table layer and `uppercase` on a text layer; `spec_sheet_pptx.build_pptx` applies them.
"""
from __future__ import annotations

import io

import pytest

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain  # noqa: F401  (helper, not a test)
from .test_project_spec_sheets_v2 import _make

_SIDE = {"color": "#3f7d3a", "width_mm": 0.2}


def _cell(text: str) -> dict:
    return {"text": text, "padding_mm": 1, "border": {k: _SIDE for k in ("top", "right", "bottom", "left")}}


def _table_layer(layer_id: str = "tbl", **extra_props) -> dict:
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
            "columns": [{"width_mm": 60}],
            "rows": [{"height_mm": 30}, {"height_mm": 6}, {"height_mm": 20}],
            "cells": [[_cell("{{doc.subject_title}}")], [_cell("REF : {{doc.ref}}")], [_cell("")]],
            "fontFamily": "DM Sans",
            "fontSize": 8,
            "color": "#000000",
            "align": "left",
            "verticalAlign": "top",
            **extra_props,
        },
    }


def _text_layer(layer_id: str = "title", **extra_props) -> dict:
    return {
        "id": layer_id,
        "type": "text",
        "x_mm": 5,
        "y_mm": 5,
        "width_mm": 80,
        "height_mm": 10,
        "rotation_deg": 0,
        "z_index": 1,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {
            "kind": "text",
            "text": "Wall hung water closet",
            "fontFamily": "DM Sans",
            "fontSize": 12,
            "fontWeight": 400,
            "color": "#000000",
            "align": "left",
            "lineHeight": 1.2,
            "letterSpacing": 0,
            **extra_props,
        },
    }


# ------------------------------------------------------------------ template doc schema (AC-C4.2, AC-C5.2)


def test_c4_template_doc_schema_accepts_header_row_on_a_table():
    from app.schemas.price_tag import TagTemplateDocModel

    doc = TagTemplateDocModel.model_validate(
        {"width_mm": 80, "height_mm": 60, "layers": [_table_layer(headerRow=True)]}
    )
    assert doc.layers[0].props.headerRow is True


def test_c5_template_doc_schema_accepts_uppercase_on_a_table():
    from app.schemas.price_tag import TagTemplateDocModel

    doc = TagTemplateDocModel.model_validate(
        {"width_mm": 80, "height_mm": 60, "layers": [_table_layer(uppercase=True)]}
    )
    assert doc.layers[0].props.uppercase is True


def test_c5_template_doc_schema_accepts_uppercase_on_a_text_layer():
    from app.schemas.price_tag import TagTemplateDocModel

    doc = TagTemplateDocModel.model_validate(
        {"width_mm": 80, "height_mm": 60, "layers": [_text_layer(uppercase=True)]}
    )
    assert doc.layers[0].props.uppercase is True


def test_c4_c5_old_tables_and_text_without_the_flags_still_validate_and_read_as_off():
    from app.schemas.price_tag import TagTemplateDocModel

    doc = TagTemplateDocModel.model_validate(
        {"width_mm": 80, "height_mm": 60, "layers": [_table_layer(), _text_layer()]}
    )
    table, text = doc.layers[0].props, doc.layers[1].props
    assert not getattr(table, "headerRow", None)
    assert not getattr(table, "uppercase", None)
    assert not getattr(text, "uppercase", None)


def test_c4_c5_template_doc_schema_still_refuses_an_unknown_table_or_text_prop():
    from pydantic import ValidationError

    from app.schemas.price_tag import TagTemplateDocModel

    with pytest.raises(ValidationError):
        TagTemplateDocModel.model_validate(
            {"width_mm": 80, "height_mm": 60, "layers": [_table_layer(headerRows=True)]}
        )
    with pytest.raises(ValidationError):
        TagTemplateDocModel.model_validate(
            {"width_mm": 80, "height_mm": 60, "layers": [_text_layer(allCaps=True)]}
        )


# ------------------------------------------------------------------ spec sheet page edit (AC-C4.2, AC-C5.2)


def test_c4_c5_a_spec_sheet_page_edit_keeps_header_row_and_uppercase():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        spec.save_page_edit(
            db,
            sheet,
            c["basin"].id,
            [_table_layer(headerRow=True, uppercase=True), _text_layer(uppercase=True)],
        )
        saved = {layer["id"]: layer for layer in sheet.page_edits[c["basin"].id]["layers"]}
        assert saved["tbl"]["props"]["headerRow"] is True
        assert saved["tbl"]["props"]["uppercase"] is True
        assert saved["title"]["props"]["uppercase"] is True


# ------------------------------------------------------------------ PowerPoint (AC-C4.1, AC-C5.2)


def _deck(layers):
    from pptx import Presentation

    from app.services.spec_sheet_pptx import build_pptx

    return Presentation(io.BytesIO(build_pptx([{"layers": layers}], (338.7, 190.5))))


def _pptx_table(**flags) -> dict:
    """A resolved table as the print page exports it: 2 rows x 2 columns."""
    return {
        "kind": "table",
        "x_mm": 10,
        "y_mm": 20,
        "width_mm": 60,
        "height_mm": 12,
        "columns_mm": [30, 30],
        "rows_mm": [6, 6],
        "fontFamily": "DM Sans",
        "fontSize": 10,
        "color": "#000000",
        "align": "left",
        "verticalAlign": "middle",
        "cells": [
            {"row": 0, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "Ref", "fill": None},
            {"row": 0, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "Value", "fill": "#ff0000"},
            {"row": 1, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "Code", "fill": None},
            {"row": 1, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "Wc-1 basin", "fill": None},
        ],
        "edges": [],
        **flags,
    }


def _only_table(deck):
    tables = [s for s in deck.slides[0].shapes if s.has_table]
    assert len(tables) == 1
    return tables[0].table


def _runs(cell):
    return [run for paragraph in cell.text_frame.paragraphs for run in paragraph.runs if run.text]


def _fill_hex(cell):
    """The cell's solid fill as RRGGBB, or None when it has no solid fill."""
    values = cell._tc.xpath("a:tcPr/a:solidFill/a:srgbClr/@val")
    return values[0].upper() if values else None


def test_c4_pptx_header_row_is_bold_and_the_rest_is_not():
    table = _only_table(_deck([_pptx_table(headerRow=True)]))
    for col in (0, 1):
        runs = _runs(table.cell(0, col))
        assert runs and all(run.font.bold is True for run in runs), f"header cell 0,{col} not bold"
    for col in (0, 1):
        assert all(not run.font.bold for run in _runs(table.cell(1, col))), f"body cell 1,{col} is bold"


def test_c4_pptx_header_row_is_shaded_and_the_cell_own_fill_wins():
    table = _only_table(_deck([_pptx_table(headerRow=True)]))
    shade = _fill_hex(table.cell(0, 0))
    assert shade is not None, "the header cell with no fill of its own gets the light shade"
    assert shade not in ("FFFFFF", "000000")
    # A light shade: every channel high (the mock's #f1f5ee).
    assert all(int(shade[i : i + 2], 16) >= 0xD0 for i in (0, 2, 4)), shade
    assert _fill_hex(table.cell(0, 1)) == "FF0000"
    assert _fill_hex(table.cell(1, 0)) is None


def test_c4_pptx_without_header_row_row_one_is_plain():
    table = _only_table(_deck([_pptx_table()]))
    assert all(not run.font.bold for run in _runs(table.cell(0, 0)))
    assert _fill_hex(table.cell(0, 0)) is None


def test_c5_pptx_uppercase_table_prints_capitals():
    table = _only_table(_deck([_pptx_table(uppercase=True)]))
    assert table.cell(0, 0).text == "REF"
    assert table.cell(1, 1).text == "WC-1 BASIN"


def test_c5_pptx_uppercase_text_layer_prints_capitals_and_off_keeps_case():
    layer = {
        "kind": "text",
        "x_mm": 5,
        "y_mm": 5,
        "width_mm": 80,
        "height_mm": 10,
        "text": "Wall hung water closet",
        "fontFamily": "DM Sans",
        "fontSize": 12,
        "color": "#000000",
        "align": "left",
    }
    deck = _deck([{**layer, "uppercase": True}, {**layer, "y_mm": 40}])
    texts = sorted(s.text_frame.text for s in deck.slides[0].shapes if s.has_text_frame)
    assert texts == ["WALL HUNG WATER CLOSET", "Wall hung water closet"]
