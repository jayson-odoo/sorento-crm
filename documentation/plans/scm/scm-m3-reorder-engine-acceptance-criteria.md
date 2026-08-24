# UAC - SCM M3: Reorder Engine (the deterministic core)

> Given/When/Then contract for milestone M3. Parent umbrella: `scm-reorder-copilot-acceptance-criteria.md`.
> Depends on M0/M1/M2. Governs: `PRINCIPLES.md`. **TDD centerpiece - golden-set authored test-first.**

**Slug:** `scm-m3-reorder-engine` · **Domain:** scm · **Milestone:** M3 · **Status:** DRAFT (grilled, pre-code)

## Scope
The heart: turn M2's inputs into reorder decisions - *when* (trigger) and *how much* (qty), driven by
the `reorder_policy` ruleset, per a `reorder_run`. Produces `reorder_recommendation` rows (buy +
disposition). **No cash ranking (M4), no Accept/Adjust interaction (M4), no LLM prose (M5).** All
deterministic; golden-set testable.

## Locked decisions (from M3 grill)

| # | Decision |
|---|---|
| M3-D1 | **Computation chain** per SKU×warehouse: resolve policy (SKU → ABC/XYZ cell → product_class → global; most-specific **active** wins, tiebreak `policy.priority`) → select supplier → lead_time (measured M2 → declared `product_suppliers` → policy default) → demand (M2 `demand_stat`, projected = baseline + committed spike) → SS (method per policy) → ROP → trigger → qty → round. |
| M3-D2 | **SS default `fixed_days`; per-product toggle via a SKU-scoped policy** (`statistical`/`manual`). `statistical` = `Z(service_level)·√(LT·σ_d² + d²·σ_LT²)` using σ_d (demand_cv) + σ_LT (lead_time_variance) from M2. `fixed_days` = `demand_rate·safety_days`. |
| M3-D3 | **Supplier selection:** `is_primary` → (none) best `composite_score` → (tiebreak) lowest `unit_cost`. Single supplier → use it. **No supplier → flagged exception** (no silent skip). Policy toggle `supplier_selection` = `primary`\|`best_score`\|`lowest_cost` (default `primary`). **Ranked alternatives attached** (cost/lead/score) for human override at M4. Chosen supplier's measured lead-time + cost drive ROP/SS/qty. |
| M3-D4 | **`buy_scope=network`:** aggregate demand+position across selected warehouses → one buy qty → **auto-allocate** per warehouse (each warehouse's deficit first; rounding surplus split **velocity-proportional**) as an **editable suggested breakdown**. `buy_scope=warehouse`: per-warehouse independent. |
| M3-D5 | **Two recommendation types.** `buy` (triggered) - `reorder_point`: `net ≤ ROP`; `periodic_review`: on cadence if `net < order_up_to`; `min_max`: `net ≤ min`. `disposition` (not a buy) - `dead` (no movement > `dead_stock_days`) → discontinue/promo; `overstock` (DoC > `overstock_days`) → hold/promo + **advisory transfer flag** (overstock-here + short-there → "consider transfer X"; **buy qty unchanged**, netting deferred). Run evaluates ALL planning SKUs; buy recs for triggered only. |
| M3-D6 | **Background-job run** on the RQ worker. `reorder_run.status` = running/completed/failed + run log. **UI shows live running→complete feedback**; on completion a **summary + next-step CTA** ("N SKUs need reorder → Review"). |
| M3-D7 | **Confidence band** = deterministic `(xyz_class × data_sufficiency) → high|medium|low`. A/X + adequate samples → high; C/Z or thin demand/supplier samples → low. Stored on the recommendation; gates human scrutiny. |
| M3-D8 | **Recommendation freezes its inputs** (forecast_daily_demand, ROP, SS, net_position, lead_time, supplier_id, policy_ref, allocation breakdown, triggered_reason, confidence) → reproducible without stat versioning. |
| M3-D9 | **M3 UI = read-only.** "Run planning" action + read-only results grid (buy + disposition: qty, allocation breakdown, ROP, net, reason, confidence, selected supplier + alternatives). Accept/Adjust/Dismiss + cash = **M4**; LLM prose = **M5**. |
| M3-D10 | **Golden-set blessed here** - the M0 fixture SKUs' expected ROP/SS/qty/allocation are authored as **failing tests FIRST**, engine built to green. TDD centerpiece. |

## Acceptance criteria

### Engine correctness (golden-set - authored test-first)
- **AC-M3.1** GIVEN the golden-set fixtures (one per ABC/XYZ cell, one multi-warehouse, one stockout, one dead, one open-PO) WHEN the engine runs THEN ROP/SS/qty/allocation equal the hand-computed blessed numbers. Any formula change moving a golden number fails CI until re-blessed.
- **AC-M3.2** GIVEN a `reorder_policy` change (service_level / SS method / trigger / window / safety_days) WHEN the run reruns THEN output changes with **no code change**; resolution picks the most-specific active policy (SKU > ABC/XYZ > class > global), priority breaking ties.
- **AC-M3.3** GIVEN a computed qty WHEN rounded THEN it respects `order_multiple` and floors at `moq`; order-up-to = `ROP + demand_rate·review_period`.
- **AC-M3.4** GIVEN measured supplier lead-time/variance (M2) WHEN ROP/SS compute THEN measured overrides declared; where no measurement, declared → policy default, and the fallback used is recorded.

### Supplier selection
- **AC-M3.5** GIVEN a SKU with multiple suppliers WHEN selected THEN precedence = is_primary → best composite_score → lowest cost (per `supplier_selection` toggle); the chosen supplier's lead-time + cost drive the maths; ranked alternatives are attached.
- **AC-M3.6** GIVEN a SKU with no linked supplier WHEN evaluated THEN a flagged exception is produced (not silently skipped).

### Trigger, allocation, disposition
- **AC-M3.7** GIVEN each trigger type WHEN evaluated THEN reorder_point fires on `net ≤ ROP`, periodic_review on cadence when `net < order_up_to`, min_max on `net ≤ min`; `triggered_reason` set correctly.
- **AC-M3.8** GIVEN `buy_scope=network` WHEN a buy qty is computed THEN it aggregates across selected warehouses and auto-allocates (deficit-first + velocity-proportional surplus) into a per-warehouse breakdown summing to the buy qty.
- **AC-M3.9** GIVEN a dead SKU or an overstock SKU WHEN evaluated THEN a `disposition` recommendation is produced (discontinue/promo), and an **advisory transfer flag** appears when the same SKU is overstocked in one warehouse and short in another - **buy qty unchanged**.

### Run / feedback / reproducibility
- **AC-M3.10** GIVEN a "Run planning" action WHEN triggered THEN a background job runs, `reorder_run.status` transitions running→completed, the UI reflects progress live, and on completion shows a summary + next-step CTA.
- **AC-M3.11** GIVEN a completed run WHEN a recommendation is inspected THEN it carries frozen inputs (demand/ROP/SS/net/lead_time/supplier/policy_ref/allocation/confidence) reproducing the decision.
- **AC-M3.12** GIVEN confidence WHEN computed THEN it deterministically follows `(xyz × data_sufficiency)`; low-confidence recs are visibly flagged for scrutiny.

### Conventions
- **AC-M3.13** No LLM anywhere in M3 (pure maths); reads canonical `public` + M2 stats only (decoupling). Read-only UI: DataGrid standards, no UUIDs, SearchableSelect, extractApiError.
- **AC-M3.14 (verify)** Playwright: sidebar → SCM → Run planning → watch running→complete → open read-only results → assert buy + disposition recs + allocation breakdown + `/api/v1/*` calls, at 375px + 1280px.

## Tests (test-first - TDD; golden-set authored BEFORE the engine)
- **pytest golden-set (centerpiece):** ROP/SS/qty/allocation per fixture SKU; policy-resolution precedence + tiebreak; policy-change-alters-output; rounding/MoQ; measured-vs-declared lead time; supplier precedence + no-supplier exception; each trigger type; network aggregation+allocation; disposition + transfer flag; confidence map.
- **pytest run:** background job status transitions, run log, reproducible frozen inputs, auth.
- **vitest:** results grid states, run-status/progress feedback, completion CTA, confidence badge, alternatives display.
- **playwright:** AC-M3.14.

## Deferred
Cash-constraint ranking + Accept/Adjust/Dismiss + override capture (M4); LLM explanation + market
advisory (M5); transfer **netting** (reduces buy qty) + multi-echelon allocation optimization (later).
