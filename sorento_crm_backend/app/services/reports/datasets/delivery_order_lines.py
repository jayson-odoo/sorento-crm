"""The rows behind the chatbot's sales report: every delivered DO line (lane SALES-REPORT,
PR #1401; `documentation/plans/chatbot/PLAN-chatbot-selfref-scope-30sep.md`, "Design note:
one dimension/measure model"; UAC AC-SR-20 to AC-SR-22).

One row per `order_lines` row of a delivery order (`orders`) that is not cancelled, not
deleted, dated, and not a replacement DO (number `REP...`). Filed by the DO's own date
(`orders.order_date`).

**The amount is computed once, per line, in a base subquery**, so every grouping (customer,
product, period, DO, sales agent) sums to the same Total to the sen:

* an AutoCount DO (`source_book` set, `db1`) carries its own line totals: a line's amount is
  its own `total`;
* a legacy import (`source_book` NULL) repeats the DOC total on every line: the DO counts it
  ONCE, split across its lines by weight qty x unit price x (1 - discount), in equal shares
  when every weight is 0. The split is rounded by cumulative rounding (each line takes the
  rounded running total minus the rounded running total before it), so the shares sum to
  the DOC total exactly, the last sen included;
* a legacy DO whose lines carry MORE THAN ONE distinct total is not a repeated DOC total
  (owner ruling, PR #1401 fix round 1; rule a2, fix round 2): each line is the LESSER of its
  own qty x unit price x (1 - discount), rounded to the sen, and its stored total (none
  stored = the line math). The discount is normalised first (`discount_fraction`).

The DO-level filters a run names (its customers, its window, its company grant) are pushed
into that subquery as well: a share is a fraction of its whole DO, so only a filter that
keeps or drops a WHOLE DO may go there. Product, location and channel filters (per line) stay outside.

Not registered on the Reports screen (`reg.register`): the chatbot's sales report runs this
definition directly (`sales_report_service.delivered_sales_report`). Trigger for the screen:
the owner wants it there.
"""
from __future__ import annotations

import dataclasses
from typing import Any, List, Optional

import sqlalchemy as sa

from app.models.inventory import Warehouse
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Brand, Product, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services.reports import ask_params as ap
from app.services.reports import registry as reg

#: A DO with no sales order, or a sales order with no agent, groups here.
NO_AGENT = "(no agent)"

#: The two channel values the `channel` dimension and filter speak (sales order `demand_class`).
CHANNELS = ("project", "retail", "other")

_LINE_SO = sa.orm.aliased(SalesOrder)
_LINE_SOL = sa.orm.aliased(SalesOrderLine)
_DOC_SO = sa.orm.aliased(SalesOrder)

#: The line's sales order class, by the line link (sales order line -> sales order).
_BY_LINE_LINK = (
    sa.select(_LINE_SO.demand_class)
    .select_from(_LINE_SOL)
    .join(_LINE_SO, _LINE_SO.id == _LINE_SOL.sales_order_id)
    .where(_LINE_SOL.id == OrderLine.sales_order_line_id)
    .scalar_subquery()
)

#: The same, by the doc number the line says it came from (unique per company and number,
#: so at most one sales order matches and the line is never fanned out).
_BY_DOC_NUMBER = (
    sa.select(_DOC_SO.demand_class)
    .where(
        OrderLine.from_doc_type == "SO",
        _DOC_SO.so_number == OrderLine.from_doc_no,
        _DOC_SO.company_id == OrderLine.company_id,
    )
    .scalar_subquery()
)

#: A DO line's channel is its sales order's `demand_class` (line link, then the DO header's
#: link, then the doc number), `project` / `retail`, or NULL when no sales order is found.
CHANNEL_EXPR = sa.func.coalesce(_BY_LINE_LINK, SalesOrder.demand_class, _BY_DOC_NUMBER)


#: The pending-delivery variant (REPORT-UNIFY): the same DO lines, only those of a DO not yet delivered.
PENDING_KEY = "delivery_order_lines_pending"


def _fixed_filters(ctx: Any) -> List[Any]:
    """The predicates that define which DO lines exist at all (AC-SR-20); the pending variant
    adds `order_service`'s own "not delivered" predicate (a delivered status with no date is NOT
    delivered)."""
    preds: List[Any] = [
        Order.is_cancelled.is_(False),
        Order.deleted_at.is_(None),
        Order.order_date.isnot(None),
        ~Order.order_number.like("REP%"),
    ]
    if ctx.definition.key == PENDING_KEY:
        from app.services import order_service

        pending = order_service._outstanding_clause(order_service._delivered_status_ids(ctx.db))
        if pending is not None:
            preds.append(pending)
    return preds


def _do_level_filters(ctx: Any) -> List[Any]:
    """The run's filters that keep or drop a WHOLE DO, safe to apply before the split."""
    preds: List[Any] = [
        Order.order_date >= ctx.period.start,
        Order.order_date < ctx.period.end_exclusive,
    ]
    customers = ctx.values.get("customer") or []
    if customers:
        preds.append(Order.customer_id.in_(customers))
    grants = ctx.company_grants
    if grants is None:
        pass
    elif isinstance(grants, frozenset) and grants:
        preds.append(Order.company_id.in_(sorted(grants)))
    else:
        preds.append(sa.false())
    return preds


def discount_fraction() -> Any:
    """A line's discount as a fraction 0..1. The column is mostly a fraction, but some rows
    store a percent (real data: three lines carry 100.0000), so a value above 1 is read as a
    percent (100 -> 1.0, 37 -> 0.37), then clamped to 0..1."""
    raw = sa.func.coalesce(OrderLine.discount, 0)
    fraction = sa.case((raw > 1, raw / 100), else_=raw)
    return sa.func.least(sa.func.greatest(fraction, 0), 1)


def _line_amounts(ctx: Any) -> Any:
    """Each DO line's amount, as a subquery keyed by the line id. Built once per run (the
    base and the `amount` measure must read the SAME subquery object)."""
    cached = ctx.__dict__.get("_delivery_order_line_amounts")
    if cached is not None:
        return cached

    partition = (OrderLine.order_id,)
    weight = (
        sa.func.coalesce(OrderLine.quantity, 0)
        * sa.func.coalesce(OrderLine.unit_price, 0)
        * (1 - discount_fraction())
    )
    lines = (
        sa.select(
            OrderLine.id.label("line_id"),
            OrderLine.order_id.label("order_id"),
            OrderLine.line_sequence.label("line_sequence"),
            Order.source_book.label("source_book"),
            sa.func.coalesce(OrderLine.total, 0).label("line_total"),
            OrderLine.total.label("stored_total"),
            weight.label("weight"),
            sa.func.coalesce(sa.func.max(OrderLine.total).over(partition_by=partition), 0).label("doc_total"),
            # Postgres has no COUNT(DISTINCT) window: min <> max is "more than one total".
            (
                sa.func.min(OrderLine.total).over(partition_by=partition)
                != sa.func.max(OrderLine.total).over(partition_by=partition)
            ).label("mixed_totals"),
            sa.func.sum(weight).over(partition_by=partition).label("weight_sum"),
            sa.func.count().over(partition_by=partition).label("line_count"),
        )
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(sa.and_(*_fixed_filters(ctx), *_do_level_filters(ctx)))
        .subquery("do_lines")
    )
    share = sa.case(
        (lines.c.weight_sum > 0, lines.c.doc_total * lines.c.weight / lines.c.weight_sum),
        else_=lines.c.doc_total / lines.c.line_count,
    )
    running = sa.func.sum(share).over(
        partition_by=lines.c.order_id,
        order_by=(lines.c.line_sequence, lines.c.line_id),
        rows=(None, 0),
    )
    amount = sa.case(
        (lines.c.source_book.isnot(None), sa.func.round(lines.c.line_total, 2)),
        # A legacy DO whose lines carry more than one distinct total is not one repeated DOC
        # total (owner ruling, fix round 1 S1; rule a2, fix round 2): each line is the lesser
        # of its own qty x price x (1 - discount), rounded to the sen, and its stored total
        # (none stored = the line math). Nothing is split.
        (
            lines.c.mixed_totals.is_(True),
            sa.func.least(
                sa.func.round(lines.c.weight, 2),
                sa.func.coalesce(sa.func.round(lines.c.stored_total, 2), sa.func.round(lines.c.weight, 2)),
            ),
        ),
        else_=sa.func.round(running, 2) - sa.func.round(running - share, 2),
    )
    subquery = sa.select(lines.c.line_id, amount.label("amount")).subquery("do_line_amounts")
    ctx.__dict__["_delivery_order_line_amounts"] = subquery
    return subquery


def _base(ctx: Any) -> sa.Select:
    amounts = _line_amounts(ctx)
    return (
        sa.select()
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .join(amounts, amounts.c.line_id == OrderLine.id)
        .outerjoin(Customer, Customer.id == Order.customer_id)
        .outerjoin(Product, Product.id == OrderLine.product_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(Warehouse, Warehouse.id == OrderLine.warehouse_id)
        .outerjoin(SalesOrder, SalesOrder.id == Order.sales_order_id)
        .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
        .where(sa.and_(*_fixed_filters(ctx)))
    )


# ------------------------------------------------------------------------ filters


def customer_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Order.customer_id.in_(values)


def product_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return OrderLine.product_id.in_(values)


def brand_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """Per line (the product's brand), so it stays out of `_do_level_filters`."""
    return Product.brand_id.in_(values)


def category_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.category_id.in_(values)


def sales_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return SalesOrder.sales_agent_id.in_(values)


def location_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return OrderLine.warehouse_id.in_(values)


def channel_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """Per line (its sales order's class); a line with no sales order is in no channel."""
    return CHANNEL_EXPR.in_(values)


# ------------------------------------------------------------------------ catalog


def _text_date(expr: Any) -> Any:
    return sa.func.to_char(expr, "YYYY-MM-DD")


COLUMNS = (
    reg.Column("customer", "Customer", "text", "dimension", lambda c: sa.func.coalesce(Customer.customer_name, sa.func.nullif(sa.func.btrim(Order.debtor_name), "")), size=220),
    reg.Column("product", "Product", "text", "dimension", lambda c: Product.product_code, size=160),
    reg.Column("brand", "Brand", "text", "dimension", lambda c: Brand.brand_name, size=160),
    reg.Column("category", "Category", "text", "dimension", lambda c: ProductCategory.category_name, size=160),
    reg.Column(
        "sales_agent",
        "Sales agent",
        "text",
        "dimension",
        lambda c: sa.func.coalesce(SalesAgent.sales_agent, NO_AGENT),
        size=140,
    ),
    reg.Column("location", "Location", "text", "dimension", lambda c: Warehouse.warehouse_code, size=120),
    reg.Column("channel", "Channel", "text", "dimension", lambda c: CHANNEL_EXPR, size=120),
    reg.Column("day", "Day", "text", "dimension", lambda c: _text_date(Order.order_date), size=110),
    reg.Column(
        "week",
        "Week",
        "text",
        "dimension",
        lambda c: _text_date(sa.func.date_trunc("week", Order.order_date)),
        size=110,
    ),
    reg.Column("month", "Month", "text", "dimension", lambda c: sa.func.to_char(Order.order_date, "YYYY-MM"), size=110),
    reg.Column("delivery_order", "Delivery order", "text", "dimension", lambda c: Order.order_number, size=140),
    # The one-column side of a one-dimension view. An expression, not a bare constant:
    # Postgres refuses a constant in GROUP BY.
    reg.Column("all", "All", "text", "dimension", lambda c: sa.cast(sa.literal("all"), sa.Text), size=80),
    reg.Column("amount", "RM", "money", "measure", lambda c: _line_amounts(c).c.amount, size=130),
    reg.Column("qty", "Qty", "integer", "measure", lambda c: OrderLine.quantity, size=100),
)

DATASET = reg.Dataset(
    key="delivery_order_lines",
    scope="company",
    columns=COLUMNS,
    date_bases=(reg.DateBasis("order_date", "DO date", Order.order_date),),
    base=_base,
    company_column=Order.company_id,
    product_id_column=OrderLine.product_id,
)


def _no_options(db: Any) -> List[Any]:
    return []


#: The definition the chatbot's sales report runs (never registered on the Reports screen).
DEFINITION = reg.ReportDefinition(
    key="delivery_order_lines",
    title="Delivered sales",
    permission="order_management.orders.view",
    dataset=DATASET,
    params=(
        reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
        reg.PeriodParam(key="period", label="Period", default=reg.current_year_period),
        reg.SelectParam("customer", "Customer", True, (), ap.customer_options, customer_condition),
        reg.SelectParam("product", "Product", True, (), _no_options, product_condition, hidden=True),
        reg.SelectParam("brand", "Brand", True, (), ap.brand_options, brand_condition),
        reg.SelectParam("category", "Category", True, (), ap.category_options, category_condition),
        reg.SelectParam("sales_agent", "Sales agent", True, (), ap.agent_options, sales_agent_condition),
        reg.SelectParam("location", "Location", True, (), _no_options, location_condition, hidden=True),
        reg.SelectParam("channel", "Channel", True, (), _no_options, channel_condition, hidden=True),
        reg.SelectParam("spec", "Specification", True, (), ap.spec_options, ap.spec_condition),
    ),
    detail=reg.DetailLayout(
        title="Delivery order lines",
        order_by=lambda c: [Order.order_date.desc(), Order.order_number.desc(), OrderLine.line_sequence.asc()],
    ),
    pivot=reg.PivotLayout(title="Delivered sales"),
    default_view={
        "params": {"date_basis": "order_date"},
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "month", "cols": "all", "measures": ["qty", "amount"]},
    },
    workbook=reg.WorkbookSpec(company_name=""),
    module_key="order_management",
)

#: Delivery order lines of DOs not yet delivered: the chatbot's `pending_delivery` basis, also registered on the
#: "Sales & outstanding" screen (`definitions/sales_and_outstanding`). The columns, base and params are the delivered ones.
PENDING_DATASET = dataclasses.replace(DATASET, key=PENDING_KEY)
PENDING_DEFINITION = dataclasses.replace(
    DEFINITION, key=PENDING_KEY, title="Pending delivery", dataset=PENDING_DATASET,
    # An open basis: with no period named it counts every date, as the chatbot does.
    params=tuple(
        dataclasses.replace(p, default=reg.all_dates_period) if p.key == "period" else p for p in DEFINITION.params
    ),
    pivot=reg.PivotLayout(title="Pending delivery"),
)

reg.validate(DEFINITION)
reg.validate(PENDING_DEFINITION)
