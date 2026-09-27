# PLAN: bound and index the S1 achievement query (#1319)

Status: in progress (fix lane, small fix track; a migration only if the plan proves an index is missing)

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
