"""`product_suppliers.standard_lead_time_days` may be empty (#1288, round 6, R3).

Owner ruling of 28 Sep 2026 on PR #1305: the cost upload no longer asks for a lead time. A
link the upload creates takes the supplier's most common lead time across its links, else it
stays empty, and Apply never blocks on it (AC-S2-05 as amended). The column was NOT NULL with
no default, so "stays empty" needs the constraint dropped. Every reader already copes with a
null (the reorder engine falls back to its default, the SCM SQL sorts NULLS LAST).

The downgrade fills an empty lead time with 90 days, the value
`product_rules.resolve_standard_lead_time_days` falls back to when the setting is unset, so
the NOT NULL can come back.

Revision ID: cpc3_lead_time_nullable
Revises: cpc2_cost_price_tick_schedule
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa


revision = "cpc3_lead_time_nullable"
down_revision = "cpc2_cost_price_tick_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "product_suppliers", "standard_lead_time_days",
        existing_type=sa.Integer(), nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE product_suppliers SET standard_lead_time_days = 90 "
        "WHERE standard_lead_time_days IS NULL"
    )
    op.alter_column(
        "product_suppliers", "standard_lead_time_days",
        existing_type=sa.Integer(), nullable=False,
    )
