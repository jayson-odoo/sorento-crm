# PLAN: chatbot failure review (1 Nov 2026)

**Status:** Build, small fix track, one PR (#2061). Owner GO 1 Nov: S5 then S3, size S each, red-first, every
unverified claim proven or dropped. Phase 1 cause table filed; it holds production counts, so it stays outside the repo
(`crew/state/eval/fail-review-1nov/cause-table.md`). UAC: `chatbot-fail-review-acceptance-criteria.md`. Reply templates
mapped to code: `chatbot-fail-review-template-map.md`.

Held by the owner, not in this PR: stalled API and lost message (S4), long lists (S2), stale ask re-fire (Q4). Dropped by
the owner: glued code + quantity (H1a). Left as it is: invoice asks.

## Goal

Owner, 1 Nov: "I don't have a requirement on no sorry, I just don't want us to fail due to some bug or
loading issue or resource issue." Find every recent production chatbot failure the system caused, fix the
root cause. Wording-only changes are out. An honest correct answer (no stock, access denied by design) is
not a failure.

## Phases

1. Cause table, one `crew report --ask`: failure type, count, release window, root cause with file:line,
   already fixed by a merged PR (which), proposed fix and size, recommended order. Includes failure classes
   the Gemini parser switch with no reasoning effort (31 Oct ~23:30) may have introduced, before/after
   where the data allows.
2. After the owner's OK: UAC, then per fix a tester writes red tests with masked real failing turns as gold
   cases, a coder makes them green, kill test, reviewer.

## Definitions

- Failure: `turn_outcome` says `technical` (`app/services/chatbot/analytics/outcome.py:159`), or the reply
  is a dead end caused by a bug, timeout, missing or wrong key, provider error, loading, resource limit or
  bad routing, whatever the outcome column says.
- Not a failure: `refused_policy`, a correct empty answer, a clarifying question the turn genuinely needs.

## Prior work to net out

- #2018 and #2030 (fail triage batches 1 and 2), #2054 (key per provider), #2045 (console no longer flips
  global switches), #2049 and #2050 (MCP hardening). Turns before those releases that match their causes are
  reported as "already fixed" with the PR, not as open work.

## Rules

Never commit real data (public repo): gold cases are masked. Prompt changes go through the fixed-baseline
gate. Red-first and kill proof per fix.

## What shipped

- S5, proven on main with the real engine: a failed stock or incoming read printed "No stock and no incoming" beside "I
  could not fetch". Path: `turn_runtime.envelope_of` keeps `error`, `turn/fetch.envelope_missed` says not a miss,
  `engine` calls `answer_bridge.apply_crossdomain_hit`, which read only the reply text and the empty figures. Review
  round 1 found three more ways: a CRM connection failure behind MCP (no failing status, so rendered as empty), a failed
  PO rung ("nothing on order"), a plain-text answer on a multi-ask line ("Stock: 0").
- S3: a timeout or dropped connection retries up to `CHATBOT_LLM_RETRIES` (default 3), inside `CALL_DEADLINE_SECONDS`.
  The budget is the real ceiling: the 20 s attempt and 35 s budget fit one timeout retry and at most four connection
  retries. The clarifier keeps one attempt's time, so a parser retry stays inside the turn's budget.
- My earlier cite for S5, `answer_bridge.py:1935-1937`, was the wrong path; that is the miss arm. Crew's independent
  read and the engine test both land on `apply_crossdomain_hit`.
