# PLAN: CONFIRM-DIALOG-SPEED

Status: PR 1 #2128 merged (81d653330b, 3 Nov). PR 2 in progress, lane CONFIRM-SPEED-PR2,
branch `crew/confirm-speed-pr2`. Track: standard (M: two owner-visible dialog rules; no migration,
no auth/RBAC change). UAC: `confirm-dialog-speed-3nov-acceptance-criteria.md`.

Owner report (3 Nov 13:15): Fulfilment Planning -> Confirm SO423361 sits on the Review split
skeleton for a very long time on prod. Prod request log (3 Nov 12:50-13:32 MYT): POST
`confirm-all` 36-46 s, GET `board` 6-8 s typical, 20 s worst. New since #2091
(CONFIRM-PREVIEW-STALE): openGuide re-read the whole board, then the Review split waited on the
confirm-all dry run as well, in series.

## PR 1: the dialog stops waiting, and the placement pass gets cheap

1. The Review split waits for the board re-read and the order's split read only, never for the
   email dry run. Next is usable while the dry run is out.
2. Every page's email dry run is planned as the guide opens, on the decisions the tab holds,
   beside the board re-read, and runs one at a time in page order (crew ruling S2). Paging never
   cancels a run. A page's run is replaced only when its key moves: its body, or a save made on
   that page (the body carries no split rows), or its Retry.
3. A page whose email words have not landed prints "Preparing email preview..." in its REMARK
   cells, editable and read-only rows alike (never the board's words as if they were the
   email's), and takes no line-remark typing yet; split-row remarks are the sheet's own.
   Confirm waits until every page's run has landed, under the same line. A failed run shows its
   own Retry and holds Confirm only; the sheet (and any unsaved edit) stays.
4. Opening Confirm joins a board read already in flight instead of cancelling and resending it.
5. Backend (crew profile hot spot 1): the placement pass reads each product's open PO lines and
   SPO allocations once per pass (`_document_rows_memo`, keyed by product and the session's
   company scope) instead of once per row walked.
   Skipping the pass in a dry run was considered and refused by crew ruling: keeping it keeps
   the dry run the press's own write by construction. (An "ORDER 25 vs ORDER 15" measurement
   offered as the reason was a test-session artifact, PREVIEW-EMAIL-PLANCHANGE #2135.)

Not done, on evidence: re-reading only the opened SO. The board is the selection itself and its
cells pile several orders together, so one order's read cannot be merged into it safely; PR 2
makes the read itself faster instead.

## PR 2: `_oi_placements`, one board assignment, the placement pass's row reads, two preview gaps

Measured on the prod clone `sorento_prod_1020` with crew's harness (real FastAPI app, one
connection, outer transaction always rolled back, outbound sockets refused), SO373923, Mac
under other lanes' load:

| Request | Before | Prototype (items 1 + 2) |
| --- | --- | --- |
| board GET | 11-20 s cold, 11.3 s warm | 5.0-8.5 s cold, 2.26 s warm |
| confirm-all dry run | 12-18 s | 5.6-7.0 s |

Outputs identical: the board JSON equal after sorting each `incoming` list (main itself orders
`incoming` differently run to run, so the harness compares that list as a set); the dry-run
response byte-equal.

### Architecture

Backend only for items 1-3, all inside existing services; no new table, column, index,
endpoint or setting. Items 4-5 are frontend only, inside the Confirm dialog.

1. **`ProjectSupplyService._oi_placements`** (`project_supply_service.py:3399`). Same rows, new
   statement shape: the SO lines are read first in a `MATERIALIZED` CTE (`source_ref` + product
   [+ company], joined to their project lines), then their live order-inquiry rows, their links,
   and the SPO rows by primary key with the same product/company pairing. Why: the one-join
   form had the planner drive from `spo_allocations` by product (estimated 11 rows a loop,
   actual 1,302; 1.45M loops). EXPLAIN ANALYZE on the clone: 2.4-5.4 s -> 15-400 ms, the same
   101 rows. **No index:** a `sales_order_lines.source_ref` index alone measured 2.2-2.9 s (it
   made the line lookup cheap; the planner kept the 1.45M-row loop). Trigger to add one later:
   `_oi_placements` above 0.5 s in prod logs with this shape.
2. **Board: one stock-debt assignment read per GET** (plan rule R21). Measured misses on main:
   the main walk (10 products), six single-product reads from covered rows' donor lookups
   (`project_fulfilment_board_service.py:3111-3118` -> `order_borrow_candidates_for`,
   `project_supply_service.py:4258`), one more from a fresh service per covered order
   (`_suggest_live_for_covered`, board `:3228`, 23 products). Fix: `_allocate` warms
   `planning_assignments` once with every plannable row's product before the main walk, and
   `_suggest_live_for_covered` reads all its orders' lines first, warms their products once,
   and hands the board service's `_assignment_cache` / `_assignment_index` to each per-order
   service. 8 reads -> 2. Safe in a GET: every input `assignments_for` reads is a
   request-invariant DB read (`incoming_by_location`, `po_by_location`, `lead_times`,
   `_fulfilment_settings`, `_decision_allocation_query(exclude_line_ids=None)`,
   site pools/reserves), none depends on the per-order `replacing` state `_facts_for` sets.
3. **Placement pass row identity reads** (`project_order_inquiry_service.py`). The dry run's
   largest remaining cost is the placement pass (5.0 s, 3,684 statements over 489 rows of 8
   products): `_resolve_product_id` x978 (`:14514`), `claim_identity` 3 x489 (`:14700`).
   Memoised for the pass beside PR 1's `_document_rows_memo` (same owner/nesting rule): a
   project line's `(product_id, core_sales_order_line_id)` by line id, an inquiry's SO number
   by inquiry id. Neither changes inside a pass. `_links_of` / `_suggested_of_row` are NOT
   memoised: the pass writes links.
4. **Gap A** (owner rule: email = preview = attachment). A page whose dry run answers
   `ok=false` shows the dry run's own error on that page, prints no words in its REMARK cells,
   and holds Confirm. Today `FulfilmentBoardPanel.tsx:2567-2570` settles it `ready` with no
   words and drops the error; `:2416` then falls back to the board's words.
5. **Gap B**: every email line appears on Review split. SO373923's dry run emails line 8
   (CKSW015, 8, "ORDER BACK MWH-BB"), which this press does not confirm, so `countsInPress`
   (`fulfilmentBoard.ts:917-923`) leaves it off the page (`:1136`).

Behaviour card answered by crew from the owner's rules (3 Nov): item 4 reuses the failed-run
pattern (`role=alert` line + Retry, `ConfirmGuideDialog.tsx:598-610`), REMARK cells empty;
Confirm NOT held (second ruling: today's press already posts only the ok orders and lands a
refused one on the result card with its reason table, pinned by 10 tests); no mock (existing row + alert pattern). Item 5: verified, line 8 belongs (a carried borrow
owing ORDER BACK under #1534's rule; this press raises it; policy kept as is). If it leaks from an earlier press, the EMAIL is the bug (purchasing must not
get a line this press did not confirm, or it is labelled as carried) and crew is told; if it
belongs, the page shows it as a read-only row in the same split sheet once the dry run lands,
remark = the email's words (an email line whose SO line is not on the board: item, qty, remark
from `email_lines`).

### Not done, on evidence

- **Confirm: one assignment read for the whole order / all orders up front.** Refused: it
  changes outputs. `_write_decision` supersedes the previous revision and flushes
  (`project_supply_service.py:7735-7739`) BEFORE its walk reads the order's remaining products
  (`:7746` `_proposals_for` -> `compose_lines` warm `:2004`), while `_check_line` reads its 5
  products before that write. One read up front moves those 18 products' read to before the
  supersede. Confirm keeps its reads; each is cheap after item 1 (6 reads 9.9 s -> 1.15 s).
- **Payload trim** (1.78 MB board JSON): 116 KB on the wire (`GZipMiddleware`,
  `app/main.py:150`); not worth a contract change.
- **Indexes for `_demand_pressure` / `_grouped_refusals` / `_lent_from`**: 1.0 / 0.9 / 0.2 s
  cold, 0.04 / 0.04 / 0.07 s warm on the clone; the cold cost is this Mac's disk under other
  lanes' load. Trigger: the board's prod log still above 3 s after this PR.

### Tests

- Equivalence (pytest, seeded chain, red before nothing; they guard): `_oi_placements` returns
  the same rows as the old statement (kept in the test as the oracle), with and without
  `company_id`, cancelled rows excluded, wrong-product/company SPO rows excluded;
  `assignments_for([P, Q])` equals `assignments_for([P])` + `assignments_for([Q])`.
- Red-first: a board GET with a covered order and a covered row's donor product calls
  `StockDebtService.assignments_for` at most twice (main: 3+); the placement pass reads a
  project line's identity once per line, not per call.
- Clone harness before/after, logged in the PR: board and dry-run timings, outputs identical.
