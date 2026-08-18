"""Rejoin Stage 1C's supply-decision table with the integration branch's head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** Stage 1C branched off `373_merge_scm_stage0_1a` and put its
own table revision straight on it, while the integration branch went on to join the
projects lineage above the same revision:

    374_so_supply_decisions        (Stage 1C: creates `projects.so_supply_decisions`,
                                    revises 373_merge_scm_stage0_1a)
    375_merge_scm_1a_and_projects  (integration: joins 374_merge_proj_media_flyer and
                                    374_merge_scm_stage0_1a_main, both of which sit
                                    above 373_merge_scm_stage0_1a too)

They are siblings, so merging Stage 1C in leaves two heads. Two heads is not a
warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

Neither parent is renumbered or deleted. `375_merge_scm_1a_and_projects` is already
landed on the integration branch and any database stamped with it must still be able
to upgrade; `374_so_supply_decisions` carries the real DDL Stage 1C depends on. Join
forward, never renumber a landed revision.

`374_so_supply_decisions` is the only one of the two with DDL, and it touches a table
no other lane knows about, so order between the two branches genuinely does not
matter.

The id is 29 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 376_merge_1c_supply_decisions
Revises: 375_merge_scm_1a_and_projects, 374_so_supply_decisions
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "376_merge_1c_supply_decisions"
down_revision = (
    "375_merge_scm_1a_and_projects",
    "374_so_supply_decisions",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
