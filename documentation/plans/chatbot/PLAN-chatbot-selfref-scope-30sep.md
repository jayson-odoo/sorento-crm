# PLAN: a linked contact's sales asks run the customer sales report

Status: in review on PR #1401, small fix track (one additive grant migration, no auth/RBAC
change to staff, no new ingest surface). The engine/resolver half of the lane is PARKED on
PR #1403 (owner decision, 30 Sep 2026: the parser prompt is fixed in production first).
Lane: CHATBOT-SELFREF-SCOPE. Parent: `PLAN-chatbot-customer-scope-29sep.md` (PR #1365).
UAC: `selfref-scope-acceptance-criteria.md`.

## Symptom (production, 30 Sep 2026)

A contact linked to six HANLIM TRADING customers asked "I want to check my sales for this
month" and got the customer-scope refusal line at 0 ms (trace one). After "clear all" the
same question ran as `order_status="sales_analysis"` and came back "Could not run the sales
report right now." with `has_result=true` and `error=null` on the trace (trace two).

## Trace one (parked, PR #1403)

Replayed in the engine harness with the real resolver against the owner's focus verbatim:
the carried category token `water tap` reached the resolver, which re-types a category
token as a customer under `order` (`entity_resolver._DOMAIN_HINT_EXPANSIONS`, introduced by
`2aa63ce8a` for a TYPED customer name the n8n agent had hinted brand/category) and
fuzzy-matched two accounts nobody named; the picker tripped `_screen_resolver_for_scope`'s
offer rule. The parser had emitted `domain_in_message=false` beside `order_status=sales_report`
("sales" is not in the prompt's DOMAIN IN MESSAGE word list), so the engine carried the
standing subject. Owner's call: fix the parser prompt in production first; the engine and
resolver work (carried context keeps its kind, typed-word-only refusal) waits on #1403.

## Trace two (this PR)

- B1 `/api/v1/sales/analysis` is gated on `sales.reports.view` for the API key's act-as
  principal; `sales_s1_reports_module` granted it to admin and superadmin only, so the n8n
  key's role `integration_n8n` was answered 403.
  `alembic/versions/selfref_0001_n8n_sales_view.py` grants it (idempotent);
  `scripts/bootstrap_env.py` replays it for a create_all database.
- B2 Even once granted, the analysis route refuses any contact linked to a customer
  (AC-S1-23): a company's totals are not a linked contact's figures. `run_fetch` now
  answers a customer-scoped contact's `sales_analysis` ask with `crm_sales_report` over the
  linked customer ids (parent plan Q6a, Q8a); staff and unlinked contacts keep
  `crm_sales_analysis`.
- B3 `sorento_crm_mcp.http_client` returned the 403 body verbatim and
  `presenters._sales_analysis_envelope` rendered any non-status body as "Could not run the
  sales report right now." with `has_result: true`. `http_error_body` now stamps
  `status_code`, `error` and `http_error` on every non-2xx body and `present_response`
  answers an error envelope (`has_result: false`, `error`, `status_code`, `detail`) for every
  presenter tool, which the lane records as a tool error on the trace.
- The reply is TEXT. `crm_sales_report` renders the presenter's month blocks
  (`sorento_crm_mcp/presenters.py::_sales_report_envelope`) and carries no attachment
  (`fetch._sales_report_output`); the Excel belongs to `crm_sales_analysis` alone (owner
  ruling 26 Sep 2026, "always text + file"), which a linked contact no longer reaches.
- R4 Every scope decision writes a `customer_scope` trace event (the gate's and the
  screen's refusal with the ids dropped, the scoped-to-links pass, the fetch and tier-probe
  refusals, the B2 re-route). `trace_detail.compose_trace_detail` projects them and the chat
  history turn drawer prints a "Customer scope" panel: the event existed before but no panel
  read it, which is why the owner's trace showed nothing for it.

## Tests

- `tests/chatbot/test_customer_scope_lane.py`: B2 (linked, unlinked, staff), the trace
  records (scoped, gate refusal, resolver refusal with dropped ids).
- `tests/chatbot/test_customer_scope_fetch.py`: `ScopeViolation.dropped`, the fetch and
  tier-probe refusal traces.
- `tests/chatbot/test_sales_analysis_lane.py`: B3 through `run_fetch` with the real presenter.
- `tests/chatbot/test_rearch_s3_trace.py`: the `customer_scope` projection.
- `tests/test_migration_selfref_0001_n8n_sales_view.py`: B1.
- `sorento_crm_mcp/tests/test_http_error_envelope.py`: B3 at the MCP.
- `TurnDetailDrawer.test.tsx`: the panel.
