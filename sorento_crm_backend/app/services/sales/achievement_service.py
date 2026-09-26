"""Live achievement of target periods, counted from sales orders at read time (plan 3.2, 16.2).

Nothing is stored: sales orders keep arriving and changing from AutoCount, so a stored figure
would go stale (trigger for a snapshot: plan 3.1). One query per screen covers every period
shown, whatever mix of subjects, metrics, bases and scopes they carry.

**Which lines count for a period.** `sales_order_lines` of a sales order that is not
cancelled, on a line that is not cancelled (the sales report's own predicate), with a non-null
`order_date` (a null date never counts, either basis), inside the target's product scope
(a category counts its sub-categories, through a recursive CTE over `parent_category_id`), and
credited to the subject:

- **An agent** (G2, R2): the order's `sales_agent_id` is the agent or one of their label
  siblings, the visible agents sharing the agent's non-empty `person_label`.
- **A team** (T2, R2): EXISTS a stay of a member in the team whose window covers the order's
  date and whose agent (widened to label siblings) is the order's agent. EXISTS, never a join,
  so an order counts once for a team even when two members share a person label. The window
  always reads the SALES ORDER's date, also for DO-dated quantities.

Both come down to one set of credit rows per period, `(agent_id, valid_from, valid_to)`, built
in Python from the small agent and membership tables and checked with one EXISTS.

**How much a line counts** (`achievement_value_expr`): ordered amount is `line_total`, ordered
quantity `qty_ordered`, both when the order date is in the period. Delivered goes through
`delivered_by_date`: the linked DO quantities dated in the period, counted in DO date order
and capped so a line never counts more than `qty_ordered` in total, plus the residual AutoCount
reports delivered that no linked DO explains, on the order date. Amount delivered is
`round(line_total x delivered / qty_ordered, 2)`, 0 when nothing was ordered, the sales
report's `confirmed_value` exactly while no DO is linked.

**Company.** Every read is an ORM statement run through the session, and the achievement query
also names the company explicitly on every table it reads (`sales_orders`, `sales_order_lines`,
`orders`, `order_lines`, `product_categories`, `sales.target_scope`): the scope listener's
criteria do not reach inside a CTE, so a DO line of another company linked to this company's
sales order line would otherwise count. `any_do_linked` applies the same rule, so the Counts
label and the figures always agree.

**Shape (review round 2, B1).** The DO lines are aggregated once, never per line and period:
`do_counted` gives each linked DO line its capped quantity once; its per-(period, line) sum on
the DO date and its per-line total are unioned with the lines dated in each period and grouped
into one row per (period, line), which then joins the line and its order by primary key. No
correlated subquery reads the DO lines, and nothing crosses every line with every period, so
the plan stays linear even where the planner has no statistics (a freshly filled table).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import (
    Date,
    String,
    Text,
    and_,
    cast,
    case,
    column,
    exists,
    func,
    literal,
    or_,
    select,
    union_all,
    values,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from app.models.order import Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory
from app.models.sales import SalesTargetScope, SalesTeamMember
from app.models.sales_agent import SalesAgent

#: (agent_id, valid_from, valid_to): the orders of `agent_id` dated inside the window count.
Credit = Tuple[str, Optional[date], Optional[date]]

_UUID = UUID(as_uuid=False)


@dataclass
class PeriodSpec:
    """One target period to count, with the credit rows of its subject."""

    period_id: str
    target_id: str
    period_start: date
    period_end: date
    metric: str
    basis: str
    product_scope: str
    credits: List[Credit] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# credit rows: label siblings and dated team membership
# --------------------------------------------------------------------------------------


def label_siblings(db: Session, company_id: str, agent_ids: Iterable[str]) -> Dict[str, Set[str]]:
    """Each agent with the visible agents sharing its non-empty `person_label` (R2), else itself."""
    ids = set(agent_ids)
    if not ids:
        return {}
    visible = or_(SalesAgent.company_id.is_(None), SalesAgent.company_id == company_id)
    agents = db.query(SalesAgent).filter(SalesAgent.id.in_(ids), visible).all()
    labels = {(a.person_label or "").strip() for a in agents} - {""}
    by_label: Dict[str, Set[str]] = {}
    if labels:
        for sibling in db.query(SalesAgent).filter(SalesAgent.person_label.in_(labels), visible):
            by_label.setdefault(sibling.person_label.strip(), set()).add(sibling.id)
    out: Dict[str, Set[str]] = {agent_id: {agent_id} for agent_id in ids}
    for agent in agents:
        label = (agent.person_label or "").strip()
        if label:
            out[agent.id] |= by_label.get(label, set())
    return out


def agent_credits(db: Session, company_id: str, agent_ids: Iterable[str]) -> Dict[str, List[Credit]]:
    """An agent target counts every order of the agent and their label siblings, any date."""
    return {
        agent_id: [(sibling, None, None) for sibling in sorted(siblings)]
        for agent_id, siblings in label_siblings(db, company_id, agent_ids).items()
    }


def team_credits(db: Session, company_id: str, team_ids: Iterable[str]) -> Dict[str, List[Credit]]:
    """A team counts each member's orders (label siblings included) inside each stay (T2)."""
    ids = set(team_ids)
    out: Dict[str, List[Credit]] = {team_id: [] for team_id in ids}
    if not ids:
        return out
    stays = db.query(SalesTeamMember).filter(SalesTeamMember.sales_team_id.in_(ids)).all()
    siblings = label_siblings(db, company_id, {s.sales_agent_id for s in stays})
    for stay in stays:
        for agent_id in sorted(siblings.get(stay.sales_agent_id, {stay.sales_agent_id})):
            out[stay.sales_team_id].append((agent_id, stay.valid_from, stay.valid_to))
    return out


# --------------------------------------------------------------------------------------
# the value of one line in one period
# --------------------------------------------------------------------------------------


def achievement_value_expr(metric: str, basis: str, delivered_qty, line_total=None, qty_ordered=None):
    """What one sales order line adds to a period, by metric and basis (3.2).

    Written once and pinned against `sales_report_service`'s `confirmed_value` by
    `test_value_expr_pinned_to_sales_report`. The ordered cells are gated on the order date
    by the caller; `delivered_qty` already carries its own dating (`delivered_by_date`).
    `line_total` and `qty_ordered` default to the `sales_order_lines` columns; the achievement
    query passes the same columns as carried through its steps.
    """
    line_total = func.coalesce(SalesOrderLine.line_total if line_total is None else line_total, 0)
    qty_ordered = SalesOrderLine.qty_ordered if qty_ordered is None else qty_ordered
    if basis == "ordered":
        return line_total if metric == "amount" else qty_ordered
    if metric == "quantity":
        return delivered_qty
    return func.coalesce(func.round(line_total * delivered_qty / func.nullif(qty_ordered, 0), 2), 0)


def _same_company(col, company_id: str):
    """`col = company_id` for a row reached by its parent's key, compared as text on purpose.

    Written as a plain `=` against a constant, the planner may walk the whole-company index
    instead of the key it was given: on a table without statistics (a freshly filled one) it
    believes that index returns one row, and a DO read crossed every DO line with every DO of
    the company (25.9M rows, 11 s, review round 2). As text it is a filter on rows the key walk
    already reached. Postgres folds `IS NOT DISTINCT FROM` a constant back into `=`, so that
    spelling does not work. Same meaning: the column is a non-null uuid.
    """
    return cast(col, Text) == str(company_id)


# --------------------------------------------------------------------------------------
# the query
# --------------------------------------------------------------------------------------


def achieved_by_period(db: Session, specs: List[PeriodSpec], company_id: str) -> Dict[str, Decimal]:
    """`{period_id: achieved}` for every spec, one statement for all of them.

    Steps (review round 2, B1), each reading a small VALUES, one earlier step once, or an index:
    `agent_lines` (the credited agents' live, dated lines with what the value needs),
    `do_counted` (their linked DO lines with the capped quantity, and the line's columns), then
    one row per (period, line) from three sources grouped together: lines dated in the period,
    DO quantity dated in the period, and all linked DO quantity on the line's own period.
    """
    out: Dict[str, Decimal] = {s.period_id: Decimal("0") for s in specs}
    # An open end becomes the earliest or latest date, never NULL: a NULL in VALUES is untyped
    # text to Postgres, and `text <= date` does not exist.
    credit_rows = [
        (s.period_id, agent_id, valid_from or date.min, valid_to or date.max)
        for s in specs
        for agent_id, valid_from, valid_to in s.credits
    ]
    if not credit_rows:
        return out

    def periods(name: str):
        # One VALUES per use: a VALUES construct cannot be aliased, it renders its own name.
        return values(
            column("period_id", _UUID),
            column("target_id", _UUID),
            column("pstart", Date),
            column("pend", Date),
            column("metric", String),
            column("basis", String),
            column("product_scope", String),
            name=name,
        ).data(
            [
                (s.period_id, s.target_id, s.period_start, s.period_end, s.metric, s.basis, s.product_scope)
                for s in specs
            ]
        )

    credit = values(
        column("period_id", _UUID),
        column("agent_id", _UUID),
        column("valid_from", Date),
        column("valid_to", Date),
        name="credit",
    ).data(credit_rows)
    agent_ids = sorted({row[1] for row in credit_rows})
    delivered = any(s.basis == "delivered" for s in specs)

    # The four order tables are read as tables, not mapped classes: the company rule is named
    # explicitly on each below, and the scope listener's own `company_id IN (...)` on a mapped
    # class is an indexable constant a statistics-less planner walks instead of the key.
    SO, SOL = SalesOrder.__table__.c, SalesOrderLine.__table__.c
    OL, ORD = OrderLine.__table__.c, Order.__table__.c
    # The credited agents' live lines with a date: the sales report's predicate, company first.
    agent_lines = (
        select(
            SOL.id.label("sol_id"),
            SOL.product_id.label("product_id"),
            SOL.qty_ordered.label("qty_ordered"),
            SOL.qty_delivered.label("qty_delivered"),
            SOL.line_total.label("line_total"),
            SO.order_date.label("order_date"),
            SO.sales_agent_id.label("agent_id"),
        )
        .select_from(SalesOrder.__table__)
        .join(SalesOrderLine.__table__, SOL.sales_order_id == SO.id)
        .where(
            SO.company_id == company_id,
            _same_company(SOL.company_id, company_id),
            SO.sales_agent_id.in_(agent_ids),
            SO.status != "cancelled",
            SOL.line_status != "cancelled",
            SO.order_date.isnot(None),
        )
        .cte("agent_lines")
    )
    line_cols = (
        agent_lines.c.product_id,
        agent_lines.c.qty_ordered,
        agent_lines.c.qty_delivered,
        agent_lines.c.line_total,
        agent_lines.c.order_date,
        agent_lines.c.agent_id,
    )

    # Rows of (period, line, line columns..., own, by_do, all_linked). `own` is 1 on the line's
    # order-date period: ordered figures and the delivered residual count there only.
    pb = periods("pb")
    sources = [
        select(
            pb.c.period_id, agent_lines.c.sol_id, *line_cols,
            literal(1).label("own"), literal(0).label("by_do"), literal(0).label("all_linked"),
        )
        .select_from(agent_lines)
        .join(pb, agent_lines.c.order_date.between(pb.c.pstart, pb.c.pend))
    ]
    if delivered:
        # Each linked DO line of those lines with the quantity it counts under the cap:
        # `greatest(least(quantity, qty_ordered - prior), 0)`, `prior` the sum of the line's
        # earlier live DO lines in (DO date nulls last, DO id, line sequence) order, so the
        # first `qty_ordered` units delivered count and the rest counts nowhere (S1-8, S1-26 d).
        # A cancelled or soft-deleted DO counts nothing: its quantity is 0 here rather than
        # filtered out, so the planner walks the DO by its key and never by the cancelled or
        # deleted index (see `_same_company`). Another company's DO never joins.
        live_qty = case(
            (and_(ORD.is_cancelled.is_(False), ORD.deleted_at.is_(None)), OL.quantity), else_=0
        )
        prior = func.sum(live_qty).over(
            partition_by=OL.sales_order_line_id,
            order_by=(ORD.order_date.asc().nullslast(), ORD.id, OL.line_sequence),
            rows=(None, -1),
        )
        do_counted = (
            select(
                agent_lines.c.sol_id,
                *line_cols,
                ORD.order_date.label("do_date"),
                live_qty.label("qty"),
                func.greatest(
                    func.least(live_qty, agent_lines.c.qty_ordered - func.coalesce(prior, 0)), 0
                ).label("counted"),
            )
            .select_from(agent_lines)
            .join(OrderLine.__table__, OL.sales_order_line_id == agent_lines.c.sol_id)
            .join(Order.__table__, ORD.id == OL.order_id)
            .where(
                _same_company(OL.company_id, company_id),
                _same_company(ORD.company_id, company_id),
            )
            .cte("do_counted")
        )
        do_cols = (
            do_counted.c.product_id,
            do_counted.c.qty_ordered,
            do_counted.c.qty_delivered,
            do_counted.c.line_total,
            do_counted.c.order_date,
            do_counted.c.agent_id,
        )
        # The capped DO quantity per (period, line), bucketed by the DO date.
        pd = periods("pd")
        sources.append(
            select(
                pd.c.period_id, do_counted.c.sol_id, *do_cols,
                literal(0), func.sum(do_counted.c.counted), literal(0),
            )
            .select_from(do_counted)
            .join(pd, do_counted.c.do_date.between(pd.c.pstart, pd.c.pend))
            .where(pd.c.basis == "delivered")
            # The line's columns ride along in the key: they are the line's own, one value each.
            .group_by(pd.c.period_id, do_counted.c.sol_id, *do_cols)
        )
        # Every linked DO quantity of the line, whatever its date, on the line's own period
        # (the residual's input).
        linked = (
            select(
                do_counted.c.sol_id, *do_cols,
                func.sum(do_counted.c.qty).label("qty"),
            )
            .group_by(do_counted.c.sol_id, *do_cols)
            .subquery("linked")
        )
        pl = periods("pl")
        sources.append(
            select(
                pl.c.period_id, linked.c.sol_id,
                linked.c.product_id, linked.c.qty_ordered, linked.c.qty_delivered,
                linked.c.line_total, linked.c.order_date, linked.c.agent_id,
                literal(0), literal(0), linked.c.qty,
            )
            .select_from(linked)
            .join(pl, linked.c.order_date.between(pl.c.pstart, pl.c.pend))
            .where(pl.c.basis == "delivered")
        )
    rows = union_all(*sources).subquery("rows")
    pairs = (
        select(
            rows.c.period_id,
            rows.c.sol_id,
            rows.c.product_id,
            rows.c.qty_ordered,
            rows.c.qty_delivered,
            rows.c.line_total,
            rows.c.order_date,
            rows.c.agent_id,
            func.max(rows.c.own).label("own"),
            func.sum(rows.c.by_do).label("by_do"),
            func.sum(rows.c.all_linked).label("all_linked"),
        )
        .group_by(
            rows.c.period_id, rows.c.sol_id, rows.c.product_id, rows.c.qty_ordered,
            rows.c.qty_delivered, rows.c.line_total, rows.c.order_date, rows.c.agent_id,
        )
        .cte("pairs")
    )

    p = periods("p")
    in_period = pairs.c.own == 1
    confirmed = func.least(pairs.c.qty_delivered, pairs.c.qty_ordered)
    residual = case((in_period, func.greatest(confirmed - pairs.c.all_linked, 0)), else_=0)
    delivered_qty = pairs.c.by_do + residual

    def cell(metric: str, basis: str):
        value = achievement_value_expr(
            metric, basis, delivered_qty, pairs.c.line_total, pairs.c.qty_ordered
        )
        if basis == "ordered":
            value = case((in_period, value), else_=0)
        return (and_(p.c.metric == metric, p.c.basis == basis), value)

    value = case(
        cell("amount", "ordered"),
        cell("quantity", "ordered"),
        cell("quantity", "delivered"),
        cell("amount", "delivered"),
        else_=0,
    )

    # The scope's categories and every category below them (a "Basins" target counts
    # "Basins > Countertop"). UNION, not UNION ALL, so a cycle in the tree still terminates.
    target_ids = sorted({s.target_id for s in specs})
    scope_cat = (
        select(
            SalesTargetScope.target_id.label("target_id"),
            SalesTargetScope.product_category_id.label("category_id"),
        )
        .where(
            SalesTargetScope.target_id.in_(target_ids),
            SalesTargetScope.company_id == company_id,
            SalesTargetScope.product_category_id.isnot(None),
        )
        .cte("scope_cat", recursive=True)
    )
    scope_cat = scope_cat.union(
        select(scope_cat.c.target_id, ProductCategory.id)
        .join(ProductCategory, ProductCategory.parent_category_id == scope_cat.c.category_id)
        .where(ProductCategory.company_id == company_id)
    )

    credited = exists().where(
        credit.c.period_id == p.c.period_id,
        credit.c.agent_id == pairs.c.agent_id,
        pairs.c.order_date.between(credit.c.valid_from, credit.c.valid_to),
    )
    in_scope = or_(
        p.c.product_scope == "all",
        and_(
            p.c.product_scope == "categories",
            exists().where(
                scope_cat.c.target_id == p.c.target_id,
                Product.id == pairs.c.product_id,
                Product.category_id == scope_cat.c.category_id,
            ),
        ),
        and_(
            p.c.product_scope == "products",
            exists().where(
                SalesTargetScope.target_id == p.c.target_id,
                SalesTargetScope.company_id == company_id,
                SalesTargetScope.product_id == pairs.c.product_id,
            ),
        ),
    )

    stmt = (
        select(p.c.period_id, func.sum(value))
        .select_from(pairs)
        .join(p, p.c.period_id == pairs.c.period_id)
        .where(credited, in_scope)
        .group_by(p.c.period_id)
    )
    for period_id, total in db.execute(stmt).all():
        out[str(period_id)] = Decimal(total or 0)
    return out


def unassigned_amount(db: Session, on: date, company_id: str) -> Decimal:
    """Ordered amount with no agent, in the calendar month of `on` (S1-14)."""
    month_start = on.replace(day=1)
    next_month = date(on.year + (on.month == 12), on.month % 12 + 1, 1)
    total = db.execute(
        select(func.coalesce(func.sum(func.coalesce(SalesOrderLine.line_total, 0)), 0))
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.company_id == company_id,
            SalesOrderLine.company_id == company_id,
            SalesOrder.sales_agent_id.is_(None),
            SalesOrder.status != "cancelled",
            SalesOrderLine.line_status != "cancelled",
            SalesOrder.order_date >= month_start,
            SalesOrder.order_date < next_month,
        )
    ).scalar()
    return Decimal(total or 0)


def any_do_linked(db: Session, company_id: str) -> bool:
    """True once any live DO line of the company is linked to one of its sales order lines.

    The same company rule the achievement query applies to DO lines, so the Counts label reads "by DO date"
    exactly when a DO line can count.
    """
    return bool(
        db.execute(
            select(literal(True))
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .join(SalesOrderLine, SalesOrderLine.id == OrderLine.sales_order_line_id)
            .where(
                OrderLine.company_id == company_id,
                Order.company_id == company_id,
                SalesOrderLine.company_id == company_id,
                Order.is_cancelled.is_(False),
                Order.deleted_at.is_(None),
            )
            .limit(1)
        ).scalar()
    )


def achieved_pct(achieved: Optional[Decimal], target: Optional[Decimal]) -> Optional[float]:
    """round(achieved / target x 100, 1); None with no target or a target of 0."""
    if achieved is None or target is None or Decimal(target) == 0:
        return None
    return float(round(Decimal(achieved) / Decimal(target) * 100, 1))
