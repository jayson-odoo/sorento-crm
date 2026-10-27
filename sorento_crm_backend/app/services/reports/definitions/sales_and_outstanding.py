"""The "Sales & outstanding" screen's six reports (REPORT-UNIFY slice 4, plan section 3b): the ask definitions the
chatbot's report ask runs (`ask.CATALOGUE["sales"]`), registered on the generic reports API so staff can check the
bot's number. They are registered as the SAME objects, never copies, so the screen and the bot cannot drift.

Permission follows each definition: invoiced `sales.reports.view`, unpaid `finance.billing_documents.view` (receivables are
finance data), the other four `order_management.orders.view`.
"""
from __future__ import annotations

from app.services.reports import registry as reg
from app.services.reports.datasets import billing_document_lines as invoiced
from app.services.reports.datasets import delivery_order_lines as delivery
from app.services.reports.datasets import sales_order_lines_ask as order_lines
from app.services.reports.datasets import unpaid_documents as unpaid

#: Tab order of the screen: invoiced, delivered, ordered, undelivered orders, pending delivery, unpaid invoices.
DEFINITIONS = (
    invoiced.ASK_DEFINITION,
    order_lines.DEFINITIONS["delivered"],
    order_lines.DEFINITIONS["ordered"],
    order_lines.DEFINITIONS["outstanding"],
    delivery.PENDING_DEFINITION,
    unpaid.DEFINITION,
)

for _definition in DEFINITIONS:
    reg.register(_definition)
