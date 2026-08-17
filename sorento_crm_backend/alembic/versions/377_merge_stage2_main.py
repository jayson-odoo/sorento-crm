"""Join the Stage 2 lane with the base branch's four-head merge.

No DDL. Merging origin/fm/scm-stage0-1a-land into the Stage 2 branch left two
heads: `376_scm_channel_read_model` (this lane: 374_uom_decimal_places ->
375_plan_grain_run_stamp -> 376, all cut from `373_merge_scm_stage0_1a`) and
`374_merge_scm_stage0_1a_main` (the base's join of the four 373 siblings after
it pulled main). Both descend from `373_merge_scm_stage0_1a`; the lanes touch
disjoint tables, so order between them does not matter. Join forward, never
renumber a landed revision.
"""

from alembic import op  # noqa: F401

revision = "377_merge_stage2_main"
down_revision = ("376_scm_channel_read_model", "374_merge_scm_stage0_1a_main")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
