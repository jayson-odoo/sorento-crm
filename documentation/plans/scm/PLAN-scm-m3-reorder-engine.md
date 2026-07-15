# PLAN — SCM M3: Reorder Engine

**Slug:** `scm-m3-reorder-engine` · **Milestone:** M3 · **UAC:** `scm-m3-reorder-engine-acceptance-criteria.md`
**Umbrella:** `PLAN-scm-reorder-copilot.md` · **Depends:** M0/M1/M2 · **Status:** DRAFT (grilled, pre-code)
**Type:** BE engine (deterministic, TDD golden-set) + background run + read-only results UI

## Goal
The deterministic reorder core: policy-resolved trigger + quantity per SKU×warehouse, network
aggregation + auto-allocation, supplier selection, buy + disposition recommendations — all reproducible
and golden-tested. Read-only surfacing; interaction lands in M4.

## 1. Engine service (test-first — golden-set FIRST)
`app/services/scm/reorder_engine.py`, pure functions (no I/O in the maths → unit-testable):
```
resolve_policy(sku, wh)            # SKU → abc/xyz cell → class → global ; active ; priority tiebreak
select_supplier(sku, policy)       # is_primary → best_score → lowest_cost ; alternatives[] ; no-supplier exception
lead_time(sku, supplier)           # measured(M2) → declared → policy default   (records source)
safety_stock(policy, demand, σ_d, σ_LT, LT)   # statistical | fixed_days | manual
reorder_point(demand, LT, SS)      # demand·LT + SS
trigger(policy, net, ROP, min, review)         # reorder_point | periodic_review | min_max → triggered_reason
order_qty(policy, net, ROP, demand)            # order_up_to − net ; round(order_multiple, floor moq)
confidence(xyz, sample_adequacy)   # → high|medium|low
```
Inputs come from M2 (`demand_stat`, `item_classification`, `supplier_performance`) + M1 views
(`scm_net_position_v`, per-warehouse position). Maths take plain values → golden-testable in isolation.

## 2. Network aggregation + allocation
- `buy_scope=network`: sum demand + net position across selected warehouses → one buy qty (ROP/SS on the aggregate). **Auto-allocate**: each warehouse gets its deficit (`ROP_i − net_i`, floored 0); rounding surplus (buy_qty − Σdeficit) split **velocity-proportional** (by each warehouse's demand_rate); store `allocation` jsonb breakdown (editable in M4).
- `buy_scope=warehouse`: independent per-warehouse ROP/qty; no aggregation.

## 3. Disposition + transfer flag
- `dead` (last-movement > `dead_stock_days`) → `disposition` rec, action discontinue/promo.
- `overstock` (DoC > `overstock_days`) → `disposition` rec, action hold/promo; **advisory transfer flag** when the same SKU is overstock in warehouse A and short (net<ROP) in B → attach "consider transfer X A→B"; **buy qty unchanged**.

## 4. reorder_run (background job)
- `POST /api/v1/scm/reorder-runs` (warehouse_ids, buy_scope, budget_id[M4], policy snapshot) → enqueue RQ job → returns run_id, status=running.
- Worker task `run_reorder(run_id)`: evaluate all planning SKUs in the selected warehouses, write `reorder_recommendation` rows (frozen inputs), set status=completed + run-log counts. **Restart worker after task edits** (dev-session rule); `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` on macOS.
- `GET /api/v1/scm/reorder-runs/{id}` → status + summary (counts: buy, disposition, exceptions, total cash impact).
- `GET /api/v1/scm/reorder-runs/{id}/recommendations` → paginated results (DataGrid).

## 5. FE — read-only run + results (Phase 1 prototype → Phase 2 wire)
- **Run planning** action (modal: warehouse multi-select, buy_scope; budget picker greyed until M4).
- **Live feedback:** poll `reorder-runs/{id}` → progress state (running spinner + stage) → on complete, summary card + **CTA "Review N recommendations"**.
- **Results grid** (read-only): type (buy/disposition), SKU, warehouse (or "network" + expandable allocation), qty, ROP, net, days-of-cover, triggered_reason, confidence badge, selected supplier + alternatives popover. Disposition rows show action + transfer flag. Reuse DataGrid + stat tiles + SearchableSelect.
- No Accept/Adjust/Dismiss yet (M4).

## 6. Tests (TDD — golden-set authored before the engine)
- **pytest golden-set (write FIRST, watch red):** the M0 fixtures blessed here — ROP/SS/qty/allocation per SKU (AC-M3.1); policy resolution + tiebreak + change-alters-output (AC-M3.2); rounding/MoQ (AC-M3.3); lead-time precedence (AC-M3.4); supplier precedence + no-supplier (AC-M3.5/3.6); triggers (AC-M3.7); network aggregation+allocation (AC-M3.8); disposition + transfer flag (AC-M3.9); confidence map (AC-M3.12).
- **pytest run:** background status transitions, run log, frozen-input reproducibility (AC-M3.10/3.11), auth.
- **vitest:** results states, run-progress feedback, completion CTA, confidence badge, alternatives.
- **playwright:** AC-M3.14 full flow.

## 7. Risks
- **Golden-set discipline** — numbers authored + hand-verified before code, else TDD is theatre. Re-bless only deliberately.
- **σ availability** — statistical SS needs σ_d + σ_LT; where M2 sample is thin, fall back to fixed_days automatically + record it (don't emit a bogus statistical SS).
- **Allocation edge** — buy qty < Σdeficit (budget/MoQ interplay is M4) → allocate proportional to deficit; buy qty > Σdeficit → velocity surplus. Cover both in golden tests.
- **Big-catalog run time** — batch evaluation, reuse M2 indexes; run log captures duration.
- **No-overfit** — engine keyed on data + policy, never tuned to a specific SKU/scenario.
