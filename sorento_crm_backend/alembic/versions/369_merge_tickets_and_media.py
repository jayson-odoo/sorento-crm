"""Join the intervention-ticket lane with the multimodal-media lane.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE head to aim at.

Both sides of this merge are themselves merge revisions, which is why two heads
survived a merge that already carried one each:

    368_merge_tickets_main     (main, PR #137: joins the 321..330 conversation
                                intervention-ticket chain back onto
                                367_promote_flyer_provenance)
    368_merge_media_and_flyer  (this branch: joins the 356..361 chatbot media /
                                AI-config chain back onto the same 367)

They share `367_promote_flyer_provenance` as their common ancestor and then fork
again, so neither is an ancestor of the other and the graph stays forked even
though the Python merged cleanly. Two heads is not a warning, it is a broken
deploy: `alembic upgrade head` refuses to guess.

The two lanes touch disjoint tables (conversation tickets, chat history,
message snippets and inbox permissions on one side; media jobs, AI provider
config and voice notices on the other), so order between them genuinely does
not matter.

The id is 23 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay within it
(see `tests/test_alembic_revision_ids.py`).

Revision ID: 369_merge_tickets_media
Revises: 368_merge_tickets_main, 368_merge_media_and_flyer
Create Date: 2026-08-17
"""

# revision identifiers, used by Alembic.
revision = "369_merge_tickets_media"
down_revision = (
    "368_merge_tickets_main",
    "368_merge_media_and_flyer",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
