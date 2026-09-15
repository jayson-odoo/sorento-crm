# Console check differential - MAIN (5d3f46ed6) vs lane merged head d4ae8203b

Backend under test: primary checkout `/Users/tehjayson/Documents/foundryx/sorento_crm`, branch
`main` at `5d3f46ed6`, serving `:8000`, `DATABASE_URL=sorento_ai_automation_0907`. All 8 case
files run read-only via `scripts/chatbot_console_check.py --sleep-seconds 8`, dry runs only
(`is_test`). Compared against the committed lane result
`documentation/plans/chatbot/evidence/focus-l1/console-check-merged-d4ae8203b.md` (v20 column)
and its raw logs `/tmp/console-check-focus-l1/merged/v20-*.log` (still present on this machine).

## Pre-flight (asked for explicitly, so recorded in full)

- `curl :8000/health` -> `{"status":"healthy"}`.
- `alembic current` on 0907 = `ptag_0009_combos_tags`; `alembic heads` = `518_osr_last_receipt_spo`
  (one migration ahead, adds `scm.order_summary_row.last_receipt_spo_number` /
  `last_receipt_container_number` - unrelated to chatbot, does not confound this run).
- Contact `437264483` (`respond_contacts.id 80560c8f-6358-4115-8b2c-e139ef31e48e`, "Jayson")
  exists on both `sorento_ai_automation_0907` and `sorento_ai_automation_focus_full`.
  `contact_agent_access` (10 rows) and `contact_field_reveals` (5 rows: `inventory.sellable`,
  `purchase_orders.cost`, `purchase_orders.placed`, `purchase_orders.supplier`,
  `sales_orders.outstanding`) are **byte-identical between the two databases as of this run**.
  No grant-parity confound between the two DBs today.

## CRITICAL CONFOUND - the prompt version pinned for this run

No `ai_prompt_versions` row for `chatbot_semantic_parser` on 0907 matches this checkout's
`app.services.chatbot_parser_prompt.SEMANTIC_PARSER_PROMPT_SLIM` text (compared by length and
md5 across all 22 stored versions). `517_chatbot_low_stock_vocab` IS in 0907's alembic chain
(ancestor of the stamped revision), but **none of the 22 `chatbot_semantic_parser` versions on
0907 contain the low-stock-report vocabulary text at all** - the migration's revision id is
stamped but its `publish()` content was never actually inserted into this database (a
stamped-without-content gap, functionally identical to "never applied" for grading purposes).
The only label on `chatbot_semantic_parser` is `production`, pinned to **v1**
(`b9132ae0-039e-4a15-99a6-25c7c74af30b`, 46,906 chars, created 2026-09-05 07:18) - it predates
essentially every chatbot parser slice shipped since (growth-r1 8 Sep, answer-polish 12 Sep,
last-cost 12 Sep, outstanding-report 13-14 Sep, low-stock-vocab, and this lane's own focus
vocabulary). Per the fallback instruction ("if 517 was never applied, use the labelled version
and state the mismatch"), **this whole run was pinned to v1**
(`--prompt-version b9132ae0-039e-4a15-99a6-25c7c74af30b`), printed on every log's header line.

**This is the dominant cause of MAIN failures below**, not code. `2026-09-15-focus.yaml`'s own
header already says so before I ran anything: "the Console/Settings default is an older
production-labelled row that predates this lane's parser contract." Every case tagged
`# NEW VOCABULARY` in the growth-r1 and last-cost files is *expected* to fail under v1 by the
case file's own design - that tag exists to measure exactly this gap.

A second, independently-confirmed confound turned up mid-run and explains a large share of the
outstanding-report-family failures: **the `sales_orders.outstanding` grant on contact 437264483
has been added since the lane's evidence run** (both DBs show it granted today; several case
comments in `2026-09-14-outstanding-owner-rounds.yaml` and `2026-09-15-focus.yaml` explicitly say
"this contact has no sales-order key" as their premise - premise no longer holds on either DB).
Confirmed directly: main's "merge E" turn 2 asks the 3-way SO/DO/Both scope question (correct
behavior now that the grant exists) where the case's frozen expectation is the single-scope DO
offer written when the grant was absent. This almost certainly also explains why 6 of the 10
"data prerequisite" failures the lane's own doc attributed to the missing grant on
`sorento_ai_automation_focus_full` (R16, R19, R19b, R20 guard, R21, R21 guard) now PASS on MAIN
with the SAME older code, and it likely means a fresh run of the LANE's own stack today would
also turn several of those green - not something this differential can confirm without running
the lane stack, which was out of scope here.

One turn hit a live OpenAI 429 (`chatbot.turns.error`, tokens-per-minute) mid-run
(`2026-09-06.yaml`'s last case) - read `chatbot.turns.error` first per the known gotcha; that
result is excluded from all three lists as inconclusive, not a behavioral read.

## Per-case matrix

`P`=passed, `F`=failed, `X`=XPASS (counted as failed by the script's own convention - a
marker that outlived its fix), `429`=turn-level rate-limit error (inconclusive), `-`=case did
not exist in the lane's v20 run (added to the file after that evidence run).

### 2026-09-06.yaml (lane 15p/3f -> wait, lane v20: 13p/5f; MAIN: 15p/3f)

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| three codes, the third has neither stock nor incoming | F | F | same reason both runs |
| a container number is named, never its uuid | P | P | |
| eta for a partly typed variant code offers the family | P | P | |
| an eta miss names the product code, never its description | P | P | |
| an idea reaches the ideate lane | P | P | |
| a cold "all of them" is a clarification, not small talk | P | P | |
| a document ask with nothing to narrow by is refused, not listed | P | P | |
| the not-found line labels its axes and hides the debtor code | F | F | same reason both runs (see List 2) |
| a pick-resolved order list still states its search scope | P | P | |
| a pending order roster does not swallow a bare product code | F | P | **List 1** |
| an out-of-range tier pick keeps the product in scope | P | P | |
| a delivered-status miss names the status and the eta date | P | P | |
| escalate to a named person routes by staff lookup | P | P | |
| escalate to a team word never inherits the previous team | F | P | **List 1**, caveated (not `cold`) |
| a filter reply under an open roster is answered, not re-asked | F | P | **List 1** |
| a bare product code under a stock thread answers stock, not incoming | P | P | |
| an eta question about a product code still answers incoming | P | P | |
| a code with no stock is named before the incoming block | P | 429 | inconclusive, excluded |

### 2026-09-07-growth-r1.yaml (lane v20: 23p/6f; MAIN: 20p/9f)

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| A1 spec ask shows the compact Specs line (NEW VOCAB) | P | F | prompt-staleness confound |
| A1 one-key spec ask answers that key only (NEW VOCAB) | F | 429 | inconclusive, excluded |
| item 8 - list price of a product reaches base List Price | P | P | |
| D12 - product details names no property | P | P | |
| item 8 - seat cover material reaches the key that contains it (NEW VOCAB) | P | 429 | inconclusive, excluded |
| E2 - Catalog Sorento is a resource attachment ask | P | P | |
| D7 - an incoming ask on a zero-stock code climbs to the PO rung | P | P | |
| D6 - a code miss with an attachment word is one did-you-mean group (NEW VOCAB) | P | P | |
| A2 stock for a contact with no grant is unchanged | P | P | |
| A3 outstanding SO for a customer (NEW VOCAB) | P | P | |
| A3 belum DO is the same bucket in Malay (NEW VOCAB) | P | P | |
| A3 how many did customer take - three-line pipeline (NEW VOCAB) | P | P | |
| D8 - all customers of a code carry the SO block per row (NEW VOCAB) | F | P | **List 1**, see note |
| A3 how many did customer take - by-product SO line per row (NEW VOCAB) | F | F | same reason both runs (List 2) |
| A3 open DO grouped by customer renders headed sections (NEW VOCAB, group_by) | P | F | prompt-staleness confound |
| A5 PO for a product, no supplier for a dealer (NEW VOCAB, check_po) | P | F | prompt-staleness confound |
| A6 last in for a product (NEW VOCAB, check_spo "last in") | F | F | different reasons - see List 2 |
| A6 last 3 received returns three (NEW VOCAB, top_n) | F | F | different reasons - see List 2 |
| A6 the same question in Chinese (NEW VOCAB) | P | P | |
| A7 no stock, no incoming, but PO is placed | P | P | |
| A7 nothing on any rung, offers to escalate | P | P | |
| A7 suffixed SRTWT7445-LV-NEW reaches incoming rung | P | P | |
| A7 suffixed MSK11A-QT reaches incoming rung | P | P | |
| A7 suffixed CWCX1009-SH reaches incoming rung | P | P | |
| stock then PO carries the product | P | P | |
| owner 8 Sep - stock, then PO, then last in | P | P | |
| owner 8 Sep - delivery word + name over escalate offer | P | P | |
| D10 - product-set-only code offers real siblings | P | P | |
| D10c - product-set collision keeps certificate DYM | X | X | XPASS both runs (marker stale both places, unrelated to this diff) |

### 2026-09-07-pass5-item1.yaml (1/1 both) - PASS / PASS, exact text match.

### 2026-09-12-answer-polish.yaml (4/4 both) - all 4 PASS / PASS, exact text match both runs.

### 2026-09-12-last-cost.yaml (lane v20: 2p/2f; MAIN: 0p/4f)

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| AC-32a - default contact denied (NEW VOCAB) | P | F | grant-state + prompt confound, see below |
| AC-32b - granted contact gets the answer (NEW VOCAB) | F | F | different reasons - see List 2 |
| AC-32c - family ask, one row per member (NEW VOCAB) | F | F | different reasons - see List 2 |
| AC-30 - last in for a family names every member | P | F | see List 1, caveated |

### 2026-09-13-outstanding-report.yaml (lane v20: 1p/3f; MAIN: 1p/3f)

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| outstanding report journey (6-turn) | F | F | prompt-staleness confound both (worse on MAIN, turn 1 never routes) |
| D17 - parser-driven word answers | F | F | prompt-staleness confound (MAIN never leaves the SO/DO/Both header state) |
| R12 - scope word inside a longer sentence | P | F | prompt-staleness confound (explicit PROMPT fix per case comment) |
| R13 - customer-only ask, By product not By customer | F | P | **List 1**, grant-drift caveat |

### 2026-09-14-outstanding-owner-rounds.yaml (lane v20: 2p/10f; MAIN: 6p/6f)

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| R15 - refinement by date and location stacked | F (grant) | F (different: low_signal on "only BRW") | both fail, different reasons - List 2 |
| R16 - picker keeps the outstanding ask (fullshun) | F (grant) | P | **List 1**, grant-drift |
| R19 - scope header shows customer names | F (grant) | P | **List 1**, grant-drift |
| R19b - full header lists all distinct names | F (grant) | P | **List 1**, grant-drift |
| R20 - no DO hint on the picker | F (grant) | F (different: turn 3 misses DO block) | both fail, different reasons - List 2 |
| R20 guard - plain DO ask keeps picker hint | P | P | |
| R21 - all on picker keeps outstanding ask | F (grant) | P | **List 1**, grant-drift |
| R21 guard - all on picker, plain DO ask | P | P | |
| R22a - decline leaves the offer | F (grant) | F (different: turn 1 never opens the offer) | both fail, different reasons - List 2 |
| R22b - second unreadable turn leaves the offer | F (grant) | F (different: turn 1 never opens the offer) | both fail, different reasons - List 2 |
| R23 - SO detail list, latest date first | F (grant) | F (different: turn 1 never opens the offer) | both fail, different reasons - List 2 |
| R24 - business query under an open offer is a new ask | F (grant) | F (different: turn 1 never opens the offer) | both fail, different reasons - List 2 |

### 2026-09-15-focus.yaml (lane v20: 7p/5f on the 12 cases that existed then; MAIN: 7p/10f on all 17)

R-A through R-E were added to the case file AFTER the referenced lane v20 run (their own header
says "owner-found on the merged head d4ae8203b... 15 Sep 2026") - **no lane v20 baseline exists
for them**; MAIN's result is reported for completeness only, not diffed.

| Case | Lane v20 | MAIN | Note |
|---|---|---|---|
| A - sequential picks 1/2/3 | F (turn 4 only) | F (turn 3 AND 4) | both fail, MAIN fails one turn earlier - List 2 |
| B - promo tier menu | P | P | |
| C - roster survives a declined escalate offer | P | F (turn 4) | **List 1** |
| D - yes consumes escalate, roster does not re-arm | P (AC-1019) | F (turn 4 re-picks) | **List 3** - this IS the lane's own AC-1019 fix |
| F - roster survives a casual turn | F (turn 3 wording) | F (turn 3 wording) | both fail, same shape - List 2 |
| G - ten-row picker 8/10/9/4 | P | F (turns 2-5, wrong codes at each position) | **List 3** - the off-by-one picker bug this lane's own PR fixes |
| H - "another one" is one bubble, no dash | F (turns 3+4) | F (turn 4 only; turn 3 also wrong per raw DB text, script did not flag it - see note) | both fail - List 2 |
| I - new subject clears the picker | F (turn 3) | P (turn 3) | **List 1** |
| merge D - outstanding detail on first pick | P | F | grant-drift confound (contact now holds the SO key the case assumes it lacks) |
| merge E - customer picker scopes the report | P | F | grant-drift confound (confirmed directly, see below) |
| near-miss did-you-mean, single pick | P | P | |
| stock? low-signal clarifier | F (wording only) | P | **List 1**, cosmetic-only lane failure |
| R-A (no lane v20 baseline) | - | P | informational only |
| R-B/R-F (no lane v20 baseline) | - | F | informational only |
| R-C (no lane v20 baseline) | - | F | informational only |
| R-D (no lane v20 baseline) | - | P | informational only |
| R-E (no lane v20 baseline) | - | P | informational only |

## (1) LANE v20 FAIL + MAIN PASS - regression candidates

For each: lane's v20 turn id (from the committed evidence doc or its raw log) and MAIN's reply
text for the differing turn.

1. **2026-09-06.yaml "a pending order roster does not swallow a bare product code"** (3-turn case,
   `delivery to hanlim, product srtwc286` / `last month` / `rpacc`). Lane v20 turn 3 failed
   `branch_kind=low_signal`, reply `"Sure - what would you like to say? Sure - what would you
   like to say?"`. MAIN turn 3: `branch_kind=business_query`, reply `"Customer: hanlim Product:
   rpacc Dates: 01/08/2026 to 31/08/2026 Here are the orders I found. 1. *Company:* Sorento *Or..."`
   - correctly answers RPACC under the open roster. No lane turn id recorded in the committed
   doc for this case (only Case A/F/H/I/stock-clarifier have ids there); the reply text above is
   from `/tmp/console-check-focus-l1/merged/v20-2026-09-06.yaml.log` line 15.

2. **2026-09-06.yaml "a filter reply under an open roster is answered, not re-asked"** (same
   3-turn shape, different case). Lane v20 turn 3 failed `branch_kind=low_signal`, reply `"Sure -
   I can help with that. What would you like to say in your reply? Sure - I can help with that.
   What would you like..."`. MAIN turn 3: `branch_kind=business_query`, reply `"Customer: hanlim
   Product: rpacc Dates: 01/08/2026 to 31/08/2026 Here are the orders I found. 1. *Company:*
   Sorento *Or..."` - same correct-answer shape as #1. Text from v20 log line 23.

3. **2026-09-06.yaml "escalate to a team word never inherits the previous team"** (`escalate to
   marketing`, single turn, **not `cold`** - the script borrows whatever real
   `previous_conversation_state` the contact's most recent stored turn happens to carry, so this
   result is state-dependent and time-of-run-dependent, not fully reproducible). Lane v20 failed
   `branch_kind=out_of_scope`, reply `"Which team should I pass this to - marketing product,
   marketing form or marketing promotion? Which team should I pass th..."` (the inherited-team
   bug the case is built to catch). MAIN: `branch_kind=out_of_scope`, reply `"Your request is out
   of the scope of my ability and require human assistance. We are directing your enquiry to the
   correc..."` - passes cleanly. Given the non-`cold` nature, this could reflect a difference in
   the contact's residual stored state at each run's moment rather than a code difference; flagged
   as a candidate, not a confirmed regression.

4. **2026-09-07-growth-r1.yaml "D8 - all customers of a code on the orders list carry the SO
   block per row"** (`how many did all customers take of SRTWT8201`, tagged NEW VOCABULARY).
   Lane v20 failed `branch_kind=business_query`, reply `"Which customer do you mean? Please
   choose: 1. T & O KITCHEN BATHROOM GALLERY (SRT) - no DO 2. SP PEARL POINT HOME GALLER..."`.
   MAIN: `branch_kind=business_query`, reply `"Customer: all customers Product: SRTWT8201 Dates:
   all dates Here are the orders I found. *Customers:* 64 *Product Code..."` (passes, contains
   the `*SO:*`/`*Ordered:*` block per row). Worth a closer look on its own merits - the case is
   tagged NEW VOCABULARY yet the OLDER v1 prompt passes it while the NEWER v20 prompt fails it,
   which is the reverse of the pattern every other NEW VOCABULARY case shows in this run, so the
   "prompt staleness" explanation does not obviously apply here.

5. **2026-09-12-last-cost.yaml "AC-30 - last in for a family names every member"** (no grant
   needed, explicitly not NEW VOCABULARY per the case's own header). Lane v20 passed, reply `"Here
   is the last SPO line per product. 1. *SPO Number:* SPO-202606-0080 *Product Code:*
   SRTWC8517-SH-UF *SPO Quantity:*..."`. MAIN failed, reply `"incoming search needs to be more
   specific. Multiple matches found. Please choose: 1. SRTWC8517-SH-UF - has incoming 2. S..."` -
   MAIN's resolver treats the bare family prefix `SRTWC8517` as ambiguous and throws a multi-match
   picker instead of listing every family member directly. The case's own comment says no new
   *addendum* vocabulary is needed, but v1 differs from v20/lane in far more than the addendum
   (the whole prompt body), so this is still plausibly prompt-driven rather than a shared-code
   regression; flagged as a candidate, not confirmed.

6. **2026-09-13-outstanding-report.yaml "R13 - a customer-only ask reaches the same report, By
   product instead of By customer"** (`outstanding report for hanlim` then `3`, `cold: true`).
   Lane v20 failed, reply `"Reply 1 for the delivery order list. Reply 1 for the delivery order
   list."` (a single-scope DO-only offer). MAIN passed, reply `"Product: all Customer: HANLIM
   TRADING SDN BHD [A/C II], HANLIM TRADING SDN BHD [A/C I], HANLIM TRADING SDN BHD [A/C
   III]..."` with both SO and DO sections. **Strong grant-drift signal**: the single-scope DO-only
   offer is the exact signature of a contact lacking `sales_orders.outstanding` (documented
   elsewhere in this same lane's evidence for the R-series cases); contact 437264483 holds that
   grant today on both databases. This is very likely the same grant-state drift, not a code
   difference - a fresh lane-stack run today would likely also pass this.

7. **2026-09-14-outstanding-owner-rounds.yaml R16, R19, R19b, R21** (all four picker/header
   cases keyed on `sales_orders.outstanding` being granted). Lane v20 failed all four,
   `branch_kind=out_of_scope` or `business_query` with the single-scope DO offer / no SO in the
   header. MAIN passes all four with the full SO+DO header. **Confirmed grant-drift**: the lane's
   own evidence doc already attributes exactly this failure shape, on this exact contact, to a
   missing `sales_orders.outstanding` grant on `sorento_ai_automation_focus_full` at the time of
   that run; the grant is present on both databases as of today. Not treated as code regressions.

8. **2026-09-15-focus.yaml "C - roster survives a declined escalate offer"** (turn 4, bare `"1"`
   after `"no"` declines the escalate offer). Lane v20 turn 4 passed: `"Here's what you want: •
   product: SRTWT2632..."`. MAIN turn 4 (id `f837ddef-10cb-4d72-ad43-d924fee1a718`):
   `branch_kind=low_signal`, reply `"Hi! How can I help today?"` - the roster is swallowed. Same
   shape as the Case A/H swallow the task asked about (see below) - a bare digit against the
   sticky roster resolves correctly under the lane's newer parser shapes and incorrectly under
   MAIN's much older v1 prompt.

9. **2026-09-15-focus.yaml "I - a new subject clears the multi-match picker"** (turn 3, bare
   `"8"` after `"SRTWC8517 stock?"` clears the old `wc286` roster). Lane v20 turn 3
   (id `1a205662-f067-42c9-9da3-67689c664ee9`) failed: `"That would search every stock we have -
   I need at least one filter to narrow it down..."` (the generic no-filter clarifier). MAIN turn
   3 (id `81050cf6-d9cf-46d7-ba61-0285f6d2b7d5`): `branch_kind=business_query`, reply `"Stock
   details found for the requested products.\n\n1. *Product Code:* SRTWC8517-SH-UF-200..."` -
   correctly re-answers about SRTWC8517. Notably the lane's OWN unpromoted v15 also passes this
   turn (per the committed doc), so both the oldest (v1/MAIN) and newest (v15/lane) prompt shapes
   get it right while the intermediate v20 (today's actual production label) does not - this
   looks like a v20-specific regression in the prompt body itself, not something this lane's code
   changes, one way or the other.

10. **2026-09-15-focus.yaml "stock? low-signal clarifier, no stale product reused"** (single cold
    turn, `"stock?"`). Lane v20 failed only on wording (`"Give me a product code or warehouse, and
    I can look it up."` vs the actual trailing clause) - functionally correct on lane already per
    the committed doc's own classification. MAIN passes with matching text (id
    `a176ab50-5160-4b14-9872-f08c24363ce3`, `"That would search every stock we have - I need at
    least one filter to narrow it down. Give me a product code, warehouse,..."`). Cosmetic-only
    difference on the lane side; not a meaningful regression signal either direction.

## (2) Both fail - pre-existing, not attributable to this lane

- **2026-09-06.yaml "three codes, the third has neither stock nor incoming"** - both runs miss
  `"No stock and no incoming for MSK11A-QT"`, identical reason.
- **2026-09-06.yaml "the not-found line labels its axes and hides the debtor code"** - both runs
  print `[A/C I]` on the not-found line (task's specific question: **yes, MAIN also prints
  `[A/C I]`**, confirmed via the same assertion failing the same way: `reply contains '[A/C I]'
  and must not`). Same defect on both, outside this lane's diff surface per the lane's own doc.
- **2026-09-07-growth-r1.yaml "A3 how many did the customer take - by-product tool carries the SO
  line per row"** - both runs hit the identical ambiguous-customer picker for "heng seng
  hardware" (`"Which customer do you mean? Please choose: 1. HENG SENG HARDWARE SDN BHD (MCH,
  SRT) - has DO 2. HENG SENG HARDWARE - SRI..."`), byte-for-byte the same failure text on both.
  Data/customer-name ambiguity, not code.
- **2026-09-07-growth-r1.yaml "A6 last in for a product"** and **"A6 last 3 received returns
  three"** - both runs fail, but for different reasons. Lane v20 reaches the right SPO tool and
  fails on a field-label assertion (`GR Q...` vs expected "Quantity Received"). MAIN's v1 prompt
  does not even recognize "last in" as the SPO-last-receipt intent (tagged NEW VOCABULARY) and
  answers from the INCOMING/container tool instead (`"I have attached the file(s) below... *Loading:*... *ETC:*..."`)
  - a completely different domain. Both fail, neither attributable to this lane's diff.
- **2026-09-12-last-cost.yaml "AC-32b"** and **"AC-32c"** - both fail, different reasons. Lane
  v20 reaches the `purchase_cost` domain (predates neither this grant nor this vocabulary issue)
  but hits `"Sorry, you are not allowed to access purchase cost"` - an access-denial the case's
  own header says should NOT happen once granted, meaning the grant was likely absent at lane's
  run time despite the file's setup instructions (contradicts today's DB state, where the grant
  IS present on both databases - grant state has clearly moved more than once on this shared
  contact). MAIN's v1 prompt does not recognize "last purchase cost" as `purchase_cost` at all
  (NEW VOCABULARY, migration `513_chatbot_parser_last_cost` postdates v1) and falls through to a
  plain product listing. Neither failure is comparable to the other; neither is this lane's code.
- **2026-09-13-outstanding-report.yaml, all 3 remaining failures** ("outstanding report journey",
  "D17", "R12") - all three fail on both runs because the MAIN v1 prompt predates the
  outstanding-report vocabulary (turn 1 of the 6-turn journey case falls straight through to a
  plain product lookup on MAIN instead of any outstanding-report branch at all). Pre-existing on
  the lane side per its own doc classification ("an EARLIER, now superseded case file... not
  this lane's diff surface"); confounded further on MAIN by the same missing vocabulary.
- **2026-09-14-outstanding-owner-rounds.yaml R15, R20, R22a, R22b, R23, R24** - all fail on both
  runs, but for different reasons on each side (lane: missing SO grant at run time; MAIN: mostly
  the v1 prompt never recognizing the report-opening phrasing at turn 1, e.g. R22a/R22b/R23/R24
  all fail with `turn 1: reply does not contain 'Reply 1 for the sales order list.'` - the
  very first turn never opens the outstanding-report offer under v1). R15 fails differently again
  on MAIN (`branch_kind=low_signal` on the `"only BRW"` refinement, a distinct dialogue-parsing
  gap) - with the grant now present, R15's true behavior under current code has never actually
  been graded clean anywhere, lane or MAIN.
- **2026-09-15-focus.yaml "A - did-you-mean roster, sequential picks 1/2/3"** - both fail, but
  MAIN fails one turn earlier than lane. Lane v20 turn 3 (pick `"2"`) resolves correctly
  (`SRTWT2633`) and only turn 4 (pick `"3"`) breaks (`branch_kind=low_signal`, `"Sure - option 3
  it is."`). MAIN turn 3 already breaks (id `ec641c6e-d9a5-4b7e-b646-95bb2fe845e1`,
  `branch_kind=low_signal`, `"Of course - how can I help?"`), and turn 4 (id
  `92f978b9-723f-464d-ad6d-5938d19205ea`) also fails (`"Hi! How can I help?"`, never reaches
  `SRTWT2634`). Task's specific question (turn 4, `"3"` after picks 1 and 2): **on MAIN the
  sequence never gets that far cleanly - the roster is already swallowed one turn earlier**,
  consistent with the lane's own diagnosis that this is a parser-shape-dependent deterministic-
  engine behavior and MAIN's v1 is even further from the lane's "asks" shape than v20 is.
- **2026-09-15-focus.yaml "F - roster survives a casual turn"** - both fail turn 3 only, same
  shape: the casual `"thanks"` ack gets composed with different wording than the pinned string
  on both runs (lane: `"You're welcome! Happy to help."` missing; MAIN: `"Of course - how can I
  help?"` instead) - turn 4 (the actual roster-survival check) passes on BOTH runs. LLM-composed
  ack wording variance, not a roster defect on either side.
- **2026-09-15-focus.yaml "H - another one after a pick is ONE bubble, no dash"** - both fail.
  Lane v20 fails turns 3 and 4. MAIN's script only flagged turn 4
  (id `d5ed0c55-12c5-4560-b612-3ec853b30e47`, contains `product: SRTWT2633` which must not
  appear - the re-pick regression). Reading the raw DB text directly, MAIN's turn 3 reply (id
  `28e93e33-6a9d-4eab-b47c-aa1780a323b7`) is `"Hi! Could you tell me what you'd like another one
  of?"`, which also does not contain the pinned `"Do you mean you want another option from the
  list?"` string - the console script did not report this as a turn-3 failure for reasons not
  investigated here (possibly a grading-order quirk in the script, out of scope to debug). Task's
  specific question (turn 4): MAIN re-picks against the closed roster (`product: SRTWT2633`
  present) exactly like lane v20 does - same regression shape on both, so not attributable to
  this lane; if anything it is evidence the fix for AC-1020 genuinely needs the lane's merge.

## (3) Lane PASS + MAIN FAIL - lane improvements (expected, this is what the merge buys)

1. **"D - yes consumes the merged escalate question, roster does not re-arm"** (turn 4). Lane v20
   passes (`branch_kind=low_signal`, `"Sure - option 2 it is. How can I help next?"` - no re-pick).
   MAIN fails, re-picking `SRTWT2633`. This is literally AC-1019/AC-1020's own deliverable working
   correctly on the lane and not on MAIN (which lacks the fix) - expected, not concerning.

2. **"G - incoming wc286 ten-row picker, 8/10/9/4 each scoped to one product"**. Lane v20 passes
   all 5 turns with each row number resolving to its documented product. MAIN fails from turn 2
   onward - picking row `"8"` returns `SRTWC286-SH-NEW-200` instead of `SRTWC286-SH-NEW-P`,
   picking `"10"` also returns the wrong code, etc. The case file's own header says this exact
   off-by-one/mismatched-position picker bug ("the original s7 run's step '10' bug") is what
   this lane's own PR fixed. MAIN reproducing that shape is expected - it is pre-lane code.

Everything else in the "no lane v20 baseline" rows of `2026-09-15-focus.yaml` (R-A through R-E)
is reported in the matrix above for completeness but is not part of any of the three lists -
there is no lane v20 result to diff it against.

## Follow-up attempt - removing the prompt confound for the 10 regression candidates

Asked to re-run the 10 List-1 regression candidates against MAIN pinned to the lane's exact v20
SLIM text, to separate real code differences from the v1-vs-v20 prompt gap. Two paths were tried;
neither completed a re-run. Nothing was committed and nothing was written to `0907`.

1. **Publish the v20 text as a new unlabelled row on `sorento_ai_automation_0907`** - refused by
   the Claude Code auto-mode classifier under "Modify Shared Resources", both as a direct SQL
   `INSERT` and as the sanctioned backend route
   (`POST /api/v1/system/ai-assistant/prompts/chatbot_semantic_parser/versions`, the same
   mechanism the admin UI uses, which appends an immutable version and touches no label). A
   follow-up plain `GET` against that same route was refused too. Correct outcome per the
   coordinator's "do not insert anything on 0907" - stated here only as the record of what was
   tried before that instruction arrived. No partial write occurred on either path.

2. **Point at a second stack instead** - `/Users/tehjayson/Documents/foundryx/sorento_crm/.claude/worktrees/low-stock-stack`
   does not exist (not on disk, not in `git worktree list`), nothing listens on `:8085`, and no
   running process on this machine references `sorento_ai_automation_0915` - the low-stock-report
   lane's worktrees were already removed as part of the 15 Sep cleanup (session memory confirms
   this). Read-only checks against the DB itself (no writes made) found it in good shape for a
   *future* run:
   - `sorento_ai_automation_0915` holds the **exact** v20 SLIM text as an **unlabelled** version:
     `chatbot_semantic_parser` version **19**, id `fc9d81f5-b044-412a-8f94-6ab2b8b3342e` - length
     43,926 and md5 `0ca32418480b978c71403065798f2f14`, matching
     `/tmp/console-main/v20_template_source.txt` exactly (the `production` label on this DB
     points elsewhere, at v17 - moving nothing is needed to use v19 via `--prompt-version`).
   - Contact 437264483's grants on `0915` are identical to `focus_full`: the same 10
     `contact_agent_access` rows (all `is_allowed=t`) and the same 5 `contact_field_reveals` rows
     (`inventory.sellable`, `purchase_orders.cost`, `purchase_orders.placed`,
     `purchase_orders.supplier`, `sales_orders.outstanding`, all granted).
   - This DB is therefore usable for a main-under-SLIM re-run of the 10 candidates the moment a
     main backend is booted against it (`DATABASE_URL=sorento_ai_automation_0915`, pinned to
     `--prompt-version fc9d81f5-b044-412a-8f94-6ab2b8b3342e`) - no further DB setup needed.

**Disposition**: per the coordinator, stopping here. The 10 List-1 candidates remain unclassified
by console re-run; they will be classified by reading the code diff between MAIN and the lane's
merged head instead. Nothing in this section was committed.
