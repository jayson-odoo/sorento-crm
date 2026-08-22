"""Rejoin the projects lineage with the two heads main was left holding.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE head
to aim at.

    projects schema move + main    ---- 373_merge_projects_main
    chatbot media endpoint         ---- 373_merge_media_into_main
    flyer spec proposals           ---- 373_merge_372_flyer_specs

Main landed the chatbot media endpoint and the flyer spec ingestion from different
bases and cut a merge revision for each against `372_merge_three_heads`, without
either re-merging the other, so main itself arrived here with two heads. This branch
adds its own third. Rather than duplicate main's two joins, this revision sits on top
of all three, exactly as `373_merge_projects_main` sat on top of main's earlier join.
With more than one head `scripts/bootstrap_env.py` aborts its stamp with "Multiple
heads are present" and every CI job fails at the bootstrap step before a single test
runs.

The id stays at or under 32 characters because `bootstrap_env` stamps it into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 374_merge_proj_media_flyer
Revises: 373_merge_projects_main, 373_merge_media_into_main, 373_merge_372_flyer_specs
Create Date: 2026-08-17
"""

revision = "374_merge_proj_media_flyer"
down_revision = (
    "373_merge_projects_main",
    "373_merge_media_into_main",
    "373_merge_372_flyer_specs",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
