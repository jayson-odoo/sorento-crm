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

**Lanes (plan section 3):** W1 corpus (#2209 merged; the re-record is a read-only extraction of the `prompt_text` trace, plan 3.2.1) -> W2 spec + prod shadow -> W3 delta prompt ->
W4 clarify as delta (beside W5 agent spec) -> W6 delete the old path (after the shadow week + published prompt) ->
W7 resolver table. ~13-15 lane-days.

## Rulings (owner 7 Nov ~16:15, "2229 ok")

1. Parser emits explicit per-axis ops (keep / set / add / remove / all, missing = keep).
2. `crm_report_ask` takes `ReportSpec`: one engine for chatbot and agent.
3. Merge #2209 when done, then freeze keep/clear rules.
4. Crew re-records the 26 steps with the `Held report:` line; the owner's hand-test Expected list is the per-turn
   expectation.
5. One week of production shadow logging (`turn_trace`) before the old path is deleted.
