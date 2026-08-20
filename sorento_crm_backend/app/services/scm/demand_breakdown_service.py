"""Which orders a planned buy is actually for.

> "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh, i will
>  want to see in the reorder planning, what's the demand quantity, where it comes from, is
>  it project / retail"

A recommendation names a POOL, and pooled netting is the reason a shortage at BRW-IB is
bought into BRW. That is correct and completely opaque from the row alone: the planner sees
a location they did not order for, and a quantity larger than the order they remember.

This lists the open order lines the number was built from - order, location, class, quantity,
when it is needed, who ordered it and at what price - including the ones that named no
location and were attributed here. It explains, it never re-derives: the same filter
`scm.committed_v` applies, so the sum of these lines IS the committed figure the engine
netted.

SCOPE IS THE ROW'S, NOT THE POOL'S. A plan row is a product AT a location, and it was
netted per location unless the run netted its pool together. Listing the whole pool
regardless answered a question nobody asked - the buyer looking at BRW-BB was shown
BRW-IB's orders and a total larger than the SO figure printed on their own row. So the
scope is the set the RUN netted, and is stated in the header when it is the pool.

PROVENANCE (20 Aug live ask): "for project is order inquiry, for retail is sales order
directly". Every line carries a `source` - `order_inquiry` when the order the sheet-leg
line belongs to was created BY the Order Inquiry feed (`demand_origin`), `sales_order`
when it was not (the retail book, straight off AutoCount). A THIRD source,
`order_inquiry_confirmed`, is the leg the sheet-leg query cannot show at all: once CS
confirms a line, its sheet quantity leaves this query by design (`PLAN_DEMAND_LINE_SQL`'s
`NOT EXISTS`) and the confirmed Buy residual on `projects.order_inquiry_rows` becomes the
only Project reading of it - `scm.committed_v`'s own two-leg split, mirrored here so the
popover's total and the netted figure never disagree. The two legs are mutually exclusive
PER LINE by construction: a core line only ever appears in the confirmed leg here if an
active decision's `line_snapshots` names it, and that is exactly the condition
`PLAN_DEMAND_LINE_SQL` excludes it on in the sheet leg - so summing both is additive,
never double-counted.

WHO SOLD IT (21 Aug live ask): `sales_orders.sales_agent_id` -> `sales_agents`, the same
salesperson master `sales_order_service._agent_fields` already reads for the SO detail
page. Every code ships with `person_label` unset today (measured on the live book: 0 of
the codes carry one), so `AGENT_LABEL_SQL` falls back from the grouping label to the code
itself - never invented, and never the raw FK. NULL on a sheet-leg line built by the Order
Inquiry import (`project_order_inquiry_import_service` never sets it), which is the honest
reading for it: nobody has attributed an agent to that order yet.

WHAT THEY PAY (21 Aug live ask): `sol.unit_price` / `psl.unit_price` were already the read
- this module has carried them since the price question was first asked (see the PROVENANCE
history below). A captain-witnessed "RM 0.00" is a real value on that line, not a
serializer bug: measured live, 60% of sheet-leg Order-Inquiry lines and 50% of confirmed-leg
lines carry a positive price, and the rest are genuinely priced at 0.00 or carry no price at
all - the FE already tells those two apart (a null price renders nothing, a stated 0.00
renders "RM 0.00"). Nothing here changed for the price read; this note exists so the next
person who goes looking for the bug does not re-derive the same investigation.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.scm.customer_label import CUSTOMER_JOIN_ON, CUSTOMER_LABEL_SQL
from app.services.scm.demand import (
    ACTIVE_DECISION_STATE,
    BUY_VERB,
    ORDER_INQUIRY_ORIGIN,
    PLAN_DEMAND_LINE_SQL,
    PLAN_DEMAND_ORDER_SQL,
    PROJECT_CLASS,
    UNPLACED_INQUIRY_STATE,
)
from app.services.scm.trajectory import month_shift
from app.services.scm.trajectory_service import demand_context_for_product

# One screen's worth. A pool with thousands of lines is a reading problem, not a listing
# problem, and the total is reported separately so the cap is never silent.
DEFAULT_LIMIT = 200

# The three buckets a line's `demand_class` sorts into (captain, 20 Aug: "i think it would
# be easier if we can just put the icon at project and retail separately then we don't need
# the open SOs"). Filtering the LIST by channel, not just labelling it after the fact, is
# the point - ordering the unfiltered query by `required_date` let one channel's earliest
# lines crowd the other off the 200-line cap, so a Project trigger next to
# `project_committed` popped open a page that was mostly Retail (BRW: 279 lines, 200 shown,
# retail happened to sort first).
_CHANNELS = {"project", "retail", "unclassified"}

# Quantities are floats out of NUMERIC, and "does this set reproduce the frozen figure"
# must not turn on the last bit of a sum.
_QTY_TOLERANCE = 0.001

#: Who sold it - the salesperson master, resolved off `sales_orders.sales_agent_id`
#: (`app/models/sales_agent.py`). `person_label` is the grouping a human sets on top of
#: the raw code ("SEAN I"/"SEAN III"/"LCL" are three agents, one person); every code ships
#: with it unset today, so this reads as the code itself until someone groups it. NULL
#: when the order carries no agent at all - never invented (see the module docstring).
#: Assumes the query joins `LEFT JOIN sales_agents sa ON sa.id = so.sales_agent_id`.
AGENT_LABEL_SQL = "COALESCE(sa.person_label, sa.sales_agent)"


def _pool_of(db: Session, wid: str) -> tuple[list[str], Optional[str]]:
    """Every location sharing this one's pool, and the pool's own code.

    The row sits on the location that was short, NOT on the pool root, so the pool is
    resolved FROM it: root first, then every member. Reading the row's own id as the pool
    returned nothing for a bin, and the breakdown came back empty for exactly the rows
    that most need explaining.

    Company-scoped by hand, because this is raw SQL and the isolation filter runs on ORM
    execution ONLY (same reason as `reorder_run_service._planning_rows`): another company's
    warehouse sharing this pool would put its orders under this row.
    """
    co, co_params = company_sql_predicate(db, "w.company_id", param_prefix="dbs")
    rows = db.execute(text(
        "SELECT w.id::text AS id, w.warehouse_code, "
        "       COALESCE(w.pool_warehouse_id, w.id)::text AS pool_id "
        "FROM warehouses w "
        "WHERE COALESCE(w.pool_warehouse_id, w.id) = ("
        "  SELECT COALESCE(pool_warehouse_id, id) FROM warehouses WHERE id::text = :wid"
        ") " + (f"AND {co}" if co else "")
    ), {"wid": wid, **co_params}).mappings().all()
    pool_id = next((r["pool_id"] for r in rows), None)
    pool_code = next((r["warehouse_code"] for r in rows if r["id"] == pool_id), None)
    return [r["id"] for r in rows], pool_code


def _scope_for(db: Session, rec,
               total_for: Callable[[list[str]], float]) -> tuple[list[str], str,
                                                                 Optional[str]]:
    """The locations this row's demand was netted over, and what to call that set.

    READ OFF THE RUN, NEVER OFF THE POLICY. `pool_netting` is a switch the buyer can flip
    at any time, and resolving it at popover time described a frozen row by a rule it was
    never planned under: flip it off and a pooled row's own list shrank below the quantity
    printed on it; flip it on and a per-location row acquired its siblings' orders, which
    is the "why so many" the popover exists to answer, reintroduced by the explanation.
    Every fact below is on the recommendation the run wrote, so nothing said here can move
    until the plan is re-run.

    Two frozen facts answer it, in order:

    1. `allocation`. Only the pooled path writes one (`_emit_pool` -> `eng.allocate`), and
       it carries a key for EVERY location the pool was sized over, share or no share. So
       an allocation naming more than one location IS the netted set - already restricted
       to what the run planned, which the pool read off `warehouses` is not (a run scoped
       to two bins of a three-bin site netted two).
    2. `inputs.committed`, the quantity the row was sized against. A row netted on its own
       cell reproduces it from its own location; the pool's single `covered` / `exception`
       row sits on the pool root carrying the pool's total, and no allocation, so the pool
       is what reproduces it. Where neither does - the order book has moved on since the
       run froze - the row's own location is the honest answer, because listing a sibling's
       orders under a row that may not have been sized against them is the failure this
       scoping exists to prevent.
    """
    wid = rec["warehouse_id"]
    if not wid:
        # A network-scope row names no location, so there is nothing to narrow to.
        return [], "warehouse", None

    pool_ids, pool_code = _pool_of(db, wid)

    allocated = {
        str(a["warehouse_id"]) for a in (rec["allocation"] or [])
        if isinstance(a, dict) and a.get("warehouse_id")
    } & set(pool_ids)
    # A pool of one is the row's own warehouse under another name, and calling that "pool"
    # in the header would invent a netting decision that never happened. Mirrors the
    # engine's own `len(members) == 1` branch.
    if len(allocated) > 1:
        return sorted(allocated), "pool", pool_code

    committed = (rec["inputs"] or {}).get("committed")
    if committed is None or abs(total_for([wid]) - float(committed)) <= _QTY_TOLERANCE:
        return [wid], "warehouse", None
    if len(pool_ids) > 1 and abs(total_for(pool_ids) - float(committed)) <= _QTY_TOLERANCE:
        return sorted(pool_ids), "pool", pool_code
    return [wid], "warehouse", None


def demand_for_recommendation(db: Session, rec_id: str,
                              limit: int = DEFAULT_LIMIT,
                              channel: Optional[str] = None,
                              scope: Optional[str] = None) -> dict[str, Any]:
    """Open demand behind one recommendation, newest-needed first.

    `channel` narrows the list to ONE of `project`/`retail`/`unclassified` - anything else
    (None, an unrecognised string) is unfiltered, so a caller that never asks for a channel
    (the ungrouped row's own popover) sees exactly what it always has. Filtering happens
    before the display cap and before the sort, never after, and the SCOPE test below still
    runs against the UNFILTERED total - a channel is a display slice of an already-resolved
    row, never a second opinion on which locations that row was netted over.

    `scope="product"` (5.3 follow-up, 21 Aug live ask: "put the tooltip on the TOP
    product-grain row too") unions this recommendation's own netted locations with every
    SIBLING recommendation this run wrote for the SAME product - each resolved by the same
    `_scope_for` test, so a sibling that was itself pooled contributes its whole pool, not
    just its own cell. This is the exact union the grouped Buy view's channel columns
    already sum (`planLineGrouping.ts`'s `channelQty`), so a drill opened from the top
    product-grain row lists precisely the orders behind the number printed beside it.
    Anything else (the default) keeps the existing ROW scope - a pool, or the row's own
    warehouse.
    """
    channel = channel if channel in _CHANNELS else None
    rec = db.execute(text(
        "SELECT run_id::text AS run_id, product_id::text AS product_id, "
        "       warehouse_id::text AS warehouse_id, rec_type, inputs, allocation "
        "FROM scm.reorder_recommendation WHERE id = :id"
    ), {"id": rec_id}).mappings().first()
    if rec is None:
        return {"lines": [], "total": 0, "shown": 0, "committed_total": 0.0,
                "unlocated_total": 0.0, "locations": [], "scope": "warehouse",
                "pool_code": None, "project_total": 0.0, "retail_total": 0.0,
                "unclassified_total": 0.0, "project_12m_qty": 0.0, "retail_3m_qty": 0.0,
                "project_window_months": None, "retail_window_months": None,
                "demand_context_as_of": None, "channel": channel,
                "history_lines": [], "history_shown": 0}

    # The run's own "Plan until" cutoff (captain, 20 Aug), so this drill speaks the SAME
    # window `inputs.committed` was frozen against. Without it the scope test compares a
    # live, unhorizoned total to a horizoned frozen figure - the two can never tie, so a
    # row is mislabelled "pool" and lists a sibling warehouse's lines, and even a correctly
    # scoped row's lines fail to sum to it (a live sum over dates the run itself excluded).
    horizon = db.execute(text(
        "SELECT plan_horizon_date FROM scm.reorder_run WHERE id = :rid"
    ), {"rid": rec["run_id"]}).scalar()

    # Unlocated demand was attributed to exactly one location per product, so it belongs to
    # this row only when THIS row is the one carrying it.
    include_unlocated = bool((rec["inputs"] or {}).get("unlocated_demand"))

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="dbk")
    qty = ("GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
           "         - COALESCE(sol.qty_delivered, 0), 0)")
    # Both halves of the rule: which orders the sheet speaks for, and which of their lines
    # CS has already decided (`demand.py`). Applying only the first would show a buyer the
    # sheet quantity of a line whose confirmed Buy is already in the plan beside it.
    plan_demand = f"{PLAN_DEMAND_ORDER_SQL} AND {PLAN_DEMAND_LINE_SQL}"
    # Same horizon rule as `demand.horizon_committed_select_sql` / `reorder_run_service`'s
    # own horizon predicates: a stated `required_date` past the cutoff is excluded, no
    # date at all is always in. A NULL `:horizon` reproduces the unhorizoned query.
    horizon_pred = ("(CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL "
                    "OR sol.required_date <= CAST(:horizon AS date))")

    def _committed_total(candidate: list[str], include_unloc: bool) -> float:
        """What this candidate location set commits for this product, by the same filter
        the display list uses - the scope test has to ask the question the list will
        answer, or the header could name a set the lines below it do not add up to.

        Parametrized on `include_unloc` (rather than closing over the row's own
        `include_unlocated`) so a SIBLING recommendation's own unlocated attribution
        (`scope="product"`, below) is tested against ITS OWN flag, not the primary row's -
        unlocated demand is attributed to exactly one row per product, and only that row's
        own scope test should ever fold it in.
        """
        loc = "sol.warehouse_id::text = ANY(:members)"
        if include_unloc:
            loc = f"({loc} OR sol.warehouse_id IS NULL)"
        return float(db.execute(
            text(f"""
                SELECT COALESCE(sum({qty}), 0)
                FROM sales_order_lines sol
                JOIN sales_orders so ON so.id = sol.sales_order_id
                WHERE sol.product_id::text = :pid
                  AND so.status = 'open' AND sol.line_status = 'open'
                  AND sol.purchasing_status <> 'covered'
                  AND {qty} > 0
                  AND {plan_demand}
                  AND {loc}
                  AND {horizon_pred}
                  {("AND " + co) if co else ""}
            """),
            {"pid": rec["product_id"], "members": candidate, "horizon": horizon, **co_params},
        ).scalar() or 0)

    members, rec_scope, pool_code = _scope_for(
        db, rec, lambda candidate: _committed_total(candidate, include_unlocated)
    )

    if scope == "product":
        siblings = db.execute(text(
            "SELECT id::text AS id, warehouse_id::text AS warehouse_id, inputs, allocation "
            "FROM scm.reorder_recommendation "
            "WHERE run_id = :rid AND product_id = :pid AND id <> :self_id"
        ), {"rid": rec["run_id"], "pid": rec["product_id"], "self_id": rec_id}).mappings().all()
        member_set = set(members)
        for srec in siblings:
            s_include = bool((srec["inputs"] or {}).get("unlocated_demand"))
            s_members, _, _ = _scope_for(
                db, srec, lambda candidate, incl=s_include: _committed_total(candidate, incl)
            )
            member_set.update(s_members)
            include_unlocated = include_unlocated or s_include
        members = sorted(member_set)
        # Distinct from "warehouse"/"pool" - a product-wide union is neither a single
        # location nor one pool, and calling it either would invent a netting decision the
        # run never made. The FE already treats an unrecognised scope word as "no pool
        # suffix", so this reads as the plain location list plus its own count.
        rec_scope, pool_code = "product", None

    where_loc = "sol.warehouse_id::text = ANY(:members)"
    if include_unlocated:
        where_loc = f"({where_loc} OR sol.warehouse_id IS NULL)"

    # Whether an Order Inquiry row exists for THIS core line right now - not whether the
    # order was ever TOUCHED by the OI import (`source`/`demand_origin` below, which is a
    # stamp on the ORDER and survives long after CS confirms every line off it). The "OI"
    # chip promised a worklist entry that this alone can promise: 605 core SOs carry the
    # import stamp, 7 still have a row. Same join shape as the confirmed leg further down
    # (`oir.so_line_id` -> `psl.id` -> `psl.core_sales_order_line_id` -> `sol.id`), state
    # and verb left unfiltered because `orderInquiryWorklistHref` opens the worklist with
    # no state filter either - this must agree with what that click-through will show.
    has_inquiry_pred = (
        "EXISTS (SELECT 1 FROM projects.sales_order_lines hpsl "
        "JOIN projects.order_inquiry_rows hoir ON hoir.so_line_id = hpsl.id "
        "WHERE hpsl.core_sales_order_line_id = sol.id)"
    )

    # Which bucket a line falls in - the same three-way split the totals CASE below already
    # applies, restated as a WHERE so the display list and cap can be scoped to it. `TRUE`
    # (channel=None) reproduces the unfiltered query byte-for-byte.
    if channel == "project":
        channel_pred = "so.demand_class = :channel_project_class"
    elif channel == "retail":
        channel_pred = ("so.demand_class IS NOT NULL "
                        "AND so.demand_class <> :channel_project_class")
    elif channel == "unclassified":
        channel_pred = "so.demand_class IS NULL"
    else:
        channel_pred = "TRUE"

    def _sql_for(pred: str) -> str:
        return f"""
            SELECT so.so_number, so.order_type, so.demand_class, so.order_date,
                   so.demand_origin,
                   sol.required_date, w.warehouse_code, sol.unit_price,
                   {CUSTOMER_LABEL_SQL} AS customer_label,
                   {AGENT_LABEL_SQL} AS agent_label,
                   {qty} AS qty, {has_inquiry_pred} AS has_inquiry_row
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            LEFT JOIN warehouses w ON w.id = sol.warehouse_id
            LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
            LEFT JOIN sales_agents sa ON sa.id = so.sales_agent_id
            WHERE sol.product_id::text = :pid
              AND so.status = 'open' AND sol.line_status = 'open'
              AND sol.purchasing_status <> 'covered'
              AND {qty} > 0
              AND {plan_demand}
              AND {where_loc}
              AND {horizon_pred}
              AND {pred}
              {("AND " + co) if co else ""}
        """

    # The channel-filtered query, used for everything shown to the reader - the lines, the
    # display cap, and the totals below. Equal to `_sql_for("TRUE")` when unfiltered.
    display_sql = _sql_for(channel_pred)

    limit_n = max(1, int(limit or DEFAULT_LIMIT))
    params: dict[str, Any] = {"pid": rec["product_id"], "members": members,
                              "horizon": horizon, "channel_project_class": PROJECT_CLASS,
                              **co_params}
    rows = db.execute(text(
        display_sql + " ORDER BY sol.required_date NULLS LAST, so.so_number LIMIT :limit"
    ), {**params, "limit": limit_n}).mappings().all()
    # SF-2: `project_qty`/`retail_qty`/`unclassified_qty` are read off this SAME uncapped
    # aggregate (never off the capped `rows`/`all_lines` fetched below), the same way
    # `committed`/`unlocated` already were - so the by-channel totals stay correct past the
    # display cap instead of only summing whatever page happened to be returned. When
    # `channel` filters the underlying set, the other two buckets come back zero here -
    # which is honest: nothing of that bucket is IN this filtered list to sum.
    totals = db.execute(text(
        f"SELECT count(*) AS n, COALESCE(sum(qty), 0) AS committed, "
        f"       COALESCE(sum(qty) FILTER (WHERE warehouse_code IS NULL), 0) AS unlocated, "
        f"       COALESCE(sum(qty) FILTER (WHERE demand_class = :project_class), 0) "
        f"           AS project_qty, "
        f"       COALESCE(sum(qty) FILTER (WHERE demand_class IS NOT NULL "
        f"                                    AND demand_class <> :project_class), 0) "
        f"           AS retail_qty, "
        f"       COALESCE(sum(qty) FILTER (WHERE demand_class IS NULL), 0) "
        f"           AS unclassified_qty "
        f"FROM ({display_sql}) t"
    ), {**params, "project_class": PROJECT_CLASS}).mappings().first()

    lines = [
        {
            "so_number": r["so_number"],
            # The location the ORDER named, or the fact that it named none. "-" would read
            # as missing data; this is a fact about the order.
            "warehouse_code": r["warehouse_code"],
            "is_unlocated": r["warehouse_code"] is None,
            "order_type": r["order_type"],
            "demand_class": r["demand_class"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "required_date": r["required_date"].isoformat() if r["required_date"] else None,
            "qty": float(r["qty"] or 0),
            # Who ordered it, who sold it, and what they pay. Both people are read off the
            # order rather than looked up elsewhere: an unresolvable debtor code is still an
            # attribution, and a line the extract carries no price for says nothing rather
            # than 0.
            "customer_label": r["customer_label"],
            "agent_label": r["agent_label"],
            "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
            # "for project is order inquiry, for retail is sales order directly" - which
            # feed wrote the order this line belongs to. `order_inquiry` here means the
            # ORDER was created by the OI import (`demand_origin`), not that a row still
            # exists for THIS line - `has_inquiry_row` (below) is the one that answers that.
            "source": (
                "order_inquiry" if r["demand_origin"] == ORDER_INQUIRY_ORIGIN
                else "sales_order"
            ),
            # Whether the Order Inquiry worklist actually has something to show for this
            # line right now - the fact the "OI" chip used to claim just by existing.
            "has_inquiry_row": bool(r["has_inquiry_row"]),
        }
        for r in rows
    ]

    # The CONFIRMED Order-Inquiry leg (front planning 6.3 / `scm.committed_v`'s own
    # second UNION ALL leg) - the sheet-leg query above cannot show it at all, because
    # `PLAN_DEMAND_LINE_SQL` excludes exactly the core lines it covers. Same join shape as
    # `summary_order_service._earliest_project_need_dates`. Scoped to `members`, the SAME
    # locations the sheet leg was scoped to, so a pooled row's confirmed evidence is the
    # pool's and a per-location row's is that location's alone. Entirely project-class by
    # construction (S13b), so a `retail`/`unclassified` channel filter excludes it outright
    # rather than querying for rows that can never match.
    confirmed_rows: list[Any] = []
    confirmed_n = 0
    confirmed_total = 0.0
    if members and channel in (None, "project"):
        # SF-1: unlike the sheet leg above, this had NO `LIMIT` at all - past the cap the
        # sheet leg's `total`/`shown` were already correct and this leg's were not, so the
        # combined figures disagreed with what was actually returned. Same shape as the
        # sheet leg: a base query with no ORDER BY/LIMIT, a capped fetch for the lines the
        # FE renders, and a separate uncapped count/sum for the totals.
        confirmed_base_sql = f"""
            SELECT so.so_number, so.order_type, so.order_date,
                   oir.delivery_date AS required_date, w.warehouse_code,
                   psl.unit_price AS unit_price,
                   {CUSTOMER_LABEL_SQL} AS customer_label,
                   {AGENT_LABEL_SQL} AS agent_label,
                   oir.qty AS qty
            FROM projects.order_inquiry_rows oir
            JOIN projects.so_supply_decisions d
              ON d.id = oir.supply_decision_id AND d.state = :active_state
            JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
            JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
            JOIN sales_orders so ON so.id = sol.sales_order_id
            LEFT JOIN warehouses w ON w.id = sol.warehouse_id
            LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
            LEFT JOIN sales_agents sa ON sa.id = so.sales_agent_id
            WHERE oir.verb = :buy_verb
              AND oir.state = :unplaced_state
              AND oir.qty > 0
              AND sol.product_id::text = :pid
              AND sol.warehouse_id::text = ANY(:members)
              -- Same horizon rule as `demand.horizon_committed_select_sql`'s confirmed
              -- leg: off the inquiry row's own delivery date, not the sheet leg's.
              AND (CAST(:horizon AS date) IS NULL OR oir.delivery_date IS NULL
                   OR oir.delivery_date <= CAST(:horizon AS date))
              {("AND " + co) if co else ""}
        """
        confirmed_params = {
            "pid": rec["product_id"], "members": members, "horizon": horizon,
            "active_state": ACTIVE_DECISION_STATE, "buy_verb": BUY_VERB,
            "unplaced_state": UNPLACED_INQUIRY_STATE, **co_params,
        }
        confirmed_rows = db.execute(text(
            confirmed_base_sql
            + " ORDER BY oir.delivery_date NULLS LAST, so.so_number LIMIT :limit"
        ), {**confirmed_params, "limit": limit_n}).mappings().all()
        confirmed_totals = db.execute(text(
            f"SELECT count(*) AS n, COALESCE(sum(qty), 0) AS qty FROM ({confirmed_base_sql}) t"
        ), confirmed_params).mappings().first()
        confirmed_n = int(confirmed_totals["n"] or 0)
        confirmed_total = float(confirmed_totals["qty"] or 0)

    confirmed_lines = [
        {
            "so_number": r["so_number"],
            "warehouse_code": r["warehouse_code"],
            "is_unlocated": r["warehouse_code"] is None,
            "order_type": r["order_type"],
            "demand_class": PROJECT_CLASS,
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "required_date": r["required_date"].isoformat() if r["required_date"] else None,
            "qty": float(r["qty"] or 0),
            "customer_label": r["customer_label"],
            "agent_label": r["agent_label"],
            "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
            "source": "order_inquiry_confirmed",
            # This leg is BUILT from `projects.order_inquiry_rows` - there is always a row,
            # by construction, unlike the sheet leg's stamp-only `order_inquiry` source.
            "has_inquiry_row": True,
        }
        for r in confirmed_rows
    ]

    all_lines = sorted(
        lines + confirmed_lines,
        key=lambda ln: (ln["required_date"] is None, ln["required_date"] or "",
                        ln["so_number"] or ""),
    )

    # Trailing-window context (captain, 20 Aug follow-up): the past year's project orders /
    # past 3 months' retail orders for THIS product, so the buyer can judge whether to top
    # up the quantity - separate from `committed_total`/`project_total` above, which are the
    # still-OPEN demand this row was netted against, not the historical order flow.
    context = demand_context_for_product(db, rec["product_id"])

    # The order-level evidence behind that same window (21 Aug live ask: "for project,
    # what's the sales order for the past year, who is the customer and agent... for
    # retail, past 3 months, same"). `context` above already carries the number; this is
    # the SAME window (`month_shift`, the identical arithmetic `trajectory_service` uses),
    # fed as a second section rather than folded into `lines` above - the sheet-leg list is
    # OPEN, undelivered demand scoped to this row's own location(s), and the window here is
    # the WHOLE product's order flow regardless of status or location, exactly like
    # `project_12m_qty`/`retail_3m_qty` already are. Two different questions ("what is
    # still owed here" vs "what did we sell of this, everywhere, lately") sharing one
    # response is cheaper than a second endpoint/hook, and honest about which one each
    # section answers. Unclassified has no configured window (S13d), so it stays empty.
    history_lines: list[dict[str, Any]] = []
    if channel in ("project", "retail"):
        as_of = date.today()
        months = context["project_months"] if channel == "project" else context["retail_months"]
        until = month_shift(as_of, 0)
        since = month_shift(until, -months)
        hist_pred = (
            "so.demand_class = :hist_project_class" if channel == "project"
            else "so.demand_class IS DISTINCT FROM :hist_project_class"
        )
        hist_rows = db.execute(text(f"""
            SELECT so.so_number, so.order_date, so.demand_class,
                   sol.qty_ordered AS qty, sol.qty_delivered, sol.unit_price,
                   {CUSTOMER_LABEL_SQL} AS customer_label,
                   {AGENT_LABEL_SQL} AS agent_label
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
            LEFT JOIN sales_agents sa ON sa.id = so.sales_agent_id
            WHERE sol.product_id::text = :pid
              AND so.order_date >= :since AND so.order_date < :until
              AND {hist_pred}
              {("AND " + co) if co else ""}
            ORDER BY so.order_date DESC, so.so_number
            LIMIT :limit
        """), {"pid": rec["product_id"], "since": since, "until": until,
               "hist_project_class": PROJECT_CLASS, "limit": limit_n,
               **co_params}).mappings().all()
        history_lines = [
            {
                "so_number": r["so_number"],
                "order_date": r["order_date"].isoformat() if r["order_date"] else None,
                "demand_class": r["demand_class"],
                "qty": float(r["qty"] or 0),
                # Delivered vs still owed - "clearly separated or marked" (captain, 21
                # Aug), since this section, unlike the sheet leg above, includes both.
                "delivered": bool(
                    r["qty"] and float(r["qty"] or 0) > 0
                    and float(r["qty_delivered"] or 0) >= float(r["qty"] or 0)
                ),
                "customer_label": r["customer_label"],
                "agent_label": r["agent_label"],
                "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
            }
            for r in hist_rows
        ]

    return {
        "lines": all_lines,
        "total": int(totals["n"] or 0) + confirmed_n,
        "shown": len(all_lines),
        # The confirmed leg IS inside `project_committed` (`scm.committed_v`), so it
        # belongs in the same total the sheet leg's committed figure already reports -
        # additive, never a double count (see the module docstring's PROVENANCE note).
        # `confirmed_total` is the UNCAPPED sum (SF-1/SF-2), never `sum(l["qty"] for l in
        # confirmed_lines)`, which would undercount past the display cap.
        "committed_total": float(totals["committed"] or 0) + confirmed_total,
        "unlocated_total": float(totals["unlocated"] or 0),
        # Where the demand actually sits, so "why BRW when I ordered for BRW-IB" is answered
        # by the row itself rather than by opening every order.
        "locations": sorted({(ln["warehouse_code"] or "No location") for ln in all_lines}),
        # Which set of locations the list was drawn from - the row's own warehouse, its
        # pool, or (scope="product") the union across every recommendation this run wrote
        # for the product. Without it a pooled/unioned total reads as this bin's, which is
        # the reading the whole popover exists to correct.
        "scope": rec_scope,
        "pool_code": pool_code,
        # SF-2: read off the UNCAPPED `totals`/`confirmed_total` figures, never off
        # `all_lines` (the capped display set) - past the cap the two diverged. The
        # confirmed leg is entirely project-class by construction (S13b), so its whole
        # uncapped sum lands on `project_total`.
        "project_total": float(totals["project_qty"] or 0) + confirmed_total,
        "retail_total": float(totals["retail_qty"] or 0),
        "unclassified_total": float(totals["unclassified_qty"] or 0),
        "project_12m_qty": context["project_qty"],
        "retail_3m_qty": context["retail_qty"],
        "project_window_months": context["project_months"],
        "retail_window_months": context["retail_months"],
        "demand_context_as_of": context["as_of"],
        # Which channel this list was narrowed to, echoed back so the caller never has to
        # trust its own request state - None means unfiltered (every existing caller).
        "channel": channel,
        # The trailing-window order-history section (see the comment above) - every order
        # PLACED in the window, whatever its status today. Empty when `channel` was not
        # project/retail, or the window carries nothing.
        "history_lines": history_lines,
        "history_shown": len(history_lines),
    }
