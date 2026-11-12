# PLAN: Chatbot speed (CHATBOT-SPEED, work-order lane 2)

Status: Waiting (small fix track, size S, cloud lane). Step 1 diagnosis posted on the PR; waiting on crew go + stage timings.

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

## Diagnosis (step 1, 12 Nov, verified in the repo)
- Cause of the 26 Oct jump: #1865 CHAT-SLIM-INDEX (263643ae). The lookup step runs before the parser on every turn
  (`engine.py:6224` -> `_lookup_lines` `engine.py:1756`): visibility checks, `lookup_lists.load_rows`, one embedding
  round trip for the message pieces, shortlist scoring. Live with the prod label move to v65/v66 (26 Oct ~11:02 MYT).
  Earlier measurement: `PLAN-chat-v66-regressions-26oct.md:24,62` (turn medians about 4.3 s -> 6.3 s, parser flat).
  #1872 cut only part of it.
- Today (span pass on, v70+): `_span_prep` (`engine.py:1871`) then `_span_lookup` (`engine.py:2272`): span LLM call,
  then a serial span embedding round trip, then the parser.
- Smaller regression: since #1967 (e86b4592, 30 Oct) every embedding request opens a new `httpx.Client`
  (`embedding_client.py:71,99`): a fresh TCP + TLS handshake per call on the turn path.
- Ruled out: #1848 inbox queue (off by default; `started_at` re-stamped at claim). Caveat: on that path `finished_at`
  is stamped after the sender POST, so the send step counts in `reply_ms` there.

## Proposed fix (needs crew go)
One shared keep-alive `httpx.Client` per process in `embedding_client` (re-made after a fork), per-request timeout.
Red-first test: two `embed_texts` calls build one client (mock transport, no network).

## Span-pass replay design (step 3, needs a cap)
`scripts/chatbot_eval/replay.py live` with `--prompt-version-id`: arm A = prod parser text pinned by md5 (span on),
arm B = the same text with only the `== LOOKUP SPANS ==` line removed (unlabelled version on the crew copy). Same
100 recent real turns, x1 first, `--max-usd` cap. Metrics per arm: wrong answers (graded), not-found rate, LLM calls,
`understood` ms. Stop at the first checkpoint where arm B is worse.
