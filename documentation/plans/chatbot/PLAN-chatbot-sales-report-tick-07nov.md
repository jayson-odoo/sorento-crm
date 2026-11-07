# PLAN: chatbot invoiced sales follow the contact's Sales report tick

Status: in progress (small fix track: no migration, under 300 lines; access change, so security-reviewer runs)

## Problem

Owner 7 Nov: a WhatsApp ask for invoiced sales from contact "Mr Loo" (ticked "Sales report")
answered "Invoiced sales need the sales reports permission". The invoiced gate
`invoiced_sales.require_invoiced_access` checks `sales.reports.view` on the API key's act-as user
(and, on an identity read, the staff member), never the contact's `sales_orders.sales_report` reveal.

## Rule

- A chatbot call naming a contact (API key + contact_id/space_id, no staff identity): invoiced is
  open iff the resolved contact holds `sales_orders.sales_report`. Scope (companies, brands,
  customers) is unchanged.
- An identity read (AI panel, `key_user_id`) and a session user: `sales.reports.view`, as today.
- Unticked contact: today's 403 `invoiced_needs_sales_reports`.

One helper, `require_invoiced_access(db, current_user, contact_keys=...)`, called by
`report_ask.py` and `orders.py` (top selling items).

## Tests

`tests/test_invoiced_gate_contact_tick.py`: ticked contact without slug -> allowed; unticked -> refused;
session user / identity read unaffected.
