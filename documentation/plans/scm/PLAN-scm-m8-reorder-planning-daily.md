# PLAN - SCM M8 - Daily Reorder Planning, Budget Co-Pilot & Unified Assistant

> Status: DRAFT (2026-07-17). Classification: MODULE (scm) refinement, public schema, normal FKs.
> UAC: `scm-m8-reorder-planning-daily-acceptance-criteria.md` (written first). This PLAN fulfils it.
> Guardrail (umbrella §0): no path from LLM output to any numeric field.
> Builds on M3 (engine), M4 (cash co-pilot), M5 (semantic + market), M6 (chat + market search).

## Guiding principle (user directive 2026-07-17)

**Adjust the existing reorder planning page, do NOT reinvent it.** Reuse the existing real components
and behaviours - `RunHistoryPanel` (run history + view past runs), `ReorderExplanationDialog`
(row-click detail), `ReorderResultsGrid` (disposition/read-only), the real `useReorderRun` /
`reorderRunService` wiring - and layer the M8 improvements (single draggable table, inline explain
icons, inline reason popover, inline decisions, budget-in-section, cleaner icons) on TOP. The M8
prototype's mock scaffolding is a staging step; the end state keeps the existing page's useful
features and adopts M8's cleaner interaction/visuals. "Take the best of both."

## Goal

Turn the reorder planning page from a manual-run, three-grid, dropdown-action surface into a
**daily-scheduled snapshot the user reviews and steers**: one table with two draggable sections, a
budget control that funds/defers in place, per-line inline decisions with a mandatory reason,
click-to-explain drills, and one conversational assistant that merges discuss + market and lands
every plan change as a confirm-gated human override.

## Current state (verified, on feat/scm-reorder-copilot)

- Page: `sorento_crm_frontend/app/(protected)/scm/reorder/page.tsx` -> `ReorderPlanningView.tsx`.
- Split: `CashCopilotResults.tsx` computes funded/deferred/needs_cost via
  `lib/reorderCashAllocation.ts::computeFunding()` against a budget slider, renders THREE
  `CashResultsGrid` instances.
- Table + columns + `RowActions` "..." menu: `CashResultsGrid.tsx`.
- Decisions: `hooks/useDecisions.ts` -> `services/decisionService.ts` -> `api/v1/scm/decisions.py`
  (accept/adjust/reject/bulk/confirm), overlay model `RecommendationOverride` (`models/scm.py:253`).
- Assistant: `PlanAssistant.tsx` two tabs (`PlanChat` -> `/reorder-runs/{id}/chat`; `MarketSearch`
  -> `/market-search`), hooks in `hooks/useExplainer.ts`.
- Days cover: `services/scm/reorder_engine.py::days_of_cover(net, demand_rate)`; demand from
  `scm.demand_stat.avg_daily_demand` (historical DO outflow via `scm.consumption_v`), net from
  `scm.net_position_v`. `explain_demand()` (`analytics_service.py:780`) already re-derives the
  weekly outflow sample.
- Cash impact / funding: `reorder_run_service.py::_build_rec`; `cash_ranking.py::allocate_funding`.
- Stockout: `dashboard_service.py::_compute_status` = `on_hand <= 0`; `_is_overstock` exists.
- Run trigger: `POST /reorder-runs` -> `reorder_run_service.create_run` (RQ job). NO cron for
  planning today (only nightly `scm_analytics` in `scheduler/task_scheduler.py`).
- Market: `market_research_service.py` (Anthropic `web_search_20250305`, key-gated); advisory via
  `explainer_service.market_advisory()`.

## Desired behaviour

See UAC slices A-E. Summary of the deltas from current state:

1. Explain drills on Net, Days cover, Order qty (reuse `explain_demand`; add net + qty explainers).
2. Merge stockout + low-stock into one "Stock warning" tile with split counts (low = net <= ROP).
3. Collapse 3 grids -> 1 table, 2 sections (Within/Over budget), budget control in the funded
   section, rows draggable, inline reason popover, inline accept/reject; needs_cost -> banner only.
4. Add a configurable daily scheduled run (all warehouses, full budget, market off); page opens to
   today's snapshot; remove `buy_scope`; staged-decision reset + lapse nudge.
5. Merge the two assistant tabs into one chat; add `query_past_plans` tool; auto web search; market
   signal -> confirm-gated qty-delta overrides.

## Approach by slice

### Slice A - Explain drills

- BE:
 - Net explainer: new read-only endpoint `GET /recommendations/{rec_id}/explain-net` returning
    `{ on_hand, on_order, committed, net, committed_sales_orders: [{so_number, qty, customer,
    order_date}] }`. Source committed SO lines from `scm.committed_v` / `sales_order_lines` for the
    rec's product+warehouse. (M8-A1.)
 - Days cover explainer: `GET /recommendations/{rec_id}/explain-days-cover` composing the net
    explainer + `explain_demand(product_id, warehouse_id)` output + the `net / demand_rate`
    arithmetic; handle deficit/no-demand cases (M8-A2, M8-A3).
 - Order qty explainer: `GET /recommendations/{rec_id}/explain-order-qty` returning the SS / ROP /
    order-up-to / rounded-qty inputs from the engine's per-rec computation (M8-A4). Persist the raw
    inputs on the rec at run time if not already available, so the explainer is reproducible.
- FE:
 - Reusable `ExplainPopover` / `ExplainDrawer` in `CashResultsGrid.tsx`; info icon beside Net, Days
    cover, Order qty; Rank keeps hover; Cash hover unchanged (M8-A5).
 - Resolve all ids to names; no UUIDs (M8-A6).
- Tests: pytest for each explainer (happy, deficit, no-demand, auth); vitest for popover
  states (loading/empty/error/data); playwright drill open on a real row.

### Slice B - Stock warning tile

- BE: extend `dashboard_service.py` composition to emit `stock_warning = { total, no_stock,
  low_stock }` where `no_stock = on_hand <= 0`, `low_stock = on_hand > 0 AND net <= reorder_point`
  (ROP from engine/policy), mutually exclusive (M8-B1..B3). Reuse net_position + ROP already
  computed; do not add a static-min path.
- FE: replace the stockout tile with the merged "Stock warning" tile showing total + split; click
  filters the listing (all / no-stock / low-stock) (M8-B4).
- Tests: pytest for the three counts incl. boundary (net == ROP, on_hand == 0 with committed);
  vitest tile render; playwright click-to-filter.

### Slice C - One table, budget in place, inline decisions

- FE (largest slice):
 - Replace the three-grid render in `CashCopilotResults.tsx` with ONE `CashResultsGrid` that takes
    all buys and renders a section-divider row between funded and deferred (M8-C1).
 - Move the budget input into the Within-budget section header; keep the live client-side
    `computeFunding()` recompute but make it **pin-aware**: pinned (manually accepted) lines are
    force-funded and consume budget first; rejected excluded; only un-pinned reshuffle (M8-C2, C3).
    Extend `lib/reorderCashAllocation.ts` to accept a `pins`/`rejects` set.
 - Drag rows between sections (dnd) -> pin/defer; drag needs no reason (M8-C4).
 - `InlineEditPopover`: anchored to the qty/supplier cell, field + live cash preview + required
    reason, Save disabled until reason present; persists via existing `useDecisions` adjust path
    (M8-C5). Supplier field uses `SearchableSelect` (M8-X2).
 - Decision column: inline Accept / Fund / Reject buttons replacing `RowActions` "..." menu; Reject
    opens a tiny reason popover (M8-C6).
 - Needs-cost: drop the third grid; render a single dismissible banner + "Review & add cost" link;
    keep those lines out of the budget math (M8-C7).
 - Keep "Confirm decisions" bar -> draft POs (M8-C8, unchanged from M4).
 - Mobile: table in `overflow-x-auto`, popover fits at 375px, Save reachable (M8-C9, per shared
    dialog scroll rule).
- BE: `unit_cost = 0` -> flag as data-error in the rec payload so FE can badge it (M8-C7).
- Tests: vitest for pin-aware `computeFunding` (golden cases: pin over budget, reject frees cash,
  slider reshuffles only un-pinned), InlineEditPopover (reason-gates-save, cash preview), inline
  decision buttons; playwright full flow (drag defer->fund, inline adjust with reason, reject with
  reason, confirm -> draft PO, needs-cost banner).

### Slice D - Daily scheduled run + continuity

- BE:
 - New scheduler handler `_handler_scm_daily_reorder` in `scheduler/task_scheduler.py`, registered
    like `scm_analytics`, firing at a **configurable** time (system setting), creating a run for ALL
    warehouses with `budget = full` and `include_market = False` (M8-D1, D2, D6). Reuse
    `reorder_run_service.create_run`.
 - "Full budget" = a sentinel meaning fund-everything at view time (e.g. budget_amount = null ->
    allocate treats all costed buys as within budget). Confirm `allocate_funding` handles the
    null/unbounded case; add if missing.
 - Remove `buy_scope` from the run inputs / `create_run` signature and `ReorderRun` usage (keep the
    column nullable/deprecated to avoid a destructive migration; stop reading/writing it) (M8-D5).
 - First-view: `GET /reorder-runs/today` returns today's snapshot or, if absent/failed, the most
    recent, with a flag so FE can show the fallback + Manual plan (M8-D4).
 - Lapse nudge: `GET /reorder-runs/lapsed-decisions` returns count of staged (unconfirmed)
    decisions on prior snapshots for the nudge (M8-D8). Staged decisions are inherently per-run
    (keyed to a rec on that snapshot), so they naturally do not carry - verify no cross-run
    inheritance exists.
- FE:
 - Page opens to `/reorder-runs/today`; "Run planning" button becomes "Manual plan" with inputs
    warehouse / budget / market toggle (no buy_scope) (M8-D3, D5).
 - Lapse nudge banner with a review link (M8-D8).
- Tests: pytest scheduler handler creates a full-budget all-warehouse run; `/today` fallback logic;
  buy_scope removal doesn't break create_run; lapsed-decisions count. Playwright: open page cold ->
  today's plan shows without a click.

### Slice E - Unified assistant

- FE:
 - Collapse `PlanAssistant.tsx` two tabs into one `PlanChat` surface; remove the standalone
    `MarketSearch` tab UI (M8-E1). Market search becomes a tool the chat invokes.
- BE (`/reorder-runs/{id}/chat` agent loop):
 - Tools available to the chat: existing plan grounding (M8-E2) + `query_past_plans(sku |
    category | product)` reading prior `reorder_recommendation` snapshots for same SKU + category
    siblings (id-OR-code) + `variant_of_id` neighbours (M8-E3) + web search (auto, key-gated,
    graceful) (M8-E4).
 - Market signal -> proposal: when a signal maps to plan products, the chat returns a structured
    `proposed_overrides` payload (per line: old_qty, new_qty, recomputed cash impact, pre-filled
    reason) rendered as a pending diff; the user confirms per line/all -> writes to the override
    layer via the SAME adjust path as M8-C5 (M8-E5). Ambiguous matches listed, not auto-applied
    (M8-E6).
 - Guardrail test: assert engine `reorder_recommendation` numeric fields are unchanged before/after
    any chat interaction; only `RecommendationOverride` rows change (M8-E7).
- Tests: pytest for `query_past_plans` (same-sku, category, variant expansion); chat proposes
  overrides not numeric writes (guardrail assertion); web-search-off graceful path. Playwright:
  ask historical question -> answer cites past plans; trigger market signal -> confirm diff ->
  override lands, engine numbers unchanged. Use real fixtures per the e2e-real-samples rule.

## Data model / migrations

- Likely NO new tables: reuse `ReorderRun` (snapshot), `ReorderRecommendation` (frozen line),
  `RecommendationOverride` (overlay). Add columns only if an explainer needs persisted engine inputs
  (order-qty SS/ROP/OUT) not already stored on the rec - one additive migration, nullable.
- `buy_scope` column: keep, stop using (no destructive drop).
- System setting for the scheduled run time.
- Alembic: chain new migration onto the COMMITTED main head, keep idempotent; verify single head
  after (per the dual-head + downrev lessons).

## Risks / open questions

- **Full-budget semantics.** Need to confirm `allocate_funding` cleanly handles unbounded budget
  (fund all costed). If it assumes a finite number, add an explicit "unbounded" branch rather than a
  huge magic number.
- **Drag + reason friction.** RESOLVED (user, 2026-07-17): drag-to-fund/defer needs NO reason (like
  Accept); only qty / supplier edits require a reason.
- **Order-qty explainer reproducibility.** If the engine does not persist SS/ROP/OUT per rec, the
  explainer must recompute from frozen inputs; ensure those inputs are frozen on the rec.
- **Scheduled run cost.** A daily all-warehouse full-budget run must complete within the RQ window;
  reuse the analytics cron's batching if needed.
- **Lapse semantics.** Confirm staged decisions are truly per-run (no SKU-level carry) before
  building the nudge.

## Phasing (three-phase loop, per slice)

Build order (independent-first): A -> B -> C -> D -> E. Each slice: Phase 1 FE prototype with mocks
(especially C's table + popover + drag, and E's chat proposal diff), sign-off, then Phase 2
test-first BE wiring + FE off-mocks (vitest + playwright + pytest), then Phase 3 `/code-review`.
Slice E depends on C's override path existing. The emdash rule (separate plan) ships independently
and first.

## Verification

Per slice, self-verify FE AND BE against every M8 UAC id end-to-end in a real browser (prod build at
handoff) before reporting complete. Test report keys each id PASS/FAIL/DEFERRED.
