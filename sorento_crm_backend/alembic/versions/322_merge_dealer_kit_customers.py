"""Join main's customer-importer chain with the Dealer Kit chain.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has
ONE head to aim at.

`origin/main` landed the customer importer (`353_customer_import_aliases` ->
`354_customer_import_permission` -> `355_customers_length_drift`, joined to the
portal-revisions chain by `885010d94677`) after this branch had already merged
main once. Neither lineage is an ancestor of the other, so the graph forked a
third time:

    885010d94677              (main's head: the customer importer chain)
    321_merge_dealer_kit_main (this branch's head: the Dealer Kit chain)

Two heads is not a warning, it is a broken deploy: CI's `bootstrap_env` job and
`alembic upgrade head` both fail with "Multiple heads are present".

The id is 30 characters, and that is a constraint rather than a preference.
`scripts/bootstrap_env.py` builds the schema from the ORM models and then calls
`command.stamp(cfg, "head")`, which INSERTs the head revision id into an
`alembic_version` table Alembic has just created with `version_num varchar(32)`.
Migration `103b_widen_alembic_version_num` widens that column to 255, but it
never runs on the stamp path, so a head id longer than 32 characters aborts the
bootstrap with StringDataRightTruncation. Any future head must stay <= 32.
"""

revision = "322_merge_dealer_kit_customers"
down_revision = ("885010d94677", "321_merge_dealer_kit_main")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins two lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the two lineages genuinely are independent below this point."""
