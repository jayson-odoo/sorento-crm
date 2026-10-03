"""Publish the `ideate_extractor` no-problem rule to the live prompt registry.

The fallback template gained a rule: a message that only says the user wants to submit or
share an idea ("want to submit idea") has no problem, so the extractor leaves problem empty
instead of inventing one. A seeded install holds the old text as its `production` version and
`seed_prompt_registry` never updates a live row, so `bump_prompt_to_fallback` publishes the new
text as the next immutable version and moves the label. It is a no-op when production already
equals the fallback, so a re-run changes nothing. The seed runs first so a fresh database has a
row to compare against.

Revision ID: ideation_capture_0001
Revises: merge_03oct_join5
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_to_fallback, seed_prompt_registry

revision = "ideation_capture_0001"
down_revision = "merge_03oct_join5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())
    bump_prompt_to_fallback(op.get_bind(), "ideate_extractor")


def downgrade() -> None:
    # The published version stays: dropping it would strip any edit the owner published on
    # top of it, and an unused version costs nothing.
    pass
