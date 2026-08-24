"""SCM M7 - market-research priority factor.

Adds an opt-in per-run flag (`scm.reorder_run.include_market`) and a configurable
market weight on the cash-ranking policy (`scm.cash_ranking_policy.weight_market`).
Both idempotent (ADD COLUMN IF NOT EXISTS) so a redeploy is safe.
"""
from alembic import op

revision = "283_scm_market_priority_factor"
down_revision = "282_scm_run_overview"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE scm.reorder_run "
        "ADD COLUMN IF NOT EXISTS include_market boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE scm.cash_ranking_policy "
        "ADD COLUMN IF NOT EXISTS weight_market numeric"
    )


def downgrade():
    op.execute("ALTER TABLE scm.cash_ranking_policy DROP COLUMN IF EXISTS weight_market")
    op.execute("ALTER TABLE scm.reorder_run DROP COLUMN IF EXISTS include_market")
