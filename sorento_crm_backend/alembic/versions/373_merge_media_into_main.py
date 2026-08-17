"""Join the multimodal-media lane onto the merge main already cut for its own lanes.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE head to aim at.

Two heads meet here:

    372_merge_three_heads    (main: joins the three lanes that each cut their own
                              merge off 368_merge_tickets_main - onboarding
                              intake, product spec verification, brand-aware SLA
                              routing)
    369_merge_tickets_media  (this branch: the 356..361 chatbot media /
                              AI-config chain, already joined to the
                              intervention-ticket lane)

Main resolved its own three-way fork in `372_merge_three_heads` while the media
lane was still hanging off `369_merge_tickets_media`, a sibling of those three
rather than an ancestor. So pulling main in leaves exactly two heads, and this
revision joins forward from both of them. Two heads is not a warning, it is a
broken deploy: `alembic upgrade head` refuses to guess, and `bootstrap_env`
aborts its stamp with "Multiple heads are present" before a single test runs.

An earlier attempt on this branch (`372_merge_media_main_heads`) merged the four
pre-372 heads directly. It never landed on main, and once main's own
`372_merge_three_heads` arrived the two merges were siblings covering the same
lanes, which is two heads again. It is deleted rather than kept, because nothing
outside this branch ever recorded it.

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

The lanes touch disjoint tables (media jobs, AI provider config and voice
notices on this side; onboarding requests, product spec verifications and brand
tags on team members on main's), so order between them genuinely does not matter.

The id is 25 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay within it
(see `tests/test_alembic_revision_ids.py`).

Revision ID: 373_merge_media_into_main
Revises: 372_merge_three_heads, 369_merge_tickets_media
Create Date: 2026-08-17
"""

# revision identifiers, used by Alembic.
revision = "373_merge_media_into_main"
down_revision = (
    "372_merge_three_heads",
    "369_merge_tickets_media",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
