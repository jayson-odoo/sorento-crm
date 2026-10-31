# PLAN: chatbot failure review (1 Nov 2026)

**Status:** Plan, Phase 1 cause table filed with crew 1 Nov, waiting for the owner's choices (no code yet).
Feature track M, lead pattern. The table holds production counts and stays outside the repo
(`crew/state/eval/fail-review-1nov/cause-table.md`). UAC is written after the owner picks the fixes.
Reply templates mapped to code: `chatbot-fail-review-template-map.md`.

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
