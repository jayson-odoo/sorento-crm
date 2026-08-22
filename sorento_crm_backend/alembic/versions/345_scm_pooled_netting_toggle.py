"""S10: pooled netting becomes a switch, and this phase turns it off.

Pooled netting exists because netting strictly per bin recommended buying 67 units of an
item the site already held 4,397 of, sitting in a sibling bin (ADR-0011). That reasoning
assumes the engine decides from raw demand.

It does not. CS filters demand into the order inquiry, and moving stock between bins is
their decision, taken BEFORE purchasing sees the requirement. This phase has also parked
transfer proposals. So pooled netting has the engine quietly assuming a transfer it will
never propose: it buys less on the expectation that somebody moves stock, and nobody has
agreed to.

Both rules stay in the code. `pool_netting` selects between them per policy scope, so a
tenant whose planners really do move stock freely turns it back on with a row rather than a
deploy - same shape as `policy_type` selecting the planning basis.

Default FALSE: assume nothing, buy what the bin is short. The alternative silently
under-buys, and an under-buy is invisible until the stock runs out.

Revision ID: 345_scm_pooled_netting_toggle
Revises: 344_scm_reorder_level_basis
"""
import sqlalchemy as sa
from alembic import op

revision = "345_scm_pooled_netting_toggle"
down_revision = "344_scm_reorder_level_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_policy",
        sa.Column("pool_netting", sa.Boolean, nullable=True,
                  server_default=sa.text("false")),
        schema="scm",
    )
    # Existing rows predate the switch and were all planned WITH pooling. Setting them
    # false is the deliberate change, not a migration artefact: leaving them NULL would
    # make the new default depend on which code path read the row first.
    op.execute("UPDATE scm.reorder_policy SET pool_netting = false WHERE pool_netting IS NULL")


def downgrade() -> None:
    op.drop_column("reorder_policy", "pool_netting", schema="scm")
