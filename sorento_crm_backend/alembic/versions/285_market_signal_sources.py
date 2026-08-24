"""Add ``scm.market_signal.sources`` (JSONB) - multiple citation sources per signal.

SCM M8-F: the market card must cite SOURCES (several, when available) to prove the
figure is factual. A signal previously carried a single ``source_url``; this adds a
``sources`` JSONB list of ``{url, title}`` harvested from the web-search result. Legacy
rows keep working via a service-side fallback to ``[source_url]``.

Idempotent (``ADD COLUMN IF NOT EXISTS``) so a redeploy is safe.

Revision ID: 285_market_signal_sources
Revises: 284_seed_scm_reorder_run_task
Create Date: 2026-07-18
"""
from alembic import op


revision = "285_market_signal_sources"
down_revision = "284_seed_scm_reorder_run_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scm.market_signal ADD COLUMN IF NOT EXISTS sources JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scm.market_signal DROP COLUMN IF EXISTS sources")
