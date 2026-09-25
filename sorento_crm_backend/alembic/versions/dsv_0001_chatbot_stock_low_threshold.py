"""Chatbot stock ask v2 S3 (PLAN-chatbot-stock-ask-v2-24sep.md) - ports PR #1118's
`dsv_0001` (branch feat/chatbot-dealer-stock-verdict, not merged, owner ruling 24 Sep
2026) so the ported availability-branch read (`StockService._apply_stock_visibility`)
has a column to read: the low-stock threshold `stock_verdict.verdict()` compares ask
against available/incoming/purchase, "make the T configurable" (owner).

Additive, NOT NULL, server default 50 (the owner's own matrix threshold). No backfill:
this is a new decision with no prior value anywhere to copy from, and 50 is the safe
landing state for every existing tenant. `ADD COLUMN IF NOT EXISTS` (`500_product_
exclude_planning`'s idiom, also used by `sa2_0002_contact_toggles`) keeps this
re-runnable against a schema where `Base.metadata.create_all` already created the
ORM-mapped column.

R11 (lavish review, 24 Sep 2026): the column and its Settings > Chatbot card stay
exactly as #1118 lands them - v2's four branches (B1 to B4) never read it.

Revision ID: dsv_0001
Revises: sa2_0002_contact_toggles
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "dsv_0001"
down_revision = "sa2_0002_contact_toggles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
            "chatbot_stock_low_threshold_pct INTEGER NOT NULL DEFAULT 50"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE system_settings DROP COLUMN IF EXISTS "
            "chatbot_stock_low_threshold_pct"
        )
    )
