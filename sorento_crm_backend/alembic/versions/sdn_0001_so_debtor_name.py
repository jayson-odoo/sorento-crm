"""`sales_orders.debtor_name`: the customer name an SO was issued under.

Owner decision, 30 Sep 2026 (CUSTOMER-CODE-IDENTITY, re-scoped): the ingested
`customer_name` of a sales order is stored on the order itself and is what every
SO-facing screen shows, with the customer master's name as the fallback for an
order that carries none. AutoCount lets a user edit the debtor name on the SO, so
it is per document; `orders` (delivery orders) already carries one.

Also re-creates `uq_customers_company_code_name_lower` if it is missing - the same
definition migration 305 gave it. A no-op on main; it puts a dev database that an
earlier, parked version of this lane had dropped it from back in step with main.

Revision ID: sdn_0001_so_debtor_name
Revises: merge_30sep_batch9
Create Date: 2026-09-30
"""
from __future__ import annotations

from alembic import op

revision = "sdn_0001_so_debtor_name"
down_revision = "merge_30sep_batch9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS debtor_name varchar(255)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_company_code_name_lower ON customers "
        "(company_id, lower(btrim(customer_code)), lower(btrim(customer_name)))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales_orders DROP COLUMN IF EXISTS debtor_name")
