# PLAN — SCM M2: Demand, ABC/XYZ, Supplier Performance

**Slug:** `scm-m2-demand-classification-supplier-perf` · **Milestone:** M2
**UAC:** `scm-m2-demand-classification-supplier-perf-acceptance-criteria.md` · **Umbrella:** `PLAN-scm-reorder-copilot.md`
**Depends:** M0, M1 · **Status:** BE ENGINE BUILT (Phase-2 checkpoint; FE binding pending) · **Type:** BE-heavy (analytics job) + M1 column light-up

## Implementation notes (M2 engine — checkpoint)
Deterministic engine in `app/services/scm/analytics_service.py` (+ route
`app/api/v1/scm/analytics.py`, gated `scm.reorder.run` to run / `scm.dashboard.view` to
read). Golden set blessed in `tests/scm/fixtures/golden_m2.json`, derived independently
by `scripts/scm_m2_golden_derive.py` over the REAL prod-copy DO outflow. Resolved
ambiguities in the locked decisions:
- **Window bucketing:** 90-day window = **three trailing 30-day buckets** ending at a
  configurable `as_of` (default today; tests pin `2026-06-01`). Equal-length buckets
  avoid partial-calendar-month bias and keep `avg_daily = baseline_total / 90`
  dimensionally exact. With n=3 the "drop top+bottom 10%" trim removes 0 periods, so a
  high-CV SKU's numeric baseline == plain sum (branch label still records
  `trimmed_mean`); the robust trim is proven meaningful in a pure-function unit test on
  a 12-period spiky series (AC-M2.2). CV = population σ/µ over the 3 bucket totals.
- **Demand source:** reads `scm.consumption_v` (DO `order_lines`⋈`orders`), NOT
  `stock_ledger` (snapshot-only) — supersedes plan §2.1's stock_ledger mention.
- **Channel coverage on real data:** only ~8 customers are segment-tagged, so ~84% of
  window outflow is untagged→continuous. Coverage % is logged per run in
  `scm_analytics_run.counts.channel_coverage_pct`.
- **ABC policy convention:** canonical = CUMULATIVE percent cut points (A≤80, B≤95).
  The engine also normalises the legacy M0-seed fraction/band convention
  (`abc_a_pct=0.80`, `abc_b_pct=0.15`) on read so existing rows classify correctly; the
  M0 seed script is updated to the canonical 80/95. Null-cost SKUs → `abc_class` NULL.
- **Supplier weights:** locked 0.5/0.5 (M0 seed updated from 0.6/0.4). Golden supplier
  tests pin the scoring policy so blessed composites are deterministic regardless of the
  ambient row.
- **On-GR hook** = `refresh_supplier_performance(supplier_id, product_id)` (scoped, no
  full-catalog scan). The **scheduled** trigger + FE column light-up are the NEXT slice.

## Goal
Produce the engine's inputs — a transparent, channel-separated demand rate; ABC/XYZ; a supplier
scorecard — all deterministic, observable, and reproducible. Light up the deferred M1 columns.

## 1. Schema additions
- **`market_segments`** (existing, `access.py`) + `demand_nature` (`continuous`|`spike`, nullable→default continuous).
- **`customers`** + `market_segment_code` FK → `market_segments.code`.
- **`reorder_policy`** + `overstock_days` (for overstock state).
- **`scm.demand_stat`** (SKU×warehouse): avg_daily_demand, baseline_rate, spike_rate, demand_cv, window_days, sample_days, method, channel_split jsonb, computed_at.
- **`scm.item_classification`** (SKU×warehouse): abc_class, xyz_class, annual_value, demand_cv, computed_at (+ network rollup view).
- **`scm.abc_xyz_policy`**: abc_a_pct, abc_b_pct, xyz_x_max, xyz_y_max, is_active.
- **`scm.supplier_scoring_policy`**: delivery_weight, quality_weight, grace_days, min_sample_size, is_active.
- **`scm.supplier_performance`** (supplier×product): on_time_rate, avg_lead_time_days, lead_time_variance, reject_rate, fill_rate, composite_score, sample_size, confidence, period_start/end, computed_at. + `suppliers.current_performance_score` denorm (M0).
- **`scm.scm_analytics_run`**: started_at, finished_at, status, scope jsonb, counts jsonb, window_days, config_ref, error_text.

## 2. The analytics service (deterministic; test-first)
`app/services/scm/analytics_service.py` — one entry `run_analytics(scope, config)`:
1. **Demand** — per SKU×warehouse: read sales outflow (`stock_ledger`, `reference_type` in DO set), bucket per period, join DO→customer→market_segment→demand_nature to split continuous vs spike; compute baseline MA (robust/trimmed if CV high; weighted if policy), spike series, CV. Upsert `demand_stat`.
2. **Classification** — annual value (Σ qty×cost) → ABC by cumulative cut points; CV → XYZ by thresholds (`abc_xyz_policy`). Upsert `item_classification`.
3. **Supplier perf** — per supplier×product from PO→GR: on_time (`receipt ≤ expected+grace`), avg_lead_time (completing receipt), variance, reject/fill, composite (weights). Min-sample fallback → supplier-level → `confidence=low`. Upsert `supplier_performance` + `suppliers.current_performance_score`.
4. **Log** — write `scm_analytics_run` (counts, window, duration, status); structured stage logs.
- **Explain** — `explain_demand(product_id, warehouse_id)` re-derives the working (window, sample points, MA, CV, channel split) deterministically for debugging (AC-M2.13).

## 3. Triggers
- **Scheduled** — register a `scheduled_task` `scm_analytics` (cadence configurable; nightly default). Runs the full job.
- **On-run** — a `reorder_run` (M3) triggers/reads the latest stats (pinned into recommendations there).
- **On-GR** — posting a GR (M4 flow / seed) fires a hook refreshing only that supplier×product's `supplier_performance`.
- Worker note: analytics runs on the RQ worker or scheduler process; **restart worker after task edits** (dev-session rule).

## 4. FE — light up M1 columns
- M1 dashboard columns previously "—" now bind to real values: `avg_daily_demand`, `days_of_cover` (net_position÷demand_rate), **overstock** state (DoC > `overstock_days`), ABC/XYZ columns + filter. Add ABC/XYZ to the filter bar (`SearchableSelect`).
- Optional light admin views: `item_classification` grid, `supplier_performance` grid (reuse DataGrid) — gated `scm.dashboard.view`.
- A small **supplier scorecard** panel in the Supplier perspective (reuse stat tiles).

## 5. Tests (test-first / TDD — golden fixtures authored FIRST)
- **pytest golden-set** (the dozen fixtures from M0, now with blessed demand/CV/class/supplier numbers):
  MA steady + robust-on-spiky (AC-M2.1/2.2), channel split + double-count (AC-M2.3), ABC/XYZ (AC-M2.5/2.6),
  supplier metrics + grace + completing-receipt + fallback (AC-M2.8–2.10), backfill (AC-M2.14), explain determinism (AC-M2.13).
- **pytest job:** run-log written + on-GR hook scoped (AC-M2.11/2.12); auth.
- **vitest/playwright:** M1 columns render real values + ABC/XYZ filter (AC-M2.4/2.7).

## 6. Risks
- **Channel tag coverage** — customers without a market_segment → demand_nature defaults to continuous; log the coverage % so it's visible (a big untagged share silently biases the baseline).
- **cost_price nulls** — ABC annual value can't be computed for null-cost SKUs; classify as unknown, don't zero.
- **Thin supplier data at demo** — supplier_perf off seeded PO/GR only; `confidence=low` where sparse; don't oversell.
- **Robust-MA method choice** — pick one transparent method (trimmed mean or median-based); document it; golden-test it. Don't tune to one SKU (no-overfit rule).
- **Job cost over big catalog** — batch by SKU×warehouse; index outflow by (product_id, warehouse_id, created_at); the run log captures duration to catch regressions.
