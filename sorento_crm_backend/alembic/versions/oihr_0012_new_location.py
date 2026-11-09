"""Order inquiry handover email: LOCATION / NEW LOCATION for a line AutoCount moved
(SPLIT-SHEET-LOCATION, owner change request 9 Nov 2026).

Mirrors QTY / NEW QTY and DELIVERY / NEW DATE: a line whose location moved carries the old
location as `was.location`. LOCATION then prints that old location and a NEW LOCATION column,
right after it, prints the line's new one. The column shows only when some line in the email
moved, and is blank on every other line. The REMARK `NEW LOCATION (was X)` stays as the
handover builder writes it. HTML and text part alike.

Updates ``email_templates`` (``code`` = ``TEMPLATE_CODE``) IN PLACE only while its
``layout_json`` and ``body_text`` are still exactly what `oihr_0011_item_code_wrap` wrote; a
row an admin edited is left alone with a logged warning. Idempotent. Downgrade restores
`oihr_0011`'s document, read from that migration's own frozen constants.

Revision ID: oihr_0012_new_location
Revises: town_0001_town_days
Create Date: 2026-11-09
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from alembic import op


revision = "oihr_0012_new_location"
down_revision = "town_0001_town_days"
branch_labels = None
depends_on = None


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{name}_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load("oihr_0006_no_remark_column")
_PREVIOUS = _load("oihr_0011_item_code_wrap")

#: The column flags, set from the lines (both parts open with the same statement).
_COLS_OLD = (
    "{%- set cols = namespace(item_code=false, qty=false, delivery_date=false) -%}"
    "{%- for line in handover.lines -%}"
)
_COLS_NEW = (
    "{%- set cols = namespace(location=false, item_code=false, qty=false, delivery_date=false) -%}"
    "{%- for line in handover.lines -%}"
    "{%- if line.was and line.was.location %}{% set cols.location = true %}{% endif -%}"
)
#: LOCATION: the old location on a moved line, else the line's own.
_LOC_VALUE_OLD = '{% if not line.continued %}{{ line.location | default("", true) }}{% endif %}'
_LOC_VALUE_NEW = (
    "{% if not line.continued %}{% if line.was and line.was.location %}{{ line.was.location }}"
    '{% else %}{{ line.location | default("", true) }}{% endif %}{% endif %}'
)
#: NEW LOCATION: the line's own (new) location, on a moved line only.
_NEW_LOC_VALUE = (
    '{% if not line.continued and line.was and line.was.location %}'
    '{{ line.location | default("", true) }}{% endif %}'
)
_TD = '<td style="white-space:nowrap;padding:4px;">'


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"oihr_0012: expected one {old[:60]!r} in oihr_0011's document")
    return text.replace(old, new)


def _layout() -> dict:
    layout = copy.deepcopy(_PREVIOUS._LAYOUT)
    block = layout["blocks"][2]
    if block.get("type") != "custom_text":
        raise RuntimeError("oihr_0012: oihr_0011's line table block moved")
    html = block["html"]
    html = _once(html, _COLS_OLD, _COLS_NEW)
    html = _once(
        html,
        "{%- set span = 5 + ",
        "{%- set span = 5 + (1 if cols.location else 0) + ",
    )
    html = _once(
        html,
        "{%- set total = 16 + 26 + 10 + 15 + 30 + ",
        "{%- set total = 16 + 26 + 10 + 15 + 30 + (16 if cols.location else 0) + ",
    )
    html = _once(
        html,
        "{%- set w = namespace(loc=(16 * 100) // total, ",
        "{%- set w = namespace(loc=(16 * 100) // total, "
        "new_loc=((16 * 100) // total if cols.location else 0), ",
    )
    html = _once(html, "{%- set rem = 100 - w.loc - ", "{%- set rem = 100 - w.loc - w.new_loc - ")
    html = _once(
        html,
        'white-space:nowrap;padding:4px;">LOCATION</th>',
        'white-space:nowrap;padding:4px;">LOCATION</th>'
        '{% if cols.location %}<th width="{{ w.new_loc }}%" style="width:{{ w.new_loc }}%;'
        'white-space:nowrap;padding:4px;">NEW LOCATION</th>{% endif %}',
    )
    html = _once(
        html,
        _TD + _LOC_VALUE_OLD + "</td>",
        _TD + _LOC_VALUE_NEW + "</td>\n      "
        "{% if cols.location %}" + _TD + _NEW_LOC_VALUE + "</td>{% endif %}",
    )
    block["html"] = html
    return layout


def _body_text() -> str:
    text = _PREVIOUS._BODY_TEXT
    text = _once(text, _COLS_OLD, _COLS_NEW)
    text = _once(
        text,
        "LOCATION | ITEM CODE |",
        "LOCATION |{% if cols.location %} NEW LOCATION |{% endif %} ITEM CODE |",
    )
    return _once(
        text,
        _LOC_VALUE_OLD + " | ",
        _LOC_VALUE_NEW + " |{% if cols.location %} " + _NEW_LOC_VALUE + " |{% endif %} ",
    )


_LAYOUT = _layout()
_BODY_TEXT = _body_text()


def upgrade() -> None:
    _BASE._set(
        op.get_bind(),
        layout=_LAYOUT,
        body_html=_BASE._mirror(_LAYOUT),
        body_text=_BODY_TEXT,
        only_when=(_PREVIOUS._LAYOUT, _PREVIOUS._BODY_TEXT),
        direction="upgrade",
    )


def downgrade() -> None:
    _BASE._set(
        op.get_bind(),
        layout=_PREVIOUS._LAYOUT,
        body_html=_BASE._mirror(_PREVIOUS._LAYOUT),
        body_text=_PREVIOUS._BODY_TEXT,
        only_when=(_LAYOUT, _BODY_TEXT),
        direction="downgrade",
    )
