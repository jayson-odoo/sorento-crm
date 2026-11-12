# PLAN: Chatbot speed (CHATBOT-SPEED, work-order lane 2)

Status: Plan (small fix track, size S, cloud lane). Step 1 read-only diagnosis in progress.

## Goal
WhatsApp chatbot replies faster with no new wrong answers. Target median / slowest-5% reply
7.7 s / 19.6 s -> 5 s / 13 s or less. Guard: wrong answers 3% or less on a fresh 100-turn check.

## Steps
1. Read-only diagnosis (US$0): name the non-AI change of 25-26 Oct that added about 2 s, with
   file:line and commit, from git history and stage timings. Posted as `crew-note: speed-diagnosis`.
2. If a code fix is agreed: red-first test, fix, reviewer, `crew-tests:` on the head.
3. Span pass: replay design only until crew approves a cap; paired replay with/without span pass.
4. Report numbers and a recommendation for lane 4 (span pass off: yes/no).

## Out of scope
Prompt changes or publishes, stock-code matching (lane 1), scoreboard (lane 3), promotions,
follow-up memory (#1747), keyword/regex guards, engine carry changes.
