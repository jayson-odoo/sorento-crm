# UAC: Reorder planning feedback batch, 9 Sep 2026

Plan: `PLAN-reorder-feedback-9sep.md`. Status: IN PROGRESS 9 Sep 2026; issues #770-#778.

## Journey

**Actor:** the buyer (purchasing seat). Arrives from the sidebar: Procurement > Supply Chain >
Reorder Planning, or Procurement > SPO Allocations.

**J1 Buyer starts a plan.** Start Plan asks for the sales-order window: an optional start date
and an optional end date ("Empty = every open order counts" stays true for both ends).
Warehouses and products as today. The system already knows which products are excluded from
planning (a flag on the product), so those never appear. The buyer decides ONE thing: the
window.

**J2 Buyer reads the plan.** Lines tab. The five preset dropdowns in Filters are gone; the
filter builder alone slices the grid. Prices everywhere carry two decimals. A CNY last price
reads "CNY 110.00" in both places, never "RM 110.00" beside "CNY 110.00". The Project count
on a row and the Project demand lightbox agree: every source the engine counted is listed.

**J3 Buyer decides a row.** Expanded panel. Product health arrives with the engine's
suggestion already selected: Dead -> Discontinue, Slow or Fast moving -> Keep selling. The
AutoCount level suggestion is built from retail deliveries only, so a project job that shipped
2,000 pieces once does not lift the dealer reorder level. Buyer changes what they disagree
with, saves.

**J4 Buyer confirms.** Confirm (N) counts only products the buyer decided (an explicit
decision saved or drafted). Rows nobody touched are NOT bought. Nothing decided -> Confirm (0),
disabled. What the buyer decided is what is bought, exactly.

**J5 Buyer changes the window or scope later.** Header tab, Edit is the primary call to action
on the Plan card. Both dates editable. Re-plan carries decisions as today (G8, 1 Sep).

**J6 Buyer prints the order sheet.** Order summary (already reachable from the plan) grows the
columns of the paper sheet: delivery quantities grouped by month, the project/customer names
behind the project quantity, the suggested supplier, and remarks (BRW PO qty, incoming SPO
qty, last receipt date + qty, MOQ). Export gives the sheet as PDF (landscape, one row per
product) and Excel. Nothing on the sheet is typed twice: every figure is the plan's own.

**J7 Buyer reads SPO allocations.** The list shows the document date as its own sortable
column; the SPO No cell is one line tall again. On the SPO document Lines tab every column
sorts when clicked and a search box narrows the lines by product code/name or warehouse code.

**Other stakeholders told automatically:** none new. AutoCount level output travels back by
the user as today.

## Acceptance criteria

Tags: [BE] backend, [FE] frontend, [E2E] browser walk, [T] test pinned.

### S1 SPO list date column + SPO Lines sort and search

- AC-S1.1 [FE] SPO Allocations list has a "Date" column right of SPO No showing `doc_date`
  as dd/mm/yyyy, sortable (server `sort=doc_date`, already supported). The SPO No cell no
  longer stacks the date underneath.
- AC-S1.2 [FE] SPO Document Lines tab: clicking Product, Warehouse, Plan, Packing List,
  Status, PO, SO covered headers reorders the rows (client-side sorted row model wired;
  every column has an accessor).
- AC-S1.3 [FE] SPO Document Lines tab has a search input (placeholder "Search product or
  warehouse") that filters lines by product code, product name, warehouse code or name,
  case-insensitive, with a clear button. Empty result shows "No lines match".
- AC-S1.4 [E2E] Sidebar walk: SPO Allocations -> sort by Date desc -> open an SPO -> sort
  Lines by Warehouse -> search a warehouse code -> only matching lines remain.
- AC-S1.5 [T] vitest: list renders Date column and no sub-line; detail sort by warehouse
  reorders; search narrows; product cell is one line when name equals code.
- AC-S1.6 [FE] SPO Document Lines Product cell follows the PO form view rule
  (`PurchaseOrderDetail.tsx:495-510`): the product name sub-line renders only when it is
  non-empty and differs from the code (case-insensitive); otherwise the cell is one line.
  Captain, 9 Sep 14:30 (screenshot 16).

### S2 Plan grid: filters, money, price label, Edit CTA

- AC-S2.1 [FE] Filters popover shows the filter builder only; the five preset selects
  (statuses, decided, price answer, suggested action, level answer) are removed, and their
  state code is deleted (not hidden). Rec type and Decision state remain builder fields.
- AC-S2.2 [FE] Every money value in `scm/` renders with exactly two decimals: `fmtMoney`
  and `fmtMoneyIn` use min/max 2 fraction digits. Cash tiles read "RM 9,070,460.00",
  a zero reads "RM 0.00".
- AC-S2.3 [FE] Last price in the row panel is labelled in the purchase's own currency
  (`price.last.currency`), so a CNY purchase reads "CNY 110.00" in both the value and the
  sub-line. Only when no purchase is on file does it fall back to the line's currency.
- AC-S2.4 [FE] When the purchase currency has no MYR rate on file, the row panel shows
  "No MYR rate for CNY, set it under SCM policies" under Line cost instead of a bare "-".
- AC-S2.5 [FE] Header tab Plan card: Edit is the primary button (default variant), same
  placement.
- AC-S2.6 [T] vitest: presets absent; fmtMoney 2dp; CNY label; Edit primary.

### S3 Project demand lightbox matches the row

- AC-S3.1 [FE] The "open" tab of the demand lightbox on a grouped (product) row queries
  with `scope=product`, the same scope the history tab already uses.
- AC-S3.2 [BE] `demand_for_recommendation` returns form-leg rows (Order Inquiry Form rows
  with no supply decision, the view's third leg) as `confirmed_lines` with
  `source='order_inquiry_form'`, customer from the inquiry, project title where linked,
  qty = raised minus linked, needed = `delivery_date`. The lightbox total equals the row's
  Project figure for every product on a run.
- AC-S3.3 [T] pytest: a product whose only project demand is one form-leg row shows
  `project_committed=N` on the row and N in the lightbox lines. Golden reads unchanged.
- AC-S3.4 [E2E] A product with Project > 0 opens a lightbox whose total equals the cell.

### S4 Sales-order window (start + end)

- AC-S4.1 [BE] `CreateReorderRunRequest` and `ReplanReorderRunRequest` accept optional
  `plan_horizon_start: date`; `ReorderRun` stores it; `plan_horizon_start <= plan_horizon_date`
  when both set, else 422.
- AC-S4.2 [BE] `horizon_committed_select_sql` applies the start on every leg the end applies
  to (book `sol.required_date`, confirmed and form `oir.delivery_date`):
  `(:start IS NULL OR date IS NULL OR date >= :start)`. Undated demand stays in (G2 ruling).
- AC-S4.3 [BE] Re-plan carries `plan_horizon_start` and treats a changed start as a changed
  horizon (decision carry rules unchanged).
- AC-S4.4 [FE] Start Plan modal: "Sales orders needed" with From and To date inputs, each
  optional, helper "Empty = every open order counts."; To before From is refused inline.
- AC-S4.5 [FE] Header tab shows "Sales orders needed: 01/01/2025 to 31/10/2026" (or "up to",
  "from", "every open order"); Edit exposes both inputs; plan page subtitle uses the same
  wording.
- AC-S4.6 [T] pytest: run with start only, end only, both; a line dated before start is
  out of committed, undated line stays in. vitest: modal validation, header wording.
- AC-S4.7 [E2E] Start Plan with From 01/01/2026: an SO required 2025 is absent from the
  Retail lightbox of its product.

### S5 Product excluded from planning

- AC-S5.1 [BE] Migration adds `products.exclude_from_planning BOOLEAN NOT NULL DEFAULT false`
  with no backfill (G3 ruling: the buyer flips products by hand).
- AC-S5.2 [BE] `_planning_rows` adds `p.exclude_from_planning = false`; an explicitly named
  product at Start Plan still bypasses (G10, 1 Sep) is NOT extended: an excluded product is
  excluded even when named, and the create request answers 422 naming it.
- AC-S5.3 [BE] Product read/update schemas carry the field; both manual dict builders and
  the product list serializer include it (CLAUDE.md "both dict builders").
- AC-S5.4 [FE] Product form (create + edit modal) has a "Exclude from reorder planning"
  switch under the existing status fields; product detail shows it; product list gets an
  optional column and a filter field.
- AC-S5.5 [T] pytest: excluded product absent from a run that would otherwise carry it;
  named excluded product -> 422. vitest: switch round-trips.
- AC-S5.6 [E2E] Toggle on `**NEW` from the product page, start a plan, `**NEW` absent.
- AC-S5.7 [FE][BE] The product form saves a product whose code contains `*` (AutoCount
  placeholder codes `**NEW`, `**SPARE PART`, `**REPLACE`, `**REPAIR`): the product code
  validation accepts `*` in both the frontend schema and any backend validator. Found by the
  browser walk, 9 Sep: without it the buyer cannot flip the exclusion on `**NEW` at all.

### S6 Confirm buys decided rows only

- AC-S6.1 [BE] `confirm_decisions` with `ids=[]` confirms every row holding a saved decision
  (`PlanRowDecision` / product decision with buy > 0) and NEVER sweeps undecided `buy` recs
  into PO lines. The R3 "untouched rows confirm as suggestion" blocks in both grains are
  removed. Order summary's confirm (same endpoint) inherits the rule.
- AC-S6.2 [FE] `confirmSummary` counts products with an explicit decision (drafted edit or
  persisted decision) and buy > 0; suggested-only rows are not counted. Zero -> button
  disabled, label "Confirm (0)".
- AC-S6.3 [FE] Decisions tile "N of M made" unchanged; Confirm tooltip when zero: "Decide at
  least one row first".
- AC-S6.4 [T] pytest: run with 3 buy recs, 1 decided: confirm creates exactly 1 PO line;
  run with none decided: confirm creates none and answers 200 with confirmed=0. vitest:
  confirmSummary excludes suggested-only rows.
- AC-S6.5 [E2E] Fresh plan, Confirm reads (0) disabled; decide one row (Use suggestion),
  Save, Confirm (1).

### S7 AutoCount level from retail deliveries only

- AC-S7.1 [BE] `scm.consumption_v` gains `warehouse_segment` (from `warehouses.segment`);
  `average_daily_usage` and `suggest_level_from_usage` inputs read only rows whose segment
  is `dealer` (G1 ruling). Health `movement_class` is unchanged (all deliveries).
- AC-S7.2 [BE] Level suggestion payload gains `basis.retail_only: true` and the FE terms line
  reads "ADU 1.911 / day (retail)".
- AC-S7.3 [T] pytest: product with 100 project-bin deliveries and 10 pool deliveries in the
  window: ADU uses 10. View migration is a `CREATE OR REPLACE` that appends the column only.

### S8 Product health carries a default decision

- AC-S8.1 [FE] Radio preselects from the health class when no decision is stored: `dead`
  -> Discontinue; `fast_moving`, `slow_moving`, `no_history` -> Keep selling. A stored
  decision always wins.
- AC-S8.2 [FE] The preselected value is a suggestion: it is sent on Save only for rows the
  buyer decided (any edit on that row), and on Confirm for every confirmed product (G4).
- AC-S8.3 [FE] Confirm's preceding plan-edits save carries the suggested lifecycle for every
  confirmable product (`withConfirmLifecycle`); no new backend path (S5, Phase 3 ruling -
  confirm already saves plan-edits before it confirms, and that save is where the
  suggestion is persisted, so a second write path for the same fact was never needed).
- AC-S8.4 [T] vitest: default mapping; `withConfirmLifecycle` carries the suggestion.

### S9 Order summary = the paper sheet

- AC-S9.1 [BE] `OrderSummaryRowOut` gains `delivery_by_month: [{month: "2026-09", qty}]`
  (open retail SO lines by `required_date` + project OI rows by `delivery_date`, undated
  under `month: null`), `project_customers: [{label, qty}]` (project OI rows grouped by
  customer/project title), `supplier_name` (chosen else suggested), `po_open_qty` (BRW pool
  open PO qty), `incoming_spo_qty`, `last_receipt: {date, qty}` (latest goods_received
  picking line for the product), `moq`. All frozen with the row at run time.
- AC-S9.2 [FE] Order summary grid adds columns Delivery (month groups rendered "Sep 30 -
  Oct 30", newest last), Project / customer (names, qty in brackets, truncated with title),
  Supplier, Remarks ("PO 400 + incoming 89 = 489", "Last in 21/07/2026 - 300", "MOQ 1000").
  Column order mirrors the sheet: Item, On hand, Project qty, Dealer o/s, Order qty,
  Delivery, Project/customer, Supplier, Remarks.
- AC-S9.3 [BE] `GET /order-summary/export?run_id=&format=pdf|xlsx` renders the same rows:
  PDF landscape A4 via `pdf_render`, Excel via an openpyxl workbook built directly in
  `summary_order_service` (Phase 3 ruling S2 - `xlsx_renderer`'s fixed multi-sheet register
  shape did not fit this flat nine-column sheet). Order qty column carries the chosen qty,
  blank when undecided (the pen column).
- AC-S9.4 [FE] Export button on the Order summary toolbar offers PDF and Excel, downloads
  through the existing file download helper, toast on failure.
- AC-S9.5 [T] pytest: report row for a fixture product shows two delivery months, one
  project customer, last receipt, MOQ; export endpoints return the right content types.
  vitest: Remarks cell composition.
- AC-S9.6 [E2E] Open Order summary from a plan, see Delivery and Remarks populated, export
  PDF, file lands.

### Cross-cutting

- AC-X.1 Usable at 375px and 1280px on every touched screen.
- AC-X.2 No new Playwright spec; agent-browser evidence run recorded per slice.
- AC-X.3 Every touched listing keeps `tableLayout` fixed + resizable columns.
