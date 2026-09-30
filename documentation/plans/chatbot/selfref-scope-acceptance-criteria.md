# UAC - Chatbot: a linked contact's sales asks run the customer sales report

Plan: `PLAN-chatbot-selfref-scope-30sep.md`. Crew lane CHATBOT-SELFREF-SCOPE, PR #1401
(the engine/resolver half is parked on PR #1403). Parent UAC:
`chatbot-customer-scope-29sep-acceptance-criteria.md` (AC-CS-10, 11, 22 to 26 stay green).

## Journey

A dealer's purchaser, linked to six customer accounts, asks "what is my sales this month".
The bot answers with the customer sales report over all six accounts, as text on WhatsApp:
the period, the ordered and confirmed figures, the outstanding, by month and by product.
Never "Could not run the sales report right now." When a tool call fails behind the bot,
the trace says which route, which status and why, and every customer-scope decision is
readable in Chat history.

- **AC-SR-10** `[BE]` Migration `selfref_0001_n8n_sales_view` grants `sales.reports.view` to
  role `integration_n8n`, creates the permission row when absent, is idempotent, grants
  nothing to other roles, and its downgrade removes exactly that grant.
- **AC-SR-11** `[BE]` A scoped contact's `order_status: sales_analysis` ask is answered by
  `crm_sales_report` over the linked ids with the verdict's date window, as text with no
  attachment; `crm_sales_analysis` is not called; the trace carries
  `decision: sales_analysis_answered_as_sales_report`. An unlinked or staff contact keeps
  `crm_sales_analysis`.
- **AC-SR-12** `[MCP]` A non-2xx answer from the CRM keeps the route's own keys and gains
  `status_code`, `error` (one line: method, path, status, the route's code or message) and
  `http_error`; `present_response` renders it for every presenter tool as `has_result: false`,
  `error`, `status_code`, `detail`, empty `response` and `answers`.
- **AC-SR-13** `[BE]` `run_fetch` given that envelope returns a `kind: error` fragment whose
  error names the status and code, never a `has_result: true` line, and the `tool` trace
  event carries the envelope with its `error`, `status_code` and `detail`.
- **AC-SR-14** `[BE]` Every scope decision writes a `customer_scope` trace event: the gate's
  refusal (`typed_customer_word_outside_links`), the screen's refusal
  (`resolver_matched_only_other_customers`, with the dropped ids), the scoped-to-links pass
  (with `ids` and `self_reference`), the fetch refusal and the tier-probe refusal (with the
  dropped ids). `compose_trace_detail` projects them as `customer_scope` and the Chat history
  turn drawer shows a "Customer scope" panel, empty when the turn made none.
