# PLAN: AGENT-QUOTE-COMPARE - the agent compares a project's quotations

Status: built, in review (PR #2315; size M; behaviour card answered by crew 10 Nov: Q1-Q5 all (a)). Track: M (agent
behaviour on an existing screen; new panel read, so security-reviewer joins).

UAC: `agent-quote-compare-acceptance-criteria.md`. Behaviour card (causes with file:line, real dev examples):
`agent-quote-compare-behaviour-card.md`.

## Why

Owner, 10 Nov 2026 ~16:10 MYT, prod, AI agent panel on project PPF2611004: "compare the two quotation for this
project". 8 rounds, 152,593 tokens in, ended "The agent could not answer: the model provider failed." Five causes
(a-e), each in the behaviour card.

## Architecture

All backend, Python. No migration, no FE change, no MCP change.

| Layer | File | Change |
|---|---|---|
| Panel service | `app/services/chatbot/panel_service.py` (`_page_context` :166, `_run_agent_side` :229) | Pass the UUIDs found in the page snapshot `path` to the agent turn as `seed_ids`. |
| Agent loop | `app/services/chatbot/agent/loop.py` (`run_agent_turn` :1309, `seen_ids` :1801, `forced_final` :1818, failure branch :2139) | `seen_ids` starts from `seed_ids`. `forced_final` failures after a tool result become a code-built partial reply (status `limited`); `_ProviderFailed` carries the exception class, which the trace records. |
| Agent tools | `app/services/chatbot/agent/tools.py` (`_check_ids` :697, `_resolve` :837, `RESOLVE_SCHEMA` :326, `_dispatch_inner` :1206) | Unknown-id message names the right source per argument; unknown-argument messages state the accepted shape; id args forwarded stripped; a list on a single `*_id` refused; `crm_resolve` description says what it cannot find; new local tool registered (registry row, label, non-render, panel-only, schema, dispatch). |
| New module | `app/services/chatbot/agent/quotation_lines.py` | `crm_project_quotation_lines(project_id, refs?)`: in process, as the user; project via `projects.get_project_or_404`; documents/scopes via `ProjectQuotation` rows; current versions via `serialize_quotations` fields; issued revisions via `quotation_issues` + `quotation_issue_scopes` (`models/projects.py:1368`, `:1759`) and `quotation_no` for the ref; lines via `project_quotation_service.list_lines`; compact rows only. |
| Route | `app/api/v1/projects/quotations.py:144-145` | Use the id `validate_uuid_path` returns. |

Mechanisms reused, not added: `_check_ids`/`seen_ids` guard, `cap_result` (16k chars), `TOOL_LABELS`, the
panel-only gate (`PANEL_ONLY_TOOLS`), REGISTRY slug + own-slug gate (as `crm_project_quotations_list`,
tools.py:137), `limit_sentence`/`status="limited"`.

## Changes

1. (a) Page ids seed `seen_ids` (AC-A1..A3).
2. (b) Refusal routing + argument shapes (AC-B1..B4). Static map of id argument to its finder
   (`project_id` -> `crm_projects_find`, `complaint_id` -> `crm_complaints_find`); every other id keeps crm_resolve.
3. (c) Clean ids before forwarding; single-id list refused; route uses cleaned id (AC-C1..C3).
4. (d) Partial reply on a failed final call after tool results; failure class traced (AC-D1..D4).
5. (e) `crm_project_quotation_lines` (AC-E1..E6).

## Tests (red first, tester writes, coder makes green)

- `tests/chatbot/agent/test_agent_quote_compare.py` (new): A, B, C (agent side), D, E (tool, on Postgres fixture
  with a seeded project, two documents, an issued revision).
- `tests/chatbot/agent/test_agent_round3.py:512` expectation changes to AC-D2.
- Route padded-uuid test (AC-C3) beside the existing quotations route tests.

## Live evidence

The owner's question on the panel of PPF2611008 (PRJQ-2026-0013 vs QT-2026-0003) and PPF2611003 (revisions), x3,
dev DB sorento_prod_1104, Gemini ledger lines before/after; rounds, tokens and answers in crew-done.

## Review rounds (10 Nov)

- Round 2 (reviewer + security-reviewer): the in-process read skipped the project router's "only theirs" guard
  (`_own_scope.check`) and the module guard; the partial reply would have reached WhatsApp contacts. Fixed: own
  scope + module guard on the tool, partial reply on staff panel turns only, provider failure class traced in
  `chat()`, `rate_only` on lines.
- Round 3-4 (live runs + crew pass): a line priced above list gave a negative discount the answer verifier
  cannot back ("-(not verified)"). Fixed: `discount_pct` only below list, `above_list_pct` above it, and the tool
  description says how to show both.
