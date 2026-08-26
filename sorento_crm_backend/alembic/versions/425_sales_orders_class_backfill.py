"""Nothing is unclassified: every NULL `sales_orders.demand_class` becomes retail

Revision ID: 425_sales_orders_class_backfill
Revises: 424_committed_v_project_oi_only
Create Date: 2026-08-26 20:30:00.000000

`PLAN-scm-purchasing-uat-journey.md` P4, question QP1, ruled by the captain: "nothing should
be unclassified". The plan page grew an Unclassified column for a channel nobody can act on,
and the honest fix is upstream - the orders get a class and the column goes.

The captain's ruling of 26 Aug 2026 is that all 148 open orders carrying no class are
RETAIL. Read off the dev copy, they belong to fifteen debtors, grouped by who sold them:

    agent LCL        117 orders   300-A036, 300-C108, 300-C110, 300-M172, 300-P121,
                                  300-P122, 300-S289, 303-K001, 303-M004
    no agent          16 orders   300-A031
    KATHERINE         10 orders   300-C083, 301-C001
    XUAN               3 orders   300-M168, 302-J005
    JAMYN CHANG        2 orders   300-M168

CLOSED orders are stamped too - 11,006 of them on the dev copy, 11,154 rows in total. A
closed order is not demand and no plan reads it, but it IS history: the demand-class split
on every trailing-window report, every trend and every classification study reads the same
column, and leaving eleven thousand NULLs behind would leave those answers reading
"unclassified" forever for orders the client has just told us are retail.

REVERSIBLE, and that is why there is a table. `scm.demand_class_backfill_425` records the id
of every row this migration actually stamps, so `downgrade()` puts back a NULL on exactly
those rows and touches nothing that was already classified - the alternative, "set every
retail order to NULL", would destroy classifications that predate this migration by months.

Idempotent in both directions: the insert takes only rows that are still NULL, the update
only rows the table names, and re-running either way is a no-op.

No application code is imported. The class vocabulary is written out as the literal
`'retail'` rather than read from `app.services.scm.demand_class.DEFAULT_DEMAND_CLASS` - a
migration describes a point in history, and the day that constant changes this migration
must still do what it did (`tests/scm/test_committed_v_migration_chain.py`).
"""
from alembic import op

revision = "425_sales_orders_class_backfill"
down_revision = "424_committed_v_project_oi_only"
branch_labels = None
depends_on = None


#: The class every unclassified order is stamped with, frozen as a literal - see above.
_RETAIL = "retail"

_MARKER = "scm.demand_class_backfill_425"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scm")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_MARKER} (
            sales_order_id uuid PRIMARY KEY,
            stamped_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    # Recorded BEFORE the update, and only for rows that are still NULL, so the table
    # names exactly what this migration changed and a second run adds nothing.
    op.execute(
        f"""
        INSERT INTO {_MARKER} (sales_order_id)
        SELECT id FROM sales_orders WHERE demand_class IS NULL
        ON CONFLICT (sales_order_id) DO NOTHING
        """
    )
    op.execute(
        f"UPDATE sales_orders SET demand_class = '{_RETAIL}' WHERE demand_class IS NULL"
    )


def downgrade() -> None:
    # Only the rows this migration stamped, and only while they still read retail: a row
    # somebody has since reclassified is theirs, not ours, and putting a NULL back on it
    # would delete a real decision.
    op.execute(
        f"""
        UPDATE sales_orders SET demand_class = NULL
        WHERE demand_class = '{_RETAIL}'
          AND id IN (SELECT sales_order_id FROM {_MARKER})
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {_MARKER}")
