# data-D: linkage-unify data scout (read-only, dev copy sorento_cagent_stack)

Run via `run.sh` (psql, read-only, search_path projects,public). SQL files in same dir: d-01 (OI rows), d-02 (L880 chain), d-03 (class counts), d-03b (no open-SO filter), d-04 (class x PO receipt kind), d-05a/b (d variants), d-06 (the 9 d rows), d-07 (R3 landed/bin split), d-08..d-09/d-13 (samples), d-10/d-11 (timing gap), d-12 (row state per class), d-14 (overcommit), d-15 (partial test). d-base.sql is the shared CTE chain (pl -> po -> d -> dagg -> ds -> c).

## Definitions used (from code, read whole)
- R1 (OI Lines tab SPO column): real link entries (PO and direct SPO; links_for_rows hides only retired-and-never-received SPO via visible_line_clauses, direct SPO shown with a `received` flag) PLUS derived SPO entries only when `derived_spo_open_clauses()`: retired_at null AND allocated > coalesce(received,0) AND line_status open/null AND receipt_status not fully_received/received AND shipment.actual_arrival_date null.
- R2 (PO popup SPO column, `_spo_numbers_by_po_line`): every OI-SPO-EXACT match with `visible_line_clauses()` (retired_at null OR received>0). Arrived/closed SPOs shown. Only exists for PO lines (no direct-SPO equivalent).
- R3 (stock debt `_holds`): PO link: PO hold only for min(rest, qty_ordered - qty_received) when PO open (PO status in active/received/partial/closed, line open, ordered>received, not crm_spo); first follows to transferred SPOs (capacity = allocated if still incoming else landed). SPO incoming -> SPO hold; not incoming -> on-hand hold at SPO bin of min(qty, landed) where landed = received, else allocated if arrived/receipt_status received, else 0; hold dropped if the bin is in the read span and holds no on-hand event; retired-and-never-received SPO excluded by visible_line_clauses.
- R4 `_coverage_state`: linked qty (ALL links, any target, retired SPOs included, receipt ignored) vs row qty -> raised / partly_linked / placed.
- "Live placement": order_inquiry_links with reserve_request_row_id null (the table has no deleted flag; a link is dead only through its row), OI row state <> cancelled, on an open core SO line (public.sales_order_lines line_status='open', cancelled_at null, qty_ordered > qty_delivered). Cancelled-row and delivered filters changed class d by 0 (d-05a/b).

## Storage of OI code and "line 880"
- OI code = `projects.order_inquiries.inquiry_no` ('OI-2609-0128'). Row = `order_inquiry_rows` (so_line_id -> `projects.sales_order_lines`, whose `line_no` is 1..47 here, the OI-local line, and `core_sales_order_line_id` -> `public.sales_order_lines`).
- "Line 880" = `public.sales_order_lines.line_no = 880` (core AutoCount SO line) on SO364824; the OI row for it is psl line_no 22 (row id ffcde9a6). The same OI has a second SRTSS4210 row on core line 1040 (raised, unlinked).
- `public.sales_order_lines` has no OI link; the PO line has no line number column, its AutoCount line is the last segment of `source_ref` (`AED_SORENTO:<doc>:<line key>`).

## Task 1: OI-2609-0128 line 880 chain
| item | value |
|---|---|
| OI row | OI-2609-0128, OI line 22, SRTSS4210, qty 486, state placed |
| SO line | SO364824 core line 880, qty_ordered 486, qty_delivered 0, line_status open |
| link | one link, 486, to po_line (auto=true, document '202607-S0100'), no spo_allocation_id |
| PO line | 202607-S0100, source_ref ...:45383749:45521662, qty_ordered 486, qty_received 486, line_status closed, PO header status closed, expected 2026-09-01, bin BRW-BB |
| derived SPO (OI-SPO-EXACT) | exactly one: SPO-2026/09-0107 line 9, from_po_number 202607-S0100, from_po_line_ref same key, allocated 486, quantity_received 486, receipt_status fully_received, line_status closed, retired_at null, expected 2026-09-27, warehouse BRW-BB |
| shipment | PL-2609-060, shipment_status in_transit, estimated arrival 2026-09-27, actual_arrival_date NULL, warehouse_arrival_date 2026-09-28 |
| stock | public.stock for the product: BRW-BB 976 on hand (= 486 + 490, the sibling lines 9 and 10 of the same SPO, both fully received), BRW 32, CON 1 |

Readers for L880:
- R1: PO chip (marked received: qty_received >= qty_ordered), SPO column EMPTY (derived SPO fails line_status closed AND receipt fully_received; actual_arrival_date null does not even matter).
- R2: shows SPO-2026/09-0107 (retired_at null).
- R3: PO line not open (closed) so no PO hold; transferred SPO not incoming, landed = 486 (received) -> on-hand hold 486 at BRW-BB (bin has 976, so it survives). Net: the line is pinned to landed goods at BRW-BB.
- R4: placed (486 linked of 486), receipt not looked at.

## Task 2: population (live placements on open SO lines), d-03.sql
| class | meaning | placements | units | products | SO lines |
|---|---|---|---|---|---|
| a | PO line still on order, not transferred | 728 | 64391 | 182 | 694 |
| b | PO transferred, all derived SPOs still incoming | 114 | 9776 | 44 | 110 |
| c | PO transferred, derived SPOs received/landed/closed | 191 | 16806 | 53 | 181 |
| d | PO line reads transferred (qty_received = qty_ordered, line closed) but NO visible spo_allocations match | 9 | 232 | 7 | 9 |
| e | direct on SPO line still incoming | 34 | 1010 | 19 | 33 |
| f | direct on SPO line received/landed/closed | 1048 | 112198 | 261 | 1016 |
| x | direct on SPO line retired with received 0 (hidden) | 4 | 443 | 4 | 4 |
| z | PO line not open and not transferred (cancelled, received 0) | 20 | 2565 | 15 | 20 |
| g | partial transfer | 0 | 0 | | |

Notes:
- d re-measured: 9 placements / 7 products / 232 units (crew said 11 / 9 / 247). Dropping every SO-line filter gives 12 / 10 / 249 (d-03b), so crew's figure sits between; likely a different filter or an older data state. UNVERIFIED which. All 9 d rows: PO line closed or cancelled, qty_received = ordered, zero spo_allocations with the same from_po_number even ignoring ref/product (d-06: n_spo_same_po_prod = 0 for all 9). So the match failure is not a key-format problem, the SPO rows are simply absent (older POs 202104-S0087, PO-2025/12-0013, PO-2026/03-0024 (WESERP10B, 30000 ordered, 3 placements 6+182+5), PO-2026/04-0018, PO-2026/05-0011, PO-2026/09-0023). Several look like consumables/stock POs whose received qty was a plain receipt, not an SPO transfer, so "qty_received = transferred" does not hold for them: UNVERIFIED inference.
- g: zero partial transfers. All 297 transferred PO placements have qty_received = qty_ordered (d-04); in b/c the sum of visible SPO allocations equals po_received in 303 of 305 (the other 2 are c with SPO total larger, 4 units) (d-15). The partial branch of R3 (`po_left` > 0 with `_transferred_allocations` non-empty) has no live data on this DB. UNVERIFIED on prod.
- Row state (R4) per class (d-12): every class is almost entirely `placed` (a 684/728, b 112/114, c 188/191, d 9/9, e 31/34, f 935/1048, x 4/4, z 19/20); the rest `partly_linked`. R4 never differs by class.
- Overcommit (d-14): 24 SPO allocations carry more placed qty (direct + derived, live) than allocated, 923 excess units. Pool-sharing in R3 therefore clips some placements; I did not replay the sharing order, so the per-class R3 outcomes below are before pool clipping. UNVERIFIED how many are clipped.

### R3 split inside c and f (d-07): landed vs placement, bin state
| class | landed vs placement | bin | placements | units |
|---|---|---|---|---|
| c | landed < placement (R3 holds less) | has on-hand | 1 | 14 |
| c | landed >= placement | bin EMPTY for the product | 15 | 539 |
| c | landed >= placement | has on-hand | 175 | 16253 |
| f | landed >= placement | bin EMPTY | 139 | 11397 |
| f | landed >= placement | has on-hand | 909 | 100801 |
Every c/f SPO has received > 0 (no row relies on arrival-only evidence). "Bin EMPTY" means product on-hand across `public.stock` at the SPO warehouse is 0; whether R3 drops the hold depends on whether that bin is in the read span: UNVERIFIED (not run through the service).

### Readers by class
| class | R1 OI Lines SPO column | R2 PO popup SPO column | R3 stock debt | R4 coverage |
|---|---|---|---|---|
| a | PO only | none | PO hold | On PO/SPO |
| b | PO (shown received) + derived SPO | SPO | SPO hold (PO hold 0 since line closed) | On PO/SPO |
| c | PO only, SPO hidden | SPO shown | on-hand hold at SPO bin min(qty, landed); dropped if bin empty and in span | On PO/SPO |
| d | PO only | none | NOTHING (PO not open, no SPO to follow) | On PO/SPO |
| e | SPO | n/a | SPO hold | On PO/SPO |
| f | SPO (with received mark) | n/a | on-hand hold at SPO bin; dropped if bin empty and in span | On PO/SPO |
| x | nothing (retired, 0 received, link hidden) | n/a | nothing | On PO/SPO (link still counted) |
| z | PO only (cancelled line) | none | nothing | On PO/SPO |

Divergences: c (R1 vs R2 vs R3), d (R3/R1/R2 say nothing or PO only, R4 says covered), x (R1/R3 nothing, R4 covered), z (same shape as d), f when bin empty (R3 nothing, R1 and R4 covered). Classes a, b, e agree on "incoming supply".

## Task 3: sampled SO lines (all codes; no names, no customers)
| # | OI / line | SO / line | product | qty | PO / ref tail | SPO / line | SPO state | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (c) | OI-2609-0128 L22 | SO364824 L880 | SRTSS4210 | 486 | 202607-S0100 / :45521662 | SPO-2026/09-0107 L9 | 486/486 fully_received, line closed, shipment in_transit, wh arrival 2026-09-28, BRW-BB | PO only | SPO-2026/09-0107 | on-hand hold 486 at BRW-BB (976 there) | placed |
| 2 (c, landed<qty) | OI-2609-0053 L38 | SO403889 L816 | SRTUB206 | 14 | 202608-S0049 / :45568285 | SPO-2026/10-0032 L6 | 10/10 fully_received, closed, BRW | PO only | SPO shown | on-hand hold 10 at BRW (4 on hand), 4 of 14 uncovered | placed |
| 3 (c, bin empty) | OI-2609-0549 L62 | SO398090 L1408 | CGB762 | 303 | 202606-S0019 / :45073889 | SPO-2026/10-0015 L19 | 395/395 fully_received, closed, wh arrival 2026-10-07, BRW-BB on hand 0 | PO only | SPO shown | hold on an empty bin (dropped if in span) | placed |
| 4 (d) | OI-2609-0013 L14 | SO314592 L80 | WESERP10B | 182 | PO-2026/03-0024 / :44243732 | none exists | PO line 30000/30000 closed, header closed | PO only (received) | none | nothing | placed |
| 5 (b + e on one SPO line, control) | OI-2609-0194 L2 | SO396348 L64 | SRTA8046 | 701 (PO link) + 3 (PO link) + 194 (direct SPO link) | 202607-S0105 / :45565659 | SPO-2026/10-0008 L76 | 1092/0 pending, open, shipment in_transit, BRW-BB | derived SPO + the real SPO entry for the 194 | SPO | SPO holds, PO hold 0 | placed |
| 6 (c + f + x on one SO line) | OI-2609-0252 L36 | SO396349 L784 | SRTSS3170 | 294 (PO link) + 60 (direct, SPO L12) + 294 (direct, SPO L7 retired) | 202607-S0100 / :45717392 | SPO-2026/09-0107 L12 (354/354 received) and L7 (294/0, retired) | L12 fully_received closed; L7 retired, 0 received | PO, real SPO L12 entry; L7 hidden | SPO L12 | on-hand hold at BRW-BB for the L12 placements; L7 placement nothing | placed (354 + 294 vs 294 needed counts the retired link) |
| 7 (e) | OI-2610-0034 L8 | SO424924 L8 | SRTWT07SP | 34 | none | SPO-2026/10-0012 L11 | 34/0 pending open, in_transit, BRW-BB (product on hand 0) | SPO | n/a | SPO hold | placed |
| 8 (f, bin empty) | OI-2609-0289 L19 | SO313699 L464 | SRT6638 | 1260 | none | SPO-2026/01-0005 L328 | 1260/1260 fully_received closed, BRW-IR, product on hand 0 | SPO with received mark | n/a | on-hand hold at BRW-IR dropped if bin in span (bin empty) | placed |
Note on #5: the three placements share the SPO line (alloc 1092, 0 received) so no disagreement among the readers on state, but R1 prints the same SPO twice (derived entry from the PO links plus the real direct link) and shares one 1092 pool; included as the "agree" control and to show the duplicate entry risk (UNVERIFIED how R1 renders duplicates).
Note on #1..#4, #6, #8: these are the disagreement lines.

## Task 4: timing gap check (d-10, d-11)
- Surprise: `inbound_shipments.actual_arrival_date` is NULL on ALL 359 shipments on this DB (218 have `warehouse_arrival_date`). So the "landed" clause in `open_incoming_clauses()` (`actual_arrival_date IS NULL`) is always true here; landing is effectively decided by `quantity_received` / `receipt_status` / `line_status`, never by the shipment. Whether prod has actual_arrival_date populated: UNVERIFIED.
- Shipment status and receipt disagree both ways, on non-retired allocations:
  - received but shipment not landed: in_transit shipment with rcv full: 2668 allocations (wh_arr set) + 56 (no wh_arr), 685,519 units; partially_received shipments with rcv full: 89.
  - shipment says landed (wh_arr set or status fully_received) but allocation received = 0: 17 allocations: 16 have line_status closed (zero effect on any reader, none has a placement), 1 is open: SPO-2026/09-0023 L1 qty 199, shipment PL-2608-001 fully_received, MOCHA-WH, receipt pending. R1/R3 treat it as incoming; no placements reference it (direct_links 0, transfer links 0).
  - shipment in_transit with wh_arr set and rcv 0: 14 allocations, 6442 units, all line_status closed.
- Cannot tell: stock balance vs shipment landing per allocation. `public.stock` is a per-product/bin balance, `stock_ledger` carries only bulk_import / autocount_push / stock_snapshot_import references, none of which point at an `spo_allocations.id` (0 rows join), and there is no per-allocation receipt posting date. Missing: a per-allocation receipt event or date to compare against the book's quantity_received.
