# PLAN: bound and index the S1 achievement query (#1319)

Status: implemented (PR #1320; fix lane, small fix track; no migration: the plans showed no missing index)

## Problem

Saving a sales target (all products) hangs for minutes: the response's `target_detail` runs
`achievement_service.achieved_by_period`, whose `agent_lines` CTE reads every live line of the
credited agents, compares `sales_order_lines.company_id` as TEXT, and only then joins the
periods. See issue #1319 for the owner's report and the pg_stat_activity evidence.

## Work list

- R1 the company comparison on `sales_order_lines` is UUID to UUID, no cast on the column side.
- R2 lines are bounded by the specs' date span (order date, and DO date for delivered) and the
  credited agents before any product or category join; the category set is resolved once.
- R3 a save runs the achievement at most once (the response's `target_detail`).
- R4 a performance test pins the plan shape and a wall-clock budget on a seeded volume.
- R5 nothing else changes; S1 and S2 suites stay green.

The UAC is `sales-achievement-query-perf-acceptance-criteria.md` alongside.

## Outcome

- R1: no column is cast. `sales_orders.company_id` is a typed UUID filter; on the tables below
  it the company rule is a UUID comparison inside CASE that gates a foreign row's values to 0,
  so a statistics-less planner never probes a whole-company index per order (8.5 s measured).
- R2: `agent_lines` reads only the credited agents' lines dated in the periods' span, plus the
  lines a DO dated in a delivered period's span delivers. Periods are expanded to days and met
  by an equality on (credit group, date). The scope set is resolved once into a hashed IN;
  an all-products target reads no scope.
- R3: a save runs the achievement once, for the response's target page.
- R4: `tests/test_sales_achievement_perf.py` on `tests/_sales_volume.py`.
