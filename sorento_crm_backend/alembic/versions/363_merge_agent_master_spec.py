"""Join main's scm sales-agent lineage with the spec-authoring lineage.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** `362_merge_grn_fm_with_spec` joined this branch's spec-authoring
work to `357_merge_grn_spo_fm_heads`, which was main's head when that merge was
written. Main then landed the scm sales-agent master work, whose own merge revision
`46cf6ce8b6d0` also hangs off `357_merge_grn_spo_fm_heads`:

    357_merge_grn_spo_fm_heads
      |-- 361_spec_registry_grant_sweep --- 362_merge_grn_fm_with_spec  (this branch)
      `-- c62867691a75 ------------------- 46cf6ce8b6d0                 (main)

Neither is an ancestor of the other, so the merged result carries two heads and
`scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision" - which took out both `Backend test
suite (Postgres)` and `Dealer Kit PDF render (real browser)` before a single test ran.

The id stays under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 363_merge_agent_master_spec
Revises: 362_merge_grn_fm_with_spec, 46cf6ce8b6d0
Create Date: 2026-08-15
"""

revision = "363_merge_agent_master_spec"
down_revision = (
    "362_merge_grn_fm_with_spec",
    "46cf6ce8b6d0",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
