# PLAN - SCM M9 - Stock Allocation (inter-warehouse transfer)

> Status: DRAFT (2026-07-17). MODULE (scm), public schema. UAC:
> `scm-m9-stock-allocation-transfer-acceptance-criteria.md` (grilled, decisions locked). Guardrail:
> deterministic engine only, no LLM in the transfer maths. Builds on M3 + M8.

## Goal

Transfer-first rebalancing: cover a warehouse's shortage of a product from another warehouse's
genuine excess before buying, as a new deterministic pass over the existing engine outputs, surfaced
in the M8 "Stock allocation" view with accept/reject -> draft transfer order + linked buy reduction.

## Current state (verified)

- `reorder_engine.py`: `order_up_to(rop, demand_rate, review_days)` (S level); `network_recommend`
  builds `per_wh = [{warehouse_id, demand_rate, net}]` + `allocate(buy_qty, warehouses)` distributes a
  buy across warehouses (line 289/323); `disposition(...)` flags overstock when days-of-cover >
  `overstock_days` (line 350). So per-warehouse `net`, `order_up_to`, and the overstock signal all
  already exist per product.
- `scm.net_position_v` = per product x warehouse net. `reorder_recommendation` freezes per-rec
  `net_position`, `order_up_to`, `reorder_point`, warehouse.
- Decision overlay = `RecommendationOverride` + `decision_service` (accept/adjust/reject/confirm ->
  draft PO per supplier). `reorder_run_service` builds + freezes recs; confirm materializes draft POs.
- **No inter-warehouse transfer / stock-movement entity exists** (grep confirmed; only `SPOAllocation`,
  unrelated). So the draft transfer order is a thin NEW entity.
- FE M8: "Stock allocation" view = `DispositionResultsGrid` (read-only disposition rows today).

## Approach

### 1. Engine - allocation pass (deterministic, TDD golden-first)

Add a pure `allocate_transfers(products_with_per_wh_positions) -> list[Transfer]` in a new
`services/scm/transfer_allocation.py` (mirrors `cash_ranking.py` purity + golden tests):
- Input per product: `[{warehouse_id, net, order_up_to, is_overstock}]` (all already produced by the
  engine / freezable on the run).
- Sources = overstock AND `net > order_up_to`; movable = `net - order_up_to`. Destinations =
  `net < order_up_to`; shortfall = `order_up_to - net` (M9-E1/E2).
- Greedy fill: for each product, sort sources by movable desc, destinations by shortfall desc; fill
  each destination from sources, `qty = min(remaining source excess, remaining dest shortfall)`,
  never below target, whole units, multi-source split (M9-E3/E5).
- Emit `Transfer{product_id, source_wh, dest_wh, qty, dest_buy_rec_id, source_excess, dest_shortfall}`.
- Golden tests FIRST: single-source full cover, multi-source split, full-cover-drops-buy, source
  protected at target, no-self, no over-fill.

### 2. Run integration + buy reduction

- In `reorder_run_service.run_reorder`, after buy recs + dispositions are built, run
  `allocate_transfers` over the frozen per-warehouse positions; persist transfers (M9-D1) and
  reduce each linked destination buy rec's qty by the covered amount (M9-E4). Keep the ORIGINAL buy
  qty recorded (pre-transfer) for explainability; the plan shows the reduced qty.
- Persist transfers frozen on the run (new table, below).

### 3. Data model (one thin migration, chain onto committed head, single-head)

- `scm.reorder_transfer` (frozen suggestion): `id, run_id FK, product_id FK, source_warehouse_id FK,
  dest_warehouse_id FK, qty, source_excess, dest_shortfall, dest_recommendation_id FK, decision_status
  (suggested|accepted|rejected), created_at`. Normal cross-schema FKs into public.
- Draft transfer order on confirm: extend `reorder_transfer` with a `transfer_order_no` +
  `status(draft|...)` OR a sibling `scm.stock_transfer_order` if cleaner (decide during build;
  prefer the smallest thing that mirrors the draft-PO pattern). NOT a stock adjustment.

### 4. Decisions

- Extend `decision_service` / `decisions.py` with transfer accept/reject:
  `POST /reorder-transfers/{id}/accept|reject`, and fold accepted transfers into
  `confirm-decisions` so one confirm materializes both draft POs (buys) and draft transfer orders.
  Reuse the existing staged-decision + confirm pattern; do NOT build a parallel flow.

### 5. API

- `GET /reorder-runs/{id}/transfers` (list suggestions + status).
- `POST /reorder-transfers/{id}/accept|reject`.
- Confirm reuses `POST /reorder-runs/{id}/confirm-decisions` (now also materializes transfers).

### 6. FE (adjust existing, reuse)

- Stock allocation view: add transfer rows to the existing view (SKU, From, To, Qty, days-cover,
  reason) with inline Accept/Reject (M9-U1/U2). Reuse the M8 inline-decision pattern + SearchableSelect
  where needed; warehouse names not UUIDs (M9-U4).
- Buy view: linked buy line shows reduced qty + "N covered by transfer" note (M9-U3).
- New hook/service following the M8 patterns (`extractApiError`, no hand-rolled fetch).

## Risks / open questions

- **Where over-fill could sneak in**: a product with multiple destinations + one source - ensure the
  greedy loop decrements the shared source across destinations (don't double-spend excess).
- **Buy-reduction ordering**: transfers must be computed on the SAME frozen net the buy used, or the
  reduction double-counts. Compute transfers from the frozen per-wh net, then reduce buys - single
  pass, one source of truth.
- **Draft transfer order entity shape**: decide reuse-vs-new during build (search found none); keep it
  thin (no fulfilment lifecycle in v1).
- **Overstock ceiling per warehouse**: confirm the overstock signal is available per (product,
  warehouse), not only per network rec, before relying on it for source eligibility.

## Phasing (three-phase loop)

Phase 1: FE prototype of the transfer rows + accept/reject + buy-reduction note against mock
transfers (reuse the M8 Stock allocation view). Sign-off. Phase 2: engine `allocate_transfers`
(golden-first) + run integration + migration + decisions + API, FE off-mocks, tests
(pytest golden + endpoint, vitest, playwright). Phase 3: `/code-review`. Verify every M9 id
end-to-end in the browser before PR.
