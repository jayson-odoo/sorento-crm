"""Rejoin the projects schema move with the three lineages main landed after it.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE head
to aim at.

    projects schema move    ---- ac3c69a20ec0
    onboarding intake       ---- 369_merge_onboarding_tickets
    product spec verify     ---- 370_merge_tickets_spec_verif
    brand member routing    ---- 371_brand_member_routing

Main itself carried the last three as separate heads (each PR merged off a different
base and none re-merged the others), so this revision joins four rather than the
usual two. None is an ancestor of another, and with more than one head
`scripts/bootstrap_env.py` aborts its stamp with "Multiple heads are present" and
every CI job fails at the bootstrap step before a single test runs.

The id stays at or under 32 characters because `bootstrap_env` stamps it into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 372_merge_projects_main
Revises: 369_merge_onboarding_tickets, 370_merge_tickets_spec_verif, 371_brand_member_routing, ac3c69a20ec0
Create Date: 2026-08-17
"""

revision = "372_merge_projects_main"
down_revision = (
    "369_merge_onboarding_tickets",
    "370_merge_tickets_spec_verif",
    "371_brand_member_routing",
    "ac3c69a20ec0",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
