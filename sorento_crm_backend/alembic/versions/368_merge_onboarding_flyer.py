"""Rejoin the two heads main grew while the onboarding slice was in review.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

The onboarding slice branched before #194 landed, so after merging main the graph
carries two heads that are not ancestors of each other:

    onboarding intake slice ---- 361_onboarding_role_label
    #194 spec extraction    ---- 367_promote_flyer_provenance

`scripts/bootstrap_env.py` stamps the head and aborts on "Multiple heads are
present", which fails CI before a single test runs.

The id stays at or under 32 characters because `bootstrap_env` stamps it into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 368_merge_onboarding_flyer
Revises: 361_onboarding_role_label, 367_promote_flyer_provenance
Create Date: 2026-08-17
"""

revision = "368_merge_onboarding_flyer"
down_revision = (
    "361_onboarding_role_label",
    "367_promote_flyer_provenance",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
