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
- Channel is the sales order's dealer or project class (G4); with both ticked the file
  writes the DEALER block, then the PROJECT TEAM block, on one sheet (Q1 (b), AC-R4-7).
- Basis is Delivered by default, Ordered on request, printed on every header (G1).
"""
from __future__ import annotations

from datetime import date

from app.services.reports import registry as reg
from app.services.reports.datasets import sales_order_lines as ds

KEY = "sales_yearly"
PERMISSION = "sales.reports.view"
MODULE_KEY = "sales"

DEFAULT_DETAIL_COLUMNS = [
    "so_number",
    "order_date",
    "customer",
    "agent_code",
    "product_code",
    "channel",
    "sales_value",
]


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
                default=tuple(value for value, _label in ds.CHANNELS),
                options=lambda db: list(ds.CHANNELS),
                condition=ds.channel_condition,
            ),
            reg.SelectParam(
                key="basis",
                label="Basis",
                multi=False,
                default=("delivered",),
                options=lambda db: list(ds.BASES),
                condition=ds.basis_condition,
                clearable=False,
            ),
            reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
            reg.PeriodParam(key="period", label="As at", default=as_at_period),
        ),
        detail=reg.DetailLayout(title="Sales order lines", order_by=ds.order_by, cap="truncate"),
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
                "channel": [value for value, _label in ds.CHANNELS],
                "basis": ["delivered"],
            },
            "detail": {
                "columns": list(DEFAULT_DETAIL_COLUMNS),
                "order": list(DEFAULT_DETAIL_COLUMNS),
            },
            "pivot": {"rows": "year", "cols": "month_of_year", "measures": ["sales_value"]},
        },
        note=ds.note,
        opens_on="summary",
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
