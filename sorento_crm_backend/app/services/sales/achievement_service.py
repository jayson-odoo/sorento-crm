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

Every read is an ORM statement over mapped classes run through the session, so the company
scope listener adds its predicate (`sales_report_service`'s rule).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import Date, String, and_, case, column, exists, func, literal, or_, select, values
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


def achievement_value_expr(metric: str, basis: str, delivered_qty):
    """What one sales order line adds to a period, by metric and basis (3.2).

    Written once and pinned against `sales_report_service`'s `confirmed_value` by
    `test_value_expr_pinned_to_sales_report`. The ordered cells are gated on the order date
    by the caller; `delivered_qty` already carries its own dating (`delivered_by_date`).
    """
    line_total = func.coalesce(SalesOrderLine.line_total, 0)
    if basis == "ordered":
        return line_total if metric == "amount" else SalesOrderLine.qty_ordered
    if metric == "quantity":
        return delivered_qty
    return func.coalesce(
        func.round(line_total * delivered_qty / func.nullif(SalesOrderLine.qty_ordered, 0), 2), 0
    )


def _do_lines_cte(agent_ids: Set[str]):
    """Linked, live DO lines with the quantity each one counts under the running-sum cap.

    `counted = greatest(least(quantity, qty_ordered - prior), 0)`, `prior` being the sum of the
    line's earlier DO lines in (DO date nulls last, DO id, line sequence) order, so the first
    `qty_ordered` units delivered count and the rest counts nowhere (S1-8, S1-26 d). Limited to
    the credited agents' sales orders, so the window never ranges over the whole DO book.
    """
    prior = func.sum(OrderLine.quantity).over(
        partition_by=OrderLine.sales_order_line_id,
        order_by=(Order.order_date.asc().nullslast(), Order.id, OrderLine.line_sequence),
        rows=(None, -1),
    )
    counted = func.greatest(
        func.least(OrderLine.quantity, SalesOrderLine.qty_ordered - func.coalesce(prior, 0)), 0
    )
    return (
        select(
            OrderLine.sales_order_line_id.label("sol_id"),
            Order.order_date.label("do_date"),
            OrderLine.quantity.label("qty"),
            counted.label("counted"),
        )
        .join(Order, Order.id == OrderLine.order_id)
        .join(SalesOrderLine, SalesOrderLine.id == OrderLine.sales_order_line_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            OrderLine.sales_order_line_id.isnot(None),
            Order.is_cancelled.is_(False),
            Order.deleted_at.is_(None),
            SalesOrder.sales_agent_id.in_(agent_ids),
        )
        .cte("do_lines")
    )


# --------------------------------------------------------------------------------------
# the query
# --------------------------------------------------------------------------------------


def achieved_by_period(db: Session, specs: List[PeriodSpec]) -> Dict[str, Decimal]:
    """`{period_id: achieved}` for every spec, one statement for all of them."""
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

    p = values(
        column("period_id", _UUID),
        column("target_id", _UUID),
        column("pstart", Date),
        column("pend", Date),
        column("metric", String),
        column("basis", String),
        column("product_scope", String),
        name="p",
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

    target_ids = sorted({s.target_id for s in specs})
    # The scope's categories and every category below them (a "Basins" target counts
    # "Basins > Countertop"). UNION, not UNION ALL, so a cycle in the tree still terminates.
    scope_cat = (
        select(
            SalesTargetScope.target_id.label("target_id"),
            SalesTargetScope.product_category_id.label("category_id"),
        )
        .where(
            SalesTargetScope.target_id.in_(target_ids),
            SalesTargetScope.product_category_id.isnot(None),
        )
        .cte("scope_cat", recursive=True)
    )
    scope_cat = scope_cat.union(
        select(scope_cat.c.target_id, ProductCategory.id).join(
            ProductCategory, ProductCategory.parent_category_id == scope_cat.c.category_id
        )
    )

    in_period = SalesOrder.order_date.between(p.c.pstart, p.c.pend)
    agent_ids = {row[1] for row in credit_rows}
    delivered = any(s.basis == "delivered" for s in specs)

    if delivered:
        do_lines = _do_lines_cte(agent_ids)
        by_do = (
            select(func.coalesce(func.sum(do_lines.c.counted), 0))
            .where(
                do_lines.c.sol_id == SalesOrderLine.id,
                do_lines.c.do_date.between(p.c.pstart, p.c.pend),
            )
            .scalar_subquery()
        )
        all_linked = (
            select(func.coalesce(func.sum(do_lines.c.qty), 0))
            .where(do_lines.c.sol_id == SalesOrderLine.id)
            .scalar_subquery()
        )
        confirmed = func.least(SalesOrderLine.qty_delivered, SalesOrderLine.qty_ordered)
        residual = case((in_period, func.greatest(confirmed - all_linked, 0)), else_=0)
        delivered_qty = by_do + residual
        candidate = or_(
            in_period,
            and_(
                p.c.basis == "delivered",
                exists().where(
                    do_lines.c.sol_id == SalesOrderLine.id,
                    do_lines.c.do_date.between(p.c.pstart, p.c.pend),
                ),
            ),
        )
    else:
        delivered_qty = literal(0)
        candidate = in_period

    def cell(metric: str, basis: str):
        value = achievement_value_expr(metric, basis, delivered_qty)
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

    credited = exists().where(
        credit.c.period_id == p.c.period_id,
        credit.c.agent_id == SalesOrder.sales_agent_id,
        SalesOrder.order_date.between(credit.c.valid_from, credit.c.valid_to),
    )
    in_scope = or_(
        p.c.product_scope == "all",
        and_(
            p.c.product_scope == "categories",
            exists()
            .where(
                scope_cat.c.target_id == p.c.target_id,
                Product.id == SalesOrderLine.product_id,
                Product.category_id == scope_cat.c.category_id,
            ),
        ),
        and_(
            p.c.product_scope == "products",
            exists().where(
                SalesTargetScope.target_id == p.c.target_id,
                SalesTargetScope.product_id == SalesOrderLine.product_id,
            ),
        ),
    )

    stmt = (
        select(p.c.period_id, func.sum(value))
        .select_from(p)
        .join(SalesOrderLine, literal(True))
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.status != "cancelled",
            SalesOrderLine.line_status != "cancelled",
            SalesOrder.order_date.isnot(None),
            SalesOrder.sales_agent_id.in_(agent_ids),
            credited,
            in_scope,
            candidate,
        )
        .group_by(p.c.period_id)
    )
    for period_id, total in db.execute(stmt).all():
        out[str(period_id)] = Decimal(total or 0)
    return out


def unassigned_amount(db: Session, on: date) -> Decimal:
    """Ordered amount with no agent, in the calendar month of `on` (S1-14)."""
    month_start = on.replace(day=1)
    next_month = date(on.year + (on.month == 12), on.month % 12 + 1, 1)
    total = db.execute(
        select(func.coalesce(func.sum(func.coalesce(SalesOrderLine.line_total, 0)), 0))
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.sales_agent_id.is_(None),
            SalesOrder.status != "cancelled",
            SalesOrderLine.line_status != "cancelled",
            SalesOrder.order_date >= month_start,
            SalesOrder.order_date < next_month,
        )
    ).scalar()
    return Decimal(total or 0)


def any_do_linked(db: Session) -> bool:
    """True once any DO line of the company is linked to a sales order line (counts label)."""
    return bool(
        db.execute(
            select(literal(True)).select_from(OrderLine).where(
                OrderLine.sales_order_line_id.isnot(None)
            ).limit(1)
        ).scalar()
    )


def achieved_pct(achieved: Optional[Decimal], target: Optional[Decimal]) -> Optional[float]:
    """round(achieved / target x 100, 1); None with no target or a target of 0."""
    if achieved is None or target is None or Decimal(target) == 0:
        return None
    return float(round(Decimal(achieved) / Decimal(target) * 100, 1))
