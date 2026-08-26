"""Report #1: the sponsorship register, the workbook the project-sales team keeps by hand.

The whole report is this file plus its dataset. There is no route, no schema, no frontend
page and no Excel code specific to it - which is the claim the foundation was built to make
(PLAN-reporting-foundation, "Why a foundation and not a page").

The defaults are the workbook's own shape, decided with the user on 2026-08-26:

- month bucket = `approved_at`, and the basis is a filter, because a form approved in July
  for a June enquiry belongs in July's takings;
- statuses = approved + processed by CS, because a draft is not a sponsorship;
- eight detail columns, the OTHERS column dropped (empty in all twelve 2025 sheets);
- the summary is salesman by month on both money columns, which is the pivot the team
  reads first.
"""
from __future__ import annotations

from app.services.reports import registry as reg
from app.services.reports.datasets import sponsorship_forms as ds

KEY = "sponsorship"
PERMISSION = "procurement.sponsorship_forms.report"

#: The eight columns of the client's monthly table, in the client's order (AC-B7). The rest
#: of the catalog is hidden, not absent: the Columns panel still offers every one of them.
DEFAULT_DETAIL_COLUMNS = [
    "request_number",
    "sales_agent",
    "customer_name",
    "project_title",
    "sponsor_subject",
    "project_value",
    "sample_price",
    "expected_delivery_year",
]


REPORT = reg.register(
    reg.ReportDefinition(
        key=KEY,
        title="Sponsorship report",
        permission=PERMISSION,
        dataset=ds.DATASET,
        params=(
            reg.DateBasisParam(key="date_basis", label="Date basis", default="approved_at"),
            reg.PeriodParam(
                key="period",
                label="Period",
                # Resolved per request: the year in front of the USER, not a year baked
                # into a release and not the year this process happened to boot in.
                default=reg.current_year_period,
            ),
            reg.SelectParam(
                key="sales_agent",
                label="Sales agent",
                multi=True,
                default=(),  # empty = every agent
                options=ds.sales_agent_options,
                condition=ds.sales_agent_condition,
            ),
            reg.SelectParam(
                key="status",
                label="Status",
                multi=True,
                default=ds.DEFAULT_STATUSES,
                options=ds.status_options,
                condition=ds.status_condition,
            ),
        ),
        detail=reg.DetailLayout(
            title="Sponsorships",
            order_by=ds.order_by,
            groups=(
                reg.TickGroup(source="expected_delivery_year", label="Expected year of delivery"),
            ),
        ),
        pivot=reg.PivotLayout(title="Summary by salesman"),
        default_view={
            "params": {
                "date_basis": "approved_at",
                # `period` is deliberately absent: the engine fills it from the param's
                # own default, which is resolved per request.
                "sales_agent": [],
                "status": list(ds.DEFAULT_STATUSES),
            },
            "detail": {
                "columns": list(DEFAULT_DETAIL_COLUMNS),
                "order": list(DEFAULT_DETAIL_COLUMNS),
            },
            "pivot": {
                "rows": "sales_agent",
                "cols": "month",
                "measures": ["project_value", "sample_price"],
            },
        },
        workbook=reg.WorkbookSpec(company_name="Sorento", department="PROJECT SALES"),
    )
)
