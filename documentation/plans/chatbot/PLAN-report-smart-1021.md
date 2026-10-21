# PLAN: smarter chatbot reports (lane REPORT-SMART-1021)

Status: built, review round 1 fixed (B2, S1-S4), re-review pending; exploratory build for the owner hand test 21 Oct 21:00 MYT. Track: L (diff over 300
lines; no migration, no auth/RBAC change, no new ingest surface). Branch `claude/report-smart-1021-r2xexf` (cloud
sandbox; stands in for `crew/report-smart-1021`), base `claude/release-chat-1021-sppzcw` 9d64921e9 with PR #1721
(`crew/chat-fix-reports` 52b336345) merged in at cf7aded65.

## Goal

Owner 15 Oct: "the report engine, it is not very smart and dynamic". 30 days of dev chat: 384 report turns, about 84
failed or weak; the splits people wanted were by sales agent (37), customer (35), product (20), month (10).

Rulings that bind: MCP tools are the only executor (no raw SQL); the parser outputs params and CODE picks the tool (no
agent loop); no regex or keyword rules over the message, no fuzzy matching; every missing detail asked in ONE question,
no silent default (16 Oct); generalise, never per case; never a code or UUID on screen.

## Facts (base cf7aded65, paths under `sorento_crm_backend/app/services/` unless shown)

- The tool was picked by `order_status` alone (`chatbot/lanes/business/__init__.py` run_fetch), so "total sale for all
  sale agents in September" (sales_analysis, group_by sales_agent) answered "I can't break sales down by sales_agent
  yet", and "top 10 dealers selling <product>" (top_selling, group_by customer) listed the top items overall.
- `reports/engine.py` already aggregates `count_distinct` measures (`_aggregates`, `_distinct_by`); the sales ask
  datasets declared only amount and qty (`reports/datasets/sales_order_lines_ask.py`).
- #1721 hand test step 7: a re-typed whole ranking with a channel word ("..., dealer sales only") parsed as a refine
  (the prompt maps a channel word to `ranking_refine` true) and re-ran the held frame with the held basis and measure.
- `fetch._top_selling_output` printed a result the presenter never rendered as its text (`[object Object]` for a
  body, the tool error string verbatim, the likely path of the raw INVALID_UUID a user saw).
- A period the parser wrote in words ("SEP 2026") was run: the analysis answered "Could not run the sales report right
  now.", the sales report echoed "Dates: SEP 2026".

## Changes (each red-first)

1. A re-typed ranking starts a new frame (`report_ask.restates_the_ask`): a refine-flagged verdict that names its own
   `group_by`, or carries a `new_subject` op, is read as a fresh ask, in `settle` and in `as_held_refine`.
2. Capability table (`report_ask.CAN_DRAW`, `by_capability`, engine seam before `hold_words`): an axis the named kind's
   tool cannot draw but `crm_report_ask` can sends the ask there (by sales agent, customer, product, brand, category,
   location, channel, month, with the product, customer, agent and brand filters). A breakdown that is not a ranking
   lists every row (up to 100) instead of asking how many. Dealer limits unchanged (lane DEALER_KEYS, route 403).
3. Count measures customers, orders, products: dataset columns, `reports/ask.run_ask`, schema, route, MCP presenter and
   catalog, lane. Parser `measure` enum lines handed to crew (CHAT-CLOSED-LISTS-L owns the prompt).
4. Stretch: `compare_to` previous_period | last_year, with the earlier figures and the change in percent on every row
   and the total. Parser field lines handed to crew.
5. A report failure is a clear sentence: the top selling output never prints raw tool text; an unreadable period is
   asked.

## Parser half (not in this lane, named)

Steps 3 and 4 need two parser fields: `measure` customers | orders | products and `compare_to` previous_period |
last_year. The parser schema and prompt are parser input, owned tonight by CHAT-CLOSED-LISTS-L; the exact lines are on
PR #1816 (crew-notes). Until they ship, live chat cannot reach a count or a comparison: the route and MCP tool serve
them (n8n agents), and the lane reads both fields the moment the parser emits them.

## Review round 1 decisions

- A breakdown's every-row count is a flag (`report_breakdown`) read only by a fresh ask in `settle`, never written as
  `top_n` on the verdict: an answer parsed as another report kind with the axis echoed still asks how many (B2).
- A month breakdown is not compared (route 422 `compare_by_month`, lane says so): its rows are named by month and the
  earlier window's months never match (S1). Trigger to build month shifting: an owner ask for a compared trend.
- A held `compare_to` rides on the frame: refines keep comparing until a new ask (a new frame) drops it.

## Out (named)

- Example 7 ("top 200 project hot selling item": cap and a stale brand from earlier chat) and example 8 (a total for an
  earlier product family): top selling slot carry and sales report subject carry, not the tool pick. Trigger: crew's
  EVAL-BENCH on this head still failing them.
- The dealer "what is my sales this month" "Could not run": not reproduced from the masked text; an unreadable period
  is one cause now fixed.

## Gates

Red-first test commits per step; backend report and sales chatbot set plus the report ask route suites green locally
(sandbox Postgres 16 + pgvector + Redis), MCP suite green; reviewer subagent with a kill test; crew's EVAL-BENCH runs the
25-chain report slice and the 8 real asks on this head.
