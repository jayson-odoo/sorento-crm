"""Merge the three heads main was left with.

Three migrations landed from independent branches and none knew about the others:

  * ``359_flyer_read_background_job``  (down: 359_scm_plan_feedback_r2)
  * ``360_merge_um_gates_scm_r2``      (itself a merge revision)
  * ``362_promotion_type_perms``       (down: 361_promotion_types)

Alembic resolves heads from the FILESYSTEM, so all three files being on main is
enough to make every `alembic upgrade head` fail with "Multiple heads are
present". CI hits it in the Bootstrap-the-database step, which runs BEFORE any
test, so a branch cut from main goes red on the backend suite and the Dealer Kit
render at a step that has nothing to do with its own diff.

Empty on purpose: a merge revision only rejoins the graph. No DDL from any side
is repeated here, and each still runs in its own revision.

Revision ID: 363_merge_heads
Revises: 359_flyer_read_background_job, 360_merge_um_gates_scm_r2, 362_promotion_type_perms
"""
from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "363_merge_heads"
down_revision = (
    "359_flyer_read_background_job",
    "360_merge_um_gates_scm_r2",
    "362_promotion_type_perms",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
