"""Make promotions.start_date and promotions.end_date nullable (n8n posts header before dates resolved).

Revision ID: 192_promotion_dates_nullable
Revises: 191_inbound_shipment_number_nullable
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op


revision = "192_promotion_dates_nullable"
down_revision = "191_inbound_shipment_number_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("promotions", "start_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("promotions", "end_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    op.alter_column("promotions", "start_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("promotions", "end_date", existing_type=sa.Date(), nullable=False)
