# PLAN: Reorder planning - one formula, one scope

Status: building (lane `fix/reorder-plan-row-tidy`, 11 Sep 2026)
UAC: `reorder-one-formula-acceptance-criteria.md`
Owner rulings: 11 Sep 2026 (this session), on top of #829 (10 Sep, one scope) and #794 (no-level project buy, now superseded by the formula below).

## Why

Measured on run de3a0cf7 (11 Sep 07:30 MYT), product B2155-NL-BLUE: on hand 128, SPO 0, PO 339, project 493, retail 170, no buyer level. The plan showed Suggested qty 493, Suggestion "Stock 128 + PO 339 + Buy 26", ledger "Net -196" beside "Gap to line 493" and "Buy before rounding 26". The sheet printed Dealer o/s 1381. The footer said "0 of 826" while the Decisions tile said "0 of 418" and the plan list said "826 / 0 / 826".

Three causes, all post-#828:

1. **Two sizing rules and two nettings.** A no-level product buys its confirmed project need in full with no netting (`reorder_run_service` ~1948, issue #794); at location grain project need is added on top of the retail netting (~2215). The grid then nets AGAIN: product rows carry no warehouse id, so `proposeCover` offers the row's own pool stock (128) back, and `poOffset` subtracts the open PO (339) that #828 already put inside the net. On the local 10 Sep run, 134 Buy rows carry on hand and 75 carry open PO, so every one of those reads a Buy that is too small.
2. **The sheet's Dealer o/s reads the whole open SO book.** `summary_order_service._demand_aggregates` has no horizon and no acknowledgement rule (verified on the 0907 copy: 1381 open across 8 lines, 170 inside 01/01-31/12/2026). The grid's Retail column (170) is the engine's horizoned `retail_committed`.
3. **Three counters never learned the one scope.** `PlanLinesSection` hands `planLines.totals` (every line) to `PlanBudgetReview` while the tile gets `reportedTotals` (default-visible lines). The plan list's Lines column is `run_log.recommendation_count` and its Decided total is `decision_service._refresh_run_counts` planned (DISTINCT product over every rec). `plan_scope.hidden_by_default` is Python-only, so SQL readers cannot apply it.

## The one formula (owner ruling, 11 Sep 2026)

For every plan row, product grain or location grain, level set or not:

```
level  = reorder_level, or 0 when the product has none ("no level = 0")
need   = project + retail + level - SPO arriving
buy    = need - on hand - PO open              (= level - net; clipped at 0)
```

`net` is the stored `net_position` the ledger's "Net now" block already prints (on hand + SPO + PO - project - retail). `on hand`, `SPO`, `PO` are the site-pool figures #828 fixed (`ACTIVE_SITE_POOL_SQL`). MOQ / order multiple round `buy` up once, after the formula.

What each surface shows, from that one number:

| Surface | Reads |
| --- | --- |
| Suggested qty (grid column, sheet column) | rounded `buy` (196 for B2155) - the figure the buyer copies into Order qty |
| Suggestion / Decision pill / panel prefill / sheet Suggestion | `Stock S + PO P + Buy B` where `S = min(on hand, need)`, `P = min(PO, need - S)`, `B = rounded buy`. Parts are DISPLAY of what the net consumed, never a second netting. `S + P + unrounded buy = need`. Zero parts are omitted; `buy = 0` reads "Nothing" |
| Ledger "Gap to line" | `level - net` (196); "Buy before rounding" the same before MOQ |
| Panel inputs BRW / PO / Buy | prefilled `S / P / B`; editing S or P down raises Buy by the same amount (`composeMixture` with `gap = need`), never below 0 |
| SPO | stays inside `need` and is shown as the read-only SPO fact row, never a mixture part |

Worked examples (UAC carries them as tests):

| Product | level | project | retail | on hand | SPO | PO | need | buy | Suggestion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B2155-NL-BLUE | none -> 0 | 493 | 170 | 128 | 0 | 339 | 663 | 196 | Stock 128 + PO 339 + Buy 196 |
| CBMC5570 | 100 | 0 | 2 | 0 | 0 | 1 | 102 | 101 | PO 1 + Buy 101 (today: "PO 1 + Buy 100") |
| CSK2800-QT | none -> 0 | 914 | 0 | 0 | 0 | 0 | 914 | 914 | Buy 914 |
| covered | 120 | 0 | 0 | 135 | 0 | 0 | 120 | 0 | Nothing (hidden by default, net 135 > 120) |

Consequences, stated so nobody is surprised:

- A no-level product with negative net and NO project demand now becomes a Buy (level 0 is breached). The 11 Sep run had 184 `needs_level` rows; the count that flips is measured on live after deploy and reported.
- The #794 "project buy" bypass and the location-grain "project need added on top" are deleted: project demand is in `net`, so level 0 already triggers it. `needs_level` and the "Set AutoCount level" nudge stay.
- Cross-location cover (`proposeCover`, warehouse grain) stays for locations NOT already inside the row's own net; a product-grain row's on hand already sums every in-scope pool, so it offers nothing extra. The coder verifies that claim against `inputs.plan_basis.locations` before deleting the product-grain call.
- P8 (`isProjectOnlyLine` hides the PO part on project-only rows) is retired: the engine nets PO for every row since #828, so hiding the part breaks the identity. The reserve already reduces `project_need` (`project_supply_reduction`).

## Slices (one lane, one PR)

- **S1 (done, feafc759b):** grid drops the duplicated product-name subtitle; cover panel labels BRW / PO / SPO.
- **S2 - sheet Dealer o/s on the run's horizon.** `write_rows` sets `dealer_outstanding` (and `dealer_outstanding_line_count`) from the recs' frozen `retail_committed`, summed over the product's rows, when the run carries the channel snapshot; the SO-book aggregate stays only for `max_days_outstanding` (ageing) and the unclassified count. Legacy runs (no snapshot) keep today's read.
- **S3 - one scope for the counters.** Migration adds `scm.reorder_recommendation.hidden_by_default BOOLEAN NOT NULL DEFAULT false`, backfilled in the same migration by the SQL twin of `plan_scope.hidden_by_default` (one-off; the Python rule stays the only runtime source). `reorder_run_service` stamps the column at write time. `run_log.recommendation_count`, `_refresh_run_counts` planned, the recommendations serializer and `decision_service.list_plan_row_decisions` total all read the column. `PlanLinesSection` passes `reportedTotals` to `PlanBudgetReview`.
- **S4 - the formula.** Engine: level None plans as 0 at both grains; delete the two project-buy bypasses; `_channel_freeze` / `suggested_qty` on the sheet equals the rounded buy; `_suggestion_text` prints the parts. Frontend: `suggestedDecisionFor` / `composeMixture` / panel prefill / ledger "Gap to line" read the parts above; `poOffset` and product-grain `proposeCover` stop re-netting.

Tester writes the red tests from the UAC first; the lane coder makes them green; reviewer + browser once at lane end.

## Out of scope

Level suggestions (`suggested_level`, "+ Add" horizon), the Order Inquiry link rules, warehouse-grain cover scope policy.
