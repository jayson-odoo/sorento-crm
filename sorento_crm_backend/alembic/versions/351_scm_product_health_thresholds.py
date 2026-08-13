"""Margin and turnover thresholds for the product-health advisory.

The margin verdict ("thin", "negative") and the discontinue advisory need a line the
business draws, not one the code invents. Both live on the planning policy beside the
level windows, NULL meaning "use the code default" (15% floor, 6 months) - the same
convention `level_study_months` / `level_cover_months` follow.

Revision ID: 351_scm_product_health_thresholds
Revises: 350_scm_level_suggestion_amend
"""
from alembic import op
import sqlalchemy as sa


revision = "351_scm_product_health_thresholds"
down_revision = "350_scm_level_suggestion_amend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_policy",
        sa.Column("margin_floor_pct", sa.Numeric(6, 2), nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_policy",
        sa.Column("dead_turnover_months", sa.Numeric(6, 2), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_policy", "dead_turnover_months", schema="scm")
    op.drop_column("reorder_policy", "margin_floor_pct", schema="scm")
