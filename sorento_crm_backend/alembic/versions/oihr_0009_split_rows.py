"""Order inquiry handover email: a split line's later rows print QTY and DELIVERY blank
(OI-LINE-SPLIT round 3, UAC AC-G6 / AC-G9, `documentation/plans/scm/oi-line-split-16oct-
acceptance-criteria.md`).

A split line prints one row per split under the SO line, like the owner's own Excel:
LOCATION, ITEM CODE, QTY and DELIVERY on the line's first row only (AC-G11), NEW QTY / NEW
DATE / REMARK on every row. The line items carry `continued` on every row after a line's
first; this is `oihr_0008`'s document with that one rule added to those four cells (HTML and
text part). Every other cell and the existing blank rule are unchanged.

Updates ``email_templates`` (``code`` = ``TEMPLATE_CODE``) IN PLACE only while its
``layout_json`` and ``body_text`` are still exactly what `oihr_0008_so_table_on_top` wrote; a
row an admin edited is left alone with a logged warning. A database with no row gets one
inserted. Idempotent. Downgrade restores `oihr_0008`'s document, read from that migration's
own frozen constants.

Revision ID: oihr_0009_split_rows
Revises: ols_0001_so_line_splits
Create Date: 2026-10-18
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from alembic import op


revision = "oihr_0009_split_rows"
down_revision = "ols_0001_so_line_splits"
branch_labels = None
depends_on = None


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{name}_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load("oihr_0006_no_remark_column")
_PREVIOUS = _load("oihr_0008_so_table_on_top")

_QTY = "{% if line.was and line.was.qty %}{{ line.was.qty }}"
_DELIVERY = "{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}"
_BLANK = "{% if line.continued %}{% elif "
#: LOCATION and ITEM CODE, as `oihr_0008` prints them in the HTML part and the text part.
_LOCATION = '{{ line.location | default("", true) }}'
_ITEM = (
    "{% if line.was and line.was.item_code %}{{ line.was.item_code }}{% else %}"
    '{{ line.item_code | default("", true) }}{% endif %}'
)


def _continued(text: str) -> str:
    """QTY, DELIVERY, LOCATION and ITEM CODE blank on a continued row (AC-G6, AC-G11); fails
    loudly if `oihr_0008`'s text moved."""
    for old in (_QTY, _DELIVERY):
        if text.count(old) != 1:
            raise RuntimeError(f"oihr_0009: expected one {old[:40]!r} in oihr_0008's document")
        text = text.replace(old, _BLANK + old[len("{% if "):])
    for old in (_LOCATION, _ITEM):
        if text.count(old) != 1:
            raise RuntimeError(f"oihr_0009: expected one {old[:40]!r} in oihr_0008's document")
        text = text.replace(old, "{% if not line.continued %}" + old + "{% endif %}")
    return text


def _layout() -> dict:
    layout = copy.deepcopy(_PREVIOUS._LAYOUT)
    block = layout["blocks"][2]
    if block.get("type") != "custom_text":
        raise RuntimeError("oihr_0009: oihr_0008's line table block moved")
    block["html"] = _continued(block["html"])
    return layout


_LAYOUT = _layout()
_BODY_TEXT = _continued(_PREVIOUS._BODY_TEXT)


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
