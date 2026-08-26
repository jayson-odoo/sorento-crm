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

#: The ORDER-level half of the demand rule, as `PLAN-scm-purchasing-uat-journey.md` P3
#: leaves it (captain, 26 Aug 2026):
#:
#:   "Project demand = the UNLINKED remainder of raised OI ORDER rows, per product and
#:    location. Nothing else project-class counts."
#:
#: The SALES-ORDER BOOK speaks for the retail side and for nothing else. A project-class
#: line is never demand as a book line - it becomes demand when CS raises an Order Inquiry
#: ORDER row for it, and it stops being demand when that row is linked to a PO or an SPO.
#: One requirement, one place at a time (plan section 1).
#:
#: What this drops is the SHEET leg: an order the old Joey feed stamped
#: `demand_origin = 'scm_order_inquiry'` used to count from the book while nobody had
#: confirmed it on the fulfilment board. M310-CR-PJ showed 16 units of Project demand at
#: BRW-BB on runs b805ba89 / 93305b25 with every one of its inquiry rows already placed,
#: which is that leg and only that leg. Such an order is now AWAITING CS, counted and named
#: by `demand_source_service.set_aside_project_demand`, never netted.
#:
#: The rule is still in TWO halves, and the second one has outlived the first: the
#: line-level `PLAN_DEMAND_LINE_SQL` below says which lines an active decision already
#: covers, which is what the fulfilment board reads as "covered". Every book-demand reader
#: applies BOTH; this half now excludes project class outright, so the second is a no-op
#: for them and the board keeps the meaning it needs.
PLAN_DEMAND_ORDER_SQL = "(so.demand_class IS DISTINCT FROM 'project')"

#: Which core sales-order LINES an active supply decision already covers.
#:
#: Since P3 (26 Aug 2026) this is no longer part of what the plan counts - the order-level
#: half above excludes project class outright, so there is no sheet quantity left for a
#: decision to displace. What it still answers, and what it is now kept for, is the
#: FULFILMENT BOARD's "covered" flag: a line CS has already decided on, per LINE, so a
#: partially confirmed order shows which of its lines are done and which are not
#: (`project_fulfilment_board_service`).
#:
#: PER LINE, and that is the whole point (PLAN-fulfilment-planning-from-autocount-so.md
#: 13.4). It used to be per ORDER, joining `projects.sales_orders.so_id` to any active
#: decision, which was exact while a confirmation had to cover every line of its order.
#: Partial confirmation ended that.
#:
#: Which lines a decision COVERS is read out of `line_snapshots`, because that JSONB is
#: where it is recorded: one object per covered line, each carrying its `core_line_id`
#: (`ProjectSupplyService._snapshot`). No new table, no new column - 13.4's open
#: sub-question, answered by measuring the lateral rather than by adding a link table.
#: The match is on the core sales-order line id and never on a reference, a document
#: number or an item code.
PLAN_DEMAND_LINE_SQL = (
    "NOT EXISTS ("
    "    SELECT 1 FROM projects.so_supply_decisions d "
    "    CROSS JOIN LATERAL jsonb_array_elements(d.line_snapshots) AS snap "
    "    WHERE d.state = 'active' "
    "      AND (snap->>'core_line_id')::uuid = sol.id)"
)


def _decided_core_line_ids():
    """The core sales-order LINES an active supply decision already covers.

    UNCORRELATED on purpose, and that is the whole reason it is a list rather than the
    `NOT EXISTS` the view uses. Callers reach this predicate with `sales_order_lines`
    aliased (the coverage timeline reads `sales_order_lines AS sales_order_lines_1`), and
    a correlated sub-select then renders a reference to an alias the enclosing query never
    made - `missing FROM-clause entry for table "sales_order_lines_1"`, every demand read
    in the system. A subquery that names nothing outside itself cannot be adapted wrongly,
    and `SalesOrderLine.id` beside it is an ordinary outer column exactly like
    `SalesOrderLine.line_status`. The view keeps its `NOT EXISTS`, which is the same set:
    raw SQL has no aliasing to get wrong.

    The `IS NOT NULL` filter is load-bearing, not tidiness: a NULL in a `NOT IN` list makes
    the whole predicate NULL, which would silently drop EVERY line from the readers that
    apply it.
    A snapshot with no `core_line_id` cannot happen through the confirmation path (a line
    with no reconciled core line is refused), and the filter means a hand-written one
    could not take the plan down with it either.

    Built over the TABLE rather than the mapped class so the company-scope loader criteria
    cannot rewrite a sub-select whose only job is to answer "which lines are decided": the
    scoping that matters is the caller's, on `sales_order_lines` itself.
    """
    from sqlalchemy import cast, literal_column
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    from app.models.project_so import DECISION_ACTIVE, SOSupplyDecision

    decision = SOSupplyDecision.__table__
    snapshots = (
        func.jsonb_array_elements(decision.c.line_snapshots)
        .table_valued("value")
        .render_derived(name="snap")
        .lateral()
    )
    core_line_id = cast(
        snapshots.c.value.op("->>")(literal_column("'core_line_id'")),
        PG_UUID(as_uuid=False),
    )
    return (
        select(core_line_id)
        .select_from(decision.join(snapshots, literal_column("true")))
        .where(decision.c.state == DECISION_ACTIVE, core_line_id.isnot(None))
    )


def is_plan_demand_order():
    """`PLAN_DEMAND_ORDER_SQL`, as a SQLAlchemy expression over `sales_orders`."""
    return SalesOrder.demand_class.is_distinct_from(PROJECT_CLASS)


def is_plan_demand_line():
    """`PLAN_DEMAND_LINE_SQL`, as a SQLAlchemy expression over `sales_order_lines`.

    Applied BESIDE `is_plan_demand_order()`, never instead of it: one says which orders
    the sheet speaks for, the other which of their lines CS has already decided.
    """
    return SalesOrderLine.id.notin_(_decided_core_line_ids())


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

#: The states whose UN-LINKED remainder is still demand, which is what `scm.committed_v`
#: counts (migration 422). `partly_linked` belongs here and `raised` alone does not: since
#: the links table a row is netted by what it has been linked to rather than emptied by a
#: state change, so a row half covered by a purchase order is half of a demand still.
UNLINKED_INQUIRY_STATES = ("raised", "partly_linked")

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
#: Project demand has ONE source: `projects.order_inquiry_rows` (P3, captain 26 Aug 2026).
#: Two legs read it, and they are disjoint by construction:
#:
#: * the CONFIRMED leg - current un-linked Buy on a row pointing at an ACTIVE
#:   `projects.so_supply_decisions` row, landed at the location of the reconciled core SO
#:   line (the DONOR's location for an ORDER BACK).
#: * the FORM leg - a row the CS Order Inquiry Form raised that the sales-order book carries
#:   no line for, landed at the item code and stock location the ROW itself states.
#:
#: The SHEET leg is GONE. It counted an open line of a `demand_origin = 'scm_order_inquiry'`
#: order while no active decision covered that line, which is how M310-CR-PJ read 16 units of
#: Project demand at BRW-BB (SO394803 line 10 + SO411133 line 6) with every one of its
#: inquiry rows already placed, and how MSK11B read 243 at BRW-IB off SO409325. Those orders
#: came in through the old sheet feed months ago and nobody has confirmed them on the
#: fulfilment board - so they are AWAITING CS, not demand, and
#: `demand_source_service.set_aside_project_demand` is where they are counted and named.
#:
#: With the sheet leg gone the BOOK leg speaks for the retail side alone, so `project_qty`
#: and `project_confirmed_qty` are always equal (`project_committed` IS the confirmed
#: figure) and the old `decided` CTE has nothing left to exclude.
#:
#: Every constant leg column is `0::numeric`, and the cast is LOAD-BEARING. Postgres types a
#: bare `0` as integer, `SUM(integer)` comes out bigint, and `CREATE OR REPLACE VIEW` refuses
#: to change an existing column's type: applying this over a database already carrying the
#: view dies with `cannot change data type of view column "unclassified_committed" from
#: numeric to bigint`. It did, on the dev copy. The bodies before P3 never hit it because
#: their zeros sat in a `CASE` whose other arm was numeric, which coerced them; a whole
#: column of bare zeros has nothing to be coerced by.
#:
#: `unclassified_qty` is a CONSTANT ZERO, not a leg (P4). Nothing is unclassified any more:
#: migration 425 stamped every NULL `demand_class` retail and the SO import now refuses a
#: file that would create another, so a NULL class here reads as retail - the book-direct
#: channel - instead of as a fourth column nobody can act on. The COLUMN survives because
#: `CREATE OR REPLACE VIEW` may only append columns, never drop one, and dropping it would
#: mean dropping and rebuilding `scm.net_position_v` and everything under it for a figure
#: that is now always 0.
COMMITTED_V_SQL = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                 - COALESCE(sol.qty_delivered, 0), 0) > 0
      AND so.demand_class IS DISTINCT FROM 'project'
    UNION ALL
    -- The confirmed leg: what CS decided must be bought, at the reconciled core line's
    -- product and fulfilment location, LESS whatever of it now sits on a document
    -- (PLAN-scm-cs-planning-uat.md section 3.I). Never matched on provisional_ref,
    -- autocount_doc_no or item code (plan 4).
    --
    -- Netted per ROW rather than tested per STATE. Before `order_inquiry_links` a row was
    -- all or nothing - `raised` counted the whole quantity, `placed` counted none - so a
    -- cascade that could only cover part of a row had to SPLIT the row for the arithmetic
    -- to come out, which is how nine sales-order lines became eleven instructions. A fully
    -- linked row now leaves confirmed demand exactly as `placed` did, and a half-linked
    -- one leaves half of it.
    --
    -- ORDER_BACK counts here too (PLAN-scm-purchasing-uat-journey.md section 4b): it is
    -- still demand until it is linked. At the DONOR's location, which is what the row's
    -- own `stock_location` names: the row hangs off the BORROWING line, so reading the
    -- core line's warehouse would put the hole in a warehouse that never had one.
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    LEFT JOIN warehouses donor ON donor.warehouse_code = oir.stock_location
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) lk ON TRUE
    WHERE oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). CS writes `ORDER BACK` where a delivery date belongs, and the form is the only
    -- writer that can raise it - the fulfilment board has nothing to decide about a line
    -- AutoCount has closed. The ROW states its own item and location, and those are what
    -- this leg reads, whether or not it also names a sales-order line. Without it the
    -- fourteen instructions on SO381895's first two forms are raised, shown to purchasing,
    -- and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `supply_decision_id IS NULL` keeps this leg disjoint from the CONFIRMED leg above:
    -- a row a CS decision points at is counted there, at the core line's product and
    -- location, and every OTHER raised row is counted here at its own. The leg used to
    -- demand `so_line_id IS NULL` as well, because a row naming a book line was already
    -- counted by the SHEET leg; P3 retired that leg, and the condition would now DELETE
    -- such a row from planning instead of de-duplicating it - the form raises ORDER BACK
    -- rows carrying an `so_line_id` (`project_order_inquiry_import_service`), and they are
    -- demand like any other.
    --
    -- The `NOT EXISTS` below keeps it disjoint from the BOOK leg, which is the other half
    -- of the same worry and the half P3 opened: the book still speaks for retail, so a
    -- decision-less row naming a RETAIL line would be counted twice, once as the line and
    -- once as the row. Stated as "the book leg does not count this line" - the same four
    -- openness conditions the book leg applies, plus its class test - rather than as "the
    -- line is project": a row whose line is unreconciled, closed or fully delivered is
    -- counted by nothing else, and a class test alone would drop it.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.supply_decision_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM projects.sales_order_lines fpsl
          JOIN sales_order_lines fsol ON fsol.id = fpsl.core_sales_order_line_id
          JOIN sales_orders fso ON fso.id = fsol.sales_order_id
          WHERE fpsl.id = oir.so_line_id
            AND fso.demand_class IS DISTINCT FROM 'project'
            AND fso.status = 'open'
            AND fsol.line_status = 'open'
            AND fsol.purchasing_status <> 'covered'
            AND GREATEST(COALESCE(fsol.qty_required, fsol.qty_ordered)
                       - COALESCE(fsol.qty_delivered, 0), 0) > 0)
      AND oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
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


def horizon_committed_select_sql() -> str:
    """`COMMITTED_V_SQL`'s body, as a bare SELECT (no `CREATE VIEW`) with a `:horizon`
    bind narrowing both legs to demand due at or before it.

    Planning horizon (captain, 20 Aug): "SOs needed in 2030" a buyer never asked about
    should not distort a plan they only want through December. `scm.committed_v` itself
    is untouched and every OTHER reader (the demand-drill popover, the dashboard, the
    coverage timeline) keeps reading it unfiltered - this is used ONLY by
    `reorder_run_service._planning_rows` to override a single run's own committed figure
    when that run was asked for a horizon.

    A NULL `:horizon` reproduces `scm.committed_v` exactly: every date comparison short-
    circuits true, so an unhorizoned run (the daily scheduled one, and any manual run
    that leaves the field empty) nets byte-for-byte as before. Demand carrying NO date at
    all is always counted, whatever the bind - unscheduled demand is still demand, not a
    reason to guess it is late.

    Kept beside `COMMITTED_V_SQL` rather than derived from it: the view body is frozen
    for the migration/downgrade pair (`test_committed_v_migration_chain.py`) and must
    stay copy-pasteable, so this is a second copy of the same `legs` shape with one
    predicate added to each leg - the same relationship `COMMITTED_V_SQL` already has to
    the individual predicates in this module (`PLAN_DEMAND_ORDER_SQL` etc).
    """
    return """
WITH legs AS (
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                 - COALESCE(sol.qty_delivered, 0), 0) > 0
      AND so.demand_class IS DISTINCT FROM 'project'
      -- Planning horizon, book leg: a stated required_date past the cutoff is excluded;
      -- no date at all is always in.
      AND (CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL
           OR sol.required_date <= CAST(:horizon AS date))
    UNION ALL
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    LEFT JOIN warehouses donor ON donor.warehouse_code = oir.stock_location
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) lk ON TRUE
    WHERE oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
      -- Planning horizon, confirmed leg: same rule, off the inquiry row's own delivery
      -- date rather than the core line's required_date.
      AND (CAST(:horizon AS date) IS NULL OR oir.delivery_date IS NULL
           OR oir.delivery_date <= CAST(:horizon AS date))
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). CS writes `ORDER BACK` where a delivery date belongs, and the form is the only
    -- writer that can raise it - the fulfilment board has nothing to decide about a line
    -- AutoCount has closed. The ROW states its own item and location, and those are what
    -- this leg reads, whether or not it also names a sales-order line. Without it the
    -- fourteen instructions on SO381895's first two forms are raised, shown to purchasing,
    -- and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `supply_decision_id IS NULL` keeps this leg disjoint from the CONFIRMED leg above:
    -- a row a CS decision points at is counted there, at the core line's product and
    -- location, and every OTHER raised row is counted here at its own. The leg used to
    -- demand `so_line_id IS NULL` as well, because a row naming a book line was already
    -- counted by the SHEET leg; P3 retired that leg, and the condition would now DELETE
    -- such a row from planning instead of de-duplicating it - the form raises ORDER BACK
    -- rows carrying an `so_line_id` (`project_order_inquiry_import_service`), and they are
    -- demand like any other.
    --
    -- The `NOT EXISTS` below keeps it disjoint from the BOOK leg, which is the other half
    -- of the same worry and the half P3 opened: the book still speaks for retail, so a
    -- decision-less row naming a RETAIL line would be counted twice, once as the line and
    -- once as the row. Stated as "the book leg does not count this line" - the same four
    -- openness conditions the book leg applies, plus its class test - rather than as "the
    -- line is project": a row whose line is unreconciled, closed or fully delivered is
    -- counted by nothing else, and a class test alone would drop it.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.supply_decision_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM projects.sales_order_lines fpsl
          JOIN sales_order_lines fsol ON fsol.id = fpsl.core_sales_order_line_id
          JOIN sales_orders fso ON fso.id = fsol.sales_order_id
          WHERE fpsl.id = oir.so_line_id
            AND fso.demand_class IS DISTINCT FROM 'project'
            AND fso.status = 'open'
            AND fsol.line_status = 'open'
            AND fsol.purchasing_status <> 'covered'
            AND GREATEST(COALESCE(fsol.qty_required, fsol.qty_ordered)
                       - COALESCE(fsol.qty_delivered, 0), 0) > 0)
      AND oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
      -- Planning horizon, form leg: the same rule again. An ORDER BACK row states no
      -- date at all, so it is always in - unscheduled demand is still demand.
      AND (CAST(:horizon AS date) IS NULL OR oir.delivery_date IS NULL
           OR oir.delivery_date <= CAST(:horizon AS date))
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id
"""
