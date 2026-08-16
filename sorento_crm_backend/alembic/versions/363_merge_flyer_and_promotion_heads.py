"""Merge the two heads main was left with.

Two migrations landed on independent branches and neither knew about the other:

  * ``359_flyer_read_background_job``  (down: 359_scm_plan_feedback_r2)
  * ``362_promotion_type_perms``       (down: 361_promotion_types)

Alembic reads heads off the FILESYSTEM, so as soon as both files were on main
every `alembic upgrade head` died with "Multiple heads are present; please
specify a single target revision" - including CI's Bootstrap-the-database step,
which runs before any test. That turns every branch cut from main red at a step
that has nothing to do with its own diff.

Empty on purpose: a merge revision only rejoins the graph. Neither side's DDL is
repeated here, and both still run, in their own revisions.

Revision ID: 363_merge_heads
Revises: 359_flyer_read_background_job, 362_promotion_type_perms
"""
from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "363_merge_heads"
down_revision = ("359_flyer_read_background_job", "362_promotion_type_perms")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
