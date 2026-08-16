# PLAN - SCM plan screen: captain feedback round 2

**Status:** Planned 2026-08-15. Four PRs, built in parallel by coder subagents in separate
worktrees off main, each browser-verified with agent-browser and reviewed before its PR.
Captain merges. Contract: `UAC-scm-plan-feedback-r2.md` (same directory).

## Slices and PRs

| PR | Slice | UAC | Branch |
|----|-------|-----|--------|
| P1 | Presentation: money format, health wording, chart | AC-2, AC-5, AC-6 | `feat/scm-plan-feedback-r2` (also carries these docs) |
| P2 | Demand truth: row-scoped demand popover, customer + price on lines, Who-bought-it drill, SO import links customer + order date, honest labels | AC-1, AC-4 | `feat/scm-plan-demand-truth` |
| P3 | Cover sourcing: `cover_scope` knob, breakdown table, per-location editable Use stock | AC-3 | `feat/scm-plan-cover-scope` |
| P4 | Product primary photo on the plan row | AC-7 | `feat/scm-plan-product-photo` |
| P5 | Performance at ~10k decision rows (brief H): measure first, fix where the time goes | brief H | `feat/scm-plan-perf-10k` |

P1 is small and merges first. P2/P3/P4 are independent by intent; the shared files are
`PlanLinesGrid.tsx` (P4 sku cell, P2 nothing in the grid itself), `PlanTrendPopover.tsx`
(P1 chart + footer, P2 Who-bought-it expand + empty state) and `PlanDemandPopover.tsx` (P2
only). Whichever of P1/P2 lands second refreshes by merging main (no force-push on this
repo).

## Map (from the code, verified 2026-08-15)

- Demand popover: `PlanDemandPopover.tsx` -> `useRecommendationDemand` -> `GET
  /reorder-runs/{run}/recommendations/{rec}/demand` -> `demand_breakdown_service.
  demand_for_recommendation` (filters by POOL members always, plus unlocated when the row
  carries it). Netting: `reorder_run_service._plan_per_warehouse` groups by pool only when
  `policy.pool_netting`; `committed_v` groups per (product, warehouse). Unlocated demand lands
  on one row (`_apply_unlocated_demand`, `inputs.unlocated_demand`).
- Money: `scm/lib/format.ts` (`fmtMoney` 0dp with `RM`, `fmtSupplierCost` 2dp currency-aware).
  Bug at `PlanChecklistPopover.tsx` L56-59 (`fmtMoney` + currency suffix). Hand-rolled:
  `PoWorklistView.tsx` L288-289, `PlanMethodologySheet.tsx` L162-182.
- Cover: `cover_service.free_stock_by_product` / `propose_cover`; `GET
  /reorder-runs/{run}/cover-sources` keyed by product; FE `lib/coverPlan.ts` (`proposeCover`,
  `coverForLine`), `hooks/usePlanLines.ts` (`coverFor`, `takenByProduct`), decision shape
  `lib/planDecisions.ts` `PlanDecision.stock.sources[]`. Sentence built FE-side:
  `PlanLineDecisionCell.summary` + `coverPlan.describeCover`; ledger `PlanOrderQtyLedger.tsx`
  L464-481 (`ToggleLine`), the editable model to copy is `ForecastAddOnLine` L121-166.
  Policy: `app/models/scm.py` `ReorderPolicy` (`pool_netting` L79), FE
  `scm/policies/components/PlanningModePanel.tsx`.
- Health/trend: verdict is FE (`lib/productHealth.ts` `discontinueAdvice.consider`), strings
  in `PlanHealthCell.tsx` L97-101, L179-182; trend `PlanTrendPopover.tsx` (ApexCharts, height
  160, popover `w-96`), backend `trajectory_service` (`_CUSTOMERS_SQL` L77-105 with
  `COALESCE(c.customer_name, 'Unnamed customer')`, 24-month `order_date` window, top 5
  customers per (product, segment)).
- SO import: `outstanding_import_service._BINDINGS[SO]` (`party=None`, no `header_cols`);
  reader already yields `debtor_code` and `order_date`. History importer
  (`so_history_service`) links by debtor code and packs name/code into `internal_note`.
- Photo: `product_attachments.is_primary` + `dealer_kit/product_images.primary_image_urls`;
  chooser page `dealer-kit/brochure-images` (`set_brochure_image` flips `is_primary`).

## P1 - presentation (AC-2, AC-5, AC-6)

1. `PlanChecklistPopover`: `fmtSupplierCost(cost, rec.last_purchase_currency)`.
2. `PoWorklistView`, `PlanMethodologySheet`: route through `format.ts`; add the guard test.
3. `PlanHealthCell`: top line `Suggestion: {Discontinue|Keep selling|-}`; delete the two prose
   verdicts and the footer. `PlanTrendPopover`: delete the footer.
4. `PlanTrendPopover` chart: popover `w-[30rem] max-w-[92vw]`, height 240, `legend:
   {position:'top', horizontalAlign:'left'}`, `yaxis: {min:0, tickAmount:4, labels:{formatter:
   fmtInt}}`, x labels `rotate: -45, hideOverlappingLabels: true`.
Tests: existing component tests updated; snapshot-free assertions on the strings.

## P2 - demand truth (AC-1, AC-4)

Backend
1. `demand_for_recommendation`: scope = pool members only when the run's policy has
   `pool_netting`, else `[warehouse_id]`; unlocated as today; add `customer_label` and
   `unit_price` per line (join `customers`, `sales_order_lines.unit_price`); header gains
   `scope: 'warehouse' | 'pool'` and `pool_code`.
2. New `GET /reorder-runs/{run}/customer-orders?product_id&segment&customer_key` ->
   `{lines: [{so_number, order_date, qty, unit_price, warehouse_code}], total, shown}`,
   same window and join as `_CUSTOMERS_SQL`; `customer_key` is the customer id, or
   `debtor:<code>`, or `none`.
3. `trajectory_service._CUSTOMERS_SQL`: label = `COALESCE(c.customer_name, 'Debtor ' ||
   so.debtor_code, 'No customer on order')`, and emit `customer_key` per row.
4. Migration: `sales_orders.debtor_code VARCHAR(64) NULL` (+ index). Both SO importers write
   it. Outstanding-SO binding: `party=Customer, party_code_col="customer_code"` (link like the
   PO side), `header_fill_cols` gains `("order_date","order_date")`. Unresolvable debtor is NOT
   a row problem (the code is kept), stated in a comment and a test.
Frontend
5. `PlanDemandPopover`: header from `scope`/`pool_code`; line shows customer label + unit
   price.
6. `PlanTrendPopover`: Who-bought-it row is a disclosure; expanded, fetch customer-orders and
   render `SO | date | qty | price`, cap 20 + "N more". Empty state per AC-4.4 (needs the row's
   `outstanding_sales`, already on the line).
Tests: `test_demand_breakdown.py` (scope both modes, popover total == row committed, unlocated
carrier), new `test_customer_orders.py`, `test_outstanding_import` (customer linked, debtor
kept, order_date filled, unresolvable not a problem), vitest for both popovers.

## P3 - cover sourcing (AC-3)

Backend
1. Migration: `scm.reorder_policy.cover_scope VARCHAR(16) NOT NULL DEFAULT 'own_pool'`;
   `ensure_reorder_policy_defaults` + `load_policies` carry it; policy schema/API expose it.
2. `cover_service.propose_cover` / cover-sources: when the global policy says `own_pool`,
   filter sources to the row's pool. Because the endpoint is keyed by product, return each
   source with `pool_warehouse_id` and the run's `cover_scope`; the FE filters per row by the
   row's pool (the rec already carries `warehouse_id`; add `pool_warehouse_id` to the rec
   payload). Test both modes.
Frontend
3. `PlanningModePanel`: "Cover from" select (Own site only / Any location).
4. `lib/coverPlan.ts`: `coverForLine` filters by pool when `own_pool`; new pure helper
   `applySourceEdits(proposal, edits)` shared by ledger and Adjust mixture.
5. `PlanLineDecisionCell`: hover table component `CoverBreakdownTable` (location | use; Buy;
   total) replacing the `title` sentence; button label `Stock 1,442 + Buy 1,778`.
6. `PlanOrderQtyLedger`: COVER BEFORE BUYING becomes toggle + per-source rows with editable
   qty (pattern of `ForecastAddOnLine`), feeding buy qty and `PlanDecision.stock.sources`.
Tests: `coverPlan.test.ts` (scope filter, edits), `PlanOrderQtyLedger.test.tsx` (toggle, edit,
buy follows, decision carries sources), `PlanLineDecisionCell` table render, backend
`test_cover_from_stock.py` scope cases, policy round-trip.

## P4 - product photo (AC-7)

1. `GET /reorder-runs/{run}/product-images` -> `{images: {product_id: url}}` via
   `primary_image_urls` for the run's products, viewer-gated as that reader already is.
2. `PlanLinesGrid` sku cell: `ImageIcon` button (dimmed when absent) -> `ProductPhotoPopover`
   (photo, or empty state + link to `/dealer-kit/brochure-images`). Data via `usePlanLines`
   lazily (`enabled` on first open).
3. Brochure images page: one-line copy stating the chosen image is the product's primary photo
   across the CRM (no new surface).
Tests: backend endpoint (happy, denial, no-photo product absent), vitest popover states.

## P5 - performance at ~10k decisions (brief H)

Captain: a production plan of ~10,000 decision rows takes very long to load. Rule: measure
before guessing. Against the prod-copy DB, build or find a run with ~10k recommendations and
time, separately: (a) the run build itself (engine), (b) each request the plan page fires on
load (`/reorder-runs/{run}`, recommendations list, cover-sources, trajectory, product-
economics, price-history, purchase-trend, level-suggestions, po-book, decisions) - wall time,
payload bytes, SQL count via `statement` logging, (c) the browser: time to first row and to
interactive with 10k rows in `PlanLinesGrid` (is it virtualised or paginated?), React
re-render cost per decision. Fix the top offenders in this order of preference: pagination or
virtualisation of the grid + lazy per-page fetch of the heavy side payloads (trajectory /
economics / price-history are per product, fetch for the visible page, not the run), then
backend N+1 or missing indexes, then payload trimming. Record before/after in the PR body:
load time, bytes, request count at ~10k rows.

## Process per PR (binding)

- FE first against a stub (states: loading / empty / data / error), agent-browser screenshot,
  then backend test-first, then wire, then agent-browser pass on the real stack through the
  sidebar (SCM -> Reorder Planning). Reviewer pass before the PR. No em-dashes. Do not edit
  this PLAN's status line from the slice branches (the orchestrator updates it after merges).
