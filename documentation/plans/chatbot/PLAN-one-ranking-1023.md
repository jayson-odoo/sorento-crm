# PLAN: one ranking function (lane REPORT-SMART-L, owner direction 23 Oct 09:05)

Status: owner rulings Q1 (a), Q2 (b), Q3 + ruling-2 (a) (23 Oct ~09:35: widens nothing); R0-R3c + R4a + R3d (small fix track) + R4b READY (security PASS on R1, R3b, R4a, R4b), main merged (f76a4545e4), CI fix 91c643f00a; next R5 (prompt candidate, non-production). Track: L (routing across two lanes, access change, retire path).
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
- R0 (S, crew 23 Oct): the ranking hold honours the parser's broaden_axis channel / product with broaden_to 'all'
  (drops that axis, keeps the rest; same-axis refine, across-all and the refine naming another axis). Date widening is
  out: the report ask route requires a period (api/v1/order_management/report_ask.py:283-284, :551); 'all-time
  rankings' is an owner question (crew). The bare-count candidates change was reverted (crew a1): it contradicted the
  closed-lists design (tests/chatbot/test_closed_lists_candidates.py:419, :437: a bare number that is part of codes is
  shown as holding them); the count goes to R5.
- R1 (M) routing: one `report_ask.from_top_selling` used by by_capability (every top_selling verdict) and at
  lanes/business/__init__.py:2356 (safety net for live sessions); rank_group item / none -> group_by product, category ->
  category; never the catalogue line or a grain question; questions per Q1; access per Q3.
- R2 (M) follow-ups / state: a top-selling-shaped refine under a sales_ranking_frame is ranking_refine; remove the re-pin
  (turn/apply.py:1494-1525) and the top_selling State line; 'by customer' keeps what is on screen (rulings S6-S6c, header
  "Across all products"); decide the held brand / category / agent (top selling kept them, the across-all hold does not).
- R3a (S) reply: WhatsApp split (top_n to 1000), "no sale is not ranked" line, localisation (`_report_ask_output` never
  localizes: AC-CL33 tests/chatbot/test_chat_language_slice3.py:651-779), category code. R3b (M) agent fill-rate note
  (services/sales_report_service.py:741-752) on the report ask route. R3c (M) per Q2 (row pick / outstanding).
- R3d (S, small fix track, R4a review follow-up, BEFORE R4b): since R1 an ms / zh contact reads an item ranking's
  head line ("Top 10 products by delivered sales"), miss line ("No delivered sales found"), the route refusals ("You can
  only see sales for your own account.", "That breakdown is not available for your account.") and the Period value's
  "to" in English (the old lane localized each; measured 23 Oct by rendering the R3a fixture through
  `fetch.output_structurer` with an ms / zh Localizer). ARCHITECTURE: localization stays in `label_catalog` (layer: the
  backend's reply pass; the MCP presenter, shared with n8n, stays English). Shared mechanism: the catalog's `{token}`
  templates; the head is built from three vocabularies (rank noun, count measure, basis label), so its tokens' VALUES
  translate only when catalogued (as `{names}` already does) and a line with an unknown word stays as printed. Classes
  fixed: every sales group_by's head (not only items), the miss line per basis, every report-ask 403 line, the
  `d Mon yyyy to d Mon yyyy` period range. Out: the chat dataset (staff console), the `Total ...` / `and N more` / `pcs`
  words (English on every report-ask ranking before R1 too; listed in the final report).
- R4 (L, a + b) retire from the chatbot: lane branch and helpers, engine / apply top selling code, top_selling_pick,
  Focus.top_selling (a held status top_selling loads as None), policy rows via a migration (turn/policy_rows.py:169, :339,
  :387; reverse alembic chatbot_top_selling_tool; add crm_report_ask to the sales row); delete the 194 top-selling lane
  tests and 3 console cases; route, MCP tool and connector stay.
- R5 (S) prompt candidate (fold template :317 into :316; :75 / :99 / :110 / :320 / :358), NON-production; the owner publishes.
  R5 also carries: 'the N in top / bottom N is top_n, never a product; a holding line is never a pick' with gold rows incl.
  the owner's 'Top 100 selling item this year by product, delivered qty' (crew a1); v101 lines 53 / 297 / 310; 'only those N'
  as a scoped example; 'all channels' -> broaden_axis channel.
- Also queued: owner turn 045fb9bb ('Top sales for cb6635 in 2026, by salesppl' -> monthly report), v101 lines 53 / 297 / 310.

## Access differences the merge makes (Q3)
- Wider: an ungranted live salesperson gets items from their own customers (contact_asker.py:150-160, report_ask route
  :362-367; today refused, pinned tests/chatbot/test_report_smart_salesperson_gate.py:116-134).
- Wider: a granted contact that is unlinked and not staff gets 403 on top selling (orders.py:2075-2079) but report_ask does
  not scope it (_contact_scope.py:56-66): it would see every customer.
- Narrower: dealers lose the channel and agent filters. New: 10 reports / 10 minutes; fails closed with no company row.

## Access rulings as built (owner 23 Oct ~13:00, crew (a))
Nothing widened, nothing narrowed: item / category rankings stay refused for a granted contact that is unlinked and
not staff (top selling's 403, kept on the report ask route in R1); customer / brand / month rankings and totals stay as
today for that contact (owner ruling (b) 'leave it'); ruling 2 'my ...' own-book for an ungranted live salesperson.

## Risks
Access (Q3); the connector / any n8n caller (route kept); sessions mid-ranking at deploy (R1 safety net); the claim regex
after take_words (engine.py:2902-2933); the prompt label (owner only).
