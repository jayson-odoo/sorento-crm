"""Rejoin the two heads main grew when PRs #189 and #159 landed independently.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** Two PRs merged to main separately, each green on its own because
each saw a single head at the time it ran:

    #189 (backend alembic-head merge) ---- 363_merge_flyer_promo_um
    #159 (product Specifications tab) ---- 365_merge_scm_plan_feedback

Neither is an ancestor of the other, so main after both carries two heads and
`scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision". That is what killed CI run
https://github.com/jayson-odoo/sorento-crm/actions/runs/31951887584 at the bootstrap
step, before a single test ran.

The id stays at or under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 366_merge_363_365
Revises: 363_merge_flyer_promo_um, 365_merge_scm_plan_feedback
Create Date: 2026-08-16
"""

revision = "366_merge_363_365"
down_revision = (
    "363_merge_flyer_promo_um",
    "365_merge_scm_plan_feedback",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
