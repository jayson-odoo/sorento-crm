# UAC - Chatbot: a self-reference turn never refuses on what the conversation carried

Plan: `PLAN-chatbot-selfref-scope-30sep.md`. Crew lane CHATBOT-SELFREF-SCOPE, PR #1401.
Parent UAC: `chatbot-customer-scope-29sep-acceptance-criteria.md` (AC-CS-10, 11, 22 to 26
stay green).

## Journey

A dealer's purchaser, linked to six customer accounts, has been chatting about a product
category and then asks "I want to check my sales for this month". The bot answers with the
sales report over all six accounts. Nothing the conversation carried from before, and nothing
the resolver guesses from those carried words, can turn that into "Sorry, that isn't under
your account". Naming another customer's account still gets that line. When a tool call
fails behind the bot, the trace says which route, which status and why.

## Part A

- **AC-SR-01** `[BE]` Given a scoped contact whose focus carries a category word (no
  customer) and status `sales_report`, when the verdict is `self_reference: true`,
  `order_status: sales_report`, no entities, then `crm_sales_report` runs with
  `customer_ids` equal to the linked ids in link order, the reply is not the refusal line and
  not a picker, and no other customer's id or name appears in the call or the trace.
- **AC-SR-02** `[BE]` The same state without `self_reference` ("sales this month"): the same
  outcome.
- **AC-SR-03** `[BE]` Given a scoped contact, when the message TYPES a word (any hint) whose
  resolver matches are only customers outside the links, `self_reference` or not, then the
  refusal line (AC-CS-11), no tool call, and a `customer_scope` trace event with
  `refused: customer_not_permitted`, the typed word and the dropped ids.
- **AC-SR-04** `[BE]` `entity_ids_transformer`: on a `self_reference` turn a requested
  `customer_ids` outside `scope_customer_ids` is clamped to the ids inside (the whole scope
  when none remain) and reported on `scope_events`; on any other turn `ScopeViolation` is
  raised and carries `dropped`.
- **AC-SR-05** `[BE]` Every scope decision writes a `customer_scope` trace event: the gate's
  refusal, the screen's drop or refusal, the scoped-to-links pass (with `ids` and
  `self_reference`), the fetch clamp, the fetch refusal and the tier-probe refusal, each with
  a `reason` and the ids it dropped.
- **AC-SR-06** `[BE]` No parser or prompt change.

## Part B

- **AC-SR-10** `[BE]` Migration `selfref_0001_n8n_sales_view` grants `sales.reports.view` to
  role `integration_n8n`, creates the permission row when absent, is idempotent, grants
  nothing to other roles, and its downgrade removes exactly that grant.
- **AC-SR-11** `[BE]` A scoped contact's `order_status: sales_analysis` ask is answered by
  `crm_sales_report` over the linked ids with the verdict's date window; `crm_sales_analysis`
  is not called; the trace carries `decision: sales_analysis_answered_as_sales_report`. An
  unlinked or staff contact keeps `crm_sales_analysis`.
- **AC-SR-12** `[MCP]` A non-2xx answer from the CRM keeps the route's own keys and gains
  `status_code`, `error` (one line: method, path, status, the route's code or message) and
  `http_error`; `present_response` renders it for every presenter tool as `has_result: false`,
  `error`, `status_code`, `detail`, empty `response` and `answers`.
- **AC-SR-13** `[BE]` `run_fetch` given that envelope returns a `kind: error` fragment whose
  error names the status and code, never a `has_result: true` line, and the `tool` trace
  event carries the envelope with its `error`, `status_code` and `detail`.
