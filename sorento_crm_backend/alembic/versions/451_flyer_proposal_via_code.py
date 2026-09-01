"""One card speaks for its code family (PLAN-flyer-family-proposals.md S1).

`product_spec_flyer_proposals.via_product_code` (varchar(100), nullable) records the
printed code whose card filled a SIBLING row's gaps - a product whose own code is
`<that code>-<suffix>` and was never itself printed on the flyer. NULL on a row proposed
from the product's own card, which is every row before this feature and the base's own
rows after it (AC-A.7).

`product_spec_flyer_batches.via_count` (integer, default 0) is how many of the batch's
`product_count` got there via a family card rather than their own printed code
(AC-A.9) - counted off the rows the same way `product_count` already is, never
incremented by hand.

Both `ADD COLUMN IF NOT EXISTS`, matching `449_flyer_reading_code_overrides`'s
reasoning: several worktrees share one local database and this may already have been
applied there by hand.

Chains onto `450_spec_rules_readable`, the head on `main` once #447 landed. This lane
branched before that and originally named itself 450; it was renamed on the merge so
`alembic heads` stays at one.

Revision ID: 451_flyer_proposal_via_code
Revises: 450_spec_rules_readable
"""
from alembic import op

revision = "451_flyer_proposal_via_code"
down_revision = "450_spec_rules_readable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE product_spec_flyer_proposals
        ADD COLUMN IF NOT EXISTS via_product_code varchar(100)
        """
    )
    op.execute(
        """
        ALTER TABLE product_spec_flyer_batches
        ADD COLUMN IF NOT EXISTS via_count integer NOT NULL DEFAULT 0
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE product_spec_flyer_batches
        DROP COLUMN IF EXISTS via_count
        """
    )
    op.execute(
        """
        ALTER TABLE product_spec_flyer_proposals
        DROP COLUMN IF EXISTS via_product_code
        """
    )
