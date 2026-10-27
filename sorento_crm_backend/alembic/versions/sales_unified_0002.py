"""SALES-UNIFIED round 3 (#1916): dated agent classes and the third class `other`.

Plan: documentation/plans/sales/PLAN-sales-unified-27oct.md 2.9 (owner rulings Q6 to Q8 (a)).

1. ``sales.agent_classes``: an agent's class (``retail`` | ``project`` | ``other``) from a month
   to a month. Seeded with one open row "from the beginning" per agent that has a class today
   (``sales_agents.demand_class``), so nothing re-derives differently on the day this lands.
2. The ``sales_agents`` and ``finance.billing_documents`` class CHECKs accept ``other``.
   (``scm.reorder_run`` keeps its two planning legs: ``other`` plans as retail.)

No sales order is rewritten here: the re-derivation is the owner's call after the dry run
(``scripts/sales_order_class_rederive.py``, Q10 (a)).

Revision ID: sales_unified_0002
Revises: sales_unified_0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "sales_unified_0002"
down_revision = "sales_unified_0001"
branch_labels = None
depends_on = None

_UUID = UUID(as_uuid=False)
_THREE = "demand_class IS NULL OR demand_class IN ('project', 'retail', 'other')"
_TWO = "demand_class IS NULL OR demand_class IN ('project', 'retail')"


def _recheck(table: str, name: str, predicate: str, schema=None) -> None:
    qualified = f"{schema}.{table}" if schema else table
    op.execute(f"ALTER TABLE {qualified} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {qualified} ADD CONSTRAINT {name} CHECK ({predicate})")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS sales")
    op.create_table(
        "agent_classes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "sales_agent_id", _UUID, sa.ForeignKey("sales_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("demand_class", sa.String(32), nullable=False),
        sa.Column("from_month", sa.Date(), nullable=True),
        sa.Column("to_month", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "from_month IS NULL OR to_month IS NULL OR to_month >= from_month",
            name="ck_sales_agent_classes_months",
        ),
        sa.CheckConstraint(
            "demand_class IN ('project', 'retail', 'other')", name="ck_sales_agent_classes_class"
        ),
        schema="sales",
        if_not_exists=True,
    )
    op.create_index(
        "ix_sales_agent_classes_sales_agent_id", "agent_classes", ["sales_agent_id"],
        schema="sales", if_not_exists=True,
    )
    op.create_index(
        "uq_sales_agent_classes_open", "agent_classes", ["sales_agent_id"], unique=True,
        schema="sales", postgresql_where=sa.text("to_month IS NULL"), if_not_exists=True,
    )
    op.execute(
        "INSERT INTO sales.agent_classes (id, sales_agent_id, demand_class, from_month, to_month) "
        "SELECT gen_random_uuid(), a.id, a.demand_class, NULL, NULL FROM sales_agents a "
        "WHERE a.demand_class IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM sales.agent_classes c WHERE c.sales_agent_id = a.id)"
    )
    _recheck("sales_agents", "ck_sales_agents_demand_class", _THREE)
    _recheck("billing_documents", "ck_finance_billing_documents_demand_class", _THREE, "finance")


def downgrade() -> None:
    # Back to two classes: an `other` reads as nobody said (NULL), the state it came from.
    op.execute("UPDATE sales_agents SET demand_class = NULL WHERE demand_class = 'other'")
    op.execute("UPDATE finance.billing_documents SET demand_class = NULL WHERE demand_class = 'other'")
    op.execute("UPDATE sales_orders SET demand_class = NULL WHERE demand_class = 'other'")
    _recheck("sales_agents", "ck_sales_agents_demand_class", _TWO)
    _recheck("billing_documents", "ck_finance_billing_documents_demand_class", _TWO, "finance")
    op.drop_table("agent_classes", schema="sales", if_exists=True)
