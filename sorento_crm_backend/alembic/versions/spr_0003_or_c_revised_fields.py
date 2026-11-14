"""Spare part request: a revision proposes a product and a line delivery date; the purchasing
email names an order request's own facts.

SPARE-PART-OR-B C (UAC documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md,
C4.1 + C2.4 + "Migration"). Additive only:

* `projects.order_inquiry_rows.revised_product_id uuid` (FK products, NULL): the product an
  open revision proposes for the row.
* `projects.order_inquiry_rows.revised_delivery_date date` (NULL): the line delivery date an
  open revision proposes.
* `projects.order_inquiry_rows.revised_description text` (NULL): the description typed for
  a revision's product swap (fix round 1, R2; NULL takes the new product's name).

Then the guarded template step (`relabel_handover_template`): the seeded default handover
email `order_inquiry_handover_default` reads OR NO / OR DATE / REQUESTER / REASON over its
order table when every order in the email is an order request (`order.is_order_request`),
and S/O NO / SO DATE / CUSTOMER / PROJECT otherwise. The row is updated IN PLACE only while
its `layout_json` and `body_text` are still exactly what `oihr_0012_new_location` wrote; a row
an admin edited is left alone with a logged warning (`oihr_0006._set`). Idempotent. Downgrade
restores `oihr_0012`'s document under the same guard, then drops the two columns.

Revision ID: spr_0003_or_c_revised_fields
Revises: spr_0002_or_b_oi_no
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "spr_0003_or_c_revised_fields"
down_revision = "spr_0002_or_b_oi_no"
branch_labels = None
depends_on = None


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{name}_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE = _load("oihr_0006_no_remark_column")
_PREVIOUS = _load("oihr_0012_new_location")

#: True when every order the email names is an order request (one write never mixes the two:
#: an order request is raised by its own approval, a sales order by the board Confirm).
_OR_HEAD = (
    '{% set or_head = (handover.orders | selectattr("is_order_request") | list | length)'
    " == (handover.orders | length) and (handover.orders | length) > 0 %}"
)
_LABELS = (("S/O NO", "OR NO"), ("SO DATE", "OR DATE"), ("CUSTOMER", "REQUESTER"), ("PROJECT", "REASON"))


def _label(so_label: str, or_label: str) -> str:
    return "{% if or_head %}" + or_label + "{% else %}" + so_label + "{% endif %}"


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"spr_0003: expected one {old[:60]!r} in oihr_0012's document")
    return text.replace(old, new)


def _layout() -> dict:
    layout = copy.deepcopy(_PREVIOUS._LAYOUT)
    block = layout["blocks"][2]
    if block.get("type") != "custom_text":
        raise RuntimeError("spr_0003: oihr_0012's order table block moved")
    html = block["html"]
    for so_label, or_label in _LABELS:
        html = _once(
            html,
            f'white-space:nowrap;padding:4px;">{so_label}</th>',
            f'white-space:nowrap;padding:4px;">{_label(so_label, or_label)}</th>',
        )
    block["html"] = _OR_HEAD + html
    return layout


def _body_text() -> str:
    text = _PREVIOUS._BODY_TEXT
    header = " | ".join(_label(so, or_) for so, or_ in _LABELS) + " | REMARK\n"
    text = _once(text, "S/O NO | SO DATE | CUSTOMER | PROJECT | REMARK\n", header)
    return _OR_HEAD + text


_LAYOUT = _layout()
_BODY_TEXT = _body_text()


def relabel_handover_template(bind) -> None:
    """C2.4: the seeded default handover template takes the order request labels, only while
    it is still exactly `oihr_0012`'s document."""
    _BASE._set(
        bind,
        layout=_LAYOUT,
        body_html=_BASE._mirror(_LAYOUT),
        body_text=_BODY_TEXT,
        only_when=(_PREVIOUS._LAYOUT, _PREVIOUS._BODY_TEXT),
        direction="upgrade",
    )


def upgrade() -> None:
    op.add_column(
        "order_inquiry_rows",
        sa.Column(
            "revised_product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("revised_delivery_date", sa.Date(), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("revised_description", sa.Text(), nullable=True),
        schema="projects",
    )
    relabel_handover_template(op.get_bind())


def downgrade() -> None:
    _BASE._set(
        op.get_bind(),
        layout=_PREVIOUS._LAYOUT,
        body_html=_BASE._mirror(_PREVIOUS._LAYOUT),
        body_text=_PREVIOUS._BODY_TEXT,
        only_when=(_LAYOUT, _BODY_TEXT),
        direction="downgrade",
    )
    op.drop_column("order_inquiry_rows", "revised_description", schema="projects")
    op.drop_column("order_inquiry_rows", "revised_delivery_date", schema="projects")
    op.drop_column("order_inquiry_rows", "revised_product_id", schema="projects")
