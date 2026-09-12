# PLAN: Reorder planning feedback batch (9 Sep 2026)

Status: BUILT 9 Sep 2026, PR #784 ready; round 3 (S14, the sheet's layout and sources) built 10 Sep; S15 (Supplier column = last PO supplier) built 10 Sep. All rulings settled (captain, lavish review 9 Sep 14:20; owner ruling 10 Sep for S15). Issues #770-#778 (S1-S9 in order).
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

Settled by the captain in the lavish review, 9 Sep 2026:

- **G1 Retail deliveries = delivery-order lines shipped from a `dealer`-segment warehouse.**
  A line shipped from a `project` bin (BRW-IB, BRW-BB, ...) is a project delivery. This is
  the only channel signal on `orders`; `demand_nature` is empty and DOs carry no SO class.
  Applies to the level suggestion (ADU) only. Health stays on all deliveries.
- **G2 Undated demand stays in the window.** A start date drops lines dated before it; a
  line with no date is still counted, the same reading the end date already gives it.
- **G3 No backfill.** The migration adds the column at `false` for every product; the buyer
  flips `**NEW`, `**SPARE PART` and the rest by hand on the product page. (Captain chose this
  over marking every `**` code.)
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
- Migration: column only, default false, no backfill (G3).
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
- `GET /order-summary/export?run_id&format=pdf|xlsx`: HTML template (landscape, the sheet's
  nine columns, Order qty = chosen or blank) through `pdf_render`; workbook built directly
  with openpyxl in `summary_order_service` (Phase 3 ruling S2: `xlsx_renderer`'s fixed
  multi-sheet register shape - title block, two-row header, one tab per month - did not fit
  a single flat nine-column sheet, and forcing it would have meant bending that renderer's
  contract for one caller). FE Export split button (PDF / Excel) using the existing download
  helper.

### Round 2 (captain, 9 Sep evening): S10-S13

Rulings (captain, screenshots 17-20): the Order summary page goes, the sheet is printed from
the plan's Actions menu; prices read in the buying currency and the "No MYR rate" hint goes
(most buying is CNY); the row's "Use suggestion" becomes "Save"; an MOQ typed on a row is
remembered on the product-supplier link and applied by the next run.

- S10: `ReorderPlanView` Actions menu: two entries calling `downloadOrderSummaryExport(runId,
  'pdf' | 'xlsx')`; drop the `order_summary` view branch, `SummaryOrderReportView`,
  `useSummaryOrder` hooks and tests if nothing else consumes them (`useConfirmOrderDecisions`
  checked). Backend routes untouched.
- S11: `PlanRowPanel` supplier prefill = `price.last.supplier_id` (price-history payload
  carries `last.supplier_id`; expose supplier code/name if missing) before `line.rec.supplier`;
  line cost via a new `lib/lineCost.ts`: `{amount, currency, basis}` from (buy qty, price mode,
  last purchase, chosen supplier cost); `fmtSupplierCost` labels it; hint removed.
- S12: row "Save" = `usePlanEdits.saveRow(productId)` -> `savePlanEdits(runId, rows for that
  product)` then drop the product from `edits` and invalidate decisions/lines; "Skip" unchanged.
- S13: `reorder_run_service.set_moq_override` gains a `remember=True` path calling a new
  `product_supplier_service.remember_moq(db, product_id, supplier_id, moq)` (upsert on the
  unique (product, supplier) link); supplier resolution order chosen -> last purchase ->
  primary; plan-edits passes the row's chosen supplier. FE MOQ input value = `edit.moq ??
  rec.moq_override ?? rec.supplier?.moq ?? ''`.

### G7 (captain, 9 Sep late): the engine buys from the last-purchase supplier

Browser round 4 measured: SRTSS8710's recommendation carries `supplier_selection: primary`
(DEFAULT link, MYR 121.80, moq null) while the buyer's row prefills KAIPING HANSHUN (last
purchase CNY 48.00) and the MOQ 100 saved by S13 sits on the KAIPING link, so the next run
neither prefills nor rounds to it, and the cash tiles still price the line in RM off DEFAULT.
Ruling: the engine's chosen supplier for a product = the last-purchase supplier when one is on
file (its product_suppliers link, created by S13 when missing; price by the candidate cascade
that already exists: the last purchase first, the link's contract cost second), else the primary
link, else the cheapest candidate as today. Applies on every supplier pick: cell, product,
pool and network aggregate. A blank or 0 MOQ clears the per-run override only; the link's
MOQ is master data and is never nulled by a plan row. MOQ, lead time and price then come from that one supplier, and the row's Supplier, Line
cost and MOQ agree with each other and with the next run. Lines whose currency has no MYR rate
contribute nothing to the cash tiles (honest until the rate is keyed). Goldens re-pinned.
Recorded as AC-S13.6.

### Round 3 (captain, 10 Sep, screenshots 21-24): S14 the sheet reads like the paper one

Rulings (captain, 10 Sep): the printed sheet is the buyer's paper sheet, not a grid dump.
The header row is emphasised (dark fill, white bold text), every cell is bordered, cells
wrap and grow so a month list or a customer list sits one entry per line. Delivery and
Project / customer come from the project ORDER INQUIRY, not the SO book, and Delivery is
shown only for project inquiry rows (a row with no inquiry has a blank Delivery). Remarks
stops being a sentence: BRW PO qty, BRW incoming qty, Last in qty and Last in date become
their own columns. Reorder level gets a column beside on hand, and "HQ on hand" becomes
"BRW on hand" - BRW meaning the site pool (active, non-project warehouses, the SAME
`pool_predicate.ACTIVE_SITE_POOL_SQL` the PO column already uses), for on hand, PO and
incoming alike.

Measured (0907, run 914bacdc 9 Sep, 374 rows): `project_demand` (SO book, demand_class =
project) is > 0 on 86 rows, but the Order Inquiry book holds 46 ORDER rows (34 placed, 12
raised, 1 ORDER_BACK cancelled) on 28 products, all dated; so an inquiry-sourced Project
qty / Delivery / customer column is populated on far fewer rows than today's SO-book one,
by the captain's ruling. `on_hand` today is `network_positions` over every
`counts_as_available` warehouse, project bins included (BRW-BB alone holds 108,969 pcs);
site pool stock: HQ 697,053 / BRW 632,883 / DC1 124,707 / MWH 96,870 / WH3 58,479.
`incoming_spo_qty` today is network-wide: open SPO allocations sit 371,053 at BRW,
~26,500 at project bins, 294 with no warehouse. `scm.reorder_level` warehouse-scoped rows
carry NO level (0 of 2,260 BRW rows); the engine plans against ONE product-wide level
(`_product_level`: buyer's product-wide row, else AutoCount master) and freezes it on every
recommendation as `inputs.reorder_level` (950 of 950 recs on the run carry the key).
`orderSheetText.ts` has no importer but its own test since S10 removed the page.

Design (S14):
- Columns, in order (replaces `_EXPORT_COLUMNS`): Item code, BRW on hand, Reorder level,
  Project qty, Dealer o/s, Order qty, Delivery, Project / customer, Supplier, BRW PO qty,
  BRW incoming qty, Last in qty, Last in date, Remarks.
- `write_rows` freezes two more columns (migration 504, additive): `pool_on_hand` (sum of
  `stock.quantity_on_hand` at site pool warehouses) and `reorder_level` (the run's own
  `inputs.reorder_level` for the product - first rec carrying one; NULL when none). Neither
  replaces `on_hand`, which the grid still reads.
- `incoming_spo_qty` re-scoped in place to site pool warehouses (join `warehouses` on the
  allocation's `warehouse_id`, `ACTIVE_SITE_POOL_SQL`; an allocation naming no warehouse is
  not counted, the PO column's own rule). No migration - same column, the sheet's meaning.
- `delivery_by_month` and `project_customers` re-sourced to the Order Inquiry: ORDER rows
  with `qty > 0`, state not cancelled (raised, partly_linked, placed all count - placed is
  need already covered by a PO, which the BRW PO column shows), on an active supply
  decision, through `oir.so_line_id -> projects.sales_order_lines -> core sales_order_lines`
  for the product; month = `oir.delivery_date` (undated last, as now); label =
  "<customer> / <project title>" via `projects.sales_orders.project_id -> projects.projects`,
  else customer. Not windowed by the run horizon - the two cells and Project qty must tie.
  The retail SO leg leaves `delivery_by_month` entirely. Raw SQL with
  `company_sql_predicate` (M2).
- Export Project qty = the sum of `project_customers` qty (ties by construction). The
  API's `project_demand` is untouched.
- Text cells: Delivery = one "Mon - qty" per line ("Jul - 1\nAug - 1", undated last as
  "Undated - qty"); Project / customer = one "Name - qty" per line; Remarks = "MOQ 1000" or
  blank. Last in date = dd/mm/yyyy.
- PDF (`_render_export_pdf`): title "Order Summary" + as-of date; header row dark fill
  (#404040) white bold centred, repeated on every page; 1px solid #333 borders on every
  cell; `white-space: pre-line` on the two list cells; numbers right-aligned; product code
  bold; vertical-align middle; landscape A4 stays.
- Excel (`_render_export_xlsx`): header row bold white on #404040 fill, thin borders on
  every written cell, `wrap_text` + top alignment on every cell, explicit column widths
  (item 16, numbers 10-12, Delivery 14, Project / customer 44, Supplier 20, Remarks 16),
  freeze panes at A2, row height left unset so the application autofits wrapped rows.
  Multi-line cells carry "\n". `_xlsx_safe_text` still wraps every string.
- FE: delete `lib/orderSheetText.ts` and its test (orphans since S10). No other FE change:
  the sheet is export-only.

Out: the grid's own columns; a per-warehouse reorder level (none is set); windowing the
inquiry legs by horizon.

### S15 (owner, 10 Sep 2026): Supplier column = last PO supplier

Measured (DB `sorento_ai_automation_0907`, prod copy, 10 Sep): the Supplier column
(`_suggested_supplier_map` in `summary_order_service.py` ~line 725) was filled from the
PRIMARY `product_suppliers` link, else any link. `product_suppliers` holds 11,807 links;
11,804 point at ONE supplier, code DEFAULT (`suppliers.created_at` 2025-12-24, the oldest
supplier), none primary. So every sheet row printed "DEFAULT". Cause:
`resolve_default_supplier_id` (`app/services/rules/product_rules.py:244`) auto-links every
new/imported product to `system_settings.default_product_supplier_id`, else the OLDEST
supplier - DEFAULT here. Of the 5,353 products with `purchase_order_lines`, only 1 has a
`product_suppliers` link that agrees with its own last PO.

Ruling 1 (owner): the sheet's Supplier is the LAST-PO supplier, always - the supplier of
the newest PO line (`purchase_orders.issue_date desc nulls last, created_at desc`). A
buyer's explicit `chosen_supplier_id` on the row still wins (unchanged). A product with no
PO history prints blank, never DEFAULT, never the link table. Remarks' MOQ / order
multiple describe that SAME supplier: read from its `product_suppliers` link when one
exists, else null. `_suggested_supplier_map` -> `_last_po_supplier_map`.

Ruling 2 (owner): `scripts/backfill_product_supplier_from_last_po.py`, dry-run by default,
`--apply` to write, same shape as `scripts/backfill_grn_spo_allocation_links.py`. Per
product with PO history: upsert a `product_suppliers` link to the last-PO supplier,
`is_primary_supplier=true` (clearing the flag elsewhere on the product, touching nothing
else on those other links), `standard_lead_time_days` from
`resolve_standard_lead_time_days(settings)` when creating; then delete the product's
DEFAULT link unless the last-PO supplier IS DEFAULT. `--drop-default-all` additionally
drops the DEFAULT link of products with NO PO history. Reports products seen, links
created/promoted, DEFAULT links removed, and 10 sample `product_code -> supplier_code`
lines. Never touches a link to any other supplier beyond its primary flag.

Out: changing `_supplier_constraints` (a separate purpose - the engine's order-quantity
MOQ rounding, `_channel_freeze`); running the backfill script against real data (owner
runs it after review, on the owner's go).

## 5. Build order

S1, S2 (FE only, no backend) -> S3 -> S6 -> S5 -> S4 -> S7 -> S8 -> S9 -> S14 -> S15. S1
and S2 are Phase 1 and Phase 2 in one (no contract change). S3-S9: FE mock first where the
contract changes (S4 window, S5 switch, S9 columns), then BE test-first. S14 and S15 are
BE-only, test-first, no FE contract change.

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
- No backfill (G3): the four `**` placeholder codes keep planning until the buyer flips them.
