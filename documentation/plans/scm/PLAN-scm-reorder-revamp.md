# PLAN: Reorder planning revamp - plans list, Start Plan, decide in the expanded row, one Confirm

Status: GO (aligned 27 Aug 2026, R1-R15). Phase 1 FE next.
UAC: `scm-reorder-revamp-acceptance-criteria.md` (alongside).
Alignment artifact: `mockups/reorder-revamp-plan.html` (lavish, reviewed by the captain, "ok good to go").
Branch: `feat/scm-reorder-revamp` off main `741469185` (#353), worktree `.claude/worktrees/scm-reorder-revamp`.
Sibling: `PLAN-scm-planning-inline-decisions.md` (fulfilment board) settled the UI pattern this plan mirrors.

## 1. Goal

Reorder planning works the way fulfilment planning now does:

- `/scm/reorder` is a DataGrid list of plans; one primary **Start Plan** button.
- `/scm/reorder/{id}` is one plan. Each product row expands into the whole decision: cover mix
  (stock / PO / buy), MOQ, last price + last supplier, AutoCount level + reorder qty, product health.
- Edits are local drafts. **Save (N)** persists them in one request. **Confirm (N)** saves, then
  confirms the whole plan into draft purchase orders. Untouched rows confirm as the suggestion.
- Every number on the row (Suggested qty, Project, Retail, On hand, SPO, PO) opens a lightbox that
  names the documents behind it. No hover popovers, no (i) icons.

Nothing about the engine or its frozen numbers changes.

## 2. Verified facts (read before touching anything)

| # | Fact | Where |
|---|------|-------|
| F1 | "Live stock as of" is the **request time**: `as_of = datetime.utcnow()` | `app/services/scm/location_stock_service.py:127` |
| F2 | Confirm (N) counts **locations, not products**: `decided_count = len(data)` is one per recommendation; a product-grain row fans one decision out to every location member | `app/services/scm/decision_service.py::list_plan_row_decisions` |
| F3 | Open PO book is already keyed `product_id:warehouse_id`, so a BRW-only read is a key lookup | `app/services/scm/po_book_service.py:72` |
| F4 | Purchase history has no warehouse filter; 12,928 of 12,940 imported PO lines name no destination | `purchase_trend_service.py`; `reorder_run_service._last_purchase_cost_map` docstring |
| F5 | Demand drill already returns `customer_label`, `agent_label`, `unit_price`, `so_number`, `required_date`; `scope=product` is the history list, `scope=location` the open list | `demand_breakdown_service.py:353-364` |
| F6 | The location matrix dialog with expandable documents exists: `CellStockTable` + `StockDocumentsPanel` | `app/(protected)/project-sales/fulfilment-planning/components/` |
| F7 | Expanded row machinery exists on this grid: TanStack `getExpandedRowModel`, `meta.expandedContent` on the `sku` column, whole row toggles | `PlanLinesGrid.tsx:608, 889-897, 1732-1743` |
| F8 | Every per-row write already has an endpoint: decision `POST /recommendations/{id}/decision`, MOQ `PUT /recommendations/{id}/moq`, level `POST /reorder-levels/amend-suggestion` + `PUT /reorder-levels`, lifecycle `POST /product-lifecycle-decision` | `app/api/v1/scm/decisions.py`, `reorder_runs.py`, `reorder_levels.py` |
| F9 | Runs list endpoint exists, paginated, returns started_at, plan_horizon_date, warehouse_codes, summary counts | `reorder_runs.py::list_reorder_runs` |
| F10 | `cheaperAlternative(chosen, alternatives, thresholdPct)` exists on the FE, gated by the policy threshold | `scm/reorder/lib/priceAdvice.ts:277-305` |

## 3. Rulings (captain, 27 Aug 2026)

| # | Ruling |
|---|--------|
| R1 | Plan detail lives at `/scm/reorder/{id}`; `/scm/reorder?plan=` redirects there. |
| R2 | SPO is a fact in the panel ("N arriving, already in net"), never an input. |
| R3 | Confirm covers untouched rows as the engine suggestion; skipped rows are left out. |
| R4 | Reset planning moves under the grid's Actions menu. |
| R5 | Reorder qty becomes editable next to Level; both land in the level-changes export. |
| R6 | Suggested price = last PO price and last PO supplier, always. The engine shortlist is demoted to the amber "cheaper on file" line and the supplier select. |
| R7 | "Stock as of" = newest `stock.updated_at` for the product (fallback: last stock import job finished time). |
| R8 | Product health chip leaves the collapsed row; a Filters entry keeps it findable. |
| R9 | Tiles (N of Total made / Cash committed / Cash if all accepted) stay above the grid. |
| R10 | Order summary / Plan exceptions / PO worklist stay on the plan page under Actions. |
| R11 | Plan header = date-time + Sales order cut-off only. Save and Confirm sit on the grid's own toolbar, right of Actions, Confirm last. |
| R12 | The expanded row holds decisions only; the per-location stock table moves into the On hand lightbox. |
| R13 | Column "PO outstanding" renamed "PO". |
| R14 | Confirm (N), Save (N), "N of Total made" count **distinct products**, not locations (fixes F2). |
| R15 | PO cell and PO dialog count the **BRW pool location only** (not BRW-BB / BRW-AM), like On hand and SPO. History lines with no destination or a project destination are left out. |

Removed from the page: Manual plan button, Upload data menu (moves to the list's Actions), the reset
icon (R4), "Confirm decisions" wording, Select all in the modal, the "Live stock as of" line in the panel.

## 4. Design

### 4.1 Plans list `/scm/reorder`

- `DataGrid` (`components/ui/data-grid.tsx`), `listingKey` = `scm.reorder.run`, standard toolbar.
- Columns: Plan (started_at, dd/mm/yyyy HH:mm, "daily" badge for the cron run), Sales order cut-off
  (plan_horizon_date), Warehouses (codes or All), Products (All or count), Lines, Decided (`x / y`,
  products, R14), Status, Cash if all accepted.
- Status derived on the FE from the run row: Running (status not completed/failed), Planning
  (completed, confirmed products < products), Confirmed (every product confirmed or skipped), Failed.
- Whole row click -> `/scm/reorder/{run_id}`. No row menu.
- Toolbar: Actions = the three `UploadDataMenu` groups flattened + Refresh; primary = Start Plan.
- Backend: `GET /scm/reorder-runs` gains `sort`, `dir`, `query` (`buildDataGridParams`) and
  `product_count`, `confirmed_product_count`, `decided_product_count` in the row.
- `RunHistoryPanel` deleted. `?run=1` (auto-open modal) kept on the list route.

### 4.2 Start Plan modal

`RunPlanningModal` renamed in copy only: title "Start Plan", fields in order **Sales order cut-off**
(date, hint "Empty = every open order counts."), Warehouses, Products; no Select all; buttons Cancel /
Start Plan. Payload unchanged. On 202 navigate to `/scm/reorder/{run_id}`; the page shows the
existing progress state until the run completes.

### 4.3 Plan page `/scm/reorder/[id]`

- Header: back link "Plans", "Plan dd/mm/yyyy HH:mm", sub "Sales order cut-off dd/mm/yyyy".
- Tiles unchanged (R9), counts by product (R14).
- Grid toolbar (`DataGridListToolbar`): search, Filters, Columns, Export, Expand all / Collapse all
  (`table.toggleAllRowsExpanded`, SPO allocations icon pair, disabled when nothing to do); right:
  Actions (Order summary, Plan exceptions, PO worklist, Reset planning), Save (N), Confirm (N).
- Collapsed columns, in order: #, Product, Suggested qty, Reorder level, Reorder qty, Project,
  Retail, On hand, SPO, PO, Decision. Total cost stays defined, hidden by default. MOQ, Price,
  Supplier, Level, Health columns removed from the grid (their content moves to the panel).
- Decision cell = status pill only: Suggested / Unsaved / Saved / Confirmed / Skipped + the mix in
  words ("Stock 31", "Buy 200", "Stock 10 + Buy 90").
- Several rows may be open at once (Expand all needs it). No unsaved-edit prompt between rows;
  drafts live in a page-level map keyed by rec id.
- Legacy runs (`front_planning_contract_version` null) render the panel with every input disabled,
  same lock reason as today.

### 4.4 Expanded panel (`PlanRowPanel`, replaces `GroupMembersPanel` content)

Four zones on one `bg-muted` strip, one screen tall at 1280:

1. **Cover**: From stock (cap = pool available), From PO (cap = open PO qty, BRW), Buy (re-rounded
   to MOQ + multiple on blur), SPO arriving (read-only fact), MOQ input (master shown beside).
   Quiet hint "N over / N short" vs suggested. Buttons: Use suggestion, Skip.
2. **Price and supplier**: Last price (cost, PO ref, date from the BRW-filtered last purchase),
   Last supplier as a `SearchableSelect` over the shortlist, amber line when `cheaperAlternative`
   finds one, radio Use last price / Get new price, "Line cost RM x" (today's Total cost).
   Never purchased: "No price on file", radio defaults to Get new price.
3. **AutoCount level + qty**: suggestion badge + "now N", Level input, Reorder qty input, one-line
   terms (ADU / lead / safety) and a link that opens the existing chart in a dialog.
4. **Product health**: verdict badge, radio Keep selling / Discontinue, one-line facts.

Every input writes to the draft map; the pill turns Unsaved. Leaving the page with drafts prompts.

### 4.5 Save and Confirm

- **Save (N)**: `PUT /scm/reorder-runs/{run}/plan-edits` (new)
  `{rows: [{rec_id, decision?, moq?, level?, reorder_qty?, lifecycle?}]}`. One transaction; each
  field calls the existing service function (`record_plan_row_decision`, `set_moq_override`, level
  amend, `record_lifecycle_decision`). Grouped rows fan out to members as today. Returns the refreshed
  rows. Per-row endpoints stay.
- **Confirm (N)**: Save, then `POST /reorder-runs/{run}/confirm-decisions`. `confirm_decisions`
  treats a product with no decision row as the suggestion (R3); skipped rows are excluded.
  `ConfirmActionDialog` states products + cash. N = distinct products (R14).

### 4.6 Lightboxes (`Dialog`, `sm:max-w-[95vw]`)

| Number | Tabs | Columns | Source |
|--------|------|---------|--------|
| Suggested qty | Ledger | today's `PlanOrderQtyLedger` rows | row fields |
| Project | Order inquiries (open) / SO history | SO or Inquiry, Customer, Project, Agent, Price, Qty, Date | `demand?channel=project&scope=location` / `scope=product`, gains `project_title` |
| Retail | Open sales orders / SO history | SO, Customer, Project, Agent, Price, Qty, Required | `demand?channel=retail&scope=location` / `scope=product` |
| On hand | Site pool stock | Location, On hand, Reserved, Free, SO qty, SPO qty, Available, PO qty, expandable documents; "Stock as of" | `location-stock` pool rows (`is_pool`) + documents reader; `as_of` per R7 |
| SPO | Open to BRW / History to BRW | SPO, Supplier, Qty, Received, ETA, Arrived, Status | new `GET /reorder-runs/{run}/spo-history?product_id=` over `spo_supply` |
| PO | Open to BRW / History to BRW | PO, Supplier, Qty, Unit price, Issued, ETA, Status | `po-book` at the BRW key; `purchase-trend` with new `warehouse=` filter (R15) |

## 5. Backend changes (Phase 2, test-first)

1. `PUT /scm/reorder-runs/{run}/plan-edits` bulk save, one tx, per-field tests, 404 for a rec
   outside the run, 409 on a legacy run.
2. `GET /scm/reorder-runs/{run}/spo-history?product_id=` (BRW pool only, open first then received).
3. `purchase-trend` + `price-history` + `_last_purchase_cost_map`: `warehouse` filter, BRW pool
   (R15); `inputs.last_purchase` gains `supplier_id` + `supplier_name`.
4. `list_reorder_runs`: sort/dir/query + `product_count`, `decided_product_count`,
   `confirmed_product_count`.
5. `list_plan_row_decisions`: `decided_count` / `total_count` by distinct `product_id` (R14).
6. `confirm_decisions`: untouched product = suggestion (R3), skipped excluded; the confirmed count
   in the response is by product.
7. `location_stock_for_product`: `as_of` = `MAX(stock.updated_at)` for the product, fallback latest
   stock `ImportJob.finished_at`, else null (R7). Response also carries `as_of_source`.
8. `PUT /reorder-levels` accepts `reorder_qty` (R5).
9. `demand_for_recommendation` rows gain `project_title`.

No migration expected. If one is needed, `alembic heads` against origin/main first (main had two
heads on 27 Aug; the sibling lane's first migration is `438_merge_430_437`).

## 6. Out of scope

Engine numbers, the fulfilment board, the daily cron, order summary / exceptions / PO worklist
views (untouched, relocated under Actions), the market assistant.

## 7. Risks

- Plan size: whole run is loaded client-side; Expand all stays within the current page (50 rows).
  Lightbox data is fetched on open, never eagerly.
- Last supplier is product-wide when the BRW filter finds nothing; the panel says which basis it used
  (`last_purchase_basis`).
- Unsaved drafts die on refresh; the pill count and the leave-page prompt make that visible.
- Stack slots: :3000/:8000 = primary checkout (sibling lane), :3050/:8050 = oi-draft lane. This lane
  needs a slot before Phase 1 browser verification.

## 8. Build order

Phase 1 (FE, mocks): list page + modal; `[id]` page + toolbar + redirect; collapsed columns + pill;
Expand all; `PlanRowPanel` 4 zones + draft map + Save/Confirm against a mock; six dialogs.
Phase 2 (BE, test-first): section 5, then FE off mocks; vitest for panel, pill, Save/Confirm, dialogs.
Phase 3: agent-browser run from the sidebar (list -> Start Plan -> plan -> Expand all -> edit ->
Save -> Confirm -> draft PO), 375 px + 1280 px, `/code-review`, DoD gate, PR.
