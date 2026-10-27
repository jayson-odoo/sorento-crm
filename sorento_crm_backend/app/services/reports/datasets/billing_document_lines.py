"""Billing document LINES: the item side of the one sales calculation (SALES-UNIFIED,
`documentation/plans/sales/PLAN-sales-unified-27oct.md` 2.1, 2.5, 2.6).

One dataset, two readers, so an item figure is computed once:

- the **Top selling items** report (`definitions/top_selling_items.py`), and through it the top
  selling route `crm_top_selling_report` calls on the invoiced basis;
- the chatbot's **report ask** on its `invoiced` basis (`ASK_DEFINITION`, run by
  `app/services/reports/ask.py`), which keys its words (`customer`, `product`, `amount`, `qty`,
  ...) by the same names the order bases use.

Every figure and attribution is `app/services/sales/invoiced_sales.py`'s: the line's net of tax
times the document's rate, negative on a credit note; the agent, debtor type and sales type of
the line's document. A line whose item code is not a CRM product still counts, under its code.
"""
from __future__ import annotations

from typing import Any, List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import aliased

from app.models.finance import BillingDocument, BillingDocumentLine
from app.models.order import Customer
from app.models.product import Brand, Product, ProductCategory
from app.services.error_handler import AppException
from app.services.reports import registry as reg
from app.services.reports.datasets.sales_order_lines import MONTH_OF_YEAR
from app.services.reports.engine import month_label
from app.services.sales import invoiced_sales as inv


def _base(ctx: Any) -> sa.Select:
    return (
        sa.select()
        .select_from(BillingDocumentLine)
        .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
        .outerjoin(Customer, Customer.id == BillingDocument.customer_id)
        .outerjoin(Product, Product.id == BillingDocumentLine.product_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .where(inv.posted())
    )


# ------------------------------------------------------------------------ expressions

_ITEM_CODE = sa.func.coalesce(Product.product_code, sa.func.nullif(sa.func.btrim(BillingDocumentLine.item_code), ""))
_DESCRIPTION = sa.func.coalesce(
    sa.func.nullif(sa.func.btrim(BillingDocumentLine.description), ""), Product.description
)
#: "CODE - Description", the code alone when there is no description.
_ITEM = sa.case(
    (_DESCRIPTION.is_(None), _ITEM_CODE),
    else_=sa.func.concat(_ITEM_CODE, " - ", _DESCRIPTION),
)
_AMOUNT = inv.signed_line_amount()
_QTY = inv.signed_line_quantity()
_MONTH = sa.func.to_char(BillingDocument.doc_date, "YYYY-MM")
_SALES_TYPE = inv.sales_type_label()


# ------------------------------------------------------------------------ filters


def company_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return BillingDocument.company_id == values[0]


def channel_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return inv.sales_type_filter(values)


def customer_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return BillingDocument.customer_id.in_(inv.uuid_values(values, "customer"))


def product_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return BillingDocumentLine.product_id.in_(inv.uuid_values(values, "product"))


def brand_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.brand_id.in_(inv.uuid_values(values, "brand"))


def category_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return Product.category_id.in_(inv.uuid_values(values, "category"))


def agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return inv.agent_condition(values)


def customer_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    """Lines of customers whose assigned agent is one of the values (the report ask's customer
    card link), whoever is on the document."""
    owner = aliased(Customer)
    ids = [v for v in values if v != "none"]
    agent = (
        sa.select(owner.sales_agent_id)
        .where(owner.id == BillingDocument.customer_id)
        .correlate(BillingDocument)
        .scalar_subquery()
    )
    parts = [agent.in_(ids)] if ids else []
    if "none" in values:
        parts.append(sa.and_(BillingDocument.customer_id.isnot(None), agent.is_(None)))
    return sa.or_(*parts) if parts else sa.false()


def debtor_type_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return inv.debtor_type().in_(values)


def location_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    raise AppException(
        status_code=422,
        message="Invoiced sales have no location; ask delivered or ordered sales by location",
        code="location_needs_order_basis",
    )


# ------------------------------------------------------------------------ catalogue

COLUMNS = (
    # The report's own keys.
    reg.Column("item", "Item", "text", "dimension", lambda c: _ITEM, size=320),
    reg.Column("item_code", "Item code", "text", "dimension", lambda c: _ITEM_CODE, size=150),
    reg.Column("debtor_type", "Debtor type", "text", "dimension", lambda c: inv.debtor_type(), size=120),
    reg.Column(
        "year",
        "Year",
        "text",
        "dimension",
        lambda c: sa.cast(sa.cast(sa.extract("year", BillingDocument.doc_date), sa.Integer), sa.Text),
        size=80,
        period_years=True,
    ),
    reg.Column(
        "month_of_year", "Month", "text", "dimension",
        lambda c: sa.func.to_char(BillingDocument.doc_date, "MM"), size=80, fixed_values=MONTH_OF_YEAR,
    ),
    reg.Column(
        "year_month", "Month of the period", "text", "dimension",
        lambda c: _MONTH, size=110, period_months=True, value_label=month_label,
    ),
    reg.Column("quantity", "Qty", "integer", "measure", lambda c: _QTY, size=110),
    reg.Column("sales_value", "RM", "money", "measure", lambda c: _AMOUNT, size=140),
    reg.Column(
        "documents", "Documents", "integer", "measure",
        lambda c: BillingDocument.id, size=110, agg="count_distinct",
    ),
    # The report ask's keys (the order bases' names), on the same expressions.
    reg.Column("customer", "Customer", "text", "dimension",
               lambda c: sa.func.coalesce(Customer.customer_name, BillingDocument.customer_name), size=220),
    reg.Column("product", "Product", "text", "dimension", lambda c: _ITEM_CODE, size=160),
    reg.Column("brand", "Brand", "text", "dimension", lambda c: Brand.brand_name, size=160),
    reg.Column("category", "Category", "text", "dimension", lambda c: ProductCategory.category_name, size=160),
    reg.Column("sales_agent", "Sales agent", "text", "dimension",
               lambda c: sa.func.coalesce(inv.agent_label(), inv.NO_AGENT), size=140),
    reg.Column("location", "Location", "text", "dimension", lambda c: sa.cast(sa.null(), sa.Text), size=120),
    reg.Column("channel", "Channel", "text", "dimension", lambda c: _SALES_TYPE, size=170),
    reg.Column("month", "Month", "text", "dimension", lambda c: _MONTH, size=110),
    reg.Column("all", "All", "text", "dimension", lambda c: sa.cast(sa.literal("all"), sa.Text), size=80),
    reg.Column("amount", "RM", "money", "measure", lambda c: _AMOUNT, size=130),
    reg.Column("qty", "Qty", "integer", "measure", lambda c: _QTY, size=100),
    *(
        reg.Column(
            key, label, "integer", "measure",
            (lambda col: lambda c: sa.case((sa.or_(_QTY != 0, _AMOUNT != 0), col)))(column),
            size=110, agg="count_distinct",
        )
        for key, label, column in (
            ("customers", "Customers", BillingDocument.customer_id),
            ("orders", "Documents", BillingDocument.id),
            ("products", "Products", _ITEM_CODE),
        )
    ),
)

DATASET = reg.Dataset(
    key="billing_document_lines",
    scope="company",
    columns=COLUMNS,
    date_bases=(reg.DateBasis("order_date", "Document date", BillingDocument.doc_date),),
    base=_base,
    company_column=BillingDocument.company_id,
    company_param="company",
    product_id_column=BillingDocumentLine.product_id,
)


def _no_options(db: Any) -> List[Any]:
    return []


#: The report ask's invoiced basis (contract section 7). Registered nowhere, like the order
#: bases' ask definitions: `ask.run_ask` runs it directly.
ASK_DEFINITION = reg.ReportDefinition(
    key="sales_invoiced_ask",
    title="Invoiced sales",
    permission="order_management.orders.view",
    dataset=reg.Dataset(
        key="sales_invoiced_ask",
        scope="company",
        columns=COLUMNS,
        date_bases=DATASET.date_bases,
        base=_base,
        company_column=BillingDocument.company_id,
        product_id_column=BillingDocumentLine.product_id,
    ),
    params=(
        reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
        reg.PeriodParam(key="period", label="Period", default=reg.current_year_period),
        reg.SelectParam("customer", "Customer", True, (), _no_options, customer_condition),
        reg.SelectParam("product", "Product", True, (), _no_options, product_condition),
        reg.SelectParam("brand", "Brand", True, (), _no_options, brand_condition),
        reg.SelectParam("category", "Category", True, (), _no_options, category_condition),
        reg.SelectParam("sales_agent", "Sales agent", True, (), _no_options, agent_condition),
        reg.SelectParam("customer_agent", "Customers assigned to", True, (), _no_options, customer_agent_condition),
        reg.SelectParam("location", "Location", True, (), _no_options, location_condition),
        reg.SelectParam("channel", "Channel", True, (), _no_options, channel_condition),
    ),
    detail=reg.DetailLayout(
        title="Billing document lines",
        order_by=lambda c: [BillingDocument.doc_date.desc(), BillingDocument.doc_no.asc(), BillingDocumentLine.id.asc()],
    ),
    pivot=reg.PivotLayout(title="Invoiced sales"),
    default_view={
        "params": {"date_basis": "order_date"},
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "month", "cols": "all", "measures": ["qty", "amount"]},
    },
    workbook=reg.WorkbookSpec(company_name=""),
    module_key="order_management",
)
reg.validate(ASK_DEFINITION)
