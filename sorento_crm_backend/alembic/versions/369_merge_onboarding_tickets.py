"""Rejoin this slice with the ticket work main landed while it was in review.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

    onboarding intake slice ---- 368_merge_onboarding_flyer
    conversation tickets    ---- 368_merge_tickets_main

Neither is an ancestor of the other, so `scripts/bootstrap_env.py` aborts its stamp
with "Multiple heads are present" and every CI job fails at the bootstrap step
before a single test runs.

The id stays at or under 32 characters because `bootstrap_env` stamps it into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 369_merge_onboarding_tickets
Revises: 368_merge_onboarding_flyer, 368_merge_tickets_main
Create Date: 2026-08-17
"""

revision = "369_merge_onboarding_tickets"
down_revision = (
    "368_merge_onboarding_flyer",
    "368_merge_tickets_main",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
