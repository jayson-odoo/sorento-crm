# PLAN: chatbot failure review (1 Nov 2026)

**Status:** Review READY at 1e4c52a83f, small fix track, one PR (#2061), waiting for CI and the owner's hand test. Scope
is S5 and S3 only (owner, 1 Nov). Phase 1 cause table: `crew/state/eval/fail-review-1nov/cause-table.md`, outside the repo
because it holds production counts. UAC: `chatbot-fail-review-acceptance-criteria.md`. Reply templates mapped to code:
`chatbot-fail-review-template-map.md`.

## Dropped, with the reason

- S4 lost message and the n8n error arm: owner, "i want to discon n8n ady". Not fixed.
- "Enquiry resolved" notices to staff: owner, "need to send to staff contact". Stays as it is.
- H1a glued code and quantity: owner, skip. Invoice asks: owner, "we cannot handle yet".
- S2 long lists: no proof without a live model call. The 85-90 line limit is inference from one measured speed.
- S1 residual: `test_fail_triage_escalation.py:1074` pins a company with no team links as the honest failure, on purpose.
- "Thankyou" re-fires the last ask: reproduced through the real engine when the parser carries the domain with no entity
  ("How many units of X?", the whole previous reply). Not fixed here. The engine re-runs a carried ask, which is also how a
  real "check again" works, and only the parser can tell the two apart, so the fix is a prompt line with a gate and an
  owner publish. The cause table's `turn/task.py:681` was wrong: a trial fix there changed no reply.
- Open, not this lane: a failed promotion read can still say "no promotion" (`lanes/business/__init__.py:1780`,
  `lanes/business/fetch.py:291,295`). Found in review, unchanged by this PR.

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
  PO rung ("nothing on order"), a plain-text answer on a multi-ask line ("Stock: 0"). Round 2 found failed probes stamping
  "- no incoming" on roster and related-products lines; `pickers.probe_rows` now reads an error envelope as not measured.
- S3: a timeout or dropped connection retries up to `CHATBOT_LLM_RETRIES` (default 3), inside `CALL_DEADLINE_SECONDS`.
  The budget is the real ceiling: the 20 s attempt and 35 s budget fit one timeout retry and at most four connection
  retries. The clarifier and the chat report extractor keep one attempt's time, so a parser retry stays inside the turn's
  budget.
- My earlier cite for S5, `answer_bridge.py:1935-1937`, was the wrong path; that is the miss arm. Crew's independent
  read and the engine test both land on `apply_crossdomain_hit`.
