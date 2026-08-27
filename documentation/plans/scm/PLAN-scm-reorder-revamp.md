# PLAN: Reorder planning revamp - plans list, Start Plan, decide in the expanded row, one Confirm

Status: Phase 3 review applied 28 Aug 2026 (blockers, should-fixes, tester xfails and nits from the review pass; see section 11). PR next.
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
   `confirmed_product_count`, and `is_scheduled` (`reorder_run.created_by IS NULL` - the
   scheduler passes no actor). **Added in Phase 1**: the daily badge (A5) has no other honest
   source, and the FE refuses to guess one from the clock.
5. `list_plan_row_decisions`: `decided_count` / `total_count` by distinct `product_id` (R14).
6. `confirm_decisions`: untouched product = suggestion (R3), skipped excluded; the confirmed count
   in the response is by product.
7. `location_stock_for_product`: `as_of` = `MAX(stock.updated_at)` for the product, fallback latest
   stock `ImportJob.finished_at`, else null (R7). Response also carries `as_of_source`, plus
   `is_pool` and `po_qty` per location. **Added in Phase 1**: the On hand lightbox filters to
   site-pool rows (R15) and shows a PO qty column; without the flag it shows every location it
   is given rather than guessing a pool from a code.
8. `PUT /reorder-levels` accepts `reorder_qty` (R5).
9. `demand_for_recommendation` rows gain `project_title`.
10. `get_reorder_run` selects `started_at` too. **Added in Phase 1**: the plan header is
    "Plan dd/mm/yyyy HH:mm" (C1) and the detail response is the only thing the page reads.
11. Recommendation rows gain `pool_warehouse_code` beside `pool_warehouse_id`. **Added in
    Phase 1**: the SPO and PO lightboxes say "to BRW" (R15), and a grouped product row holds
    the pool's id but no code - a run only writes rows for locations with demand, so on live
    data (32MM TAIL PIECE COUPLING) no member sits at the pool to read one off. Until it
    ships the two dialogs drop the location from their wording rather than name a project
    bin the count excludes.

No migration expected. If one is needed, `alembic heads` against origin/main first (main had two
heads on 27 Aug; the sibling lane's first migration is `438_merge_430_437`).

**Built with NO migration** (28 Aug): every column written to already exists -
`scm.reorder_level.reorder_qty`, `warehouses.pool_warehouse_id`, `spo_allocations.*`.
`alembic heads` is the single `438_merge_price_supplier_sets` against `origin/main` at
`741469185`.

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

## 9. Phase 1 deviations (27 Aug 2026, recorded as built)

Everything below is a place the built screen departs from section 4, with the reason. Nothing
here changes a ruling.

- **Three backend reads joined section 5** (items 4, 7, 10 above): `is_scheduled`, `is_pool` +
  `po_qty`, `started_at`. Each is a field the agreed UI needs and no existing response carries.
  Until they ship the FE renders the honest fallback (no badge, every location, "Plan" with no
  time) rather than a guess.
- **SPO and PO lightboxes name no location on a grouped row** until section 5 item 11 ships:
  "Open (0)", not "Open to BRW-BB". Naming the first member printed a project bin beside a
  count that deliberately excludes it (R15).
- **PO lightbox, Open tab**: columns are PO / Still to come / ETA / Status, not the History
  tab's PO / Supplier / Qty / Unit price / Issued / ETA / Status. The open PO book
  (`po_book_service`) is a netting source and carries no supplier or unit price; those two
  belong to the purchase records the History tab reads.
- **Row click no longer opens `ReorderExplanationDialog`** - it toggles the decision panel
  (D1). The dialog is unchanged and still opens from `ReorderResultsGrid`; the Suggested-qty
  lightbox now carries the derivation a buyer opens from the plan.
- **Ungrouped (Location-grain) shape**: `Order type` and `SO` ship hidden by default, since
  Project and Retail beside them say the same thing. They stay in the Columns menu.
- **The leave-page prompt is two mechanisms**: `beforeunload` for a refresh, a close or a jump
  out of the app, and a confirm dialog on the plan header's own "Plans" link. Next's app router
  exposes no cancellable navigation event to hang a single guard on.

## 10. Phase 2 deviations (28 Aug 2026, recorded as built)

Everything below departs from section 5, with the reason. Nothing here changes a ruling.

- **`planned_product_count` joined the plans list row** beside `product_count`. Section 5.4
  named one count, but it is the SCOPE the plan was launched with and it is NULL on the
  daily run (which narrows to nothing) - so the Decided column would read "12 of -" on the
  commonest plan of all. `product_count` stays the scope (the Products column's "All");
  `planned_product_count` is what the run actually wrote rows for, and it is the
  denominator of Decided and of the Confirmed status.
- **`is_all_warehouses` joined the same row** (fix c). A plan launched with no warehouse
  scope stores every ACTIVE warehouse, so the column read "60 warehouses" for what the
  buyer asked for as "all", and only the backend knows how many there are. It is measured
  AS OF THE RUN (`warehouses.created_at <= started_at`): 60 existed on 27 Aug and 61 do
  now, so a fixed comparison against today would call every older plan partial forever.
- **`_po_for_rec` now matches BOTH source systems.** It looked only for
  `scm_recommendation`, but `_confirm_product_grain` stamps `scm_order_summary_row` on the
  same rec id - so on a product-grain run (the rollout default) the Decision pill stayed on
  Saved after a confirm that had plainly drafted the purchase order. Found in the browser
  run, fixed there.
- **The pool is resolved from the frozen `plan_basis.locations` when a row names no
  warehouse.** A product-grain buy carries `warehouse_id = NULL` (`_emit_product`), so
  section 5.11's `pool_warehouse_code` and the new SPO/PO reads found no pool at all on the
  live shape and returned an empty book. Both now read the locations the row was netted
  over, and the CODE is emitted only when they share ONE pool - a row spanning two sites
  still names none, which is Phase 1's own rule.
- **`ImportJob.completed_at`, not `finished_at`** (R7's fallback). That is the column the
  model actually carries.
- **`price-history` has NO `warehouse` filter.** Section 5.3 named one and F7 wants the
  panel's price and the PO dialog's newest row to be the same purchase, but the FE reads
  price-history once per RUN and each row has its own pool, so a run-wide parameter has no
  honest caller. It shipped in Phase 2 tested and unused, and the Phase 3 review deleted it
  (service, route and test). What the panel actually prints comes from
  `inputs.last_purchase`, which IS pool-filtered (`_last_purchase_cost_map`, basis `pool`),
  and `purchase-trend` keeps its own filter because the PO dialog calls it per row.
- **Existing saved column layouts survive.** `DataGrid` persists column sizing per
  `listingKey` (defaulting to the pathname), so the new collapsed widths only reach a user
  who has never opened the page - everyone else keeps theirs until they use Columns ->
  Reset columns. Not a defect, but it is why the widths look unchanged on a warm profile.

## 11. Phase 3 review pass (28 Aug 2026)

The review's findings, as applied. Each one flipped or added a test.

**Blockers**

- **The Level edit 422'd.** `plan_edits_service` forced `warehouse_id=None` into the level
  amendment, so on a location-grain run it looked up the product-wide `scm.reorder_level`
  row (which holds no suggestion) and refused the whole batch. The key now travels off the
  recommendation, which is where `level_suggestion_service._plan_pairs` stored the
  suggestion in the first place; the reorder quantity follows the same key for the same
  reason. The panel also disables the Level input when the row has no suggestion at all -
  an amendment of nothing has nothing to amend - and leaves Reorder qty editable.
- **R3 wrote no decision.** Confirm drafted the purchase order for an untouched product and
  recorded nothing, so the pill stayed Suggested, the tiles and the Decided column stayed
  short and Confirm (N) stayed live over rows already in a draft PO. It now writes a
  `PlanRowDecision` per member as the lines are upserted. **Deviation from the review's
  wording:** `buy_qty` is the PRODUCT's whole quantity on every member, not that member's
  share of the split - that is the shape `usePlanLines.decide` writes for a decided grouped
  row, so a re-confirm reads it back through the grid path and drafts exactly the same
  lines. A share would have re-split an already-split number on the second confirm.
- **The plan grid keyed its saved column layout on the plan.** `DataGrid` defaults
  `listingKey` to the pathname, which is `/scm/reorder/{run_id}`, so a buyer's own layout
  was never seen twice. It is `scm.dashboard.view::reorder-plan-lines` now.

**Should-fix**

- Confirm (N) counted products with nothing to buy. A row covered from stock or an open PO
  drafts no line, so it is no longer counted.
- R3 now covers the LOCATION grain too, decision row included. `_confirm_location_grain`
  had no untouched-as-suggestion branch at all, so a location run's buyer who agreed with a
  row got nothing for it.
- `reset_run_decisions` left product-grain draft lines behind (`_SRC_PRODUCT`, same rec id,
  different stamp), so the plans list read Confirmed forever after a reset. Both stamps are
  cleared now.
- The Decided column is sortable, so `_RUN_SORT` has a `decided` key (by distinct decided
  product). A test reads the sortable column ids off `ReorderRunsGrid.tsx` and asserts every
  one of them has a key, so the two cannot drift.
- The SPO history read is an ORM query using `open_incoming_clauses()`. It was raw SQL over
  a company-owned table (no company predicate at all - another company's shipping orders
  counted as ours) with a second Python copy of the open/received rule beside it.
- `price-history`'s `warehouse` parameter is deleted (see section 10).
- `_last_purchase_cost_map` broke same-day ties on `pol.created_at`. `po.issue_date` is a
  DATE, so two purchases on one day tied and the winner was whichever destination's id
  sorted first.

**Tester xfails**

- D4's "never purchased defaults to Get new price" is implemented; the `it.fails` is an
  `it`.
- The runs list ends every ordering on `id ASC`, so paging over rows tied on both
  `started_at` and `created_at` is stable. xfail removed.
- **Ruling (captain, 28 Aug): the plans list search is warehouse-only by design.** A plan's
  human handles are its time and its scope; "which plans mention this product" is the plan
  page's question. The xfailing product-code test is deleted rather than implemented.

**Nits**

- `_product_counts` drops a dead `LEFT JOIN purchase_orders` and reads the decidable
  rec types off `decision_service._PLAN_ROW_DECIDABLE_TYPES` instead of a second literal.
- The panel's supplier select is `clearable`; clearing means "no override", which reads as
  the row's proposed supplier and sends no `supplier_code`.
- The on-screen sentence "Prices older than N days are treated as stale" is gone (no rule
  explanations on screen), and the `staleAfterDays` prop with it.
- `as_of_source` was computed, typed and never rendered: dropped from the response and the
  FE type. `_stock_as_of` still returns which branch answered, which is what its tests read.
- Comments naming files this lane deleted (`ReorderPlanningView`, the five cell components,
  `UploadDataMenu.test.tsx`) say what is there now.
- The `#` column is 60px, not 36: it carries the grid's edge padding, so a rank past 99
  truncated to "1...".
- `_warehouse_id_for_code` and the as-of-the-run warehouse count carry the company
  predicate every other raw read in that file already had.
