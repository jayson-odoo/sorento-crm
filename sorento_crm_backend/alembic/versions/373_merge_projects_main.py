"""Rejoin the projects schema move with the three lineages main landed after it.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE head
to aim at.

    projects schema move    ---- ac3c69a20ec0
    everything main landed  ---- 372_merge_three_heads

Main itself carried three heads for a while (onboarding intake, product spec verify
and brand member routing, each PR merged off a different base and none re-merging the
others). Main closed that itself in `372_merge_three_heads`, so this revision joins
main's join to ours rather than re-joining the same three: two parents, not four.
With more than one head `scripts/bootstrap_env.py` aborts its stamp with "Multiple
heads are present" and every CI job fails at the bootstrap step before a single test
runs.

The id stays at or under 32 characters because `bootstrap_env` stamps it into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 373_merge_projects_main
Revises: 372_merge_three_heads, ac3c69a20ec0
Create Date: 2026-08-17
"""

revision = "373_merge_projects_main"
down_revision = (
    "372_merge_three_heads",
    "ac3c69a20ec0",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
