"""seed semantic_parser prompt key (M0 structured-parser revamp)

Idempotently seeds the new ``semantic_parser`` PROMPT_KEY at v1 from its
hardcoded fallback with a ``production`` label. The ``reformulator`` + ``router``
keys are now dormant (``active=False`` in the registry) but their DB rows are
left intact for trace history + prompt rollback. Re-running the shared seed is
safe (JOIN-based set-to-correct-value; never spawns duplicate versions/labels).

See ``docs/plans/PLAN-ai-assistant-structured-parser.md``.

Revision ID: 261_semantic_parser_prompt
Revises: 260_variant_graph_trgm
Create Date: 2026-07-04
"""
from alembic import op

from app.services.ai_prompt_seed import seed_prompt_registry


revision = "261_semantic_parser_prompt"
down_revision = "260_variant_graph_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Seeds every registered PROMPT_KEY missing a v1/production row — which now
    # includes ``semantic_parser``. Existing keys are untouched.
    seed_prompt_registry(op.get_bind())


def downgrade() -> None:
    # Data-only seed; no schema change to reverse. Leaving the seeded rows in
    # place is harmless (an unused prompt version).
    pass
