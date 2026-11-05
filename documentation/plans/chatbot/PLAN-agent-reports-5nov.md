# PLAN: AGENT-REPORTS - sales / outstanding report asks and their follow-ups on the agent path

Status: Plan (behaviour card posted as crew-ask, waiting on owner answers; build has NOT started). Track: full (routing
change on staff chat, permission scope of a data tool, likely one settings column).

Owner (5 Nov ~15:50 MYT), after a prod chat on parser prompt v72 where every follow-up failed: "should we just use agent
for this" -> yes. Sales / outstanding report asks move to the agent path, behind a switch that is OFF by default.

## Measured facts (read from main @ f2822745)

1. The shared report service already exists and the agent already has it as a tool: `crm_report_ask`
   (`app/services/chatbot/agent/tools.py:111`) calls `GET /api/v1/order-management/report-ask`
   (`app/api/v1/order_management/report_ask.py:228`). Filters: basis, measure, group_by (incl. `channel`,
   `brand`, `category`, `account_type`), top_n, brand_ids, category_ids, customer_ids, sales_agent_ids, channel,
   account_types, company, compare_to, mine. No new SQL is needed; the agent never writes its own (REPORT-UNIFY).
2. Basis is never defaulted on the agent path: `tools.py:1267` returns `SALES_BASIS_MESSAGE` (`tools.py:1112`) when
   `basis` is missing. Unpaid needs `finance.billing_documents.view` (`tools.py:169`).
3. Who answers a panel/console message is decided by `router.decide_route` (`app/services/chatbot/router.py:72`):
   state rules first, then the Jev classifier picks `chat` (today's parser + report lane) or `agent`.
   Report asks land on `chat` today: `agent_tool_labels` (`router.py:300`) deliberately leaves `REGISTRY` tools
   (which includes `crm_report_ask`) out of the agent's label list "because the bot answers those lookups too".
4. Two state rules keep a follow-up on the bot even if it should go to the agent: an open parser question
   (`router.py:89`, `session_state.pending_of` / `_bot_asked`). That is exactly the T4 -> T5 trap.
5. Agent memory replays earlier tool calls as one line each, with args clipped to 160 chars
   (`app/services/chatbot/agent/memory.py:22`, `digest_line` at `:88`). A report's filters (ids for brand, category,
   company...) do not survive that clip, so the agent cannot see what the last report held. This is the core fix.
6. Agent default provider is Gemini (`loop.py:57-58`, `gemini-3.5-flash`), matching "staff = Gemini, no OpenAI".
7. The per-contact agent switch is `respond_contacts.chatbot_agent_enabled` (`app/models/access.py:352`, default false;
   `access.agent_switch_on` at `access.py:94`). A panel (staff principal) turn has no contact gate
   (`access.py:66-69`).
8. PR #2188 (AI-QUERY-CORE) adds `crm_query` / `crm_describe` over a registry (orders, products, SCM POs, complaints).
   It does NOT cover sales/outstanding reports and must not: reports stay on `crm_report_ask`. PR #2189 is the
   AI coverage CI gate + eval case type `assistant` (`scripts/chatbot_eval/cases.py`), not chat routing; this lane
   uses its eval case type if it has merged, else the existing gold runner.
9. Gold: `scripts/chatbot_eval/gold/parser_report_totals_filters.jsonl` (34 cases, parser-shaped `report_ask` expect).

## Design (smallest thing that works)

- **Switch** `chatbot_agent_reports` (one boolean, default OFF). Proposed home: `system_settings` (one column, one
  migration) with panel + WhatsApp as one switch; see Q1. When OFF, nothing changes: the parser path answers as today.
- **Route**: when ON, `decide_route` sends a report ask, and every follow-up while a report is held, to the agent.
  Mechanism: add the report label to `agent_tool_labels` for a user who may use `crm_report_ask`, plus a state rule
  "the last done turn was an agent report turn under an hour ago -> agent" (same shape as `_agent_asked_back`), so
  "clear all" / "all" never fall to the parser.
- **Report state block**: each agent turn gets a short system block "Current report: basis, company, brand(s),
  category(ies), channel, period dd/mm/yyyy, group_by, measure" built from the LAST successful `crm_report_ask` call
  of the conversation (full args, names resolved), not from the clipped digest. The prompt rule: every report call
  states its full filters; to change one, call again with the new set. No per-phrase code.
- **Render**: the agent returns the tool's render envelope, so the panel shows the same report card (title, filter
  lines, rows, total) as today.
- **Scope**: the tool runs as the asking user (`run_as_user`, company + brand scope + `sales_orders.sales_report`
  reveal); no new permission.

## Behaviour card (the T1-T7 transcript is the acceptance test)

| # | User | Expected reply |
|---|---|---|
| T1 | Total quantity sale for Sorento brand kitchen sink on September 2026 | Sales by invoiced sales; Company Sorento; Brand SORENTO; Category Kitchen Sink; 01/09/2026 - 30/09/2026; Total 2,270 pcs, RM 1,066,977.87 |
| T2 | sorento total slaes delaer and proejct | Same filters, broken down by channel: Dealer row, Project team row, total = T1 total |
| T3 | clear all | Every held filter cleared; one short ask "Which period and what would you like to see?" (see Q3) |
| T4 | sorento total slaes by delaer and proejct | NO "brand, account type or company?" ask. "Sorento" read from context (held company Sorento before the clear; recommendation: the bare word is the company when nothing else decides it, see Q4); breakdown by channel; asks only what is still missing (period) |
| T5 | all | Answers T4's open ask: whole period choice per the ask; channel breakdown |
| T6 | all brand all category | Brand and category widened to all; other filters kept |
| T7 | for all brands and categories | Same as T6 (idempotent) |

Rules: no "sorry"/"busy" replies; dates dd/mm/yyyy; basis asked when unknown (invoiced offered first), never
defaulted; customer vs supplier decided by the domain (sales = customer); a bare "Sorento" asks once company/brand
only when nothing in context decides it.

Edge cases: ambiguous name with no context (asks once); unknown basis (asks, invoiced first); a user without
`sales_orders.sales_report` or with a narrower company/brand scope gets only their scope (tool refuses, agent says
it has no access, no figures); unpaid without billing slug refused; switch OFF = today's behaviour unchanged.

## Questions for the owner (crew-ask on PR #2201, same numbering)

1. Switch scope: (a) panel + WhatsApp now, (b) one setting, panel only this lane. Rec (b).
2. Switch home: (a) `system_settings` column, (b) per contact `chatbot_agent_enabled`. Rec (a).
3. OFF = parser untouched; ON = no parser fallback once the agent is chosen. Rec yes to both.
4. T3 "clear all" alone: (a) ask period + what to show, (b) company-wide total this month. Rec (a).
5. Cost: (a) existing agent budgets + daily turn cap, USD per eval run reported, (b) new per-turn cap. Rec (a).

Working assumption (not asked; the card states it): a bare "Sorento" right after a clear reads as the company that
was held before the clear; with no context at all it asks once company or brand.

## Steps after the answers

1. Red tests (pytest): router sends report asks + follow-ups to the agent only when ON; OFF unchanged; report state
   block holds the last call's full filters; T1-T7 tool-call expectations with a stubbed model; scope tests (other
   company, no reveal slug). Kill tests by reviewer.
2. Implement: switch column + settings dict builders + admin toggle; router rule + label; state block in loop; prompt.
3. Eval: T1-T7 + 34 totals-filters gold as agent cases, dev Gemini key only; pass rate + USD per run in the PR.
4. Reviewer + security reviewer; cloud browser pass on the panel; hand-test script `laneboard/scripts/<PR>.md`.
