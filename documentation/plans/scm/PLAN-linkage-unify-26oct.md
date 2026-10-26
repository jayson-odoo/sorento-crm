# PLAN: one answer to "where are this SO line's goods now" (LINKAGE-UNIFY)

Status: U1-U3 owner hand-test PASS (26 Oct ~15:20, "ok to merge"), merging as PR #1870 (supersedes #1866 / #1868).
U4 #1874 and U5 #1873 open, retargeted to main after #1870 merges. Size L, lead pattern. UAC:
`linkage-unify-26oct-acceptance-criteria.md`. The fix is cut into the slices of section 6.
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
| `received` | SPO hop not incoming, `_landed_qty > 0`; bin(s) from the GR lines naming the SPO line (`picking_lines.spo_allocation_id`, 5a), else the SPO's bin (Q6) | `min(rest, landed)`, split per GR bin in GR date order |
| `received_direct` | PO line transferred, not cancelled, no SPO under the key (class d); bin(s) + qty from the GR lines naming the PO line (`picking_lines.po_line_id`, 5a), else the PO line's bin (Q4) | `min(rest, received on the PO)`, split per GR bin |
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
3. OI display: `_append_derived_spo_entries` (PS:8391) shows every SPO hop with its state and
   the pill "Received <qty> at <bin>" (Q1); dead hops show red "PO cancelled" / "SPO withdrawn"
   plus a worklist filter (Q5); the row label "On PO/SPO" is untouched (Q2); Lines tab pill
   parity with the worklist (`orderInquiryHeaderLinesColumns.tsx:186-224`); worklist stage cards
   stop counting landed qty as "On PO" (WS:1179-1241, 3066-3175) only if the owner approves that
   proposal in the mock.
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

**Owner rulings (26 Oct, ~09:20, relayed by crew):**

- Q1 (a): show PO + SPO, SPO pill "Received <qty> at <bin>".
- Q2 KEEP AS IS: "On PO/SPO" label unchanged; no chain-derived label, no split.
- Q3 (a): a PO placement is received when the goods land on the SPO it was transferred onto.
- Q4 (a): received at the PO's bin and Stock Debt pins it there, BUT owner: "I am pretty sure
  there is GR for this": first check whether the AutoCount Goods Received document is synced
  (table, sync code) and carries bin + qty; if it is, Q4 follows PO -> GR (bin and qty from the
  GR) instead of assuming the PO bin; if not, state it with evidence and propose the smallest
  read-only pull. Finding: section 5a.
- Q5 (a): stays placed, red "PO cancelled" / "SPO withdrawn", worklist filter.
- Mock v1 note: the PO chip never shows "received"; the received state is on the SPO chip only.
- Mock v2: "ok" (09:39). Q6 (a) (09:45): every received bin comes from the GR lines naming the
  document, falling back to the SPO / PO bin. Stage cards: NO new Received card; landed units
  stay in Purchased exactly as today (no card change).

The card as filed:

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

Screens that change visibly under the rulings (each through a Lavish mock on a real case before
build): OI Lines tab (SPO column, pills, dead-document pill), OI worklist (pill meaning, filter,
stage cards unchanged), PO and SPO popups (state, Allocated to), SPO document detail (SO covered), SCM PO
detail (Qty received label, SPO column), Stock Debt (class d lines pin under Q4), CS reserve
email ("received" wording under Q3). Mock v1 = OI Lines tab + worklist:
`documentation/mockups/LINKAGE-UNIFY/index.html`.

### 5a. Q4: is the AutoCount GR synced? YES (evidence `gr-E-autocount-gr-sync.md`, `sql/e-*.sql`)

- Code: ingest entity `goods_receive_notes` (`app/services/autocount_doc_ingest_service.py:82`,
  `_apply_grn` :1231, `_grn_links` :985, `_po_or_spo_line` :949; route `api/v1/external/ingest.py:1005`;
  on-request pull `app/services/autocount_pull_service.py:44-74`). Lands in `picking_headers`
  (`picking_type = 'goods_received'`, `doc_key` = AutoCount DocKey) and `picking_lines`
  (`location_code` = received bin, `qty`, `from_doc_no`, `po_line_id` OR `spo_allocation_id`).
  One AutoCount table serves PO and SPO, so a GR line links to either.
- Data: 470 of 1,359 GRs on dev are AutoCount-synced (2026-08-21 to 2026-10-15); the other 889
  are Excel/CRM GRs (`doc_key` NULL, `qty` NULL, `quantity_picked`, bin only in
  `source_warehouse_id`, no `po_line_id`). What Excel `source_warehouse_id` means is UNVERIFIED.
- Class d (8 non-cancel placements): every one is explained by GRs except PO 202104-S0087 (2
  placements, 3 units, older than the sync and the Excel imports). PO-2026/03-0024 WESERP10B:
  30,000 = 12,680 AutoCount GR + 17,320 Excel GR, received at BRW 6,680 / DC1 + DC1-HOLD 10,000 /
  WH3 10,320, so the PO line's own bin (BRW) is right for only 6,680. PO-2026/04-0018,
  PO-2026/05-0011, PO-2026/09-0023: GR bin = PO bin. PO-2025/12-0013 is the Cancel PO (dead).
- Q4 therefore follows PO -> GR: bin and qty from the GR lines that name the PO line, split in
  GR date order; the PO line's bin only when no GR exists (202104-S0087). Excel GRs carry no
  `po_line_id`: they reach a PO line only by header `spo_number` (which holds the PO number) +
  product, unambiguous only when the PO has one line of that product (WESERP10B's 17,320 needs
  it). No pull needed for the
  build; if the owner wants those 2 old lines exact, the existing on-request GRN pull with a 2021
  DocDate range covers it (read-only for AutoCount, no new code).
- Same truth for SPO receipts (`sql/v-gr-spo.sql`, `sql/v-gr-bin.sql`): L880's SPO line was
  received by GR-2026/10-0017 (5 Oct) 486 at BRW-BB, matching. But of 801 received SPO lines with
  placements and an AutoCount GR, 248 have a GR bin different from the SPO's warehouse (top
  pairs: SPO BRW -> GR MWH 345 lines, BRW-BB -> DC1-BB 287, BRW-BB -> MWH-BB 237). Today the
  pill would name the SPO bin and Stock Debt (SPO-RECEIVED-PIN) pins at the SPO bin, so those
  lines read on an empty or wrong bin. Design: a `received` hop takes its bin(s) and qty from the
  GR lines naming the document (PO line or SPO line), falling back to the document's own bin.
  Filed as Q6 to confirm.

## 6. Slicing (one lane per slice, in order)

| slice | content | size | visible |
|---|---|---|---|
| U1 | `goods_chain.py` + Stock Debt calls it (move, no behaviour change); chain tests per class a..z | M (about 400 lines, no UI) | no |
| U2 | received semantics (Q3, Q4, Q5 data side) across the OI received tests, reserve, planning change, Stock Debt | M | pill / email wording, Stock Debt class d |
| U3 | OI display: SPO column every hop with "Received <qty> at <bin>" (Q1), dead pills + filter (Q5), Lines tab pill parity; label unchanged (Q2); stage cards unchanged | M (mock) | yes |
| U4 | popups, SPO document, SCM PO detail via `placements_on` | M (mock) | yes |
| U5 | candidate walk netting + one key everywhere (step 5 and 6) | S | no (closes a double offer) |

U1 first, alone: every later slice reads its output. U2 is ruled (Q3, Q5; Q4 waits on 5a);
U3/U4 wait on an approved mock. No migration in any slice under the rulings, unless 5a needs a
GR pull (then that pull is its own slice, U0, ahead of U2's Q4 part). Per the lane contract each
slice runs tester (red tests from the UAC) -> coder -> reviewer, security-reviewer only if a GR
pull adds an ingest surface.

## 7. U1 contract (tester and coder both build to this; owner approved mock v2 09:39)

Track: L, slice U1 of 6. Branch `crew/linkage-unify`, PR U1. No migration, no UI, no RBAC.
Behaviour: Stock Debt reads exactly as today (AC-C8); the new module is the only addition.

Module `app/services/scm/goods_chain.py`:

- State constants: `ON_ORDER = "on_order"`, `IN_TRANSIT = "in_transit"`, `RECEIVED = "received"`
  (U1); `RECEIVED_DIRECT = "received_direct"`, `DEAD = "dead"` declared now, produced from U2.
- `@dataclass(frozen=True) class Hop`: `kind` (`"po"` | `"spo"`), `state`, `qty: Decimal`,
  `po_line_id`, `po_number`, `purchase_order_id`, `spo_allocation_id`, `spo_number`,
  `spo_line_number`, `warehouse_id`, `warehouse_code` (all `Optional`, ids as `str`),
  `reason: Optional[str] = None` (U2: `"po_cancelled"` | `"spo_withdrawn"`).
- `@dataclass(frozen=True) class LinkChain`: `link_id: str`, `row_id: str`, `placed_qty: Decimal`,
  `hops: Tuple[Hop, ...]`; property `unplaced_qty = placed_qty - sum(hop.qty)`.
- `chains_for_links(db, link_ids) -> Dict[str, LinkChain]` and
  `chains_for_rows(db, row_ids) -> Dict[str, List[LinkChain]]` (links of a row in `linked_at, id`
  order). A link on a cancelled OI row is absent from the result. A direct link on a retired SPO
  line with 0 received has a chain with no hops in U1 (U2 makes it a `dead` hop).
- Moved from `stock_debt_service.py` unchanged in logic, public names: `landed_qty(...)`
  (was `_landed_qty` :158), `follow_capacity(spo)` (was `_follow_capacity` :175),
  `transferred_allocations(db, po_lines)` (was `StockDebtService._transferred_allocations` :1957,
  same key, same order, same company predicate). Stock Debt imports them.

Rules (each already in `_holds` SDS:1614-1952; U1 lifts them, it does not invent):

- Live placement: `order_inquiry_links` row whose OI row is not cancelled, passing
  `spo_supply.visible_line_clauses()` on its SPO side (SDS:1797-1808). Placements on delivered or
  closed SO lines count too: the split is screen-independent. Measured on dev: closed-SO
  placements never change a split (`sql/v-split-scope.sql`, 0 PO lines); more generally the order
  only matters on a PO line whose live placements exceed what it can supply with more than one
  placement: 4 of 1,312 PO lines (`sql/v-split-contested.sql`). On those a FILTERED Stock Debt
  read (date, group, bins) can now differ from before, always towards the unfiltered answer
  (reviewer, PR #1866). Accepted: that is the point of one chain.
- PO placement: in `linked_at, id` order over ALL live placements on that PO line, take each
  transferred SPO (key and order of `transferred_allocations`) up to its remaining
  `follow_capacity`; still incoming -> `spo` hop `in_transit`; not incoming -> `spo` hop
  `received` for `min(take, landed)` at the SPO's warehouse (nothing if 0); then the PO's own
  `ordered - received` while `open_po_line_clauses()` passes -> `po` hop `on_order`.
- Direct SPO placement: incoming (`open_incoming_clauses()` and allocated > received) -> `spo`
  hop `in_transit` for the placement qty (not capped, as today; `assign()` caps); not incoming ->
  `received` for `min(qty, landed)` at the SPO's warehouse, nothing if 0.
- Stock Debt `_holds` maps hops to `Hold`s exactly as today: `in_transit` -> `spo:<id>` hold;
  `received` -> `on_hand:<bin>` hold unless `found_empty`; `on_order` -> `po:<line>` hold.
  `_follow_totals` keeps its signature and calls the moved helpers.

Tests (red first, tester): `tests/scm/test_goods_chain.py` (new) for AC-C1..C7; AC-C8 = the
existing `tests/scm/test_stock_debt_po_transferred.py`, `tests/scm/test_stock_debt_routes.py`,
`tests/scm/test_oi_po_lightbox_spo_numbers.py` pass unedited (baseline 78 passed on the lane
throwaway DB `sorento_lu_throwaway`, 26 Oct).

## 8. U2 contract (received semantics, GR bins, dead hops; rulings Q3, Q4, Q5, Q6)

Track: slice U2 of the L lane, own PR stacked on U1. No migration, no UI (the pills are U3).

goods_chain gains:

- `DEAD` hops, qty 0, `reason`: `po_cancelled` (PO line cancelled / closed with nothing
  transferred, or a Cancel PO line: `qty_cancelled >= qty_received > 0` and no SPO under the key),
  `spo_withdrawn` (direct link on an SPO line retired with 0 received, or closed with nothing
  landed; the U1 "no hops" case). The placement's `unplaced_qty` stays its full qty.
- `RECEIVED_DIRECT` `po` hops (class d): PO line transferred (`qty_received > qty_cancelled`), no
  SPO under the key, not dead. Qty `min(rest, qty_received - qty_cancelled)`.
- GR bins (Q4, Q6) for every `received` and `received_direct` hop: the GR lines naming the
  document, `picking_headers.picking_type = 'goods_received'`, counted with the same "this GR
  counts" filter the CRM receipt recompute uses (`procurement_service.get_received_quantities_by_product`
  :1094 / `_write_received` :4745; coder confirms the filter for AutoCount GRs, `doc_key` set).
  AutoCount GR lines link by `picking_lines.spo_allocation_id` / `po_line_id`, bin =
  `location_code` resolved to `warehouses.warehouse_code` in the company, qty = `qty`. Excel GR
  lines (`doc_key` NULL) link SPO lines by `spo_allocation_id`; a PO line only by header
  `spo_number` (holds the PO number) + product when that PO has exactly one line of the product;
  bin = `source_warehouse_id`, qty = `quantity_picked`. GR line capacity is handed to placements
  in the same `linked_at, id` order, GR lines in `picking_date, id` order; a hop splits into one
  hop per bin; landed qty no GR covers stays at the document's own bin. A `location_code` that
  names no warehouse falls back to the document's bin.
- Helpers `is_received(chain)` (every unit of the placement in `received` / `received_direct`
  hops, `unplaced_qty == 0`) and `received_qty(chain)`.

Call sites switched to the chain (each keeps its signature):

1. `links_for_rows` (PS:8254-8284): a link's `received` = `is_received`, `received_qty` =
   `received_qty` (the placement's share, not the PO transfer or the SPO total).
2. `_received_documents_for` (PS:3346): a link is in the result iff `is_received`; the date
   stays the SPO shipment's `actual_arrival_date` when the chain has one, else `None`. All its
   callers (A-R3: replan "used", split, settle, reallocate, `received_links_of`, import
   `_move_received_links`, `planning_change_service.py:1604`) follow without edits.
3. `received_links_of` / `po_lines_with_open_chained_spo` (PS:13453-13503) and the worklist
   `blocked` set (WS:1742): received comes from the chain; the chained-open-SPO block becomes
   redundant (a PO link with an open SPO is no longer received). Remove it only if nothing else
   reads it; otherwise route it through the chain key.
4. Stock Debt `_holds`: `received_direct` and GR-binned `received` hops -> `on_hand:<bin>` holds
   per bin (each subject to `found_empty` and `assign()`'s bin cap, as today); `dead` -> nothing.

Tests (red first): chain level AC-R3..R7 in `tests/scm/test_goods_chain.py` (new tests, the U1
ones untouched); Stock Debt cell AC-R3, R4, R6, R7; OI received AC-R1, R2, R6, R8 in the existing
#973 / #1708 suites' style. Real-case seeds: L880 (GR-2026/10-0017 486 at BRW-BB) and
OI-2609-0352 L1216 (GR-2026/08-0155 260 at MWH while the SPO says BRW-BB).

## 9. U3 contract (OI display: Lines tab + worklist, as approved mock v2)

Track: slice U3, own PR stacked on U2. No migration, no RBAC. UI: exactly mock v2
(`documentation/mockups/LINKAGE-UNIFY/index.html`, approved 09:39) minus the card proposal
(owner 09:45: stage cards unchanged).

Wire (`links_for_rows` entries, `_shared/types/orderInquiry.types.ts` ~196):

- Every entry (real link or derived SPO entry) gains `receipts: [{qty, bin}]`: the chain's
  `received` hops on that SPO (SPO entries) or `received_direct` hops on that PO line (PO
  entries), placement share, GR bin (Q1, Q4, Q6). Empty list when nothing landed.
- Every real link gains `dead_reason`: `"po_cancelled"` | `"spo_withdrawn"` | `null` (Q5). A
  direct link on a retired SPO line with nothing received is no longer dropped from the list
  (`visible_line_clauses` filter at PS ~8186 lifted for links; the dead hop says why).
- Derived SPO entries come from the chain's `spo` hops of the row's PO links, every state (not
  `derived_spo_open_clauses` any more): in transit as today (qty = open balance), received with
  `receipts`. Dead hops are not derived entries (they belong to the real link).
- `received` / `received_qty` keep U2 meaning; the worklist reserve chip reads them unchanged.

Worklist filter "Dead document" (Q5): query param `dead_document` = `po_cancelled` |
`spo_withdrawn`; rows with a live link whose chain is dead for that reason. Candidates narrowed
in SQL (PO line not open, SPO line not incoming), confirmed by the chain (one batched call),
then `OrderInquiryRow.id IN (...)`. Option counts as in the mock ("PO cancelled (20)") come
from the same read if the worklist already serves facet counts; otherwise plain options.

FE (`app/(protected)/project-sales/order-inquiries/`):

- One shared document-pill piece used by BOTH `components/orderInquiryWorklistColumns.tsx`
  (`DocumentsCell` ~358-470, `WorklistPill` ~74) and `[id]/components/orderInquiryHeaderLinesColumns.tsx`
  (`LineDocumentsCell` ~136-184, `DocumentCell` ~186-224): parity by construction.
- PO chip: no "received" pill (owner note on mock v1). Exception: `receipts` on a PO entry
  (class d, no SPO side) -> "Received <qty> at <bin>".
- SPO chip: one "Received <qty> at <bin>" pill per receipt (Badge secondary light, the
  existing pill style); several bins -> first pill + the existing "+N" pattern.
- Dead: red "PO cancelled" / "SPO withdrawn" (Badge destructive light) on the chip.
- "Dead document" select in the filters (`OrderInquiriesClient.tsx` ~1577), `SearchableSelect`,
  clearable, same pattern as State.
- State pill "On PO/SPO" untouched; stage cards untouched.

Tests (red first): backend wire (receipts, dead_reason, derived entries for received SPOs,
retired-0 link listed, `dead_document` filter) on the real cases L880 / L64 / L784 / OI-2609-0194
L16 shapes; vitest for the shared pill piece (PO no received pill, SPO receipt pill wording,
dead pills, class d PO receipt pill) and the filter select. Browser pass 1280 / 375 on the crew
test copy, then hand test.

## 10. U5 contract (one key everywhere + the candidate walk sees followed placements)

Track: slice U5, S, backend only, stacked on U3. No migration, no UI.

1. Candidate walk (Link dialog, cascade, `po_candidates_for_row`, `has_link_candidate`):
   `_linked_by_target` (PS ~10000-10050) nets an SPO allocation's remaining by the placements
   that FOLLOW onto it from their PO line (the chain's split: the same claims `_follow_totals`
   computes for Stock Debt), so 486 placed on PO 202607-S0100 leaves SPO-2026/09-0107 L9 with
   no free 486 for another row (A-R11 / D4). The followed split comes from `goods_chain`, never
   a second copy.
2. One PO -> SPO key: own-arrival readers (`_po_received_by_so_line_ref` PSS ~3107,
   `_po_received_by_product` ~3184, `_prefetch_own_arrival` ~3312, and `_landed_holds` through
   them), the ingest SPO hook (`_refs_from_written_spo_allocations`, `api/v1/external/ingest.py`
   ~735) and `_book_names_target_for_line` (PS ~4014) match SPO to PO line through
   `goods_chain`'s key (PO number + trimmed line ref + product + company, plus the FK route).
   Measured: the loose own-arrival key gives 0 cross-PO pairs on dev (`sql/v-key.sql`), so this
   is behaviour-neutral on today's data; it closes the collision risk on bare-ordinal refs.

Tests (red first): the candidate walk offers no free SPO quantity a followed placement already
holds; a space-padded `from_po_line_ref` is followed by the own-arrival readers; an SPO with the
same line ref under ANOTHER PO number is not; the ingest hook and `_book_names_target_for_line`
follow the same key (trim, product).

## 11. Owner rulings after the U3 hand test and the U4 mock (26 Oct, ~13:40-13:50)

- #1870 hand test: the document number (SPO and PO) never truncates at any column width; the
  "Received <qty> at <bin>" tag is a smaller, quieter pill (`text-2xs`, muted) that gives way
  first: it ellipsizes, then (cell under 220 px, Tailwind container query) collapses into a
  compact "Received" chip that opens the backing-documents dialog / Lines tab popover. Wording
  kept; a shorter form may be proposed in the next hand-test note (owner decides).
- U4 mock: (a) NO "In transit" tag in the popups; (c) "Qty received" / "Received" on both PO
  screens renamed "Transferred"; (b) "SPO withdrawn" explained on #1870 (`retired_at`, L784
  example); the red pill stays until the owner picks a name ("SPO line removed" /
  "Dropped from SPO" offered). Build U4 after the #1870 round-5 pill fix.

U5 notes (26 Oct): the one key drops SPO rows that name a PO line by `from_po_line_ref` without
`from_po_number`; 0 of 72,340 dev rows have that shape (`sql/v-key-nopo.sql`), so the Stock Debt
lendable seed was corrected to the real AutoCount shape. Follow-up, not built: the Link dialog's
PO-side remaining still subtracts every placement on the PO line, so a PARTLY transferred line
can be over-netted (0 partial transfers on dev; trigger: the first one).
