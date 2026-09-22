# Evidence - dealer stock verdict (AC-1780, AC-1781)

Filled in during the ONE live pass at the end of the lane (`documentation/agents/browser-verification.md`
/ `documentation/agents/chatbot-verification.md`), not per slice. Run both:

```
venv/bin/python scripts/chatbot_journey.py --base http://localhost:<lane-port> \
    --contact 404285551 --chain tests/chatbot/journeys/dealer-stock-verdict.json \
    --sleep 8 --record tests/chatbot/journeys/_record

venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-22-dealer-stock-verdict.yaml \
    --base-url http://localhost:<lane-port> --sleep-seconds 8
```

Before either run: apply the setup SQL in both files' own headers (dealer test contact
`404285551` flipped to `availability` mode, warehouses BRW + MWH), and re-check the two
prerequisites that can drift on a shared prod copy - the parser prompt's `proceed_anyway` /
`entities[].quantity` publish state (D13) and `system_settings.chatbot_stock_low_threshold_pct` /
`default_product_standard_lead_time_days` (50 / 90 assumed below). Revert the contact's policy
row after the pass.

## Run 1 (bd1f456dd)

## Journey (`dealer-stock-verdict.json`, AC-1780)

Run `journey-1790068917-37acdfa4` against `http://localhost:8081`, prompt v43 production,
contact 404285551 flipped to `availability` (BRW+MWH). **5 passed, 23 failed.** Every FAIL
traces to ONE root cause (see "Root cause" below), not 23 independent defects.

| case | expected (ruling) | result | notes |
|---|---|---|---|
| A - four products, two quantities, then fill | D14 noted+ask, then D6/D17 four verdict lines in asked order | FAIL (2/2 turns) | Root cause A on both turns (turn 1 carries `entities[].quantity` for 2 of 4 products -> `requested_quantities` dict -> tool call errors; the customer-facing reply is a "crossdomain" PO/incoming-stock fallback that looks plausible but is not the new engine's output at all). |
| B - restated quantity | D16 replace, missing unchanged | FAIL (2/2) | Root cause A both turns (both carry a quantity). |
| C - just proceed | D15 answers noted, names not checked | FAIL (3/3) | Turn 1 no quantity, still wrong wording (Observation B). Turn 2 has a quantity -> Root cause A, tool call errors, so no `StockQtyTask` is ever created. Turn 3 ("just proceed") -> parser correctly emits `proceed_anyway: true` (confirms prompt v43 works) but is routed `low_signal`/"Understood as casual" because no task was ever open to claim against (turn 2's crash prevented task creation) - a **cascading** consequence of Root cause A, not a third defect. |
| D - detour (promotion then ETA) then fill | D21-D24 parks silently across two detours, fills after | FAIL (2/4) | Turn 1 (no quantity) wrong wording, Observation B. Turns 2-3 (the two detours) PASS - different domain/tool, unaffected. Turn 4 (fill, both quantities) -> Root cause A. |
| E - resume by naming | D22 re-asks only what is missing, no verdict on resume | FAIL (2/3) | Turn 1 carries one quantity (MHS1028 60) -> Root cause A. Turn 2 (detour) PASS. Turn 3 (resume) FAILs on the SAME expected "Noted: MHS1028 x 60." text turn 1 never produced - no new defect, same root cause surfacing again. |
| F - never mind closes | D23 close by the dealer's own words; a later bare number does not reopen | FAIL (2/3) | Turn 1 (no quantity) wrong wording, Observation B - **but the tool call itself succeeded** here and the raw envelope is visible (see Observation B detail). Turn 2 (never mind) PASSES correctly (`escalation_declined`). Turn 3 ("60" after close) FAILs: the bare number reopens the SAME old-format "How many units do you need for MHS1028, MHS1028 and MSK11A-QT? 1. 2. 3." reply rather than staying closed - this is graded FAIL on the letter of the assertion (`reply contains 'How many units do you need' and must not`), but it is the pre-existing generic `demand_qty` numbered-list flow answering a bare number as it always has, not evidence the NEW task was reopened (no task exists to reopen, per Observation B/Root cause A - turn 1 never created one). |
| G - detailed contact unchanged | D19/AC-1767 no loop, no verdict, byte-identical shape | **PASS, but vacuous** | Contact 423729473's OWN tool call carries `requested_quantities` (2 of 4 named products have quantities) and hits the identical Root cause A crash - confirmed by reading `chatbot.turns.trace` for this turn (`Error executing tool crm_inventory_stock_balance_list: 5 validation errors...`). The case only asserts ABSENCE of availability vocabulary, which the crash fallback also satisfies for any contact, detailed-mode or not. This case cannot currently distinguish "D19 correctly skips the task for a detailed contact" from "the whole tool call is broken for everyone" - re-run once Root cause A is fixed. |
| H - 18-row verdict spot checks (rows 1,2,4,5,7,9,11,13,14,16) | D6, exact text per row (see file header) | FAIL (10/10) | Every row is a single product with an explicit quantity, so every row hits Root cause A (confirmed by trace on row 1 and row 8; row 8 additionally returned `Sorry, I ran into a problem understanding that` - branch_kind None - the SAME crash, one layer further degraded with no crossdomain fallback available for that product). This case does NOT depend on the prompt publish (D13's `demand_qty` fallback), so it is graded strictly per the file's own instruction, and it is 0/10. |

## Console check (`2026-09-22-dealer-stock-verdict.yaml`, AC-1781)

Run `console-check-1790069586` against `http://localhost:8081`, same prompt/contact state.
**1 passed, 4 failed.**

| case | expected (ruling) | result | notes |
|---|---|---|---|
| ask then noted-and-missing question | AC-1757, D14 | FAIL | Turn carries 2 quantities -> Root cause A. |
| answer fills the task | AC-1762 | FAIL (2 turns) | Turn 1 no quantity, Observation B; turn 2 has a quantity, Root cause A. |
| just proceed | AC-1763, D15 | FAIL (2 turns) | Same cascade as journey case C: turn 1 wrong wording (Observation B), turn 2 ("just proceed") routed `low_signal` because turn 1 never opened a task. |
| detour parks silently, fill resumes | AC-1771, D22 | FAIL (2 turns) | Turn 1 no quantity, Observation B; turn 3 (fill, 2 quantities) Root cause A. |
| detailed contact unchanged | AC-1767, D19 | **PASS, but vacuous** | Same caveat as journey case G - this contact's own call also carries quantities and also crashes; confirmed by trace (`chatbot.turns` for this turn shows the identical Pydantic error). |

## Root cause A (confirmed, the dominant driver - 27 of 28 FAILs trace here directly or by cascade)

`app/services/chatbot/lanes/business/fetch.py` (~line 819-832) builds
`out["requested_quantities"] = dict(quantities)` - a **native Python dict**
(`{product_uuid: int}`) - and sends it as a query-style argument to the MCP tool
`crm_inventory_stock_balance_list`. `sorento_crm_mcp/server.py::_compile_tool`
(`_scalar_union = "str | int | float | bool | list[str]"`, ~line 1648) generates every
query-param's Pydantic type from that one fixed union - there is no `dict`/object case in
it, and no per-param override table for `requested_quantities` the way
`TOOL_OPTIONAL_BODY_PARAMS` overrides body params. Every call that includes
`requested_quantities` therefore fails MCP-side Pydantic validation with 5 errors
(`_impl_crm_inventory_stock_balance_listArguments`), confirmed identically in
`chatbot.turns.trace` for turns `679057a9` (case A, 2 quantities), `e8b88c4c` and
`f7571a3e` (case H rows 1 and 8, single quantity via the `demand_qty` fallback), `fec691b3`
(case C turn 2, single quantity), `956d6387` (case G, "vacuous pass"). This is a general,
data-independent defect, not a per-scenario one: **any** turn that reaches
`crm_inventory_stock_balance_list` with a non-empty `requested_quantities` map fails the
same way, regardless of which product/case/contact.

Consequence chain: the tool call errors -> the engine's crossdomain fallback (PO/incoming
lookups) produces a plausible-looking but wrong reply instead of surfacing the error ->
`tasks_after_reply` (`app/services/chatbot/turn/task.py`) never sees a
`stock_availability` envelope block to build a `StockQtyTask` from -> no task is ever open
-> every later turn that depends on an open task (resume, proceed, fill) has nothing to
resume/fill/proceed against, which is why "just proceed" (case C turn 3 / console case 3
turn 2) reads as `low_signal`/casual rather than answering the noted product, even though
the parser itself correctly emitted `proceed_anyway: true` (confirmed by trace) - the
prompt publish (prerequisite 1) worked; the engine had nothing open to apply it to.

Coverage gap: `sorento_crm_mcp/tests/test_catalog_stock_balance_requested_quantities.py`
(S2's own red-then-green test) only asserts the `ToolSpec.query_params` tuple and
docstring text - it never exercises the *compiled* `_impl_crm_inventory_stock_balance_list`
function with a live dict-valued call, which is exactly the surface that fails.

## Observation B (unconfirmed root cause, distinct from A - flagged, not fixed)

On a turn with NO quantity at all (so `requested_quantities` is empty and never sent - no
crash), the tool call succeeds and returns a correct `result_type: "stock_availability"`
envelope (confirmed via trace for turn `9291bed4`, case F turn 1: `intro: "How many units
do you need for MHS1028, MHS1028 and MSK11A-QT?"`, items flagged `needs_quantity: true`).
But that raw MCP `intro` + numbered `items` list reaches the customer close to verbatim
("How many units do you need for MHS1028, MHS1028 and MSK11A-QT?  1.   2.   3.  
_Data last updated: ..._") rather than the UAC's single deduped sentence ("How many units
do you need for MHS1028 and MSK11A-QT?", no numbered list, no duplicate). Two candidate
explanations, not distinguished within this pass's time budget:
(1) the FIRST ask of a stock check (no task open yet) is not routed through whatever
produces the plan's exact `StockQtyTask.question()` wording - only a turn that ALREADY has
a task benefits from it, so even a working Root cause A would leave turn-1 wording wrong; or
(2) `MHS1028` resolving to two company variants (Mocha + Sorento) is an artefact of this
being a substitute test contact with no company scope tagged (chosen specifically because
it was unused elsewhere, header note), and a real dealer contact would resolve to one
company and print once. Recommend the coder check the FIRST-ask path specifically once
Root cause A is fixed, since D14 (journey step 1) depends on it independent of the dict bug.

## Environment notes at run time

- Parser prompt `chatbot_semantic_parser` production version / `has_proceed_anyway`: **v43 / true.**
  v42 (prior production, no `proceed_anyway`) was superseded by publishing
  `SEMANTIC_PARSER_PROMPT` (already carrying `STOCK_TASK_ADDENDUM` on this checkout,
  `bd1f456dd`) + the current `chatbot_domains`/`chatbot_entity_kinds` policy blocks, using
  the exact formula `alembic/versions/chatbot_rearch_s4.py::_body` (imported directly,
  never hand-copied): `f"{SEMANTIC_PARSER_PROMPT.rstrip()}\n\n{BLOCKS_BEGIN}\n{blocks}{BLOCKS_END}\n"`.
  `POST .../prompts/chatbot_semantic_parser/versions` -> 201, `unknown_tokens: []`,
  `missing_vars: []`; `POST .../labels` (`production`, v43) -> 200. Verified
  `GET /api/v1/system/chatbot/prompt-blocks/status` -> `stale: false`,
  `published_version: 43`. `select ... where name='chatbot_semantic_parser' and
  label='production'` -> version 43, `template ilike '%proceed_anyway%'` -> true. The
  version is LEFT PUBLISHED (production) after this pass, per the brief - this clone
  needs it.
- `chatbot_stock_low_threshold_pct` / `default_product_standard_lead_time_days`: **50 / 90**,
  measured, matches the header's assumption, no recompute needed.
- Product figures (MWT5727SS-CR, MHS1028, MSK11A-QT, and all 6 case-H products) re-derived
  with the header's own SQL against `sorento_ai_automation_rearch` immediately before the
  run: **no drift from the header's numbers on any product** - every figure (onhand minus
  open SO, incoming, purchase) matched exactly, so no expected verdict needed recomputing.
- Any case marked "environment-blocked" (prompt not yet published) rather than FAIL:
  **none.** The prompt publish (prerequisite 1) worked correctly and is confirmed working
  at the parser level (`entities[].quantity` and `proceed_anyway` both observed correctly
  emitted in `chatbot.turns.trace`, e.g. case A turn 1's verdict block, case C turn 3's
  `proceed_anyway: true`). Every FAIL below traces to Root cause A/B above, not to the
  prompt or to product-figure drift - the tester (this pass) did not need to grade
  anything as environment-blocked because the actual blocker is downstream of the parser,
  at the MCP tool call.
- Journey step 6 asked-order check (no automated matcher - read `--record` output by eye):
  **not reached** - no case got far enough to produce a real multi-line verdict reply to
  eyeball the order of (every verdict-bearing reply is either the crash fallback or the
  raw `stock_availability` intro, never the engine's own multi-product verdict text).
- Screenshot / transcript reference: none - console/journey scripts only, per the brief;
  full per-turn transcripts are in
  `tests/chatbot/journeys/_record/*.txt` (git-ignored scratch, not committed) and the raw
  `chatbot.turns.trace` rows on `sorento_ai_automation_rearch` for the turn ids named
  above (e.g. `679057a9-3585-4296-9ac7-495555778919`, `e8b88c4c-9eb1-45d2-84a4-1d3ac7bac249`,
  `956d6387-0713-4885-b1ab-e5de2d7eeaab`).
- Contact 404285551's `stock_visibility_policies` row reverted to its prior state
  (`mode = 'compact', warehouse_ids = NULL, excluded_warehouse_ids = NULL`) after the pass
  and verified by SELECT.

## Run 2 (05613f2b1)

Rerun after review round 3 (`05613f2b1`, "requested_quantities crosses the MCP as a JSON
string, not a dict"), which also fixed Observation B's numbered-list/title gap. Diff
against `bd1f456dd` touches only `app/services/chatbot/lanes/business/fetch.py`: (1)
`entity_ids_transformer`'s stock block now does
`out["requested_quantities"] = json.dumps(dict(quantities), separators=(",", ":"), sort_keys=True)`
instead of `dict(quantities)`; (2) `_item_line` falls back to an item's own `title` when it
has no `fields` (this is what makes `_stock_availability`'s per-product verdict sentence,
which the presenter puts in `title` alone, actually reach the customer); (3) a new
`stock_ask_render` gate suppresses the numbered items list entirely while any product still
needs a quantity (`result_type == "stock_availability"` and any item flagged
`needs_quantity`).

**Prerequisites re-applied and re-verified**, same as Run 1: contact 404285551
(`ef6744dc-...`) flipped `compact` -> `availability` (BRW+MWH, ids re-verified against
`warehouses`), settings 50/90 unchanged, all 9 product figures (3 journey + 6 case-H)
re-derived with zero drift from Run 1's numbers. Reverted to `compact` after the pass,
verified by SELECT.

**Runs (each done ONCE, `--sleep 8`), against backend `05613f2b1` at `http://localhost:8081`:**
- Journey: `journey-1790071599-3bde5b9b` - **5 passed, 23 failed** (byte-identical pass/fail
  pattern to Run 1, case by case).
- Console: `console-check-1790072063` - **1 passed, 4 failed** (same pattern).

**Verdict: Root cause A's fix did NOT take effect. Observation B's fix DID take effect.**
Confirmed by reading `chatbot.turns.trace` for fresh turn ids (all NEW turn_ids this run,
not reused from Run 1) across cases A, G and H:

- `entity_ids_transformer` now genuinely produces a `str` for `requested_quantities` -
  confirmed directly: `trace.args.requested_quantities` is `'{"21222491-...":60,...}'`,
  Python type `str`, for turn `d9bf5ded-4745-4e53-9ddc-41cc42bf4471` (case A turn 1), turn
  `4251c285-35bf-494d-8e70-0eb6881bfeba` (case G), and turn `864515cc-74db-4802-93ee-10676cfe59dd`
  (case H row 1). Also confirmed in isolation by calling `entity_ids_transformer` directly
  in the lane checkout's own venv with a representative `trigger`/`semantic_input` - it
  returns `'{"fdf23b11-...":5}'`, a plain `str`, not a dict.
- Despite that, the SAME turns' `envelope` still carries the IDENTICAL Pydantic error:
  `Error executing tool crm_inventory_stock_balance_list: 5 validation errors for
  _impl_crm_inventory_stock_balance_listArguments\nrequested_quantities.str\n  Input should
  be a valid string [type=string_type, input_value={'21222491-...': 60, ...},
  input_type=dict]` - the value Pydantic actually validated was STILL a native dict, not
  the string the backend sent.
- This rules out a stale-process explanation for Root cause A specifically: the SAME file
  (`fetch.py`), the SAME commit, changed OTHER observable behaviour in this exact process
  (the numbered-list suppression, confirmed below) - a module that were serving pre-fix
  bytecode would show neither change, not one of the two.
- Conclusion: the JSON string the backend sends does not survive the MCP round trip -
  something between `MCPRuntimeClient.call_tool`'s plain `httpx.Client(...).post(url,
  json=payload, ...)` (audited: no custom re-encoding, a `str` value stays a JSON string
  on the wire under standard `json=` serialization) and the compiled tool's Pydantic
  validation on the MCP SERVER converts the string back into a dict before validating it -
  most likely an argument-coercion step in the MCP/FastMCP tool-calling framework itself
  (not this repo's own code - `sorento_crm_mcp/server.py`'s `_compile_tool` was not
  touched by this fix and its `_scalar_union` still has no dict case) that auto-parses any
  JSON-object-looking string argument back into a native object before Pydantic sees it.
  This tester did not go further into the MCP SDK/FastMCP internals to find the exact
  line - that is coder territory - but the round-trip failure is unambiguous and
  reproduced identically on 3 separate turns/cases this run.
- Observation B's fix DID work: comparing the SAME first-ask turn text before/after on
  identical input, the numbered "1.   2.   3." list of empty items is GONE in Run 2. Case
  D turn 1, Run 1: `'How many units do you need for MHS1028, MHS1028 and MSK11A-QT?  1.
  2.   3.   _Data last updated: 1'`; Run 2: `'How many units do you need for MHS1028,
  MHS1028 and MSK11A-QT?  _Data last updated: 14/09/2026 17:25'`. The company-duplication
  wording gap (still "MHS1028, MHS1028" rather than deduped "MHS1028") was NOT part of
  this fix and remains open - not a regression, just not yet addressed.

### Per-case results, Run 2 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | FAIL (2/2) | Byte-identical reply text to Run 1 on both turns (both quantity-bearing, Root cause A unfixed). Quoted below. |
| B - restated quantity | FAIL (2/2) | Same as Run 1, Root cause A. |
| C - just proceed | FAIL (3/3) | Turn 1 wording still wrong but numbered list now suppressed (Observation B fixed). Turn 2 (quantity) Root cause A. Turn 3 ("just proceed") still routes `low_signal` - same cascade, no task was ever created because turn 2 crashed. Quoted below. |
| D - detour then fill | FAIL (2/4) | Turns 2-3 (detours) still PASS, unaffected domain. Turn 1 and turn 4 (fill) still FAIL, Root cause A / cascade. Quoted below. |
| E - resume by naming | FAIL (2/3) | Same pattern as Run 1. |
| F - never mind closes | FAIL (2/3) | Turn 1 numbered list now suppressed (Observation B), turn 2 still PASSES, turn 3 still reopens the old `demand_qty` flow on a bare number (no task exists to reopen, same as Run 1). |
| G - detailed contact unchanged | **PASS, still vacuous** | Confirmed by trace: this contact's own call ALSO now sends a correct `str` for `requested_quantities` and STILL hits the identical dict-validation crash. Quoted below. |
| H - 18-row verdict spot checks | FAIL (10/10) | Every row still crashes identically; row 1 quoted below. |

**Quoted replies (Run 2):**

- Case A turn 1 (`d9bf5ded-4745-4e53-9ddc-41cc42bf4471`): `"Here's what you want: •
  product: MWT5727SS-CR (Mocha), MWT5727SS-CR (Sorento), MHS1028 (Mocha), MHS1028
  (Sorento), MSK11A-QT (Sorento) ... Would you like me to escalate to purchasing team?"` -
  the same crossdomain PO/incoming fallback as Run 1, not the new engine's output.
- Case C turn 3 "just proceed" (`d68e02e1-0e75-4dc3-b176-c1a41d0d3310`): `'Hi! How can I
  help you today?'`, `branch_kind: low_signal` - parser still correctly emits
  `proceed_anyway: true` (unaffected by this fix, confirmed working since Run 1), but
  there is still no open task to apply it to.
- Case D turn 1 (`4e095339-4002-4cde-b8e4-4975646ee2b3`): `'How many units do you need for
  MHS1028, MHS1028 and MSK11A-QT?  _Data last updated: 14/09/2026 17:25...'` - numbered
  list gone (Observation B fixed), company-duplication wording still open.
- Case G (`4251c285-35bf-494d-8e70-0eb6881bfeba`): identical reply text to Run 1's case G -
  still the crossdomain fallback, trace confirms the identical Pydantic crash despite a
  correctly-string-typed `requested_quantities` in `trace.args`.
- Case H row 1, `FG-SRTGB01-BR 50` (`864515cc-74db-4802-93ee-10676cfe59dd`): `"Here's what
  you want: • product: FG-SRTGB01-BR  But no inventory matched these. No stock and no
  inco..."` - expected `'Yes, we have stock. FG-SRTGB01-BR x 50: Yes, available.'`; trace
  confirms `requested_quantities` sent as `'{"0b3c69da-...":50}'` (a `str`), tool still
  received a dict and errored.

### Console check, Run 2

Same pattern: `console-check-1790072063`, **1 passed (case 5, detailed contact, vacuous -
same crash confirmed by trace), 4 failed** (cases 1-4, all Root cause A / cascade,
byte-identical failure reasons to Run 1's console pass).

### Environment notes, Run 2

- Prompt `chatbot_semantic_parser` production: still v43 (untouched by this fix, unaffected).
- Settings 50/90: unchanged, re-verified.
- Product figures (all 9): re-derived, zero drift from Run 1.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked - same reasoning as Run 1, the parser layer is fine;
  the blocker is downstream, now narrowed further to specifically the MCP client/server
  round trip for a string-shaped argument, not the backend's own arg-building code (which
  is now confirmed correct by direct trace inspection and by calling
  `entity_ids_transformer` in isolation).

## Run 3 (6429a20e5)

Rerun after the fix that lets the MCP accept the `dict[str, int] | str` union for
`requested_quantities` directly (`pre_parse_json` in
`mcp/server/fastmcp/utilities/func_metadata.py` was turning the JSON string into a dict
before Pydantic validation; `_compile_tool` now types the param as `dict[str, int] | str`
instead of the old scalar-only union, so the pre-parsed dict validates) plus a per-code
merge on the availability presenter (one entry per product code across the dealer's
companies - summed figures, earliest ETA - so the `MHS1028, MHS1028` duplication is gone).
Diff `05613f2b1` -> `6429a20e5` touches `app/services/inventory_service.py` and
`sorento_crm_mcp/server.py` only (plus the catalog test).

**Prerequisites re-applied, same as Runs 1-2:** contact 404285551 flipped `compact` ->
`availability` (BRW+MWH, re-verified), reverted after (verified). Settings 50/90
unchanged. All 9 product figures re-derived, zero drift from Runs 1-2.

**Runs (each done ONCE, `--sleep 8`), backend `6429a20e5` at `http://localhost:8081`:**
- Journey: `journey-1790073434-a32c0701` - **15 passed, 13 failed** (up from 5/23 in
  Runs 1-2 - the two MCP-argument/rendering root causes are genuinely fixed; the
  remainder are DIFFERENT, newly-exposed defects, not a continuation of Root cause A/B).
- Console: `console-check-1790073916` - **2 passed, 3 failed** (up from 1/4).

### Root cause A and Observation B: CONFIRMED FIXED

Case G (journey) and console case 5 (detailed contact) are **no longer vacuous passes.**
Trace for G1 (`7662373b-3e8b-4606-b5f7-68e74d4b351b`) shows a REAL, successful tool call:
`crm_inventory_stock_balance_list` with `requested_quantities:
"{\"21222491-...\":60,\"6a43b9ec-...\":5,\"98f3418b-...\":60,\"fdf23b11-...\":5}"` (a JSON
string carrying all 4 real quantities) and `product_ids` naming all 5 resolved product
UUIDs (2 companies x 2 products with quantities + 1 without) - no error envelope this
time, and the reply is genuine detailed-mode content: `"Stock details found for the
requested products.  1. *Company:* Sorento *Product Code:* MHS1028 *Warehouse:* ..."`
(vs. Runs 1-2's identical crossdomain-fallback text for this same case). Console case 5
shows the same real tool call and the same genuine detailed-mode reply
(`'Stock details found for the requested products.  1. *Company:* Sorento *Product Code:*
MHS1028 *Warehouse:* BUKIT RAJA *'`). Case A turn 1 and console case 1 now produce the
UAC's actual sentence for the first time across all three runs: `'Noted: MHS1028 x 60,
MWT5727SS-CR x 5. How many units do you need for MSK11A-QT?'` - product order is reversed
from the asked order (see New finding B below), but the wording itself is right, no
numbered list, no crash fallback.

### New findings, Run 3 (distinct from Root cause A/B, not present in Runs 1-2's diagnosis)

**New finding A - a restated single-product quantity, with another product still open in
the same task, drops the still-open product from the fetch instead of asking again for
it (D16).** Case B turn 2 ("make MHS1028 80") and case C turn 2 ("MHS1028 60") both
immediately fetch and answer MHS1028 alone, instead of replying `'Noted: ... x 80/60. How
many units do you need for MSK11A-QT?'`. Confirmed by trace (`340d4822-...` and
`264a7153-...`): `verdict.entities` carries ONLY `MHS1028` (correct - the message only
names MHS1028), but the tool call's `product_ids` / `requested_quantities` ALSO carry only
MHS1028's two company UUIDs - MSK11A-QT, which turn 1 explicitly left open (`"How many
units do you need for MSK11A-QT?"`), is entirely absent from the fetch, as if the open
task had only ever had one slot. This is what closes the task early and is the direct
cause of the C-turn-3 "just proceed" cascade (still `low_signal`, same symptom as Runs 1-2
but now for a different underlying reason - there is no open task by the time "just
proceed" runs because turn 2 wrongly closed it, not because the tool call crashed).

**New finding B - products are noted in the REVERSED order from how they were asked.**
Case A/case B turn 1, asked `"stock for MWT5727SS-CR 5, MHS1028 60, ..."`, reply says
`'Noted: MHS1028 x 60, MWT5727SS-CR x 5.'` - MHS1028 first even though MWT5727SS-CR was
named first. Journey step 6 (asked order) is the UAC's own requirement; case B turn 1's
assertion bundles the two into one exact substring (`'Noted: MWT5727SS-CR x 5, MHS1028 x
60.'`) so this reads as a hard FAIL rather than the "eyeball only" the file's own header
allows for a multi-line verdict reply - a single "Noted:" line's product order is
mechanically checkable and is wrong.

**New finding C - a family-grouped product code auto-expands a single literal ask into a
multi-slot task across sibling SKUs the customer never named.** Case H rows 5-8: asking
`"stock for CB313 1200?"` (a real, single, literal product code) opens a task with FOUR
slots - `CB313`, `CB313A-NL`, `CB313-NL`, `CB313-L` (confirmed by trace `e6459937-...`:
`state_diff.products.after` lists all four) - and the reply asks `'How many units do you
need for CB313-L, CB313-NL and CB313A-NL?'`, three products never mentioned. Same pattern
for `SRT392-24` -> `SRT392-24-NL` (rows 7-8). This looks unrelated to Root cause A/B (a
product-family/did-you-mean resolver behaviour, not an MCP argument or presenter issue)
and was not reachable in Runs 1-2 because the task engine never got this far.

**New finding D - the SAME phrasing ("stock for `<code>` `<qty>`?") parses inconsistently
across two back-to-back turns of the identical shape, and the engine's single-slot
`demand_qty` fallback does not cover the resulting case.** Case H row 9 (`"stock for
CWC8315-NEW 935?"`) parses with `entities[].quantity: 935` and answers correctly in one
turn. Row 10, the very next turn, same case, same product, same sentence shape (`"stock
for CWC8315-NEW 75?"`) parses with `entities[].quantity: null` and `demand_qty: 75`
instead (trace `69b0ee35-...` vs `c084326b-...`) - the number landed in the OTHER schema
field. The reply then re-asks `'How many units do you need for CWC8315-NEW?'` rather than
answering with 75, meaning the engine's documented "D13 fallback: a bare number with
exactly one slot still owed belongs to that slot" does not fire here even though exactly
one slot (CWC8315-NEW) is open and `demand_qty` is present. Not confidently isolated to
one side (LLM non-determinism choosing a different schema field for equivalent input, vs.
an engine gap that only applies the D13 fallback when a task already pre-exists) - flagged
for the coder rather than guessed at further.

**New finding E - a parked task's domain (from the detour it parked behind) leaks into
the fill turn instead of resuming the task's OWN domain (D21-D24).** Case D turn 4 (fill,
after the "any incoming ETA on MSK11A-QT?" detour): `plan.fetch = ['incoming']`,
`plan.domains = ['incoming']` (trace `c811446e-...`) - NOT `['inventory']`. The tool
called is `crm_incoming_stock_list`, not the stock-balance tool, so the reply is an
incoming-shipment listing (`'I have attached the file(s) below. 1. *Company:* Sorento
*Product Code:* MSK11A-QT *Container:* ...'`), never a stock verdict, even though both
products now have explicit quantities. Console case 4 shows a different symptom of what
looks like the same family of defect: after the SAME "any promotion" detour, the fill
turn routes to `clarify_menu` (`'Product: MSK11A-QT Which one do you mean? 1. MHS1028
(promotion) 2. MHS1028 (product) ...'`) instead of answering - the detour's domain
(promotion) appears to leave MHS1028 ambiguous between "product" and "promotion" on the
very next turn.

**New finding F - a resumed task (no tool call) does not restate the earlier "Noted:"
line.** Case E turn 3 ("back to the stock check"): trace (`e1de83f8-...`) shows a REAL
tool call was made (`product_ids: [MSK11A-QT]`, no `requested_quantities`) rather than the
"no tool call" resume the UAC (D22) and the file's own `_note` describe - and the reply
(`'How many units do you need for MSK11A-QT?'`) is missing the `'Noted: MHS1028 x 60.'`
prefix turn 1 gave. The dealer is not told anything wrong (MHS1028 is not re-verdicted,
which is D22's hard requirement and still holds), but the recap is gone and a tool call
happens where the UAC says none should.

**Case F turn 3 - unchanged from Runs 1-2, still reopens after close.** A bare "60" after
"never mind the stock check" still reprints `'How many units do you need for MHS1028 and
MSK11A-QT?'` rather than staying closed - same D23 gap as before, unrelated to this
round's fixes (case F never carries a quantity that would touch Root cause A/B or New
findings A-E, so this is genuinely unmoved).

### Per-case results, Run 3 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS / FAIL (1/2) | Turn 1 PASS (first correct "Noted:.../How many units" reply across all 3 runs). Turn 2 FAIL - New finding A (MWT5727SS-CR/MHS1028 verdict lines missing, only the just-filled MSK11A-QT prints). Quoted below. |
| B - restated quantity | FAIL (2/2) | Turn 1 FAIL - New finding B (order reversed). Turn 2 FAIL - New finding A (MSK11A-QT dropped, immediate wrong answer). |
| C - just proceed | PASS / FAIL (1/3) | Turn 1 PASS. Turn 2 FAIL - New finding A. Turn 3 FAIL - low_signal cascade (task closed early by turn 2's bug, not a crash this time). Quoted below. |
| D - detour then fill | PASS / PASS / PASS / FAIL (3/4) | Turns 1-3 PASS (first-ask wording now correct, both detours pass as before). Turn 4 FAIL - New finding E (wrong domain, incoming tool instead of stock). Quoted below. |
| E - resume by naming | PASS / PASS / FAIL (2/3) | Turns 1-2 PASS. Turn 3 FAIL - New finding F (tool call made, "Noted:" prefix missing). Quoted below. |
| F - never mind closes | PASS / PASS / FAIL (2/3) | Turns 1-2 PASS. Turn 3 FAIL - unchanged D23 gap, not this round's fixes. Quoted below. |
| G - detailed contact unchanged | **PASS, no longer vacuous** | Confirmed by trace - real tool call, real detailed-mode reply. Quoted below with the tool call. |
| H - 18-row verdict spot checks | 6/10 PASS | Rows 1-4, 9 PASS (single product, no family-code siblings). Rows 5-8 FAIL - New finding C (family-grouped siblings CB313-*/SRT392-24-NL pulled into the task uninvited). Row 10 FAIL - New finding D (parser inconsistency + missing fallback). Two rows quoted below (1 pass, 5 fail). |

**Quoted replies (Run 3):**

- Case A turn 2 (`703fbd18-c5f3-45fd-926c-f1773281b3ab`): `'Sorry, we do not have enough
  stock for that quantity.  1. MSK11A-QT x 110: Not available, but there is limited
  incoming, ETA 02/09/2026.  ...'` - correct for MSK11A-QT, but MWT5727SS-CR x 5 and
  MHS1028 x 60 (both noted in turn 1) are never verdicted.
- Case C turn 3 "just proceed" (`9fd74dbd-50bc-4993-80e8-9e130456d737`): `'Hi! How can I
  help you today?'`, `branch_kind: low_signal` - no open task survives to turn 3 because
  turn 2 closed it early (New finding A), not because of a crash this time.
- Case D turn 4 (`c811446e-0b33-4b70-9491-2a44c1aa00c9`): `'I have attached the file(s)
  below.  1. *Company:* Sorento *Product Code:* MSK11A-QT *Container:* TEM...'` - the
  incoming-shipment tool's own output, not a stock verdict; trace confirms
  `plan.fetch=['incoming']`.
- Case E turn 3 (`e1de83f8-dad5-43c8-9671-192898d366a0`): `'How many units do you need for
  MSK11A-QT?  _Data last updated: 14/09/2026 17:25:40_ No stock for MSK...'` - correct
  question, missing the `'Noted: MHS1028 x 60.'` recap; trace confirms a real tool call
  was made (`product_ids: [MSK11A-QT]`) where the UAC expects none.
- Case F turn 3 (`b08b3dcb-1449-453e-9269-4cec4d0fcf26`): `'How many units do you need for
  MHS1028 and MSK11A-QT?  _Data last updated: 14/09/2026 17:25:40_ No s...'` - unchanged
  from Runs 1-2, reopens the closed task on a bare number.
- Case G (`7662373b-3e8b-4606-b5f7-68e74d4b351b`): reply `'Stock details found for the
  requested products.  1. *Company:* Sorento *Product Code:* MHS1028 *Warehouse:* ...'`;
  **tool call** `crm_inventory_stock_balance_list` `requested_quantities:
  "{\"21222491-b5d9-43bb-ac5b-69c241f7bedf\":60,\"6a43b9ec-9806-4bcb-9732-eb106bbf2b69\":5,
  \"98f3418b-6d7a-4e33-bdf2-317ea933c3f8\":60,\"fdf23b11-903e-43a8-a817-e588efa1625d\":5}"`,
  `product_ids` naming all 5 resolved UUIDs, no error envelope - this is a REAL pass now.
- Case H row 1, `FG-SRTGB01-BR 50` (`5d98c6d4-38d6-430d-89a4-00e4697d537a`) - **PASS**:
  `'Yes, we have stock.  1. FG-SRTGB01-BR x 50: Yes, available.  _Data last updated:
  14/09/2026 17:25:40'` - exact expected text.
- Case H row 5, `CB313 1200` (`e6459937-7105-46ac-8a2f-5a24e2cbe558`) - **FAIL**: `'Noted:
  CB313 x 1200. How many units do you need for CB313-L, CB313-NL and CB313A-NL?  ...'`;
  trace confirms `state_diff.products.after` resolved CB313 to four separate products
  (`CB313`, `CB313A-NL`, `CB313-NL`, `CB313-L`) from one literal code in the message - New
  finding C.

### Console check, Run 3

`console-check-1790073916` - **2 passed, 3 failed** (up from 1/4 in Runs 1-2). Case 1
("ask then noted-and-missing question") now PASSES with the real sentence. Case 5
(detailed contact) PASSES, **no longer vacuous** - reply `'Stock details found for the
requested products.  1. *Company:* Sorento *Product Code:* MHS1028 *Warehouse:* BUKIT
RAJA *'`, the same real tool call as journey case G (both contacts' calls go through the
now-working MCP argument path). Cases 2 and 3 fail the same way as journey cases A/C (New
finding A). Case 4 ("detour parks silently, fill resumes") fails differently from the
journey's case D: turn 3 (the fill) routes to `branch_kind: clarify_menu`, reply `'Product:
MSK11A-QT Which one do you mean? 1. MHS1028 (promotion) 2. MHS1028 (product) ...'` -
plausibly the same family of defect as New finding E (the "any promotion" detour's domain
context bleeding into the very next turn), though the symptom here is a disambiguation
menu rather than a wrong tool, not traced further within this pass's budget.

### Environment notes, Run 3

- Prompt v43 unchanged, unaffected by this round's fixes.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all three runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked. Root cause A and Observation B (Runs 1-2) are
  CONFIRMED FIXED by this pass. The remaining 13 journey / 3 console failures are SIX
  newly-exposed, mutually distinct defects (New findings A-F above), none of them a
  continuation of the MCP-argument or numbered-list/title issues this round targeted -
  the task engine now runs far enough into the actual dealer-stock-verdict logic to reach
  problems Runs 1-2 could never see past the MCP crash.

## Run 4 (e5c73c1b0)

Rerun after rounds 6-7: `stock_availability` now rides through the MCP render envelope's
`_PASSTHROUGH_KEYS` (it never used to, so no task ever survived a turn - the real root
under New findings A/E/F above), plus six rules landed: a fill never drops open slots
(restated/partial quantity re-asks the missing, never fetches early); asked order kept
in the block and the map; an entity carrying a quantity fetches its exact code only
(D29); `demand_qty` with one named code fills it on open; the task's domain drives the
fill fetch; resume-by-naming makes no tool call; a never-mind aimed at the stock check
clears the products so a following bare number is not read as a quantity. Diff
`6429a20e5` -> `e5c73c1b0` touches `app/services/chatbot/lanes/business/fetch.py`,
`app/services/chatbot/turn/apply.py` (new), `app/services/chatbot/turn/task.py`,
`app/services/chatbot/turn_runtime.py`, `app/services/inventory_service.py`, and
`sorento_crm_mcp/presenters.py` (the passthrough-keys fix).

**Prerequisites re-applied, same as Runs 1-3:** contact flipped `compact` ->
`availability` (BRW+MWH, re-verified), reverted after (verified by SELECT). Settings
50/90 unchanged. All 9 product figures re-derived, zero drift across all four runs.
Backend `/health` confirmed `git_sha: e5c73c1b0`, `prompt_version: 43` before the pass.

**Runs (each done ONCE, `--sleep 8`), backend `e5c73c1b0` at `http://localhost:8081`:**
- Journey: `journey-1790076690-19b445ef` - **22 passed, 6 failed** (up from 15/13 in Run 3).
- Console: `console-check-1790077166` - **5 passed, 0 failed** (up from 2/3 in Run 3 - the
  console file is now fully green).

**New findings A, B, D and F (Run 3) are CONFIRMED FIXED.** Case A turn 1, case B (both
turns), case C (all 3 turns), case E (all 3 turns), case F (turns 1-2), case H row 10 all
now PASS with exact expected text - a restated/partial quantity correctly re-asks the
missing product instead of fetching early, order is correct ("Noted: MWT5727SS-CR x 5,
MHS1028 x 60."), "just proceed" answers noted and names not checked correctly (real
non-crash text this time: `'Sorry, we do not have enough stock for that quantity. 1.
MHS1028 x 60: Not available. ... Not checked: MSK11A-QT.'`), resume-by-naming reprints
the correct "Noted:" line, and row 10's parser-inconsistency case now resolves correctly
regardless of which schema field the LLM filled.

### Three findings remain, all classified ENGINE (each with a distinct seam), zero
### environment or parser causes this run

**Finding 1 (was part of New finding C, Run 3) - D29 ("an entity with a quantity fetches
its exact code only") is not effective: a family-grouped sibling code still gets pulled
into the task even when only the literal code was quantified.** Case H rows 5-8 (`CB313`
-> `CB313A-NL`/`CB313-NL`/`CB313-L`; `SRT392-24` -> `SRT392-24-NL`) still ask about
products never named, exactly as in Run 3. Trace for row 5 (`05ae3025-...`) shows the
parser correctly narrows the QUANTITY map to CB313 alone
(`requested_quantities: {"a76dccb2-...":1200}` - only CB313's own uuid) but the ENTITY
RESOLUTION step still returns all four family UUIDs in `product_ids`
(`['a76dccb2-...' (CB313), 'd0d29649-...', '314781c6-...', 'a62f930c-...']`), and the
task/presenter then treats the other three as open slots needing their own quantity -
`decision.kind: 'new_ask'`, `decision.why: 'domain_in_message'`. **Engine, seam: entity
resolution / family (`did_you_mean`) expansion for a product-family code still runs
BEFORE the "exact code only" narrowing D29 describes, or the narrowing was applied only
to the requested-quantities MAP and not to the `product_ids`/task-slot list itself** -
`app/services/chatbot/turn/task.py` (`StockQtyTask`/entity resolution) or wherever
`product_ids` gets built ahead of the tool call is the seam, not `fetch.py`'s quantity
map building (which is provably correct here).

**Finding 2 (new this run) - a purchase-only disclaimer drops out of a multi-product
verdict batch for one product, even though its own purchase figure is present and
correct.** Case A turn 2 (`38d74c62-...`): the raw MCP envelope's `stock_availability`
array shows `MWT5727SS-CR`'s own entry as `{"verdict": "not_available", "disclaimer":
null, ...}` - NO disclaimer at all - while `MSK11A-QT`'s entry in the SAME batch
correctly carries `{"limited": true, "sources": ["incoming"], "incoming_eta":
"2026-09-02", ...}`. MWT5727SS-CR's own figures (re-verified this run: avail 0, incoming
0, purchase 177) should produce `sources: ["purchase"], purchase_eta_days: <lead time>`,
not `null` - the same product answered WITH its purchase disclaimer correctly in Runs
1-3's crossdomain-fallback text (a different code path: raw PO-line listing, not this
batch verdict). **Engine, seam: `app/services/inventory_service.py`'s per-product
disclaimer computation inside a multi-product `requested_quantities` batch call** - the
purchase-only branch of the disclaimer logic appears not to fire for at least one
product in a 3-product batch where a DIFFERENT product's disclaimer source is
`incoming`; not isolated further within this pass's budget (single-product PURCHASE-only
disclaimer cases, e.g. H rows 7/8's SRT392-24, never got a clean isolated PASS run this
round to compare against - they still fail on Finding 1's family-expansion first).

**Finding 3 (was New finding F, Run 3, re-diagnosed with a precise seam this run) -
"never mind" is read as declining a PENDING ESCALATION OFFER, not as closing the stock
task, when both are live from the same prior turn - so the task survives and a later
bare number still reopens it.** Case F: turn 1's own reply ends with `"Would you like me
to escalate to purchasing team?"` (an escalation offer, alongside the still-open stock
task). Turn 2, `"never mind the stock check"`, routes to `branch_kind:
escalation_declined`, reply `"Escalation declined."` - it silently declined the
ESCALATION OFFER and left the stock task untouched. Trace for turn 3 (`ae7fbc06-...`)
confirms this directly: the turn's OWN `focus.tasks` (read from session state at the
START of turn 3, i.e. as turn 2 left it) still shows `{"kind": "stock_qty", "slots":
[{"label": "MHS1028", "value": null}, {"label": "MSK11A-QT", "value": null}], "status":
"open", ...}` - the task was never closed. Turn 3 ("60") then correctly reads as
"trying to provide a quantity for the open stock check" (`demand_qty: 60`) against a
task with TWO open slots, which correctly does NOT auto-fill either (the documented rule
is single-slot only) - so the reply re-asks both, which is the CORRECT behaviour GIVEN
the task was still open; the actual defect is one step earlier, that "never mind the
stock check" didn't close it. **Engine, seam: the never-mind/topic-decline handling
picks the escalation-offer interpretation over the stock-task-close interpretation when
both are pending simultaneously** - likely in `turn_runtime.py`'s topic-reset/decline
path or wherever `escalation_declined` is chosen ahead of the D23 "never mind the stock
check" close rule this round's fix targeted (the fix evidently handles a never-mind with
NO competing escalation offer live, since case F's turns 1-2 in this exact run show no
escalation offer having been made yet at the point the rule was tested in isolation
elsewhere - not confirmed, flagged for the coder).

### Per-case results, Run 4 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS / FAIL (1/2) | Turn 1 PASS (correct order this time). Turn 2 FAIL - Finding 2 (MWT5727SS-CR's purchase disclaimer missing). MHS1028 and MSK11A-QT both correct. Quoted below. |
| B - restated quantity | PASS (2/2) | Both turns PASS - New finding A (Run 3) confirmed fixed. |
| C - just proceed | PASS (3/3) | All three turns PASS - New finding A cascade (Run 3) confirmed fixed. |
| D - detour then fill | PASS (4/4) | All four turns PASS, including the fill (New finding E, Run 3, confirmed fixed - domain no longer leaks from the ETA detour). |
| E - resume by naming | PASS (3/3) | All three turns PASS - New finding F (Run 3) confirmed fixed, "Noted:" recap restored, no stray tool call visible in the reply. |
| F - never mind closes | PASS / PASS / FAIL (2/3) | Turns 1-2 PASS. Turn 3 FAIL - Finding 3 (escalation-decline vs stock-task-close ambiguity). Quoted below. |
| G - detailed contact unchanged | PASS | Real detailed-mode content, consistent with Run 3's non-vacuous confirmation. Quoted below. |
| H - 18-row verdict spot checks | 6/10 PASS | Rows 1-4, 9-10 PASS (row 10's Run 3 parser-inconsistency issue is fixed). Rows 5-8 FAIL - Finding 1 (family-code expansion). Rows 1 and 5 quoted below. |

**Quoted replies (Run 4):**

- Case A turn 2 (`38d74c62-4a22-4532-a413-245a08df024e`): `'Sorry, we do not have enough
  stock for that quantity.  1. MWT5727SS-CR x 5: Not available.  2. MHS1028 x 60: Not
  available.  3. MSK11A-QT x 110: Not available, but there is limited incoming, ETA
  02/09/2026.'` - expected `'MWT5727SS-CR x 5: Not available, but there is purchase, ETA
  in 90 days.'`; the disclaimer clause is missing for MWT5727SS-CR alone (Finding 2).
- Case B turn 2 (`26989914-2cf5-47ba-874c-b2112d32d50a`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 80. How many units do you need for MSK11A-QT?'` - exact match, PASS.
- Case C turn 3 "just proceed" (`e993f172-d810-4a2a-8573-e1e8760f44be`): `'Sorry, we do
  not have enough stock for that quantity.  1. MHS1028 x 60: Not available. ... Not
  checked: MSK11A-QT.'` - exact match, PASS (compare Runs 1-3, always FAIL here before).
- Case D turn 4 (`fd1c840c-9b34-4e05-b67e-7d4b90dfac69`): `'Sorry, we do not have enough
  stock for that quantity.  1. MHS1028 x 60: Not available.  2. MSK11A-QT x 110: Not
  available, but there is limited incoming, ETA 02/09/2026.'` - exact match, PASS
  (compare Run 3's wrong-domain `crm_incoming_stock_list` failure here before).
- Case E turn 3 "back to the stock check" (`e6061c5d-c170-4d35-9581-52df28b3f5db`):
  `'Noted: MHS1028 x 60. How many units do you need for MSK11A-QT?'` - exact match, PASS
  (compare Run 3's missing-"Noted:" failure here before).
- Case F turn 3 (`ae7fbc06-523b-404c-b784-b838d0e4fa44`): `'How many units do you need
  for MHS1028 and MSK11A-QT?'` - reopens; trace confirms the task was still `status:
  "open"` with both slots `null` going INTO this turn, because turn 2
  (`15126963-a66e-4338-bc9d-88aa7809d728`, `branch_kind: escalation_declined`, reply
  `'Escalation declined.'`) closed the ESCALATION offer, not the stock task (Finding 3).
- Case G (`2cee0a39-b863-446d-8b0b-74a2a1e7b5f6`): `'Stock details found for the
  requested products. 1. *Company:* Sorento *Product Code:* MHS1028 *Warehouse:* BUKIT
  RAJA *System Location:* BRW-BB *Quantity On Hand:* 0 *Outstanding:* 154 ...'` - real
  detailed-mode content across 6 rows (2 companies x MHS1028/MWT5727SS-CR), no
  availability vocabulary anywhere - a genuine pass.
- Case H row 1, `FG-SRTGB01-BR 50` (`3542e491-3d36-49e3-b08e-c21e98bdd819`) - **PASS**:
  `'Yes, we have stock.  1. FG-SRTGB01-BR x 50: Yes, available.  _Data last updated:
  14/09/2026 17:25:40'` - exact expected text, unchanged from Run 3.
- Case H row 5, `CB313 1200` (`05ae3025-1890-4572-a3b8-bfdcd32d14a6`) - **FAIL**: `'Noted:
  CB313 x 1200. How many units do you need for CB313A-NL, CB313-NL and CB313-L?'` -
  expected `'Sorry, we do not have enough stock for that quantity. CB313 x 1200: Not
  available, but there is limited incoming, ETA 20/08/2026.'`; unchanged from Run 3
  (Finding 1, D29 not effective for this literal case).

### Console check, Run 4

`console-check-1790077166` - **5 passed, 0 failed. The console file is fully green for
the first time across all four runs.** All 5 cases (noted-and-missing question, answer
fills the task, just proceed, detour parks silently, detailed contact) now produce the
exact expected text. None of the console cases happen to exercise Finding 1 (no
family-grouped code), Finding 2 (no multi-product batch with a mixed purchase/incoming
disclaimer), or Finding 3 (no escalation offer precedes the never-mind) - so the console
file's green run is consistent with, not contradictory to, the three journey-only
findings above.

### Environment notes, Run 4

- Backend `/health` confirmed `git_sha: e5c73c1b0`, `prompt_version: 43` before the pass.
- Prompt v43 unchanged, unaffected by this round's fixes.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all four runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked; no case classified as a parser problem this run -
  every trace read this pass shows the parser emitting exactly the entities/demand_qty/
  proceed_anyway the message text supports. All three remaining findings are ENGINE,
  each with its own distinct seam (entity-resolution family expansion; per-product
  disclaimer computation in a batch call; never-mind vs escalation-decline
  disambiguation) - none of them a continuation of Runs 1-3's MCP-argument, rendering,
  or task-persistence root causes, all of which are now confirmed fixed.

## Run 5 (96817ad65)

Rerun after round 8: D29 now really narrows the family (the round-7 filter never fired
because resolved rows carry their OWN code in `raw`, not the typed code - rows are now
grouped by "equals or starts with the typed code"); a named id in availability mode
stands for its code so the fill turn reads every company's rows (Finding 2, Run 4's
purchase-disclaimer drop); and "never mind the stock check" closes the task even when an
escalation offer is live (the decline arm was discarding the task outcome - Finding 3,
Run 4). Diff `e5c73c1b0` -> `96817ad65` touches only `app/services/chatbot/turn/apply.py`
and `app/services/inventory_service.py`. Backend `/health` confirmed `git_sha:
96817ad65`, `prompt_version: 43` before the pass.

**Prerequisites re-applied, same as Runs 1-4:** contact flipped `compact` ->
`availability` (BRW+MWH, re-verified), reverted after (verified by SELECT). Settings
50/90 unchanged. All 9 product figures re-derived, zero drift across all five runs.

**Runs (each done ONCE, `--sleep 8`), backend `96817ad65` at `http://localhost:8081`:**
- Journey: `journey-1790078650-04665ddb` - **24 passed, 4 failed** (up from 22/6 in Run 4).
- Console: `console-check-1790079116` - **5 passed, 0 failed** (still fully green, same
  as Run 4 - none of these findings are reachable by the 5 console cases).

**Run 4's Finding 2 (purchase disclaimer) is CONFIRMED FIXED.** Case A turn 2 now reads
exactly `'MWT5727SS-CR x 5: Not available, but there is purchase, ETA in 90 days.'` (was
missing the clause in Run 4). Finding 3 (never-mind vs escalation-decline) is
**PARTIALLY fixed and has exposed a more serious NEW regression** - see Finding 4 below,
the most severe finding across all five runs.

### Four remaining issues, classified by seam

**Finding 4 (NEW, most severe this run) - a bare "carry" turn with nothing open and no
named product still fires an UNSCOPED, catalog-wide stock fetch instead of doing
nothing, listing ~50 unrelated products and opening a task across all of them.** Case F
turn 3 ("60", after "never mind the stock check" closed everything): trace confirms
`state_diff: {}` for this turn (nothing changed - task and products were ALREADY empty,
i.e. turn 2's close genuinely worked, the closing half of Finding 3 IS fixed), but
`plan.fetch: ['inventory']` still fires with `verdict.entities: []`,
`decision: {"why": "nothing_answered", "kind": "carry"}` - a "nothing answered, do
nothing" decision that nonetheless calls `crm_inventory_stock_balance_list` with NO
product filter at all. The tool's own documented behaviour then applies literally ("ALL
FILTERS OPTIONAL - call with none to span every product") and the reply becomes `'How
many units do you need for 32MM TAIL PIECE COUPLING, AC15S, ACC- BIDET, ACC-CB1002,
ACC-CB6001, ACC-CB8001, ... [50 products] ...and ACC-SRT8007?'` - the dealer is asked to
quantify their ENTIRE catalog. This is worse than Run 4's version of the same case (which
at least re-asked about the correct 2 products). **Engine, seam:
`app/services/chatbot/lanes/business/fetch.py` or `turn_runtime.py`'s fetch-gating for
`decision.kind == 'carry'`/`why == 'nothing_answered'`** - a carry decision with zero
entities and no open task should suppress the `inventory` domain fetch entirely rather
than falling through to the tool's own "no filter = everything" default.

**Finding 5 (was Finding 1/New finding C, narrowed further this run) - D29's exact-code
narrowing reads `entities[].quantity` but not the equivalent `demand_qty`-only case, so
the SAME family-expansion bug still fires when the parser routes the number to
`demand_qty` instead.** Case H row 5 (`CB313 1200`, parser put `1200` in
`entities[].quantity`) now PASSES cleanly - D29 correctly narrows to CB313 alone. Row 6
(`CB313 361`), the very next turn, same literal phrasing shape, parses with
`entities[].quantity: null` and `demand_qty: 361` instead (the same parser
non-determinism documented as Run 3's New finding D) - and this time `product_ids` still
carries all 4 family UUIDs (trace `17bdb411-...`), reopening the
"How many units do you need for CB313A-NL, CB313-NL and CB313-L?" ask exactly as before
D29 landed. **Engine, seam: wherever D29's exact-code filter reads the quantity source -
it evidently keys off `entities[].quantity` specifically and was not extended to cover
`demand_qty`,** even though `StockQtyTask.fill()`'s documented single-slot `demand_qty`
fallback already treats the two as equivalent elsewhere in the same file.

**Finding 6 (state hygiene, did not affect the actual answer) - a family task opened by
one row's mismatch (Finding 5) persists into the NEXT row's turn, for an unrelated
product, without being asked about or closed.** Trace for H7 (`e8a1d7f6-...`) shows
`state_diff.tasks.before` STILL carrying H6's stray 4-slot CB313 task
(`status: "open"`, 3 slots still `null`) at the START of the SRT392-24 turn - H7 itself
correctly ignores it and answers SRT392-24 alone (its own `product_ids` has exactly 1
entry), so this did not corrupt H7's own reply, but the CB313 task is never asked about
again or explicitly closed within the 10-row chain. Not confirmed whether it would
eventually resurface (e.g. on "just proceed") - flagged, not chased further.

**Finding 7 (test-assertion artifact, NOT a verdict-computation defect) - rows 7/8's
`reply_not_contains: ['incoming']` assertion collides with unrelated crossdomain-fallback
boilerplate that accompanies every resolved reply, not with the verdict line itself.**
Case H row 7 (`SRT392-24 180`): the actual verdict line is
`'SRT392-24 x 180: Not available, but there is limited purchase, ETA in 90 days.'` -
byte-for-byte the row's own expected text, and D29/the disclaimer computation are both
fully correct here. The FAIL comes from a LATER, unrelated line in the same reply -
`'No stock and no incoming for SRT392-24, but PO is placed:...'` - the crossdomain
probe's routine boilerplate, which every other case's reply ALSO carries (e.g. H1's PASS
reply contains the identical `"No stock and no incoming for..."` phrase) but only rows
7/8 happen to assert against the word "incoming" at all. Row 8 (`SRT392-24 171`) is the
same: verdict line `'SRT392-24 x 171: Not available, but there is purchase, ETA in 90
days.'` is exactly correct. Not classified as environment, parser, or a verdict-engine
defect - the boilerplate append is pre-existing behaviour every case shares, and the
test's own assertion is what is incompatible with it, not the engine's answer.

### Per-case results, Run 5 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS (2/2) | Finding 2 (Run 4) confirmed fixed - exact expected text both turns. Quoted below. |
| B - restated quantity | PASS (2/2) | Unchanged from Run 4, still exact. |
| C - just proceed | PASS (3/3) | Unchanged from Run 4, still exact. |
| D - detour then fill | PASS (4/4) | Unchanged from Run 4, still exact. |
| E - resume by naming | PASS (3/3) | Unchanged from Run 4, still exact. |
| F - never mind closes | PASS / PASS / FAIL (2/3) | Turns 1-2 PASS. Turn 3 FAIL - Finding 4 (NEW, catalog-wide unscoped fetch). Quoted below. |
| G - detailed contact unchanged | PASS | Unchanged from Run 4, real detailed-mode content. Quoted below. |
| H - 18-row verdict spot checks | 6/10 PASS | Rows 1-5, 9-10 PASS (row 5's family-expansion now fixed). Rows 6 FAIL (Finding 5, demand_qty path). Rows 7-8 FAIL on the test-assertion artifact only (Finding 7) - verdict text itself is correct. Rows 1 and 5 quoted below. |

**Quoted replies (Run 5):**

- Case A turn 2 (`370e072f-c648-48c2-92c3-9fcbe21ffea1`): `'Sorry, we do not have enough
  stock for that quantity.  1. MWT5727SS-CR x 5: Not available, but there is purchase,
  ETA in 90 days.  2. MHS1028 x 60: Not available.  3. MSK11A-QT x 110: Not available,
  but there is limited incoming, ETA 02/09/2026.'` - exact match, PASS (Finding 2 fixed).
- Case B turn 1 (`3b06c40a-1da9-4c02-bc80-f275dfd07ad2`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 60. How many units do you need for MSK11A-QT?'` - exact match, PASS.
- Case C turn 1 (`16df8d16-8517-48d8-99c4-7cd2fef4c375`): `'How many units do you need
  for MHS1028 and MSK11A-QT?'` - exact match, PASS.
- Case D turn 1 (`b4de0da6-8f14-468f-9488-d7318c163147`): `'How many units do you need
  for MHS1028 and MSK11A-QT?'` - exact match, PASS.
- Case E turn 1 (`c7b0cdb0-f512-4e64-bc85-1b3261a797f7`): `'Noted: MHS1028 x 60. How many
  units do you need for MSK11A-QT?'` - exact match, PASS.
- Case F turn 3 (`cfcca4a8-140b-4b60-883c-a55a5a8f21bd`): `'How many units do you need
  for 32MM TAIL PIECE COUPLING, AC15S, ACC- BIDET, ACC-CB1002, ACC-CB6001, ACC-CB8001,
  ACC-CB8002-HN, ... and ACC-SRT8007?'` (50 products, verbatim from the raw MCP envelope
  `intro`) - Finding 4, the most severe defect across all five runs: an unscoped
  catalog-wide fetch fired on a bare number with nothing open.
- Case G (`28813616-6e7c-4a1e-8466-446cb3923a48`): `'Stock details found for the
  requested products. 1. *Company:* Sorento *Product Code:* MHS1028 *Warehouse:* BUKIT
  RAJA *System Location:* BRW-BB *Quantity On Hand:* 0 *Outstanding:* 154 ...'` - real
  detailed-mode content, unchanged from Run 4, genuine pass.
- Case H row 1, `FG-SRTGB01-BR 50` (`02b415e3-81fe-44af-a87e-ae7ac4627bce`) - **PASS**:
  `'Yes, we have stock.  1. FG-SRTGB01-BR x 50: Yes, available.  _Data last updated:
  14/09/2026 17:25:40'` - exact expected text, unchanged since Run 3.
- Case H row 5, `CB313 1200` (`5f200d7c-673d-4d35-b335-3911e4d08f71`) - **PASS (newly
  fixed this run)**: `'Sorry, we do not have enough stock for that quantity. 1. CB313 x
  1200: Not available, but there is limited incoming, ETA 20/08/2026.'` - exact expected
  text; compare Runs 3-4's family-expansion failure on this exact row.

### Console check, Run 5

`console-check-1790079116` - **5 passed, 0 failed**, unchanged from Run 4, fully green.
None of the five console cases carry a family-grouped product code, a bare number with
nothing open, or the `demand_qty`-routed parser path, so none of them are positioned to
exercise Findings 4-7.

### Environment notes, Run 5

- Backend `/health` confirmed `git_sha: 96817ad65`, `prompt_version: 43` before the pass.
- Prompt v43 unchanged, unaffected by this round's fixes.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all five runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked; no case classified as a parser problem this run in
  the sense of the parser emitting something the message text does not support - Finding
  5's `demand_qty` vs `entities[].quantity` split is parser NON-DETERMINISM (the same
  phrasing shape parses two different ways across turns), but the actual FAIL is the
  engine's D29 narrowing not covering both paths, so it is classified engine, not parser.
  Findings 4, 5 and 6 are ENGINE, each a distinct seam; Finding 7 is a test-assertion
  artifact, not a defect in the answer itself.

## Run 6 (b9cfa0809)

Rerun after round 9: a bare number with no task open, no entities and nothing on the
products axis plans NO inventory fetch (fixes Run 5's Finding 4 - the unscoped
catalog-wide fetch on a "carry" turn); the MCP presenter caps the noted/missing lists at
10 codes plus "and N others"; a top-level `demand_qty` with exactly one named code is
written onto that entity before the exact-code narrowing (fixes Run 5's Finding 5 - case
H row 6 "CB313 361" now fetches CB313 alone, no stray family task); the cross-domain
zero-set boilerplate ("No stock and no incoming for ...") no longer appears on any
availability reply per the brief. Backend `/health` confirmed `git_sha: b9cfa0809`,
`prompt_version: 43` before the pass.

**Prerequisites re-applied, same as Runs 1-5:** contact 404285551 (`ef6744dc-...`) flipped
`compact` -> `availability` (BRW+MWH, `21608757-0065-4ef2-bd05-1397452411eb` /
`3632e6d8-f398-4f73-8a89-b71988f6f1da`, re-verified against `warehouses`), reverted after
(verified by SELECT: `mode='compact'`, both id arrays NULL). Settings re-checked: `50 / 90`,
unchanged. Prompt `chatbot_semantic_parser` production re-checked: version 43,
`has_proceed_anyway = true`, unchanged. All 9 product figures re-derived with the header's
own SQL immediately before the run: **zero drift across all six runs** on every figure
(MWT5727SS-CR avail 0/incoming 0/purchase 177; MHS1028 0/0/0; MSK11A-QT avail 0/incoming
157 eta 2026-09-02; FG-SRTGB01-BR avail 1560; FG-SRTGB02-BL avail 362; BFAL5061-NL avail
1/incoming 0/purchase 0; CB313 avail 161 [onhand 163 - open_so 2]/incoming 2026 eta
2026-08-20; SRT392-24 avail 166/purchase 20; CWC8315-NEW avail 35/incoming 73 eta
2026-09-02/purchase 1537).

**Runs (each done ONCE, `--sleep 8`), backend `b9cfa0809` at `http://localhost:8081`:**
- Journey: `journey-1790080632-dd91275b` - **26 passed, 2 failed** (up from 24/4 in Run 5).
- Console: `console-check-1790081058` - **5 passed, 0 failed** (fully green, same as Runs
  4-5).

**Run 5's Finding 4 (unscoped catalog-wide fetch on a bare-number carry turn) is CONFIRMED
FIXED.** Case F turn 3 (`841201b0-0b89-4c3b-b565-1b57a8cfd674`) now routes `low_signal`
with reply `'The system will check and respond shortly.'` - no tool call, no 50-product
listing. (Case F turn 3 is still not the D23 "task stays closed and says so" ideal wording
the plan describes, but it is no longer the severe catalog-wide-fetch regression Run 5
found, and the journey's own assertion for this step now PASSES.)

**Run 5's Finding 5 (D29 not covering the `demand_qty` path, family-expansion reopened on
`CB313 361`) is CONFIRMED FIXED.** Case H row 6 (`f13989dd-2991-4b33-bd4c-0016e9d600c3`)
now fetches CB313 alone and answers `'Sorry, we do not have enough stock for that
quantity. 1. CB313 x 361: Not available, but there is incoming, ETA 20/08/2026.'` - no
`CB313-L`/`CB313-NL`/`CB313A-NL` siblings pulled in, exact expected text, PASS (compare
Run 5's reopened family-task FAIL on this exact row).

### Two remaining journey failures - SAME test-assertion artifact as Run 5's Finding 7,
### unchanged, not a new defect

Case H rows 7 and 8 (`SRT392-24 180` / `SRT392-24 171`) both FAIL on `reply_not_contains:
['incoming']` while their `reply_contains` assertions (the actual verdict line) both PASS
byte-for-byte. Read `chatbot.turns` for row 7 (`9c1b634c-74ae-4192-bf73-c585df01fc4c`,
`branch_kind: business_query`):

```
response.reply.text = "Sorry, we do not have enough stock for that quantity.

1. SRT392-24 x 180: Not available, but there is limited purchase, ETA in 90 days.

_Data last updated: 14/09/2026 17:25:40_
No stock and no incoming for SRT392-24, but PO is placed:
*Product Code:* SRT392-24
*Ordered:* 20
*Outstanding:* 20
*PO date:* 2026-03-04
*Location:* BRW

Would you like me to escalate to purchasing team?"
```

The verdict line itself (`'SRT392-24 x 180: Not available, but there is limited purchase,
ETA in 90 days.'`) is the row's exact expected text - D29/the disclaimer computation are
both correct. The FAIL comes from a separate, later block in the SAME reply - a
crossdomain PO-listing fallback still appending `"No stock and no incoming for
SRT392-24, but PO is placed: ..."` after the verdict. Row 8 is byte-identical in shape
(verdict line exactly matches its own expected text; same trailing block trips its
`reply_not_contains: ['limited purchase', 'incoming']`).

**This is the same phenomenon Run 5 classified as Finding 7 (test-assertion artifact, not
a verdict-computation defect), unchanged by this round's fixes.** One discrepancy from the
brief worth flagging: the brief states the cross-domain zero-set boilerplate "no longer
appears on any availability reply" - that is NOT what this run observed for rows 1-4/7-8
(all of which still print `"No stock and no incoming for <code>, but PO is placed: ..."`
or `"No stock, no incoming and nothing on order for <code>."` trailing blocks in the raw
`_record` transcript, confirmed by trace for row 7 above). Whatever the round-9 fix
actually removed, it was not this specific trailing crossdomain-PO block for a
purchase-only product - classified **test artefact**, per the brief's own instruction
("if a row's assertion depended on it, report it as a test artefact, do not edit the
journey file"), not re-diagnosed further within this pass's budget.

### Per-case results, Run 6 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS (2/2) | Unchanged from Runs 4-5, exact text both turns. |
| B - restated quantity | PASS (2/2) | Unchanged from Runs 4-5. |
| C - just proceed | PASS (3/3) | Unchanged from Runs 4-5. |
| D - detour then fill | PASS (4/4) | Unchanged from Runs 4-5. |
| E - resume by naming | PASS (3/3) | Unchanged from Runs 4-5. |
| F - never mind closes | PASS (3/3) | Turn 3 now PASSES - Finding 4 (Run 5) confirmed fixed, `low_signal`/"The system will check and respond shortly", no catalog-wide fetch. |
| G - detailed contact unchanged | PASS | Unchanged from Runs 4-5, real detailed-mode content. |
| H - 18-row verdict spot checks | 8/10 PASS | Rows 1-6, 9-10 PASS (row 6's family-expansion now fixed - Finding 5 confirmed fixed). Rows 7-8 FAIL - same test-assertion artifact as Run 5's Finding 7, verdict text itself is correct. |

**Quoted replies (Run 6):**

- Case A turn 1 (`8172370b-84d4-4d3d-8e47-fb3c4341b360`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 60. How many units do you need for MSK11A-QT? _Data last updated...'` - exact
  match, PASS.
- Case B turn 1 (`88f5fe20-b1ac-4fe4-a0b3-7aeeb794f1bf`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 60. How many units do you need for MSK11A-QT? _Data last updated...'` - exact
  match, PASS.
- Case C turn 1 (`bbd744ea-d27b-42c0-a5a5-d22634d9ef31`): `'How many units do you need for
  MHS1028 and MSK11A-QT? _Data last updated: 14/09/2026 17:25:40_ No s...'` - exact match,
  PASS.
- Case D turn 1 (`53f050e5-4451-4f0d-9b21-98cb21816676`): `'How many units do you need for
  MHS1028 and MSK11A-QT? _Data last updated: 14/09/2026 17:25:40_ No s...'` - exact match,
  PASS.
- Case E turn 1 (`69241e81-ceed-4cfc-9354-a23cb5704bd3`): `'Noted: MHS1028 x 60. How many
  units do you need for MSK11A-QT? _Data last updated: 14/09/2026 17:25...'` - exact
  match, PASS.
- Case F turn 3 (`841201b0-0b89-4c3b-b565-1b57a8cfd674`): `'The system will check and
  respond shortly.'`, `branch_kind: low_signal` - Finding 4 (Run 5) confirmed fixed: no
  tool call, no 50-product catalog listing; the journey's assertion for this step PASSES.
- Case G (`c145f2aa-5d14-42d4-90ec-c2b0836b9e55`): `'Stock details found for the requested
  products. 1. *Company:* Sorento *Product Code:* MHS1028 *Ware...'` - real detailed-mode
  content, unchanged from Runs 4-5, genuine pass.
- Case H row 1, `FG-SRTGB01-BR 50` (`88ff99b9-692f-4607-8108-046f357787fa`) - **PASS**:
  `'Yes, we have stock. 1. FG-SRTGB01-BR x 50: Yes, available. _Data last updated:
  14/09/2026 17:25:40'` - exact expected text, unchanged since Run 3.
- Case H row 5, `CB313 1200` (`2397ba53-64d1-4b20-aeaa-10bee93eb0e1`) - **PASS**: `'Sorry,
  we do not have enough stock for that quantity. 1. CB313 x 1200: Not available, but
  there is limited incoming, ETA 20/08/2026.'` - exact expected text, unchanged since
  Run 5.
- Case H row 6, `CB313 361` (`f13989dd-2991-4b33-bd4c-0016e9d600c3`) - **PASS (newly fixed
  this run)**: `'Sorry, we do not have enough stock for that quantity. 1. CB313 x 361:
  Not available, but there is incoming, ETA 20/08/2026.'` - exact expected text; compare
  Run 5's `demand_qty`-path family-expansion FAIL on this exact row (Finding 5, now fixed).
- Case H row 7, `SRT392-24 180` (`9c1b634c-74ae-4192-bf73-c585df01fc4c`) - **FAIL (same
  test-assertion artifact as Run 5)**: verdict line `'SRT392-24 x 180: Not available, but
  there is limited purchase, ETA in 90 days.'` is exactly correct; the reply's own
  crossdomain trailing block (`'No stock and no incoming for SRT392-24, but PO is
  placed:...'`) is what trips `reply_not_contains: ['incoming']`.

### Console check, Run 6

`console-check-1790081058` - **5 passed, 0 failed**, fully green, unchanged from Runs 4-5.
None of the five console cases carry a family-grouped code, a bare-number carry turn with
nothing open, or a purchase-only-disclaimer SRT392-24-shaped ask, so none of them are
positioned to exercise the H7/H8 test-assertion artifact.

### Environment notes, Run 6

- Backend `/health` confirmed `git_sha: b9cfa0809`, `prompt_version: 43` before the pass.
- Prompt v43 unchanged, unaffected by this round's fixes.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all six runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked; no case classified as a parser problem this run.
  Finding 4 and Finding 5 (Run 5) are CONFIRMED FIXED. The two remaining journey failures
  (H rows 7-8) are the SAME test-assertion artifact as Run 5's Finding 7 - the assertion,
  not the engine's answer, is what is wrong - with one flagged discrepancy: the brief's
  claim that the cross-domain zero-set boilerplate no longer appears on any availability
  reply does not match what this run's `_record` transcript and trace show (the trailing
  "No stock and no incoming for `<code>`, but PO is placed"/"No stock, no incoming and
  nothing on order for `<code>`" blocks are still present on rows 1-4 and 7-8's replies).

## Run 7 (d1bb6e022), intended final

Rerun after round 10: `answer_bridge.apply_crossdomain_hit` had been dropping
`stock_availability` when it handed the item to the crossdomain ladder, so round 9's own
gate never actually saw an availability reply and the ladder kept firing regardless - this
round's fix closes that, so a dealer reply is the verdict lines alone: no "No stock and no
incoming for ..." sentence, no PO/incoming listing, no escalate offer. Diff `b9cfa0809` ->
`d1bb6e022` is in `app/services/chatbot/turn/answer_bridge.py` (per the brief; not
independently diffed by this pass). Backend `/health` confirmed `git_sha: d1bb6e022`,
`prompt_version: 43` before the pass.

**Prerequisites re-applied, same as Runs 1-6:** contact 404285551 (`ef6744dc-...`) flipped
`compact` -> `availability` (BRW+MWH, re-verified), reverted after (verified by SELECT).
Settings re-checked: `50 / 90`, unchanged. Prompt production re-checked: version 43,
`has_proceed_anyway = true`, unchanged. All 9 product figures re-derived: **zero drift
across all seven runs**, identical to Run 6's numbers.

**Runs (each done ONCE, `--sleep 8`), backend `d1bb6e022` at `http://localhost:8081`:**
- Journey: `journey-1790081839-e2af8b3b` - **26 passed, 2 failed** (same count as Run 6,
  but the FAILING rows moved - see below).
- Console: `console-check-1790082304` - **5 passed, 0 failed** (fully green, unchanged).

**Run 6's H7/H8 test-assertion artifact (Finding 7, first raised Run 5) is CONFIRMED
FIXED for real this time.** The crossdomain ladder's trailing block genuinely no longer
appears on any availability reply - confirmed by reading the full `_record` transcript for
case H: every one of the 10 rows now ends cleanly after `"_Data last updated: ..."`, no
`"No stock and no incoming for ..."`, no PO/incoming listing, no escalate offer, on ANY
row (not just 7/8 - rows 1-4 and 9-10 lost it too, matching the brief). Rows 7 and 8 now
PASS with their exact expected verdict text and nothing else:
`'Sorry, we do not have enough stock for that quantity. 1. SRT392-24 x 180: Not available,
but there is limited purchase, ETA in 90 days.'` / `'... SRT392-24 x 171: Not available,
but there is purchase, ETA in 90 days.'`

### NEW regression this run - case F, both remaining turns FAIL on an unscoped
### catalog-wide fetch, the SAME symptom as Run 5's Finding 4 but on a DIFFERENT trigger

Case F turn 1 (`stock for MHS1028 and MSK11A-QT?`) now asks the question with no
escalate offer attached (consistent with the ladder fix - there was nothing to escalate
yet). Turn 2 (`'never mind the stock check'`), which PASSED as `escalation_declined` in
every prior run (an offer existed there to decline), now has NO offer live to decline -
and instead of closing the still-open stock task (D23), it falls through to a full
`business_query`/`inventory` lookup with an EMPTY product filter. Read
`chatbot.turns.trace` for turn 2 (`8c11d51d-aecf-4aaf-b1c7-61ff8c5c9647`):

```
stage=understood: entities: [], demand_qty: null, domain_hint: "inventory",
  intent_hint: "check_stock", domain_in_message: true, topic_reset: true,
  message_type: "business_query", user_goal: "trying to cancel the stock check"
stage=routed: facts.domains: ["inventory"], facts.lane: "business_query"
stage=looked_up: raw payload omitted, "58773 bytes exceeds the 32768 byte cap"
  (the same order-of-magnitude payload size as Run 5's Finding 4 catalog dump)
```

The parser correctly reads the message as a cancel (`user_goal: "trying to cancel the
stock check"`) but ALSO sets `domain_in_message: true` (the word "stock" is in "never mind
the **stock** check") with zero entities - and the engine's fetch-gating routes that
combination straight to an unfiltered `crm_inventory_stock_balance_list` call exactly as
Run 5's Finding 4 described, just reached via `topic_reset: true` + `business_query` +
`domain_in_message: true` instead of via a `carry`/`nothing_answered` decision, which is
the specific shape round 9's fix targeted. Reply:
`'How many units do you need for 32MM TAIL PIECE COUPLING, AC15S, ACC- BIDET, ACC-CB1002,
ACC-CB6001, ACC-CB8001, ACC-CB8002-HN, ACC-CB8003-HN, ACC-CB8004-HN, ACC-CB8005-HN and 40
others?'` - the dealer's entire catalog, opened as a task. Turn 3 (`'60'`) - trace confirms
the message text is genuinely `"60"` and the parser again reads intent correctly
(`user_goal: "trying to provide the quantity 60 for the open stock check"`,
`continuation: true`) but again emits `demand_qty: null` and `entities: []` (the same
parser non-determinism class documented in Run 3's New finding D / Run 5's Finding 5, now
hitting the `demand_qty` field itself rather than routing) - with nothing to fill and a
50-slot task already open from turn 2, the reply repeats the identical unscoped question
verbatim, still asking about the whole catalog.

**Classified ENGINE, a regression, distinct seam from Run 5's Finding 4 (which is
otherwise fixed - a genuine "carry"/nothing-open bare number no longer triggers this).**
The gap is specifically: a `topic_reset: true` message with `domain_in_message: true` and
zero entities - i.e. "never mind the X check" phrased with the domain word still in it -
is not recognised as "close the task, fetch nothing" and instead falls through to the
same "no filter = every product" default the tool documents. This is at least as severe
as Run 5's original Finding 4 (same blast radius, same "ask the dealer to quantify their
entire catalog" reply) and newly exposed by round 10's own fix: with the crossdomain
ladder no longer firing an escalation offer ahead of "never mind", the "never mind the
stock check" phrasing now reaches the fetch-gating path directly rather than being
intercepted by `escalation_declined` first (which is how it happened to pass in Runs 4-6 -
not because the underlying close-vs-fetch gating was ever fixed, but because an
escalation offer was always coincidentally live to catch it first).

### Per-case results, Run 7 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS (2/2) | Exact text both turns, ladder gone (`ABC123` "could not find" note only, no PO/escalate block). Quoted below. |
| B - restated quantity | PASS (2/2) | Unchanged from Runs 4-6. |
| C - just proceed | PASS (3/3) | Unchanged from Runs 4-6, ladder gone from turn 3's reply. Quoted below. |
| D - detour then fill | PASS (4/4) | Unchanged from Runs 4-6. |
| E - resume by naming | PASS (3/3) | Unchanged from Runs 4-6. |
| F - never mind closes | PASS / FAIL / FAIL (1/3) | Turn 1 PASS. Turns 2-3 FAIL - NEW regression, unscoped catalog-wide fetch (see above). Quoted below. |
| G - detailed contact unchanged | PASS | Unchanged from Runs 4-6 - this contact is detailed-mode, not availability-mode, so its own crossdomain block for the one unresolved product (MSK11A-QT) is untouched by this round's fix and still appears; the case's own assertion does not care. Quoted below. |
| H - 18-row verdict spot checks | 10/10 PASS | ALL rows PASS for the first time across all seven runs - rows 7-8's test-assertion artifact (Finding 7) is genuinely gone, ladder confirmed absent from every row's reply. Rows 1, 5, 7, 8 quoted below. |

**Quoted replies (Run 7):**

- Case A turn 1 (`33b7ec40-f74c-45d2-a057-a3b9ca73283b`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 60. How many units do you need for MSK11A-QT? _Data last updated:
  14/09/2026 17:25:40_ I could not find ABC123.'` - exact match on the scored text, PASS.
- Case A turn 2 (`0ca623d7-2b38-4874-838c-ef9f79883d00`): `'Sorry, we do not have enough
  stock for that quantity. 1. MWT5727SS-CR x 5: Not available, but there is purchase, ETA
  in 90 days. 2. MHS1028 x 60: Not available. 3. MSK11A-QT x 110: Not available, but there
  is limited incoming, ETA 02/09/2026. _Data last updated: 14/09/2026 17:25:40_ I could
  not find ABC123.'` - exact match, PASS, no crossdomain ladder appended.
- Case C turn 3 "just proceed" (`89ba9dc2-59e7-4070-808f-6c64b9bfe877`): `'Sorry, we do
  not have enough stock for that quantity. 1. MHS1028 x 60: Not available. _Data last
  updated: 14/09/2026 17:25:40_ Not checked: MSK11A-QT.'` - exact match, PASS.
- Case F turn 1 (`9e29c488-0906-4f71-834c-17781af427c7`): `'How many units do you need for
  MHS1028 and MSK11A-QT? _Data last updated: 14/09/2026 17:25:40_'` - exact match, PASS,
  no escalate offer this time (nothing to escalate yet, ladder gone).
- Case F turn 2 "never mind the stock check" (`8c11d51d-aecf-4aaf-b1c7-61ff8c5c9647`):
  `'How many units do you need for 32MM TAIL PIECE COUPLING, AC15S, ACC- BIDET,
  ACC-CB1002, ACC-CB6001, ACC-CB8001, ACC-CB8002-HN, ACC-CB8003-HN, ACC-CB8004-HN,
  ACC-CB8005-HN and 40 others? _Data last updated: 14/09/2026 17:25:40_'` -
  `branch_kind: business_query` - NEW regression: unscoped catalog-wide fetch instead of
  closing the task; expected `reply_not_contains: ['How many units do you need']`.
- Case F turn 3 (`ec0af441-e836-4c3e-a9bb-3afcbda85f76`): byte-identical to turn 2's reply
  - trace confirms message text was genuinely `"60"`, parsed with `demand_qty: null`,
  `entities: []` despite `user_goal: "trying to provide the quantity 60 for the open
  stock check"` - nothing to fill, the same 50-slot task re-asked verbatim.
- Case G (`96975e46-4f77-4caf-a45d-858d96233b88`): `'Stock details found for the requested
  products. 1. *Company:* Sorento *Product Code:* MHS1028 *Ware...'` (6-row detailed
  listing) `... I could not find ABC123. No stock for MSK11A-QT. But there is INCOMING
  stock (ETA)... Would you like me to escalate to warehouse team?'` - real detailed-mode
  content, unchanged from Runs 4-6; the trailing MSK11A-QT crossdomain block is expected
  here (detailed-mode contact, not availability-mode, outside this round's fix scope) and
  the case's own assertion (no availability vocabulary, no loop) still PASSES.
- Case H row 1, `FG-SRTGB01-BR 50` (`cb71d27b-4737-49b3-8935-4a1fbd9d86dc`) - **PASS**:
  `'Yes, we have stock. 1. FG-SRTGB01-BR x 50: Yes, available. _Data last updated:
  14/09/2026 17:25:40'` - exact expected text, unchanged since Run 3, and now the ENTIRE
  reply (nothing trails it).
- Case H row 5, `CB313 1200` (`939fee37-49b4-4305-b9d0-051fb387e414`) - **PASS**: `'Sorry,
  we do not have enough stock for that quantity. 1. CB313 x 1200: Not available, but
  there is limited incoming, ETA 20/08/2026.'` - exact expected text, unchanged since
  Run 5, no trailing incoming-shipment block this time.
- Case H row 7, `SRT392-24 180` (`d333c211-ce1f-47d5-be4c-9d1de5235e6c`) - **PASS (newly
  fixed this run)**: `'Sorry, we do not have enough stock for that quantity. 1. SRT392-24
  x 180: Not available, but there is limited purchase, ETA in 90 days.'` - exact expected
  text, no trailing "No stock and no incoming" block; compare Runs 5-6's identical FAIL
  on this exact row (Finding 7, now genuinely gone).
- Case H row 8, `SRT392-24 171` (`941564a6-a033-485e-a991-86758dd3664c`) - **PASS (newly
  fixed this run)**: `'Sorry, we do not have enough stock for that quantity. 1. SRT392-24
  x 171: Not available, but there is purchase, ETA in 90 days.'` - exact expected text,
  same fix as row 7.

### Console check, Run 7

`console-check-1790082304` - **5 passed, 0 failed**, fully green, unchanged from Runs 4-6.
None of the five console cases exercise a "never mind" turn with no escalation offer
already live, so none of them are positioned to reach the Case F regression.

### Environment notes, Run 7

- Backend `/health` confirmed `git_sha: d1bb6e022`, `prompt_version: 43` before the pass.
- Prompt v43 unchanged, unaffected by this round's fix.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all seven runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked. The crossdomain-ladder fix this round is CONFIRMED
  correct and complete for every availability reply (all 10 case-H rows, case A, case C,
  case F turn 1) - Run 5/6's Finding 7 test-assertion artifact is genuinely resolved, not
  just newly unreachable. One NEW regression was found: case F turns 2-3, classified
  ENGINE (fetch-gating for a `topic_reset`+`domain_in_message`+zero-entities turn falls
  through to an unfiltered inventory fetch, the same blast radius as Run 5's Finding 4 but
  a different trigger, newly exposed because this round removed the escalation offer that
  had been coincidentally intercepting "never mind the stock check" in Runs 4-6 before it
  ever reached the fetch-gating path).

## Run 8 (b426ce00a)

Rerun after round 11: a `topic_reset` turn with no entities and no quantity now closes the
task and plans no fetch (the fix for Run 7's regression - case F turn 2 answers without a
tool call, turn 3's bare "60" stays silent rather than reopening an unscoped catalog-wide
fetch); an availability contact whose stock ask names no product gets `Which product do
you need? Send the product code and the quantity.` from a new backend flag
`needs_product`, never the catalogue (this specific journey/console pass never exercises a
zero-product stock ask, so this half of the fix is not directly observed here). Both
processes rebooted at `b426ce00a`, `/health` confirmed `git_sha: b426ce00a`,
`prompt_version: 43` before the pass.

**Prerequisites re-applied, same as Runs 1-7:** contact 404285551 (`ef6744dc-...`) flipped
`compact` -> `availability` (BRW+MWH, re-verified), reverted after (verified by SELECT).
Settings re-checked: `50 / 90`, unchanged. Prompt production re-checked: version 43,
`has_proceed_anyway = true`, unchanged. All 9 product figures re-derived: **zero drift
across all eight runs**, identical to Runs 6-7's numbers.

**Runs (each done ONCE, `--sleep 8`), backend `b426ce00a` at `http://localhost:8081`:**
- Journey: `journey-1790083573-b539fa7d` - **28 passed, 0 failed.** Fully green for the
  first time across all eight runs.
- Console: `console-check-1790083959` - **5 passed, 0 failed** (fully green, unchanged
  since Run 4).

**Run 7's regression (case F turns 2-3, unscoped catalog-wide fetch on "never mind the
stock check") is CONFIRMED FIXED.** Full case F transcript:

```
step 1: 'stock for MHS1028 and MSK11A-QT?'
  -> 'How many units do you need for MHS1028 and MSK11A-QT?  _Data last updated: ...'
     branch=business_query

step 2: 'never mind the stock check'
  -> 'The system will check and respond shortly.'
     branch=low_signal

step 3: '60'
  -> 'The stock summary is already available. If you want, I can help clarify what
      quantity or product you'd like checked next.'
     branch=low_signal
```

Turn 2 no longer opens any task or fires any tool call (no 50-product listing); turn 3's
bare "60" - the exact input that, in Run 7, re-triggered the identical unscoped question -
now stays silent about products/quantities entirely and offers to clarify instead. Neither
turn touches `crm_inventory_stock_balance_list`. This matches the case's own assertions
(`reply_not_contains: ['How many units do you need']` on both turns) and both PASS.

No new regressions found. Every one of the 28 journey steps and 5 console cases now
produces the UAC's expected text with no crossdomain-ladder boilerplate anywhere
(confirmed again by reading the full case-A, case-G and case-H `_record` transcripts - the
detailed-mode case G is the only reply that still carries a trailing crossdomain block, for
its one genuinely-unresolved product MSK11A-QT, which is outside round 10's fix scope and
does not affect that case's own assertion).

### Per-case results, Run 8 (journey)

| case | result | notes |
|---|---|---|
| A - four products, two quantities, then fill | PASS (2/2) | Exact text both turns, unchanged from Run 7. Quoted below. |
| B - restated quantity | PASS (2/2) | Unchanged from Runs 4-7. |
| C - just proceed | PASS (3/3) | Unchanged from Runs 4-7. Quoted below. |
| D - detour then fill | PASS (4/4) | Unchanged from Runs 4-7. |
| E - resume by naming | PASS (3/3) | Unchanged from Runs 4-7. |
| F - never mind closes | PASS (3/3) | Turn 1 unchanged. Turns 2-3 NEWLY FIXED - Run 7's regression confirmed fixed, both route `low_signal`, no catalog-wide fetch, no reopened task. Quoted below (all three turns). |
| G - detailed contact unchanged | PASS | Unchanged from Runs 4-7, real detailed-mode content. Quoted below. |
| H - 18-row verdict spot checks | 10/10 PASS | All rows PASS, unchanged from Run 7 - no crossdomain ladder on any row. Rows 1 and 7 quoted below. |

**Quoted replies (Run 8):**

- Case A turn 1 (`87d70795-7f8f-4adf-98f5-7e34009c6b03`): `'Noted: MWT5727SS-CR x 5,
  MHS1028 x 60. How many units do you need for MSK11A-QT? _Data last updated:
  14/09/2026 17:25:40_ I could not find ABC123.'` - exact match, PASS.
- Case A turn 2 (`85eebfc1-d968-4883-b8e3-b769de464380`): `'Sorry, we do not have enough
  stock for that quantity. 1. MWT5727SS-CR x 5: Not available, but there is purchase, ETA
  in 90 days. 2. MHS1028 x 60: Not available. 3. MSK11A-QT x 110: Not available, but there
  is limited incoming, ETA 02/09/2026. _Data last updated: 14/09/2026 17:25:40_ I could
  not find ABC123.'` - exact match, PASS.
- Case C turn 1 (`50506b13-81f2-4a4a-8a43-f1aca16fef90`): `'How many units do you need for
  MHS1028 and MSK11A-QT? _Data last updated: 14/09/2026 17:25:40_'` - exact match, PASS.
- Case C turn 2 (`85da8224-524f-4582-a0cd-863aa06ffabf`): `'Noted: MHS1028 x 60. How many
  units do you need for MSK11A-QT?'` - exact match, PASS.
- Case C turn 3 "just proceed" (`d7cb9088-d0f2-4ae4-9552-bfaba7becd6f`): `'Sorry, we do
  not have enough stock for that quantity. 1. MHS1028 x 60: Not available. _Data last
  updated: 14/09/2026 17:25:40_ Not checked: MSK11A-QT.'` - exact match, PASS.
- Case F turn 1 (`190c9fe5-702c-4379-b0d9-050bb462edc0`): `'How many units do you need for
  MHS1028 and MSK11A-QT? _Data last updated: 14/09/2026 17:25:40_'` - exact match, PASS.
- Case F turn 2 "never mind the stock check" (`7583ef9e-6857-4473-a922-00776299e8f7`):
  `'The system will check and respond shortly.'`, `branch_kind: low_signal` - Run 7's
  regression confirmed fixed: no unscoped catalog fetch, no tool call, task closed.
- Case F turn 3 "60" (`8e5e9fb0-e072-4834-8b6f-bc60a714b6ed`): `'The stock summary is
  already available. If you want, I can help clarify what quantity or product you'd like
  checked next.'`, `branch_kind: low_signal` - the bare number that reopened the
  50-product question in Run 7 now stays silent about products entirely; PASS.
- Case G (`3d1b7a60-05e0-4308-8942-596482e88f58`): `'Stock details found for the requested
  products. 1. *Company:* Sorento *Product Code:* MHS1028 *Ware...'` (6-row detailed
  listing) `... I could not find ABC123. No stock for MSK11A-QT. But there is INCOMING
  stock (ETA)... Would you like me to escalate to warehouse team?'` - real detailed-mode
  content, unchanged from Runs 4-7; the trailing MSK11A-QT crossdomain block is expected
  here (detailed-mode contact, outside round 10's fix scope) and the case's own assertion
  still PASSES.
- Case H row 1, `FG-SRTGB01-BR 50` (`6cd7db72-72af-4528-b95b-b29927dc8434`) - **PASS**:
  `'Yes, we have stock. 1. FG-SRTGB01-BR x 50: Yes, available. _Data last updated:
  14/09/2026 17:25:40'` - exact expected text, unchanged since Run 3, nothing trailing.
- Case H row 7, `SRT392-24 180` (`2d0fa194-6acd-4355-8d96-6ecfb3fd6ef3`) - **PASS**:
  `'Sorry, we do not have enough stock for that quantity. 1. SRT392-24 x 180: Not
  available, but there is limited purchase, ETA in 90 days.'` - exact expected text,
  unchanged since Run 7, nothing trailing.

### Console check, Run 8

`console-check-1790083959` - **5 passed, 0 failed**, fully green, unchanged from Runs 4-7.
None of the five console cases exercise a "never mind" turn or a zero-product stock ask,
so none of them are positioned to exercise either half of round 11's fix directly, but
none regressed either.

### Environment notes, Run 8

- Backend `/health` confirmed `git_sha: b426ce00a`, `prompt_version: 43` before the pass.
- Prompt v43 unchanged, unaffected by this round's fix.
- Settings 50/90 unchanged, re-verified.
- All 9 product figures re-derived, zero drift across all eight runs.
- Contact 404285551 flipped to `availability` (BRW+MWH) before the pass, reverted to
  `compact` after, both verified by SELECT.
- No case graded environment-blocked; no case classified as a parser or engine defect
  this run. Run 7's case-F regression is CONFIRMED FIXED with no new regression found
  anywhere in the 28-step journey or the 5-case console file.

### Summary across all eight runs (journey / console pass counts)

| run | sha | journey | console |
|---|---|---|---|
| Run 1 | `bd1f456dd` | 5 passed, 23 failed | 1 passed, 4 failed |
| Run 2 | `05613f2b1` | 5 passed, 23 failed | 1 passed, 4 failed |
| Run 3 | `6429a20e5` | 15 passed, 13 failed | 2 passed, 3 failed |
| Run 4 | `e5c73c1b0` | 22 passed, 6 failed | 5 passed, 0 failed |
| Run 5 | `96817ad65` | 24 passed, 4 failed | 5 passed, 0 failed |
| Run 6 | `b9cfa0809` | 26 passed, 2 failed | 5 passed, 0 failed |
| Run 7 | `d1bb6e022` | 26 passed, 2 failed | 5 passed, 0 failed |
| Run 8 | `b426ce00a` | 28 passed, 0 failed | 5 passed, 0 failed |

**No functional defect remains open.** Run 8 is the first fully green pass across both the
journey (28/28) and the console file (5/5) in this evidence file's history. Every prior
finding tracked across Runs 1-7 (Root cause A, Observation B, New findings A-F, Findings
1-7, and Run 7's case-F regression) is either confirmed fixed by a later round or was
itself a test-assertion artifact rather than a real defect (Finding 7, resolved for real
in Run 7). This pass found no new mismatch to diagnose.
