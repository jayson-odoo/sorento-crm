"""Join main's scm plan-feedback revision with the spec-authoring lineage.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**The same shape as 362, 363 and 364.** Main landed `359_scm_plan_feedback_r2` while
this branch was validating, and this branch already carried `364_merge_scm_aliases_spec`:

    ...
      |-- 364_merge_scm_aliases_spec   (this branch)
      `-- 359_scm_plan_feedback_r2     (main)

Neither is an ancestor of the other, so the merged result carries two heads and
`scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision" before a single test runs.

This one arrived by a different route than its predecessors: the branch takes main
through a MERGE rather than a rebase, because the repository forbids rewriting a
published branch, so main's newest revision joins the graph when the merge lands
rather than when a rebase replays it. The fix is unchanged - join forward, never
renumber a landed revision, since rewriting one strands every database that already
recorded the old id.

The id stays under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 365_merge_scm_plan_feedback
Revises: 364_merge_scm_aliases_spec, 359_scm_plan_feedback_r2
Create Date: 2026-08-16
"""

from __future__ import annotations

revision = "365_merge_scm_plan_feedback"
down_revision = (
    "364_merge_scm_aliases_spec",
    "359_scm_plan_feedback_r2",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
