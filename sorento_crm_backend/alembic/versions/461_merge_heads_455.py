"""Merge the spec-registry value-labels head with the reorder-replan chain head.

PR #520 merged 455_spec_registry_value_labels (down_revision
454_order_inquiry_born_ack) alongside the already-merged reorder-replan chain
(454 -> 455_saved_views_and_perms -> 456 -> 457_reorder_replan), leaving two
heads on origin/main and failing "Bootstrap the database" in every CI run and
the main deploy. Empty merge revision, exactly like 448's.
458 to 460 are claimed by open PRs, hence 461.

Revision ID: 461_merge_heads_455
Revises: 455_spec_registry_value_labels, 457_reorder_replan
"""

revision = "461_merge_heads_455"
down_revision = ("455_spec_registry_value_labels", "457_reorder_replan")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
