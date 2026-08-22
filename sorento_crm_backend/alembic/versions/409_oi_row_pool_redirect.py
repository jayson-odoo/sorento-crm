"""order_inquiry_rows.redirected_to_pool - the placed-PO redirect flag.

`PLAN-so-book-diff-replanning.md`, the captain's ruling on 21 Aug 2026: when a planning
change's fresh proposal draws on the shared pool to cover a line, the pool take stands
and any PLACED purchase order this line already holds is REDIRECTED to replenish the pool
instead of being relabelled onto Buy. This flag marks a redirected row so
`refresh_for_decision`'s placed-quantity netting and the worklist's "Taken from PO"
aggregate both stop counting it for the line it used to serve - it is still real placed
quantity, just not this line's anymore.

Revision ID: 409_oi_row_pool_redirect
Revises: 408_scm_plan_row_decision
Create Date: 2026-08-21
"""
import sqlalchemy as sa
from alembic import op

revision = "409_oi_row_pool_redirect"
down_revision = "408_scm_plan_row_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_inquiry_rows",
        sa.Column(
            "redirected_to_pool",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="projects",
    )


def downgrade() -> None:
    op.drop_column("order_inquiry_rows", "redirected_to_pool", schema="projects")
