"""Order inquiry handover email: REMARK as the last column of the SO table (FULFIL-SO-REMARK).

The SO table (S/O NO | SO DATE | CUSTOMER | PROJECT) gains REMARK, the per-SO remark staff see
and edit on the Confirm split page (`handover.orders[].remark`). The text part, which listed the
SO facts as a dashed line, prints the same table as pipe-separated rows. The line table is
unchanged.

Updates ``email_templates`` (``code`` = ``TEMPLATE_CODE``) IN PLACE only while its
``layout_json`` and ``body_text`` are still exactly what `oihr_0009_split_rows` wrote; a row an
admin edited is left alone with a logged warning. A database with no row gets one inserted.
Idempotent. Downgrade restores `oihr_0009`'s document, read from that migration's own frozen
constants.

Revision ID: oihr_0010_so_remark_column
Revises: fsr_0001_so_remark_columns
Create Date: 2026-10-25
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from alembic import op


revision = "oihr_0010_so_remark_column"
down_revision = "fsr_0001_so_remark_columns"
branch_labels = None
depends_on = None


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{name}_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load("oihr_0006_no_remark_column")
_PREVIOUS = _load("oihr_0009_split_rows")

_TH = '<th width="{w}%" style="width:{w}%;white-space:nowrap;padding:4px;">{name}</th>'
_HEAD_OLD = "".join(
    _TH.format(w=w, name=n)
    for w, n in ((13, "S/O NO"), (13, "SO DATE"), (32, "CUSTOMER"), (42, "PROJECT"))
)
_HEAD_NEW = "".join(
    _TH.format(w=w, name=n)
    for w, n in (
        (11, "S/O NO"), (11, "SO DATE"), (28, "CUSTOMER"), (30, "PROJECT"), (20, "REMARK"),
    )
)
_CELL_OLD = '<td style="padding:4px;">{{ order.project | default("", true) }}</td>\n'
_CELL_NEW = _CELL_OLD + '      <td style="padding:4px;">{{ order.remark | default("", true) }}</td>\n'

_TEXT_OLD = (
    '{% for order in handover.orders %}{{ order.so_number | default("", true) }}'
    "{% if order.so_date %} - {{ order.so_date }}{% endif %}"
    "{% if order.customer %} - {{ order.customer }}{% endif %}"
    "{% if order.project %} - {{ order.project }}{% endif %}\n{% endfor %}\n"
)
_TEXT_NEW = (
    "S/O NO | SO DATE | CUSTOMER | PROJECT | REMARK\n"
    '{% for order in handover.orders %}{{ order.so_number | default("", true) }}'
    ' | {{ order.so_date | default("", true) }} | {{ order.customer | default("", true) }}'
    ' | {{ order.project | default("", true) }} | {{ order.remark | default("", true) }}\n'
    "{% endfor %}\n"
)


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"oihr_0010: expected one {old[:50]!r} in oihr_0009's document")
    return text.replace(old, new)


def _layout() -> dict:
    layout = copy.deepcopy(_PREVIOUS._LAYOUT)
    block = layout["blocks"][2]
    if block.get("type") != "custom_text":
        raise RuntimeError("oihr_0010: oihr_0009's SO table block moved")
    html = _once(block["html"], _HEAD_OLD, _HEAD_NEW)
    block["html"] = _once(html, _CELL_OLD, _CELL_NEW)
    return layout


_LAYOUT = _layout()
_BODY_TEXT = _once(_PREVIOUS._BODY_TEXT, _TEXT_OLD, _TEXT_NEW)


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
