# PLAN: AGENT-PANEL-FIXES (AI assistant panel)

Status: Review (track: M, cloud lane; all six slices built, live x3 blocked in the cloud sandbox: no provider credit)

Owner report 11 Nov 2026: stuck "still working on your earlier message" reply, bare "74.52%" in a
quotation compare answer, slow turn (88,995 input tokens over 3 rounds), trace drawer shows only
"Not recorded" for agent turns, "View trace" opens a new tab, Steps / trace visible to non-admins.

Slices (each red-test first):

- A. Busy lock safe behind pgbouncer transaction mode (no session advisory lock), with TTL.
- B. Quotation-line percentages labelled ("x% below list" / "x% above list").
- C. Speed: measure per-round input tokens by part, trim tool schemas on non-crm_query rounds,
  report before/after.
- D. Trace drawer reads agent_round / agent_tool / agent_reasoning records ("Agent" section,
  "Context sent to the AI"), hides empty legacy stages for agent turns.
- E. "View trace" opens the drawer on the same tab.
- F. Steps, route line and View trace visible to admins only.

UAC: `agent-panel-fixes-11nov-acceptance-criteria.md`.

## Decisions

- A: Redis `SET NX PX` + compare-and-delete, TTL 360 s (settings cap 300 s + 60). Not the scheduler's direct DB
  URL: `SCHEDULER_LEADER_DATABASE_URL` is optional and unset by default (`app/scheduler/leader.py`), Redis is
  already required (RQ, rate limiter). Redis down = the turn runs unlocked, with a warning (rate limiter rule).
- B: `vs_list` string replaces `discount_pct` / `above_list_pct`.
- C: measured before cutting (seeded compare, real MCP catalogue, admin): tool schemas were 93,991 of 106,843
  characters per round. Narrowing after the quotation lines round cuts round 2 to 19,807. `prompt_cache_key` on
  main rounds. The dealer-access side call (one extra call per admin turn) is left as is and reported.
- F: admin roles (superadmin, admin), by role slug, both sides. The settings slug no longer opens the trace.
