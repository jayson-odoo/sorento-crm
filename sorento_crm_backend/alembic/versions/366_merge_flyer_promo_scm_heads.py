"""Rejoin the two heads main carried into the PR-4 flyer-promote slice.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

**The same shape as 362 to 365.** Main at `eb2cf0ce` already carried two heads
before this branch added anything:

    ...
      |-- 363_merge_flyer_promo_um     (the three-way rejoin of the PR #184 /
      |                                 user-management / promotion-types fork)
      `-- 365_merge_scm_plan_feedback  (the scm plan-feedback lineage)

Neither is an ancestor of the other, so `alembic heads` reports both and
`tests/test_alembic_revision_ids.py::test_migration_graph_has_a_single_head` is
red on main. PR 4 has to chain its promote revision onto a single head, so it
joins them here first rather than picking one and stranding the other.

Nothing is renumbered. Rewriting a landed revision strands every database that
already recorded the old id, so the graph is only ever joined forward.

The id stays under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 366_merge_flyer_promo_scm_heads
Revises: 363_merge_flyer_promo_um, 365_merge_scm_plan_feedback
Create Date: 2026-08-16
"""

from __future__ import annotations

revision = "366_merge_flyer_promo_scm_heads"
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
