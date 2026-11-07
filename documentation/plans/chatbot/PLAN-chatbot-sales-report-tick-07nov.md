# PLAN: chatbot invoiced sales follow the contact's Sales report tick

Status: in review (small fix track: no migration, under 300 lines; access change, so security-reviewer runs)

## Problem

Owner 7 Nov: a WhatsApp ask for invoiced sales from contact "Mr Loo" (ticked "Sales report")
answered "Invoiced sales need the sales reports permission". The invoiced gate
`invoiced_sales.require_invoiced_access` checks `sales.reports.view` on the API key's act-as user
(and, on an identity read, the staff member), never the contact's `sales_orders.sales_report` reveal.

## Rule

- A chatbot call naming a contact (the chatbot's SHARED key + contact_id/space_id, no staff
  identity): invoiced is open iff the resolved contact holds `sales_orders.sales_report`, whatever
  the act-as user holds. Scope (companies, brands, customers) is unchanged.
- Any other integration key keeps the slug, contact pair or not (security review S1).
- An identity read (AI panel, `key_user_id`) and a session user: `sales.reports.view`, as today.
- Unticked contact: today's 403 `invoiced_needs_sales_reports`.

One helper, `invoiced_sales.may_read_invoiced` / `require_invoiced_access(db, current_user,
api_key=, contact_id=, space_id=)`, called by `report_ask.py` and `orders.py` (top selling items),
the only two callers of the gate.

Narrowing (noted for the owner): a contact WITHOUT the tick used to get invoiced figures whenever
the act-as user held the slug (e.g. a salesperson on its own book). It now gets the 403, as asked
("unticked keeps today's reply").

Owner 7 Nov 18:50 ("strict", option a): confirmed as built, and the same rule applies to the sales
target route. The helper is generic, `invoiced_sales.contact_tick_or_slug(grant=, slug=)`:
- invoiced: grant `sales_orders.sales_report`, slug `sales.reports.view`;
- target progress (`sales/target_progress.py`, `crm_sales_target_progress`): grant
  `sales.sales_target` (`contact_field_reveal_service.py:84`; staff slug `sales.targets.view`,
  line 108), slug `sales.reports.view`. The route-level `require_permission_with_api_key` gate is
  replaced by the helper, so a chatbot call naming a contact needs only the contact's tick.

Not changed: `sales/analysis.py` gates the whole route on `sales.reports.view` on the act-as
user; no chat path calls `crm_sales_analysis` any more (`sales_basis_ask.py:13`).

## Tests

`tests/test_invoiced_gate_contact_tick.py`: ticked contact without slug -> allowed; unticked -> refused;
session user / identity read unaffected.
