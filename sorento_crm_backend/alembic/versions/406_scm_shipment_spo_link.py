"""scm: shipment line -> SPO line link ("Create SPO" off a shipment).

`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision: "Separate button after
packing-list apply. The shipment page gets a Create SPO action she presses when ready."
This is the provenance half of that button - `scm.shipment_line_spo_link`, one row per
shipment line the action touched, pointing at the new `purchase_orders` line it became (or
carrying `unmatched_reason` when the line could not convert). See the model docstring
(`ShipmentLineSpoLink`, `app/models/scm.py`) for why this is a link table rather than a
column, mirroring `scm.proforma_invoice_shipment_link` (migration 405).

Revision ID: 406_scm_shipment_spo_link
Revises: 405_scm_pi_draft_shipment
Create Date: 2026-08-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "406_scm_shipment_spo_link"
down_revision = "405_scm_pi_draft_shipment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shipment_line_spo_link",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_shipment_spo_link_company_id"),
            nullable=True,
        ),
        sa.Column(
            "inbound_shipment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("inbound_shipments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inbound_shipment_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("inbound_shipment_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id",
            UUID(as_uuid=False),
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "purchase_order_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unmatched_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "ix_scm_shipment_spo_link_shipment", "shipment_line_spo_link",
        ["inbound_shipment_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_shipment_spo_link_po", "shipment_line_spo_link",
        ["purchase_order_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_shipment_spo_link_company_id", "shipment_line_spo_link",
        ["company_id"], schema="scm",
    )
    op.create_index(
        "uq_scm_shipment_spo_link_line", "shipment_line_spo_link",
        ["inbound_shipment_line_id"], unique=True, schema="scm",
    )


def downgrade() -> None:
    op.drop_table("shipment_line_spo_link", schema="scm")
