# UAC - SCM M2: Demand Model, ABC/XYZ, Supplier Performance

> Given/When/Then contract for milestone M2. Parent umbrella: `scm-reorder-copilot-acceptance-criteria.md`.
> Depends on M0 (schema/views/seed) + M1 (dashboard). Governs: `PRINCIPLES.md`.

**Slug:** `scm-m2-demand-classification-supplier-perf` · **Domain:** scm · **Milestone:** M2 · **Status:** DRAFT (grilled, pre-code)

## Scope
The **intelligence inputs** the engine (M3) consumes: a transparent demand rate (channel-separated,
no double-count), ABC/XYZ classification, and a supplier performance scorecard. Mostly backend +
one scheduled analytics job; lights up the deferred M1 dashboard columns. **No engine, no
recommendations yet.**

## Locked decisions (from M2 grill)

| # | Decision |
|---|---|
| M2-D1 | **Channel via customer → market_segment.** `market_segments` gains a `demand_nature` column (`continuous`\|`spike`) - "mark the segment's demand type," configurable. `customers` gains a `market_segment_code` FK. demand_nature resolves through **customer → market_segment** (works for historical DO AND committed SO - both have a customer). The `order_type → demand_nature` map is **demoted to an optional per-SO override** (default off); segment is primary. |
| M2-D2 | **Demand = sales outflow only.** From `stock_ledger` outbound where `reference_type` = DO/order - **exclude** adjustments/transfers/damage/returns. Per SKU×warehouse. |
| M2-D3 | **Transparent MA.** `demand_rate` = moving average over `forecast_window_days` (policy). **Robust/trimmed** for high-CV SKUs so a past one-off project doesn't inflate a steady SKU's baseline; **weighted-MA** as a policy option. NOT ARIMA/Prophet. Stored in `scm.demand_stat` (SKU×warehouse). |
| M2-D4 | **Channel-split projection, no double-count.** MA splits into a **continuous baseline** + a **spike series** via the M2-D1 tag. `projected_demand(h) = baseline·h + committed_SO_spike(h)` per policy `spike_handling`. `days_of_cover = net_position / demand_rate`. History (past) and committed (forward) never overlap. |
| M2-D5 | **ABC/XYZ.** ABC by annual consumption **value** (Σ qty×cost, trailing 12mo), cut points A=80%/B=15%/C=5% cumulative - **configurable**. XYZ by demand **CV** (=σ/μ of per-period demand); thresholds X<0.5 / Y 0.5 - 1.0 / Z>1.0 - **configurable**. Both at **SKU×warehouse** + network rollup for display. Config in `scm.abc_xyz_policy`. Stored in `scm.item_classification`; gates **confidence**, not maths. |
| M2-D6 | **Supplier performance** (supplier×product): `on_time_rate` (`receipt ≤ expected + grace_days`, `grace_days` configurable default 0), `avg_lead_time` (clock = the **completing** receipt, when cumulative qty_received reaches qty_ordered), `lead_time_variance`, `reject_rate` (Σrejected/Σreceived), `fill_rate` (Σreceived/Σordered), `composite_score` (`delivery_w·on_time + quality_w·(1−reject_rate)` from `scm.supplier_scoring_policy`). **Min-sample fallback** to supplier-level when `sample_size < min_sample_size` (default 3); below that `confidence=low`, no fabrication. |
| M2-D7 | **One combined `scm_analytics` scheduled job** computes demand_stat + item_classification + supplier_performance (shared window read); **on-run pinning**; an **on-GR-posting hook** refreshes supplier_perf only. |
| M2-D8 | **Latest-only stats** - `demand_stat`, `item_classification`, `supplier_performance` upserted (one row per key, `computed_at` bumped). **Reproducibility** = run log + `computed_at` + frozen recommendation inputs (M4) + deterministic explain (below). No versioned snapshots. |
| M2-D9 | **Observability (no silent jobs).** `scm.scm_analytics_run` log per execution: started/finished/status/scope/counts/window/config-ref/error. Clear stage logs. A deterministic **explain debug endpoint** re-shows a SKU's demand/CV working (window, sample points, MA, CV, channel split). |
| M2-D10 | **M1 columns light up:** `avg_daily_demand`, `days_of_cover`, **overstock** state (DoC > `overstock_days`, added to `reorder_policy`), ABC/XYZ columns + filter. Still dark till M3: ROP, low/reorder-due. |
| M2-D11 | **First run backfills all planning SKUs** (DoD backfill, not seed-if-absent). Demo: demand off **real outflow**; supplier_perf off **seeded PO/GR** (curated/thin, honest). |

## Acceptance criteria

### Demand
- **AC-M2.1** GIVEN a steady SKU's real sales outflow WHEN the job runs THEN `demand_stat.avg_daily_demand` = the MA over `forecast_window_days`, matching a hand-computed golden value; adjustments/transfers/damage are excluded.
- **AC-M2.2** GIVEN a spiky (high-CV) SKU with one past project spike WHEN the baseline computes THEN the robust/trimmed estimate is NOT inflated by the spike (asserted vs a naive-MA baseline on the same series).
- **AC-M2.3** GIVEN a SKU sold to both a continuous-segment and a spike-segment customer WHEN demand computes THEN the continuous baseline and spike series are separated by customer→market_segment→demand_nature; **a project order present in history is not also added as committed** (double-count test).
- **AC-M2.4** GIVEN `demand_stat` + `net_position` WHEN days-of-cover computes THEN `DoC = net_position / demand_rate`, and the M1 dashboard shows it (was "-").

### Classification
- **AC-M2.5** GIVEN trailing consumption value WHEN ABC computes THEN SKUs bucket A/B/C by configurable cumulative cut points; changing the cut points reclassifies with no code change.
- **AC-M2.6** GIVEN per-period demand WHEN XYZ computes THEN `CV = σ/μ` buckets X/Y/Z by configurable thresholds; a steady series → X, a lumpy series → Z (golden fixtures).
- **AC-M2.7** GIVEN `item_classification` WHEN stored THEN it's SKU×warehouse with `computed_at`, network rollup available for display, and the M1 ABC/XYZ columns + filter light up.

### Supplier performance
- **AC-M2.8** GIVEN seeded PO→GR pairs WHEN the snapshot runs THEN supplier×product `on_time_rate`/`avg_lead_time`/`lead_time_variance`/`reject_rate`/`fill_rate`/`composite_score` match hand-computed golden values; `grace_days` and scoring weights change output with no code change.
- **AC-M2.9** GIVEN a PO line received over multiple GRs WHEN avg_lead_time computes THEN the clock uses the **completing** receipt.
- **AC-M2.10** GIVEN a supplier×product with `sample_size < min_sample_size` WHEN scored THEN it falls back to supplier-level; below fallback → `confidence=low`, never a fabricated score.
- **AC-M2.11** GIVEN a GR posting WHEN it commits THEN the on-GR hook refreshes that supplier×product's snapshot (not the whole catalog).

### Job / observability
- **AC-M2.12** GIVEN the `scm_analytics` job WHEN it runs THEN one `scm_analytics_run` row records status/scope/counts/window/duration/error, and stage logs are human-readable.
- **AC-M2.13** GIVEN a SKU's stored demand WHEN the explain debug endpoint is called THEN it deterministically re-derives and returns the working (window, sample points, MA, CV, channel split) matching the stored value.
- **AC-M2.14** GIVEN no prior stats WHEN the first job runs THEN all planning SKUs get populated (backfill), not just new ones.

### Conventions
- **AC-M2.15** Deterministic engines built **test-first** (golden fixtures authored before code). Config tables editable; no LLM anywhere in M2 (pure maths). Decoupling preserved (reads canonical `public` tables only).

## Tests (test-first - TDD; golden fixtures FIRST)
- **pytest golden-set:** demand MA (steady + robust-on-spiky), CV/ABC/XYZ classification, supplier metrics (on-time/grace, completing-receipt lead time, reject/fill, composite, min-sample fallback), double-count test, backfill, explain-determinism.
- **pytest job:** run-log written; on-GR hook scoped; auth.
- **vitest:** M1 columns now render real values (avg-daily-demand, DoC, overstock, ABC/XYZ); filter works.
- **playwright:** dashboard shows lit-up columns + ABC/XYZ filter against real data.

## Deferred
Historical censored-demand reconstruction + forward unmet-demand capture (fast-follow); ROP +
reorder-due (M3); recommendations (M4). `order_type→demand_nature` override wiring optional.
