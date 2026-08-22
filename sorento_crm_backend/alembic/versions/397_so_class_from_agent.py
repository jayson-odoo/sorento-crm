"""sales_orders.demand_class - backfill from the agent for pre-existing NULLs.

`outstanding_import_service._classify_demand` reads the sales agent's `demand_class` LAST,
after order type, the file's own type and the customer's market segment - so an order
imported BEFORE its agent was classified resolved through that ladder to NULL and was
written that way, and nothing re-imports it. `sales_agent_service.set_demand_class` /
`.annotate` now backfill an agent's NULL-class orders the moment the class is set, but that
only covers classifications made after this change - a company whose agents were already
classified needs the same fill applied once, here, for whatever an earlier answer left NULL.

Idempotent: scoped to `sales_orders.demand_class IS NULL`, so a row this (or the app-level
backfill) has already filled never matches a re-run. This exact statement was already run by
hand against the shared dev database on 2026-08-19 (1,722 rows) before this migration existed,
so `upgrade()` here is expected to match 0 rows there - that IS the idempotency check.

Revision ID: 397_so_class_from_agent
Revises: 396_oi_single_location
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "397_so_class_from_agent"
down_revision = "396_oi_single_location"
branch_labels = None
depends_on = None


def apply(bind) -> int:
    """Fill every `sales_orders.demand_class` still NULL from its agent's class.

    Returns the number of rows changed.
    """
    return (
        bind.execute(
            sa.text(
                """
                UPDATE sales_orders AS so
                   SET demand_class = sa.demand_class
                  FROM sales_agents AS sa
                 WHERE sa.id = so.sales_agent_id
                   AND so.demand_class IS NULL
                   AND sa.demand_class IS NOT NULL
                """
            )
        ).rowcount
        or 0
    )


def revert(bind) -> int:
    """No-op. Which rows this filled and which arrived NULL for another reason (no agent,
    order type unresolved, ...) is not recorded anywhere once written, so there is nothing
    to tell apart on the way back down. Rows changed: always 0.
    """
    return 0


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
