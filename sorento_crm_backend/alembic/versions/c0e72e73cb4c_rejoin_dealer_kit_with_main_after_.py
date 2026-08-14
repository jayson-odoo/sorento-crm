"""Rejoin the Dealer Kit chain with main after the status engine.

BOOKKEEPING ONLY. This revision creates, alters and drops nothing, and it must
stay that way: its whole job is to give the two heads a single descendant so
`alembic upgrade head` has one place to go.

Two heads existed because both lines grew from the same ancestor at the same
time. Main took `309_merge_status_engine` (the status engine, merged while the
Dealer Kit branch was open), and this branch took the 309 to 316 Dealer Kit
chain. Neither is wrong and neither can be renumbered now that both are
published; a merge revision is how Alembic expresses "these two happened, in
either order".

Left unmerged, deployment fails outright rather than degrading: Alembic refuses
to upgrade when it cannot tell which head is meant.

Revision ID: c0e72e73cb4c
Revises: 309_merge_status_engine, 316_dealer_kit_flyer_reading
Create Date: 2026-08-02
"""

# revision identifiers, used by Alembic.
revision = "c0e72e73cb4c"
down_revision = ("309_merge_status_engine", "316_dealer_kit_flyer_reading")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing. See the module docstring: this node carries no schema change."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this simply forks the history again."""
