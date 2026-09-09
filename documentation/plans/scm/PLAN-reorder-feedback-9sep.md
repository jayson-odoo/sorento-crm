# PLAN: Reorder planning feedback batch (9 Sep 2026)

Status: IN PROGRESS 9 Sep 2026. Rulings G2, G3, G1, G6 pending in the lavish review; S1 S2 S3 S6 S8 cleared by the brief. Issues #770-#778 (S1-S9 in order).
UAC: `reorder-feedback-9sep-acceptance-criteria.md` (journey J1-J7 lives there).
Lane: worktree `.claude/worktrees/reorder-feedback-9sep`, branch `feat/reorder-feedback-9sep`
off `origin/main` 3c3738ad7.

## 1. Goal

Fifteen screenshots of feedback from the purchasing seat, folded into nine slices. Every
item is a repair or a small extension of something that ships; no new module, no new
registry. The one structural addition is a boolean on `products`.

## 2. Measured facts (worktree at 3c3738ad7; DB = `sorento_ai_automation_0907`, prod copy)

- SPO list stacks `doc_date` under SPO No (`SPOAllocationsList.tsx:177`); the backend
  `list_documents` sort map already carries `doc_date` (`procurement_service.py` ~2304), so
  the column is FE only.
- SPO Document Lines sorting is decorative: `useReactTable` at `SPODocumentDetail.tsx:834`
  wires `getCoreRowModel` + `getPaginationRowModel` only, no sorted row model; Product,
  Warehouse, Plan, Packing List, Status have no accessor. No search box on the tab. The PO
  and SO detail pages each carry an inline `lineSearch` + `getFilteredRowModel` block
  (`PurchaseOrderDetail.tsx:779-793`, `SalesOrderDetail.tsx:1047-1057`); no shared component.
- Plan grid Filters: five preset selects at `PlanLinesGrid.tsx:1153-1216`, client-side
  `.filter()` at 382-420; the builder (`DynamicFilterBuilder`, fields in
  `lib/planLineFilterFields.ts`) already covers rec type and decision state.
- `fmtMoney` / `fmtMoneyIn` (`scm/lib/format.ts:61-79`) format with 0 fraction digits;
  `fmtSupplierCost` uses 2. Hence "RM 0" beside "RM 2.00".
- Last price (`PlanRowPanel.tsx:356-363`) prints `price.last.unit_cost` labelled with
  `line.currency` (the rec's, MYR/null) while the sub-line `describeLastPurchase` labels
  with the purchase's own `CNY`. Same number, two labels. `scm.currency_rate` has 0 rows on
  the prod copy, so `to_base` answers `missing_currency` and Line cost reads "-".
- Project lightbox: FE "open" tab omits `scope: 'product'` (`PlanRowDialogs.tsx:200`) while
  the history tab passes it, and `recId = anyRecId(line)` picks one member location of a
  grouped row. BE `demand_breakdown_service` states in its docstring (lines 34-37) that
  form-leg rows are "absent rather than misattributed". Either produces "Project 3, 0 open".
- Horizon: `plan_horizon_date` (end only) on `CreateReorderRunRequest`
  (`scm_reorder.py:34`), `ReplanReorderRunRequest` (44-51), applied in
  `demand.py:477-479, 507-509, 584-586` as `date IS NULL OR date <= :horizon`. No start.
- Products: `is_active`, `is_discontinued` exist (`product.py:209,215`), no planning flag.
  Candidate filter is one list at `reorder_run_service.py:740`. The `**NEW`, `**SPARE PART`,
  `**REPLACE`, `**REPAIR` placeholder codes are active and not discontinued, so they plan.
- Confirm: `decision_service.py:688-720` (location grain) and `918-935` (product grain)
  sweep every undecided `buy` rec with `rounded_qty > 0` into PO lines, by design (R3,
  27 Aug). FE `confirmSummary` (`lib/planEdits.ts:195-229`) counts the same way, hence
  "Confirm (309)" on "0 of 996 made".
- ADU: `reorder_level_service.average_daily_usage` (126-151) sums `scm.consumption_v`
  `qty_out` with no channel filter. The view's `demand_nature` is NULL on every row (both
  market segments carry no nature). Last 90 days of delivery-order lines: 38,371 lines /
  399,710 pcs shipped from `dealer`-segment warehouses, 15,010 lines / 452,409 pcs from
  `project`-segment bins. Project shipments are 53% of the quantity that lifts every level.
- Health: `movement_class` (`product_economics_service.py:238-252`) sold-3mo x bought-6mo
  grid; decision in `scm.product_lifecycle_decision`, no default (line 215).
- Order summary exists (`summary_order_service.py`, `SummaryOrderReportView.tsx`, reached
  by the "Order summary" link on the plan) and is frozen per run. Its docstring still says the
  split reads `sales_orders.order_type` because `demand_class` was empty; today
  `demand_class` is project 11,379 / retail 75,447 / NULL 466. No delivery-month, customer
  names, last receipt or MOQ on the row. Reusable renderers: `services/reports/xlsx_renderer.py`
  (openpyxl) and `services/pdf_render.py` (WeasyPrint, guarded).
- Last receipt is answerable: `picking_lines.qty_accepted` + `picking_headers.picking_type =
  'goods_received'`, e.g. SRTSA-SS last in 29/07/2026, SRTWT6813 21/07/2026.

## 3. Rulings

Standing (unchanged): G1/G8/G10 of 1 Sep (committed-demand universe, Re-plan supersedes,
named product bypasses the demand gate). R16-R19 of 28 Aug (pool-only on hand). "No
warehouse-segment derivation of DEMAND channel" (R17) stands; G1 below is about
CONSUMPTION history, where the shipping bin is the only channel signal that exists.

Proposed, need the captain's word:

- **G1 Retail deliveries = delivery-order lines shipped from a `dealer`-segment warehouse.**
  A line shipped from a `project` bin (BRW-IB, BRW-BB, ...) is a project delivery. This is
  the only channel signal on `orders`; `demand_nature` is empty and DOs carry no SO class.
  Applies to the level suggestion (ADU) only. Health stays on all deliveries.
- **G2 Undated demand stays in the window.** A start date drops lines dated before it; a
  line with no date is still counted, the same reading the end date already gives it.
- **G3 Backfill the exclusion flag** for every product code starting with `**` at migration.
  Everything else stays in; the buyer flips the rest by hand on the product page.
- **G4 Health suggestion persists on Confirm.** The preselected radio is written as the
  product's lifecycle decision for every product the buyer confirms; products left undecided
  get nothing written.
- **G5 Confirm never sweeps.** Reverses R3 (27 Aug). Untouched rows are not bought; Confirm
  (0) is disabled. Applies to the Order summary confirm too (same endpoint).
- **G6 Report shape = the sheet.** Order summary grows the sheet's columns and exports as
  landscape PDF + Excel; no separate report page. Month groups render as text in one cell,
  the way the sheet writes them.

## 4. Design

### S1 SPO list + Lines tab (FE only)
- `SPOAllocationsList.tsx`: new column `doc_date` (`accessorKey: 'doc_date'`, header "Date",
  `size: 110`, `fmtEta`), sub-line removed from the SPO No cell. Server sort key already
  `doc_date`.
- `SPODocumentDetail.tsx`: add `getSortedRowModel` + `getFilteredRowModel`, `sorting` state,
  accessors for product (`product.product_code`), warehouse (`warehouse.warehouse_code`),
  plan (`planning_span`), packing list (`inbound_shipment?.shipment_number ?? ''`), status
  (`receipt_status`). Search: copy the PO detail block (state + `globalFilterFn` +
  Search-icon Input + clear) into the Lines `CardToolbar`; matches product code/name,
  warehouse code/name.

### S2 Plan grid presentation (FE only)
- Delete the five preset selects and their state/`filtered` branches in `PlanLinesGrid.tsx`;
  keep the builder. Delete their tests.
- `scm/lib/format.ts`: `moneyFmt` min/max 2 fraction digits (touches every SCM screen; that
  is the ask, "standardized").
- `PlanRowPanel.tsx:358`: label with `price?.last?.currency ?? line.currency`. Under Line
  cost, when `price.last.currency` is foreign and `line.unit_cost_base == null`, render the
  "No MYR rate for CNY" hint with a link to `/scm/policies`.
- `PlanHeaderTab.tsx:242`: Edit `variant` default.

### S3 Lightbox parity
- FE: pass `'product'` scope on the open tab for grouped rows (`PlanRowDialogs.tsx:200`).
- BE: `demand_breakdown_service` adds the form leg to the project query (same predicates as
  `demand.py` form leg, minus horizon end -> both dates from the run), `source =
  'order_inquiry_form'`, customer = inquiry header customer, project title via
  `_PROJECT_TITLE_SQL` when the row's inquiry belongs to a project SO, else null. Update the
  docstring paragraph.

### S4 Window start
- Model: `ReorderRun.plan_horizon_start DATE NULL` (migration, additive). Schemas: both
  requests + `ReorderRunOut`. Validator: start <= end.
- `demand.horizon_committed_select_sql` binds `:horizon_start` beside `:horizon` on all
  three legs. Every caller that binds `horizon` binds `horizon_start` (grep
  `horizon_committed_select_sql` callers: `_planning_rows`, coverage, order summary).
- Re-plan: `replan_run` copies/overrides start; "horizon changed" test includes start.
- FE: `RunPlanningModal` two date inputs (`horizonStart`, `horizon`); `ManualPlanInputs` +
  `createReorderRun` + `replanReorderRun` carry `plan_horizon_start`; `PlanHeaderTab` two
  inputs in edit, one sentence in read; `runListing.ts` subtitle wording helper
  `describeWindow(start, end)` used by header, subtitle and plans list.

### S5 Exclusion flag
- Migration: column + backfill `UPDATE products SET exclude_from_planning = true WHERE
  product_code LIKE '**%'`.
- `Product` model, `ProductCreate/Update/Out` schemas, `product_service` dict builders,
  list serializer in `list_query_registry` (products resource).
- `_planning_rows` predicate; `create_run` refuses named excluded products with 422 listing
  the codes.
- FE: product form modal switch; detail page field; products list optional column
  `exclude_from_planning` (hidden by default) + filter field.

### S6 Confirm decided only
- `decision_service._confirm_location_grain` / `_confirm_product_grain`: remove the
  "untouched rows" loops; `ids=[]` = every decided row of the run. Response unchanged.
- `planEdits.confirmSummary`: `effective = edit?.decision ?? persisted`; no
  `suggestedDecisionFor` fallback. `PlanLinesSection` disables Confirm at 0 with tooltip.

### S7 Retail-only ADU
- Migration: `CREATE OR REPLACE VIEW scm.consumption_v` appending `warehouse_segment`
  (LEFT JOIN warehouses on `ol.warehouse_id`). Append only, no type change (lesson on
  `unclassified_committed`).
- `reorder_level_service.average_daily_usage(..., retail_only=True)` adds
  `AND warehouse_segment = 'dealer'`; `level_suggestion_service.refresh_for_run` passes it
  and stamps `basis.retail_only`. `monthly_movement` (3-month chart) gets the same flag so
  the chart under the level agrees with the number. `product_economics_service` untouched.
- FE `levelTerms()` appends "(retail)".

### S8 Health default
- `lib/productHealth.ts`: `suggestedLifecycle(movement_class)`. `PlanRowPanel` radio value
  = `edit?.lifecycle ?? economics?.lifecycle_decision ?? suggestedLifecycle(...)`.
- `usePlanEdits` payload: include `lifecycle` for any row with an edit (already) and, on
  confirm, for every confirmable product, via the existing `plan-edits` save that precedes
  confirm (no new endpoint: confirm already saves first).

### S9 Order summary = the sheet
- `summary_order_service.write_rows`: compute and freeze on `scm.order_summary_row` five
  JSONB/scalar columns (migration, additive): `delivery_by_month`, `project_customers`,
  `po_open_qty`, `incoming_spo_qty`, `last_receipt_date`, `last_receipt_qty`, `moq`,
  `supplier_name`. Sources: the run's committed legs (retail `sol.required_date`, project
  `oir.delivery_date`), `po_book_service` (pool PO), `spo_supply` (incoming), goods-received
  picking lines, `SupplierChoice.moq`. Fix the docstring's `order_type` note to `demand_class`.
- Schema `OrderSummaryRowOut` + FE types; `SummaryOrderReportView` columns re-ordered to the
  sheet with the four new cells; `lib/orderSheetText.ts` builds the month / customer /
  remarks strings (tested).
- `GET /order-summary/export?run_id&format=pdf|xlsx`: HTML template (Jinja, landscape, the
  sheet's nine columns, Order qty = chosen or blank) through `pdf_render`; workbook through
  `xlsx_renderer`. FE Export split button (PDF / Excel) using the existing download helper.

## 5. Build order

S1, S2 (FE only, no backend) -> S3 -> S6 -> S5 -> S4 -> S7 -> S8 -> S9. S1 and S2 are
Phase 1 and Phase 2 in one (no contract change). S3-S9: FE mock first where the contract
changes (S4 window, S5 switch, S9 columns), then BE test-first.

## 6. Out of scope

- PO list still stacks `order_date` under PO number; not asked, left alone.
- Product health class itself (sold 3mo x bought 6mo) unchanged.
- Currency rates data entry: the buyer keys CNY under SCM > Policies > Currency rates; this
  plan only stops the mislabel and names the gap.
- Segment / saved-view machinery unchanged.

## 7. Risks

- S6 reverses a ruling that the confirm tests pin (R3). Goldens re-pinned; Order summary
  confirm shares the path, verified there too.
- S7 changes every suggested level on the next run; the captain should expect lower levels
  on project-heavy SKUs. Stated in the PR.
- `fmtMoney` 2dp touches every SCM screen's snapshots; expect a wide but mechanical vitest
  update.
- `**` backfill (G3) marks four placeholder codes; if any real product code starts with
  `**` it is caught by the list column.
