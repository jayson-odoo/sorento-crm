# UAC - SCM Reorder Co-Pilot (Supply Chain & Inventory Optimisation Module)

> Independently-verifiable Given/When/Then contract. Phase-2 test report keys back to these ids
> (PASS/FAIL/DEFERRED). No plan ships without this file. Governs: `PRINCIPLES.md` >
> `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `scm-reorder-copilot`
**Domain:** scm
**Type:** New installable **MODULE** (per-tenant) - canonical demand/supply model + deterministic reorder engine + cash-constrained co-pilot + LLM semantic layer
**Status:** DRAFT (grilled, pre-code)
**Classification:** **MODULE** - installable per tenant via `app_modules_catalog` + `tenant_modules` + `require_module_enabled_with_api_key("scm")`. **Schema split by uninstall lifecycle:** core business records (SO/PO/GR/product_suppliers ext) in **`public`**; reorder brain (policy/run/recommendation/override/classification/supplier_perf/budget/market) in a dedicated **`scm`** schema with **cross-schema FKs** into `public` core (Postgres-native - NOT the old no-FK `foundryx_*` isolation, that doctrine was corrected; see memory `project_core_vs_module_schema`). Uninstall = drop `scm` schema, records survive. Source-decoupling via read-model **views** + `source_system`/`source_ref` columns.
**Timeline:** Day 2 → this UAC + PLAN for internal team discussion. Day 4 → live demo on **real prod data**, module deployed **dormant** (zero UX change for existing users).

---

## Problem

AutoCount's naive min/max reorder logic ignores cash, lead-time reality, committed demand, supplier
reliability, and market conditions. Purchasing computes optimum buys in their heads. We build a
**decision-support co-pilot** (NOT autopilot): it drafts cash-aware, judgment-augmented reorder
recommendations; a human accepts/adjusts/rejects with a reason; the reason trains future
suggestions. The platform **never raises a PO** - it drafts; a human confirms.

## The one principle that makes this a module, not a throwaway demo

**The SCM engine reads canonical tables/views, never a source-specific shape.** AutoCount is
deferred but the contract is designed now. Every new table carries `source_system`
(`manual`|`seed`|`autocount`) + `source_ref`. The engine queries **views**, so the physical source
can swap beneath it. No source-specific field name leaks into the core.

## Locked decisions (from grill)

| # | Decision |
|---|---|
| D1 | **Bind to existing canonical tables** (not a parallel seed schema). Reads flow through **read-model views** for source-decoupling. New tables ONLY for what genuinely doesn't exist. |
| D2 | `orders`/`order_lines` = **Delivery Orders (DO)**, not SO. Build **new `sales_order`/`sales_order_line`**. `order_type` is **lookup-bound** (configurable via `lookup_sets`, no enum). SO carries `priority`; line carries `qty_ordered`+`qty_delivered`. **No historical DO↔SO matcher.** Provide **"create DO from SO"** function (soft link, stamps `qty_delivered`; no hard FK constraint). |
| D3 | **Demand is bimodal.** `demand_nature` = `continuous`\|`spike`, **derived from `order_type` via a configurable mapping**. Projection is **policy-configurable**: `baseline_source` (`continuous_only`\|`all`), `spike_handling` (`committed_only`\|`statistical`\|`ignore`). Default: baseline on continuous + spike via committed_only. **Actual consumption** = realized DO/`stock_ledger` outflow; **committed** = open SO. Streams never overlap → no double-count. |
| D4 | Build **new `purchase_order`/`purchase_order_line`**. `on_order = Σ(qty_ordered − qty_received)` on open PO lines. **GR = existing `picking_headers` where `picking_type='goods_received'`** - reuse, don't rebuild. Link GR→PO via header `source_entity_type='purchase_order'`/`source_entity_id` + soft `picking_lines.po_line_id`. Provide **"create GR from PO"** function (stamps `qty_received`). `inbound_shipments`, `spo_number`, `spo_allocations`, packing list are **OUT of this flow**. |
| D5 | **Actual lead time** = `gr.receipt_date − po.issue_date` per line (overrides declared once enough samples). **Quality** = from `picking_lines.picked_condition` + `quantity_discrepancy` + `picking_headers.inspection_status`, plus explicit `qty_accepted`/`qty_rejected`. |
| D6 | **Supplier performance = stored snapshot** (`supplier_performance`), **supplier×product grain**, `computed_at`. Metrics: `on_time_delivery_rate`, `avg_lead_time_days`, `lead_time_variance`, `reject_rate`, `fill_rate`, `sample_size`. Denormalized `suppliers.current_performance_score`. Snapshot runs **both** nightly (scheduler) **and** on GR posting. **Configurable `supplier_scoring_policy`** (delivery vs quality weighting). Fall back to supplier-level when SKU `sample_size < N`. |
| D7 | **Extend `product_suppliers`**: add `moq`, `order_multiple`, `unit_cost`, `currency`, `is_primary_supplier`, `lead_time_variability_days`. |
| D8 | **`reorder_policy` = L2 config.** Toggle+weight factors **and** method choice per scope: `safety_stock_method` (`statistical`\|`fixed_days`\|`manual`), `policy_type`/trigger (`reorder_point`\|`periodic_review`\|`min_max`), `service_level`, `forecast_window_days`, baseline/spike handling, `dead_stock_days`. **Resolution:** SKU → ABC/XYZ cell → product_class → global; most-specific active policy wins. Policy change alters output with **no code change**. |
| D9 | **Factor split.** Hard-math factors (stock movement, supplier perf, MoQ, cost, urgency, priority) are **deterministic formula inputs**. Soft factors (market condition, economic) are **advisory-only annotations** - surfaced to the human, **never touch a computed number**. |
| D10 | **Core formulas (deterministic).** `net_position = on_hand + on_order − committed`. `avg_daily_demand = channel-adjusted outflow / window`. `SS`: statistical `Z×√(LT×σ_d² + d²×σ_LT²)`, or fixed_days, or manual. Trigger per policy. Qty = order-up-to − net_position, then **round to `order_multiple`, floor `moq`**. |
| D11 | **`reorder_run`** is first-class: `warehouse_ids[]` (**selected per run**), `buy_scope` (`network`\|`warehouse`), `budget_id`, `policy_snapshot_ref`, `status`. `network` aggregates demand+position for one buy qty; `warehouse` computes per warehouse. Recommendations FK `run_id`. |
| D12 | **Cash constraint.** `purchasing_budget` keyed by period, optional per-supplier/category override, or ad-hoc per run. When `Σ cash_impact > budget`: rank by a **configurable weighted score** (urgency/days-of-cover, margin, ABC, SO `priority`, committed-vs-forecast; default urgency×margin). Non-fitting items shown **deferred with visible stockout risk** - never silently dropped. |
| D13 | **Feedback loop = L1 suggest-only.** `override_reason` master vocabulary. **LLM classifies** `reason_text`→`reason_code` (schema-forced structured output + confidence; human can correct). `reason_code → suggested_action` is a **deterministic** map. Human applies. **Engine never self-writes policy.** `recommendation_override` is append-only; it never mutates the recommendation row. |
| D14 | **Market research** = **backend web-search service** (no n8n). Configurable `market_research_topic` table → writes structured `market_signal` rows (topic/category/currency/value/trend/summary/source_url/captured_at), **visualized in UI**; LLM condenses to a short advisory on the recommendation. Runs via **scheduled task + manual**. Advisory-only. Backend web-search capability is a **build dependency**. |
| D15 | **LLM boundary (hard).** LLM does exactly four things: (1) recommendation explanation prose, (2) `reason_text` classification, (3) NL Q&A on displayed numbers, (4) market advisory prose. It is **given** computed numbers as input and has **no tool/path** to compute or alter any number. **No code path feeds LLM output into a quantity/ROP/SS field.** |
| D16 | **ABC/XYZ** stored in `item_classification` (ABC by annual value, XYZ by demand CV; continuous≈X, spike≈Z). Gates **confidence**, not the maths. |
| D17 | **Forecast = transparent moving average** (weighted MA option). **NOT** ARIMA/Prophet. Historical censored-demand reconstruction **deferred**; forward unmet-demand capture is fast-follow. |
| D18 | **UI in-platform** (Next.js/Metronic/DataGrid; hooks→service→api-client). Purpose-built SCM dashboard. **Drag-drop BI builder DEFERRED** to its own track (separate client requirement; embed-vs-build-vs-buy decision not coupled here). |

## Milestones (each independently demoable; M0 - M5 = the 4-day demo)

| M | Deliverable |
|---|---|
| M0 | Schema (SO/PO/GR-link/policy/recommendation/override/supplier_perf/market_signal/budget/classification) + views + `source_system`/`source_ref` + module registration (dormant) |
| M1 | Net-position dashboard on real data (on-hand/on-order/committed/net/DoC/cash-tied-up per warehouse) |
| M2 | Demand model (continuous/spike, projected) + ABC/XYZ + `supplier_performance` snapshot |
| M3 | Reorder engine: trigger + qty + `reorder_policy` L2 resolution + `reorder_run` (warehouse select, buy_scope) |
| M4 | Cash constraint ranking + recommendation view + Accept/Adjust/Dismiss + override capture + reason→LLM-classify→suggested-action |
| M5 | LLM explanation per recommendation + market_signal advisory (backend web search, scheduled + manual) |
| Later | AutoCount ETL into same tables; historical censored-demand reconstruction; full statistical SS; drag-drop BI builder |

---

## Acceptance criteria

### AC-M0 - Foundation & decoupling
- **AC-M0.1** GIVEN the module is registered WHEN a tenant has SCM disabled THEN no SCM route/UI is reachable and **existing users see zero UX change**.
- **AC-M0.2** GIVEN new SCM tables WHEN inspected THEN each carries `source_system` + `source_ref` (nullable now).
- **AC-M0.3** GIVEN the engine WHEN it reads demand/supply/position THEN it queries **views** (`scm_net_position_v` etc.), never source-specific raw shapes. A **decoupling test** fails if the core imports/queries an AutoCount-shaped or legacy inbound/spo table.
- **AC-M0.4** GIVEN a migration WHEN applied on a copy of prod THEN it is single-head, reversible, and chains onto a committed main head.

### AC-M1 - Net position (the number everything hangs off)
- **AC-M1.1** GIVEN on-hand, open PO lines, open SO lines for a SKU/warehouse WHEN the dashboard renders THEN `net_position = on_hand + on_order − committed` with `on_order = Σ(qty_ordered−qty_received)` (open PO) and `committed = Σ(qty_ordered−qty_delivered)` (open SO).
- **AC-M1.2** GIVEN a SKU with an open PO WHEN net position is computed THEN the in-transit qty is included (no double-order).
- **AC-M1.3** GIVEN the dashboard WHEN filtered by warehouse/class/supplier/ABC-XYZ THEN every row shows on-hand, on-order, committed, net, avg-daily-demand, days-of-cover, ROP, status (OK/reorder-due/stockout/dead), cash-tied-up, last-movement. Every section renders even when empty (CRUD UX standard).

### AC-M2 - Demand, classification, supplier performance
- **AC-M2.1** GIVEN a configurable `order_type→demand_nature` mapping WHEN a policy sets `baseline_source=continuous_only` THEN the statistical baseline excludes spike history and committed spike SO is added on top - asserted to **not double-count** a project order present in both history and committed.
- **AC-M2.2** GIVEN outflow history WHEN `avg_daily_demand` is computed THEN it uses the policy's moving-average window (not ARIMA/Prophet) and is reproducible.
- **AC-M2.3** GIVEN a SKU WHEN classified THEN `item_classification` holds ABC (annual value) × XYZ (demand CV) with `computed_at`.
- **AC-M2.4** GIVEN PO + GR history for a supplier×product WHEN the snapshot runs (nightly AND on GR posting) THEN `supplier_performance` holds on_time_rate, avg_lead_time, lead_time_variance, reject_rate, fill_rate, sample_size; supplier-level fallback applies when `sample_size < N`.
- **AC-M2.5** GIVEN `supplier_scoring_policy` weights change WHEN the composite score recomputes THEN the score changes accordingly with no code change.

### AC-M3 - Reorder engine
- **AC-M3.1** GIVEN a golden-set SKU with hand-computed ROP/SS/net/qty WHEN the engine runs THEN output equals the blessed numbers (CI golden-set; any formula change that moves a number fails until re-blessed).
- **AC-M3.2** GIVEN a `reorder_policy` change (service_level / SS method / window / trigger) WHEN the engine reruns THEN output changes with **no code change**, and resolution picks the most-specific active policy (SKU → ABC/XYZ → class → global).
- **AC-M3.3** GIVEN a computed qty WHEN rounded THEN it respects `order_multiple` and floors at `moq`.
- **AC-M3.4** GIVEN a `reorder_run` with `buy_scope=network` and N selected warehouses WHEN it runs THEN demand+position aggregate to one buy qty; with `buy_scope=warehouse` THEN per-warehouse qty. Recommendations FK the `run_id`.
- **AC-M3.5** GIVEN measured supplier lead-time/variance WHEN ROP/SS compute THEN measured values override declared `standard_lead_time_days`.

### AC-M4 - Cash constraint & co-pilot loop
- **AC-M4.1** GIVEN `Σ cash_impact > budget` WHEN ranked THEN the configurable weighted score orders survivors; funded items accepted-eligible, unfunded shown **deferred with stockout risk** (never dropped).
- **AC-M4.2** GIVEN a recommendation WHEN the user picks Accept/Adjust/Dismiss THEN status updates; **Adjust** opens override capture.
- **AC-M4.3** GIVEN an override WHEN saved THEN a linked `recommendation_override` row is written and the original recommendation row is **never mutated** (override-integrity test).
- **AC-M4.4** GIVEN free-text override reason WHEN classified THEN the LLM maps it to a `reason_code` from the master vocabulary with confidence; the user can correct the code; a **deterministic** `suggested_action` is surfaced.
- **AC-M4.5** GIVEN a surfaced suggested action WHEN the user clicks Apply THEN the policy change is applied by the human's action; the engine never self-writes policy.
- **AC-M4.6** GIVEN Unlink/Dismiss/Delete on any SCM entity WHEN triggered THEN an `AlertDialog` confirm precedes it (never one-click; per feedback doctrine).

### AC-M5 - Semantic layer & market advisory
- **AC-M5.1** GIVEN a computed recommendation WHEN explained THEN the LLM prose reflects the numbers unchanged; a test asserts the displayed qty/ROP/SS equal the engine's (no LLM drift).
- **AC-M5.2** GIVEN configurable `market_research_topic` rows WHEN the scheduled task or a manual run executes THEN backend web-search writes `market_signal` rows (visualized) and the recommendation shows a short advisory annotation.
- **AC-M5.3** GIVEN any code path WHEN traced THEN **no LLM output feeds a quantity/ROP/SS field** (LLM-boundary test).

### AC-cross - Conventions
- **AC-X.1** All DataGrid listings use `tableLayout:{width:'fixed',columnsResizable:true}`, explicit `size`, truncate+title; dropdowns use `SearchableSelect`/`SearchableMultiSelect`; **no UUIDs shown in UI** (resolve to human-readable).
- **AC-X.2** FE uses `extractApiError` + `buildDataGridParams`; hooks→service→api-client layering; BE raises `AppException`.
- **AC-X.3** Delete = hard delete + confirm; retention (if any) = separate Archive action.
- **AC-X.4** Verified end-to-end in a real browser via Playwright (sidebar → SCM → run → recommendation → accept/override), console clean, correct `/api/v1/*` calls.

## Test strategy
- **Golden-set fixtures** in git: a dozen representative SKUs (one per ABC/XYZ cell, one multi-warehouse, one stockout, one dead, one with open PO), hand-computed expected ROP/SS/net/qty; asserted in CI.
- **Decoupling test:** fails if the core queries a legacy inbound/spo/AutoCount-shaped table.
- **Double-count test:** a project order present in both history and committed is not counted twice.
- **Override-integrity test:** an override never mutates the original recommendation.
- **LLM-boundary test:** no LLM output reaches a numeric field.

## Explicitly deferred (architecturally not precluded)
AutoCount integration (ETL into same tables); project/dealer registration modules (SO stands in);
auto-execution of POs (**hard rule - never**); historical censored-demand reconstruction; full
statistical SS where clean σ is absent; multi-echelon/inter-warehouse transfer optimisation;
drag-drop BI builder.
