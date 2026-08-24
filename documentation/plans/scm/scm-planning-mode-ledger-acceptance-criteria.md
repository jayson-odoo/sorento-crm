# UAC: Planning mode toggle + quantity ledger

Status: Approved by user 2026-08-12 (chat design session). Build pending.

## Journey

The actor is the buyer (Joey seat). They arrive at Reorder Planning (or the Simulation
planning tab) from the sidebar.

1. Before any of this, an admin has picked HOW the company plans, once, on the SCM
   settings surface: **Auto** (the engine computes the trigger line from demand, lead
   time and safety stock) or **Manual** (the trigger line is the reorder level someone
   set, AutoCount round-trip). One universal toggle. Not per product - per-product
   overrides remain possible later through policy rows, but no UI for that now.
2. The buyer opens a row's order-qty popover. They read a LEDGER that runs in the same
   order their decision runs:
 - **THE LINE**: where the trigger came from. Manual mode: the reorder level, its
     source and date. Auto mode: the computed ROP with its derivation (current popover).
     Then net now (broken into on hand + SPO - SO), the open PO book (named but not
     counted), and the gap.
 - **COVER BEFORE BUYING**: the live cover parts of the decision - use stock at a
     named warehouse, SPO arriving (named, never re-offered), use an open PO. Each line
     is the same toggle the Adjust dialog offers; unticking one recomputes the lines
     below in place.
 - **THE BUY**: an OPTIONAL forecast add-on line the buyer clicks to include
     (engine proposes the number = demand rate x horizon; never assumed), then the buy
     before rounding, then MoQ / order multiple rounding with the "+N extra, clears in
     ~X" note. When cover eats the whole gap this block collapses to "Nothing to buy -
     MoQ not relevant".
3. The buyer accepts / adjusts / skips exactly as today; the ledger IS the explanation
   of the same decision composition.

## Acceptance criteria

### A. Universal planning mode

- A1. The SCM settings surface (Policies page) shows a "Planning mode" control:
  Auto (computed reorder point) / Manual (reorder level). Reads and writes the GLOBAL
  `scm.reorder_policy` row's `policy_type` (`reorder_point` <-> `reorder_level`),
  touching no other column. Same route family as the existing global-policy knobs in
  `app/api/v1/scm/config.py`.
- A2. Flipping the mode changes the NEXT run only; completed runs keep the basis they
  ran with (already frozen in `inputs.policy_type`).
- A3. Per-product policy rows (scope sku/class) still win over the global row - the
  toggle moves the default, it does not delete overrides.

### B. Ledger popover (shared grid, both pages)

- B1. One popover component in the shared PlanLinesGrid; renders on /scm/reorder and
  the simulation Planning tab identically.
- B2. Block one varies by the ROW's frozen `inputs.policy_type`: manual shows level +
  source; auto shows the ROP derivation. Blocks two and three identical in both modes.
- B3. Net breakdown states each source once, in its true role: SO and SPO inside net,
  PO outside net ("not counted", per ADR-337) and offered only as a cover choice.
- B4. Cover lines are the LIVE decision parts (same composition as the Adjust dialog,
  S16): toggling one recomputes "left to buy", the forecast line, and the MoQ rounding
  in place. No second editor.
- B5. Forecast add-on is opt-in: a labelled "+ Add N (next Xd demand at r/day)" action;
  never silently included. Adding it grows the buy part of the decision.
- B6. MoQ and order multiple render ONLY inside THE BUY block. Zero buy -> the block
  reads "Nothing to buy - MoQ not relevant".
- B7. No UUIDs, no explanatory prose beyond the one-line hints shown in the journey.

### C. Simulation coverage

- C1. `scripts/scm_sim/world.py` seeds a `scm.reorder_level` row for EVERY scenario
  whose story tolerates one (value consistent with the scenario's demand story);
  P033 keeps NULL (needs_level is its story).
- C2. The snapshot records which planning mode the run executed under.
- C3. With the global mode flipped to manual and a run executed, the harness produces a
  coherent manual-mode result set (trigger = level, qty = level - net floored at MoQ)
  for the scenarios seeded with levels; flipping back reproduces the blessed auto
  baseline exactly.

## Non-goals

- Per-product mode UI (later; policy rows already support it).
- Changing the engine's qty math in either mode.
- Blending the two lines (no averaging, no fallback from one to the other).
