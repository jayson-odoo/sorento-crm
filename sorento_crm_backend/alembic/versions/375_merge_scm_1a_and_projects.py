"""Rejoin the SCM stage 0 + 1A lineage with the one main landed for Project Sales.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** Both lineages solved the same four-way fork, independently,
while the other was still open:

    374_merge_proj_media_flyer     (main, via #155: joins 373_merge_projects_main,
                                    373_merge_media_into_main and
                                    373_merge_372_flyer_specs)
    374_merge_scm_stage0_1a_main   (this branch: joins those same three plus
                                    373_merge_scm_stage0_1a)

They are siblings, so merging main into this branch leaves two heads. Two heads is
not a warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

Neither of the two is renumbered or deleted. `374_merge_proj_media_flyer` is on
main and any production database will already be stamped with it;
`374_merge_scm_stage0_1a_main` is on the pushed branch and databases stamped with
it must still be able to upgrade. Join forward, never renumber a landed revision.

The two parents carry no DDL of their own and the lanes beneath them touch disjoint
tables, so order between them genuinely does not matter.

The id is 29 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 375_merge_scm_1a_and_projects
Revises: 374_merge_proj_media_flyer, 374_merge_scm_stage0_1a_main
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "375_merge_scm_1a_and_projects"
down_revision = (
    "374_merge_proj_media_flyer",
    "374_merge_scm_stage0_1a_main",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
