# SCM M8 - Daily Reorder Planning, Budget Co-Pilot & Unified Assistant - Acceptance Criteria

> Status: DRAFT (2026-07-17) - written FIRST per methodology, before PLAN and code.
> Classification: MODULE (scm) refinement. Public schema, normal FKs.
> Governing guardrail (umbrella §0): **no path from LLM output to any numeric field.**
> Deterministic engine computes numbers -> human overrides sit on top -> LLM is semantic only.

This milestone reworks the reorder planning page from a manual-run, three-grid, dropdown-action
surface into a **daily-scheduled snapshot** the user reviews and steers: one table with two
draggable sections, a budget control that funds/defers in place, per-line inline decisions with a
mandatory reason, click-to-explain drills on the calculated numbers, and one conversational
assistant that merges "discuss" + "market search" and lands every plan change as a confirm-gated
human override.

Five slices, keyed A-E. Each Given/When/Then is independently verifiable and drives a Phase-2 test.

---

## Slice A - Explain drills on calculated numbers (topics 1 & 5)

Rationale: every displayed number that comes from a query must be openable so it is never a black
box. Days cover is `net / demand_rate` - it is NOT open sales orders; open SOs only appear inside
`net` as committed. The drill must show that honestly.

- **M8-A1 (Net drill lists committed SOs).**
  GIVEN a recommendation row with `net = on_hand + on_order - committed`
  WHEN the user clicks the info icon beside the Net value
  THEN a drill shows the three components and, under `committed`, the list of open sales-order lines
  contributing (SO number, qty, customer, order date), summing to the committed figure.

- **M8-A2 (Days cover drill = net breakdown + demand as a navigable DO list).**
  GIVEN a row with a finite days-cover value
  WHEN the user clicks the info icon beside Days cover
  THEN the drill shows two parts: (1) the Net breakdown from M8-A1, and (2) the demand basis shown as
  a **navigable list of the delivery orders (DOs)** that drove the outflow - each row a DO number +
  date + qty out, clickable to open that DO - NOT a row of raw weekly bucket numbers. It also shows
  avg daily demand and the variability metric spelled out in full as **"Coefficient of variation"**
  (never "CV"; it is NOT covariance) with a one-line plain explanation, and the final arithmetic
  `net / demand_rate = X days`.

- **M8-A3 (Days cover drill on a deficit).**
  GIVEN a row where `net < 0` or `demand_rate <= 0` (days cover renders as `-`)
  WHEN the user opens the drill
  THEN it explains why days cover is undefined (deficit net, or no measurable demand) rather than
  showing a broken division.

- **M8-A4 (Order qty formula popover).**
  GIVEN a buy recommendation with an order qty
  WHEN the user clicks the info icon beside Order qty
  THEN a popover shows the qty derivation (safety stock, reorder point, order-up-to level, and the
  inputs used), consistent with the deterministic engine's actual computation.

- **M8-A5 (Rank + Cash unchanged).**
  Rank keeps its existing factor hover; Cash impact shows `qty x unit_cost` on hover. No new drill
  is added for these two.

- **M8-A6 (No UUIDs, human-readable).**
  All drill content resolves ids to human-readable identifiers (SO number, customer name, product
  name); no raw UUIDs appear.

---

## Slice B - Low-stock on the SCM dashboard (topic 2) - REVISED 2026-07-17

Rationale (revised after prototype review): stock-warning does NOT belong on the reorder planning
page. It lives on the **SCM dashboard**, which already has a `Stockouts` tile (`on_hand <= 0`) and a
`Below reorder point` tile (currently shows `-`). Populate the existing `Below reorder point` tile
with the low-stock count; keep `Stockouts` as-is. Two tiles, not one merged tile - the dashboard
already separates them. The reorder planning page shows NO stock-warning card (see Slice C card set).

- **M8-B1 (Below reorder point tile populated).**
  GIVEN the SCM dashboard
  WHEN it renders the `Below reorder point` tile
  THEN it shows the count of products with **`on_hand > 0 AND net <= reorder_point`** (demand-aware
  ROP), no longer `-`.

- **M8-B2 (Stockouts tile unchanged).**
  The `Stockouts` tile continues to count `on_hand <= 0`. A product is counted in exactly one of the
  two tiles (stockout takes precedence; a product with `on_hand <= 0` is never also "below reorder
  point").

- **M8-B3 (Low-stock threshold is demand-aware ROP).**
  Low-stock uses `net <= reorder_point` (engine ROP), NOT a static per-product min qty.

- **M8-B4 (Tile drill/filter).**
  WHEN the user clicks the `Below reorder point` tile
  THEN the dashboard warehouse listing filters to those products.

- **M8-B5 (Removed from reorder page).**
  The reorder planning page renders NO "Stock warning" card. Its summary cards are Buy / Disposition
  / Cash impact (Slice C).

- **M8-B7 (Terminology sweep: "Out of stock" / "Low stock", never "Stockout") - 2026-07-17.**
  GIVEN any SCM surface that renders a stock status (dashboard tiles, warehouse cards, net-position
  grid, supplier "products supplied" table, all product-list drill dialogs, the shared status chip).
  WHEN a status is shown
  THEN the `stockout` status renders as **"Out of stock"** (never "Stockout"), and a below-reorder
  product renders as **"Low stock"** (not "Healthy"). The backend `_compute_status` emits a `low`
  status for `on_hand > 0 AND net <= reorder_point` (after stockout/dead precedence) so these surfaces
  show it consistently. Centralize the label change in the shared status-chip component.

- **M8-B8 (Low-stock drill columns).**
  GIVEN the "Low stock" drill dialog
  THEN each row's Status shows **"Low stock"** (not Healthy), and the dialog has a **Reorder point**
  column (from `ProductSummary.reorder_point`) so the below-ROP relationship is visible.

- **M8-B9 (Avg-daily-demand explain in the product dialog).**
  GIVEN a product-list drill dialog with an Avg daily demand column
  THEN the column header has an (i) explaining the metric, and each row's avg-daily-demand number has
  an (i) that opens the contributing delivery-order / sales-order list (reuse the Slice A2
  demand-DO drill via `GET /analytics/explain/demand`) so the number is provably fact-based.

- **M8-B6 (Dashboard "Reorder plan" nav button).**
  GIVEN planning now lives on the reorder planning page (daily cron + Manual plan there), the SCM
  dashboard's inline "Run planning" button is obsolete.
  WHEN the dashboard renders
  THEN that button is relocated to the **top-right of the dashboard header** (above the Overstock
  valuation tile area), relabeled **"Reorder plan"**, and clicking it **navigates to
  `/scm/reorder`** (it no longer triggers an inline run).

---

## Slice C - One table, two draggable sections, budget in place, inline decisions (topic 4 + inline of 6)

Rationale: funded/deferred become one table with two sections; the budget control lives with the
funded section; every decision is line-by-line inline with a mandatory reason; no "..." menu.

- **M8-C0 (Summary cards).**
  The reorder planning page's summary cards are exactly three: **Buy** (count of buy recs),
  **Disposition** (count of disposition recs), and **Cash impact** (total cash of the plan). NO
  Today's-plan / Stock-warning / Within-budget / Over-budget cards (within/over counts already show
  in the table section headers).

- **M8-C1 (Single table, two sections).**
  GIVEN today's plan
  WHEN the planning page renders the buy recommendations
  THEN they appear in ONE table with two sections - **Within budget** and **Over budget** - separated
  by a section divider row, same columns throughout. (The legacy `needs_cost` third grid is removed;
  see M8-C7.)

- **M8-C2 (Budget control funds/defers live, in the funded section).**
  GIVEN the budget input rendered at the top of the Within-budget section
  WHEN the user changes the cash budget
  THEN the within/over split recomputes immediately: un-pinned buys are greedily funded by rank until
  the budget is spent; the rest defer. Committed and free cash are shown beside the input. The input
  is fully clearable (the user can delete the value to empty; empty is treated as 0 for the split, it
  does not force a stuck leading `0`).

- **M8-C3 (Manual pins win).**
  GIVEN a manually accepted (pinned) line and a manually rejected line
  WHEN the budget auto-fill runs
  THEN pinned lines are force-funded and consume budget first; rejected lines are excluded entirely;
  only un-pinned lines are reshuffled by the slider. A pinned line never drops to Over budget on a
  budget decrease (instead the free/over figures reflect the overspend).

- **M8-C4 (Rows drag between sections).**
  WHEN the user drags an Over-budget row up into Within budget
  THEN it becomes pinned/funded (subject to M8-C3); dragging a funded un-pinned row down defers it.
  Drag-to-fund/defer needs NO reason (it is a fund/defer decision like Accept). Only qty/supplier
  edits require a reason (M8-C5).

- **M8-C5 (Inline edit popover with mandatory reason).**
  GIVEN a funded or deferred row
  WHEN the user clicks the Order qty or Supplier cell
  THEN a row-anchored popover opens with the editable field, a live cash-impact preview
  (`new_qty x unit_cost`, delta vs original), and a **required** reason input; Save is disabled until
  the reason is non-empty; on Save the change persists to the decision/override layer and the row
  and split recompute. The engine's frozen recommendation value is never mutated.

- **M8-C6 (Accept / Reject inline in Decision column).**
  GIVEN a row
  WHEN the user clicks Accept (funded) / Fund (deferred) / Reject in the Decision column
  THEN the decision is staged inline without opening the "..." dropdown; Reject captures a reason
  (small popover); Accept needs none. The staged state is visible on the row.

- **M8-C7 (Needs-cost excluded with a banner, not a section).**
  GIVEN buy recommendations whose chosen supplier has no `unit_cost` on record (price unknown)
  WHEN the plan renders
  THEN those lines are excluded from both budget sections (they cannot be budgeted) and a single
  dismissible banner states "N products skipped - no supplier cost yet" with a "Review & add cost"
  link to those SKUs. A genuine `unit_cost = 0` is flagged as a likely data error (verify), not
  auto-funded as free.

- **M8-C8 (Confirm decisions -> draft POs).**
  GIVEN staged decisions
  WHEN the user confirms
  THEN consolidated draft POs are materialized (existing M4 behaviour), raising `on_order`.

- **M8-C9 (Mobile).**
  The table, budget control, and inline popover are usable at ~375px width (horizontal scroll on the
  table container; popover fits and its Save button is reachable).

- **M8-C11 (Warehouse column).**
  GIVEN the reorder plan table (Buy view)
  THEN it has a **Warehouse** column (the existing pre-M8 page has one). Per-rec warehouse; network
  recs show a network/all label.

- **M8-C12 (Disposition renamed to "Stock allocation").**
  The Disposition card + view are relabeled **"Stock allocation"**. The current actions
  (discontinue/promote/hold) stay for now; the inter-warehouse transfer suggestion (overstock
  warehouse -> shortage warehouse) is a SEPARATE feature to be grilled + planned (see
  "Stock allocation - to grill" below), not implemented blind.

- **M8-C10 (Row click opens detail).**
  GIVEN a recommendation row
  WHEN the user clicks the row (outside the inline-edit cells / decision buttons / drag handle)
  THEN it opens the existing recommendation detail view (`ReorderExplanationDialog` or equivalent),
  preserving the pre-M8 row-detail behaviour. The inline explain icons, edit popover, decision
  buttons, and drag handle keep their own click targets and do NOT trigger the row-detail.

---

## Slice D - Daily scheduled run, run inputs, snapshot continuity (topic 4)

Rationale: planning becomes a daily scheduled snapshot the user just reviews; the manual button
remains for on-demand runs; each morning is a clean decision slate over fresh numbers, but nothing
committed is re-suggested.

- **M8-D1 (Scheduled daily run).**
  GIVEN the scheduler
  WHEN the configured daily time is reached
  THEN a reorder run is created and persisted for that day across ALL warehouses, with **full budget**
  (funds everything initially) and **market insight OFF**, with no user interaction.

- **M8-D2 (Configurable time).**
  The scheduled run time is user-configurable (settings), not hard-coded.

- **M8-D3 (Page opens to today's plan).**
  WHEN the user opens the reorder planning page
  THEN it shows today's scheduled snapshot directly, without requiring a "Run planning" click.

- **M8-D4 (First-view fallback).**
  GIVEN today's scheduled run has not yet fired (or failed)
  WHEN the user opens the page
  THEN it shows the most recent available snapshot plus the "Manual plan" action, rather than
  auto-generating on page open or showing an empty page.

- **M8-D5 (Manual run inputs) - REVISED 2026-07-17.**
  GIVEN the "Manual plan" action
  WHEN the user opens it
  THEN the inputs are exactly: warehouse (pick) and budget (user enters). **No market-insight
  toggle** - market never enters a run; it only reaches the plan through the chat (Slice E). The
  legacy `buy_scope` input is **removed** (planning is always per-warehouse). Full budget is the
  default only for the scheduled run, not manual.

- **M8-D9 (Run history + view past runs).**
  GIVEN prior runs exist
  WHEN the user opens the reorder planning page
  THEN a run-history list is available (like the pre-M8 page): each entry shows the run date/time and
  summary; clicking one loads that run's snapshot into the plan view (read-only decisions or a clear
  "past run" state).

- **M8-D10 (Collapsible plan sections).**
  GIVEN the Within-budget and Over-budget sections
  WHEN the user collapses them
  THEN the plan table collapses so the user can scroll quickly to the run-history list below. Each
  section (or the whole plan block) has a collapse toggle.

- **M8-D11 (Past-run header reflects that run).**
  GIVEN the user is viewing a past run (not today's)
  WHEN the snapshot loads
  THEN the header stops saying "Today's plan" and shows that run's **date AND time** (e.g. "Plan ·
  15 Jul 2026, 06:00"), so it is unambiguous which run is on screen.

- **M8-D6 (Full-budget auto-run funds everything).**
  GIVEN a scheduled full-budget run
  WHEN it completes
  THEN all costed buys are Within budget initially; the user tightens the budget on the page to
  defer.

- **M8-D7 (Confirmed decisions reflected via net).**
  GIVEN decisions confirmed into draft POs yesterday
  WHEN today's snapshot is generated
  THEN those POs raise `on_order` so today's net accounts for them and the engine does not
  re-suggest what was already ordered.

- **M8-D8 (Staged decisions reset with a lapse nudge).**
  GIVEN staged-but-unconfirmed decisions on yesterday's snapshot
  WHEN today's snapshot appears
  THEN staged decisions do NOT carry onto today's rows; the user sees a "N unconfirmed decisions from
  yesterday lapsed" nudge with a way to review them.

---

## Slice E - Unified conversational assistant (topic 6)

Rationale: "Discuss this plan" and "Search the market" merge into one chat that knows this plan and
past plans, auto-searches the web when a question needs it, and lands every plan change as a
confirm-gated override. Guardrail: the LLM proposes; the human confirms; the confirmed value is an
override, never the model writing a number.

- **M8-E1 (One conversational surface).**
  GIVEN the plan assistant
  WHEN it renders
  THEN there is a single chat (the two-tab discuss/search split is gone). Market search is an
  auto-invoked tool inside the chat, not a separate mode.

- **M8-E2 (Grounded on this plan).**
  WHEN the user asks about today's plan (e.g. "which buys eat the most cash", "why is this
  deferred")
  THEN the assistant answers grounded on today's snapshot lines.

- **M8-E3 (Historical Q&A via snapshots, similar = category + variant).**
  WHEN the user asks about past plans for similar products
  THEN the assistant uses a `query_past_plans` tool that reads prior snapshots for the same SKU, its
  category siblings (category id-OR-code), and `variant_of_id` neighbours, returning past qty /
  days-cover / decisions / reasons across run dates.

- **M8-E4 (Auto web search).**
  GIVEN a question that needs a live market trend
  WHEN the assistant determines web search is needed
  THEN it auto-invokes web search (model self-selected tool); when no API key is configured it
  degrades gracefully (states search is unavailable) without crashing.

- **M8-E5 (Market signal -> confirm-gated qty deltas).**
  GIVEN a returned market signal that maps to products in the plan
  WHEN the assistant offers "Include in plan"
  THEN it proposes a concrete pending diff on the matching lines (old -> new qty, recomputed cash
  impact, reason pre-filled from the signal); NOTHING changes until the user confirms per line or
  all; on confirm the change lands in the override layer (M8-C5 semantics), not the engine.

- **M8-E6 (Ambiguous market match is listed, not auto-applied).**
  GIVEN a signal that matches products ambiguously
  WHEN the assistant proposes
  THEN it lists the candidate matches for the user to choose, rather than auto-applying to all.

- **M8-E7 (Guardrail invariant).**
  No chat action, market signal, or "include in plan" ever writes a numeric field on
  `reorder_recommendation` or re-runs the deterministic engine with LLM-chosen numbers. Every
  numeric change is a human-confirmed row in the override layer. (Assertable by test: engine outputs
  are byte-identical before and after any chat interaction; only override rows change.)

---

## M8 review fixes (2026-07-17, from user prod-build review) - MUST be test cases

- **M8-F1 (Reject keeps the row IN PLACE; drag is the only fund action) - REVISED 2026-07-17.**
  Rejecting a line must NOT remove it from the table AND must NOT move it between sections: a
  within-budget row that is rejected STAYS in the Within-budget section (greyed, "Rejected" chip); an
  over-budget rejected row stays in Over budget. Reject only marks the decision (excluded from
  committed cash), it never changes section membership. **Remove the "Fund" button entirely** from
  Over-budget rows - the ONLY way to fund/move a row into Within budget is to DRAG it to the top (one
  action type: drag for section changes; Accept/Reject for the decision). Re-accepting an
  over-budget-but-not-rejected row is still via Accept; moving sections is drag-only.
- **M8-F2 (Confirm-decisions bar gated on accepted).** The "... ready to confirm into draft purchase
  orders" bar appears ONLY when there is at least one ACCEPTED/adjusted (funded-by-decision) line -
  that is the only case where a draft PO is created. It must NOT show merely because within-budget
  lines exist with no decision made.
- **M8-F3 (Supplier/Decision column overlap).** Fix the table layout - the Supplier column text
  overlaps the Decision column. Correct widths / min-width / truncation so columns never collide.
- **M8-F4 (Rank factor "Value" not "ABC value").** In the "Why this rank" popover, the factor labelled
  "ABC value" must read the layman term **"Value"**.
- **M8-F5 (Reorder point explain).** Reorder point must be explainable: an (i) showing the formula
  `ROP = safety stock + demand rate x lead time` with the actual inputs (safety_stock, forecast daily
  demand, supplier lead-time days - all already on the rec). Applies on the reorder page and the
  Low-stock drill dialog's Reorder point column.
- **M8-F6 (Assistant: no separate "Search market" button; auto-route).** Remove the standalone "Search
  market" button. ONE Ask input; the assistant auto-determines from the question whether a live market
  web search is needed and runs it, answering conversationally; if the returned signal matches plan
  lines it attaches the confirm-gated proposal, otherwise it just answers the trend. Never require the
  user to pick a mode.
- **M8-F7 (Assistant past-plans + no implementation leakage).** "Tell me about the previous plan for
  similar plans" must surface past-plans context (use the plan's own top SKUs/categories when the user
  names none), and the assistant must NEVER expose implementation internals to the user (e.g. "the
  provided JSON does not include a 'past_plans' array"). Prompt hygiene: answer in business terms or
  say "no prior plans found for similar products", never mention JSON/context structure.

- **M8-F8 (PO link per line + View PO in detail).** Once decisions are confirmed and a draft PO is
  created, each line that went into a PO shows a link to that PO (the pre-M8 page pattern - reuse it),
  and the row-detail popup (`ReorderExplanationDialog`) has a **"View PO"** button that redirects to
  the PO page. The `GET /reorder-runs/{id}/decisions` response already carries the draft-PO number per
  rec; use it.

- **M8-F9 (Confirm bar clears after confirm).** After "Confirm decisions" creates the draft PO(s), the
  confirm bar must DISAPPEAR - a confirmed accepted line (one that now has a draft PO) is no longer
  "pending confirmation". The bar's count = accepted/adjusted decisions that do NOT yet have a draft
  PO. When all accepted lines are confirmed, the bar is hidden; those lines show a "PO created /
  <PO no>" state instead of Accept/Reject.

- **M8-F10 (Reorder-point explain defines + values safety stock and lead time).** The ROP explain
  (reorder page order-qty drill AND the Low-stock dialog reorder-point (i)) must SHOW the actual
  safety-stock and lead-time values AND a one-line plain definition of each: lead time = days from PO
  to goods received (supplier lead); safety stock = buffer for demand/supply variability over the lead
  time. The Low-stock dialog currently lacks these values - surface them (from the rec / rollup) rather
  than saying "set on the reorder plan".

- **M8-F11 (Table columns use full width; PO number not truncated).** The Decision column truncates
  the draft-PO number because the layout reserves horizontal space for the cash-budget control. Make
  the budget control's placement independent of the table column grid so the columns use the full
  width and the PO number (e.g. "PO-DRAFT-0008") renders in full, untruncated.

- **M8-F12 (Sticky sections - reject/accept never reflow the table).** Rejecting or accepting a line
  must NOT re-run the budget greedy-fill and must NOT cause any other row to jump between sections
  (the current glitchy auto-promote when reject frees budget). Section (Within/Over) membership is
  recomputed ONLY on an explicit budget-value change or a drag. Reject/accept only toggle the
  decision flag and update the committed/free totals in place; freed budget does NOT auto-promote an
  over-budget row.

- **M8-F13 (Over-budget rows have NO call-to-action).** Over-budget rows show NO Accept / Reject /
  Fund buttons. The only way to fund one is to DRAG it up into Within budget. Accept / Reject live
  only on Within-budget rows.

- **M8-F14 (Review & add cost -> filtered product page).** The needs-cost banner's "Review & add
  cost" link redirects to the product listing page pre-filtered to the needs-cost SKUs (the ones
  skipped for missing supplier cost), so the user can add cost there. Not a no-op.

- **M8-F15 (Plan methodology / "how this plan was built" explainer).** An information icon next to
  the "Today's plan - <date>" header opens a clean, well-designed panel (drawer or dialog) explaining
  the deterministic thought process behind the daily plan, so the user trusts the unattended
  recommendations. It must be grounded in the ACTUAL engine (no invented metrics): the demand rate
  (90-day delivery-order outflow avg + coefficient of variation), net position (on hand + on order -
  committed open SOs), reorder point (safety stock + demand rate x lead time), order-up-to (ROP +
  demand x review period) and order qty (order-up-to - net, rounded to MoQ/multiple), the ranking
  factors + weights (urgency/margin/value/committed-vs-forecast/market), and cash funding (greedy by
  rank vs the budget -> within/over). It also shows THIS run's context (daily scheduled, all
  warehouses, full budget, market off, generated-at time). Design: clean, spacious, step-by-step
  cards, strong hierarchy, plain language + the formula per step; NO dense tables, no visual fatigue.
  Reuse the existing run-overview endpoint (`GET /reorder-runs/{id}/overview`) for run context if
  useful, but the methodology steps are authored/deterministic (LLM-boundary: no LLM-generated
  numbers).

- **M8-F16 (Assistant action pipeline -> Apply to plan).** The chat must turn a natural-language plan
  instruction (e.g. "buy FT-B only, reject the rest", "defer everything under RM 50k", "accept the top
  3 by urgency") into a STRUCTURED action proposal: it resolves the referenced lines to real plan rec
  ids, proposes a per-line decision (accept / reject / adjust-qty) with a short reason, and renders a
  proposal card with an **Apply** button. Apply routes each proposed line through the existing
  decision endpoints (`/accept`, `/reject`, `/adjust`) - one confirm-gated action. Guardrail: the LLM
  proposes which lines + which decision; the human clicks Apply; no LLM writes a numeric field
  directly (adjust qty still goes through the human-confirmed override). Ambiguous references are
  listed for the user, not auto-applied. This extends the existing market-proposal card pattern from
  qty-deltas to accept/reject/adjust actions.

- **M8-F18 (Stock allocation shows only actionable rows; Hold is FYI).** The Stock allocation view is
  dominated by "Hold" rows (overstock just above the ceiling, no action needed) causing information
  fatigue. Show ONLY rows with a real call-to-action - Discontinue (dead stock) and Reallocate (the
  M9 inter-warehouse transfer, when built). "Hold" rows are FYI-only: hide them from the main list or
  move them to a muted, collapsed "No action needed (N)" section, and EXCLUDE them from the headline
  "Stock allocation" count/card (the card should count actionable items). Reduce fatigue: the default
  view surfaces only what the user must act on.

## Stock allocation (inter-warehouse transfer) - TO GRILL (SPECCED in M9)

User intent (2026-07-17): "Stock allocation" (renamed from Disposition) should suggest moving stock
**from a warehouse that is overstocked to a warehouse that has demand and is out-of-stock / low-stock**
for the same product. e.g. product X overstocked at WH-KL but out-of-stock at WH-JHR with open demand
-> suggest a transfer WH-KL -> WH-JHR of qty N. This is a NEW deterministic capability (a
network-rebalance pass) distinct from the buy plan and the discontinue/promote/hold dispositions.

Open questions to grill before building: transfer qty formula (cover the shortage vs balance
days-cover across warehouses); lead time / transfer cost; which warehouse pairs are eligible; how it
interacts with the buy plan (transfer instead of buy when possible?); does it become its own decision
type with accept/reject; does the engine already surface overstock+shortage per warehouse to build on.
Rename ships now (M8-C12); the transfer engine is a separate grilled slice.

## Cross-cutting

- **M8-X1 (No emdash).** All new/edited human-authored strings in this milestone use a hyphen, never
  an em-dash or en-dash (see the separate emdash-ban plan). Assistant/LLM output is stripped of
  em/en dashes before render.
- **M8-X2 (Searchable dropdowns).** Any new select (supplier swap, warehouse pick, category) uses
  `SearchableSelect` / `SearchableMultiSelect`.
- **M8-X3 (Confirm before destructive/detach).** Reject and any unlink/clear-decision action confirms
  first.

---

## Test report keying

The Phase-2 test report keys each row above to PASS / FAIL / DEFERRED. A slice is done only when its
Definition-of-Done gate passes, not merely when tests are green.
