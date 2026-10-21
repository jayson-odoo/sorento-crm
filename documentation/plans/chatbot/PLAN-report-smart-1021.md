# PLAN: smarter chatbot reports (lane REPORT-SMART-1021)

Status: built; EVAL-BENCH re-run fix (State domain switch) reviewer READY, lane REPORT-SMART-L 21 Oct; exploratory build for the owner hand test 21 Oct late MYT. Track: L (diff over 300
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

## EVAL-BENCH fix (21 Oct, crew notes 6311920067, 6312015162)

The live parser repeats the held axis, count and measure on most refines (98 of 130 live refines carry a `group_by`), so
step 1's `group_by` test turned "ordered" into a fresh ask that lost the period, and the next re-typed ask was eaten as
that period's answer. Now only the parser's `new_subject` op restarts the frame (`restates_the_ask`); a refine naming its
own entity or `new_subject` is never an open question's answer (`names_its_own_ask`). A whole ask typed again that the
parser flags as a plain refine re-runs the held report with what it names: the parser decides, and the prompt half
(emit `new_subject` on a fully re-typed ask) is CHAT-CLOSED-LISTS-L's.

## EVAL-BENCH re-run fix (21 Oct, crew note 6312251738, lane REPORT-SMART-L)

Steps 5-6 still failed on bcbc823214 with the State prompt on (turn 516a6b39). Not report_ask: step 4's refine ran and
`turn_runtime._report_status_means_order_domain` wrote the turn's domain `sales` (a sales figure status); step 5's
parse names the same ask with the prompt's `domain_hint "order"`, and `chat_state.apply_changes` (engine.py:5015, before
that seam at :5082) read raw `order` against the held `sales` as a domain switch, so `_drop_domain_bound` dropped the
held report frame. The refine then ran as a fresh ask with no period ("Which period?") and step 6 was that slot's answer.

ARCHITECTURE. Layer: the State's domain-switch check (`chat_state._message_domains`). Shared mechanism: the ONE domain
normalisation the turn already writes with (`turn_runtime.report_domain`, a copy wrapper over
`_report_status_means_order_domain`), now read by the State for the `order`/`sales` alias pair before it compares
domains. Other classes fixed: every sales figure status (`sales_report`, `sales_analysis`, `top_selling`,
`sales_ranking`) under the prompt's `order`, and the reverse (`sales` with no sales status is the order ask, so a held
order list is not switched away). Special cases removed: none added; no report_ask rule, no words.

Guards: any other named domain stands as named, so a stock ask echoing a held sales status is still a switch
(`test_r10_restated_dropped_values_do_not_survive_the_switch_to_a_stock_ask`, which the first, unscoped version broke);
and a `status` equal to the held one is an echo, not the message's report kind, so an outstanding ask under `order`
after a held top selling ranking is still the switch (review should-fix 1).

Named, not fixed here: `master_products` / `inventory` with a sales status, and mixed `asks`, still read differently by
the State and the turn (as before this change). A held order list followed by a sales figure ask is now a switch, so
the held status and sort drop (the turn already writes `sales` for it), and a message naming its own product rebuilds
the subject (CHAT-STATE r8 rule). A parse of `domain_hint sales` with no sales status in either field on a refine after
a held `sales` report is now a switch (frame dropped); the prompt has the parser repeat the status or null the domain
(`head/parser_template.py`), so it is not seen live.

Red-first: `tests/chatbot/test_report_smart_step7.py` state-on console tests and chat_state unit tests (red f1c864e3e2,
should-fix red 224b848032); the console fixture runs state-off, which is why the earlier tests could not see it.

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
