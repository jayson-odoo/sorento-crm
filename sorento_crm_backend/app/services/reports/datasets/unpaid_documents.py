"""The chatbot's `unpaid` basis (lane REPORT-UNIFY, slice 1; `documentation/plans/reports/PLAN-report-unify-27oct.md`
section 0, Q2): what customers still owe on posted AutoCount billing documents.

One row per billing document that is posted, not a credit note and has `outstanding` above 0 (AutoCount's
own balance, in ringgit; NULL is "not synced" and is out). Dated by the document's own date. A document
has no product, so the report has no product, brand, category, spec, location or channel axis: the route
answers those under `not_applied` (`per_document`).

Registered on the Reports API as the "Sales & outstanding" screen's Unpaid invoices report
(`definitions/sales_and_outstanding`), the very object `ask.run_ask` runs, so the screen and the bot cannot drift.
"""
from __future__ import annotations

from typing import Any, List, Optional

import sqlalchemy as sa

from app.models.finance import CREDIT_NOTE, POSTED, BillingDocument
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services.reports import ask_params as ap
from app.services.reports import registry as reg
from app.services.reports.datasets.delivery_order_lines import NO_AGENT
from app.services.reports.datasets.sales_order_lines_ask import _agent_in


def _base(ctx: Any) -> sa.Select:
    return (
        sa.select()
        .select_from(BillingDocument)
        .outerjoin(Customer, Customer.id == BillingDocument.customer_id)
        .outerjoin(SalesAgent, SalesAgent.id == BillingDocument.sales_agent_id)
        .where(
            BillingDocument.status == POSTED,
            BillingDocument.document_type != CREDIT_NOTE,
            BillingDocument.outstanding > 0,
        )
    )


def _no_options(db: Any) -> List[Any]:
    return []


def customer_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return BillingDocument.customer_id.in_(values)


def sales_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return _agent_in(BillingDocument.sales_agent_id, values)


def customer_agent_condition(ctx: Any, values: List[str]) -> Optional[Any]:
    return _agent_in(Customer.sales_agent_id, values, owner=Customer.id)


COLUMNS = (
    reg.Column(
        "customer", "Customer", "text", "dimension",
        lambda c: sa.func.coalesce(Customer.customer_name, BillingDocument.customer_name), size=220,
    ),
    reg.Column(
        "sales_agent", "Sales agent", "text", "dimension",
        lambda c: sa.func.coalesce(SalesAgent.sales_agent, NO_AGENT), size=140,
    ),
    reg.Column("month", "Month", "text", "dimension", lambda c: sa.func.to_char(BillingDocument.doc_date, "YYYY-MM"), size=110),
    reg.Column("all", "All", "text", "dimension", lambda c: sa.cast(sa.literal("all"), sa.Text), size=80),
    reg.Column("amount", "RM", "money", "measure", lambda c: BillingDocument.outstanding, size=130),
    # No quantity on a document: the shared pivot reads one.
    reg.Column("qty", "Qty", "integer", "measure", lambda c: sa.literal_column("0"), size=100),
)

DATASET = reg.Dataset(
    key="unpaid_documents",
    scope="company",
    columns=COLUMNS,
    date_bases=(reg.DateBasis("order_date", "Document date", BillingDocument.doc_date),),
    base=_base,
    company_column=BillingDocument.company_id,
)

DEFINITION = reg.ReportDefinition(
    key="unpaid_documents",
    title="Unpaid invoices",
    # Receivables are finance data: the billing documents' own slug, as `api/v1/finance/billing_documents` reads them
    # (security review B1).
    permission="finance.billing_documents.view",
    dataset=DATASET,
    params=(
        reg.DateBasisParam(key="date_basis", label="Date basis", default="order_date"),
        reg.PeriodParam(key="period", label="Period", default=reg.all_dates_period),
        reg.SelectParam("customer", "Customer", True, (), ap.customer_options, customer_condition),
        reg.SelectParam("sales_agent", "Sales agent", True, (), ap.agent_options, sales_agent_condition),
        reg.SelectParam("customer_agent", "Customers assigned to", True, (), _no_options, customer_agent_condition, hidden=True),
    ),
    detail=reg.DetailLayout(
        title="Unpaid invoices",
        order_by=lambda c: [BillingDocument.doc_date.desc(), BillingDocument.doc_no.asc(), BillingDocument.id.asc()],
    ),
    pivot=reg.PivotLayout(title="Unpaid invoices"),
    default_view={
        "params": {"date_basis": "order_date"},
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "month", "cols": "all", "measures": ["qty", "amount"]},
    },
    workbook=reg.WorkbookSpec(company_name=""),
    module_key="finance",
)

reg.validate(DEFINITION)
