"""Collapse the two heads that merging main into the Dealer Kit branch created (again).

No DDL. This exists solely so `alembic upgrade head` has ONE head to aim at.

A second merge of `origin/main` into this branch forked the revision graph a
second time. Both lineages added migrations after the previous merge point, so
neither is an ancestor of the other and the graph had two heads:

    7cc13b71908c                 (main's head at the time of the merge)
    320_dealer_kit_tile_template (the page-level default tile design, this branch)

Two heads is not a warning, it is a broken deploy: `alembic upgrade head` fails
with "Multiple head revisions are present" and the container never starts.

The id is 25 characters, and that is a constraint rather than a preference.
`scripts/bootstrap_env.py` builds the schema from the ORM models and then calls
`command.stamp(cfg, "head")`, which INSERTs the head revision id into an
`alembic_version` table Alembic has just created with `version_num varchar(32)`.
Migration `103b_widen_alembic_version_num` widens that column to 255, but it
never runs on the stamp path, so a head id longer than 32 characters aborts the
bootstrap with StringDataRightTruncation. Any future head must stay <= 32.
"""

revision = "321_merge_dealer_kit_main"
down_revision = ("7cc13b71908c", "320_dealer_kit_tile_template")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins two lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
