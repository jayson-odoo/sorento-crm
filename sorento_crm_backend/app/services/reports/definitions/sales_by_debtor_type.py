"""Sales by debtor type (SALES-UNIFIED, `documentation/plans/sales/PLAN-sales-unified-27oct.md`
2.5): the AutoCount "Weekly Sales by Debtor Type by Sales Agent" report on the reports kernel.

Agents down, the customers' AutoCount debtor types across, one block per sales type (Dealer,
Project team, Set apart, Mixed, Type not set, No sales order) through the kernel's own
`sheet_per`, so with every type ticked the blocks add up to all sales (owner ruling 27 Oct
16:3x: nothing hidden). The AutoCount report's own total is the same run with the last three
types unticked. Sorento and Mocha are the same report: the company setting decides whose agent
a sale is (`invoiced_sales.agent_id`), and the columns are whatever types the period carries.

Every figure is the billing dataset's, so the chatbot's `crm_sales_analysis` (rows `agent`,
cols `debtor_type`) runs this definition and cannot disagree with the screen (AC-30).
"""
from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services.reports import registry as reg
from app.services.reports.datasets import billing_documents as bd
from app.services.reports.datasets import sales_order_lines as ds
from app.services.sales import invoiced_sales as inv

KEY = "sales_by_debtor_type"
PERMISSION = "sales.reports.view"
MODULE_KEY = "sales"

DEFAULT_DETAIL_COLUMNS = [
    "document_no",
    "document_date",
    "document_type",
    "customer",
    "sales_agent",
    "debtor_type",
    "channel",
    "sales_value",
]


def this_month() -> dict:
    today = reg.today_malaysia()
    return {"kind": "custom", "from": date(today.year, today.month, 1).isoformat(), "to": today.isoformat()}


def agent_options(db) -> list:
    from app.models.base import get_company_scope
    from app.services.scm.sales_agent_service import scope_filter

    q = db.query(SalesAgent.id, SalesAgent.sales_agent).filter(SalesAgent.is_active.is_(True))
    predicate = scope_filter(get_company_scope(db))
    if predicate is not None:
        q = q.filter(predicate)
    rows = q.all()
    return sorted(((str(i), str(code)) for i, code in rows), key=lambda r: r[1])


def debtor_type_options(db) -> list:
    rows = (
        db.query(Customer.autocount_debtor_type)
        .filter(Customer.autocount_debtor_type.isnot(None))
        .distinct()
        .all()
    )
    return sorted((str(v), str(v)) for (v,) in rows)


def agent_condition(ctx, values):
    return inv.agent_condition(values)


def debtor_type_condition(ctx, values):
    return inv.debtor_type().in_(values)


def note(ctx) -> str:
    return (
        "Sales = invoices + cash sales + debit notes - credit notes, excluding tax, by document "
        "date. Blocks are the sales type of the sales orders each document traces to."
    )


REPORT = reg.register(
    reg.ReportDefinition(
        key=KEY,
        title="Sales by debtor type",
        permission=PERMISSION,
        module_key=MODULE_KEY,
        dataset=bd.DATASET,
        params=(
            reg.SelectParam(
                key="company", label="Company", multi=False, default=(),
                options=ds.company_options, condition=ds.company_condition, clearable=False,
            ),
            reg.SelectParam(
                key="channel", label="Sales type", multi=True,
                default=tuple(value for value, _label in inv.SALES_TYPES),
                options=lambda db: list(inv.SALES_TYPES),
                condition=bd.channel_condition,
            ),
            reg.SelectParam(
                key="agent", label="Sales agent", multi=True, default=(),
                options=agent_options, condition=agent_condition,
            ),
            reg.SelectParam(
                key="debtor_type", label="Debtor type", multi=True, default=(),
                options=debtor_type_options, condition=debtor_type_condition,
            ),
            reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
            reg.PeriodParam(key="period", label="Period", default=this_month),
        ),
        detail=reg.DetailLayout(title="Billing documents", order_by=bd.order_by, cap="truncate"),
        pivot=reg.PivotLayout(title="Sales agent by debtor type", whole_units=False),
        default_view={
            "params": {
                "date_basis": "order_date",
                "channel": [value for value, _label in inv.SALES_TYPES],
            },
            "detail": {"columns": list(DEFAULT_DETAIL_COLUMNS), "order": list(DEFAULT_DETAIL_COLUMNS)},
            "pivot": {"rows": "sales_agent", "cols": "debtor_type", "measures": ["sales_value"]},
        },
        note=note,
        opens_on="summary",
        workbook=reg.WorkbookSpec(
            company_name="",
            report_title="WEEKLY SALES BY DEBTOR TYPE BY SALES AGENT",
            headers={"sales_agent": "SALES AGENT", "sales_value": "RM"},
            sheet_per="channel",
            month_sheets=True,
            money_format="#,##0.00;(#,##0.00)",
        ),
    )
)
