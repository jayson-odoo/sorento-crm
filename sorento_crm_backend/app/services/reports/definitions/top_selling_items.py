"""Top selling items (SALES-UNIFIED, `documentation/plans/sales/PLAN-sales-unified-27oct.md`
2.5): items by invoiced quantity and RM, from billing document LINES, a credit note line
negative. Ranked by RM (the pivot's `__total__` sort), every column sortable.

The top selling route (`/order-management/top-selling`, MCP `crm_top_selling_report`) answers
its invoiced basis by running this definition, and the chatbot's report ask reads the same
dataset (`billing_document_lines.ASK_DEFINITION`), so the three cannot disagree (AC-30).
`customer` and `category` are hidden params: the routes filter by them, the screen does not.
"""
from __future__ import annotations

from datetime import date

from app.models.product import Brand
from app.services.reports import registry as reg
from app.services.reports.datasets import billing_document_lines as bl
from app.services.reports.datasets import sales_order_lines as ds
from app.services.reports.definitions.sales_by_debtor_type import (
    agent_options,
    debtor_type_options,
)
from app.services.sales import invoiced_sales as inv

KEY = "top_selling_items"
PERMISSION = "sales.reports.view"
MODULE_KEY = "sales"


def year_to_date() -> dict:
    today = reg.today_malaysia()
    return {"kind": "custom", "from": date(today.year, 1, 1).isoformat(), "to": today.isoformat()}


def brand_options(db) -> list:
    rows = db.query(Brand.id, Brand.brand_name).all()
    return sorted(((str(i), str(n)) for i, n in rows), key=lambda r: r[1])


def _none(db) -> list:
    return []


def order_by(ctx):
    from app.models.finance import BillingDocument, BillingDocumentLine

    return [BillingDocument.doc_date.desc(), BillingDocument.doc_no.asc(), BillingDocumentLine.id.asc()]


DEFAULT_DETAIL_COLUMNS = ["item", "customer", "sales_agent", "channel", "quantity", "sales_value"]

REPORT = reg.register(
    reg.ReportDefinition(
        key=KEY,
        title="Top selling items",
        permission=PERMISSION,
        module_key=MODULE_KEY,
        dataset=bl.DATASET,
        params=(
            reg.SelectParam(
                key="company", label="Company", multi=False, default=(),
                options=ds.company_options, condition=bl.company_condition, clearable=False,
            ),
            reg.SelectParam(
                key="channel", label="Sales type", multi=True,
                default=tuple(value for value, _label in inv.SALES_TYPES),
                options=lambda db: list(inv.SALES_TYPES),
                condition=bl.channel_condition,
            ),
            reg.SelectParam(
                key="agent", label="Sales agent", multi=True, default=(),
                options=agent_options, condition=bl.agent_condition,
            ),
            reg.SelectParam(
                key="brand", label="Brand", multi=True, default=(),
                options=brand_options, condition=bl.brand_condition,
            ),
            reg.SelectParam(
                key="debtor_type", label="Debtor type", multi=True, default=(),
                options=debtor_type_options, condition=bl.debtor_type_condition,
            ),
            reg.SelectParam(
                key="customer", label="Customer", multi=True, default=(),
                options=_none, condition=bl.customer_condition, hidden=True,
            ),
            reg.SelectParam(
                key="category", label="Category", multi=True, default=(),
                options=_none, condition=bl.category_condition, hidden=True,
            ),
            reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
            reg.PeriodParam(key="period", label="Period", default=year_to_date),
        ),
        detail=reg.DetailLayout(title="Billing document lines", order_by=order_by, cap="truncate"),
        pivot=reg.PivotLayout(title="Items", whole_units=False),
        default_view={
            "params": {
                "date_basis": "order_date",
                "channel": [value for value, _label in inv.SALES_TYPES],
            },
            "detail": {"columns": list(DEFAULT_DETAIL_COLUMNS), "order": list(DEFAULT_DETAIL_COLUMNS)},
            "pivot": {
                "rows": "item",
                "cols": "year",
                # RM first: the summary's Total sort reads the first measure (ranked by RM).
                "measures": ["sales_value", "quantity", "documents"],
                "sort": {"key": "__total__", "dir": "desc"},
            },
        },
        note=lambda ctx: (
            "Invoice, cash sale and debit note lines less credit note lines, excluding tax, by "
            "document date. RM is the line net of tax times the document's exchange rate."
        ),
        opens_on="summary",
        workbook=reg.WorkbookSpec(
            company_name="",
            report_title="TOP SELLING ITEMS",
            month_sheets=False,
            money_format="#,##0.00;(#,##0.00)",
        ),
    )
)
