"""add nullable ideation_product_id to respond_workspaces (ideation pipeline)

Binds a sorento workspace to exactly one shared-service ideation Product (kind
software). The value is a shared-service Product UUID stored as text; it is
server-side only and NEVER rendered in the FE. NULL keeps ideation dormant /
fail-closed for that workspace (the ideate brain path makes no create_idea call
without a binding).

Idempotent: ADD/DROP COLUMN ... IF (NOT) EXISTS so a re-run is a no-op. Chained
onto 272 (the ideate-parser prompt head) so the alembic graph stays a single
linear head - see the dual-head / down_revision lessons in LESSONS-LEARNT.md.

See documentation/plans/ideation/PLAN-ideation-ideate-intent.md (Group C, AC-30).

Revision ID: 273_ideation_product_binding
Revises: 272_ideate_intent_parser_prompt
Create Date: 2026-07-19
"""
from alembic import op

revision = "273_ideation_product_binding"
down_revision = "272_ideate_intent_parser_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_product_id VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces "
        "DROP COLUMN IF EXISTS ideation_product_id"
    )
