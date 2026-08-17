"""Join the four 373 heads (main's two, PR #155's and this branch's) into one.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE target.

**Why there are four.** Main carried two 373 merge heads of its own. Both were
cut off `372_merge_three_heads` and neither re-merged the other:

    373_merge_372_flyer_specs   (main: 372_merge_three_heads + the flyer spec
                                 proposals lane)
    373_merge_media_into_main   (main: 372_merge_three_heads + the chatbot media
                                 / AI-config lane)

On top of that, PR #155 carries `373_merge_projects_main` (the projects schema
move rejoined to main) and this branch carries `373_merge_scm_stage0_1a` (the
SCM stage 0 + 1A lane rejoined to main). All four are siblings, so pulling main
into this branch leaves four heads. Four heads is not a warning, it is a broken
deploy: `alembic upgrade head` refuses to guess and `bootstrap_env` aborts its
stamp with "Multiple heads are present" before a single test runs. This revision
joins forward from all four.

**Why `373_merge_scm_stage0_1a` is kept rather than rewritten.** It is already
on the pushed branch, and two follow-on branches (PRs #207 and #208) sit on it.
Any database already stamped with that id must still be able to `alembic upgrade
head`, and renumbering or deleting a landed revision strands it. Join forward,
never renumber a landed revision.

The lanes touch disjoint tables, so order between them genuinely does not matter.

The id is 28 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under
32 (see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 374_merge_scm_stage0_1a_main
Revises: 373_merge_372_flyer_specs, 373_merge_media_into_main,
         373_merge_projects_main, 373_merge_scm_stage0_1a
Create Date: 2026-08-17
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "374_merge_scm_stage0_1a_main"
down_revision = (
    "373_merge_372_flyer_specs",
    "373_merge_media_into_main",
    "373_merge_projects_main",
    "373_merge_scm_stage0_1a",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
