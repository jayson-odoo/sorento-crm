"""Billing documents (`/finance/billing-documents`): invoices, cash sales, debit notes and credit notes, and the
owner's sales figure over them.

Sales = Invoices + Cash sales + Debit notes - Credit notes, net of tax in RM, by document date, cancelled
documents excluded (owner ruling, SALES-UNIFIED). The figure, the agent and the sales type are the expressions of
`app/services/sales/invoiced_sales.py`, the one sales calculation, never written again here. The screen is
`finance.billing_documents.view` with no own rule (`api/v1/finance/billing_documents.py`). The figures follow the
sales report's gate on top (crew pass, 5 Nov): money fields and every total need the staff reveal the report needs,
so `crm_query` never shows what `crm_report_ask` refuses.
"""
from __future__ import annotations

from app.models.finance import POSTED, BillingDocument
from app.services.assistant_registry import register
from app.services.assistant_registry.query import OUTSTANDING, SALES_REPORT
from app.services.assistant_registry.types import EntityDef, FieldDef
from app.services.sales import invoiced_sales

BILLING_VIEW = "finance.billing_documents.view"

register(
    EntityDef(
        key="billing_document",
        label="Billing documents (invoices, cash sales, debit and credit notes)",
        module="finance",
        model=BillingDocument,
        view_permission=BILLING_VIEW,
        fields={
            "doc_no": FieldDef("Document no."),
            "document_type": FieldDef("Type", note="invoice, cash_sale, debit_note or credit_note."),
            "doc_date": FieldDef(
                "Document date", note="The date sales are counted by; use it for a period such as last month.",
            ),
            "debtor_code": FieldDef("Debtor code"),
            "customer_name": FieldDef("Customer"),
            "agent": FieldDef(
                "Agent", expr=invoiced_sales.agent_label, agent_id=invoiced_sales.agent_id,
                note="The agent the sale belongs to, as the sales reports count it; group by this for per agent sales.",
            ),
            "sales_amount": FieldDef(
                "Sales (RM)", expr=invoiced_sales.signed_amount, permission=SALES_REPORT,
                note="THE sales figure: net of tax in RM, a credit note negative. Sales = sum of this "
                     "(invoices + cash sales + debit notes - credit notes).",
            ),
            "sales_type": FieldDef(
                "Sales type", expr=invoiced_sales.sales_type_label,
                note="Dealer, Project team, Other, Set apart, ... as the sales reports split sales.",
            ),
            "net_total": FieldDef("Net total", permission=SALES_REPORT, note="In the document's currency, not signed; use sales_amount for sales."),
            "total": FieldDef("Total incl. tax", permission=SALES_REPORT, note="In the document's currency, not signed."),
            "currency_code": FieldDef("Currency"),
            "status": FieldDef("Status", note="posted or cancelled."),
            "outstanding": FieldDef("Outstanding", permission=OUTSTANDING, note="Still owed on the document (synced from AutoCount)."),
            "due_date": FieldDef("Due date"),
        },
        relations={"customer": ("customer", "customer_id")},
        name_by=("doc_no", "customer_name"),
        # Owner ruling: sales leave cancelled documents out, and the answer says so.
        default_filters=(("status", "eq", POSTED, "Cancelled documents excluded."),),
        screen_path="/finance/billing-documents/{id}",
        pages=("/finance/billing-documents",),
        routes=("GET /api/v1/finance/billing-documents",),
        # Totals and lines of every brand: refused on a brand-scoped contact's turn (security review B1).
        brand_blind=True,
        # Crew pass 5 Nov: the money and every total follow the sales report's own gate
        # (`api/v1/order_management/report_ask.py`: the staff reveal `sales_orders.sales_report`, held through
        # `sales.reports.view`; outstanding through `sales_orders.outstanding`), so the registry is no side door.
        aggregate_permission=SALES_REPORT,
        list_fields=("doc_date", "document_type", "agent", "sales_amount"),
        date_field="doc_date",
        aggregate_note="Invoiced sales (invoices + cash sales + debit notes - credit notes, by document date).",
        hint="invoices, cash sales, debit and credit notes. ANY 'sales' question with no basis named: sum "
             "sales_amount by doc_date (invoiced), per agent = group by agent; table and total from this ONE query",
    ),
)
