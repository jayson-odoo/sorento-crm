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

from sqlalchemy import func, select

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
#:
#: Front planning section 4 narrows the sheet leg once more: it counts only while the core
#: SO has NO active confirmed supply decision. After CS confirms, the confirmed Buy
#: residual in `projects.order_inquiry_rows` IS the project demand, and leaving the sheet
#: leg on would count the same requirement twice - once as the quantity the sheet named
#: and once as the quantity CS decided still had to be bought. The join is through
#: `projects.sales_orders.so_id`, never a reference, a document number or an item.
PLAN_DEMAND_ORDER_SQL = (
    "(so.demand_class IS DISTINCT FROM 'project' "
    "OR (so.demand_origin = 'scm_order_inquiry' "
    "    AND NOT EXISTS ("
    "        SELECT 1 FROM projects.sales_orders pso "
    "        JOIN projects.so_supply_decisions d "
    "          ON d.project_sales_order_id = pso.id "
    "        WHERE pso.so_id = so.id AND d.state = 'active')))"
)


def _decided_sales_order_ids():
    """The core sales orders CS has already confirmed a supply decision for.

    UNCORRELATED on purpose, and that is the whole reason it is a list rather than the
    `NOT EXISTS` the view uses. Callers reach this predicate with `sales_order_lines`
    aliased (the coverage timeline reads `sales_order_lines AS sales_order_lines_1`), and
    a correlated sub-select then renders a reference to an alias of `sales_orders` that
    the enclosing query never made - `missing FROM-clause entry for table
    "sales_orders_1"`, every demand read in the system. A subquery that names nothing
    outside itself cannot be adapted wrongly, and `SalesOrder.id` beside it is an ordinary
    outer column exactly like `SalesOrder.demand_class`. The view keeps its `NOT EXISTS`,
    which is the same set: raw SQL has no aliasing to get wrong.

    `so_id IS NOT NULL` is load-bearing, not tidiness: a NULL in a `NOT IN` list makes the
    whole predicate NULL, which would silently drop EVERY sheet-leg order from planning.

    Built over the TABLES rather than the mapped classes so the company-scope loader
    criteria cannot rewrite a sub-select whose only job is to answer "which orders are
    decided": the scoping that matters is the caller's, on `sales_orders` itself.
    """
    from app.models.project_so import (
        DECISION_ACTIVE,
        ProjectSalesOrder,
        SOSupplyDecision,
    )

    pso = ProjectSalesOrder.__table__
    decision = SOSupplyDecision.__table__
    return (
        select(pso.c.so_id)
        .select_from(pso.join(decision, decision.c.project_sales_order_id == pso.c.id))
        .where(decision.c.state == DECISION_ACTIVE, pso.c.so_id.isnot(None))
    )


def is_plan_demand_order():
    """`PLAN_DEMAND_ORDER_SQL`, as a SQLAlchemy expression over `sales_orders`."""
    return SalesOrder.demand_class.is_distinct_from(PROJECT_CLASS) | (
        (SalesOrder.demand_origin == ORDER_INQUIRY_ORIGIN)
        & SalesOrder.id.notin_(_decided_sales_order_ids())
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


#: The Order Inquiry verb that says "buy this". The only verb that is new purchasing
#: demand; every other verb is an amendment instruction or a coverage note.
BUY_VERB = "ORDER"

#: An inquiry row still waiting to be placed. `actioned` means purchasing has bought it
#: and `cancelled` means it went away, so neither is current need.
UNPLACED_INQUIRY_STATE = "raised"

#: The one decision state that counts. A superseded or challenged revision's Buy is
#: history, and counting it would buy the same requirement twice.
ACTIVE_DECISION_STATE = "active"

#: The body of `scm.committed_v`. Kept as a constant so the migration that installs it and
#: the expression above are edited in the same file.
#:
#: Front planning (plan 4, 5.3, 6.4) splits the SAME aggregate row by demand channel. The
#: keys and the cardinality are untouched - one row per (product_id, warehouse_id) - and
#: `committed` stays the sum of the three new columns, so `scm.net_position_v` and every
#: consumer of it sees no change. What is new is that the row can now SAY which channel its
#: commitment came from, which is what makes a Project total firm and a Retail total
#: nettable without a second read model.
#:
#: Two legs supply Project demand, and they are mutually exclusive by design (plan 4):
#:
#: * the CONFIRMED leg - current unplaced Buy on `projects.order_inquiry_rows` pointing at
#:   an ACTIVE `projects.so_supply_decisions` row, landed at the location of the reconciled
#:   core SO line. This is CS's own decision and it passes through unnetted.
#: * the SHEET leg - a `demand_origin = 'scm_order_inquiry'` order, counted ONLY while its
#:   SO has no active decision. The moment CS confirms, the confirmed Buy residual replaces
#:   the sheet quantity, so a sheet-named SO that is later confirmed counts exactly once.
#:
#: A project-class order with neither (the normal book, no decision) is still set aside -
#: unchanged behaviour, now provably absent from all four columns rather than just from the
#: old one.
#:
#: Only ONE of those legs is FIRM, which is why there is a fifth column. Plan 5.3 defines
#: `project_need` as "confirmed unplaced Buy" and AC-E05 bypasses the reorder trigger for
#: "confirmed unplaced Project Buy": that is the CONFIRMED leg alone, so it gets its own
#: `project_confirmed_committed` for the engine to read. The sheet leg stays inside
#: `project_committed` (plan 6.4: the Project column reads both legs, and the display column
#: must not lose it) but is netted like any other commitment, exactly as it was before this
#: split existed - S13b's "the book supplies the rest". Passing the whole of
#: `project_committed` past the trigger bought stock a shared pool already held.
COMMITTED_V_SQL = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH decided AS (
    SELECT DISTINCT pso.so_id AS sales_order_id
    FROM projects.sales_orders pso
    JOIN projects.so_supply_decisions d
      ON d.project_sales_order_id = pso.id
     AND d.state = 'active'
    WHERE pso.so_id IS NOT NULL
),
legs AS (
    SELECT sol.product_id,
           sol.warehouse_id,
           CASE WHEN so.demand_class = 'project'
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS project_qty,
           -- The sheet leg is project-class demand, never firm Buy: no CS decision points
           -- at it, so it is netted like any other commitment (S13b).
           0 AS project_confirmed_qty,
           CASE WHEN so.demand_class IS NOT NULL AND so.demand_class <> 'project'
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS retail_qty,
           CASE WHEN so.demand_class IS NULL
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                   - COALESCE(sol.qty_delivered, 0), 0) > 0
      -- S13b: project demand comes from the Order Inquiry; the book supplies the rest.
      -- Front planning narrows the sheet leg further: once CS has confirmed a decision
      -- for the order, its confirmed Buy residual below is the only Project reading.
      AND (so.demand_class IS DISTINCT FROM 'project'
           OR (so.demand_origin = 'scm_order_inquiry'
               AND NOT EXISTS (SELECT 1 FROM decided dd
                               WHERE dd.sales_order_id = so.id)))
    UNION ALL
    -- The confirmed leg: what CS decided must be bought, at the reconciled core line's
    -- product and fulfilment location. Never matched on provisional_ref, autocount_doc_no
    -- or item code (plan 4).
    SELECT sol.product_id,
           sol.warehouse_id,
           oir.qty AS project_qty,
           oir.qty AS project_confirmed_qty,
           0 AS retail_qty,
           0 AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    WHERE oir.verb = 'ORDER'
      AND oir.state = 'raised'
      AND oir.qty > 0
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       -- LAST on purpose: appended, so a CREATE OR REPLACE of this body over a database
       -- already carrying the four-column view is legal (Postgres lets a replacement add
       -- columns at the end and nowhere else). A SUBSET of `project_committed`, never a
       -- fourth addend of `committed` - adding it there would count confirmed Buy twice.
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""
