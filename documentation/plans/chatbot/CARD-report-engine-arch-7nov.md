# CARD: report engine scalability (REPORT-ASK-ARCH, 7 Nov 2026)

Full plan: `ARCH-report-engine-7nov.md` (same folder).

**Verdict:** the query layer (`reports/ask.py` CATALOGUE + `run_ask`) and the renderer scale. The follow-up merge does
not: `report_ask.py` is 3931 lines / 478 `if`s on #2209 (3781 / 464 on main); 55% of it is merging the parser's
full-state object with the held report through ~29 keep/clear rules, each a guess about what an EMPTY slot meant.

**Fix:** the parser emits per-axis ops (keep / set / add / remove / all, absent = keep); one 5-row merge table; one
ordered validator that asks at most one question, whose answer is just another delta; one AXES table that drives
resolution, route params and header labels; `crm_report_ask` takes the same `ReportSpec` from the agent.

**New feature cost, end state:** new filter axis ~40-80 lines, no merge change; dealer vs project split 0 lines
(already `group_by: channel`); supplier outstanding ~250 lines (a dataset + a kind); leaderboard vs target ~120.

**Waves:** W0 corpus (156 #2209 turns + owner Expected list, L1 no-LLM + L0 md5-pinned) -> W1 shadow -> W2 delta
prompt -> W3 clarify-as-delta -> W4 delete the old path (~ -1600 net) -> W5 agent -> W6 resolver table.
~12-14 lane-days.

## Questions

1. Parser contract: per-axis ops or full-state object? **Rec: ops.**
2. Agent: `crm_report_ask` with `ReportSpec`, or sales inside `crm_query`? **Rec: `crm_report_ask`.**
3. #2209: merge as the bridge then freeze rules, or park? **Rec: merge after its hand test, then freeze.**
4. Re-record the 26 steps with the `Held report:` line, and the 7 Nov hand-test Expected list as the per-turn
   expectation? **Rec: yes.**
5. One week of production shadow logging before W4 deletes? **Rec: yes, trace only.**
