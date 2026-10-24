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
- R5 follow-ups from EVAL-BENCH EXPLORE-1023C (24 Oct; :3105 = main + #1816 b830f31ca6, gemini-3.5-flash-lite, v101):
  row 4: a refine naming another axis while a question is open swaps that axis into the open ask (filters kept, only owed
  fields asked; an answer that fills a field stays an answer) (8a322acb5e red, d29ad668d5); row 5: prompt v102 contrast line
  (an item ranking with no basis / measure word leaves both null; flash-lite 40% -> 73% on that class) + gold c74f6fb2a4;
  owner rulings 24 Oct 08:10 (ask a40448868): (A) a1 'Top sales for X in 2026' with no 'by' stays a TOTAL (no axis question,
  no default axis); (B) b2 row N of an agent / customer ranking opens that row's detail (agent -> its customers, customer ->
  its products, plus months; period / product / basis held), the item pick rule (ed44bae38d red, f9aaca0573).
- R6 (M, crew (A') (b) 24 Oct ~11:00): ruling A in code. The parser gets ONE new field `by_words` (first named `axis_words`): the verbatim words of the
  CURRENT message that name what is ranked or grouped (a "by ..." phrase: "by salesppl", "ikut pelanggan", "按客户"; or the ranked
  noun: "salesppl" in "top 5 salesppl", "items" in "top 30 selling items"), null when the message names no axis ("Top sales for
  CB6635 in 2026"). ARCHITECTURE: layer = the parser contract (schema + prompt v104) and one reader in the report ask lane
  (lanes/business/report_ask.py, where group_by is taken from a verdict); no word list in code, the parser decides what an axis
  word is. Rule: a verdict whose `axis_words` key is PRESENT and null names no axis, so its group_by is not typed (a fresh ask is
  a TOTAL; a refine changes no axis); a verdict WITHOUT the key (v92 production and every older version) behaves exactly as
  today. Classes fixed: axis-less top / best / tertinggi / 最高 sales asks on any model; a guessed axis on a refine. Also in v104:
  (B') "<channel> is channel" / "only project" under a held ranking is a channel refine (prompt + gold; crm_sales_report's own
  channel basis, market segment vs SO type, is the owner's separate question, not changed here); R-P3-16: self_reference only from
  a first-person word in the current message. Measure: gpt-5.4-mini first (checkpointed x1, x3 only if close), then ONE
  gemini-3.5-flash-lite x1 run on the org key under crew/state/eval/gemini-org-key-ledger.md.
  R6 outcome (24 Oct ~12:10): code READY (Opus) and shipped INERT: the field is offered and read only when the rendered prompt
  defines `by_words`, and no published prompt does. Candidates v104 / v105 / v106 defined it; gemini-3.5-flash-lite read it exactly
  (v105 22/22 on the target classes), gpt-5.4-mini misread it on every wording (writes 'top sales' / 'jualan tertinggi' / '销售最高' as
  axis words; class a 2/6 vs v103 6/6). Crew (c): v103 for both models; ruling A stays prompt-only until a model reads the field.
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
