# SCM M7 — Market-research priority factor — Acceptance Criteria

Status: DRAFT (2026-07-17). Branch `feat/scm-reorder-copilot`. Classification: MODULE (scm).

Make market research an OPT-IN, bounded PRIORITY factor in cash ranking — trending
categories fund first under a tight budget — WITHOUT changing order quantities. The
factor value comes from the deterministic `market_signal` table; the LLM never sets a
ranking number (same boundary as M5/M6).

Decisions (user, 2026-07-17): per-run toggle (not always-on) · symmetric de-prioritize
(down-trend lowers rank) · modest weight (~0.10) but CONFIGURABLE via the policy.

## Engine (cash_ranking.py — PURE maths, golden-tested)

- **AC-M7.1** — `FACTOR_KEYS` gains `market`; `DEFAULT_WEIGHTS['market'] = 0.10`.
- **AC-M7.2** — `market_value(trend, magnitude)` normalizes a signal 0–1, SYMMETRIC:
  `up → 1.0`, `flat → 0.5`, `down → 0.0`; `None`/unknown trend → `None` (factor DROPPED,
  never fabricated). If a magnitude/strength 0–1 is present it scales toward the extreme
  (up: 0.5+0.5·s, down: 0.5−0.5·s) so a strong trend counts more than a weak one.
- **AC-M7.3** — `build_factors(..., market_value=None)` adds the market factor:
  `present=(market_value is not None)`. With `None` the factor is dropped from BOTH sums
  of `rank_score` (graceful degrade) — so a run WITHOUT market signals scores exactly as
  before (backward-compatible).
- **AC-M7.4** — golden: two buys equal on every other factor, one in an `up`-trend
  category and one in `down`, rank_score(up) > rank_score(down); both drop to the old
  score when `market_value=None`.

## Wiring (reorder_run_service + models + migration)

- **AC-M7.5** — migration: `scm.reorder_run.include_market boolean NOT NULL DEFAULT false`
  + `scm.cash_ranking_policy.weight_market numeric` (nullable; code default 0.10).
- **AC-M7.6** — `create_run(..., include_market=False)` stores the flag on the run;
  `load_cash_weights` reads `weight_market`.
- **AC-M7.7** — `_apply_cash_stage(db, recs, include_market)`: when `include_market`, each
  buy's product category → latest matching `market_signal` (id-OR-code) → `market_value`
  passed to `build_factors`; when off, `market_value=None` for all (no effect). The matched
  signal summary is frozen into `inputs.market_factor` for explainability.
- **AC-M7.8** — `order_qty` / `recommended_qty` / ROP / safety stock are byte-identical
  whether `include_market` is on or off (ONLY rank_score/rank/rank_factors may move).

## API + FE

- **AC-M7.9** — `POST /scm/reorder-runs` accepts `include_market: bool` (default false).
- **AC-M7.10 (FE)** — Run planning modal has a "Factor in market signals" toggle with a
  one-line explainer ("Trending categories fund first; quantities are unchanged").
- **AC-M7.11 (FE)** — the explanation dialog's "why this rank" shows the Market factor
  (label + the matched signal summary) when present; absent otherwise. No UUID surfaces.
- **AC-M7.12** — the policy weight is admin-configurable (default 0.10) wherever the other
  cash-ranking weights are edited.

## Test report keys back to these ids.
