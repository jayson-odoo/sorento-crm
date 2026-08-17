"""Rejoin the multimodal media chain with main's flyer/promotion chain.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` (and
the `alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE head to aim at.

**What happened.** The multimodal media endpoint branch grew its own line off
`885010d94677` (`356_chatbot_media_endpoint` through `361_ai_config_gemini_key`:
the media tables, the media permissions, the image-model tiers, the voice
degraded notices and the per-provider Gemini key column). While that ran, main
grew the user-management read gates, the promotion types, the flyer background
job and the flyer provenance promote, ending at
`367_promote_flyer_provenance`. Neither head is an ancestor of the other, so the
merge of the two carries two heads and alembic refuses to stamp or upgrade until
they are joined.

Both lines are published, so neither can be renumbered; a merge revision is how
alembic expresses "these two happened, in either order". The two lines touch
disjoint tables (media/AI config versus promotions/flyer readings/permission
seeds), so order between them genuinely does not matter.

The id stays under 32 characters because a database provisioned by a plain
`alembic stamp` gets `alembic_version.version_num varchar(32)` (see
`tests/test_alembic_revision_ids.py`).

Revision ID: 368_merge_media_and_flyer
Revises: 361_ai_config_gemini_key, 367_promote_flyer_provenance
Create Date: 2026-08-17
"""

# revision identifiers, used by Alembic.
revision = "368_merge_media_and_flyer"
down_revision = (
    "361_ai_config_gemini_key",
    "367_promote_flyer_provenance",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
