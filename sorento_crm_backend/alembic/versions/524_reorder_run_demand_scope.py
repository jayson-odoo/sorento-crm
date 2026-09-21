"""`scm.reorder_run` gains a demand scope (PLAN-reorder-plan-demand-class-orders.md).

Start Plan can now narrow a run to one leg of demand - `demand_class` `project` | `retail`,
NULL (the default) nets both, unchanged from before this migration - and, for a project run,
to an explicit set of sales orders (`so_numbers`, JSONB list; NULL = none asked for, an empty
list = Project chosen with no SO narrowed - every project order in range).

`demand_class` reuses the SAME closed vocabulary `demand_class.py` already governs for
`sales_orders`/`sales_agents` (`check_constraint_sql`), so the constraint here cannot drift
from the model's own `CheckConstraint`. Both columns are additive and nullable, so the
downgrade is a plain drop and no data is rewritten either way.

Revision ID: 524_reorder_run_demand_scope
Revises: ptag_0013_r10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.services.scm.demand_class import check_constraint_sql

revision = "524_reorder_run_demand_scope"
down_revision = "523_oi_monthly_no_raises"
branch_labels = None
depends_on = None

_CHECK_NAME = "ck_scm_reorder_run_demand_class"


def upgrade() -> None:
    op.add_column(
        "reorder_run",
        sa.Column("demand_class", sa.String(length=16), nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_run",
        sa.Column("so_numbers", JSONB(), nullable=True),
        schema="scm",
    )
    op.create_check_constraint(
        _CHECK_NAME, "reorder_run", check_constraint_sql("demand_class"), schema="scm",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "reorder_run", schema="scm", type_="check")
    op.drop_column("reorder_run", "so_numbers", schema="scm")
    op.drop_column("reorder_run", "demand_class", schema="scm")
