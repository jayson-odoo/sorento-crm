# PLAN: self-reference turns never refuse on carried foreign customers

Status: in review on PR #1401, small fix track (one additive grant migration, no auth/RBAC
change to staff, no new ingest surface).
Lane: CHATBOT-SELFREF-SCOPE. Parent: `PLAN-chatbot-customer-scope-29sep.md` (PR #1365).
UAC: `selfref-scope-acceptance-criteria.md`.

## Symptom (production, 30 Sep 2026)

A contact linked to six HANLIM TRADING customers asked "I want to check my sales for this
month". Parser verdict: `business_query`, `order_status="sales_report"`, `self_reference=true`,
`entities=[]`. The bot answered the scope refusal line at 0 ms and called no tool. After
"clear all" the same question ran, but as `order_status="sales_analysis"`, and came back
"Could not run the sales report right now." with `has_result=true` and `error=null` on the
trace.

## Cause, Part A (the refusal)

Replayed in the engine harness with the real resolver against the owner's focus verbatim:

- `turn_runtime.with_carried_entities` hands the carried category token `water tap` (no uuid,
  `current_message: false`) to the resolver on the fetch turn; `engine._customer_scope_gate`
  strips customer-hinted entities only.
- Under `order` the resolver re-types a category token as a customer
  (`entity_resolver._DOMAIN_HINT_EXPANSIONS`) and `_probe_customer` fuzzy-matches customer
  names by word coverage. Two or more matches open a customer picker (`_exit_kind: offer`).
- `engine._screen_resolver_for_scope` drops the foreign rows and refuses on the offer rule,
  so the turn is answered with the refusal line before any tool. One match only is dropped
  silently, which is why the cold path and a single-match replay pass.

Owner rulings (parent plan Q5/Q6/Q7b, and on this lane, option b): the refusal line is for
a TYPED foreign customer word only; a carried word's matches are dropped and traced.

## Cause, Part B (the clean path)

- `/api/v1/sales/analysis` is gated on `sales.reports.view` for the API key's act-as
  principal; `sales_s1_reports_module` granted it to admin and superadmin only, so the n8n
  key's role `integration_n8n` was answered 403.
- `sorento_crm_mcp.http_client` returned the 403 body verbatim and
  `presenters._sales_analysis_envelope` rendered any non-status body as "Could not run the
  sales report right now." with `has_result: true`, so the lane never saw an `error`.
- Even once granted, the route refuses any contact linked to a customer (AC-S1-23): a
  company's totals are not a linked contact's figures.

## Change

Part A (R1 to R5 of the brief):

- `engine._customer_scope_gate`: on a scoped `order` turn, carried brand/category-hinted
  tokens are kept off the resolver (they can only ever be re-typed as customers).
- `engine._screen_resolver_for_scope`: refuses only when the dropped matches belong to a
  token typed this message (`_typed_tokens`); returns the dropped ids. A picker a carried
  word opened is passed once spent, so the tool runs on the links.
- `fetch.entity_ids_transformer`: on a `self_reference` turn a carried `customer_ids` outside
  the links is clamped to them (recorded on `scope_events`); any other turn still raises
  `ScopeViolation`, which now carries `dropped`.
- `lanes/business.run_fetch`: every scope decision (gate, screen, fetch clamp, fetch refusal,
  tier probe refusal, the B2 re-route) writes a `customer_scope` trace event with the reason
  and the ids.

Part B (crew instruction on PR #1401):

- B1 `alembic/versions/selfref_0001_n8n_sales_view.py` grants `sales.reports.view` to
  `integration_n8n` (idempotent); `scripts/bootstrap_env.py` replays it for a create_all
  database.
- B2 `run_fetch`: a customer-scoped contact's `sales_analysis` ask runs `crm_sales_report`
  over the linked customer ids; staff and unlinked contacts keep `crm_sales_analysis`.
- B3 `sorento_crm_mcp.http_client.http_error_body` stamps `status_code` and a one-line
  `error` on every non-2xx body; `presenters.present_response` answers an error envelope
  (`has_result: false`, `error`, `status_code`, `detail`) for every presenter tool, which
  the lane records as a tool error on the trace.

## Tests

- `tests/chatbot/test_customer_scope_lane.py`: the production replay (real resolver, two
  fuzzy-matching foreign customers, owner's focus and verdict), the bare ask over the same
  focus, R2 under "my", the cold-path trace, the screen rule unit tests, B2 both ways.
- `tests/chatbot/test_customer_scope_fetch.py`: the clamp, the refusal's `dropped`, the
  `run_fetch` clamp and refusal traces, the tier-probe trace.
- `tests/chatbot/test_sales_analysis_lane.py`: B3 through `run_fetch` with the real presenter.
- `tests/test_migration_selfref_0001_n8n_sales_view.py`: B1.
- `sorento_crm_mcp/tests/test_http_error_envelope.py`: B3 at the MCP.
