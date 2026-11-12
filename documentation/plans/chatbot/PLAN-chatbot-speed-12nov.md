# PLAN: Chatbot speed (CHATBOT-SPEED, work-order lane 2)

Status: Merge-ready pending crew (small fix track, size S, cloud lane). Five no-answer-change fixes built and reviewed; span replay cancelled (owner 12 Nov, span step stays).

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
- Second cause (corrected after crew's stage timings): the #1848 inbox queue, switched on in prod on 26 Oct (656 of
  667 turns; 100% from 27 Oct). On that path `finished_at` is stamped after the sender POST (`inbox_queue.py:642,649`),
  so the send step now counts in `reply_ms`: "unaccounted" went 0.00 -> 0.80 s p50. inferred: mostly a measurement
  change, since the customer always waited for the send.
- Stage timings (crew, 12 Nov, p50): before the parser 0.06 s (25 Oct) -> 0.77 s (26 Oct) -> 2.11 s (11 Nov); parser
  flat 3.1-3.6 s; span call 1.19 s; unaccounted 0.55 s (11 Nov). Prod parser: gemini-3.5-flash-lite v72 since 4 Nov.

## Fix (crew go, 12 Nov): built
One shared keep-alive `httpx.Client` per process in `embedding_client` (re-made after a fork, lock reset after a
fork, idle connections kept 30 s), per-request timeout. Tests: `tests/test_embedding_client_keepalive.py`.
Sandbox measurement: 453 -> 47 ms per embedding call; inferred prod saving 0.2-0.6 s of the 2.11 s pre-parser time.
Also: the eval meter (`scripts/chatbot_eval/budget.py`) reads the owner-approved app prices, so a capped replay on
gemini-3.5-flash-lite is metered (`tests/chatbot_eval/test_budget_prod_model_price.py`).

## No-answer-change fixes (owner 12 Nov 16:15: speed without any behaviour change)
| # | Fix | Commit | Expected saving p50 (inferred) |
|---|-----|--------|------------------------------|
| 1 | Embeddings keep-alive (shared client, 30 s idle, no cookies) | 0509559a, b3e8b848, b306cae9, 23141d1d | 0.2-0.6 s |
| 2 | Span event stores `prep_ms`, `resolve_ms`, `usage_log_ms` | a4887fee | 0 (measurement) |
| 2b | Inbox event stores `queued_ms`, `lookup_ms`, `send_ms`, `send_attempts` | c6827ebb | 0 (measurement) |
| 3 | Span call starts before the row loading (overlap); AC-S2-2 restated (crew ruling a) | 52f9c625, fa1ae41d, a2d8ea12 | 0.2-0.5 s |
| 4b | respond.io client keep-alive (takeover check before every inbox turn) | 4352eade | 0.1-0.3 s |
Parked: #4 sender POST keep-alive (about 10 test files fake `httpx.post`; decide on `send_ms` data).
Shared helper: `app/services/http_keepalive.py` (one per-process client per purpose).

## Span-pass replay design (cancelled: owner 12 Nov, the span step stays)
`scripts/chatbot_eval/replay.py live` with `--prompt-version-id`: arm A = prod parser text pinned by md5 (span on),
arm B = the same text with only the `== LOOKUP SPANS ==` line removed (unlabelled version on the crew copy). Same
100 recent real turns, x1 first, `--max-usd` cap. Metrics per arm: wrong answers (graded), not-found rate, LLM calls,
`understood` ms. Stop at the first checkpoint where arm B is worse.
