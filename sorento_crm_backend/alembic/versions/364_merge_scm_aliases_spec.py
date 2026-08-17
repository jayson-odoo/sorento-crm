"""Join main's scm PO/SPO history aliases with the spec-authoring lineage.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened, again.** `363_merge_agent_master_spec` joined this branch to
`46cf6ce8b6d0`, main's head when that merge was written. Main then landed
`358_scm_po_spo_history_aliases`, which also hangs off `46cf6ce8b6d0`:

    46cf6ce8b6d0
      |-- 363_merge_agent_master_spec      (this branch)
      `-- 358_scm_po_spo_history_aliases   (main)

Neither is an ancestor of the other, so the merged result carries two heads and
`scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision" before a single test runs.

Fixed forward, as 362 and 363 were: the revisions on either side have already been
applied to databases, and rewriting one of them would strand every database that
recorded the old id.

The id stays under 32 characters because `bootstrap_env` stamps the head into an
`alembic_version` table alembic creates as `version_num varchar(32)` (see 322's
docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 364_merge_scm_aliases_spec
Revises: 363_merge_agent_master_spec, 358_scm_po_spo_history_aliases
Create Date: 2026-08-16
"""

revision = "364_merge_scm_aliases_spec"
down_revision = (
    "363_merge_agent_master_spec",
    "358_scm_po_spo_history_aliases",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
