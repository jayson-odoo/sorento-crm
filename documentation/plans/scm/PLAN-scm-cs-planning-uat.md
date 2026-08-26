# PLAN - CS fulfilment planning: UAT fixes (board vocabulary, colour, transfers, set heads, PO occupancy)

Status: IN PROGRESS. Section 4 item 5, **G (PO occupancy) plus the AC-I3 form-upload
raise**, is BUILT on `feat/scm-uat-po-occupancy` (stacked on the section I lane): the
Allocated to panel below the PO lines grid, the Allocated column and filter on the PO list,
the `(product, warehouse)`-first line matcher and the placement relink both book channels
run, and `project_order_inquiry_import_service` raising the fixture's `[NL]` rows with the
cascade behind it (migration `423_committed_v_form_rows`).

Section 4 item 1 is BUILT on `feat/scm-uat-cs-board`: A + C + item 7
(FE only: `supplyVocabulary.ts`, `SupplyBar`, `SupplyLegend`, cell colour, per-location suggestion
wording, stock-documents header removed) and H (subtitle removed; Raised by / Raised at on the
worklist and the SO detail header; search by CS name or email prefix; Raised by filter off the
summary facet; reconfirm re-stamps the header).

Section 4 item 2, **ladder v3 (section 1b + 1c)**, is BUILT on `feat/scm-uat-ladder-v3`
(stacked on the above): rung 0 short-circuits on the lead-time window as well as the coverage
date; the ownership group (own location included) is drawn before the pool; group borrow left
the engine and is a manual pick; the whole-line rule reaches Amend; the Amend Buy is a
whole-line switch; a same-agent borrow asks who authorised it; the donor cell says what was
lent. AC-L1/L2/L3/L5/L6 pass.

Section 4 item 6, **E (stock transfers)**, is BUILT on `feat/scm-uat-stock-transfers`
(stacked on the decision strip): `projects.stock_transfers` (migration `419_stock_transfers`,
`TR-000001` numbering, the grant sweep off `inventory.stock.*` + `projects.projects.*`);
`project_supply_service._write_transfers` raises one `proposed` row per decided component
drawn from anywhere but the line's own location and cancels the superseded revision's open
rows ("Superseded by revision N"); `/api/v1/inventory/stock-transfers` with approve /
mark-moved / cancel / bulk-approve; the page at `/inventory-management/stock-transfers` plus
its detail (General | History, `RecordNavigation`, the three verbs); Transfers tabs on the SCM
SO detail and the sales-agent detail; a Moves line under the board popover's Decision card.
AC-E1/E3/E4/E5/E6 pass; `committed_v` and `on_order_v` are byte-identical before and after
(pytest). **AC-E2's six transfers for SO324132 rev 1 are not backfilled**: transfers are
written at confirm, and rev 1 predates the writer, so the six appear on the next reconfirm of
that order.

Section 4 item 3, **D (suggested vs decided)**, is BUILT on `feat/scm-uat-decision-strip`
(stacked on ladder v3): confirm freezes `line_snapshots[].proposed_components` beside the
decided `components`; the board contribution carries `proposed` (the frozen composition on a
covered line, the live ladder on an undecided one, `null` on a revision written before the
field); a covered line's rebuilt sources and its decision's reserve rows now carry their
`rung`, so the FE no longer falls back to the ownership-group reading for them; the board page
gains the decision strip (six cards, Suggested vs Decided, amber dot on a differing pair, card
click filters the grid); the cell popover gains a Decision card beside the Suggestion card;
the board list view and the SCM SO detail Lines tab gain Suggested / Decided columns.
AC-D1/D2/D3/D4 pass. Verified on :3080 against SO324132 rev 1, whose four lines predate
`proposed_components` and therefore read "Not recorded" on the suggested side - which is the
"old snapshots fall back" case the plan names, seen live. **The SO detail's Suggested column
is blank on an UNDECIDED line**: the plan wanted a live `proposal_for` call there, and 300
engine walks on a detail page is not worth the column, so the board stays the live surface.

Section 4 item 7, **B (popover location table)**, is BUILT on `feat/scm-uat-popover-locations`
(stacked on stock transfers): the cell payload lists every active site pool after the agent's
group, own site first, tagged `site_pool` (`_pool_locations`, off the same
`supply.site_pool_warehouses()` the ladder walks and the same per-location reader every other
row uses); a stated location with no stock row reads 0 rather than "Not stated" (both the
service and the table, one rule each side); `po_open_qty` on `BoardCellLocation` carries the
open PO balance at that location netted for the order-inquiry rows already placed on those
lines, SPO documents excluded, ONE query per board; and the table gains PO qty + Taken and
drops Reserved (nothing else on the screen read it). AC-B1/B2/B3 pass. Measured on :3080:
SRT382-6-DIY on SO415472 lists BRW-BB, the four -BB siblings and the five pools with BRW
leading (pool BRW: on hand 1728, available 1716, PO qty 0); CWCY605 on SO324132 reads Taken
454 / 267 / 211 at DC1-BB / MWH-BB / WH3-BB, 0 everywhere else, summing to the 932 needed.
**A section of ONE row still prints no subtotal** (a single-row section IS its own subtotal,
which is the rule already shipped; AC-B1 now says so). `po_open_qty` counts a line on the same
four tests every other on-order reader applies - `line_status = 'open'`, a balance still to
come, and `purchase_orders.status IN ('active', 'partial')`, SPO documents excluded - so a
`draft_recommendation` PO, which `decision_service` writes one of per supplier per run and
`on_order_v` leaves out, never reads as a purchase. A location OUTSIDE the board's fetched
warehouse set (only a cited cross-group Borrow donor can be one) keeps NULLs rather than
zeroes, because nothing looked there and a zero would claim it did.

**AC-A1 does NOT hold and the cause is not the ladder**:
SRT382-6-DIY is classified DEALER HOT-SELLING at BRW, so PLAN 3.3a keeps the pool for retail
and offers rung 3 nothing - see the trail reading below. Everything from item 3 down is still
to do.

Section 4 item 4's first half, **K (SPO documents live in `spo_allocations`)**, is BUILT on
`feat/scm-uat-spo-allocations` (stacked on the plan-page lane): migration
`420_spo_docs_in_allocations` widens the table and moves all 3,983 `SPO-` documents
(79,968 lines) across, the purchase-history import writes the SPO family there instead of
`purchase_orders`, and `on_order_v` plus the two incoming readers stop dropping a row that has
no shipment. AC-K1/K2/K3/K4 pass on the scratch schema. See the BUILT block under section K
for the ways the build differs from the paragraphs above, the `order_link_claim` decision,
the TRUST THE BOOK ruling and the open gap (no feed refreshes a live SPO balance). Migration 420
has been applied to the shared dev database once; the review added two guarded steps to it
(`add_claim_spo_side`, `repoint_spo_claims`), so it must be re-applied, and until it is every
`pg_session` test touching `scm.order_link_claim` reads `UndefinedColumn`.

Section 4 item 4's second half, **I (Link PO / Link SPO)**, is BUILT on
`feat/scm-uat-oi-links` (stacked on K): migration `421_order_inquiry_links` gives a row a
child table and merges the split rows back, `422_committed_v_link_netting` makes the
confirmed leg carry `qty - linked` instead of testing a state, and every screen reads Link
PO / Auto-link / Unlink with Linked / Partly linked. The walk is Q5 then Q7, location only
RANKS a candidate, a cited document comes first, and an SPO allocation is a candidate for
an ORDER BACK row alone. See the BUILT block under section I for the ways the build differs
from the paragraphs there. **Migrations 421 and 422 are APPLIED on the shared dev database
(26 August 2026)**: the 4 split groups (12 rows) merged to 4, 19 links were written, 0 rows
carried `BORROW_SHORTFALL`, 34 rows became 26, `committed_v` carries the link netting, and
SO414285 reads nine rows (AC-I6).

Lane: `.claude/worktrees/scm-uat` (FE :3080, BE :8080). One coder per worktree; queue behind that lane or cut a sibling from its head.
UAC: `scm-cs-planning-uat-acceptance-criteria.md` (alongside).

**AC-A1, measured on :3080 on 25 Aug** (SO415472 line 1, SRT382-6-DIY, 71 due 15 Sep 2026,
inside the reserve window). The cell reads `Buy 71`, and the trail says why:

| Rung | Offered | Taken | Why |
| --- | --- | --- | --- |
| 1 reserve_own (read-only) | 0 | 0 | 0 left at BRW-BB after 698 outstanding to 8 lines ranked ahead |
| 2 incoming | 0 | 0 | no supplier PO arrives by 15 Sep 2026 |
| 3 group_take | 0 | 0 | no BB sibling has positive available stock |
| 4 pool | 0 | 0 | **dealer hot-selling at BRW: BRW is kept for retail, so the pool is not offered** |
| 5 group_borrow | 0 | 0 | a person's pick, never proposed (section 1c) |
| 6 cross_group_borrow | 0 | 0 | nothing outside the group within the cap |
| 7 buy | 71 | 71 | took |

So "Use shared stock 71 from BRW" needs a ruling on 3.3a's dealer hot-selling gate, not on the
rung order. The vocabulary itself is right: SRTWT165-QT line 4 on the same order reads
"Shared 22 at BRW · Borrow (other) 35 from BRW-IB" - rung 4 then rung 6, whole line from stock.

## 0. What the captain reported (25 Aug, walking SO415472 / SO404352 / SO324132 / PO-2026/07-0029)

1. "Use own location, 71 from BRW" reads wrong. Own location = the line's `-BB` location. BRW (the plain site code) is the SHARED pool.
2. "Why is BRW the only pool considered? What about MWH, DC1, WH3?"
3. After Approve, stock taken from BRW (or borrowed from anywhere else) has to physically move to the line's location. Nothing today says so.
4. One page that shows, per line, what was SUGGESTED (buy / own / shared / borrow) and what was DECIDED, in the same words.
5. SO324132 has four lines; the order inquiry raised the SET code (CWCSC605), not the items. Items must flow, not the set.
6. When an order inquiry occupies quantity on a PO, the PO must show how much of its outstanding is occupied, by which OI and SO, and at which location (PO line says DC1; the demand is at BRW-BB). It must live BESIDE the PO line, not in it: the user re-keys the split in AutoCount and re-uploads, and an upload overwriting our split would lose it.
7. The "TPE-9204 · BRW  On hand 241 - SO 3334 + SPO 0 = Available -3093" header on the stock documents popover is redundant. Remove.
8. On the board grid a cell says nothing about the suggestion until it is opened. Colour the cell by the suggestion; once a decision differs, colour by the decision.

## 1. What the code does today (verified against the lane, 25 Aug)

| Fact | Where |
| --- | --- |
| The v2 ladder AS IT WAS before this plan (rung 0 coverage date, 1 incoming, 2 site pools own-site first then every other active pool, 3 group take at sibling `*-BB`, 4 group borrow from lower-ranked SOs, 5 cross-group borrow, 6 whole-line-or-Buy), with the line's own location never a reserve source (rule 7). Section 1b replaces it. | `app/services/scm/front_planning_engine.py` `propose_line`, `project_supply_service.py` `_pool_chain` / `_group_take_candidates` |
| Every active pool IS walked (`_site_pool_warehouses` = every warehouse that is some location's `pool_warehouse_id`: BRW, MWH, DC1, WH3, RSW). For SRT382-6-DIY the own-site pool BRW covered all 71 so the walk stopped there. The popover's location table lists only the agent group's members plus the own pool, so the other pools look "not considered". | `_pool_chain`, `BoardCellBreakdownDialog` location table |
| The FE labels split own/shared by SITE PREFIX: source `BRW` vs line `BRW-BB` share the site, so a pool draw reads "Use own location". That is the mislabel. | `project-sales/_shared/lib/boardSuggestion.ts` `rowOf` |
| `BoardContribution` already carries `sources[]` (proposal, with `rung`) and `decision` (`reserve[]`, `borrow[]`, `buy_qty`). The cell can be coloured client-side with no new endpoint. | `_shared/types/fulfilmentPlanning.types.ts` |
| Confirm freezes `line_snapshots[].components` = the DECIDED composition. The engine's proposal is not frozen anywhere; an amended line loses what the engine had said. | `project_supply_service.confirm` |
| There is NO stock transfer entity. Inventory models: stock, stock_batches, stock_ledger, warehouses. AutoCount is the stock ledger of record and is not integrated. | `app/models/inventory/` |
| Order-inquiry verbs: ORDER, RESERVE_AND_ORDER, ADVANCE, DELAY, CHANGE_SO, CANCEL_BALANCE, PRE_ORDERED, ALREADY_INBOUND, RELEASE, BORROW_SHORTFALL. `committed_v` counts ORDER rows in state raised only, so a new verb is invisible to netting for free. | `app/models/project_so.py` |
| SO324132: four SO lines, 932 each: CWCSC605, CWCX605-RL, CWCY605, WESERP10B. Decision rev 1: lines 2 and 3 reserved by group take (DC1-BB / MWH-BB / WH3-BB), lines 1 and 4 Buy 932. OI-000006 rows: CWCSC605 932 raised, WESERP10B 487 placed on PO-2026/07-0029 + 445 raised. So items DID flow; the defect is that CWCSC605 is a set HEAD that AutoCount exported alongside its three components, and the engine planned it as a fourth physical item. `product_sets` holds 2 sets today; CWCSC605 is not registered. | DB, `product_sets` / `product_set_members` |
| PO-2026/07-0029: one line, WESERP10B, 500 ordered / 0 received, warehouse DC1, expected 2026-08-04. Placed against it: OI-000001 (SO416191, 6 + 7, location BRW) and OI-000006 (SO324132, 487, location BRW-BB). Evidence rows exist in `order_inquiry_rows` (state placed, `po_line_id`) and `scm.order_link_claim`. The PO detail page shows none of it. | DB, `PurchaseOrderDetail.tsx` |
| PO book re-upload matches existing lines by `line_no` and updates IN PLACE (`po_history_service`), and the edit screen reconciles by id/SKU (`purchase_order_service._upsert_lines`). Placements survive a re-upload as long as the line numbers do not shift. Splitting a line in AutoCount DOES shift them. | `po_history_service.py:510`, `purchase_order_service.py:490` |
| Auto-place cascades earliest `expected_date` first and re-runs idempotently after a PO import, after a confirm, and on demand. | ladder-v2 plan section G2 |

## 1b. Ladder v3 (captain's ruling, 25 Aug, Q1)

> "if delivery date exceed lead time, directly buy; if within lead time, consider the group
> location first (only available quantity); if group location don't have then consider the pool
> (BRW, MWH, DC1, WH3); if pool also don't have then consider borrowing from other location's
> available quantity"

| Rung | v2 today | v3 |
| --- | --- | --- |
| 0 | beyond `reorder_coverage_until` -> Buy; beyond the ATP window -> surplus rungs only | beyond `as_of + lead time + buffer` (or the coverage date, which folds into the same rule) -> **rung 1 runs and NOTHING ELSE: incoming supply covering the whole open quantity is proposed as it stands, and anything short of that is a whole-line Buy naming the window. No stock rung is walked, however much sits beside the line; incoming is not a stock rung, because it is already bought and buying it again is a double purchase.** |
| 1 | timely incoming (SPO by required date) | unchanged; reads `spo_allocations` (section K) |
| 2 | site pools, own site first | becomes rung 3 |
| 3 | group take: `*-<group>` siblings at OTHER sites, own location never | becomes rung 2: **own group first, own location included**, own location then siblings by site. Siblings are capped at `max(min(free, available), 0)`; **the OWN location is capped at `available_to_this_line` instead**, because `available` nets every open sales order at a location including this line's own, so a line standing alone on exactly the stock it needs would read zero available and buy it. |
| 4 | group borrow from lower-ranked SOs' committed qty | **not proposed automatically**; ruled 25 Aug: stays as a manual pick in Amend / BorrowAddDialog |
| 5 | cross-group borrow, capped | rung 4: other locations' AVAILABLE quantity, cap kept |
| 6 | whole-line rule | unchanged, and EXTENDED to Amend (captain 25 Aug): a line is either wholly covered from stock (own group, pools, borrow, incoming in any mix) or wholly Buy; `_check_line` refuses a reserve/borrow + Buy mix on one line; the Amend dialog's Buy is a whole-line switch |

Engine change is confined to `propose_line` (rung order + the rung-0 short-circuit, which runs rung 1 and nothing else) and the callers that pass `outside_reserve_window`; `pool_reserve_capacity` is reused as it is, and `_group_take_candidates` gains the own-location cap above. `_group_sibling_warehouses` drops the `code != fact.own_code` exclusion. The service still reads `timely_qty` / `timely_refs` for a line beyond its window, because rung 1 runs for it. Golden set `tests/scm` expectations change with it; the parity test over singleton pools must stay byte-identical.

### 1c. Urgent order borrows from the same agent's other order (captain 25 Aug)
Covered today: rung 4 group borrow. Amend -> BorrowAddDialog lists donor lines at the group's locations; a donor sharing the line's sales agent is offered at ANY rank ("she can authorise"), another agent's order only when ranked below. Confirm writes `so_line_allocations` source `order` and raises the order-back for the donor line as an OI row (verb `BORROW_SHORTFALL`, due = donor's date). Same location, so no transfer.
Align with the rest of this plan: (1) manual only, never auto-proposed (ruled); (2) the order-back verb becomes `ORDER_BACK` (one verb with part 2 4b; `BORROW_SHORTFALL` renamed), so it links to SPO/PO like any order-back - BUILT as a DISPLAY rename only ("ORDER BACK" on screen), the column value waiting for section I's migration so no live row is stranded; (3) Amend requires a reason "Authorised by agent ..." on a same-agent borrow, stored in `so_line_allocations.reason`; (4) the donor's board cell reads "71 lent to SO415472". Mockup M2b.

## 1d. Ladder v4: availability is the GROUP's, not the warehouse's (captain, 26 Aug)

Sorento books every sales order at `BRW-<group>` while the stock sits at any `<site>-<group>`, so a per-warehouse "available" misleads twice: BRW-IB reads -22514 while MWH-IB reads +7000 for one pile of IB stock. The unit of availability is the OWNERSHIP GROUP.

| Rung / reader | v3 | v4 |
| --- | --- | --- |
| own group (rung 2) | own location capped at `available_to_this_line` (the rank queue), siblings at signed available each | `group_net = sum(on hand) + sum(SPO) - sum(SO)` over every `*-<group>` location (AutoCount's signed available, summed). **The offer is `max(group_net + this line's own open quantity, 0)`**, drawn own location first then siblings by site. The rank queue no longer decides availability |
| site pools (rung 3) | own-site pool first, each pool's own signed available | ALL FIVE pools as one pile: `pools_net = sum(signed available)` over BRW, DC1, MWH, RSW, WH3. The offer is `max(pools_net, 0)` - no per-pool cap, exactly as rung 2 has no per-location one - drawn own site first, then the other pools by on hand. This line's demand is booked at `BRW-<group>`, never at a pool, so nothing of it is inside `pools_net` and nothing is un-netted here |
| cross-group borrow (rung 4) | a donor warehouse's free stock, capped | the DONOR GROUP's net as a whole (all `*-IR`), capped as before; a single warehouse's on hand means nothing if its group nets negative |
| incoming (rung 1) | SPO at the line's location arriving by the required date | SPO counts INSIDE the group net (an SPO to BRW-IB is owed to the IB backlog first); what is incoming for this line is the positive remainder, same overdue wording |
| PO link candidates (section I) | tiers, never filtered | a group-location PO line is free only to the extent `group_net + sum(open PO at the group) > 0`; in deficit the group's lines are spoken for and only pool-location lines link; the row otherwise stays raised and buys |
| popover table (section B) | per-row figures with subtotals | same rows; the subtotal IS the number that matters, and Taken appears only where the net allows |
| order back | same-agent borrow only | a borrow from another `-xx` group or from another order raises an ORDER BACK row against the donor; a pool draw raises nothing (ruled 26 Aug) |

One function, `group_net(product, group)` (and `pools_net(product)`), is the only reader of
availability for the engine, the popover, the PO candidate walk and the WhatsApp stock
answer (S12), so none of them can disagree.

**THE OFFER, exactly (ruled while building, AC-L14).** `sum(SO)` counts every open line at
the group INCLUDING the one asking, so the net is the group's position AFTER this line is
served. What this line may take is therefore `max(group_net + its own open quantity, 0)`:
its own claim is handed back to it, every other line's stays netted. Without the un-netting
a line standing alone on exactly the stock it needs reads a net of zero and buys stock that
is sitting in the warehouse waiting for it - and every line whose only cover is an SPO
loses rung 1 the same way. The band it produces, on a line of 60: net -70 offers 0, net -20
offers 40, net 0 offers 60, and the offer is never more than the line asks for because the
ladder stops when the line is covered.

**What it does NOT do is re-introduce the queue.** The offer is the same for every line of
the group, so on a group whose book runs ahead of its stock EVERY line of it buys, the line
at the front included: 1,015 on hand against 9,080 owed proposes a Buy for the 80 at the
front as well as for the 9,000 behind it, where v3 reserved the 80. While the group is
short, its stock is promised to nobody in particular and whoever ships first uses it. That
is the price of `available_to_this_line` retiring, and it is the behaviour AC-L7 asks for.

Golden set changes again with the captain's sign-off. Status: RULED 26 Aug, build queued
ahead of part 3.

## 2. Vocabulary (ONE table, used by the board, the SO detail and the cell colour)

Decided by the engine's `rung`, never by comparing warehouse codes:

| Rung | Label | Colour token | Meaning in plain words |
| --- | --- | --- | --- |
| `group_take` at the line's own location or any `*-<group>` sibling | Use own location | emerald | stock the agent's group already holds, named per location ("454 from DC1-BB") |
| `pool` (BRW / MWH / DC1 / WH3 / RSW) | Use shared stock | sky | the site pool, named per pool ("71 from BRW") |
| `group_borrow` | Borrow from another order | amber | another sales order's committed quantity, order-back raised |
| `cross_group_borrow` | Borrow other location | amber | free stock outside the group |
| `buy` | Buy | rose | not held anywhere |
| `incoming` | Incoming supply | violet | an SPO already on its way; never folded into Buy |

`boardSuggestion.ts` becomes `supplyVocabulary.ts` under `project-sales/_shared/lib`, exporting `rowOf(source)`, `LABELS`, `COLOURS`, and a `describe(components)` that renders "Shared 71 (BRW) · Buy 0" style text for a row. Every surface below imports it.

## 3. Workstreams

### A. Labels (FE only, half a day)
- `rowOf` keys on `rung` only: `pool` -> shared, `group_take` -> own, `group_borrow` -> borrow-order, `cross_group_borrow` -> borrow-other. Delete `siteOf`.
- Suggestion rows name their locations with quantities per location ("Use own location 454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB"), not a bare list of codes.
- Remove the "On hand - SO + SPO = Available" header line from `StockDocumentsPanel` (item 7).

### B. Location table in the cell popover (FE + thin BE, one day)
- The table lists, in this order with a "Where" tag: the line's own location; every sibling of the agent's group (`*-BB` at MWH, DC1, WH3, RSW); every site pool (BRW, MWH, DC1, WH3, RSW). Subtotal rows per tag. Blank stock reads "0", never "Not stated" (that phrase was for an unknown, and an absent stock row means zero on the last upload).
- A "PO qty" column (captain 25 Aug): open PO balance at that location not yet linked to an OI row. Information only; Available stays On hand - SO + SPO (PO reaches a project line only through a link, part 2 journey step 2).
- A "Taken" column: the quantity the suggestion (or the decision, once decided) draws from that row. Rows not drawn on read "0", so "why not MWH" is answered by the row itself: it was listed, it had N, nothing was needed from it.
- BE: `board` cell payload gains the other pools' triples for the cell's product (already computed in `_pool_chain`; expose them on `cell.locations` with `where: 'pool'`).

### C. Cell colour on the grid (FE only, one day)
- Each cell shows a thin segmented bar under the quantity, one segment per kind in proportion, colours from section 2. One kind -> one solid segment. Mixed -> several. Below the bar, the dominant label in words ("Shared 71").
- Source of the bar: the line `decision` when the contribution is decided (confirmed revision OR ticked in the draft), else `sources`. So a cell whose decision changed from Buy to Shared flips from rose to sky the moment the tick lands, and again if the tick is cleared.
- Decided cells draw the bar solid; suggested-only cells draw it at 50% opacity. The existing "N/M decided" badge stays.
- The "already past" tint moves off the cell body and onto the column header only (the header already says "Already past"). Rose on a cell now means Buy and nothing else.
- Legend row ON the fulfilment-planning page, above the grid, always visible (captain: "make sure the legend is in the fulfilment planning page so the user knows what each colour means"); six swatches with the section 2 labels; the same legend component on the list view.
- List view (`FulfilmentBoardListView`) gets the same bar in its Suggestion / Decision columns so the two views agree.

### D. Suggested vs decided on the BOARD page (BE snapshot + FE cards, one to two days)
The captain means `/project-sales/fulfilment-planning?orders=...`, not the SO detail: "I need cards in this page".
- Board page gets a **decision strip** above the grid: one card per kind (Buy / Own / Shared / Borrow / Incoming) with two figures each, Suggested and Decided, summed over the selection, coloured per section 2. A kind whose two figures differ is marked. Clicking a card filters the grid to cells carrying that kind.
- The cell popover keeps the Suggestion card and gains the Decision card beside it (same four-row shape).
- The list view gets Suggested / Decided columns; the SO detail Lines tab gets the same two columns as a secondary surface.
- At confirm, `line_snapshots[]` gains `proposed_components` (the engine's composition at the moment of confirm, `rung` included) beside `components` (decided). Amend reason already lives there. Old snapshots without it fall back to "not recorded".
- SO detail Lines tab (`/scm/sales-orders/{id}`) gains two columns using section 2's `describe()`: **Suggested** and **Decided**. Undecided line: Suggested from a live `proposal_for` call, Decided blank. A differing pair gets the amber "changed" dot the board uses.
- Board cell popover: beside the existing "Suggestion" card, a "Decision" card in the same four-row shape once any contributing line is decided. Same component, two inputs.
- Board list view: the same two columns.

### E. Stock transfers: an entity, a page, a deliberate approval (BE + FE, three days) - Q2 ruled
Captain: "we need a stock transfer entity" and "a person needs to deliberately approve the transfer in the transfer page".
- New table `projects.stock_transfers` (CompanyScopedMixin): `transfer_no` (TR-000001, same numbering shape as `inquiry_no`), `so_line_id` (core), `project_sales_order_id`, `supply_decision_id`, `product_id`, `from_warehouse_id`, `to_warehouse_id`, `qty`, `kind` (`own_group | pool | borrow`, from the rung), `state` (`proposed | approved | moved | cancelled`), `proposed_at`, `approved_by/at`, `moved_by/at`, `cancelled_reason`, `autocount_ref` (the transfer document number keyed into AutoCount, free text). Migration next after the lane head.
- Written at confirm for every reserve/borrow component whose source differs from the line's location, state `proposed`. Reconfirm cancels the open ones ("Superseded by revision N") and writes fresh rows. A same-location component writes nothing.
  - **Netting rule (found in review, 26 Aug).** A component's quantity is netted against what has ALREADY `moved` for the same `(so_line_id, product_id, from_warehouse_id, to_warehouse_id)` on earlier revisions of this order, and a row is written only for the remainder above zero. Without it a carried line re-proposed a movement the warehouse had already made, and the stock would have been carried twice. A larger quantity after a move raises a row for the difference alone.
  - The supersede sweeps by `project_sales_order_id` + open state, keeping only the revision being written. Keying it on `previous.id` stranded rows open forever whenever a best-effort write failed on the revision in between.
  - The write stays best-effort (savepoint) so it cannot fail a promise already made, but the outcome is REPORTED: `transfers_written` / `transfers_failed` on the confirm result, and the board toasts "Transfers not written: N" when the second is non-zero.
- **Transfers page** `/inventory-management/stock-transfers` (sidebar under Inventory management, captain 25 Aug) with a detail form view `/inventory-management/stock-transfers/{id}` (General | History, `RecordNavigation` "12 / 48" like Users, Approve / Mark moved / Cancel in the header; same layout view and edit): DataGrid, filters state / kind / from / to / product, search; row actions Approve (confirm dialog), Mark moved (asks for the AutoCount ref), Cancel (reason). Bulk Approve on the selection. Detail shows the SO line, the decision revision, and the product's stock by location (`ProductStockTab`, the product page's own component).
  - BUILT as `/inventory-management/...`, not `/inventory/...`: every other inventory screen in this app lives under that segment (`warehouses`, `stock`, `stock-batches`, `stock-ledger`), and one page in a route group of its own is a second place to look.
  - **SO and AGENT are typed into the search box, never picked from a select.** The page's audience is the warehouse, and neither `master_data.sales_agents.view` nor `scm.dashboard.view` - the two reads an agent select would need - is granted to a warehouse role, so a dropdown would 403 for exactly the people the page is for. The search matches the SO number, the agent code and the person label; `sales_order_id` / `sales_agent_id` stay as API params, which is what the two detail tabs below pass.
- Not demand, not supply, no view change: `committed_v` / `on_order_v` untouched. Stock figures move only when the next stock upload lands; the page shows "moved, awaiting stock upload" until then (no automatic closure, per the ruling).
- Board popover Decision card ends with "Moves: 454 DC1-BB -> BRW-BB · 267 MWH-BB -> BRW-BB" before Approve; SO detail gains a Transfers tab; the sales-agent detail too.

### F. Why CWCX605-RL and CWCY605 did not reach the order inquiry (answer, and the fix rides on E)
Captain: "SC is a product, not a set". Withdrawn: nothing about sets. The real question is "X and Y are on the SO detail, why did they not flow?". Answer from the decision snapshot (rev 1, 25 Aug 08:42): lines 2 and 3 were decided **Use own location** (group take 454 DC1-BB + 267 MWH-BB + 211 WH3-BB, and 354 + 79 + 499), not Buy. Only Buy rows become order-inquiry ORDER rows; a reserve row has no purchase to ask for, so today it leaves no trace anywhere but the decision. Lines 1 (CWCSC605) and 4 (WESERP10B) were Buy 932 and did flow. With section E every one of those reserves becomes a **Transfer** (DC1-BB -> BRW-BB 454, and so on), so X and Y show up on the Transfers page as the movements they are, and the order-inquiry page stays purchasing's list. No set logic, no backfill of OI-000006.

### G. PO occupancy panel (BE read + FE panel, one to two days)
- PO detail gains an **Allocated to** section on the LINES tab below the lines table (captain 25 Aug), NOT columns in it. Per PO line: outstanding (`qty_ordered - qty_received`), allocated (sum of placed OI rows on `po_line_id`), free (outstanding - allocated), then one row per placement: OI no, SO no, customer, agent, qty, needed-at location (`order_inquiry_rows.stock_location`), PO line location, and a "location differs" mark when they differ (DC1 vs BRW-BB).
- BE: `GET /scm/purchase-orders/{id}` gains `allocations[]` per line from `order_inquiry_rows` (state placed) joined to `order_inquiries`, `projects.sales_orders`, customers, agents. No write path.
- PO list gains an "Allocated" column (sum per PO) and an "Allocated" filter.
- Re-upload safety: after the AutoCount split comes back, line numbers shift, so `po_history_service` MUST match existing lines by `(product_id, warehouse_id)` first and `line_no` second before creating new lines, and the auto-place re-run after import must prefer a PO line whose `warehouse_id` matches the row's `stock_location`. Test: import a book where one DC1 500 line became BRW-BB 487 + BRW 13; placements land on the matching lines, nothing is orphaned.

**BUILT on `feat/scm-uat-po-occupancy`** (stacked on the section I lane), migration
`423_committed_v_form_rows`. What the build found, and where it differs from the four
paragraphs above:

- **The panel reads `order_inquiry_links`, not `order_inquiry_rows` (state placed).** The
  paragraph above predates section 3.I: since migration 421 a row may sit on two lines of
  one document, `order_inquiry_rows.po_line_id` is the DERIVED display of the first link,
  and reading it would under-count every multi-link row. A cancelled row's links are
  excluded, the same predicate `links_for_rows` already applies for the worklist and the
  SO detail, so the three readers cannot come to disagree.
- **`allocated_qty` is on every list row; `allocations[]` only on the single read.** "Is
  this order spoken for" is a list question and "by whom" is a detail-page one, and a page
  of 50 orders must not pay for 50 placement queries. The list filter is the EXACT
  predicate the column sums, so the two cannot disagree.
- **A line nobody is waiting on is absent from the panel.** The lines grid above it already
  prints every line; the panel answers who is waiting, and a block of three zeroes per line
  is noise on a 200-line order. The panel itself is always rendered, with its empty state.
- **`free` is floored at 0.** A line promised more than it has left is over-committed, which
  is a finding for the buyer, never a credit they may spend again.
- **The matcher alone cannot satisfy AC-G3, so the placements MOVE.** `po_history_service`
  now keys existing lines on `(product_id, warehouse_id)` first and the ordinal second, and
  that is right on its own merits: the structured extract carries no line number, so
  `purchase_history_reader` numbers rows POSITIONALLY, and a split shifts every ordinal
  below it - the test that pins it swaps two locations' quantities under the old rule. But
  matching rewrites a LINE; it cannot move a placement from one line to another, which is
  what "keeps every placement attached to the line whose warehouse matches" asks for. So
  `ProjectOrderInquiryService.relink_to_matching_lines` is the step that finishes it, run at
  the end of BOTH book channels (`po_history_service.apply`, and
  `outstanding_import_service.apply` for the PO doc type - the latter is the one the buyer's
  own "Upload purchase orders" action goes through, which the paragraph above did not name).
  It is deliberately narrow: within one purchase order, exact location only, never off a line
  that already fits, whole links only, and best-effort so a defect costs a relocation the
  next upload makes again rather than the book. It does NOT touch `actioned_by` / `actioned_at`
  - those say who in purchasing dealt with the instruction, and a book upload is not a person
  dealing with it - and it walks the documents in chunks of 200, because a purchase-history
  upload names thousands in one call.
- **AC-G5 holds and is pinned.** Nothing in G writes `purchase_order_lines`; the test
  snapshots every line before and after a detail read and a filtered list read.
- **PR note - the new Allocated column and existing saved column preferences.** Checked
  rather than assumed: `mergeColumnOrderWithLeafColumns` places a column a saved order has
  never seen "after its nearest preceding neighbour rather than at the far right", so
  Allocated lands beside Lines for a buyer who already has a saved config; and saved
  visibility is MERGED over the listing's defaults rather than replacing them, so the column
  is visible for them too. No preference reset is needed and none is shipped.

### H. Order-inquiry page: who pushed it, and when (BE + FE, one day)
- Remove the subtitle "Every project and every adopted sales order, by delivery month."
- `order_inquiries.raised_by` / `raised_at` already exist (FK users, set at confirm). Expose them on the worklist row as **Raised by** (user's display name, never the id) and **Raised at** (MY time), on the SO detail Order inquiry column tooltip, and on the per-SO inquiry header. `so_supply_decisions.confirmed_by/at` is the same person; `raised_by` is what the OI shows.
- Search bar matches the CS name (`users.name` / email prefix) beside item code, SO number, project. Add a **Raised by** filter (SearchableSelect of users who have raised any inquiry).
- Every reconfirm re-stamps `raised_by`/`raised_at` on the header and carries the actor on each new row (`actioned_by` stays purchasing's).

### I. Link PO / Link SPO (rename + candidate rules; BE + FE, two days) - needs Q5
- Rename the verb everywhere: "Place on PO" -> **Link PO**; "Auto-place" -> **Auto-link**; "Unplace" -> **Unlink**; state `placed` keeps its DB value, reads "Linked". Route names unchanged.
- **SPO is a link target for ORDER BACK rows only** (captain, 25 Aug; part 2 section 4b defines the `ORDER_BACK` verb), **read from `spo_allocations`** (Q6 ruled: "SPO should be in spo_allocations, not purchase_orders"; section K moves it there). Candidates = open `spo_allocations` rows of the product (allocated minus received) first, then open PO lines by `expected_date`. The row records which: `spo_ref` for an allocation, `po_ref` / `po_line_id` for a PO line; new `spo_allocation_id` FK on `order_inquiry_rows` (SET NULL).
- **Location rule (Q5, ruled).** Candidate lines are ranked by location fit, never filtered out: (1) same location as the row's `stock_location` (BRW-IB row -> a BRW-IB line), (2) same group at another site (DC1-IB), (3) the site pool (BRW, then the other pools), (4) sibling locations at the site (BRW-BB), each tier by expected date. A link outside tier 1 shows "location differs" on the PO occupancy panel (section G), which is the split instruction for AutoCount. 
- **One OI row per SO line, many links per row** (captain, 25 Aug, on SO414285: "1 line here should correspond to 1 line in sales order, so 1 line can be placed by multiple PO and SPO"). Today the cascade SPLITS the row: M310-CR-PJ 8 became two rows (5 + 3, two lines of 202607-S0105) and MSK11C 67 became 10 + 57, so nine SO lines read as eleven rows. Fix: `order_inquiry_rows` stays one row per SO line per revision with the FULL quantity; a new child table `projects.order_inquiry_links` (`row_id`, `po_line_id` | `spo_allocation_id`, `qty`, `linked_by/at`, `auto` marker, `claim_id`) carries each placement. Row state: raised (no links) | partly linked (sum < qty) | linked (sum = qty). `po_ref` / `po_line_id` / `spo_ref` on the row become derived display (first link) and stop being written. `committed_v` nets `qty - linked qty` per row instead of testing `state = 'placed'`. The worklist row shows "Linked 8 of 8: 202607-S0105 L3 5, L7 3" with the PO occupancy panel (G) reading the same child table. Backfill: merge split rows of one `(so_line_id, supply_decision_id)` into one row + N links.
**BUILT on `feat/scm-uat-oi-links`** (stacked on the section K lane), migrations
`421_order_inquiry_links` and `422_committed_v_link_netting`. What the build found, and
where it differs from the paragraphs above:

- **`cited_document` is its own column, not `spo_ref`.** The plan has `po_ref` / `spo_ref`
  becoming the derived display of the first link, and a CITATION is a different fact from a
  placement - CS naming `202604-S0083` on the form is what the walk tries first, not where
  the row already sits. Overloading either column would have made "where is this linked"
  unanswerable, so the row gained one nullable column and both old ones became display.
- **The row state gained `partly_linked`.** `placed` keeps its stored value and reads
  "Linked": renaming it would have rewritten `committed_v`, the worklist filter and every
  saved column preference to say the same thing in a different word.
- **Location is a `(tier, sub-rank)` pair internally.** Q5 names four tiers and puts "BRW,
  then the other pools" inside the third, which one integer cannot express. The sub-rank
  orders the row's own site pool ahead of the others; the tier a person reads is still the
  four the plan names.
- **`ORDER_BACK` has TWO writers and they are told apart by the LINE.** The donor hole a
  borrow leaves (`_raise_borrow_shortfalls`) and a Buy CS marked "Order back" in Amend.
  They can never meet on one sales-order line, because the whole-line rule (AC-L5) makes a
  line either wholly stock or wholly Buy, so the line is the discriminator: the Buy path
  supersedes and nets its rows like an ORDER, and the donor path keeps its own netting.
- **`committed_v` counts an order back at the DONOR's location**, from the row's own
  `stock_location`, not at the core line's warehouse. The row hangs off the BORROWING line,
  so reading `sales_order_lines.warehouse_id` for it would put the shortfall in a warehouse
  that never had one - the exact mis-attribution the verb was created to avoid. Measured: 0
  rows carry the verb today, so this changes no live number.
- **`L3` is printed only where the book numbered the line.** `purchase_order_lines.source_ref`
  carries it and `spo_allocations.spo_line_number` carries it, and neither is set on
  202607-S0105 or 202608-S0002 on the dev copy - so AC-I9's "L3 / L7" reads as the LOCATION
  instead ("202607-S0105 BRW-BB 5"), which is a fact rather than an invented ordinal.
- **An `ALREADY INBOUND` row still traces to a purchase order through its own `spo_ref`.**
  That reference is a coverage note the netting engine writes, never a placement, so it
  never became a link; the worklist keeps it as the last leg of the Supplier / PO no
  coalesce behind the two link legs.
- **The Order Inquiry Form upload does NOT raise rows.** `project_order_inquiry_import_service`
  writes stock locations onto sales-order lines and PO claims, and nothing else - making it a
  writer of `order_inquiry_rows` is a new feed, not a rename. The READER now recognises
  `ORDER BACK` in the delivery-date cell and reports the count, so the fact is available;
  the fixture's `[NL]` rows are "recorded as not raisable", which its own section 5 allows.
  **CLOSED on `feat/scm-uat-po-occupancy`** - `_raise_rows` is that feed, and what it found
  is below.

**AC-I3 finished on `feat/scm-uat-po-occupancy`: the form upload raises the `[NL]` rows.**

- **Two cases, and only two.** The book states no line for this instalment -> raise with
  `so_line_id` empty, which is the honest record (pointing it at the nearest line of the same
  item would attach the quantity to somebody else's instalment). The book states the line AND
  the form says ORDER BACK -> raise against that line, because an order back is a fact about
  the line that no board decision produces. A dated ORDER row whose instalment the book
  already carries raises nothing: the demand is in the book and a second instruction for it
  is a second purchase.
- **ORDER BACK ONLY, and the unit is the SHEET ROW.** A dated row raises nothing whatever
  the book says about it: a date is ordinary demand, the sales-order book is its record, and
  a row the book has not got yet stays in `lines_unmatched` exactly as it always has -
  raising one would put a second instruction beside a line the board already reads. And the
  order backs are read off `parsed.rows`, not off the collapsed instalments: an order back
  has no date, so the `(SO, item, delivery date)` key cannot tell two of them apart, and
  collapsing turns two things CS asked for into one. Measured on the committed forms: form 1
  raises **14**, form 2 restates all **14** and raises none, and every row ends at BRW-IB
  because form 2 amends the location - which is exactly what the fixture sheet's `[NL]`
  column says should happen. `_instalments` is untouched and still collapses for the
  demand-writing path, where a repeat genuinely is a second call-off of one dated line.
- **Identity is CONTENT first, POSITION second**, within a `(sales order line, item)` group,
  each held row consumed at most once - the same two-pass shape
  `po_history_service._match_existing_lines` uses. Pass one pairs on location, cited document
  and quantity, which is what separates SRTWCX7405-RL-S-PJ's 10 at BRW-IB from its 12 at
  BRW-BB and lets form 2 move the 12 without either landing on the other. Pass two takes the
  next unconsumed row, which is how an amended instruction finds the row it amends and how
  form 1's two identical C-FH14 30 at BRW-IB rows pair at all - no content key can separate
  those, and it does not matter which is which.
- **The line match ignores the date, but only among UNDATED lines.** Matching
  `(SO, item, location)` across dated lines would be worse than not matching: SO381895 carries
  open SRTWCX7405-RL-S-PJ lines at BRW-IB for 25 August, 5 and 10 September, and the form's
  order back is about the 10 August quantity AutoCount closed. Attaching it to one of those
  says this quantity is that line's, when that line has its own quantity and is already
  counted - and the fixture's `[NL]` marking ("no open SO line in the book FOR THIS FORM
  ROW") says so outright. An undated open line is the shape an order back's OWN line has
  when this feed owns the order, and that is the only case where the two are the same thing.
- **The verb comes off the delivery-date cell, never the remark.** `ORDER BACK` is the words,
  a date is `ORDER` due then, and only an `ORDER_BACK` row may name an SPO allocation - so
  reading that cell wrong decides which documents the row may be linked to at all. An ORDER
  BACK row keeps a NULL `delivery_date`: inventing today, or the sales order's own date,
  would put it on a horizon nobody asked for.
- **`cited_document` is the FIRST document the remark names; the rest goes on the note.**
  `SPO-2026/08-0061 & 202606-S0082` cites the first and keeps the second as words, because
  the second document is the answer when the first cannot cover the quantity - and the walk
  proves it: the allocation holds 2, so the row links 2 there and 8 to `202606-S0082`.
- **The inquiry hangs off an ADOPTED planning record.** SO381895 has no project mirror, so
  the raise adopts the core order first (`ProjectSOAdoptionService.adopt`, idempotent) and
  reuses the amendment-less inquiry the board would use. An order adoption REFUSES (retail
  class, not open, nothing outstanding) raises nothing and is named on the result as
  `orders_not_plannable` rather than being swallowed.
- **It records no per-row import outcome, deliberately.** Every sheet row already carries
  exactly one outcome from `_create_orders` - the `[NL]` rows all take the
  `document_owned_elsewhere` skip, because the SO book owns SO381895 - and the job's progress
  bar is one outcome per source row, so a second here would report 83 processed out of 69.
  What the step did is on the SUMMARY (`rows_raised`, `rows_restated`, `rows_linked`),
  exactly as the stock-location and claim steps already report theirs.
- **`committed_v` needed a THIRD leg** (migration `423_committed_v_form_rows`). Both existing
  confirmed legs join on `so_line_id` and on an active supply decision, and a form-raised row
  has neither - so without it the fourteen instructions are raised, shown to purchasing, and
  invisible to the plan that decides what to buy. The new leg reads the ROW's own `item_code`
  and `stock_location`, joined on the code AND the company together (what
  `uq_products_company_product_code` makes unique). INNER on `products` - a row naming an item
  we do not hold is demand for nothing - and LEFT on `warehouses`, so a row naming no location
  is still in the view at a NULL warehouse that every reader's `(product, warehouse)` join
  matches nowhere: counted at no location rather than invented at one. Measured before the
  change: 0 rows carry `so_line_id IS NULL`, so it moves no live number.
- **The leg deliberately does NOT extend to a row that carries a `so_line_id`**, and that is
  the one place this build overrules its own review. The review asked for it, guarding only
  against the CONFIRMED leg; the leg that actually bites is the SHEET one, which counts every
  open line of an order whose `demand_origin` is `scm_order_inquiry` - which this very upload
  sets. So a row raised against a line the book carries is already counted at that line, and
  adding the row would have the planner buy the same quantity twice. One test pins all three
  cases on one product: the null-line row counted once, the line-carrying row not counted
  here, and the location-less row present at no warehouse.
- **The auto-link runs at the end of the upload, scoped to the ROWS it raised** - a new
  `row_ids` argument on `auto_place_for_products`. A product scope is right for "this purchase
  order was just confirmed, who was waiting for this item" and wrong here: the form's items are
  items half the company's open orders also name, and one CS spreadsheet must not re-cascade
  somebody else's instructions.
- **Every citation is ranked, not just the first.** `SPO-2026/08-0061 & 202606-S0082` names
  two and the row has one `cited_document` column, so the rest go on the note behind a fixed
  prefix and `_cited_documents` reads them back - ONLY that segment, never the whole note,
  which also carries the cascade's own "Linked to ..." stamp and would otherwise pin the walk
  to the document the row already sits on. The candidate sort key carries a citation RANK
  rather than a flag, because a flag puts both documents in one bucket and lets the dates
  decide between two the form already ordered.
- **An upload with nobody to attribute a link to does not link.** `linked_by` is nullable, so
  the cascade would happily write a row of anonymous placements nobody can question. The actor
  is the uploader, failing that `EXTERNAL_API_KEY_ACT_AS_USER_ID`, and failing both the rows
  are left for purchasing's own Auto-link button and the result says so (`link_error`).
- **`raised_by` is stamped only on a header this upload CREATED.** An inquiry the board raised
  belongs to the CS who confirmed it, and re-stamping it would make the order-inquiry page
  name whoever last sent a spreadsheet as the person who decided the order.
- **A restatement appends to the note and never blanks it**, so the cascade's stamp and the
  relocation a book re-upload wrote survive an amended form.
- **Not done here, and named rather than half-fixed: `planning_change_service` still reads
  `INQUIRY_PLACED` alone** in its "already actioned" predicates, so a `partly_linked` row
  reads there as wholly unactioned. Conservative rather than wrong (its unlinked half IS
  still changeable), and part 3 owns the link-shift on a planning change anyway.

- **Cascade order (Q7 ruled: PO date first).** Candidates order by `purchase_orders.issue_date` ascending, then line `expected_date`, then document number. Today's key is line `expected_date` (`_open_po_lines_for_product`); one-line swap. Candidate list shows both dates.
- **SO detail shows the links too:** `/scm/sales-orders/{id}` Lines tab gains a **Linked to** column (PO / SPO document + line + qty per link, via the SO line's OI row and its `order_inquiry_links`), beside Order inquiry and the Suggested / Decided columns. Same data as the worklist and the PO occupancy panel, one reader.
- `committed_v` nets the unlinked remainder of every ORDER row; a fully linked row leaves confirmed demand exactly as `placed` does today.
- Worklist: "PO no" column becomes **Linked to** (document + kind badge PO / SPO); filter Linked = po | spo | none.

### I2. Order inquiries read like the board (captain, 26 Aug)
The schedule (matrix) view and the list view show the row's state the way the board shows a cell: a `SupplyBar` under the quantity and a decision strip of cards above. Three kinds only: **Use SPO** (violet, quantity linked to SPO allocations), **Use PO** (sky, quantity linked to PO lines), **Buy** (rose, raised and unlinked). A partly linked row is a split bar ("PO 5 · Buy 3"). Cards sum the current filter and click to filter, same component as the board's strip. No new endpoint: rows carry `links[]` and `linked_qty`; the summary gains one facet for the three totals. When a PO is confirmed and the cascade links the row, the cell flips from Buy to Use PO by itself. Legend: none (the cards carry the labels). Queued after ladder v4, one PR.

**BUILT** (26 Aug), and one thing the paragraph above did not name: pressing a card has to narrow the LIST as well as the matrix, and the list pages server-side, so the press is a query parameter rather than a client-side cut of the rows on hand. `GET /order-inquiries` (and the export, and the summary) take `kind=spo|po|buy`, meaning every row CARRYING that kind - a row linked 5 of 8 to a purchase order answers to `po` and to `buy` alike. That is a different question from the existing `linked` filter, which asks only where a row's links point, so the two live side by side. A CANCELLED row carries no kind at all: its quantity is not owed and its links are already history (`links_for_rows` hides them), so it is dropped from the filter and from the facet alike, which is why the three totals need not add up to `total_qty`. The summary's own totals honour `kind` like every other filter, while the `kinds` facet is computed with it dropped - the same rule the month, supplier, project and raised-by controls are computed by, so pressing one card leaves the other two readable. AC-I13 came down to one line: confirming a purchase order now invalidates the order-inquiry query keys, as deleting one already did.

### J. UAT fixture: SO381895 with the three CS forms (data, half a day)
- The UAT basis is SO381895 (YOTU BUILDER / LOT 2752, agent Cyndi), whose three Order Inquiry Forms of 12 Aug (ADDITIONAL ORDER, BRW-IB), 19 Aug 10:25 (amended: stock location BRW-IB) and 19 Aug 17:23 (ADVANCE ITEM) sit in `Sorento/phase-2/User Requirements/purchasing/order_example_files/`. SO381895 (76 lines), SO414033 (112) and SO414050 (63) are already in the core `sales_orders` book; the cited POs 202604-S0083, 202606-S0082, 202607-S0031, 202607-S0067, 202608-S0015 and SPO-2026/08-0061 are in `purchase_orders` with open lines at BRW / BRW-BB / BRW-IB. SPO-2026/08-0046 and 202606-S0019's cited items are NOT present; note on the UAT sheet.
- What the forms teach the engine: an ORDER BACK row is a Buy whose supply is already on order, and CS names the document. So the expected UAT outcome per row is: ORDER -> Buy raised, auto-linked to the earliest fitting PO/SPO line at BRW-IB; ORDER BACK with a cited document -> Buy raised and linked to THAT document (the form is the oracle; a mismatch is a finding, not a failure); ADVANCE ITEM -> verb ADVANCE on the existing rows with the new date.
- Deliverable: `documentation/plans/scm/scm-cs-planning-uat-fixture.md` listing every form row with expected verb, quantity, location, link target, and the actual result column to be filled during UAT.

### K. SPO documents live in `spo_allocations` (BE import + netting, two days) - Q6 ruled
- Today the PO book import files every `SPO-` document into `purchase_orders` / `purchase_order_lines` with `source_system = scm_spo_history` (`po_history_service`, `doc_family == FAMILY_SPO`), and `spo_allocations` holds ONE row on the dev copy. `on_order_v` reads `spo_allocations` only, so every SPO is invisible as incoming supply, and the ladder's rung 1 (timely incoming) never fires.
- Change: the import writes each SPO line as one `spo_allocations` row (`spo_number`, `spo_line_number`, `product_id`, `warehouse_id`, `allocated_quantity`, `quantity_received`, `receipt_status`, `po_line_id` when the SPO names its PO), upserted on `(spo_number, spo_line_number)`. `purchase_orders` stops receiving SPO documents; the existing SPO rows there are migrated across once (data migration, reversible) and deleted.
- Consequences, all intended: SPO becomes incoming supply in `on_order_v` and in rung 1; the PO book page no longer needs its SPO filter; Link SPO (section I) has real rows to link; `spo_conversion_service` (draft shipment -> SPO) already writes this table, so the two writers meet on one shape.
- Tests: import round trip on the 2026 PO & SPO book; `on_order_v` totals before/after; rung 1 fires for a line whose SPO arrives before the required date.

**BUILT on `feat/scm-uat-spo-allocations`** (stacked on the plan page lane, PR #311), migration
`420_spo_docs_in_allocations`. What the build found, and where it differs from the paragraphs
above:

- **Three families move, not one.** By the `SPO-` NUMBER rather than the stamp: 3,517 documents
  (74,016 lines) under `scm_spo_history`, 414 (5,237) under `scm_po_history`, and 52 (715) under
  `scm_upload`. The last group is the whole of the OPEN balance: everything else is closed and
  fully received history, so the `scm_upload` documents are the only rows that can ever read as
  incoming supply, and AC-K3's SPO-2026/08-0061 is one of them.
- **Schema.** `inbound_shipment_id` and `warehouse_id` become nullable, `location_code` keeps the
  book's raw spelling for the 6,520 lines naming a location we do not hold, and the unique key
  moves to `(company_id, spo_number, spo_line_number)` (the old triple forbade 13,305 real
  repeated groups). Added beside them: `source_system`, `issue_date`, `expected_date`,
  `supplier_id`, `unit_cost`, `currency`, `line_status`.
- **`po_line_id` is NULL on every migrated row.** The plan expected "when the SPO names its PO":
  neither export carries a PO reference column (checked against the 27-header alias table), so
  there is nothing to resolve it from. Section I is where an SPO gets linked to a PO.
- **`scm.order_link_claim` is the one reference that had to give.** 12,390 claims point their
  `po_line_id` at an SPO line and no table has a column that could name an allocation instead.
  The claim holds both document numbers as TEXT, so the cache and its `resolved_at` are cleared
  and the claim keeps saying what it said; the downgrade re-resolves them by the resolver's own
  rule. Every other foreign key into an SPO document measured 0, and the migration REFUSES with
  its counts rather than letting `ON DELETE SET NULL` orphan one silently.
- **`on_order_v` changes twice**: LEFT JOIN to the shipment (an SPO exists before a container is
  booked, and the inner join is what made every one of them invisible) and `warehouse_id IS NOT
  NULL` (supply we cannot place is counted nowhere rather than everywhere). `line_status = open`
  joins the predicate, so history is excluded by construction, as it already was.
- **The PO book page has no SPO filter to remove** (measured: no document-family parameter on
  `GET /purchase-orders` and no such control on the list). The FE change is the SPO Allocations
  page reading `location_code` where there is no warehouse.
- **Open gap, named rather than fixed: nothing refreshes a live SPO balance.**
  `outstanding_reader` already SKIPS every `SPO-` row of the purchase book ("this book does not
  carry them") and the history channel writes closed rows, so after this migration the 715 open
  lines are a snapshot that no upload updates. Whoever takes section I should decide which feed
  owns them. Under the ruling below that snapshot IS the position - 39,110 units on 292
  (product, location) pairs, every one of them overdue - which is the honest reading of a book
  nobody has restated, and the fix is a feed that restates it, not a filter that hides it.
- **RULING (captain, 26 Aug): TRUST THE BOOK.** An open SPO allocation - allocated minus
  received above zero, a receipt status that is not `fully_received`, a line that is not
  closed - IS incoming supply, and it stays supply until the re-uploaded PO and SPO book
  shows it received. **A promised date in the past does not remove it.** The book is the
  record of what was bought and what is still owed; a date is a promise about when, and a
  supplier being late is not evidence that the goods stopped existing. Dropping the 715
  past-dated open lines would have told the planner to buy 39,110 units a second time.
  Rung 1 is unchanged: it still requires `expected_date <= required_date`, which a past date
  always satisfies, and a row with no date is never timely, so it covers nobody. What a
  passed date changes is the WORDING: the trail, the reason and the cell popover read
  "SPO-2026/08-0061 arrives on 1 Aug 2026 (overdue 25 days)", so the buyer can see which
  promise is being leaned on and go and chase it, instead of the row being silently dropped
  or silently read as fresh. One copy of the rule in `app/services/scm/spo_supply.py`
  (`open_incoming_clauses`, `overdue_days`), repeated in SQL by `on_order_v`, so
  `_spo_rows`, `_inbound_pools`, the coverage screen's already-on-order figure and the view
  cannot come to disagree. Supply that cannot be PLACED is still counted nowhere: a row with
  no warehouse is not incoming at any location.
- **The claim gained an SPO side, `scm.order_link_claim.spo_allocation_id`.** Clearing
  `po_line_id` was not enough: 12,393 claims naming 2,989 sales orders would have been
  permanently unresolvable, `sales_order_service.with_links` would have shown every one of
  those orders as "awaiting purchase order", and `po_history_service` would have gone on
  writing more of them. `order_link_service._purchase_side` now resolves an `SPO-` number
  against `spo_allocations` (lowest line number wins where a document states the item twice)
  and a claim is resolved on either column. Migration 420 adds the column and re-points the
  cleared claims; the downgrade drops it and re-resolves `po_line_id`.
- **An imported row states its own receipt.** The SPO Allocations listing recomputes
  `quantity_received` from approved GRN lines, which is right for a row this system raised
  and wrong for 74,016 history lines that arrived stating theirs: recomputing returns 0, and
  three years of delivered purchases would have read as outstanding. Recomputation is now
  applied only to rows with no `source_system`. The same ownership rule scopes the external
  GRN triple lookup and the external bulk create.
- **Also unchanged: `coverage_service`'s dated in-transit timeline** still drives off
  `inbound_shipment_lines`, so an SPO with no shipment does not appear on it. AC-K3 is about
  `on_order_v`, which it does.

## 4. Order of work (UAT-driven)

1. A + C + item 7 + H (FE plus one small BE read) - the board and the OI page read right.
2. Ladder v3 (section 1b) - engine + golden set; everything downstream reads its output.
3. D (board decision strip, popover Decision card, snapshot key).
4. K (SPO into `spo_allocations`) then I (Link PO / Link SPO, tiers); J's fixture sheet written before I starts.
5. G (PO occupancy panel, then the import matcher).
6. E (stock transfers entity + page).
7. B (popover location table).

Each item is one PR off the lane head; A+C+7 may ship as one.

## 5. Tests
- vitest: `supplyVocabulary.test.ts` (rung -> label/colour, describe()), cell bar proportions and decided-vs-suggested source switch, legend, SO detail columns, PO Allocated panel + split summary, popover table Where/Taken.
- pytest: snapshot carries `proposed_components`; TRANSFER rows written/superseded and invisible to `committed_v`; set-header exclusion from proposal/board/committed/OI plus OI-000006 backfill; PO detail `allocations[]`; PO import matcher on shifted line numbers; auto-place prefers matching warehouse.
- agent-browser evidence run on :3060 for the SO415472 / SO324132 / PO-2026/07-0029 journeys via the sidebar.

## 6. Out of scope here
The order-inquiry side (purchasing's board, place-on-PO UX) is the next planning session, per the captain: "this is just the CS part".

## 9. Rulings (captain, 25 Aug, via the Lavish review)

- **Q1 rung order:** beyond lead time -> Buy directly; within: group locations first (available only), then pools, then borrow other locations' available. Section 1b.
- **Q2 transfers:** a real stock transfer entity; a person deliberately approves it on a Transfers page. Section E.
- **Q3 sets:** withdrawn ("SC is a product, not a set"). Section F now answers the actual question (X and Y were reserved, not bought).
- **Q4 colours:** ok.
- **Q5 link location:** same location, same group location, pool, then sibling location. Section I.
- **Q6 SPO:** in `spo_allocations`, not `purchase_orders`. Section K.
- **D:** the "one page" is the fulfilment-planning board, with cards. Section D.

- **Q7 cascade date:** PO document date first, then line expected date, then document number.
- **Group borrow from another SO:** manual Amend pick only.
- **Style:** keep it simple and straight; no over-explaining.

### Open, found while building ladder v3 (25 Aug)

- **RELEASE can no longer raise an order-inquiry row.** `planning_change_service._suggestion`
  offers `release` only when the held composition carries a RESERVE, and `_release_rows` then
  needs `buy_qty > 0` on that SAME composition - which is exactly the stock-and-Buy mix AC-L5
  abolished. Measured: a wholly bought line delayed 197 days suggests `keep` ("Only a Buy is
  held ..."), and a wholly reserved one releases with nothing to tell purchasing. So the verb
  fires only on revisions frozen before AC-L5. Needs a ruling: either a release of a bought
  line should move its ORDER row to the pool (today it stays put with a DELAY row beside it),
  or RELEASE retires with the mixes that justified it.
- **AC-A1 needs a ruling on PLAN 3.3a, not on the rung order** - see the trail reading in the
  status block at the top of this file.
- **The confirm-time proposal ledger tracks the own-site POOL only, not group-take capacity.**
  `_proposals_for` draws the pool down across the lines of one confirmation (as `proposal_for`
  does), but nothing nets the ownership group's `available_to_this_line` between siblings - so
  N lines of one order sharing a product AND a location can each freeze the full available
  quantity, and the decision strip's **Suggested can exceed the stock that actually existed**.
  This mirrors `proposal_for` exactly, so the sheet and the board still agree; what neither
  does is bound the group rung the way the pool rung is bounded. It bites on orders shaped like
  SO381895 (76 lines). Fixing it means a second running ledger keyed on (product, location)
  through `_group_take_candidates`, which is the same shape as the pool one. Not done here: the
  DECISION is still checked against live capacity by `_check_line`, so nothing over-promises;
  only the frozen suggestion can read high.
- **`components` and `proposed_components` are not byte-identical in shape, and readers key on
  `kind`.** The decided side infers a reserve's rung from the location (a group sibling means
  `group_take`, anything else `pool`) and writes no `rung` key at all on a buy or an incoming;
  the proposed side carries the engine's own rung on every component. So the two agree about
  what was drawn from where and may differ about the rung on a decided buy. Compare them on
  `(kind, qty, source_location)` and treat a missing rung as "the kind already says it".

All ruled. Go/no-go on the order in section 4.

## Part 3. A changed sales order (captain, 25 Aug: SO381895 forms (2) -> (3), SRTWCX7405-RL-S-PJ 10 + 10 + 5 on 25 Aug / 5 Sep / 10 Sep becomes 25 on 19 Aug)

**Status:** **BUILT + REVIEWED** on `feat/scm-uat-so-change` (stacked on I2, #331), 26-27
Aug. UAC AC-P3-1..P3-13 in the acceptance criteria file. **No migration**: every new fact is
derived or rides an existing JSON column, so the lane head stays
`427_sales_agents_class_backfill`. 28 pytest in
`tests/test_planning_change_apply_on_board.py` (red first, on the real database because
`scm.committed_v` is a view the blank scratch schema has none of) plus vitest for the Was /
Now cell, the pre-mark, Confirm carrying the batch, the per-order block and the retired
page's entry points.

**The captain accepted the coder's two rulings** (27 Aug): AC-P3-13's "three annotated
cells" reads "three annotations", because a closed instalment that is the only line of its
product at its own date has no cell to be annotated on and lands on the survivor's; and a
line the book moved arrives UNCOVERED carrying the batch's own proposal, because its frozen
composition is about a line that no longer exists. The UAC wording was corrected to match.

**Review fixes (27 Aug), all with a test:** one press confirms ONE order of the batch
(`apply(..., only_pso_ids=)`), and `applied_at` is stamped only once no order it left out is
still pending - a batch-wide stamp used to lock every other order of the same upload; the
board's Confirm blocks per order, not batch-wide; a `release` / `retire` row confirmed from
the board is accepted as the batch row's own reaction rather than posted as an amend, so
AC-P3-10's RELEASE branch actually fires from the screen it is decided on; the closed lines'
documents reach the survivor BEFORE the cascade (`defer_auto_place`), which used to fill the
survivor's headroom from any free purchase-order line and re-deal the closed lines' own
supply to a stranger; a survivor with PARTIAL headroom now SPLITS a retired link rather than
refusing all of it; a settle answers the `CANCEL_BALANCE` an earlier revision raised for the
same line; a lone `placed` row carrying no link declines the settle (the SO349754 WESERP10B
shape) and is netted the old way; `late` reaches the sales-order detail's Linked to column
(`_line_links` never copied it); a proposal-less row lands on its OWN cell; a board opened on
a batch is not subject to the 50-order cap; the batch listing is two queries per page rather
than two per row; and the batch-confirm refusal carries `failing_lines`, so it names WHICH
line and why exactly as an ordinary Confirm does.

What shipped, and where it differs from the paragraphs below:

- **The board takes `?batch=` beside `?orders=`.** Every changed line's cell carries a Was /
  Now table of three rows (Qty, Date, Decision) in board words through the same
  `partsBreakdown` the Suggestion and Decision cards use, so the batch's own vocabulary never
  reaches the screen. A line the book CLOSED has left the board, so it has no cell of its own:
  it is annotated on the surviving cell of the same product on the same order and reads
  `Closed` in the Now column. **Captain confirmed (27 Aug):** AC-P3-13 said "three annotated
  cells"; on a board whose closed instalments are the only lines of their product at their own
  dates, the three tables land on ONE cell, and the UAC now says "three annotations". A
  changed line that DOES have a cell of its own gets its own table there - the row's own
  `project_line_id` is read before the proposal's, so a second instalment no longer borrows
  the first one's cell.
- **A changed line arrives UNCOVERED, carrying the batch's own proposal.** A covered line's
  `sources` / `qty_proposed_*` are its frozen composition rebuilt, so a line the book has
  moved offered to confirm the OLD quantity - measured live on SO381895: the board sent Buy 10
  for a line open for 25 and the server refused after Confirm was pressed. The frozen
  composition is not lost; it is the Was column.
- **Confirm carries `batch_id` on the board's own confirm endpoint.** One press, one call, one
  revision: the composed lines become the batch rows' compositions, the batch applies, and a
  line the press decided that the batch does not carry rides along beside them. A second press
  is refused 409 with the date it was applied on.
- **`refresh_for_decision` gained a settle-in-place seam** (`settle_in_place_line_ids`,
  threaded through `confirm`): on a line a planning change is applying, the existing row is
  UPDATED - same id, new quantity, new date, links kept, the previous value on its note -
  rather than superseded and re-raised. Only where the line has exactly ONE still-owed row;
  with two, this build has no way to say which the book moved and the supersede stands.
- **AC-P3-8 retires the `CANCEL_BALANCE` for a drop** the row absorbs, and only the EXCESS
  goes back, latest-arriving document first (never a whole placement the line still wants).
  `test_apply_qty_down_reduces_buy_and_raises_cancel_balance` was rewritten to say so.
- **A closed line's LINKED row is cancelled too**, which reverses the old "a placed row is
  real supply, leave it" rule: the supply does not vanish with the row, it moves to the line
  that still needs it, and what no line needs is unlinked and free again. An `actioned` row
  still keeps its state - that is a person's word.
- **RELEASE ruling (26 Aug), and the dead path is alive:** a wholly-Buy line delayed beyond
  the reserve window now suggests `release` (it was gated on a reserve-and-Buy mix AC-L5
  abolished, so it suggested `keep` and told purchasing nothing). A row a buyer already put on
  a document keeps its links and becomes a purchase for the POOL; a row with none hands
  purchasing a DELAY carrying the previous date. No `RELEASE` verb row is raised at all.
- **A line a settle wrote raises no separate DELAY / ADVANCE row** - the row itself carries
  the new date and the previous value, and a second row beside it is the duplicate
  instruction one-row-per-line exists to stop. The skip is keyed on what
  `refresh_for_decision` actually settled, never on what the apply offered it.
- **`late` is derived, not stored**: the link's own expected date against the row's required
  date, read on the worklist's Linked to column and the sales-order detail's.
- **`moved_transfer` rides `facts_json`** and is lifted to the wire by `row_out` - a phrase,
  because nobody compares it against anything. Nothing reverses a movement.
- **The batch page is retired** (route, client, `PlanningChangeDecisionControl`, `FactChip`,
  `PlanningChangeReactionPill`). The list row and its new Plan action, the sales-order list's
  Changed badge and the SO detail's Plan button all open the board on the batch; the
  import-job card points at the list, because a book upload moves many orders at once.
- **Two defects the browser found that the suite did not**, both now pinned: the covered-line
  proposal above, and the link shift reading its own pending write (`SessionLocal` runs
  `autoflush=False`, so the cancellations were invisible to the shift's query while an
  autoflushing test session watched them move). The test session is built the way the
  application's is now.

**Browser evidence (AC-P3-13), lane :3080/:8080, 26 Aug.** The RQ worker is absent on this
lane, so the SO-book re-upload could not run: the form (3) book change and `build_batch` were
driven through the service directly, and everything after that is the real screen. Planning
changes list -> the row for `SO381895 form (3) 19 Aug 17:23.xlsx`, Plan ->
`?orders=SO381895&batch=<id>` -> three Was / Now tables on the SRTWCX7405-RL-S-PJ cell
(line 24 `Qty 10 -> 25`, `Date 25/08/2026 -> 19/08/2026`, `Decision Buy 10 -> Use shared stock
5 from BRW, 10 from WH3 . Borrow other location 10 from WH3-NTC`; lines 46 and 68 `Closed` in
every Now cell), `1 approved` without a click, Confirm -> 200, revision 3, batch applied.
**Where the dev copy differs from the fixture sheet:** SO381895's three instalments carried no
order-inquiry rows at all (the fixture assumes form 2 applied with links on them), so they were
planned first through the real confirm, which raised and auto-linked all three; and the fresh
ladder meets the 25 from shared stock plus a cross-group borrow rather than buying it, so the
Order Inquiries page shows the survivor's ORDER row WITHDRAWN and an ORDER BACK of 10 at the
donor beside two cancelled rows - not the fixture's one raised row of 25. The Buy-only shape
AC-P3-5/6/11 describe is pinned on the seeded pytest chain instead.

**What exists:** `planning_change_service` + `/project-sales/planning-changes` (18-19 Aug). A batch is born when a re-uploaded SO book changes a PLANNED line: one row per line with what changed, what the decision holds, and a suggested reaction (Keep / Release / Replan / Reduce / Retire, rule table in `PLAN-so-book-diff-replanning.md` section 0). The planner accepts per row on a separate page and presses Apply; OI rows get DELAY / ADVANCE / CANCEL_BALANCE / RELEASE.

**Captain's idea:** same interface as normal ordering, change annotated, decision remade per change, then it flows to OI. Agreed, with these corrections:

| Captain said | Keep / change | Why |
| --- | --- | --- |
| user selects the SO and goes to planning change | **Trigger stays the SO re-upload.** Entry points: Planning changes list row -> Plan, SO list "Changed" badge -> Plan. Both open the board with `?orders=SO381895&batch=<id>` | The AutoCount SO is the truth; the form (3) is CS's email, not an input. Nothing to diff until the SO is re-uploaded |
| same page as fulfilment, with the change annotated | **Yes.** Board cell shows a small Was / Now table (Qty, Date, Decision), not a sentence (captain 25 Aug: structure, not words). Decision words only (Buy 25, Use own location ...): the batch's reaction vocabulary (Replan / Retire / Reduce / Keep / Release) is internal and never shown; a line closed in the book reads "Closed". Links are not shown on the board. Unchanged lines keep their decision, no tick needed. Approve on a changed line = the batch row's decision; Confirm = batch apply + new revision. The separate batch page is retired; the list stays as the entry point | one vocabulary, one screen |
| 3 OI lines -> one becomes 25, two become 0 and cancelled | **Yes, but the 25 row is UPDATED in place, never cancel-and-recreate** (one OI row per SO line, part 1 I). Lines 2 and 3 are closed in the book -> Retire -> their rows cancelled | recreating the row would drop its links |
| PO / SPO allocated to the 0 lines shift to the 25 line | **Yes, automatic on apply:** links on a cancelled row move first to the surviving row of the same product on the same SO, then the cascade fills any remainder. A link that now arrives after the new delivery date stays linked and is flagged "arrives late"; purchasing decides | nothing lost, nothing silently re-dealt |
| (not said) qty DOWN with more linked than needed | unlink the excess from the latest-dated link first; replaces today's CANCEL_BALANCE exception row | one rule for over-cover |
| (not said) a Transfer already MOVED for a line now retired | flag on the change row ("10 moved BRW -> BRW-IB, line cancelled"); no automatic reverse | stock moves are physical; a person decides |

Work: one PR. Board reads the batch (`batch` query param), annotates, pre-marks; Confirm calls batch apply; link-shift + late flag + over-cover unlink in `planning_change_service.apply`; batch page retired. UAC: SO381895 re-uploaded with the (3) change -> board shows 3 annotated lines, Approve all -> OI row 25 raised with the moved links, two rows cancelled, board and OI agree.

**Order:** after part 1 I (links table); before E is not required.
