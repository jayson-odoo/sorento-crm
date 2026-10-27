"""The Yearly comparison (was report A): a company's dealer or project sales per month,
this year beside the two before it, with the variance row and a line chart
(PLAN-retail-sales-reports-26sep 5.2, S1).

The whole report is this file plus the sales dataset: it runs on the reports kernel the
sponsorship report uses (Owner ruling 26 Sep 06:27 (Lavish) 1 and 2), so the screen, the
Excel and the chatbot share one query.

- Rows are the period's years, columns JAN to DEC, whether a month has sales or not; a
  month after the as-at date is blank, never 0 (AC-S1-9).
- VARIANCE is the last year minus the one before, over the months the last year has, so
  its total is this year to date against the same months last year (G5 (a), AC-S1-10).
- Channel is the sales type (SALES-UNIFIED 2.4): on Invoiced, the class of the sales orders
  each document traces to, plus Set apart, Mixed, Type not set and No sales order, so with every
  value ticked the blocks add up to all sales; on the order bases, the sales order's own dealer
  or project class (G4), "Type not set" its blank class, the invoice-only types empty. One block
  per ticked value, on one sheet (Q1 (b), AC-R4-7).
- Basis is Invoiced by default (SALES-UNIFIED: one sales definition, `invoiced_sales`);
  Delivered and Ordered stay on request, printed on every header (G1).
"""
from __future__ import annotations

from datetime import date

from app.services.reports import registry as reg
from app.services.reports.datasets import billing_documents as bd
from app.services.reports.datasets import sales_order_lines as ds
from app.services.sales import invoiced_sales as inv

KEY = "sales_yearly"
PERMISSION = "sales.reports.view"
MODULE_KEY = "sales"

# One list for both bases: a key the run's dataset does not hold is left out of that run,
# so Delivered opens on the order columns and Invoiced on the document ones.
DEFAULT_DETAIL_COLUMNS = [
    "so_number",
    "document_no",
    "order_date",
    "document_date",
    "document_type",
    "customer",
    "agent_code",
    "product_code",
    "channel",
    "sales_value",
]


def _of(ctx):
    """The dataset module behind this run: billing documents on Invoiced, else orders."""
    return bd if ctx.dataset is bd.DATASET else ds


#: On the order bases, a sales type -> the sales order demand class it reads (None: blank).
_ORDER_CLASSES = {inv.DEALER: "retail", inv.PROJECT: "project", inv.TYPE_NOT_SET: None}


def _channel_condition(ctx, values):
    if _of(ctx) is bd:
        return bd.channel_condition(ctx, values)
    import sqlalchemy as sa

    from app.models.order import SalesOrder

    chosen = inv.normalise_sales_types(values)
    classes = [_ORDER_CLASSES[v] for v in chosen if v in _ORDER_CLASSES and _ORDER_CLASSES[v]]
    parts = [SalesOrder.demand_class.in_(classes)] if classes else []
    if inv.TYPE_NOT_SET in chosen:
        parts.append(SalesOrder.demand_class.is_(None))
    return sa.or_(*parts) if parts else sa.false()


def _order_by(ctx):
    return _of(ctx).order_by(ctx)


def as_at_period() -> dict:
    """1 January two years back to today: the as-at date is the period's last day."""
    today = reg.today_malaysia()
    return {"kind": "custom", "from": date(today.year - 2, 1, 1).isoformat(), "to": today.isoformat()}


REPORT = reg.register(
    reg.ReportDefinition(
        key=KEY,
        title="Yearly comparison",
        permission=PERMISSION,
        module_key=MODULE_KEY,
        dataset=ds.DATASET,
        params=(
            reg.SelectParam(
                key="company",
                label="Company",
                multi=False,
                default=(),  # the caller's current company, resolved per request
                options=ds.company_options,
                condition=ds.company_condition,
                clearable=False,
            ),
            reg.SelectParam(
                key="channel",
                label="Channel",
                multi=True,
                default=tuple(value for value, _label in inv.SALES_TYPES),
                options=lambda db: list(inv.SALES_TYPES),
                condition=_channel_condition,
            ),
            reg.SelectParam(
                key="basis",
                label="Basis",
                multi=False,
                default=("invoiced",),
                options=lambda db: list(ds.BASES),
                condition=ds.basis_condition,
                clearable=False,
            ),
            reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
            reg.PeriodParam(key="period", label="Period", default=as_at_period),
        ),
        detail=reg.DetailLayout(
            title=lambda ctx: "Billing documents" if _of(ctx) is bd else "Sales order lines",
            order_by=_order_by,
            cap="truncate",
        ),
        pivot=reg.PivotLayout(
            title="Year by month",
            variance="last_two_rows",
            chart="line",
            whole_units=True,
            column_totals=False,
        ),
        default_view={
            "params": {
                "date_basis": "order_date",
                "channel": [value for value, _label in inv.SALES_TYPES],
                "basis": ["invoiced"],
            },
            "detail": {
                "columns": list(DEFAULT_DETAIL_COLUMNS),
                "order": list(DEFAULT_DETAIL_COLUMNS),
            },
            "pivot": {"rows": "year", "cols": "month_of_year", "measures": ["sales_value"]},
        },
        note=ds.note,
        opens_on="summary",
        datasets_by=("basis", {"invoiced": bd.DATASET}),
        workbook=reg.WorkbookSpec(
            # Empty: the company is the one the run READ (the Company filter).
            company_name="",
            report_title="YEARLY SALES COMPARISON",
            headers={"year": "YEAR", "sales_value": "RM"},
            column_widths={"year": 12.0, "sales_value": 14.0},
            summary_row_total_label="TOTALS",
            month_sheets=False,
            sheet_per="channel",
            period_as_at=True,
            money_format="#,##0.00;(#,##0.00)",
            no_value="",
        ),
    )
)
