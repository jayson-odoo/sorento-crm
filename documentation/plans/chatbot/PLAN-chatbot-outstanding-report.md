# PLAN - Chatbot outstanding report: SO backlog and DO pending, one shape, four filters

Status: APPROVED by owner 12 Sep 2026 on the lavish page; lane `feat/chatbot-outstanding-report` (worktree `.claude/worktrees/chatbot-outstanding-report`, test DB `sorento_osr_ci`) sits on origin/main and ships WITHOUT #847. S1 to S4 built; Phase 3 PASSED (reviewer + security reviewer + console run 5, six of six journey turns green); PR open. Owner testing round 1, 13 Sep 2026 (R1, R2) implemented. Owner testing round 2, 13 Sep 2026 (R3, D16/AC-1144/AC-1145) implemented, then SUPERSEDED. Owner testing round 3, 13 Sep 2026 (R6, R7, R9, and design ruling D17 which retires D16's word tables) - RED tests written in `test/chatbot-outstanding-red`, not yet implemented.
UAC: `chatbot-outstanding-report-acceptance-criteria.md` (AC-11xx).
Base: stacked on `feat/chatbot-focus` (lane 1 of `PLAN-chatbot-focus-multi-domain.md`,
issue #847), because the scope question and the detail pick are open-question kinds that
mechanism owns. Branch `feat/chatbot-outstanding-report`, one PR, merged after #847.
Related: `PLAN-do-search-and-mcp-feedback-7sep.md` (built the `so_outstanding` bucket this
plan stops using for the chatbot).

## Why

The owner asked "Dealer outstanding quantity SRTWT7445 in 2026" and got a summary whose
three numbers cannot reconcile (Ordered 26,723, Transferred 24,565, SO Outstanding 3) and a
false miss for a year that holds real 2026 orders. Top management will quote these numbers.
Three defects and one missing definition, all measured (UAC "Measured"):

1. Ordered/Transferred sum every line including cancelled and retired-provisional
   duplicates; Outstanding sums only live lines. Different populations, so the identity
   Ordered = Transferred + Outstanding never holds.
2. The date window travels as `actual_delivery_date_*`; the SO arm drops it and the DO
   arm uses it to exclude every undelivered DO. A dated "outstanding" ask can only miss.
3. Rows are SO lines, so one SO prints once per line, with no customer and no location.
4. "Outstanding" is two different numbers at Sorento, and DO is raised before goods leave,
   so both matter: SO backlog (booked, not yet transferred to DO) and DO pending (DO raised,
   not yet delivered). The bot must name which, and ask when the message does not say.

## Decisions (owner rulings, 12 Sep 2026)

| # | Ruling |
|---|---|
| D1 | Two named numbers. Block titles are `Sales order outstanding` and `Delivery order outstanding` (RENAMED, R7, owner testing round 3, 13 Sep 2026 - was `Delivery order pending` until R6 brought a `Delivered` figure back into the block, at which point "pending" stopped being the right word for the whole block). The bare word never appears as a heading. |
| D2 | Missing scope word → ONE numbered question (Sales orders / Delivery orders / Both). Scope words in the message bind without asking. On main this is `selection_context = "outstanding_scope"` + `pending.kind = "outstanding_scope"` + a 3-row `last_result_set`, one-turn life like `team_clarify` (see "S4 on main"). |
| D3 | No date in the message = all dates, printed as `Order date: all`. A parsed window filters SO on `sales_orders.order_date` and DO on `orders.order_date`. No date question in this lane (trigger in UAC backlog). |
| D4 | Cancelled quantity is never shown and never summed. |
| D5 | Location grammar: a token equal to a warehouse code is that code only (`BRW` = `BRW`); a token that is a `-suffix` is every code with that suffix (`IB` = `BRW-IB`, `MWH-IB`). Resolved against the `warehouses` table. |
| D6 | Grain: totals sum lines; the list is one row per SO with lines rolled up; the DO list one row per PENDING DO ONLY (REWRITTEN, R1, 13 Sep). By location and By customer are printed INSIDE each block: SO figures under the SO block, DO figures under the DO block (owner markup, 12 Sep). |
| D7 | Customer filter by `customer_name` only. Debtor code is not an input and not printed. |
| D8 | Reply is `Label: value` lines, no `.` separators, exact date ranges (`dd/mm/yyyy to dd/mm/yyyy`), no "oldest", no "+N more". Every row is sent; n8n chunks long messages already. |
| D9 | RULED on the lavish page 12 Sep: SO breakdown lines read `name: ordered (O/S: outstanding)`, the suffix shape the stock answer already uses (`presenters.py:1259-1287`). DO breakdown lines READ `name: pending`, no bracket (REWRITTEN, R1, 13 Sep: `do_qty` is gone, so there is nothing left for the bracket to disambiguate pending from) - REWRITTEN AGAIN (R6, owner testing round 3, 13 Sep 2026): the bracket is BACK, `name: do_qty (O/S: pending)`, over EVERY DO in scope (pending and delivered); a name whose pending is 0 still prints `(O/S: 0)`, never elided - REWRITTEN A THIRD TIME (R11, same sitting): `do_qty (O/S: pending)` stands, but the population behind both numbers is now the SAME one population (D14), so `do_qty == pending` on every row and a name with nothing outstanding is ABSENT rather than printed at 0. Sub-headings print `*_By location_*` / `*_By customer_*` (bold italic; WhatsApp has no underline). ORDER (R10, same sitting): both breakdowns, in both blocks, sort by the bracketed figure descending, ties by the leading figure descending, then name ascending - sorted in the ROUTE, printed as given by the presenter. |
| D10 | Detail is offered as a numbered reply (`1. Sales order list`, `2. Delivery order list`). CHANGED 13 Sep (captain, main mechanism): the answering turn re-runs the SAME tool call with the stored filter set plus `detail=so|do`; the session keeps the filters, never the rows (so_rows can be hundreds of SOs and session variables are not a cache). One GET, same numbers. |
| D11 | REWRITTEN (R13, owner testing round 3, 13 Sep 2026). The chatbot stops calling the `so_outstanding` bucket for outstanding asks - PERIOD, whether the ask names a product, a customer, or both. The original wording carved out "no product" as an exception that kept the old bucket; R13 retires that carve-out too: "when we generate the outstanding summary for customer and for product it is different, they should be the same." That bucket and `include_pipeline` stay for their OTHER readers (a plain quantity ask); repairing them is backlog (trigger in UAC). |
| R13 | **NEW, owner testing round 3, 13 Sep 2026.** The report's subject is a product, a customer, or both, one summary shape for all three. `product_code` becomes optional on the route; at least one of `product_code`/`customer_ids`/`customer_query` is required (422 otherwise). Header prints `Product: all` with no product. New groups `so_by_product[]`/`do_by_product[]` (ranked per R10, tallying per R11, same shape as the `_customer` groups they replace). Which groups the body carries depends on the subject: product subject → by_location + by_customer (today's shape, unchanged); customer subject → by_location + by_product (`*_By customer_*` becomes `*_By product_*` - R13's own words); both → by_location ONLY, `by_customer` AND `by_product` both absent. `so_rows[]`/`do_rows[]` always carry BOTH `customer_name` and `product_code` now, whatever the subject - the detail row gains a `Product` line (SO: SO Number/Customer/Product/Location/Ordered/Transferred to DO/Outstanding/Order Date; DO: DO Number/Customer/Product/Location/DO Qty/Delivered/Outstanding/DO Date). D11 and "Tool pick" (S4 point 2, above) retire the customer-only carve-out to the legacy `so_outstanding` bucket - the scope question, offers, carried filters and the `sales_orders.outstanding` reveal-key gate behave identically for a customer subject. |
| R14 | **NEW, owner testing round 3, 13 Sep 2026, same sitting as R13.** On the two-option detail offer, an answer meaning BOTH (`all`/`both`/`everything`, or position 3 if the parser emits one) returns BOTH lists in one reply, SO list then DO list, each under its own heading line - the offer text gains a THIRD option, `3. Both lists`, whenever two scopes are on offer (a single-scope offer stays R9's one sentence - there is nothing for a third option to add). |
| D13 | Access (owner ruling on the lavish page): every `order_enquiries` contact sees DO figures, as today. SO figures are gated per contact by ONE field-reveal key `sales_orders.outstanding` on Contacts > Access (same table and screen as `purchase_orders.placed`, which already gates a whole answer family: `answer.py:936, 1113-1122`). Default deny. Without the key the scope question is never asked (scope is DO) and an explicit SO ask prints `Sales order figures are not enabled for your account.` then the DO block. Checked before any fetch. No new table, no new agent. |
| D12 | The existing order-list MCP tools additionally expose `customer_query` and `warehouse_codes`. NOT `order_date_*`: the DO list tool's dates are actual delivery dates by a standing ruling (`sorento_crm_mcp/tests/test_catalog_compile.py::test_orders_list_uses_actual_delivery_date_only`), and pending DOs by order date are served by the new report route instead. |
| R1 | **REWRITTEN, owner testing round 1, 13 Sep 2026.** "Delivery order pending" means DOs that still have pending quantity, nothing else - "most of the DO are delivered right so what's outstanding? I thought outstanding means still got some pending quantity." The DO block and its two breakdowns cover ONLY DOs matching `_outstanding_clause`; `do_qty` and `delivered_qty` are GONE from the block and both breakdowns - there is nothing left to disambiguate a pending figure from, so the breakdown lines drop their `(O/S: ...)` bracket too (`name: pending`, no bracket). See "The reply" and "Backend contract" below for the new shape. PARTIALLY SUPERSEDED by R3: `do_rows[]` regains `do_qty`/`delivered_qty` on the ROW only. |
| R2 | **NEW, owner testing round 1, 13 Sep 2026.** The detail offer is STICKY: after "1" (SO list), typing "2" must give the DO list - today `pending.kind = "outstanding_detail"` is consumed by the first pick (`tail/compile_state.py::_offer_carry`'s own one-turn exclusion for it), so a second pick falls into the generic order lane. Rule: the offer stays open across picks and casual turns until a NEW ASK (a message carrying a product code or a domain word) or a topic change - the SAME carry condition `suggest_offer` / the tier offer already use, copied with its justification (`_offer_carry`), never `member_offer`'s TTL. |
| R3 | **NEW, owner testing round 2, 13 Sep 2026.** DO detail rows show the delivered quantity even when it is zero - "need to show delivered also, doesn't mean if it is 0 then we don't show, if it is 0 then we show 0, don't hide." `do_rows[]` regains `do_qty` (the DO's line quantity for the product) and `delivered_qty` (`do_qty` minus `pending_qty`, `0` for a pending DO today) - ROWS ONLY, the block and both breakdowns stay pending-only (R1 stands there). |
| D16 | **owner testing round 2, 13 Sep 2026 - SUPERSEDED by D17.** Word answers, no number required, read by a fixed word table in the deterministic head (`_OUTSTANDING_WORD_VALUES`). On `outstanding_scope`: "sales"/"sales order"/"SO" -> 1, "delivery"/"delivery order"/"DO" -> 2, "both"/"all"/"everything" -> 3. On `outstanding_detail`: matched against WHICHEVER options are actually on offer. The word table itself is what caused the "delivery to hanlim" regression (see D17) - "delivery" matched the DO-list word even though the message named a customer, not an answer - and is retired rather than patched again. |
| R6 | **NEW, owner testing round 3, 13 Sep 2026.** "need to show the delivered also, so the by location and by customer needs to be the DO qty (O/S: {pending}) so DO qty minus pending should be those quantity delivered." `do_qty` / `delivered_qty` come BACK onto the `do` block and onto BOTH breakdowns (`do_by_location[]` / `do_by_customer[]`), summed over EVERY DO in scope - pending AND delivered - reversing R1's "gone from the block and breakdowns" for these two fields only. R1's population rule survives for `do_count` / `do_date_min` / `do_date_max` / `do_rows[]`, which stay pending-DOs-only. The breakdown line regains its bracket (D9, above): `name: do_qty (O/S: pending)`, and a name whose pending is 0 (a location/customer that is only ever delivered) still prints `(O/S: 0)`, never elided. |
| R7 | **NEW, owner testing round 3, 13 Sep 2026, same sitting as R6.** Both blocks use the SAME line order, and the DO block says "outstanding", never "pending" - block title `Delivery order outstanding` (D1, above); SO block order becomes `Sales orders`, `Ordered`, `Transferred to DO`, `Outstanding`, `Order date range`; DO block prints FIVE value lines in order `Delivery orders`, `DO qty`, `Delivered`, `Outstanding`, `DO date range` (`Delivered` is back, printed even at 0; `Outstanding` replaces the `Pending` label - the JSON field stays `pending_qty`, this is presentation only). `Delivery orders` stays the count of DOs still outstanding (`do_count`, pending only). The miss line becomes `No outstanding delivery order.`; the DO detail row label `*Pending:*` becomes `*Outstanding:*` (row fields: DO Number, Customer, Location, DO Qty, Delivered, Outstanding, DO Date). The scope question option 2 and the detail offer's `2. Delivery order list` are unchanged in wording. |
| R9 | **NEW, owner testing round 3, 13 Sep 2026.** A report with only ONE scope offers detail as a single sentence, not a numbered list: `Reply 1 for the sales order list.` (SO-only) / `Reply 1 for the delivery order list.` (DO-only). The numbered form (`1. Sales order list` / `2. Delivery order list`) stays for TWO scopes. "1" still picks either way - this is a presentation change only, the deterministic resolver is unaffected. |
| D17 | **Design ruling, owner + captain, 13 Sep 2026 - REPLACES R4, R5 and R8 as previously briefed, and RETIRES D16.** Deterministic code never reads words; the PARSER (LLM) reads the customer's answer and the head only ever maps a POSITION to a stored option. When `pending.kind` is `outstanding_scope` or `outstanding_detail`, the text the engine sends the parser (`head/parser.py::build_user_block`, the same per-turn-fact path that already states "the assistant is waiting for a `{pending_kind}` reply") carries the open question's own numbered option labels, and the prompt (migration 514's published text, `chatbot_parser_prompt.py`) instructs: emit `reference_positions` for the position the message answers, by number or by words naming an option; a message that asks something new (a product, a customer, an order, another topic) is NOT an answer. `_OUTSTANDING_WORD_VALUES` / `_outstanding_word_pick` are deleted from `head/output_exchange.py` - there is no filler list and no word cap to maintain, because the head never reads a word again. The R8 regression ("delivery to hanlim" read as a DO-list pick because "delivery" matched the word table) is retired along with the table that caused it, and re-verified live by a console case rather than a pytest word list, because only the real parser reads words. New-ask precedence stays structural in the head, defensively: a turn naming its own entity is a new ask even if it also carries a stray `reference_positions` (the parser is told never to emit both). |
| D14 | **The standing DO-population rule, as of R11 (owner testing round 3, 13 Sep 2026), after R1/R6's back-and-forth.** ONE population for the WHOLE DO block: DOs matching `_outstanding_clause` (`order_service.py:67-93`), nothing else. `Delivery orders` = their count; `DO qty` = SUM `order_lines.quantity` over them; `Delivered` = `DO qty` minus `Outstanding` (the part-delivered portion on those DOs - `0` given today's schema, `order_lines` carries no per-line delivered/outstanding split below the DO header, so this can never actually be positive today; the field stays for shape parity with the SO block); `Outstanding` = SUM their outstanding qty (== `pending_qty`, same population); `DO date range` over them; both breakdowns and `do_rows[]` are one row per name/DO ON THOSE DOs ONLY. R11's own words: "the breakdown list should tally with whatever reported at the summary at the top", choosing option 1 - a customer whose only DOs are delivered is ABSENT from the breakdowns, not printed with `0`. |
| R10 | **NEW, owner testing round 3, 13 Sep 2026.** "be it DO outstanding or SO outstanding, we need to rank by highest quantity at the top." Every `*_By location_*` / `*_By customer_*` group, in BOTH blocks, sorts by the bracketed outstanding quantity DESCENDING; ties by the leading (total) quantity DESCENDING; further ties by name ASCENDING. `Unassigned` takes its place by its own numbers like any other name - never pinned first or last. Sorting happens in the ROUTE service (the JSON arrays arrive sorted); the presenter prints in the order given and never re-sorts (a golden-file ordering change, plus a presenter test that feeds an unsorted body and asserts the output order equals the input order). |
| R11 | **NEW, owner testing round 3, 13 Sep 2026 - REPLACES R6's two-population DO block, becomes D14 above.** "the breakdown list should tally with whatever reported at the summary at the top", choosing option 1 (breakdowns list only names with outstanding above 0). |
| R12 | **NEW, parser gap found live, 13 Sep 2026.** `"Srtwc8518-SH dealer delivery order outstanding how many at BRW?"` parsed `order_status: "outstanding"` (bare) instead of `do_outstanding`, so the scope question was (re-)asked over a message that had already named the scope. D17 stands: the fix is in the PROMPT (an explicit example set for a scope word embedded inside a longer sentence, plus the rule stated in words that the document word decides the scope wherever it sits), not in deterministic code - there is nothing for the head to resolve differently here, the parser simply mis-read the sentence. |
| R15 | **NEW, owner ruling, 13 Sep 2026, after the R13/R14 round.** A turn taken under an OPEN `outstanding_scope` or `outstanding_detail` question that PICKS nothing but names a filter of its OWN is a REFINEMENT of the question, not an answer and not a new ask: the stored filter set is overlaid with what this turn named (dates, a location word, a customer on a product report) and the SAME question is re-armed over the narrower set. Live capture: `outstanding dealer quantity for CNK HARDWARE` -> scope -> `3` -> report + detail offer -> `i want to see this month only` -> the bot RE-PRINTED the offer. "you are anticipating me to reply for the detail list after offering me the detail list, but i just want to shrink the search by date" - and, on the first fix sketch, "too many hardcoding, causing everything to break once something changes, LLM is supposed to help us eliminate these hard coding". So the head reads the PARSER's own verdict and nothing else: `entity_op: "reuse"` (the parser read the turn as carrying no new value - its emission on that very message was `casual` / no entities / no `reference_positions` / `entity_op: reuse` / `broaden_axis: date` / `date_filter_start` + `date_filter_end` on September), or `entity_op: "replace_combine"` whose entities all sit on axes OTHER than the stored subject's, by the SAME axis tables the entity-operation executor already uses (`_axis_for_hint`). There is no dates-only branch and no per-axis code. Under `outstanding_detail` the same `crm_outstanding_report` call re-runs for the SAME scope (stored on the filter set as `scope`), with NO `detail` argument, and the hit arms a fresh offer carrying the overlaid filters, so a later "1" lists the new window only. Under `outstanding_scope` nothing is fetched: the question is re-asked through the first-ask arm with the overlaid filters, and its text now prints the filter summary lines the report header prints (`Product:` / `Location:` / `Order date: 01/09/2026 to 30/09/2026`, dd/mm/yyyy), so the customer can see the narrowing landed. What this REPLACES is the old "ANY entity of its own is a new ask" guard, which read a date window as nothing at all and a location word as a brand new question; a turn naming a new SUBJECT (a different product under a product report) is still a new ask and still drops the offer, and D17 point 3's defensive guard is unchanged: a stray `reference_positions` riding along with an entity is still a new ask, because a refinement requires that NOTHING was picked at all. |
| R16 | **NEW, owner round 5, 13 Sep 2026.** A PICKER ANSWER CONTINUES THE QUESTION THE PICKER INTERRUPTED. Live: `outstanding dealer quantity for hanlim` hit the gate's ambiguous-customer picker, and the `1` that answered it came back as the legacy per-product order summary (`crm_order_management_orders_list`) instead of the outstanding scope question - the pick turn names no status word, and `order_status` was the ONE axis of the question the session did not keep. So the session now persists `order_status` beside the `date_filter_*` / `requested_attributes` it already kept (`tail/compile_state.py`, written only when the turn named one, allowlisted in `contracts.SessionVars`), and the head's `entity_op: "reuse"` arm carries it back exactly the way it already carries those two - same rule, same justification, no new pending kind and no picker-specific branch. Two supporting repairs the same turn needed: the scope-ask signal (`outstanding_scope_ask_candidate`) is re-read on the FINAL pass as well as the first, because a pick turn's status and its entity both arrive after the first read; and `_picker_carry`'s H29 rule ("an offer born THIS TURN outranks a carried picker") gains the outstanding scope question / detail offer as born kinds, or the question armed by the pick had its own `selection_context` overwritten by the roster it had just answered. One more, at the gate: a RE-SEATED PIN IS IN SCOPE - `gate_passed` was decided on the resolver's rows alone, before the pinned-pick re-seat ran, so a turn whose only subject is the pick failed the "requires a scoping entity" test with the picked customer already sitting in `compatible_entities` ("A PICK IS AUTHORITATIVE" is that block's own rule; the verdict is now re-taken on what is actually in scope, only where the resolver returned nothing at all). |
| R17 | **NEW, owner round 5, 13 Sep 2026 - a REGRESSION OF AC-1143 introduced by R15, and this is where it is recorded as such.** A refinement's filters belong to the OFFER, not to the conversation. R15 put the turn's own entities into `parse.output.entities`, which is the list the session persists, so `only BRW` left an UNRESOLVED `{"raw": "BRW", "hint": "warehouse", "uuid": absent}` behind; the next unrelated ask merged it back in on its own axis (location, not the subject's), the resolver searched the warehouse WORD as a customer token, and one real family became seven in the picker. AC-1143 already says a new ask drops the offer and its filters; R17 extends that to the raw entity that carried them. The refinement's entities now travel ONLY on `outstanding_refinement_entities` (offer-scoped, read by `run_fetch`'s location resolver - the same D5 read that already prefers the raw parsed entities over the gated ones), never on `entities`, so the location dies with the offer and a new ask starts from a clean filter set - including a customer-only new ask, not just a product one. |
| R18 | **NEW, owner round 5, 13 Sep 2026.** A WAREHOUSE WORD IS NEVER A CUSTOMER. `gate.py`'s "AMBIGUOUS CUSTOMER" picker keys only on the resolved `entity_type`, so a token the PARSER hinted `warehouse` that the resolver happened to answer with customer rows (`customers.customer_name ilike 'STOCK TRANSFER%BRW%'` is a real family on the prod copy) became a line in "Which customer do you mean?" and counted toward "N different companies". The uuids that ONLY a warehouse-hinted token matched are dropped from the picker's candidates AND from `compatible_entities` (the picker stopped listing them; the drop stops the turn SEARCHING them, which is the same defect one step later). Fails open in both directions: a uuid the customer word matched as well is untouched, one reached through `intersection` / `by_entity_type` (no token to attribute it to) is untouched, and the scope is never emptied. |

**Follow-up, not this PR.** R15's ruling came with a criticism of the code it lands in: "too many hardcoding, causing everything to break once something changes, LLM is supposed to help us eliminate these hard coding". `app/services/chatbot/head/output_exchange.py` is 3,589 lines, and a large part of it second-guesses the parser rather than reading it: `entity_op_corrected` (the head rewriting `reuse` into `replace_combine`), the scope-word fallback that re-derives a pick from `order_status`, the domain restore/wander arms, and until R15 the "any entity is a new ask" guard. Each was a real live defect once, and each is a rule the prompt could carry instead, now that the parser is given the open question's own options (D17). Cleaning that up is its own lane with its own grill, replay-corpus evidence and UAC - it is not a change to make inside a fix round, because the replay corpus is the only thing that says whether a removed guard is still needed. Trigger: the next time an arm in this file has to be corrected for a case the parser already emitted correctly.

## The reply (contract for Phase 1)

REWRITTEN (R6/R7, then R10/R11, owner testing round 3, 13 Sep 2026) - both blocks share
the SAME line order, the DO block gets its `Delivered` line back and says "outstanding"
rather than "pending", its breakdowns regain the `(O/S: ...)` bracket, BOTH breakdowns in
BOTH blocks rank by the bracketed figure descending (R10), and the DO block's `do_qty` is
now the SAME population as `Outstanding` (R11/D14 - the sample's `MWH-IB` outranks
`BRW-IB` because 1,211 > 1,200, and `DO qty` reads 640, not a higher figure, because a
delivered DO no longer contributes to it):

```
Product: SRTWT7445
Customer: all
Location: IB (BRW-IB, MWH-IB)
Order date: 01/01/2026 to 31/12/2026

*Sales order outstanding*
Sales orders: 12
Ordered: 2,411
Transferred to DO: 0
Outstanding: 2,411
Order date range: 05/01/2026 to 28/08/2026
*_By location_*
MWH-IB: 1,211 (O/S: 1,211)
BRW-IB: 1,200 (O/S: 1,200)
*_By customer_*
Dealer A Sdn Bhd: 900 (O/S: 900)
Dealer B Trading: 811 (O/S: 811)
Dealer C Hardware: 700 (O/S: 700)

*Delivery order outstanding*
Delivery orders: 3
DO qty: 640
Delivered: 0
Outstanding: 640
DO date range: 03/02/2026 to 30/08/2026
*_By location_*
BRW-IB: 640 (O/S: 640)
*_By customer_*
Dealer A Sdn Bhd: 640 (O/S: 640)

Reply with a number for detail:
1. Sales order list
2. Delivery order list
```

R9 (same sitting): with only ONE scope on offer, the closing line is a single sentence
rather than a numbered list - `Reply 1 for the sales order list.` / `Reply 1 for the
delivery order list.` - "1" still picks either way.

Scope question (D2):

```
Product: SRTWT7445
Outstanding for which document?
1. Sales orders (not yet transferred to DO)
2. Delivery orders (not yet delivered)
3. Both
```

Detail, SO list (D6, D10), one item per SO:

```
1. *SO Number:* SO331785
*Customer:* Dealer A Sdn Bhd
*Location:* BRW-BB
*Ordered:* 410
*Transferred to DO:* 0
*Outstanding:* 410
*Order Date:* 20/12/2024
```

Detail, DO list (D6, D10), one item per PENDING DO only, fields REWRITTEN THREE TIMES (R1,
R3, then R7): R1 dropped `DO Qty` / `Delivered`; R3 brought them BACK on the ROW ONLY (the
block above stays pending-only) because the owner wants `Delivered` shown even when it is
`0`; R7 renames the row's `Pending` label to `Outstanding` (presentation only - the JSON
field stays `pending_qty`):

```
1. *DO Number:* DO220456
*Customer:* Dealer A Sdn Bhd
*Location:* BRW-IB
*DO Qty:* 640
*Delivered:* 0
*Outstanding:* 640
*DO Date:* 03/02/2026
```

D10 is ALSO sticky now (R2, 13 Sep): the offer this reply ends with stays open across
picks and casual turns until a new ask or a topic change, not just the one turn that
answers it. D17 (13 Sep, same round as R6/R7): a WORD answer to either open question ("all",
"DO list") is resolved by the PARSER against these option labels, never by the deterministic
head - see "S4 on main" point 4/5 and D17's own row in Decisions, above.

## Backend contract

`GET /api/v1/order-management/outstanding-report`

| param | type | rule |
|---|---|---|
| `product_code` | str, required | exact, case-insensitive (AC-1119) |
| `scope` | `so` / `do` / `both` | default `both` |
| `customer_query` | str | `customers.customer_name ILIKE %q%` |
| `warehouse_codes` | csv | exact codes; resolution of tokens happens in the chatbot lane, not here |
| `order_date_from`, `order_date_to` | date | SO on `sales_orders.order_date`, DO on `orders.order_date` |

Response (`OutstandingReportResponse`, every field declared):

```
{
  "product_code": "SRTWT7445",
  "customer_name": null | "Dealer A Sdn Bhd",
  "warehouse_codes": ["BRW-IB", "MWH-IB"] | [],
  "order_date_from": "2026-01-01" | null, "order_date_to": ... | null,
  "so": { "ordered_qty", "transferred_qty", "outstanding_qty", "so_count",
          "order_date_min", "order_date_max" },              # absent when scope=do
  "do": { "do_qty", "delivered_qty", "pending_qty", "do_count",
          "do_date_min", "do_date_max" },                    # absent when scope=so
  "so_by_location": [ { "code": "BRW-IB" | null, "ordered_qty", "outstanding_qty" } ],
  "so_by_customer": [ { "customer_name", "ordered_qty", "outstanding_qty" } ],
  "do_by_location": [ { "code" | null, "do_qty", "pending_qty" } ],
  "do_by_customer": [ { "customer_name", "do_qty", "pending_qty" } ],
  "so_rows": [ { "so_number", "customer_name", "location", "ordered_qty",
                 "transferred_qty", "outstanding_qty", "order_date" } ],
  "do_rows": [ { "do_number", "customer_name", "location",
                 "do_qty", "delivered_qty", "pending_qty", "do_date" } ]
}
```

R10 (owner testing round 3, 13 Sep 2026): `so_by_location[]`, `so_by_customer[]`,
`do_by_location[]` and `do_by_customer[]` arrive already sorted - the bracketed outstanding
figure descending, ties by the leading (total) figure descending, further ties by name
ascending. `Unassigned` (a NULL `code`/`customer_name`) sorts by its own numbers, no special
casing. `so_rows[]` and `do_rows[]` keep their existing date order (AC-1114/AC-1115), R10
does not touch the detail lists.

SO population (one predicate, used by every SO figure):
`sales_orders.status = 'open' AND sales_order_lines.line_status = 'open' AND qty_ordered -
qty_delivered > 0` joined to the product and the optional filters. `ordered_qty = SUM
qty_ordered`, `transferred_qty = SUM qty_delivered`, `outstanding_qty = SUM (qty_ordered -
qty_delivered)`. The identity is then arithmetic, not luck. UNCHANGED by R11 - the SO side
already tallied this way, one population throughout.

DO population, D14's standing rule as of R11 (owner testing round 3, 13 Sep 2026, REPLACES
R6's two-population shape): "the breakdown list should tally with whatever reported at the
summary at the top", choosing option 1 (breakdowns list only names with outstanding above
0). ONE population, `OrderService._outstanding_clause` (`order_service.py:67-93`) - a
DELIVERED DO contributes to NOTHING on this route, not even `do_qty`. `do_count`,
`do_date_min`/`do_date_max`, `do_rows[]` AND NOW `do_qty`/`delivered_qty`/`pending_qty`/both
breakdowns all draw from the SAME population, the same way the SO side always has:
`pending_qty = do_qty = SUM order_lines.quantity` over outstanding DOs, joined to the
product and the optional filters; `delivered_qty = do_qty - pending_qty` (the part-delivered
portion on an otherwise-outstanding DO - always `0` given today's schema, `order_lines`
carries no per-line delivered/outstanding split below the DO header, so the field is present
for shape parity rather than because it can be observed today). `do_qty == delivered_qty +
pending_qty` holds by construction, same as the SO identity. A customer/location whose only
DOs are delivered is ABSENT from the breakdowns - not a `0` row.

<details><summary>Superseded wording, kept for the commit history's sake</summary>

12 Sep (captain's original ruling): `do_qty = delivered_qty + pending_qty` over every DO
(pending and delivered) in the window. R1 (round 1, 13 Sep) dropped `do_qty`/`delivered_qty`
entirely - "most of the DO are delivered right so what's outstanding?" R3 (round 2) brought
them back on `do_rows[]` only. R6 (round 3) brought them back on the block and both
breakdowns too, summed over EVERY DO in scope (two populations at once: `do_qty`/
`delivered_qty` over every DO, `pending_qty`/`do_count`/dates/rows over outstanding DOs
only) - the owner's OWN testing of that shape (same round 3 sitting) found the two
breakdown figures did not "tally with whatever reported at the summary at the top", which
is what R11 fixes by collapsing back to one population.

</details>

One service function `outstanding_report(db, filters) -> dict` in a new
`app/services/outstanding_report_service.py` (about 150 lines: two base queries, four
aggregations, one sort each on the four breakdown arrays). No registry, no list-query
resource: the chatbot is the only reader and the shape is a report, not a grid.

## Slices

| slice | phase | what | files |
|---|---|---|---|
| S1 | 1 | Presenter over mock report JSON; golden fixtures for both / so / do / miss / detail lists; dash guard test | `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (`_outstanding_report`, `_outstanding_detail`), `documentation/plans/chatbot/samples/outstanding-report-*.txt`, `sorento_crm_mcp/tests/test_presenters_outstanding.py` |
| S2 | 2 | Route + service + response model + tests (tester first) | `app/api/v1/order_management/orders.py` (new route), `app/services/outstanding_report_service.py`, `app/schemas/order_management.py`, `tests/test_outstanding_report.py` |
| S3 | 2 | MCP tool `crm_outstanding_report`; `customer_query` + `warehouse_codes` on the two order-list tools (no `order_date_*`); backend `warehouse_codes` on `GET /orders` and `/orders/by-product`; tool seeding | `sorento_crm_mcp/sorento_crm_mcp/catalog.py`, `orders.py`, `order_service.py:843-853`, `sorento_crm_mcp/tests/test_catalog.py` |
| S4 | 2 | Lane wiring on MAIN's picker mechanism, see "S4 on main" below | `chatbot_parser_prompt.py` (order_status vocabulary), `lanes/business/gate.py` (`ALLOWED["order"]` + warehouse), `lanes/business/services.py` (warehouse suffix rule), `lanes/business/fetch.py` (tool pick, DATE_PARAMS, param map, gate), `lanes/business/answer.py` (refusal line, detail offer), `tail/pending.py` + `tail/compile_state.py` (two pending kinds, header skip), `head/output_exchange.py` (two resolvers), `contact_field_reveal_service.py` + catalog `restricted_fields` (key), `orders.py` + `outstanding_report_service.py` (`customer_ids`, `detail`), tests `tests/chatbot/test_outstanding_lane.py`, console case YAML |
| S5 | 3 | reviewer + browser-less console check (chatbot-verification.md) in parallel; guide-writer updates the chatbot user guide with the six journey messages | `documentation/plans/chatbot/evidence/outstanding-report/`, `documentation/user-guides/` |

Phase 1 for a chatbot lane is the presenter against a mock: the "UI" is the WhatsApp text,
and the golden files are its screenshots. The captain reviews the golden files on the lavish
page before S2 starts.

## S4 on main (rewritten 13 Sep: the lane ships without #847, so no `open_question` API)

Measured on origin/main (explore pass, 13 Sep): a numbered question is armed by writing
`variables["selection_context"]` + `variables["last_result_set"]` (rows `idx/label/...`) and
letting `tail/pending.py::derive()` stamp `variables["pending"] = {"kind": ...}`
(`compile_state.py:934`); the next turn's "1"/"2" arrives as the parser's
`reference_positions` and is resolved in `head/output_exchange.py` gated on `pending.kind`
(team pick: `_team_clarify_pick` at 789, applied at 1087; member pick at ~2845-3060). The
escalate offer + team picker on a miss is produced by `not_found_error_message` returning
`escalate_message` / `is_clarification` and `tail/member_offer.py::build_cs_member_offer`.
Tool pick is a table lookup, `fetch.py::select_tool` = `DOMAIN_SPEC[domain].tools[0]`.
Warehouse is an entity type already (`TYPE_TO_PARAM["warehouse"] = "warehouse_ids"`) but
`gate.py:56 ALLOWED["order"]` does not admit it. Reveal keys are the frozen literal
`FIELD_REVEAL_KEYS` in `contact_field_reveal_service.py:41-45`, pinned to the catalog's
`restricted_fields` by `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py`.

The wiring, smallest shape that fits each of those:

1. **Parser vocabulary** (`chatbot_parser_prompt.py`, the growth-r1 addendum that already
   teaches `so_outstanding`): `order_status` gains `do_outstanding` (DO / delivery order /
   pending delivery words) and `outstanding_both` ("both"); bare "outstanding" / "o/s" /
   "backlog" with no document word stays `outstanding`. `so_outstanding` unchanged.
2. **Tool pick** (`fetch.py`), REWRITTEN (R13, owner testing round 3, 13 Sep 2026 - "when
   we generate the outstanding summary for customer and for product it is different,
   they should be the same"): domain `order` AND (a resolved product OR a resolved
   customer) AND `order_status` in (`outstanding`, `so_outstanding`, `do_outstanding`,
   `outstanding_both`) → tool `crm_outstanding_report`. The customer-only carve-out this
   point used to state is RETIRED: a customer-only outstanding ask ("outstanding SO for
   BUIMACO") no longer falls to the legacy `so_outstanding` bucket - it reaches this same
   report with `customer_ids` set and no product. AC-1119's exactness rule still applies
   whenever a product IS given.
3. **Scope** (`fetch.py` + `answer.py`): `so_outstanding` → `scope=so`; `do_outstanding` →
   `do`; `outstanding_both` → `both`; bare `outstanding` → if the contact holds
   `sales_orders.outstanding`, ARM the scope question (no fetch this turn); else `scope=do`,
   no question (D13).
4. **Scope question** (`compile_state.py` + `pending.py` + `output_exchange.py`):
   `selection_context = "outstanding_scope"`, `last_result_set = [{idx 1, label "Sales orders",
   value "so"}, {2, "Delivery orders", "do"}, {3, "Both", "both"}]`, and the parsed filter set
   (`product_code`, `date_filter_start/end`, `customer_ids`, `warehouse_codes`) stored on the
   same turn state as `outstanding_filters`. Reply text = the plan's scope question. One-turn
   life, the `team_clarify` carry rule. Next turn: resolver gated on `pending.kind ==
   "outstanding_scope"` reads `reference_positions` (or the words sales/delivery/both),
   stamps `o["order_status"]` to the picked scope and restores the stored filters into the
   parser output so the business lane runs the report without re-parsing.
5. **Detail offer** (D10): a report with at least one non-empty block arms
   `selection_context = "outstanding_detail"` with rows `1 Sales order list` / `2 Delivery
   order list` (only the scopes present) and the same stored filters; no escalate offer on a
   hit. Next turn "1"/"2" re-runs `crm_outstanding_report` with `detail=so|do`; the MCP tool
   passes `detail` through and `present_response` renders `_outstanding_detail` when it is
   set. STICKY, REWRITTEN (R2, owner testing 13 Sep 2026, supersedes "One-turn life"
   below): "after '1' (SO list), typing '2' must give the DO list" - `_offer_carry`
   (`tail/compile_state.py`) must carry `outstanding_detail` the way it already carries
   `suggest_offer` / the tier offer (a new label this turn replaces it; a domain change
   clears it; otherwise it survives, including across the pick that just answered it),
   not `member_offer`'s TTL - the one-turn exclusion that used to sit beside `team_clarify`
   is removed for this kind. `outstanding_scope` KEEPS its one-turn life (it is a QUESTION,
   answered on the very next turn or not at all, same as `team_clarify` - AC-1132's own
   out-of-range re-ask already covers it by a different path, not this carry).
6. **Miss**: both requested scopes empty → `not_found_error_message` returns the presenter's
   miss text as `found_summary` and the frozen `escalate_message`, so the existing
   escalate offer + team picker follow unchanged (AC-1107). A hit never offers.
7. **Location** (D5): `"warehouse"` added to `ALLOWED["order"]`; the warehouse resolver in
   `lanes/business/services.py` tries exact `warehouse_code` first, then codes ending in
   `-<token>`; the resolved rows carry `warehouse_code`, and for `crm_outstanding_report`
   the param map sends `warehouse_codes` (csv) instead of `warehouse_ids`.
8. **Dates** (D3): `DATE_PARAMS["crm_outstanding_report"] = ("order_date_from",
   "order_date_to")`. No parsed window → no param.
9. **Customer** (D7): the resolved customer's id goes as `customer_ids` (csv). That param is
   ADDED to the report route and the MCP tool (AC-1113b); `customer_query` stays for n8n.
   The header prints `customer_name` from the response.
10. **Header** (`compile_state.py::_search_scope_header`): skipped when the tool was
    `crm_outstanding_report` (the report carries its own Product / Customer / Location /
    Order date lines; printing both would duplicate).
11. **Gate** (D13): `sales_orders.outstanding` added to `FIELD_REVEAL_KEYS` (label `Sales
    order outstanding`) and to `crm_outstanding_report`'s `restricted_fields` in the catalog
    (pinning test). In the lane, before the fetch: scope `so`/`both` requested without the
    key → scope forced to `do` and the reply starts with `Sales order figures are not enabled
    for your account.` after the header. Read from `ctx["access"]["attributes"]` the way
    `_CROSSDOMAIN_RUNG_GRANT` does (`answer.py:936, 1113-1122`).
12. **Verification**: `tests/chatbot/test_outstanding_lane.py` (pytest over the lane
    functions with a fake fetch) + a console case YAML `tests/chatbot/console_cases/
    2026-09-13-outstanding-report.yaml` (the six journey messages) run against the lane
    stack per `documentation/agents/chatbot-verification.md`. No world: worlds are derived
    from n8n captures, and this flow has none (per `tests/chatbot/worlds.py`).

## Tester's list (S2 and S4, one line per AC)

- AC-1110 `test_so_figures_share_one_population`: 10/3/7 from four seeded lines.
- AC-1111 `test_order_date_window_filters_so_and_do`: 2025 row excluded under a 2026 window.
- AC-1112 `test_warehouse_codes_filter_and_null_bucket`: filtered out when set; `code=None` when not.
- AC-1113 `test_customer_query_matches_name_not_debtor_code`.
- AC-1114 `test_so_rows_roll_up_lines_per_so`: 205 + 205 → one row, 410, locations joined.
- AC-1115, REWRITTEN R1 `test_do_block_covers_pending_dos_only`: one delivered (5), one
  pending (7) DO seeded, pending 7, count 1, `do_rows` lists the pending DO only.
- AC-1116 `test_breakdowns_sum_to_totals`.
- AC-1117 `test_scope_omits_block_and_response_model_keeps_every_field`.
- AC-1118 `test_route_permission_and_api_key_act_as`.
- AC-1119 `test_product_code_exact_no_siblings`.
- AC-1120 `test_catalog_lists_outstanding_report_tool`; AC-1121 `test_order_list_tools_expose_new_params`.
- AC-1130 `test_missing_scope_asks_outstanding_scope`; AC-1131 `test_scope_words_bind` (table).
- AC-1132 `test_scope_answer_runs_report_with_carried_filters` (pending.kind outstanding_scope, reference_positions).
- AC-1133 `test_location_token_resolution` (exact / suffix / none).
- AC-1134 `test_no_date_means_all_and_window_maps_to_order_date`.
- AC-1135 `test_hit_arms_outstanding_detail_and_no_escalate_offer`.
- AC-1113b `test_customer_ids_filters_report` (route + tool param).
- AC-1136 `test_customer_entity_becomes_customer_ids`.
- AC-1138 `test_detail_pick_reruns_tool_with_detail` (D10 on main); AC-1139 `test_report_skips_search_scope_header`.
- AC-1140 `test_no_so_key_skips_question_and_runs_do_only`; AC-1141 `test_no_so_key_explicit_so_ask_refuses_then_do_block`; AC-1142 `test_so_key_listed_on_reveal_screen`.
- AC-1143 (NEW, R2) `test_detail_offer_survives_a_pick`, `test_detail_offer_survives_a_casual_turn`,
  `test_detail_offer_drops_on_a_new_ask`, `test_detail_offer_survives_an_out_of_range_pick`.
- AC-1115 (R3 addendum) / detail rows `test_do_block_covers_pending_dos_only` (rewritten again):
  do_rows[].do_qty/delivered_qty back, delivered=0 shown not omitted;
  `test_detail_do_list_shows_delivered_even_when_zero` (MCP presenter).
- AC-1144 (NEW, D16 - scope words) `test_scope_word_*` table over sales/SO/delivery/DO/both/all/everything.
- AC-1145 (NEW, D16 - detail words) `test_detail_word_do_list_gives_do_detail`,
  `test_detail_word_so_list_gives_so_detail`, `test_detail_word_for_an_unoffered_scope_reprints_the_offer`.

## Design brief

Surface: WhatsApp text. Density: one report per ask, read a few times a day by management.
Nothing animates. No emoji. Bold only on block titles and detail-row labels (the existing
`*Label:*` convention).

## Risks

- `feat/chatbot-focus` is mid-build (14 local commits, never pushed). This lane inherits
  its churn; the captain rebases S4 once #847's open-question API settles. S1 to S3 do not
  touch the dialogue code and can start now.
- The `warehouses` table has codes with `/` (`SPARE/P`) and no `-`; suffix resolution
  splits on the LAST `-` only and ignores codes without one.
- 25,059 SO lines carry NULL warehouse; the `Unassigned` bucket will be large for older
  products. Printed, not hidden (D8 transparency).
