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
#: The rule is in TWO halves because the decision it defers to is now per LINE. This half
#: is the ORDER-level one above, unchanged since S13b. The line-level half is
#: `PLAN_DEMAND_LINE_SQL` below, and every reader applies BOTH - `scm.committed_v`,
#: `demand_breakdown_service` and `unplanned_demand_service` all alias
#: `sales_order_lines AS sol`, which is what lets the second half be a plain string too.
PLAN_DEMAND_ORDER_SQL = (
    "(so.demand_class IS DISTINCT FROM 'project' "
    "OR so.demand_origin = 'scm_order_inquiry')"
)

#: Front planning section 4 narrows the sheet leg once more: a line counts only while it
#: has NOT been confirmed. After CS confirms it, the confirmed Buy residual in
#: `projects.order_inquiry_rows` IS that line's project demand, and leaving the sheet leg
#: on would count the same requirement twice - once as the quantity the sheet named and
#: once as the quantity CS decided still had to be bought.
#:
#: PER LINE, and that is the whole point (PLAN-fulfilment-planning-from-autocount-so.md
#: 13.4). It used to be per ORDER, joining `projects.sales_orders.so_id` to any active
#: decision, which was exact while a confirmation had to cover every line of its order.
#: Partial confirmation ended that: confirming one line of a twelve-line order would have
#: dropped all twelve from the sheet leg while only the confirmed line's Buy came back
#: through the confirmed leg, so the other eleven became demand nobody could see. The
#: captain's reason for wanting partial confirmation is precisely that those eleven keep
#: flowing to reorder planning.
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
    the whole predicate NULL, which would silently drop EVERY sheet-leg line from planning.
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
    return SalesOrder.demand_class.is_distinct_from(PROJECT_CLASS) | (
        SalesOrder.demand_origin == ORDER_INQUIRY_ORIGIN
    )


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
#: Two legs supply Project demand, and they are mutually exclusive PER LINE by design
#: (plan 4, PLAN-fulfilment-planning-from-autocount-so.md 13.4):
#:
#: * the CONFIRMED leg - current unplaced Buy on `projects.order_inquiry_rows` pointing at
#:   an ACTIVE `projects.so_supply_decisions` row, landed at the location of the reconciled
#:   core SO line. This is CS's own decision and it passes through unnetted.
#: * the SHEET leg - a line of a `demand_origin = 'scm_order_inquiry'` order, counted ONLY
#:   while no active decision COVERS THAT LINE. The moment CS confirms it, the confirmed
#:   Buy residual replaces its sheet quantity, so a sheet-named line that is later
#:   confirmed counts exactly once.
#:
#: The exclusion is per line and not per order because a confirmation now covers the
#: subset of lines the planner chose (13.4). Under the old per-order rule, confirming one
#: line of a twelve-line order removed all twelve from the sheet leg while only the
#: confirmed line came back through the confirmed leg: eleven lines of uncovered demand,
#: invisible to the reorder engine. Undecided lines keep counting, at their full
#: outstanding quantity, which is the entire reason partial confirmation was asked for.
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
    -- The core sales-order LINES an active decision covers, read out of the snapshot
    -- that records them. Per line, not per order: a confirmation covers the subset the
    -- planner chose, and the lines it left undecided must go on counting below.
    SELECT DISTINCT (snap->>'core_line_id')::uuid AS core_line_id
    FROM projects.so_supply_decisions d
    CROSS JOIN LATERAL jsonb_array_elements(d.line_snapshots) AS snap
    WHERE d.state = 'active'
      AND snap->>'core_line_id' IS NOT NULL
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
      -- Front planning narrows the sheet leg further: once CS has confirmed a LINE, its
      -- confirmed Buy residual below is the only Project reading of that line. Its
      -- undecided siblings are untouched and keep counting here.
      AND (so.demand_class IS DISTINCT FROM 'project'
           OR (so.demand_origin = 'scm_order_inquiry'
               AND NOT EXISTS (SELECT 1 FROM decided dd
                               WHERE dd.core_line_id = sol.id)))
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
           0 AS retail_qty,
           0 AS unclassified_qty
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
WITH decided AS (
    SELECT DISTINCT (snap->>'core_line_id')::uuid AS core_line_id
    FROM projects.so_supply_decisions d
    CROSS JOIN LATERAL jsonb_array_elements(d.line_snapshots) AS snap
    WHERE d.state = 'active'
      AND snap->>'core_line_id' IS NOT NULL
),
legs AS (
    SELECT sol.product_id,
           sol.warehouse_id,
           CASE WHEN so.demand_class = 'project'
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                            - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS project_qty,
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
      AND (so.demand_class IS DISTINCT FROM 'project'
           OR (so.demand_origin = 'scm_order_inquiry'
               AND NOT EXISTS (SELECT 1 FROM decided dd
                               WHERE dd.core_line_id = sol.id)))
      -- Planning horizon, sheet leg: a stated required_date past the cutoff is excluded;
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
           0 AS retail_qty,
           0 AS unclassified_qty
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
