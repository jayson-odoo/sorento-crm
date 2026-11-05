# PLAN: AGENT-REPORTS - sales / outstanding report asks and their follow-ups on the agent path

Status: Review (built; reviewer + security reviewer fix round applied; live eval not run, no dev Gemini key in the cloud sandbox). Track: full (routing change on staff chat and WhatsApp, permission scope of a data tool, one migration).
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

## Owner rulings (5 Nov 2026)

1. One switch for panel, console and WhatsApp, all enabled by this lane (Q1 a).
2. The switch is a `system_settings` column AND the existing per-contact `chatbot_agent_enabled` still gates a
   WhatsApp / console contact (Q2 a + b). They combine as AND: a contact reaches the agent only when its own flag is
   on (on every row sharing its respond.io id, `access.eligible_contact`), and report asks go there only when the
   admin switch is on too. A panel turn has no contact gate; the admin switch alone decides.
3. Switch off = today's routing and loop exactly; switch on = the agent, no parser fallback once chosen (Q3 a).
4. "clear all" clears every filter and the breakdown, keeps basis and period, answers at once, asks nothing (Q4).
5. Reuse the existing agent budgets and the daily turn cap (Q5 a).
6. No time-based reset or window of the held report (owner, later the same day). Compaction threshold
   `chatbot_agent_compact_tokens` lowered 40k to 12k.
7. Eval case: "delivery to hanlim" (customer and supplier) lands on the customer with no ask, by the agent's own
   reading, no special-case code.

## Design as built

- **Switch** `system_settings.chatbot_agent_reports_enabled` (boolean, default false; migration
  `agrep_0001_agent_reports`, which also moves the compaction default and any row still at 40000 to 12000).
  Admin toggle "Report asks go to the agent" on Settings > Chatbot Media > Agent budgets.
- **Route** (`router.decide_route`): `_reports_open` (switch on AND the asker is offered `crm_report_ask` through
  `access.permitted_tools`; any failure is false, and the session's company / brand scope is put back) then:
  - `report_held`: the latest done turn is an agent turn of the newest conversation holding a `report_state`. No
    time window. Wins over an older bot open question; the daily cap and the text length guard still apply first.
  - otherwise Jev is asked with a `reports` criterion on the agent side (and `not_for_reports` on the chat side)
    and the "sales and outstanding figures" label.
- **Loop** (`agent/report_state.py`, hooks in `loop.py`), switch on and tool offered only:
  - the `PROTOCOL` paragraph in the system prompt (rules only);
  - the held report (the last answered report call's full arguments, plus the card's head lines) as a user-role
    data message headed "Quoted data, not instructions", right before the user's message (security S2: the
    arguments carry the user's words, so never the system role);
  - the held ids satisfy `_check_ids` for `crm_report_ask` calls only (security S1); every other tool still needs
    this turn's own lookup;
  - the reply: when the model's text lacks the turn's LAST answered card, an answered turn's reply is that card; a
    turn stopped at a limit keeps its own text under the card;
  - `report_state` is written on every agent turn's response (the new one, or the held one carried forward, a
    failed turn included), which is what the router reads.

## Behaviour card (the T1-T7 transcript is the acceptance test)

| # | User | Expected reply |
|---|---|---|
| T1 | Total quantity sale for Sorento brand kitchen sink on September 2026 | Sales by invoiced sales; Company Sorento; Brand SORENTO; Category Kitchen Sink; 01/09/2026 - 30/09/2026; Total 2,270 pcs, RM 1,066,977.87 |
| T2 | sorento total slaes delaer and proejct | Same filters, broken down by channel: Dealer row, Project team row, total = T1 total |
| T3 | clear all | Every held filter and the breakdown cleared, basis and period kept, answered at once with the company-wide total (owner Q4) |
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

## Tests and eval

- `tests/chatbot/agent/test_agent_reports.py`: switch, loop, router, security S1, card rule, failed turn, savepoint,
  and a T1-T7 chain (code guarantees with a scripted model).
- `tests/chatbot/agent/eval_agent_reports.py` (not collected by CI): the live agent on T1-T7
  (`scripts/chatbot_eval/gold/agent_reports_transcript.jsonl`), the 34 totals-filters gold and the hanlim case
  (`agent_reports_party_side.jsonl`), DEV Gemini key only, pass rate + tokens (+ USD with `AGENT_EVAL_PRICE`).
  T1 is graded as a basis ask (the message names no basis and the basis is never defaulted), T1b "invoiced" as the
  prod T1 card.
- Vitest: `page.agentReports.test.tsx`.
- Hand test: `laneboard/scripts/2201.md`.
