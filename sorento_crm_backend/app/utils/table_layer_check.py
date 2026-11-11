"""SPEC-SHEET-DESIGNER-PARITY B: the one check for a designer `table` layer, shared by the spec
sheet page edits and the tag template saves.

Bounded shape (rows, columns, a full grid) and plain colours only: a colour reaches a CSS value on
the print page, which a headless browser loads, so `url(...)` and friends must never get there.
"""
from __future__ import annotations

import re
from typing import Any

TABLE_LINES_MAX = 50
#: What the frontend's `safeColour` accepts (hex, rgb()), plus `transparent` and blank.
_COLOUR = re.compile(
    r"^(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)|transparent)?$",
    re.IGNORECASE,
)


def _colour(value: Any) -> bool:
    return value is None or (isinstance(value, str) and bool(_COLOUR.match(value.strip())))


def table_props_problem(props: Any) -> str | None:
    """A sentence naming what is wrong with a table layer's props, or None."""
    if not isinstance(props, dict):
        return "A table's properties are malformed."
    columns, rows, cells = props.get("columns"), props.get("rows"), props.get("cells")
    if not all(isinstance(v, list) for v in (columns, rows, cells)):
        return "A table is malformed."
    if not (1 <= len(columns) <= TABLE_LINES_MAX and 1 <= len(rows) <= TABLE_LINES_MAX):
        return "A table can have 1 to 50 rows and columns."
    if len(cells) != len(rows) or any(not isinstance(r, list) or len(r) != len(columns) for r in cells):
        return "A table's cells must match its rows and columns."
    if not _colour(props.get("color")):
        return "A table has a colour that is not a plain colour."
    for row in cells:
        for cell in row:
            if not isinstance(cell, dict):
                return "A table cell is malformed."
            if not _colour(cell.get("fill")):
                return "A table cell has a fill that is not a plain colour."
            border = cell.get("border")
            if border is not None and not isinstance(border, dict):
                return "A table cell border is malformed."
            for side in (border or {}).values():
                if isinstance(side, dict) and not _colour(side.get("color")):
                    return "A table border has a colour that is not a plain colour."
    return None


def doc_table_problem(doc: Any) -> str | None:
    """The first table problem among a template document's layers; a document with none is fine."""
    layers = doc.get("layers") if isinstance(doc, dict) else None
    for layer in layers if isinstance(layers, list) else []:
        props = layer.get("props") if isinstance(layer, dict) else None
        is_table = isinstance(layer, dict) and (
            layer.get("type") == "table" or (isinstance(props, dict) and props.get("kind") == "table")
        )
        if is_table:
            problem = table_props_problem(layer.get("props"))
            if problem:
                return problem
    return None
