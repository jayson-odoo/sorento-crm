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

## Part 2 (#2419 slice 1; final wording after the crew answers)

5. A target question naming an agent (or "my dealers") computes only the targets that agent can be
   credited on (their own, their teams', dealer targets with any account of theirs): the rows
   returned are identical to today's, and the achievement statement reads no other target's periods.
6. `agent_target_summary` and `target_list` rows carry the remaining-to-target figure next to
   `achieved_pct`, computed by the server; the panel answer prints it without a repair round.
7. The per-question cap counts only crm_query calls that ran; crm_describe and refused calls do not
   use it up; reaching it never ends the answer with a limit message.
8. Panel, on a copy of prod data: "how are my dealers' sales this year against their targets?",
   then "and last year?", then a typo version: each answered in 2 model calls, under 35,000 input
   tokens, under 15 s, no timeout, figures equal to the Targets screen.
