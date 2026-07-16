"""SCM M5 Part B — market research topics, cached signals, run observability.

Adds three ``scm.*`` tables backing the advisory-only market layer (the M0 schema
migration 273 created the reorder brain; these were deferred to M5):

  * ``scm.market_research_topic`` — user-configured web-search topics (label,
    optional category_ref/currency match keys, free-form search_prompt, cadence).
  * ``scm.market_signal`` — cached web-search output (value/trend/summary/source_url),
    ``topic_id`` FK → market_research_topic ON DELETE CASCADE.
  * ``scm.market_research_run`` — one row per research run (running → completed |
    failed + topic_count/signal_count/error_text), mirroring ``scm.scm_analytics_run``.

``reorder_recommendation.market_advisory`` already exists (M5 prose columns) — NOT
re-added here. Advisory-only: no numeric column feeds the deterministic engine.

**Idempotent by design.** On some environments these tables were created out of
band (an earlier WIP), with ``market_research_run`` carrying an older
``counts JSONB`` shape instead of the typed ``topic_count``/``signal_count``
columns. Every statement uses ``IF [NOT] EXISTS`` and the run table is reconciled
column-by-column, so this migration is safe whether the tables pre-exist (local
prod-copy) or not (fresh deploy).

Revision ID: 280_scm_m5_market_research
Revises: 279_scm_m4_decision_numbering
Create Date: 2026-07-17
"""
from alembic import op


revision = "280_scm_m5_market_research"
down_revision = "279_scm_m4_decision_numbering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scm")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scm.market_research_topic (
            id UUID PRIMARY KEY,
            label VARCHAR(255) NOT NULL,
            category_ref VARCHAR(255),
            currency VARCHAR(3),
            search_prompt TEXT,
            cadence VARCHAR(50),
            is_active BOOLEAN NOT NULL DEFAULT true,
            source_system VARCHAR,
            source_ref VARCHAR,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scm.market_signal (
            id UUID PRIMARY KEY,
            topic_id UUID REFERENCES scm.market_research_topic(id) ON DELETE CASCADE,
            category_ref VARCHAR(255),
            currency VARCHAR(3),
            value NUMERIC,
            trend VARCHAR(30),
            summary TEXT,
            source_url TEXT,
            captured_at TIMESTAMP WITHOUT TIME ZONE,
            source_system VARCHAR,
            source_ref VARCHAR,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scm_market_signal_topic_id "
        "ON scm.market_signal (topic_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scm_market_signal_category_ref "
        "ON scm.market_signal (category_ref)"
    )

    # Fresh deploy: create with the final typed shape.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scm.market_research_run (
            id UUID PRIMARY KEY,
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            started_at TIMESTAMP WITHOUT TIME ZONE,
            finished_at TIMESTAMP WITHOUT TIME ZONE,
            topic_count INTEGER,
            signal_count INTEGER,
            error_text TEXT,
            source_system VARCHAR,
            source_ref VARCHAR,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    # Pre-existing (out-of-band) run table: reconcile to the typed shape.
    op.execute(
        "ALTER TABLE scm.market_research_run "
        "ADD COLUMN IF NOT EXISTS topic_count INTEGER"
    )
    op.execute(
        "ALTER TABLE scm.market_research_run "
        "ADD COLUMN IF NOT EXISTS signal_count INTEGER"
    )
    op.execute(
        "ALTER TABLE scm.market_research_run DROP COLUMN IF EXISTS counts"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scm.market_research_run")
    op.execute("DROP INDEX IF EXISTS scm.ix_scm_market_signal_category_ref")
    op.execute("DROP INDEX IF EXISTS scm.ix_scm_market_signal_topic_id")
    op.execute("DROP TABLE IF EXISTS scm.market_signal")
    op.execute("DROP TABLE IF EXISTS scm.market_research_topic")
