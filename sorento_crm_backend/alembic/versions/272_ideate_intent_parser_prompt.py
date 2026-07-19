"""publish semantic_parser prompt with the ideate intent line (ideation pipeline)

Republishes the ``semantic_parser`` prompt key as a NEW immutable version whose
text is the current hardcoded fallback (now carrying the ``ideate`` intent line)
and moves the ``production`` label to it. Existing installs hold a seeded v1 as
``production``; the plain seed only inserts a missing v1, so a fallback change
would otherwise never reach the runtime. Idempotent: a second run is a no-op
because the production text already equals the fallback.

See ``documentation/plans/ideation/PLAN-ideation-ideate-intent.md`` (Group A).

Revision ID: 272_ideate_intent_parser_prompt
Revises: 9785e8947154
Create Date: 2026-07-19
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_to_fallback, seed_prompt_registry


revision = "272_ideate_intent_parser_prompt"
# Re-chained onto main's post-SCM-merge head (9785e8947154) so the ideation
# migrations sit after the SCM chain instead of forking a second head off 271.
down_revision = "9785e8947154"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fresh installs (no seeded rows yet) get every key at v1 from its fallback,
    # which already includes the ideate line.
    seed_prompt_registry(op.get_bind())
    # Existing installs: publish the updated semantic_parser fallback as a new
    # version + move the production label. No-op when already current.
    bump_prompt_to_fallback(op.get_bind(), "semantic_parser")


def downgrade() -> None:
    # Data-only publish; nothing schema-level to reverse. Leaving the published
    # version + label in place is harmless.
    pass
