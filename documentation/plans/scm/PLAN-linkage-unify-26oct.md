# PLAN: one answer to "where are this SO line's goods now" (LINKAGE-UNIFY)

Status: SCOUT DONE 26 Oct 2026 (report only, no product code); behaviour card filed with crew,
build waits on the owner's answers. The fix is L in total, cut into the slices of section 6.
Lane LINKAGE-UNIFY, branch `crew/linkage-unify`, base origin/main 263643ae36.

Evidence (committed beside this plan, `evidence/linkage-unify/`):
`inventory-A-order-inquiry.md` (23 readers, OI screens), `inventory-B-supply-stock-debt.md`
(37 readers, supply side), `inventory-C-ingest-so-chatbot.md` (27 readers + 7 writers, ingest,
SO side, chatbot/MCP), `data-D-divergence-dev.md` (dev data), `sql/` (every query, read-only,
run on `sorento_cagent_stack` with `default_transaction_read_only=on`). Below, `A-R5` means
reader R5 of inventory A, and so on. Paths are under `sorento_crm_backend/` unless stated.

## 1. Why (owner, 26 Oct)

"This is the point of breaking, cause our calculation of linkage of PO SPO and SO is not unified."

Real case, verified (`sql/v-l880.sql`): OI-2609-0128, SO364824 core line 880, SRTSS4210, 486.
One link, 486, on PO 202607-S0100 (line closed, 486/486 transferred). AutoCount moved it onto
SPO-2026/09-0107 line 9 (486/486, `fully_received`, line closed, bin BRW-BB, 976 on hand there).
Shipment PL-2609-060 still reads `in_transit`, `actual_arrival_date` NULL,
`warehouse_arrival_date` 2026-09-28. Four readers, four answers:

| reader | answer for L880 | why |
|---|---|---|
| OI Lines tab SPO column (A-R2) | PO only, SPO "-" | `derived_spo_open_clauses()` (`project_order_inquiry_service.py:366-386`) shows a chained SPO only while incoming |
| PO popup SPO column (A-R9) | SPO-2026/09-0107 | `_spo_numbers_by_po_line` (`order_inquiry_worklist_service.py:2716-2757`) uses `visible_line_clauses()` only |
| Stock Debt (B-S4/S5) | pinned, on hand 486 at BRW-BB | `_holds` + `_transferred_allocations` (`scm/stock_debt_service.py:1885-1952, 1957`) follow the goods |
| OI row state (A-R14) | "On PO/SPO" | `_coverage_state` (`project_order_inquiry_service.py:9659-9669`) is link quantity only |

## 2. Inventory (every reader of the chain)

Root facts, each verified in code:

- F1. A link never changes target when AutoCount transfers a PO line. No writer repoints
  `po_line_id` -> `spo_allocation_id` (A-F1, C-Q1: `follow_book_for_rows` PS:3738 only adds links
  for unmet need; `relink_to_matching_lines` PS:13195 moves within one PO; plan
  `PLAN-oi-follow-book-chain.md:140` "LEFT AS IS"). Every reader must bridge PO -> SPO itself.
- F2. `purchase_order_lines.qty_received` is the AutoCount TRANSFER (incl. Cancel PO qty,
  `models/procurement.py:929-931`), never a receipt. What landed is `spo_allocations.quantity_received`.
- F3. Nine spellings of the PO -> SPO key (A section 3, B section 5, C section 3). The strict one,
  OI-SPO-EXACT (`from_po_number = po_number`, `btrim` both refs, same product, company, visible),
  is used by A-R2, A-R5, A-R9, the importer (`project_order_inquiry_import_service.py:2020`) and
  Stock Debt. Loose ones: own-arrival `from_po_line_ref = source_ref` only (`project_supply_service.py:3107,
  3184, 3312`), reserve-received no btrim/no product (PS:13453), ingest hook no product
  (`api/v1/external/ingest.py:735`), `_book_names_target_for_line` exact (PS:4014). Measured: the
  loose own-arrival key gives 0 cross-PO pairs on dev today (`sql/v-key.sql`), so unifying it is
  behaviour-neutral on this data.
- F4. "Received" has five meanings (C section 0). For a PO link the OI code says received when
  `qty_received >= qty_ordered` (PS:8254-8284, copied at PS:3346-3412), i.e. on TRANSFER, while
  Stock Debt says still on the water. Only `po_lines_with_open_chained_spo` (PS:13453) corrects
  it, and only inside CS reserve.

Readers that decide per SO line (the ones that must agree), grouped:

| family | readers (file:line) | SO -> PO | PO -> SPO | states it counts | differs |
|---|---|---|---|---|---|
| OI display | A-R1 `links_for_rows` PS:8081; A-R2 derived SPO PS:8391; FE Lines tab `orderInquiryHeaderLinesColumns.tsx:136-224`; worklist cell `orderInquiryWorklistColumns.tsx:358-470`; SCM SO "Linked to" `scm/sales_order_service.py:855` | OI link | strict key, open only | PO: received on transfer; SPO: open/in transit only | landed SPO vanishes; Lines tab has no received pill, worklist has one |
| OI received test | A-R3 PS:3346 (replan "used", split, settle, reallocate); A-R4 PS:13453-13554 (CS reserve); planning change `planning_change_service.py:1604`; reserve email `order_inquiry_reserve_service.py:374` | OI link | none, or no-btrim key | PO received = transferred | goods at sea read "stock in hand"; email says "(received)" |
| OI row state | A-R14 `_coverage_state` PS:9659 | link qty | none | none | "On PO/SPO" for every class, incl. dead documents |
| Worklist cards/filters | A-R5 WS:1108-1241, 3066-3175 | OI link | strict, open only | in transit only | landed qty falls back into "On PO"; no received stage |
| PO / SPO popups | A-R9 WS:2595-2757; A-R10 WS:2759-2891; SPO document `procurement_service.py:2942` (so_covered :3055); SCM PO detail `scm/purchase_order_service.py:145, 323, 468` | link on that doc only | strict (PO popup, numbers only); none elsewhere | all visible | rows on the other half of the chain are invisible; SCM PO "Qty received" is the transfer |
| Candidate walk | A-R11 PS:10272-10553, netting `_linked_by_target` PS:10000-10050 | product | none | open PO, incoming SPO | 486 placed on a transferred PO line leaves the SPO looking free (code read; UNVERIFIED live) |
| Placement engine | A-R12 / C-R11 `pair_needs` import_service:2160, `_less_own_shipments` :2081 | book `from_so_line_ref` | strict | gross capacity | the only reader that nets PO against its own SPO; runs at link creation only |
| Stock Debt + board | B-S4/S5 SDS:1614-2080; B-S6 `_landed_holds` SDS:2510; B-S7 `_book_so_holds` SDS:2598; B-S11 `assignments_for` -> `planning_assignments` PSS:2806 | OI link (S4), book text (S6/S7) | strict (S5), loose (S6) | on order / in transit / landed -> on hand | the only follower of PO -> SPO into stock; book-text pins are a second SO -> PO path |
| Own-arrival credit | B-P4 PSS:3107-3600 (board walk :1768, confirm recheck :6244, OI picker PS:3109) | book text | loose | landed only | different key from Stock Debt |
| Loading plan | B-R5 `scm/container_request_service.py:443-475` | OI link, SPO links only | none | open SPO | PO-placed lines read unplaced even after transfer |

Readers that never match an SO line (product x warehouse piles: B-S3, B-P1, B-P2, B-P5, B-I2,
B-I3, B-I4, B-R1..R4; outstanding report B-I1/C-R18; chatbot SO status C-R20 has no supply
statement at all) rely on F2 (the transfer moves `qty_received`), which is right for pile
arithmetic. They stay out of this plan.

## 3. Divergence on dev data (`data-D-divergence-dev.md`, `sql/d-03.sql`, `sql/d-08.sql`)

Live placements on open SO lines, by class (placements / units):

| class | meaning | n / units | OI SPO col | PO popup | Stock Debt | OI state |
|---|---|---|---|---|---|---|
| a | PO still on order | 728 / 64,391 | PO | - | PO hold | On PO/SPO |
| b | PO transferred, SPO in transit | 114 / 9,776 | PO + SPO | SPO | SPO hold | On PO/SPO |
| c | PO transferred, SPO received | 191 / 16,806 | **PO only** | **SPO** | **on hand at SPO bin** | On PO/SPO |
| d | PO transferred, no SPO names it | 9 / 232 | PO (received) | - | **nothing** | On PO/SPO |
| e | direct on SPO in transit | 34 / 1,010 | SPO | n/a | SPO hold | On PO/SPO |
| f | direct on SPO received | 1,048 / 112,198 | SPO (received) | n/a | on hand at bin | On PO/SPO |
| x | direct on SPO retired, 0 received | 4 / 443 | **hidden** | n/a | nothing | **On PO/SPO** |
| z | PO line cancelled, nothing transferred | 20 / 2,565 | PO | - | nothing | **On PO/SPO** |

Partial transfers: 0 on dev (every transferred PO line has received = ordered). Class d split
(`sql/v-d-cancel.sql`): 1 is a Cancel PO (qty_cancelled 11), the other 8 (221 units) are closed
local POs with stock at the PO's bin (e.g. WESERP10B PO-2026/03-0024, BRW 1,924 on hand).

Sample SO lines where screens disagree (codes only):

| # | OI / SO line | product, qty | chain | OI SPO col | PO popup | Stock Debt | state |
|---|---|---|---|---|---|---|---|
| 1 | OI-2609-0128 / SO364824 L880 | SRTSS4210 486 | PO 202607-S0100 -> SPO-2026/09-0107 L9 486/486 | - | SPO-2026/09-0107 | on hand 486 BRW-BB | On PO/SPO |
| 2 | OI-2609-0053 / SO403889 L816 | SRTUB206 14 | PO 202608-S0049 -> SPO-2026/10-0032 L6 10/10 | - | SPO shown | on hand 10, 4 short | On PO/SPO |
| 3 | OI-2609-0549 / SO398090 L1408 | CGB762 303 | PO 202606-S0019 -> SPO-2026/10-0015 L19 395/395, BRW-BB now 0 | - | SPO shown | nothing (bin empty) | On PO/SPO |
| 4 | OI-2609-0013 / SO314592 L80 | WESERP10B 182 | PO-2026/03-0024 30000/30000, no SPO | PO (received) | - | nothing | On PO/SPO |
| 5 | OI-2609-0252 / SO396349 L784 | SRTSS3170 294 | PO link -> SPO-2026/09-0107 L12 received + 294 direct on retired L7 | PO + L12; L7 hidden | L12 | on hand for L12 only | On PO/SPO (counts retired link) |
| 6 | OI-2609-0289 / SO313699 L464 | SRT6638 1260 | direct SPO-2026/01-0005 L328 1260/1260, BRW-IR now 0 | SPO (received) | n/a | nothing (bin empty) | On PO/SPO |
| 7 | OI-2609-0194 / SO396348 L64 | SRTA8046 701+3+194 | PO links + direct on SPO-2026/10-0008 L76 in transit | agree | agree | agree | control |

Other measured facts: `inbound_shipments.actual_arrival_date` is NULL on all 359 dev shipments,
so the "landed" test in `spo_supply.open_incoming_clauses()` (`scm/spo_supply.py:76`) never fires
here; landing is decided by receipt fields alone. 2,724 allocations are fully received while their
shipment still reads `in_transit`. 24 SPO allocations carry more live placed qty than they
allocate (923 units, `sql/d-14.sql`).

## 4. Design: one function, one home module

**Home: `app/services/scm/goods_chain.py`** (new, beside `spo_supply.py`, which keeps the state
predicates). It is not a new rule. It is the #1850 split lifted out of Stock Debt unchanged
(`_transferred_allocations` SDS:1957, `_follow_capacity` SDS:175, `_landed_qty` SDS:158, the
placement loop SDS:1885-1952), plus the two hop states nobody models today (classes d and x/z).
Second and later callers exist today (section 2), so the lift is earned.

**API (batched, one read per call):**

- `chains_for_links(db, link_ids) -> {link_id: LinkChain}` and `chains_for_rows(db, row_ids)`.
- `placements_on(db, po_line_ids=(), spo_allocation_ids=())`: the reverse view, every placement
  whose chain passes through those documents (for the PO / SPO popups and the SPO document).
- `po_spo_key_clauses()`: the one PO -> SPO key (OI-SPO-EXACT + company + `visible_line_clauses()`).
- `LinkChain`: link id, row id, core SO line id, placed qty, `hops`. `Hop`: kind (`po` | `spo`),
  state, qty, document ids / numbers / line number, warehouse, ETA (via `spo_supply.shown_date`).

**Hop states (one vocabulary, each with exactly one test):**

| state | test (existing code) | qty |
|---|---|---|
| `on_order` | PO hop, `ProjectSupplyService.open_po_line_clauses()` PSS:10067 | `min(rest, ordered - received)` |
| `in_transit` | SPO hop, `open_incoming_clauses()` AND allocated > received | `_follow_capacity` |
| `received` | SPO hop not incoming, `_landed_qty > 0`; warehouse = the SPO's bin | `min(rest, landed)` |
| `received_direct` | PO line transferred, not cancelled, no SPO under the key (class d, 8 of 9) | owner Q4 |
| `dead` | PO line cancelled / closed with nothing transferred (z), Cancel PO (d, 1 of 9), SPO retired with 0 received (x), SPO closed with nothing landed | 0 |

Hop quantities foot to the placed qty; anything left is reported as `unplaced` (an over-placed
SPO, 24 allocations on dev).

**Split rule (why every screen gets the same answer):** the chain reads ALL live placements on
each touched PO line, whatever the caller asked for, in `linked_at, id` order (SDS:1809), and
hands them SPO capacity earliest expected first (`expected_date nulls last, spo_number, line, id`,
SDS:2009-2014), then the PO's own on-order rest. A placement's chain therefore never depends on
which screen asked. Direct SPO placements are not netted against followed ones (parity with
Stock Debt today; the 24 over-placed allocations are a follow-up).

**Out of the chain on purpose:** physical bin stock (Stock Debt keeps `found_empty` SDS:1813 and
the `assign()` floor caps; the chain says where the goods were received, not whether they are
still there), ETA wording (`spo_supply.MaskedEta`), the book-text SO pins (`_book_so_holds`,
view only), and pile readers.

**Timing gap (PLAN-spo-received-pin.md:27-30, :94): still OPEN.** No later commit closes it
(C section 2: nothing after #1388 on `spo_supply.py`, `supply_assignment.py`,
`stock_balance_ingest_service.py` addresses it; #1658 and #1850 are adjacent). It cannot be
measured from data: `stock_ledger` has no row referencing an SPO allocation (D task 4). Candidate
signal for a later lane: `inbound_shipments.warehouse_arrival_date` (container status import,
`container_status_import.py:74`) is set on 218 of 359 dev shipments while `actual_arrival_date`
is set on none. Trigger: measure both columns on a prod copy before using either.

**Call-site migration list, in order:**

1. Stock Debt `_holds` and `_follow_totals` (SDS:1614-2080) call the chain. Pure move.
2. Received semantics: `links_for_rows` received (PS:8254-8284), `_received_documents_for`
   (PS:3346, every caller listed in A-R3), `received_links_of` + `po_lines_with_open_chained_spo` (PS:13453-13503),
   `planning_change_service.py:1604`. Received = every hop received. Stock Debt picks up
   `received_direct` (Q4) and `dead`.
3. OI display: `_append_derived_spo_entries` (PS:8391) shows every SPO hop with its state;
   row label from the chain (Q1, Q2); Lines tab received pill parity
   (`orderInquiryHeaderLinesColumns.tsx:186-224`); worklist cards gain a received stage
   (WS:1179-1241, 3066-3175).
4. Popups and documents: PO popup SPO column with state (WS:2716); "Allocated to" on both popups
   via `placements_on` (WS:2893); SPO document so_covered (`procurement_service.py:3055`); SCM PO
   detail "Qty received" relabel + SPO column (`scm/purchase_order_service.py:145`,
   `PurchaseOrderDetail.tsx:592-642`).
5. Candidate walk netting `_linked_by_target` (PS:10000-10050) counts followed qty against the SPO.
6. Key only: own-arrival (PSS:3107, 3184, 3312), `_landed_holds` (SDS:2510), reserve (PS:13453),
   ingest hook (`ingest.py:735`), `_book_names_target_for_line` (PS:4014) use `po_spo_key_clauses()`.

Not migrated, each with its trigger: loading plan `_SPO_PLACED_ON_LINE_SQL` (owner ruled 18 Sep
that PO links are not supply there; revisit if the owner wants followed placements counted);
chatbot SO status (`chatbot/so_status.py`, no supply statement today: a new feature, built when
the owner asks for "where is my order" in chat); pile readers (correct as they are).

## 5. Behaviour card (filed with crew as `--ask`)

1. OI line once its SPO is received (L880): (a) PO + SPO both shown, SPO pill "Received 486 at
   BRW-BB" [recommended]; (b) SPO only; (c) as today (SPO "-").
2. "On PO/SPO": (a) keep the stored state, replace the label with the chain's where: "On PO",
   "In transit", "Received", or a split "In transit 300 / Received 186" [recommended: no migration,
   filters keep working]; (b) new stored states (migration, every filter and count moves).
3. When a PO placement counts as received (replan "used", CS reserve, planning change, reserve
   email): (a) when the goods land on the SPO it was transferred onto [recommended: matches Stock
   Debt and the owner's 24 Sep "PO received means converted to SPO"]; (b) on transfer (today).
4. PO line closed as transferred but no shipping order names it (8 placements / 221 units; stock
   sits at the PO's bin): (a) received at the PO's bin, Stock Debt pins it there like a landed
   SPO [recommended]; (b) "Transferred, no shipping order", holds nothing (today), purchasing chases.
5. Placement on a dead document (PO line cancelled, 20 / 2,565; SPO retired with 0 received,
   4 / 443): (a) stays placed, labelled "PO cancelled" / "SPO withdrawn" in red, with a worklist
   filter so purchasing re-places [recommended: no silent unlink]; (b) auto-release the link,
   row returns to Raised.

Screens that change visibly (each through a Lavish mock on a real case before build): OI Lines
tab (SPO column, label, pill), OI worklist (cards, pill meaning), PO and SPO popups (state,
Allocated to), SPO document detail (SO covered), SCM PO detail (Qty received label, SPO column),
Stock Debt (class d lines pin under Q4a), CS reserve email ("received" wording under Q3a).

## 6. Slicing (one lane per slice, in order)

| slice | content | size | visible |
|---|---|---|---|
| U1 | `goods_chain.py` + Stock Debt calls it (move, no behaviour change); chain tests per class a..z | M (about 400 lines, no UI) | no |
| U2 | received semantics (Q3, Q4, Q5 data side) across the OI received tests, reserve, planning change, Stock Debt | M | pill / email wording, Stock Debt class d |
| U3 | OI display: SPO column every hop, chain label (Q1, Q2), Lines tab pill parity, worklist received stage | M (mock) | yes |
| U4 | popups, SPO document, SCM PO detail via `placements_on` | M (mock) | yes |
| U5 | candidate walk netting + one key everywhere (step 5 and 6) | S | no (closes a double offer) |

U1 first, alone: every later slice reads its output. U2 needs Q3-Q5; U3/U4 need Q1-Q2 plus an
approved mock. No migration in any slice under the recommended answers.
