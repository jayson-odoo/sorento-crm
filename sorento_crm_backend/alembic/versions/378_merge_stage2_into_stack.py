"""Rejoin Stage 2's product-plan chain with the integration branch's head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** Stage 2 branched off `373_merge_scm_stage0_1a`, grew its own
chain and joined it back to the Stage 0/1A head, while the integration branch had
meanwhile joined the projects lineage and Stage 1C above the same revision:

    377_merge_stage2_main          (Stage 2: joins 376_scm_channel_read_model and
                                    374_merge_scm_stage0_1a_main)
    376_merge_1c_supply_decisions  (integration: joins 375_merge_scm_1a_and_projects
                                    and 374_so_supply_decisions)

They are siblings, so merging Stage 2 in leaves two heads. Two heads is not a
warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

**Ordering between the two lanes is NOT left to this revision.** Stage 1C's
`374_so_supply_decisions` creates `projects.so_supply_decisions` and Stage 2's
`376_scm_channel_read_model` reads it and replaces the view body 374 installed, so
their order is load-bearing in both directions. That is pinned where it belongs, by
`depends_on = "374_so_supply_decisions"` on 376 itself, not by luck at this join.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision.

The id is 28 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 378_merge_stage2_into_stack
Revises: 376_merge_1c_supply_decisions, 377_merge_stage2_main
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "378_merge_stage2_into_stack"
down_revision = (
    "376_merge_1c_supply_decisions",
    "377_merge_stage2_main",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
