"""The ordered basis of the chatbot's report ask (lane REPORT-ENGINE, slice 1a;
`documentation/plans/chatbot/PLAN-report-engine.md` section 0 and section 10).

Sales order lines filed by the SO's own date, over `sales_order_lines._base` (so a cancelled
order or line is out, exactly as the Yearly comparison has it) with the product's brand and
category and the line's warehouse joined on. The amount is the Yearly comparison's ordered
value and the qty its ordered qty, both imported from `sales_report_service._per_line_exprs`,
never rewritten here.

Registered NOWHERE (no `reg.register`): the Reports screen's Yearly comparison catalogue does
not change. `ask.run_ask` runs this definition directly.
"""
from __future__ import annotations

from typing import Any, List, Optional

import sqlalchemy as sa

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Brand, Product, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services.reports import registry as reg
from app.services.reports.datasets import sales_order_lines
from app.services.reports.datasets.delivery_order_lines import NO_AGENT
from app.services.reports.datasets.sales_order_lines import channel_label
from app.services.sales_report_service import _per_line_exprs


def _base(ctx: Any) -> sa.Select:
    return (
        sales_order_lines._base(ctx)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
    )


# ------------------------------------------------------------------------ filters


def _no_options(db: Any) -> List[Any]:
    return []


def customer_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return SalesOrder.customer_id.in_(values)


def product_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return SalesOrderLine.product_id.in_(values)


def brand_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.brand_id.in_(values)


def category_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.category_id.in_(values)


def sales_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return SalesOrder.sales_agent_id.in_(values)


def location_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return SalesOrderLine.warehouse_id.in_(values)


def channel_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """Values are demand classes (`retail` / `project`), the words the delivered basis speaks."""
    return SalesOrder.demand_class.in_(values)


# ------------------------------------------------------------------------ catalog

COLUMNS = (
    reg.Column("customer", "Customer", "text", "dimension", lambda c: Customer.customer_name, size=220),
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
    reg.Column(
        "channel", "Channel", "text", "dimension", lambda c: channel_label(SalesOrder.demand_class), size=120
    ),
    reg.Column("month", "Month", "text", "dimension", lambda c: sa.func.to_char(SalesOrder.order_date, "YYYY-MM"), size=110),
    reg.Column("all", "All", "text", "dimension", lambda c: sa.cast(sa.literal("all"), sa.Text), size=80),
    reg.Column("amount", "RM", "money", "measure", lambda c: _per_line_exprs()["ordered_value"], size=130),
    reg.Column("qty", "Qty", "integer", "measure", lambda c: _per_line_exprs()["ordered_qty"], size=100),
)

DATASET = reg.Dataset(
    key="sales_order_lines_ask",
    scope="company",
    columns=COLUMNS,
    date_bases=(reg.DateBasis("order_date", "SO date", SalesOrder.order_date),),
    base=_base,
    company_column=SalesOrder.company_id,
)

DEFINITION = reg.ReportDefinition(
    key="sales_order_lines_ask",
    title="Ordered sales",
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
        reg.SelectParam("location", "Location", True, (), _no_options, location_condition),
        reg.SelectParam("channel", "Channel", True, (), _no_options, channel_condition),
    ),
    detail=reg.DetailLayout(
        title="Sales order lines",
        order_by=lambda c: [SalesOrder.order_date.desc(), SalesOrder.so_number.asc(), SalesOrderLine.id.asc()],
    ),
    pivot=reg.PivotLayout(title="Ordered sales"),
    default_view={
        "params": {"date_basis": "order_date"},
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "month", "cols": "all", "measures": ["qty", "amount"]},
    },
    workbook=reg.WorkbookSpec(company_name=""),
    module_key="order_management",
)

reg.validate(DEFINITION)
