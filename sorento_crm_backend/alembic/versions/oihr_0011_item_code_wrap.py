"""Order inquiry handover email: an ITEM CODE cell that carries an SO line description wraps
(SO-LINE-DESC, AC-14).

`<code> - <description>` is long, so the two ITEM CODE cells (ITEM CODE and NEW ITEM CODE) drop
`white-space:nowrap` when the line carries `item_wrap`, which the handover builder sets only
for a decorated line. A bare code keeps today's no-wrap. The text part is unchanged.

Updates ``email_templates`` (``code`` = ``TEMPLATE_CODE``) IN PLACE only while its
``layout_json`` and ``body_text`` are still exactly what `oihr_0010_so_remark_column` wrote; a
row an admin edited is left alone with a logged warning. Idempotent. Downgrade restores
`oihr_0010`'s document, read from that migration's own frozen constants.

Revision ID: oihr_0011_item_code_wrap
Revises: sld_0001_so_line_description
Create Date: 2026-10-30
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from alembic import op


revision = "oihr_0011_item_code_wrap"
down_revision = "sld_0001_so_line_description"
branch_labels = None
depends_on = None


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{name}_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load("oihr_0006_no_remark_column")
_PREVIOUS = _load("oihr_0010_so_remark_column")

_OLD_TD = '<td style="white-space:nowrap;padding:4px;">'
_NEW_TD = '<td style="{% if not line.item_wrap %}white-space:nowrap;{% endif %}padding:4px;">'
#: The two cells, told apart by what follows the opening tag.
_ITEM = "{% if not line.continued %}{% if line.was and line.was.item_code %}{{ line.was.item_code }}"
_NEW_ITEM = "{% if cols.item_code %}"


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"oihr_0011: expected one {old[:50]!r} in oihr_0010's document")
    return text.replace(old, new)


def _layout() -> dict:
    layout = copy.deepcopy(_PREVIOUS._LAYOUT)
    block = layout["blocks"][2]
    if block.get("type") != "custom_text":
        raise RuntimeError("oihr_0011: oihr_0010's line table block moved")
    html = _once(block["html"], _OLD_TD + _ITEM, _NEW_TD + _ITEM)
    block["html"] = _once(
        html,
        _NEW_ITEM + _OLD_TD + "{% if line.was and line.was.item_code %}{{ line.item_code",
        _NEW_ITEM + _NEW_TD + "{% if line.was and line.was.item_code %}{{ line.item_code",
    )
    return layout


_LAYOUT = _layout()
_BODY_TEXT = _PREVIOUS._BODY_TEXT


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
