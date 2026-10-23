# PLAN: one ranking function (lane REPORT-SMART-L, owner direction 23 Oct 09:05)

Status: PROPOSED, waits crew OK and the 3 owner questions. Track: L (routing across two lanes, access change, retire path).
Branch `claude/report-smart-1021-r2xexf` (PR #1816), base head 412255c5b4. UAC: `one-ranking-1023-acceptance-criteria.md`.
Evidence: owner's 08:52 turns (crew/state/eval/report-smart-v92/owner-0852-diagnosis.md); code map at 412255c5b4 (below).

## Why
Two ranking contracts: top selling holds its values on focus.top_selling (no open question, no FieldSpec), the sales
ranking on focus.required_ask (FieldSpecs). When the parser labels a reply sales_ranking under a top selling question,
nothing carries the values across (owner T2: 'Delivered qty' lost top 30 / items). The parser's rank_group 'item' is read
nowhere by the sales ranking, so an item ask lands on the catalogue line (T1-T3). Owner: ONE ranking function.

## ARCHITECTURE
- One path: every ranking ask (items, categories, customers, agents, brands, locations, channels, months) goes to
  `crm_report_ask` (services/reports/ask.py run_ask; chatbot lanes/business/report_ask.py). The numbers already match:
  tests/test_report_ask_route.py:690-745 pins report_ask product / category == top_selling() on both bases and measures.
  No SQL change. `by_capability` (report_ask.py:297-343) already sends top_selling with any other axis there.
- The parser decides (no word tables, no claim regex): order_status top_selling + rank_group item -> group_by product,
  category -> category; top_selling stays an alias label in code until the owner moves the prompt.
- Kept separate: crm_sales_report (period totals), the outstanding reports. Kept: the top selling ROUTE and MCP tool
  (the analytics connector calls it with no contact, services/analytics_connector/reused_tools.py:907); retired only from
  the chatbot.

## Rounds (each red-first, reviewer each; security-reviewer on R1 and R4: access)
- R0 (S) parser input: a bare count is never a "codes holding it" candidate (candidates.py:374 sends every 3+ char token
  with a digit; `_is_number` :191 unused there; owner T4 '100' -> M1100 -> stock). Plus "all channels" drops a held channel
  (the ranking lane ignores the parser's broaden_axis).
- R1 (M) routing: one `report_ask.from_top_selling` used by by_capability (every top_selling verdict) and at
  lanes/business/__init__.py:2356 (safety net for live sessions); rank_group item / none -> group_by product, category ->
  category; never the catalogue line or a grain question; questions per Q1; access per Q3.
- R2 (M) follow-ups / state: a top-selling-shaped refine under a sales_ranking_frame is ranking_refine; remove the re-pin
  (turn/apply.py:1494-1525) and the top_selling State line; 'by customer' keeps what is on screen (rulings S6-S6c, header
  "Across all products"); decide the held brand / category / agent (top selling kept them, the across-all hold does not).
- R3a (S) reply: WhatsApp split (top_n to 1000), "no sale is not ranked" line, localisation (`_report_ask_output` never
  localizes: AC-CL33 tests/chatbot/test_chat_language_slice3.py:651-779), category code. R3b (M) agent fill-rate note
  (services/sales_report_service.py:741-752) on the report ask route. R3c (M) per Q2 (row pick / outstanding).
- R4 (L, a + b) retire from the chatbot: lane branch and helpers, engine / apply top selling code, top_selling_pick,
  Focus.top_selling (a held status top_selling loads as None), policy rows via a migration (turn/policy_rows.py:169, :339,
  :387; reverse alembic chatbot_top_selling_tool; add crm_report_ask to the sales row); delete the 194 top-selling lane
  tests and 3 console cases; route, MCP tool and connector stay.
- R5 (S) prompt candidate (fold template :317 into :316; :75 / :99 / :110 / :320 / :358), NON-production; the owner publishes.
- Also queued: owner turn 045fb9bb ('Top sales for cb6635 in 2026, by salesppl' -> monthly report), v101 lines 53 / 297 / 310.

## Access differences the merge makes (Q3)
- Wider: an ungranted live salesperson gets items from their own customers (contact_asker.py:150-160, report_ask route
  :362-367; today refused, pinned tests/chatbot/test_report_smart_salesperson_gate.py:116-134).
- Wider: a granted contact that is unlinked and not staff gets 403 on top selling (orders.py:2075-2079) but report_ask does
  not scope it (_contact_scope.py:56-66): it would see every customer.
- Narrower: dealers lose the channel and agent filters. New: 10 reports / 10 minutes; fails closed with no company row.

## Risks
Access (Q3); the connector / any n8n caller (route kept); sessions mid-ranking at deploy (R1 safety net); the claim regex
after take_words (engine.py:2902-2933); the prompt label (owner only).
