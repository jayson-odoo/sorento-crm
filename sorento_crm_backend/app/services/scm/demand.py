"""What counts as demand, in one place.

Two books describe the same sales-order line and each owns its own columns:

    qty_ordered, qty_delivered      the sales-order book, what the customer asked for and
                                    what has shipped
    qty_required, purchasing_status the Order Inquiry sheet, what CS decided to cover and
                                    where that stands in purchasing

So the quantity to plan for is the one CS stated, falling back to what is still owed when
nobody has stated one, and always net of what has already shipped:

    GREATEST(COALESCE(qty_required, qty_ordered) - qty_delivered, 0)

`qty_required` is NULL, not zero, when unreviewed. A NULL that fell through to zero would
delete demand nobody has got round to looking at, which is the opposite of what "not
reviewed" means.

This module exists so the netting engine and `scm.committed_v` cannot drift. They are two
implementations of one rule - one in Python over the ORM, one in SQL inside a view - and a
disagreement between them shows up as a dashboard that contradicts a plan run for reasons
nobody can see. The SQL is kept here beside the expression so the next person changing one
finds the other.
"""
from __future__ import annotations

from sqlalchemy import func

from app.models.order import SalesOrder, SalesOrderLine

#: CS has ruled this line out of purchasing. It stays on the sales order (the customer is
#: still owed it) and stops being something to buy.
COVERED = "covered"

#: Nobody has looked at this line yet. It COUNTS: a plan that quietly omitted unreviewed
#: demand would be optimistic in exactly the situation where CS is behind.
NOT_REVIEWED = "not_reviewed"

#: The origin stamp the Order Inquiry feed writes on orders it creates. Its OWN column,
#: never `source_system`: when CS's outstanding extract adopts an inquiry-created order it
#: overwrites `source_system` to take ownership, and if origin were read off that column the
#: act of adoption would silently delete the order's demand from the next run. Ownership
#: moves; origin does not.
ORDER_INQUIRY_ORIGIN = "scm_order_inquiry"

#: The demand class CS filters through the Order Inquiry.
PROJECT_CLASS = "project"

#: The ORDER-level half of the demand rule (S13b, user decision 2026-08-10):
#:
#:   "order inquiry is only for project side. So for dealer side is exactly based on the
#:    sales order."
#:
#: A project-class order is demand only when the Order Inquiry created it - CS already
#: decided what purchasing should see, and a project SO the inquiry never named is CS
#: saying "not yet". Every other class (retail, and NULL, which the importer already
#: reports as unclassified) is demand straight from the book. What this predicate sets
#: aside is counted by `demand_source_service.set_aside_project_demand`, never silently
#: dropped.
PLAN_DEMAND_ORDER_SQL = (
    "(so.demand_class IS DISTINCT FROM 'project' "
    "OR so.demand_origin = 'scm_order_inquiry')"
)


def is_plan_demand_order():
    """`PLAN_DEMAND_ORDER_SQL`, as a SQLAlchemy expression over `sales_orders`."""
    return SalesOrder.demand_class.is_distinct_from(PROJECT_CLASS) | (
        SalesOrder.demand_origin == ORDER_INQUIRY_ORIGIN
    )


def demand_qty():
    """The quantity to plan for, as a SQLAlchemy expression over `sales_order_lines`."""
    return func.greatest(
        func.coalesce(SalesOrderLine.qty_required, SalesOrderLine.qty_ordered)
        - func.coalesce(SalesOrderLine.qty_delivered, 0),
        0,
    )


def is_open_demand():
    """The predicate every demand reader shares, minus the caller's own scoping."""
    return (SalesOrderLine.line_status == "open") & (
        SalesOrderLine.purchasing_status != COVERED
    ) & (demand_qty() > 0)


def qty_of(row) -> float:
    """The same rule against a fetched row, for callers that select the columns themselves."""
    required = getattr(row, "qty_required", None)
    ordered = float(row.qty_ordered or 0)
    base = float(required) if required is not None else ordered
    return max(base - float(row.qty_delivered or 0), 0.0)


#: The body of `scm.committed_v`. Kept as a constant so the migration that installs it and
#: the expression above are edited in the same file.
COMMITTED_V_SQL = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                    - COALESCE(sol.qty_delivered, 0), 0)) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.purchasing_status <> 'covered'
  AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
               - COALESCE(sol.qty_delivered, 0), 0) > 0
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR so.demand_origin = 'scm_order_inquiry')
GROUP BY sol.product_id, sol.warehouse_id;
"""
