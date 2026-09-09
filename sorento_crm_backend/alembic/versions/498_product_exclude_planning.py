"""`products` gains `exclude_from_planning` (S5, PLAN-reorder-feedback-9sep.md).

The buyer's own switch to keep a placeholder code (`**NEW`, `**SPARE PART`, `**REPLACE`,
`**REPAIR`, ...) out of the reorder engine. Defaults FALSE for every product with NO
backfill (G3, 9 Sep ruling): the captain chose the buyer flipping the four placeholder
codes by hand over marking them here, so this migration adds the column and nothing else.

Revision ID: 498_product_exclude_planning
Revises: 497_reorder_run_horizon_start
"""
import sqlalchemy as sa
from alembic import op

revision = "498_product_exclude_planning"
down_revision = "497_reorder_run_horizon_start"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS exclude_from_planning "
            "BOOLEAN NOT NULL DEFAULT false"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS exclude_from_planning"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
