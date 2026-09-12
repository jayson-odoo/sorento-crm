"""Which PACKING ROW a shipment line came from (ruling 31, 10 Sep).

Placement is a fact about a row, not about a quantity. Convert used to infer "already
placed" by walking the placed quantity over a line's rows in `row_no` order, which is only
correct when the selection was a PREFIX of that list: untick the first carton, convert the
second, and the next convert reads "50 placed" as "the first row is placed" and ships the
35 twice while the 50 never ships at all (reviewer's repro on the Kailu fixture).

Nullable, because the same table records a line-grain placement (a PI line no packing list
ever mentioned) and a SKIP row, neither of which names a packing row.

Revision ID: 507_pi_link_packing_row
Revises: 506_scm_pi_consignee_ref
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "507_pi_link_packing_row"
down_revision = "506_scm_pi_consignee_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proforma_invoice_shipment_link",
        sa.Column(
            "proforma_invoice_packing_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice_packing_line.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="scm",
    )
    # The question asked of it on every convert is "which rows have a link already", so it
    # is indexed for that read rather than left to a sequential scan of the link table.
    op.create_index(
        "ix_scm_pi_shipment_link_packing_line",
        "proforma_invoice_shipment_link",
        ["proforma_invoice_packing_line_id"],
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scm_pi_shipment_link_packing_line",
        table_name="proforma_invoice_shipment_link",
        schema="scm",
    )
    op.drop_column(
        "proforma_invoice_shipment_link", "proforma_invoice_packing_line_id", schema="scm"
    )
