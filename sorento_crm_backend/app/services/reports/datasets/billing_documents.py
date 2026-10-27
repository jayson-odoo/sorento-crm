"""The rows behind Basis = Invoiced: every posted AutoCount billing document (finance S1,
PLAN-finance-billing-documents-27sep 3.4, #1309).

**IV + CS + DN - CN, excluding tax, in ringgit.** One row per document header (a report with
no product axis needs no lines). Every figure, filter and attribution comes from the one shared
calculation, `app/services/sales/invoiced_sales.py` (SALES-UNIFIED, owner ruling 27 Oct 16:12):
the value is `local_net_total`, AutoCount's own MYR net (ruling Q12), negative on a credit note;
a cancelled document is nowhere (ruling Q13).

**Filed by the document's own date** (`doc_date`), never the order's: a credit note counts in
its own month (UAC S1-2).

**The blocks are the sales type** (SALES-UNIFIED Q1 (b), "the sales type should depend on sales
order"): derived at read time from the sales orders each document traces to, never the stored
`demand_class` (which falls back to the agent's class and the customer's segment). A document
that traces to none is "No sales order". The agent is the document's own, or the customer's on a
company whose `sales_agent_source` says so (`invoiced_sales.agent_label`).

**The keys are the order dataset's where the meaning is the same** (`year`, `month_of_year`,
`year_month`, `channel`, `customer`, `agent_code`, `sales_value`, and the `order_date` date
basis), so the Yearly comparison's default view and a saved one run on either basis; the
document's own columns carry their own keys. Company scope as the order dataset: the company
is a filter and the engine owns the company arm.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import sqlalchemy as sa

from app.models.finance import BillingDocument
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services.reports import registry as reg
from app.services.reports.datasets.sales_order_lines import MONTH_OF_YEAR
from app.services.reports.engine import month_label
from app.services.sales import invoiced_sales as inv

#: How a document type reads in the detail.
TYPE_WORDS: Tuple[Tuple[str, str], ...] = (
    ("invoice", "Invoice"),
    ("cash_sale", "Cash sale"),
    ("credit_note", "Credit note"),
    ("debit_note", "Debit note"),
)

_TYPE_LABEL = sa.case(
    *[(BillingDocument.document_type == value, sa.literal(label)) for value, label in TYPE_WORDS],
    else_=BillingDocument.document_type,
)



def _base(ctx) -> sa.Select:
    return (
        sa.select()
        .select_from(BillingDocument)
        .outerjoin(Customer, Customer.id == BillingDocument.customer_id)
        .outerjoin(SalesAgent, SalesAgent.id == BillingDocument.sales_agent_id)
        .where(inv.posted())
    )


def channel_condition(ctx, values: List[str]) -> Optional[Any]:
    return inv.sales_type_filter(values)


def order_by(ctx) -> Sequence[Any]:
    """Newest document first, as the order detail is newest order first."""
    return [
        BillingDocument.doc_date.desc(),
        BillingDocument.doc_no.asc(),
        BillingDocument.id.asc(),
    ]


COLUMNS: Tuple[reg.Column, ...] = (
    reg.Column("document_no", "Document no", "text", "text",
               lambda c: BillingDocument.doc_no, size=140),
    reg.Column("document_date", "Document date", "date", "date",
               lambda c: BillingDocument.doc_date, size=120),
    # Text, not a dimension: the report has no document axis, and a dimension here would
    # land in the order bases' Configure summary through the union catalog.
    reg.Column("document_type", "Type", "text", "text", lambda c: _TYPE_LABEL, size=110),
    reg.Column("customer", "Customer", "text", "text",
               lambda c: sa.func.coalesce(Customer.customer_name, BillingDocument.customer_name),
               size=220),
    # The document's own agent (ruling Q15), its code as sent when it did not resolve.
    reg.Column("agent_code", "Sales agent code", "text", "text",
               lambda c: sa.func.coalesce(SalesAgent.sales_agent, BillingDocument.agent_code),
               size=140),
    reg.Column("sales_agent", "Sales agent", "text", "dimension",
               lambda c: sa.func.coalesce(inv.agent_label(), inv.NO_AGENT), size=140),
    reg.Column("debtor_type", "Debtor type", "text", "dimension",
               lambda c: inv.debtor_type(), size=120),
    reg.Column("channel", "Channel", "text", "dimension",
               lambda c: inv.sales_type_label(), size=170,
               fixed_values=tuple((label, label) for _value, label in inv.SALES_TYPES)),
    reg.Column(
        "year",
        "Year",
        "text",
        "dimension",
        lambda c: sa.cast(
            sa.cast(sa.extract("year", BillingDocument.doc_date), sa.Integer), sa.Text
        ),
        size=80,
        period_years=True,
    ),
    reg.Column(
        "month_of_year",
        "Month",
        "text",
        "dimension",
        lambda c: sa.func.to_char(BillingDocument.doc_date, "MM"),
        size=80,
        fixed_values=MONTH_OF_YEAR,
    ),
    reg.Column(
        "year_month",
        "Month of the period",
        "text",
        "dimension",
        lambda c: sa.func.to_char(sa.func.date_trunc("month", c.date_basis), "YYYY-MM"),
        size=110,
        period_months=True,
        value_label=month_label,
    ),
    reg.Column("sales_value", "RM", "money", "measure", lambda c: inv.signed_amount(), size=130),
)

DATASET = reg.Dataset(
    key="billing_documents",
    scope="company",
    columns=COLUMNS,
    # Keyed `order_date` like the order dataset's, so the report's one Date basis param
    # (hidden: one choice is no choice) runs on either basis; it reads the document date.
    date_bases=(reg.DateBasis("order_date", "Document date", BillingDocument.doc_date),),
    base=_base,
    company_column=BillingDocument.company_id,
    company_param="company",
)
