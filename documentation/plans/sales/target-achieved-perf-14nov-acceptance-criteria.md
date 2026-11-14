# UAC: Invoiced target achievement speed (lane TARGET-ACHIEVED-PERF)

Plan: `PLAN-target-achieved-perf-14nov.md`.

1. Every Invoiced target's Achieved figure (per period, per account) is identical before and
   after the change: 2026 totals per dealer target and account on sorento_prod_1112 compared
   row for row.
2. The Invoiced achievement statement never compares each credited document with every period:
   rows removed by its join filters stay within (credited documents x periods of one target).
3. On sorento_prod_1112: agent_target_summary this_year, target_list this_year and the Targets
   screen dealer tab each finish well under 5 s, warm and cold.
4. When a computed assistant entity (targets, commission) times out, the message no longer tells
   the model to narrow the question with a filter.
