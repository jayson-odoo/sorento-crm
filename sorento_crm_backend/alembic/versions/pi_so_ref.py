"""The PI header carries a distinct SO number too, beside container_ref/seal_ref/bl_ref.

Owner ruling (25 Sep 2026, PLAN-pi-header-fields-convert-fixes-24sep.md, R-E): SO is its
own header field, never carried off `bl_ref` any more (the 6 Sep ruling this supersedes -
`bl_ref`'s own docstring called that "historical"). Some suppliers' `提单号` genuinely is a
bill of lading; others' is the forwarder's booking/SO number - the mapper now lets the
operator remap `提单号` (or any other label) to `so_no` per supplier, same as any other
header field (F1/F2). No shared alias is seeded here: `提单号` keeps resolving to `bl_no`
by default (375/311's own shared row, unchanged), and an operator who needs `so_no`
instead maps it for that one supplier.

Convert (`_convert_carry`/`convert_to_draft_shipment`) now writes `so_ref` onto the
draft's `forwarder_order_ref` (the SO field) and `bl_ref` onto its `bill_of_lading_number`
(a column that existed already but nothing had ever written to), rather than folding both
into `forwarder_order_ref` alone.

Revision ID: pi_so_ref
Revises: ifa_bare_container_seal
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op

revision = "pi_so_ref"
down_revision = "ifa_bare_container_seal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proforma_invoice", sa.Column("so_ref", sa.String(100), nullable=True), schema="scm",
    )


def downgrade() -> None:
    op.drop_column("proforma_invoice", "so_ref", schema="scm")
