"""Add access_levels to forms and inbound_shipments for propagation from attachments.

Revision ID: 138_form_inbound_shipment_access_levels
Revises: 137_seed_external_promotion_numbering
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "138_form_inbound_shipment_access_levels"
down_revision = "137_seed_external_promotion_numbering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "forms",
        sa.Column(
            "access_levels",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"dealer\",\"end_user\"]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_forms_access_levels",
        "forms",
        ["access_levels"],
        postgresql_using="gin",
    )
    op.add_column(
        "inbound_shipments",
        sa.Column(
            "access_levels",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"dealer\",\"end_user\"]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_inbound_shipments_access_levels",
        "inbound_shipments",
        ["access_levels"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_shipments_access_levels", table_name="inbound_shipments")
    op.drop_column("inbound_shipments", "access_levels")
    op.drop_index("ix_forms_access_levels", table_name="forms")
    op.drop_column("forms", "access_levels")
