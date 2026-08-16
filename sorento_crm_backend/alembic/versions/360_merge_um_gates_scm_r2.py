"""Rejoin the user-management read gates with the SCM plan feedback round 2 chain.

BOOKKEEPING ONLY. This revision creates, alters and drops nothing, and it must
stay that way: its whole job is to give the two heads a single descendant so
`alembic upgrade head` (and `alembic stamp head`, which is what CI bootstrap
runs) has one place to go.

Two heads existed because both lines grew from `358_scm_po_spo_history_aliases`
at the same time: main took `359_scm_plan_feedback_r2` (cover scope, debtor
code) while this branch took `359_um_contacts_reference_perms` (the two new
read permissions). Neither is wrong and neither can be renumbered now that both
are published; a merge revision is how Alembic expresses "these two happened, in
either order".

Left unmerged, bootstrap fails outright rather than degrading: Alembic refuses
to stamp or upgrade when it cannot tell which head is meant.

Revision ID: 360_merge_um_gates_scm_r2
Revises: 359_scm_plan_feedback_r2, 359_um_contacts_reference_perms
Create Date: 2026-08-16
"""

# revision identifiers, used by Alembic.
revision = "360_merge_um_gates_scm_r2"
down_revision = ("359_scm_plan_feedback_r2", "359_um_contacts_reference_perms")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing. See the module docstring: this node carries no schema change."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this simply forks the history again."""
