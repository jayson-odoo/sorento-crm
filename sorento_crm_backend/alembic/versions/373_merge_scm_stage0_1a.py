"""Rejoin the SCM stage 0 + 1A lane with main after both cut a 372.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** Branch `fm/scm-stage0-1a-land` was open while main advanced,
and the two lineages each landed their own revision numbered 372:

    main                     ---- 372_merge_three_heads
    fm/scm-stage0-1a-land    ---- 372_project_so_line_core_link

Neither is an ancestor of the other, so merging main into the branch left the
graph with two heads. That is not a warning, it is a broken deploy: CI's
"Bootstrap the database" step runs `scripts/bootstrap_env.py`, whose
`alembic stamp head` aborts with "Multiple heads are present; please specify a
single target revision" before a single test runs.

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

The id is 23 characters. `bootstrap_env` stamps the head into an `alembic_version`
table alembic creates as `version_num varchar(32)` (see 322's docstring and
`tests/test_alembic_revision_ids.py`), so any head id must stay <= 32.

Revision ID: 373_merge_scm_stage0_1a
Revises: 372_merge_three_heads, 372_project_so_line_core_link
Create Date: 2026-08-17
"""

from __future__ import annotations

revision = "373_merge_scm_stage0_1a"
down_revision = (
    "372_merge_three_heads",
    "372_project_so_line_core_link",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
