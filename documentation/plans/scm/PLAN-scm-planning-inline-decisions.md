# PLAN - Fulfilment planning: decide in the row, one Confirm, transfers on the page; sales orders list tidy-up

Status: **PHASE 1 DONE** 2026-08-27 (worktree commit, browser-checked on :3010; Phase 2 next). GO given 2026-08-27 (captain: "okay can start", after the lavish pass, R15). Building on branch `feat/scm-planning-inline-decisions` off `main` `3a5e42970` (#347). UAC: `scm-planning-inline-decisions-acceptance-criteria.md`. Review artifact: `documentation/plans/scm/mockups/planning-inline-decisions-plan.html` (lavish).

## 0. What the captain asked (27 Aug, after walking SO404352 on `/project-sales/fulfilment-planning`)

Two pages.

`/scm/sales-orders`: Add sales order goes under Actions; a new **Start** button carries Upload sales orders and Plan selected; the Source value reads Upload; the Customer cell loses its Retail sub-line; the document date leaves the SO number cell and becomes its own column.

`/project-sales/fulfilment-planning`: the product drawer said "Use own location, 9 from BRW-AM" while the AM group row said Available -15. The captain's rule: **when the group's available quantity is negative, own location must not be suggested.** The contributing-lines grid scrolls sideways; Rank goes. Decisions are made in the row itself (expand, like reorder planning's location panel), not in an Amend modal; the "24 outstanding = 0 incoming + ..." line goes; the reason box gets a flag for "this might be a system problem". One **Confirm** button, no Approve all, Undo all under a gear. The Commit section goes; the stock transfers a confirm creates appear on the same page, above the product matrix, where they can be approved. Emphasis: UI/UX and the correctness of the numbers.

## 1. Rulings (captain, 27 Aug)

| # | Question | Ruling |
| --- | --- | --- |
| R1 | Own location vs a negative group | Available is **on hand - other open SO lines at that location + SPO qty**, the asking line excluded, no date ordering, no rank. Negative means no own-location offer. This is already what the engine computes (`_group_offer` = `max(group_net + own qty, 0)`); the drawer printed the other definition. The drawer changes, the engine does not |
| R2 | Customer sub-line (market segment) | dropped entirely; the Type column already carries the demand class |
| R3 | Sales orders toolbar | primary = **Start** dropdown (Upload sales orders, Plan selected (N), disabled at 0; no header row inside the menu); **Actions** = Add sales order, Reset planning (N), Refresh |
| R4 | SPO qty in Available | kept (`+ spo_qty`), the column sits beside it |
| R5 | Expanded location documents | no `#` rank, no queue state; sorted by delivery date; the asking line stays in the list marked "this line"; Total kept |
| R6 | Decision pill | status only: Suggested / Approved / Amended / Confirmed / Rejected. **No "rev N"** |
| R7 | Where a decision is edited | the expanded row, one window for everything; `BoardAmendDialog` deleted |
| R8 | Contributing-lines columns | Sales order, Customer, Agent, Project, Outstanding, Delivery date, Location, Sourced from, Order inquiry, Decision. **Rank, Ordered, Delivered dropped** (Ordered / Delivered shown inside the expanded row) |
| R9 | Balance line | the equation goes; a small "N short" / "N over" hint only while the amendment does not add up; save disabled until it does |
| R10 | System-problem flag | checkbox beside the reason, stored on the decision line (`suspected_system_issue`), warning badge on the pill, counted in the confirm result. No investigation listing this round |
| R11 | Confirm semantics | **one button, Confirm (N)**: every plannable, non-rejected line on the board is confirmed with its amended composition if amended, otherwise the suggestion. Approve all and per-order Confirm cards go. Counter reads "N to confirm · M rejected" |
| R12 | Gear | Undo all, Back to sales orders |
| R13 | Commit section | removed. A **Stock transfers** panel sits above the product matrix listing every open (`proposed`) transfer for the orders on the board, Approve per row and Approve all, using the existing stock-transfer endpoints. Survives reload (it lists, it does not remember the click). Buy rows: a count linking to Order Inquiries |
| R14 | Confirm-time guard | the server refuses a reserve that exceeds on hand minus what other lines have already confirmed at that location; the message names the location and the earlier order |
| R15 | Drawer copy | no tooltips or explanatory icons on the numbers; SO qty is the other lines, full stop. Dropdown menus carry no header row (no "Start" inside the Start menu). Header bar order: gear, then the Confirm CTA on the far right |

## 2. Facts found while mapping (verified 27 Aug, not to rediscover)

- Sales orders list: hand-rolled route `GET /api/v1/scm/sales-orders` (`app/api/v1/scm/sales_orders.py:74`), serializer `sales_order_service.py:446`, `order_date` already in the payload (`:457`) and sortable (`:970-994`). Source labels are FE-only: `SalesOrdersGrid.tsx:113-124` (`upload: 'Sales order upload'`), filter twin `:86-92`, detail copy `SalesOrderDetail.tsx:144`. Customer sub-line = `market_segment` at `SalesOrdersGrid.tsx:405-414`. Document date is the second line of the `so_number` cell (`:381`). Columns array `:358-687`. Column preferences merge new columns next to their definition-order neighbour (`mergeColumnOrder.ts:7-27`), so a new column after `so_number` lands there for users with a saved layout. Toolbar: `DataGridListToolbar` renders "Actions" when `secondaryActions.length >= 2` (`data-grid-list-toolbar.tsx:479-529`); Plan selected built by `lib/planActions.ts:41-65`, wired `SalesOrdersGrid.tsx:713-723`.
- Engine offer: `project_supply_service.py:1853-1879` `_group_offer` = `max(group.net + open_qty, 0)`, `group.net` = sum over the group of `on_hand - so_qty + spo_qty` (`scm/group_netting.py:88-90`), floored per location by `_free_at` (`:4522-4552`, on hand minus reserved minus confirmed holds). Pinned by `tests/scm/test_ladder_v4_group_netting.py:441`. Pool rung = residual (`front_planning_engine.py:549-572`): 24 - 9 = 15 of the 16 BRW holds.
- Drawer rows: `project_fulfilment_board_service.py:3504-3648` `_location()`; `so_qty` = `_demand_pressure` (`:1461-1522`), every open line at (product, warehouse) **including the asking line**; `available_qty = on_hand - so_qty + spo_qty` (`:3563-3567`). No test pins the drawer number to the engine offer.
- SO404352 line 22 / SRTWB7518: BRW-AM on hand 10, open demand there = SO383850 (1) + this line (24). Engine 10 - 1 = 9, drawer 10 - 25 = -15. Same data, two definitions.
- Board page: Approve all / Undo all are client-draft only (`FulfilmentBoardPanel.tsx:579-590`, `:1046-1055`), no API. Confirm all → adopt → `POST .../fulfilment-planning/confirm-all` (`:666-742`). Amend modal `BoardAmendDialog.tsx` produces a `BoardDecision` via `decisionFromAmendDraft` (`_shared/lib/boardAmend.ts:277-321`) held in the draft; it reaches the server only inside `confirmLinesFor` (`_shared/lib/fulfilmentBoard.ts:250`). The "why" field is `ConfirmLine.amend_reason` (`schemas/project_supply.py:303`).
- A confirm writes `SOSupplyDecision` + `SOLineAllocation` rows, then `stock_transfer_service.write_for_decision` (`:252`): one `proposed` row per reserve / borrow component whose source ≠ the line's location; never for own location or Buy. Result carries `transfers_written` / `transfers_failed`. Transfers: `projects.stock_transfers`, states `proposed → approved → moved | cancelled`, kinds `own_group / pool / borrow`. Endpoints exist: `GET /inventory/stock-transfers`, `POST /{id}/approve`, `POST /bulk-approve`, `/mark-moved`, `/cancel` (`app/api/v1/inventory/stock_transfers.py`), perms `inventory.stock_transfers.view / .edit`. FE service `services/stockTransferService.ts:72,109`.
- Contributing lines = `PanelDataGrid` (fixed layout, resizable), `listingKey projects.projects.view::project-board-cell-breakdown`, columns at `BoardCellBreakdownDialog.tsx:202-550`.
- Expand pattern to reuse: TanStack `getExpandedRowModel` + `columnDef.meta.expandedContent` on the shared `DataGrid` (`data-grid-table.tsx:409-421`); reorder's `PlanLinesGrid.tsx:608, 889-897, 1574-1586, 1732-1743`. Whole row toggles; chevron is an indicator.
- Alembic on `main` has **two heads**: `430_plan_row_price_supplier` and `437_merge_uat_main_and_sets`. This lane's first migration is the merge. Dev DB `alembic_version` = `a67d68a2ed9a` (price-tag lane): apply DDL via `Operations.context`, never stamp.

## 3. Scope

### A. Sales orders list (FE only)

| Item | Change |
| --- | --- |
| A1 Toolbar | `primaryAction` = `Start` dropdown button (`DropdownMenu`, same Button styling): **Upload sales orders**, **Plan selected (N)** (disabled at 0, tooltip carries the max-50 rule). `secondaryActions` (the Actions dropdown) = **Add sales order**, **Reset planning (N)**, **Refresh**. `pinnedToAgent` keeps hiding Add / Upload as today |
| A2 Source | `'Sales order upload'` → `'Upload'` in `SOURCE_LABELS`, `SOURCE_FILTER_OPTIONS`, `SalesOrderDetail.tsx` |
| A3 Customer | delete the `market_segment` sub-line; cell = name only, `truncate` + `title` |
| A4 Document date | new column `order_date`, header **Document date**, size 130, sortable (server key `order_date`), placed right after `so_number`; the SO number cell keeps only the number (+ the Changed badge) |

### B. Drawer numbers (BE + FE)

| Item | Change |
| --- | --- |
| B1 `so_qty` per location excludes the asking line | `_location()` takes the asking contribution's `(warehouse_id, open_qty)`; `so_qty = pressure - own_qty_at_that_warehouse` (never below 0), `available_qty = on_hand - so_qty + spo_qty`. Group subtotal `net` recomputed from the rows so **subtotal Available == `group_offer`** (9 here). No tooltip, no extra field: SO qty is plainly the other open lines at that location (R15) |
| B2 The pinning test | `tests/test_fulfilment_board.py`: for a cell, own-row subtotal `available_qty` equals the engine's `group_offer` for the line; negative subtotal ⇒ no `group_take` component. Two cases: SO404352-shaped (10 / 1 other / 24 own → 9) and a short group (10 / 12 other → -2, offer 0) |
| B3 Expanded documents panel | `StockDocumentsPanel`: columns Doc / Number / Customer / Agent / Doc date / Delivery date / Qty; **no rank, no state**; server sorts by delivery date asc; the asking line's row carries a "this line" tag; Total kept |

### C. Contributing lines: decide in the row (FE, reuses existing draft + payload)

| Item | Change |
| --- | --- |
| C1 Columns | per R8. Rank, Ordered, Delivered removed from the definition (the saved `listingKey` layout drops unknown keys on merge). Decision column `size 160`, pill only |
| C2 Pill | Suggested (grey) · Approved (green) · Amended (blue) · Confirmed (green outline, no rev) · Rejected (red) · covered / unplannable as today. Warning triangle when `suspected_system_issue`. Buttons leave the cell |
| C3 Expand | `getExpandedRowModel` + `meta.expandedContent` on the `so_number` column, whole row toggles, one row open at a time (opening another closes the first; an unsaved edit prompts). Expanded panel = `BoardLineDecisionPanel` (new), bg-muted like reorder's `GroupMembersPanel` |
| C4 Panel layout | left: Ordered / Delivered / Outstanding / Incoming by the delivery date (read-only strip). Middle: Reserve (per location qty inputs, own + group + pools, with each location's Available beside the input), Borrow (existing rows + Add a borrow), Buy (switch + reason, as today). Right: Decision summary (composition that will be confirmed), the "N short / N over" hint (R9), **Why this differs** textarea (required when `amendNeedsReason`), **checkbox "This might be a system problem, flag it for investigation"**, buttons **Approve suggestion** (resets to the suggestion, verdict approved), **Save amendment** (verdict amended), **Reject** (verdict rejected, reason required). Confirmed rows open read-only with an **Amend** button that unlocks the same panel (a re-confirm is a new revision, the pill still says Confirmed) |
| C5 State | reuse `DraftLine` / `amendDraftFrom` / `decisionFromAmendDraft` / `lineBalance` / `lineBlockers` unchanged; `BoardDecision` gains `suspected_system_issue?: boolean`; `BoardAmendDialog.tsx` and its test deleted; bulk toolbar keeps Approve selected / Reject selected / Clear |
| C6 Width | with Rank / Ordered / Delivered gone and the Decision column narrowed the grid fits 1280 without horizontal scroll at default sizes; 375 scrolls inside the grid container as today |

### D. Header, confirm, transfers (FE + BE)

| Item | Change |
| --- | --- |
| D1 Header bar | left: "N to confirm · M rejected". Right: gear (`Settings2`) dropdown: Undo all (disabled when the draft is empty), Back to sales orders; then **Confirm (N)** primary as the last element on the right. Approve all and Confirm all approved removed |
| D2 Confirm semantics | `confirmLinesFor` builds a line for every plannable, non-covered contribution: rejected → skipped; amended → the amendment; approved or **untouched → the suggestion**. Same `POST .../confirm-all` after adopt, same AlertDialog ("Confirm N lines across M orders?"). N = plannable minus rejected minus already-confirmed-and-untouched |
| D3 Commit section | `OrderCommitRow`, `standings` UI and the copy block removed. Confirm result toast: "N lines confirmed · T transfers proposed · I inquiry rows"; failing lines still pinned per row as today |
| D4 Stock transfers panel | new `BoardTransfersPanel` **above the matrix**, below the composition cards. Data: `GET /api/v1/inventory/stock-transfers?so_numbers=SO404352,...&state=proposed,approved` (new `so_numbers` filter on the list route, joins `so_line_id → sales_order_lines → sales_orders.so_number`). Columns: Transfer no, Product, From → To, Qty, Kind, For (SO · line), State, Proposed at, action. **Approve** per row (state `proposed`) and **Approve all proposed**, via `approveStockTransfer` / `bulkApproveStockTransfers`; invalidate + toast. Hidden when the list is empty and nothing was just confirmed; users without `inventory.stock_transfers.edit` see the list without buttons. Buy summary line: "I order inquiry rows raised" linking to `/project-sales/order-inquiries` |
| D5 Flag on the wire | `ConfirmLine.suspected_system_issue: bool = False` → stored on the decision line beside `amend_reason` (`so_line_allocations` / decision-line table, one migration), echoed on the board contribution's `decision` so the pill shows it after reload, and counted as `suspected_issues` in `ConfirmResult` |
| D6 Guard (R14) | in `ProjectSupplyService.confirm`, per reserve component: `qty <= on_hand(warehouse) - confirmed_holds_by_other_lines(product, warehouse)`; otherwise `AppException 409` with `{line, warehouse_code, on_hand, held_by: [{so_number, line_no, qty}], asked}` and the message "BRW-AM: 10 on hand, 1 already reserved by SO383850, you asked 15". The FE pins it on the row like other `ConfirmSupplyError`s |

### E. Migrations (this lane's first commit)

1. `438_merge_430_437` : merge of `430_plan_row_price_supplier` + `437_merge_uat_main_and_sets` (no DDL).
2. `439_decision_suspected_issue` : `suspected_system_issue BOOLEAN NOT NULL DEFAULT false` on the decision-line table. `down_revision = "438_merge_430_437"`. Ids ≤ 32 chars. Applied to the dev DB via `Operations.context`, never stamped.

## 3b. Phase 3 fix round (28 Aug, review findings + rulings R16-R17)

| # | Change |
| --- | --- |
| F1 | **The location table is per CONTRIBUTION, not per cell** (B1 as written, which the first cut netted per cell). `_own_demand` is the asking line's own `(product, warehouse)` quantity, so `so_qty` = pressure less that one line's open qty and the group subtotal = `group net + that line's qty` = `group_offer` for every contribution (UAC B4). The payload carries `BoardContribution.locations`; `BoardCell.locations` is the first contribution's block, the drawer's table follows the expanded row and names the line when the cell holds more than one, and the decision panel's "N available" is that line's figure - in the List view too (C4) |
| F2 | `_own_demand` is keyed by `(product_id, warehouse_id)`, looked up with the ROW's own product: two products share `B2155-NL-BLUE` and land in one cell, and their demand is not each other's |
| F3 | Confirm invalidates `BOARD_TRANSFERS_KEY` (and `PLANNING_CHANGE_BATCH_KEY`), so the transfers panel fills on the press (D6). The generic "Confirmed N order(s)." toast is dropped: only the panel's three-number sentence fires, plus the partial-refusal warning |
| F4 | `BoardTransfersPanel` is gated on `inventory.stock_transfers.view` (query off + nothing rendered) as well as `.edit` for the buttons (D9); Approve and Approve all confirm first with the transfers page's own `AlertDialog` copy |
| F5 | The List view carries the unsaved-edit prompt and one-open-row rule the dialog has (C5); both use the shared `useDecisionRowExpansion` / `UnsavedDecisionPrompt` |
| F6 | The Buy switch restores the composition it zeroed when switched back off; `suspected_system_issue` is emitted as a real boolean and the DRAFT's `false` beats a frozen `true` on the pill and in the panel |
| F7 | An **unplannable** line opens read-only with its reason and no verbs: `lineFor` posts nothing for it, so an editable panel was a decision the press would silently drop |
| F8 | The unpostable notice names TOUCHED lines (capped at 5, then "and N more") and COUNTS untouched ones per reason ("12 untouched lines buy a discontinued product with no reason given; open them to decide"), because R11 made every plannable line part of that population |
| F9 | Undo all confirms first ("Discard N draft decisions?"); an order whose planning-change rows all read applied is left out of the confirm body and reported per order |
| F10 | `line_ids` on `stock-detail` goes through the shared `parse_uuid_list` (400 `INVALID_UUID` naming the parameter) |
| F11 | **R16, transfers are RECONCILED, not swept.** A confirm no longer cancels every open transfer of the order. Each open row is matched on `(so_line_id, product_id, from_warehouse_id, to_warehouse_id, kind)`: same qty = KEPT with its state, number and approval, re-pointed at the new revision; grown = kept plus a new row for the difference; shrunk = cancelled and re-proposed; vanished = cancelled. `transfers_written` counts only rows created, `transfers_kept` is new on `ConfirmResult` / `ConfirmManyOrderResult`, and the board's toast reads "N lines confirmed · T transfers proposed · K kept · I inquiry rows" (the kept part only when non-zero) |
| F12 | The R14 refusal names a competing line of the SAME order as "line N of this order" rather than repeating the planner's own SO number |

## 4. Out of scope

Engine formula (unchanged, per R1). Investigation listing for flagged decisions (R10). Mark-moved / cancel on the board panel (link to `/inventory-management/stock-transfers` for those). Order Inquiries changes. Reorder planning page.

Phase 1 deviations (27 Aug, accepted): the board `List` view was converted to the same pill + expanded panel, because it was the only other importer of the deleted Amend modal and C6 says no Amend button anywhere; the breakdown dialog widened to `sm:max-w-[95vw]` with the header capped at `max-h-[45vh]` so the editor is reachable at 900px tall; the ranking sentence under the drawer header went with the Rank column.

## 5. Build order (PRINCIPLES.md steps)

- **Phase 1, FE on mocks**: A1-A4; C1-C6 with `BoardLineDecisionPanel` against the existing board fixture; D1-D4 with a mocked transfers list. Browser check on `npm run dev` :3000 via sidebar (Project Sales → Fulfilment Planning; SCM → Sales Orders), 1280 and 375.
- **Phase 2, BE test-first**: B1-B3, D5, D6, E, the `so_numbers` filter. pytest: `test_fulfilment_board.py` (B2 pin + `so_qty_this_line`), `tests/test_stock_transfer_list_filter.py`, `tests/test_confirm_reserve_guard.py`, `tests/test_confirm_suspected_issue.py`. vitest: `SalesOrdersGrid.test.tsx` (columns, labels, Start / Actions), `BoardCellBreakdownDialog.test.tsx` (columns, expand, pill), `BoardLineDecisionPanel.test.tsx`, `FulfilmentBoardPanel.test.tsx` (confirm semantics, gear, no commit section), `BoardTransfersPanel.test.tsx`, `StockDocumentsPanel.test.tsx`.
- **Phase 3**: `/code-review`, DoD gate, agent-browser evidence run on SO404352 (the drawer reads 9 on the AM subtotal; Confirm proposes the 15 BRW → BRW-AM transfer; Approve it on the page), PR to `main`.

Estimate: FE 3 days, BE 1.5 days, review + evidence 0.5 day. One coder slot, stack on :3000/:8000 from this checkout.

## 6. Open items

None blocking. Note for the evidence run: `inventory.stock_transfers.edit` must be on the planner's role in the dev DB or the Approve buttons will not show.
