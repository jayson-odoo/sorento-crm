# PLAN: AGENT-PANEL-FIXES (AI assistant panel)

Status: Build (track: M, cloud lane)

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
