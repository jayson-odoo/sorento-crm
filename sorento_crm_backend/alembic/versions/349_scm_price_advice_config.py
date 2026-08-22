"""S13e: the price-advice thresholds become planning-policy configuration.

The S12c staleness window (180 days) and movement threshold (5%) were constants returned in
the payload so the screen could state the rule it applied - honest, but still a deploy to
change. Per the user's rule ("configurable from day 1, not later") they move onto
`scm.reorder_policy`. NULL = the code default, so existing behaviour is unchanged.

The movement threshold also gates the S13e change-supplier suggestion: an alternative
supplier is only proposed when their price is materially lower, and "materially" is this
same knob - one figure for "a price difference worth acting on", not two.

Revision ID: 349_scm_price_advice_config
Revises: 348_scm_trajectory_windows
"""
import sqlalchemy as sa
from alembic import op

revision = "349_scm_price_advice_config"
down_revision = "348_scm_trajectory_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_policy",
        sa.Column("price_stale_after_days", sa.Integer, nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_policy",
        sa.Column("price_movement_threshold_pct", sa.Numeric(6, 2), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_policy", "price_movement_threshold_pct", schema="scm")
    op.drop_column("reorder_policy", "price_stale_after_days", schema="scm")
