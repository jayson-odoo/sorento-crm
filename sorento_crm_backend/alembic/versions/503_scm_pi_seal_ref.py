"""The PI header carries a seal number too, beside container_ref/bl_ref.

Standing ruling for S2/S4/S5 (captain, 9 Sep): the packing document fills `container_ref`/
`seal_ref`/`bl_ref` on the PI header when the PI itself stated none - convert's header
carry-over (AC-D2c) reads all three onto the draft shipment.

Revision ID: 503_scm_pi_seal_ref
Revises: 502_scm_pi_packing_qty_null
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

revision = "503_scm_pi_seal_ref"
down_revision = "502_scm_pi_packing_qty_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proforma_invoice", sa.Column("seal_ref", sa.String(100), nullable=True), schema="scm",
    )


def downgrade() -> None:
    op.drop_column("proforma_invoice", "seal_ref", schema="scm")
