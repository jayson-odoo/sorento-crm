# Reorder level as the planning basis - acceptance criteria

Status: implemented (S10), not deployed

Related: `PLAN-scm-m3-reorder-engine.md` (the forecast basis this sits beside),
`PLAN-scm-m8-reorder-planning-daily.md` (the daily run), ADR-0011 (one planning engine).

## Why this exists

The engine shipped with a forecast basis: `ROP = d x lead + d x safety`,
`order_up_to = ROP + d x review`, `buy = order_up_to - net`, where `d` is
`scm.demand_stat.avg_daily_demand` over a 90-day window. That is a correct continuous
replenishment policy and it stays.

It is not how Sorento buys today. A 2-unit project order on SRTWCX7405-RL-S-PJ produced a
recommendation to buy 15.933, because 51 days of forecast cover (14 lead + 7 safety + 30
review) were baked in and the order itself played no part in the number. The buyer's actual
question is narrower and they already answer it by hand every week.

So the forecast basis is **demoted, not removed**: it becomes one selectable planning basis
among several, and it also feeds the suggestion for the number the buyer does own.

## Journey

**Actor:** Joey, the buyer. Arrives from the sidebar, `SCM -> Reorder planning`, once a week.
Nobody hands him a task; the weekly list is the task.

**What the system already knows about each item:** what is on hand and where, what is on
order (PO), what is on the water (SPO), what is already sold and not yet delivered, what it
cost last time it was bought and when, how much of it moved in each of the last three months,
what the supplier's MOQ and order multiple are, and whether the item is discontinued.

**Step 1 - he opens the weekly list.** It shows only items whose position has fallen below
their reorder level. Nothing else competes for his attention. Each row already carries every
figure he would otherwise have looked up: he does not open a second screen to decide.

*His single decision:* order this, or not.

**Step 2 - he disagrees with a quantity.** He changes it on the row. The proposal keeps the
original beside it so the change is visible to whoever approves.

*His single decision:* what quantity instead.

**Step 3 - an item has no reorder level yet.** It appears in a separate group, "needs a
level", with a suggestion computed from the last three months of movement and the arithmetic
shown. He accepts the suggestion or types his own.

*His single decision:* accept the suggested level, or set one.

**Step 4 - he sends the list to Mr Loo.** One action, one proposal document.

**What he holds at the end:** a proposal, per supplier, that Mr Loo can approve. **What
everyone else is told:** the levels he accepted are stored, so next week's list already
reflects them and he is not asked twice.

## Locked decisions

| # | decision | why |
|---|---|---|
| D1 | The planning basis is `scm.reorder_policy.policy_type`, the field that already resolves global -> product_class -> sku. `reorder_level` is a third value beside `reorder_point` and `periodic_review`. | The toggle the user asked for already exists and is already scoped. A parallel feature flag would be a second, weaker copy of it. |
| D2 | Forecast code paths are untouched. Turning forecast back on for a class or a SKU is a policy row, not a deploy. | "Don't discontinue what we have done, that's industry standard." |
| D3 | The reorder level is stored per (product, warehouse) and owned by the user. The 3-month suggestion is stored beside it and never silently applied. | The forecast basis was rejected precisely because it decided quantities the user had not agreed to. |
| D4 | An item with no level is listed under "needs a level", never proposed and never hidden. | Hiding it reads as "nothing to do"; auto-applying the suggestion is the engine deciding again. |
| D5 | Dealer vs project is a stored `warehouses.segment`, seeded from the code-suffix rule, editable. | Bare BRW is the dealer bin and BRW-BB / BRW-IB are project bins, but that is a convention, not a guarantee. Parsing the string at read time makes it unfixable when it breaks. |
| D6 | Cover months (default 2) and study months (fixed 3) live on the policy, and the arithmetic is printed on the row. | A suggestion the user cannot argue with is a suggestion they will not trust. |

## Acceptance criteria

### S10a - segment

- **AC-S10a.1 [BE]** Given a warehouse whose code has no dash suffix, when the segment
  backfill runs, then its `segment` is `dealer`.
- **AC-S10a.2 [BE]** Given a warehouse whose code has a dash suffix (`BRW-BB`, `DC1-IB`),
  when the backfill runs, then its `segment` is `project`.
- **AC-S10a.3 [BE]** Given an admin sets a warehouse's segment explicitly, when the backfill
  is re-run, then their value survives (backfill only fills what is unset).
- **AC-S10a.4 [FE]** Given the warehouse config screen, when it renders, then segment is
  shown on the read view and editable in the same position on the edit view.

### S10b - reorder level

- **AC-S10b.1 [BE]** Given a product with movement in the last 3 months at a warehouse, when
  the suggestion is computed, then `suggested_level = round_up(avg monthly movement x cover
  months, MOQ/multiple)` and the basis (each month's quantity, the average, the cover months)
  is stored with it.
- **AC-S10b.2 [BE]** Given a product with no movement in the window, when the suggestion is
  computed, then `suggested_level` is 0 and the basis says so, rather than the row being
  absent.
- **AC-S10b.3 [BE]** Given a stored level, when the suggestion is recomputed, then the stored
  level is unchanged and only `suggested_level` moves.
- **AC-S10b.4 [BE]** Given a user accepts a suggestion, when it is saved, then `source` is
  `accepted_suggestion` and the level equals the suggestion at the moment of acceptance.
- **AC-S10b.5 [BE]** Given a user types a level, when it is saved, then `source` is `manual`.
- **AC-S10b.6 [BE]** Levels are company-scoped, and a run for company A never reads company
  B's levels.

### S10c - basis toggle

- **AC-S10c.1 [BE]** Given `policy_type='reorder_level'`, when net position is at or below the
  level, then a buy is triggered and `triggered_reason` names the level and the net.
- **AC-S10c.2 [BE]** Given `policy_type='reorder_level'`, when net position is above the
  level, then no buy is triggered, regardless of forecast demand.
- **AC-S10c.3 [BE]** Given a triggered row, then `recommended_qty = level - net` and
  `rounded_qty` floors at MOQ then rounds up to the order multiple.
- **AC-S10c.4 [BE]** Given `policy_type='reorder_level'` and no level for the
  (product, warehouse), then the row is emitted as `needs_level`, never as a buy.
- **AC-S10c.5 [BE]** Given `policy_type='reorder_point'` (or `periodic_review`), then the
  existing forecast behaviour is byte-for-byte what it was before this change.
- **AC-S10c.6 [BE]** Given a class-scoped policy row selecting a different basis, then that
  class plans on that basis and the rest of the catalogue does not.

### S10d - the row

- **AC-S10d.1 [BE]** Every plan row carries: on hand, outstanding PO, incoming SPO,
  outstanding sales, MOQ, order multiple, level, suggested level, and the 3-month movement
  split by month.
- **AC-S10d.2 [BE]** Last purchase cost and date are resolved **per segment**: a dealer row
  reads receipts into dealer warehouses, a project row reads receipts into project
  warehouses.
- **AC-S10d.3 [BE]** Given a product never purchased into that segment, then the row says
  "never purchased" rather than showing another segment's cost.
- **AC-S10d.4 [FE]** The weekly list renders every one of those figures on the row without a
  drill-in, at 1280px and at 375px.
- **AC-S10d.5 [FE]** Rows needing a level are a separate group with the suggestion and its
  arithmetic, and accepting one moves the row into the proposal in place.

## What the data cannot answer yet

**AC-S10d.2 is satisfied honestly, not fully.** 12,928 of the 12,940 `purchase_order_lines`
on the customer's book carry no `warehouse_id`, because the purchase-history export names no
destination. So a segment-specific last purchase exists only where a purchase happened to
record one. The row reports which case it is - `own_segment`, `unattributed`,
`never_purchased` - and an unattributed price is never relabelled as the dealer cost. SPO
allocations already carry a destination, so the same query answers per segment as that data
arrives, with no further change.

## Found by verification, not by tests

Both leaks came through the POOL path, from running a real plan and reading the rows:

1. A pooled buy row was built from the aggregate cell, which has no on-hand, no level and no
   last price. The checklist rendered blank on exactly the rows a pool produces.
2. A pool where nobody had set a level summed to a target of **0**, and 0 is a real target
   that any deficit trips - it bought 52,872 units of one live SKU against a number nobody
   chose. That is AC-S10c.4 defeated through a path the AC did not name.

Both now have regression tests written from what the browser showed.

## Out of scope for this phase

Deferred to Phase 2 (commercial layer): selling price and margin per segment, who is selling
(`orders.salesman`), who is buying, repeat-order and good-selling flags, the push list,
continue / discontinue and the notification to salesmen and marketing.

Deferred to Phase 3: new-item promotion from the catalogue, telling customers about a
discontinued item when the PO goes in (with incoming and stock), production status by
supplier, the segment tool.

Parked: transfer proposals. They happen before CS hand over the order inquiry, and CS decide
them as stock allocation.
