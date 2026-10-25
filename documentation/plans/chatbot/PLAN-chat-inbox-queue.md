# PLAN: CHAT-INBOX-QUEUE - the CRM owns each contact's message queue

Status: Built, review READY (reviewer + security-reviewer, 3 rounds), PR #1848, waiting on owner hand test (size L, feature track: new ingest behaviour). Ships
switched OFF (`chatbot_direct_ingress_mode = off`, today's default).
UAC: `chat-inbox-queue-acceptance-criteria.md`.
Behaviour card: `PLAN-n8n-to-direct-ingress-gap.md` sections "Owner's design" and "CRM-owned
queue" (the research, options and owner rulings); this file holds the final rules.

## Owner rulings (25 Oct 2026)

- 05:35 Q1 (a): replies keep going out through the thin n8n `chatbot-sender`. One switchover,
  no pilot.
- 05:45: bursts must be handled by a real CRM-owned queue; the synchronous ticket with its 30 s
  clamp is not accepted.
- 05:50 GO: option 2 (async CRM inbox), drains on the API process pool like direct ingress,
  crash re-send rule (a) behind one small function so it can flip.
- 05:55 (hard): a deploy must cause zero failures in chat turns from the customer's view.

## Final rules

1. **Switch** = the existing `chatbot_direct_ingress_mode` (off | contacts | all) on the
   chatbot Settings screen (`sorento_crm_frontend/app/(protected)/user-management/settings/chatbot/page.tsx:69-72`,
   `:223-250`; column `models/user.py:755-761`). No new column, no migration, no UI change.
   Its meaning changes from "the webhook starts text turns early, n8n is the fallback" to "the
   CRM queues and answers every message of a covered contact". Off = today, exactly.
2. **Enqueue once.** Every injector of a covered message inserts its turn row at status
   `queued` (status exists, `contracts.py:408`) or finds it already there (unique key
   `models/chatbot_turn.py:63`). Nobody waits: the webhook answers respond.io as today;
   `/chat/turn` (`app/api/v1/external/chat.py:171`) answers at once with `duplicate: true`
   and no actions, which the spine's `head-arm` already treats as nothing to send. Media is
   queued too. `is_test` and console turns stay synchronous.
3. **Drain per contact** on the existing direct-turn pool (`app/tasks/chat_turns.py:75`,
   `_submit` `:81`): one drain per contact across all processes (Redis mutex with heartbeat,
   the liveness pattern of `dispatch.py:94`, `:243-264`; a mutex, not a ticket). Loop: take
   the oldest `queued` row by send time (`send_order.send_key_ms`, `send_order.py:105-122`),
   check takeover (`direct_ingress.py:264`, `:319`), run the turn (`run_turn`,
   `engine.py:2571`, as `direct_ingress.py:324` does), POST its actions to the sender
   (`direct_ingress.send`, `:358-437`), mark done, next. No clamp.
4. **Photo look-ahead.** Right before the turn writes conversation state
   (`turn_tail.persist`, `engine.py:8325`; the coder confirms nothing earlier in the turn
   writes conversation state) and before any POST, the drain checks for a `queued` row of the
   same contact with an EARLIER send time. If there is one: abandon this turn with no state
   written, put its row back to `queued`, and take the earlier row first; this row then runs
   again from the start.
5. **Never lose.** Rows live in Postgres. A sweeper in every API process (at start-up and at
   least every 2 s) re-arms a drain for each contact with `queued` rows and no live mutex, so a
   busy pool, a crash or a deploy only delays a row.
6. **Never double-answer.** Unique key at enqueue; one drain per contact; a row left
   `processing` by a dead process runs again only if no sender POST was attempted for it;
   otherwise `should_resend(row, send_log)` decides: re-send only when the log proves the POST
   never left (connection refused before sending); a timeout or an error answer after sending
   is not re-sent and the row is flagged for staff on the trace. One function, so policy (b)
   (always re-send) is a one-line flip.
7. **Shutdown.** On SIGTERM the drains stop taking rows, finish the current turn including its
   POST and done mark, then exit; anything arriving meanwhile just queues for the next
   process. Infra values: section "Zero-downtime deploy".
8. **Rollback** = mode `off`. Rows already queued keep draining (answered once); new messages
   take the sync path.

## Where the code goes (coder confirms each seam)

| Piece | Where |
| --- | --- |
| queue module: enqueue, drain loop, mutex, look-ahead check, sweeper, shutdown, `should_resend` | new `app/services/chatbot/inbox_queue.py` (one module, plain functions) |
| webhook copy | `app/api/v1/public/respond_webhook.py` -> `chat_turns.enqueue_direct_turn` (`app/tasks/chat_turns.py:113-152`): enqueue instead of running; drop the `not_text` skip for queue mode (`direct_ingress.py:188-191`) |
| n8n copy (spine, INJECT, Retry) | `/chat/turn` handler `app/api/v1/external/chat.py:171-`: covered and not `is_test` -> enqueue, answer `duplicate: true`, `actions: []` |
| abandon-before-state seam | engine, before `turn_tail.persist` (`engine.py:8315-8325`) |
| sender POST + log | reuse `direct_ingress.send` and its failed-log writer (`:445-504`) |
| sweeper start / shutdown hook | `app/main.py` startup and shutdown events |

## Contract (what the tests drive; internals are the coder's)

`app/services/chatbot/inbox_queue.py`, plain functions:

| Function | Behaviour |
| --- | --- |
| `queue_mode_for(db, contact_respond_id) -> bool` | True when the mode covers this contact (`direct_ingress.covers` on the settings row) |
| `enqueue(db, envelope) -> tuple[str, bool]` | insert the `queued` row or find it; returns `(turn_id, created)`; never runs the turn |
| `kick(contact_respond_id) -> None` | make sure a drain for this contact is scheduled on the pool (no-op if one is live) |
| `drain(contact_respond_id, *, session_factory=None) -> int` | run this contact's queued rows in send order until none is left or shutdown began; returns rows finished; returns 0 at once if another drain holds the contact |
| `sweep(*, session_factory=None) -> int` | one sweeper pass: recover dead `processing` rows, then `kick` every contact with `queued` rows and no live drain; returns contacts kicked |
| `begin_shutdown() -> None` / `wait_idle(timeout_s) -> bool` | stop taking rows; wait until running drains finished their current row |
| `should_resend(outcome) -> bool` | rule (a): `outcome` is the logged result of the last POST attempt, one of `"refused"` (connection refused, nothing left), `"timeout"`, `"http_error"`, `"ok"`, or `None` (attempt stamped, result never logged: a crash mid-POST). True only for `"refused"`. Flipping to rule (b) changes this one function |
| `_reset_for_tests() -> None` | clear this process's shutdown flag and local drain state (a test's "next process") |

Row states the tests read: `queued` (stage `queued`) -> `processing` -> stage `sending`
(stamped BEFORE the sender POST) -> `done`, or `failed`. Recovery of a row a dead process left
`processing`: stage `sending` means a POST may have left, so `should_resend(outcome)` decides;
any other stage means nothing was posted, so the row goes back to `queued` and runs again. A
row flagged for staff is `failed` with stage `send_unconfirmed`. Drain mutex key:
`chatbot:drain:{contact}` (Redis, TTL with heartbeat); a test deletes it to play a dead
process. Test
seams: the turn itself (`run_turn`, stub it as the S7 tests do) and the sender POST
(`direct_ingress.send`'s HTTP call), both monkeypatchable.

## Test list (tester writes red first; pytest, Postgres + real Redis like `tests/chatbot/test_s7_ordering_and_offload.py`)

1. Mode off = today (IQ-1): `/chat/turn` returns actions synchronously, no row queued, no
   sender POST; the existing S7 / direct-ingress / send-order suites unchanged.
2. Covered vs not covered, `is_test` never queued (IQ-2, IQ-3).
3. Duplicate copies (IQ-4, IQ-22): the same message via webhook, `/chat/turn` (n8n), again
   via `/chat/turn` (INJECT) and a Retry copy, in mixed order: one row, one sender POST.
4. `/chat/turn` covered: answers within 1 s with `duplicate: true`, `actions: []` while the
   turn is still running (IQ-5).
5. Photo queued via the webhook in queue mode (IQ-6).
6. Burst of 12 messages from one contact enqueued shuffled: 12 POSTs in send order, one each,
   never two of that contact running at once (IQ-8, IQ-9, IQ-10).
7. Global burst 40 contacts x 3: 120 POSTs once each, per-contact order kept, concurrency never
   above the pool size, nothing dropped (IQ-12).
8. Late earlier-sent photo while the text's turn runs: P's POST before T's, T re-ran after P,
   T's first run wrote no state (IQ-13); no earlier row -> no added wait (IQ-14).
9. Engine failure posts the error reply once and the next row continues (IQ-15).
10. `should_resend`: refused-before-send -> re-send; timeout / 5xx -> no re-send + staff flag;
    the next row continues (IQ-16).
11. Restart: rows queued and one row `processing` with an expired mutex, no live drain; the
    sweeper answers everything once, in order; the `processing` row with a logged POST attempt
    is not re-sent (IQ-17, IQ-18).
12. SIGTERM mid-turn: exactly one POST for that row, row done, later rows still queued and
    untouched; a message enqueued during shutdown is answered by the next process, in send
    order (IQ-19, IQ-20).
13. Rollback: mode switched to off with rows queued: they are still answered once; a new
    message takes the sync path (IQ-23).
14. Takeover at drain time: no POST (IQ-11).
15. Photo read not finished within 30 s in queue mode (worker down): no "could not read" reply;
    the row is answered when the read lands; the contact's later rows wait behind it (IQ-24).
16. Read job abandoned by the worker: read again once, answered once (IQ-24).
17. App shutdown handler: with a drain mid-turn, the handler returns only after the POST and
    the done mark (IQ-19).

## Zero-downtime deploy

### How prod deploys today (audit 25 Oct, read-only, file:line)

1. `deploy.yml:2004-2006`, `:2053-2103`: after the owner's approval, CI copies
   `scripts/blue_green_deploy.sh` to the server and runs it. The server compose
   `/opt/sorento-crm2/docker-compose.yml` is gitignored and hand-edited (`deploy.yml:2070-2074`).
2. `blue_green_deploy.sh:398-400`: start the NEW colour (backend runs `alembic upgrade head`,
   then `exec gunicorn`, so gunicorn is PID 1: `Dockerfile:94`, `start.sh:41-60`).
3. `:402-429`: health gate on Docker `Health.Status` of the new containers (120 x 2 s); if
   unhealthy, NEW stops and OLD keeps serving (`Dockerfile:90-91`, `curl -f /health`).
4. `:438-449`: rewrite the nginx upstream and `nginx -s reload` (graceful: new requests go to
   NEW, open ones finish on OLD).
5. `:451-453`: `sleep DRAIN_SECONDS` (30).
6. `:455-530`: `up -d --force-recreate --no-deps worker worker_fast` (old worker stops before
   the new one starts), then wait for their log lines.
7. `:532-535`: `docker compose stop` of OLD with no `-t` (compose `stop_grace_period`, Docker
   default 10 s; server value UNVERIFIED), then `rm -f`.

### What a deploy can drop today

| What | Today | Why (file:line) |
| --- | --- | --- |
| inbound webhook / `/chat/turn` arriving during the switch | not dropped | nginx reload is graceful (step 4); OLD serves until NEW is healthy |
| a 90 s sync `/chat/turn` still running on OLD | can be cut | OLD is stopped (step 7); gunicorn `graceful_timeout` unset = 30 s (`gunicorn.conf.py:42-74`), then SIGKILL; also nginx `proxy_read_timeout` 60 s default on the host (UNVERIFIED) |
| an in-flight direct-ingress turn or its sender POST | killed | the `direct-turn` pool is never drained (`chat_turns.py:75-110`); the only shutdown hook stops the scheduler (`main.py:577-585`); uvicorn re-raises SIGTERM with the default handler, so no atexit, no executor join; the row stays `processing` and its n8n copy is answered `duplicate` (`send_order.py:186-188`) |
| an RQ `media` job (a photo read) during the worker recreate | delayed, or lost if it outlives the worker's stop grace | warm shutdown finishes the current job; a SIGKILL leaves it abandoned and nothing re-runs it (no RQ `Retry`, `queue_service.py:116-160`); while the old worker stops and the new starts nothing drains `media`, so an in-turn 30 s read wait can expire |

### Design (this PR)

- **No long requests in queue mode.** Webhook and `/chat/turn` only enqueue (rule 2), so a
  deploy or nginx's 60 s read timeout has nothing long to cut.
- **Drain on shutdown (app).** The FastAPI shutdown handler calls `begin_shutdown()` then
  `wait_idle(grace)`: drains stop taking rows and finish the row they are in, including its
  sender POST and done mark. It must finish BEFORE uvicorn re-raises SIGTERM.
- **Grace above the longest turn (repo).** `gunicorn.conf.py`: `graceful_timeout = 150`
  (longest queued turn: photo read + parser + lane + sender POST, well under 120 s).
  `blue_green_deploy.sh` step 7: `docker compose stop -t 160` for OLD, so Docker does not
  SIGKILL before gunicorn's grace ends. Both files ship with the release (the script is
  copied by CI, `deploy.yml:2004-2006`).
- **Overlap is safe.** During steps 4-7 OLD and NEW both run drains and sweepers; the
  per-contact mutex and the conditional row claim keep one turn per contact and one answer per
  row. NEW's sweeper picks up queued rows within 2 s of starting.
- **Photo reads survive the worker restart (app).** In queue mode a row's photo read is waited
  for by the drain with no 30 s cap (heartbeat kept; hard cap 10 minutes), so a worker
  recreate only delays that contact's reply instead of producing "could not read it in time".
  A read job that the worker abandoned (failed with no result) is read again once.
- **Sender POST timeout.** The n8n sender now answers after its last node (switchover step 2),
  so `direct_ingress.SENDER_TIMEOUT_SECONDS` (10 s, `direct_ingress.py:62`) rises to 60 s.

### Outside the repo (owner, server; recommended, not blocking)

- `worker_fast` `stop_grace_period: 120s` in `/opt/sorento-crm2/docker-compose.yml`, so a photo
  read in flight at the worker recreate finishes instead of being abandoned (the re-read above
  covers it if not).
- Nothing on the server makes zero downtime impossible for queue mode: the nginx read timeout
  and the backend stop grace no longer matter once no request waits on a turn and the script
  passes `-t`.
- Seen, out of scope: the API process drains `notifications` on a daemon thread with a raw
  `lpop` (`queue_service.py:163-246`), so a deploy can lose one notification job in flight.

## Owner switchover (also in the PR body)

1. Merge + release with the mode `off` (inert).
2. n8n `chatbot-sender`: import if not live (`documentation/n8n/chatbot-sender.md`), Webhook
   respond "When Last Node Finishes" (today `onReceived`), credentials; on the CRM: System >
   Respond Workspaces > Chatbot sender URL + key.
3. n8n spine `THfmMmYcGzDDXBu4`: plan S6 (`PLAN-chatbot-turn-order-by-send-time.md:101-118`)
   on a clone first (its four smoke messages), then live.
4. Settings > Chatbot > Direct ingress: Listed contacts with the owner's own contact; own-phone
   test (photo then "check stock" within 3 s; a 10-message burst); then All contacts.
5. Rollback: Direct ingress Off.

## Out of scope

The CRM sending replies itself (slice 5 of the gap map), retiring the n8n producer and
dispatcher (they keep running as a second injector; their copies dedupe), failover injector.
