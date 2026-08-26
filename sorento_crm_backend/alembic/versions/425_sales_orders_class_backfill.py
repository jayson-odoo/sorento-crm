"""Nothing is unclassified: every NULL demand class becomes retail, order and customer both

Revision ID: 425_sales_orders_class_backfill
Revises: 424_committed_v_project_oi_only
Create Date: 2026-08-26 20:30:00.000000

`PLAN-scm-purchasing-uat-journey.md` P4, question QP1, ruled by the captain: "nothing should
be unclassified". The plan page grew an Unclassified column for a channel nobody can act on,
and the honest fix is upstream. Since QP1 an SO upload naming an order nothing can classify
is refused outright, so "upstream" has to mean the master data as well as the orders.

The captain's ruling of 26 Aug 2026 is that all 148 open orders carrying no class are
RETAIL. Read off the dev copy, they belong to fifteen debtors, grouped by who sold them:

    agent LCL        117 orders   300-A036, 300-C108, 300-C110, 300-M172, 300-P121,
                                  300-P122, 300-S289, 303-K001, 303-M004
    no agent          16 orders   300-A031
    KATHERINE         10 orders   300-C083, 301-C001
    XUAN               3 orders   300-M168, 302-J005
    JAMYN CHANG        2 orders   300-M168

TWO backfills, because stamping only the orders leaves a trap one upload away.

1. THE ORDERS. Every NULL `sales_orders.demand_class` becomes retail - 11,154 rows on the
   dev copy, 148 open and 11,006 closed. A closed order is not demand and no plan reads
   one, but it IS history: the demand-class split on every trailing-window report, trend
   and classification study reads the same column, and leaving eleven thousand NULLs would
   answer "unclassified" for those orders for ever.

2. THE CUSTOMERS. The real AutoCount export (`Dealer Sales Order Outstanding 2020 -
   2026.xlsx`) carries Doc No, Doc Date, Delivery Date, Debtor Code, Debtor Name, Agent,
   Ref Doc No, Ref, Remark, Item Code, Location, Qty - and NO order type column. So an
   order in that book classifies through one route only: the debtor's market segment
   (`outstanding_import_service._segment_of` -> `demand_class.class_of`). Stamping the
   ORDERS alone would leave every one of those debtors unclassified, and the first upload
   naming a NEW document for one of them would be refused with nothing an operator could
   do about it but edit master data by hand, mid-import, on a Friday.

   So every customer a NULL-class order names gets `market_segment_code = 'retail'` - the
   `market_segments` row whose code `class_of` maps to the retail class. 511 customers are
   named on the dev copy; 503 of them carry no segment and are stamped, and the 8 that
   already carry one are LEFT ALONE. That exception is the point: 300-F004's segment reads
   `project`, and overwriting it would silently demote a project buyer to retail on the
   strength of an order somebody forgot to classify.

   Company-safe on both arms. An order's `customer_id` is already the right row; the
   debtor-code arm is matched under the order's OWN company, because `customers.
   customer_code` is unique per company and not globally - fourteen debtor codes on this
   book resolve to 123 customer rows across nine companies, and classifying another
   company's buyer from this company's order is exactly the mis-prioritisation the column
   exists to prevent.

REVERSIBLE, and that is why there are two tables. `scm.demand_class_backfill_425` records
every sales order this migration stamps and `scm.market_segment_backfill_425` every
customer, so `downgrade()` puts a NULL back on exactly those rows and touches nothing that
was already classified - the alternative, "set every retail row to NULL", would destroy
classifications that predate this migration by months. The customers are recorded BEFORE
the orders are stamped, because after the stamp there is no NULL-class order left to find
them from.

Idempotent in both directions: each insert takes only rows that are still NULL, each update
only rows its table names, and re-running either way is a no-op.

No application code is imported. The class vocabulary and the segment code are written out
as literals rather than read from `app.services.scm.demand_class` - a migration describes a
point in history, and the day those constants change this migration must still do what it
did (`tests/scm/test_committed_v_migration_chain.py`).
"""
from alembic import op

revision = "425_sales_orders_class_backfill"
down_revision = "424_committed_v_project_oi_only"
branch_labels = None
depends_on = None


#: The class every unclassified order is stamped with, frozen as a literal - see above.
_RETAIL = "retail"

#: The `market_segments.code` a customer is stamped with. `demand_class.class_of` maps it to
#: `_RETAIL` because it contains none of the project words, which is the whole contract
#: between this migration and the importer.
_RETAIL_SEGMENT = "retail"

_ORDERS = "scm.demand_class_backfill_425"
_CUSTOMERS = "scm.market_segment_backfill_425"

#: The customers a NULL-class order names. Both arms of the join, company-safe: the order's
#: own linked customer, and - for a book that states a debtor code the order was never
#: linked from - the customer holding that code UNDER THE ORDER'S OWN COMPANY.
_NAMED_CUSTOMERS = """
    SELECT DISTINCT cu.id
    FROM customers cu
    JOIN sales_orders so
      ON so.customer_id = cu.id
      OR (trim(COALESCE(so.debtor_code, '')) <> ''
          AND upper(cu.customer_code) = upper(trim(so.debtor_code))
          AND cu.company_id IS NOT DISTINCT FROM so.company_id)
    WHERE so.demand_class IS NULL
      AND (cu.market_segment_code IS NULL OR trim(cu.market_segment_code) = '')
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scm")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_ORDERS} (
            sales_order_id uuid PRIMARY KEY,
            stamped_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_CUSTOMERS} (
            customer_id uuid PRIMARY KEY,
            stamped_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    # The segment the customers below point at. Seeded here rather than assumed: the FK is
    # `customers.market_segment_code -> market_segments.code`, and a database built by
    # `create_all` (CI) carries no seed rows at all, so the update would fail on the
    # constraint rather than on anything to do with this migration.
    op.execute(
        f"""
        INSERT INTO market_segments (id, code, name, is_active)
        VALUES (gen_random_uuid(), '{_RETAIL_SEGMENT}', 'Retail', true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # CUSTOMERS FIRST, and only those with no segment: after the orders are stamped there
    # is no NULL-class order left to find them from.
    op.execute(
        f"""
        INSERT INTO {_CUSTOMERS} (customer_id)
        {_NAMED_CUSTOMERS}
        ON CONFLICT (customer_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE customers SET market_segment_code = '{_RETAIL_SEGMENT}'
        WHERE id IN (SELECT customer_id FROM {_CUSTOMERS})
          AND (market_segment_code IS NULL OR trim(market_segment_code) = '')
        """
    )

    # Recorded BEFORE the update, and only for rows that are still NULL, so the table names
    # exactly what this migration changed and a second run adds nothing.
    op.execute(
        f"""
        INSERT INTO {_ORDERS} (sales_order_id)
        SELECT id FROM sales_orders WHERE demand_class IS NULL
        ON CONFLICT (sales_order_id) DO NOTHING
        """
    )
    op.execute(
        f"UPDATE sales_orders SET demand_class = '{_RETAIL}' WHERE demand_class IS NULL"
    )


def downgrade() -> None:
    # Only the rows this migration stamped, and only while they still read what it wrote: a
    # row somebody has since reclassified is theirs, not ours, and putting a NULL back on it
    # would delete a real decision.
    op.execute(
        f"""
        UPDATE sales_orders SET demand_class = NULL
        WHERE demand_class = '{_RETAIL}'
          AND id IN (SELECT sales_order_id FROM {_ORDERS})
        """
    )
    op.execute(
        f"""
        UPDATE customers SET market_segment_code = NULL
        WHERE market_segment_code = '{_RETAIL_SEGMENT}'
          AND id IN (SELECT customer_id FROM {_CUSTOMERS})
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {_ORDERS}")
    op.execute(f"DROP TABLE IF EXISTS {_CUSTOMERS}")
    # The `market_segments` row is NOT removed: it may have predated this migration, and
    # other customers may point at it.
