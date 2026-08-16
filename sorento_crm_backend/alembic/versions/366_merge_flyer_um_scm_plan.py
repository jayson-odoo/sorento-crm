"""Join the flyer/promo/um lineage with the scm plan-feedback one.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

The same shape as 362 to 365. Main carried both `363_merge_flyer_promo_um` and
`365_merge_scm_plan_feedback` at once:

    ...
      |-- 363_merge_flyer_promo_um
      `-- 365_merge_scm_plan_feedback

Neither is an ancestor of the other, so `alembic heads` printed two and
`scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision" before a single test runs. The fix
is unchanged - join forward, never renumber a landed revision, since rewriting one
strands every database that already recorded the old id.

The id stays under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 366_merge_flyer_um_scm_plan
Revises: 363_merge_flyer_promo_um, 365_merge_scm_plan_feedback
Create Date: 2026-08-16
"""

from __future__ import annotations

revision = "366_merge_flyer_um_scm_plan"
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
