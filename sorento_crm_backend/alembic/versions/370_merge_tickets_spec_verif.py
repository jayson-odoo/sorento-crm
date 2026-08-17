"""Rejoin the intervention-ticket lane with the spec-verification ledger.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** PR #137 (conversation intervention tickets) and PR #195 (product
spec verification) were open concurrently, and both branched off the same tip of main
(`367_promote_flyer_provenance`):

    #137 (intervention tickets) ---- 368_merge_tickets_main
    #195 (spec verification)   ---- 369_product_spec_verifications

#137 landed on main first, so pulling main into this branch put both revisions in one
graph with neither an ancestor of the other. Two heads is not a warning, it is a broken
deploy: `scripts/bootstrap_env.py` aborts its `alembic stamp head` with "Multiple heads
are present; please specify a single target revision" before a single test runs.

Join forward, never renumber a landed revision - rewriting one strands every database
that already recorded the old id.

The id is 28 characters. `bootstrap_env` stamps the head into an `alembic_version` table
alembic creates as `version_num varchar(32)` (see 322's docstring and
`tests/test_alembic_revision_ids.py`), so any head id must stay <= 32.

Revision ID: 370_merge_tickets_spec_verif
Revises: 368_merge_tickets_main, 369_product_spec_verifications
Create Date: 2026-08-17
"""

from __future__ import annotations

revision = "370_merge_tickets_spec_verif"
down_revision = (
    "368_merge_tickets_main",
    "369_product_spec_verifications",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
