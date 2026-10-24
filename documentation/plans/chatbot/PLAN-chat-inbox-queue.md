# PLAN: CHAT-INBOX-QUEUE - the CRM owns each contact's message queue

Status: Plan (size L, feature track: new ingest behaviour, security-reviewer required). Ships
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

## Zero-downtime deploy

(Filled from the deploy audit before the coder starts; see IQ-19 to IQ-21.)

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
