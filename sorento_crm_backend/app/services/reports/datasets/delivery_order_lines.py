"""Delivered sales: the ONE definition every delivered measure reads (lane DELIVERED-DATE-BASIS,
owner ruling 25 Oct 2026, Q0 (b); `documentation/plans/chatbot/PLAN-delivered-date-basis-25oct.md`).

A delivered quantity is filed by the delivery order (DO) that delivered it. One row per
delivery event, built per run in `_events`:

* **linked**: a live DO line (not cancelled, not deleted, dated, not a replacement `REP...`)
  that resolves to a sales order line, on the DO's own date. The SO line is the line's own
  link (`order_lines.sales_order_line_id`), else the DO header's SO (`orders.sales_order_id`)
  and else the SO the line names (`from_doc_type` SO, `from_doc_no`, same company), each of the
  last two narrowed to that SO's line of the same product (the first by `line_no`, so a line is
  never fanned out). Quantity: the DO line's own, never capped at the ordered quantity.
* **residual**: the part of a live SO line's delivered quantity (`least(qty_delivered,
  qty_ordered)`, the sales report's confirmed qty) that no linked DO line explains, on the SO
  line's own date (`required_date`, else the SO's `order_date`). Old-system DOs carry no SO link,
  so a delivery made before the DO history counts here, as it did before this lane.
* **unlinked**: an AutoCount DO line (`source_book` set) that resolves to no sales order line,
  on the DO's date, at its own total. When its header or doc number still names an SO (one with
  no line of that product), the channel and agent are that SO's; else it is in no channel and has
  no agent. An old-system DO line (`source_book` NULL) that resolves to no SO line is left out:
  its SO's own delivered quantity is the residual above, and its stored totals repeat the DOC
  total on every line, so they are no line amount.

A consignment SO is not a sale (AC-CONSIGN-CRM): neither its DO lines nor its residual count.

The amount of an SO event is the sales report's own per-line rule, `round(line_total x qty /
qty_ordered, 2)` (0 when nothing was ordered); an unlinked DO line's is its own total, to the sen.
Channel and sales agent always come from the SO, so a DO with no header link still has both.

Used by the chatbot's sales report (`sales_report_delivered`), the report ask's delivered basis
(`reports/ask.py`) and the Yearly comparison's Delivered basis (`YEARLY_DATASET`). Not registered
on the Reports screen on its own.
"""
from __future__ import annotations

from typing import Any, List, Optional

import sqlalchemy as sa

from app.models.inventory import Warehouse
from app.models.order import DOC_TYPE_CONSIGNMENT, Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Brand, Product, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services.reports import registry as reg

#: A DO with no sales order, or a sales order with no agent, groups here.
NO_AGENT = "(no agent)"

#: The two channel values the `channel` dimension and filter speak (sales order `demand_class`).
CHANNELS = ("project", "retail")

#: Q2 (owner via crew, 25 Oct 2026, recommendation (a)): the "orders" count on delivered counts
#: delivery orders; a residual (no DO behind it) counts its sales order instead.
ORDERS_COUNT_DELIVERY_ORDERS = True

_SOL = sa.orm.aliased(SalesOrderLine)
_SO = sa.orm.aliased(SalesOrder)


def _first_line_of(so_match: Any) -> Any:
    """The id of the first line (by `line_no`) of the SO `so_match` names, of the DO line's product."""
    return (
        sa.select(_SOL.id)
        .join(_SO, _SO.id == _SOL.sales_order_id)
        .where(so_match, _SOL.product_id == OrderLine.product_id)
        .order_by(_SOL.line_no.asc().nullslast(), _SOL.id.asc())
        .limit(1)
        .scalar_subquery()
    )


_BY_DOC_NUMBER = sa.and_(
    OrderLine.from_doc_type == "SO",
    _SO.so_number == OrderLine.from_doc_no,
    _SO.company_id == OrderLine.company_id,
)

#: The SO line a DO line delivered: line link, then the header's SO, then the doc number.
RESOLVED_SO_LINE = sa.func.coalesce(
    OrderLine.sales_order_line_id,
    _first_line_of(_SO.id == Order.sales_order_id),
    _first_line_of(_BY_DOC_NUMBER),
)

#: The SO a DO line names when no line of its product is on it: the header's, then the doc
#: number's (unique per company and number, so at most one).
NAMED_SO = sa.func.coalesce(Order.sales_order_id, sa.select(_SO.id).where(_BY_DOC_NUMBER).scalar_subquery())


def _fixed_filters() -> List[Any]:
    """The predicates that define which DO lines exist at all (AC-SR-20)."""
    return [
        Order.is_cancelled.is_(False),
        Order.deleted_at.is_(None),
        Order.order_date.isnot(None),
        ~Order.order_number.like("REP%"),
    ]


def _grant_filter(column: Any, ctx: Any) -> List[Any]:
    grants = ctx.company_grants
    if grants is None:
        return []
    if isinstance(grants, frozenset) and grants:
        return [column.in_(sorted(grants))]
    return [sa.false()]


def _prorated(qty: Any) -> Any:
    return sa.func.coalesce(
        sa.func.round(
            sa.func.coalesce(SalesOrderLine.line_total, 0) * qty / sa.func.nullif(SalesOrderLine.qty_ordered, 0), 2
        ),
        0,
    )


def _events(ctx: Any) -> Any:
    """Every delivery event of the run's period, as one subquery. Built once per run (the base,
    the measures and the date basis must read the SAME subquery object)."""
    cached = ctx.__dict__.get("_delivered_events")
    if cached is not None:
        return cached

    start, end = ctx.period.start, ctx.period.end_exclusive
    # Every live DO line of the granted companies, resolved once. Not cut to the period: a
    # residual needs every DO line of its SO line, whatever its date.
    do_lines = (
        sa.select(
            OrderLine.id.label("do_line_id"),
            Order.id.label("do_id"),
            Order.order_date.label("do_date"),
            Order.customer_id.label("do_customer_id"),
            Order.debtor_name.label("debtor_name"),
            Order.source_book.label("source_book"),
            Order.company_id.label("company_id"),
            OrderLine.product_id.label("product_id"),
            OrderLine.warehouse_id.label("warehouse_id"),
            sa.func.coalesce(OrderLine.quantity, 0).label("qty"),
            sa.func.round(sa.func.coalesce(OrderLine.total, 0), 2).label("total"),
            RESOLVED_SO_LINE.label("sol_id"),
            NAMED_SO.label("named_so_id"),
        )
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(*_fixed_filters(), *_grant_filter(Order.company_id, ctx))
        .cte("delivered_do_lines")
    )
    live_so = sa.and_(SalesOrder.doc_type != DOC_TYPE_CONSIGNMENT)
    linked = (
        sa.select(
            do_lines.c.do_date.label("event_date"),
            do_lines.c.qty.label("qty"),
            _prorated(do_lines.c.qty).label("amount"),
            SalesOrderLine.id.label("sol_id"),
            SalesOrder.id.label("so_id"),
            do_lines.c.do_id.label("do_id"),
            SalesOrder.customer_id.label("customer_id"),
            sa.cast(sa.null(), sa.String).label("debtor_name"),
            do_lines.c.product_id.label("product_id"),
            sa.func.coalesce(do_lines.c.warehouse_id, SalesOrderLine.warehouse_id).label("warehouse_id"),
            do_lines.c.company_id.label("company_id"),
        )
        .select_from(do_lines)
        .join(SalesOrderLine, SalesOrderLine.id == do_lines.c.sol_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(live_so, do_lines.c.do_date >= start, do_lines.c.do_date < end)
    )
    explained = (
        sa.select(do_lines.c.sol_id, sa.func.sum(do_lines.c.qty).label("qty"))
        .where(do_lines.c.sol_id.isnot(None))
        .group_by(do_lines.c.sol_id)
        .subquery("delivered_explained")
    )
    line_date = sa.func.coalesce(SalesOrderLine.required_date, SalesOrder.order_date)
    left = sa.func.greatest(
        sa.func.least(SalesOrderLine.qty_delivered, SalesOrderLine.qty_ordered) - sa.func.coalesce(explained.c.qty, 0),
        0,
    )
    residual = (
        sa.select(
            line_date.label("event_date"),
            left.label("qty"),
            _prorated(left).label("amount"),
            SalesOrderLine.id.label("sol_id"),
            SalesOrder.id.label("so_id"),
            sa.cast(sa.null(), SalesOrder.id.type).label("do_id"),
            SalesOrder.customer_id.label("customer_id"),
            sa.cast(sa.null(), sa.String).label("debtor_name"),
            SalesOrderLine.product_id.label("product_id"),
            SalesOrderLine.warehouse_id.label("warehouse_id"),
            SalesOrder.company_id.label("company_id"),
        )
        .select_from(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(explained, explained.c.sol_id == SalesOrderLine.id)
        .where(
            live_so,
            SalesOrder.status != "cancelled",
            SalesOrderLine.line_status != "cancelled",
            line_date >= start,
            line_date < end,
            left > 0,
            *_grant_filter(SalesOrder.company_id, ctx),
        )
    )
    unlinked = (
        sa.select(
            do_lines.c.do_date.label("event_date"),
            do_lines.c.qty.label("qty"),
            do_lines.c.total.label("amount"),
            sa.cast(sa.null(), SalesOrderLine.id.type).label("sol_id"),
            SalesOrder.id.label("so_id"),
            do_lines.c.do_id.label("do_id"),
            sa.func.coalesce(SalesOrder.customer_id, do_lines.c.do_customer_id).label("customer_id"),
            do_lines.c.debtor_name.label("debtor_name"),
            do_lines.c.product_id.label("product_id"),
            do_lines.c.warehouse_id.label("warehouse_id"),
            do_lines.c.company_id.label("company_id"),
        )
        .select_from(do_lines)
        .outerjoin(SalesOrder, SalesOrder.id == do_lines.c.named_so_id)
        .where(
            do_lines.c.sol_id.is_(None),
            sa.or_(SalesOrder.id.is_(None), live_so),
            do_lines.c.source_book.isnot(None),
            do_lines.c.do_date >= start,
            do_lines.c.do_date < end,
        )
    )
    events = sa.union_all(linked, residual, unlinked).subquery("delivered_events")
    ctx.__dict__["_delivered_events"] = events
    return events


def _base(ctx: Any) -> sa.Select:
    ev = _events(ctx)
    return (
        sa.select()
        .select_from(ev)
        .outerjoin(SalesOrder, SalesOrder.id == ev.c.so_id)
        .outerjoin(Order, Order.id == ev.c.do_id)
        .outerjoin(Customer, Customer.id == ev.c.customer_id)
        .outerjoin(Product, Product.id == ev.c.product_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(Warehouse, Warehouse.id == ev.c.warehouse_id)
        .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
    )


def event_date(ctx: Any) -> Any:
    return _events(ctx).c.event_date


# ------------------------------------------------------------------------ filters


def customer_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return _events(ctx).c.customer_id.in_(values)


def product_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return _events(ctx).c.product_id.in_(values)


def brand_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.brand_id.in_(values)


def category_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.category_id.in_(values)


def sales_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    from app.services.reports.datasets.sales_order_lines_ask import _agent_in

    return _agent_in(SalesOrder.sales_agent_id, values)


def customer_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """The customer CARD link (REPORT-DRILLDOWN): events of customers assigned to the agents."""
    from app.services.reports.datasets.sales_order_lines_ask import _agent_in

    return _agent_in(Customer.sales_agent_id, values, owner=Customer.id)


def location_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return _events(ctx).c.warehouse_id.in_(values)


def channel_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """Values are demand classes. An event with no sales order is in no channel (Q1 (a))."""
    return SalesOrder.demand_class.in_(values)


# ------------------------------------------------------------------------ catalog


def _text_date(expr: Any) -> Any:
    return sa.func.to_char(expr, "YYYY-MM-DD")


def _qty(c: Any) -> Any:
    return _events(c).c.qty


def _amount(c: Any) -> Any:
    return _events(c).c.amount


def _order_key(c: Any) -> Any:
    ev = _events(c)
    if ORDERS_COUNT_DELIVERY_ORDERS:
        return sa.func.coalesce(ev.c.do_id, ev.c.so_id)
    return sa.func.coalesce(ev.c.so_id, ev.c.do_id)


def _order_with_agent(c: Any) -> Any:
    """An order (as `_order_key`) whose sales order carries an agent: the fill rate's numerator."""
    return sa.case((SalesOrder.sales_agent_id.isnot(None), _order_key(c)))


#: The count measures (REPORT-SMART-1021): key, label, the id counted.
COUNT_COLUMNS = (
    ("customers", "Customers", lambda c: _events(c).c.customer_id),
    ("orders", "Orders", _order_key),
    ("products", "Products", lambda c: _events(c).c.product_id),
)
#: Q3 (a): the agent fill rate note's numerator, never a measure a caller names.
FILL_COLUMNS = (("orders_with_agent", "Orders with an agent", _order_with_agent),)


def _counted(column: Any) -> Any:
    return lambda c: sa.case((sa.or_(_qty(c) != 0, _amount(c) != 0), column(c)))


def _customer_name(c: Any) -> Any:
    return sa.func.coalesce(Customer.customer_name, sa.func.nullif(sa.func.btrim(_events(c).c.debtor_name), ""))


COLUMNS = (
    reg.Column("customer", "Customer", "text", "dimension", _customer_name, size=220),
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
    reg.Column("channel", "Channel", "text", "dimension", lambda c: SalesOrder.demand_class, size=120),
    reg.Column("day", "Day", "text", "dimension", lambda c: _text_date(c.date_basis), size=110),
    reg.Column(
        "week", "Week", "text", "dimension", lambda c: _text_date(sa.func.date_trunc("week", c.date_basis)), size=110
    ),
    reg.Column("month", "Month", "text", "dimension", lambda c: sa.func.to_char(c.date_basis, "YYYY-MM"), size=110),
    reg.Column("delivery_order", "Delivery order", "text", "dimension", lambda c: Order.order_number, size=140),
    # The one-column side of a one-dimension view. An expression, not a bare constant:
    # Postgres refuses a constant in GROUP BY.
    reg.Column("all", "All", "text", "dimension", lambda c: sa.cast(sa.literal("all"), sa.Text), size=80),
    reg.Column("amount", "RM", "money", "measure", _amount, size=130),
    reg.Column("qty", "Qty", "integer", "measure", _qty, size=100),
    *(
        reg.Column(key, label, "integer", "measure", _counted(column), size=110, agg="count_distinct")
        for key, label, column in COUNT_COLUMNS + FILL_COLUMNS
    ),
)

DATASET = reg.Dataset(
    key="delivery_order_lines",
    scope="company",
    columns=COLUMNS,
    date_bases=(reg.DateBasis("order_date", "Delivered date", event_date),),
    base=_base,
    company_column=sa.literal_column("delivered_events.company_id"),
    product_id_column=sa.literal_column("delivered_events.product_id"),
)


def _no_options(db: Any) -> List[Any]:
    return []


#: The definition the chatbot's sales report and the report ask's delivered basis run (never
#: registered on the Reports screen).
DEFINITION = reg.ReportDefinition(
    key="delivery_order_lines",
    title="Delivered sales",
    permission="order_management.orders.view",
    dataset=DATASET,
    params=(
        reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
        reg.PeriodParam(key="period", label="Period", default=reg.current_year_period),
        reg.SelectParam("customer", "Customer", True, (), _no_options, customer_condition),
        reg.SelectParam("product", "Product", True, (), _no_options, product_condition),
        reg.SelectParam("brand", "Brand", True, (), _no_options, brand_condition),
        reg.SelectParam("category", "Category", True, (), _no_options, category_condition),
        reg.SelectParam("sales_agent", "Sales agent", True, (), _no_options, sales_agent_condition),
        reg.SelectParam("customer_agent", "Customers assigned to", True, (), _no_options, customer_agent_condition),
        reg.SelectParam("location", "Location", True, (), _no_options, location_condition),
        reg.SelectParam("channel", "Channel", True, (), _no_options, channel_condition),
    ),
    detail=reg.DetailLayout(
        title="Delivered lines",
        order_by=lambda c: [c.date_basis.desc(), Order.order_number.desc().nullslast()],
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

reg.validate(DEFINITION)


# ------------------------------------------------------------------------ the Yearly comparison


def _yearly_columns() -> tuple:
    """The order dataset's keys where the meaning is the same (`datasets/sales_order_lines.py`),
    so the Yearly comparison's default and saved views run on Delivered too."""
    from app.services.reports.datasets.sales_order_lines import MONTH_OF_YEAR, channel_label
    from app.services.reports.engine import month_label

    return (
        reg.Column("so_number", "SO no", "text", "text", lambda c: SalesOrder.so_number, size=130),
        reg.Column("do_number", "DO no", "text", "text", lambda c: Order.order_number, size=130),
        reg.Column("order_date", "Delivered date", "date", "date", lambda c: c.date_basis, size=120),
        reg.Column("customer", "Customer", "text", "text", _customer_name, size=220),
        reg.Column("agent_code", "Sales agent code", "text", "text", lambda c: SalesAgent.sales_agent, size=140),
        reg.Column("product_code", "Product", "text", "text", lambda c: Product.product_code, size=160),
        reg.Column("channel", "Channel", "text", "dimension", lambda c: channel_label(SalesOrder.demand_class), size=120),
        reg.Column(
            "year", "Year", "text", "dimension",
            lambda c: sa.cast(sa.cast(sa.extract("year", c.date_basis), sa.Integer), sa.Text),
            size=80, period_years=True,
        ),
        reg.Column(
            "month_of_year", "Month", "text", "dimension", lambda c: sa.func.to_char(c.date_basis, "MM"),
            size=80, fixed_values=MONTH_OF_YEAR,
        ),
        reg.Column(
            "year_month", "Month of the period", "text", "dimension",
            lambda c: sa.func.to_char(sa.func.date_trunc("month", c.date_basis), "YYYY-MM"),
            size=110, period_months=True, value_label=month_label,
        ),
        reg.Column("sales_value", "RM", "money", "measure", _amount, size=130),
        reg.Column("delivered_value", "Delivered RM", "money", "measure", _amount, size=130),
    )


def _yearly_years(db: Any) -> List[int]:
    from app.services.reports.datasets.sales_order_lines import years

    return years(db)


YEARLY_DATASET = reg.Dataset(
    key="delivered_events_yearly",
    scope="company",
    columns=_yearly_columns(),
    date_bases=(reg.DateBasis("order_date", "Delivered date", event_date),),
    base=_base,
    company_column=sa.literal_column("delivered_events.company_id"),
    company_param="company",
    years=_yearly_years,
    product_id_column=sa.literal_column("delivered_events.product_id"),
)


def yearly_channel_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    from app.services.reports.datasets.sales_order_lines import channel_filter

    return channel_filter(SalesOrder.demand_class, values)


def yearly_order_by(ctx: Any) -> List[Any]:
    """Latest delivery first, as the order detail is newest order first."""
    return [ctx.date_basis.desc(), Order.order_number.desc().nullslast(), SalesOrder.so_number.asc()]
