# PLAN: conversation thread reads local first; Respond.io only for delta sync and backfill

Lane: CHAT-LOCAL-FIRST. Owner approved 30 Sep 2026 ("go for the chat histories lane").
Status: PR open (#1402), built and tested, awaiting review + owner hand test. Track: feature (migration, new external ingest surface: security reviewer runs).
UAC: `chat-local-first-acceptance-criteria.md` alongside.

## 1. Problem

The thread view calls Respond.io on every open and on every 10 s poll
(`conversation_thread_service.fetch_thread_page`, Respond lane first, local lane only on failure).
With ~100 dealers and many salespeople in the portal, Respond.io is the bottleneck and the outage.
`chat_histories` is fed by n8n through Redis and the owner does not trust it alone ("sometimes it
will fail"), so local must be a cache that self-heals, never one that is blindly trusted.

## 2. Facts (read on origin/main d7b3a8cb)

- List is local already: `app/api/v1/public/portal_conversations.py:66` ->
  `portal_conversation_service.list_for_agent`. Kept.
- Thread page: `portal_conversations.py:80` -> `sla_service.py:5931 _thread_page_for_contact` ->
  `conversation_thread_service.py:738 fetch_thread_page`. Respond first (`integration_service.py:491
  list_messages`, 50 per page, 15 s timeout), local on failure (`:769`), every live page written back
  (`:776 _persist_best_effort`). Search is local (`:805`).
- Frontend polls: portal `ConversationThread.tsx` THREAD_POLL_MS 10 s; CRM inbox
  `useConversationsInbox.ts` list 30 s / thread 10 s, 60 s with the live stream.
- Ingest: n8n -> `POST /api/v1/external/chat-history/messages` (`external/chat_history.py:60`),
  idempotent by `(contact_id, message_id)` through the partial unique index
  (`CHAT_HISTORY_DEDUPE_PREDICATE`, `models/chat_history.py:16`). CRM sends mirrored at once
  (`mirror_outgoing_send`, `:647`). Rows lack media URL/type and `sender.source`
  (`_row_to_item`, `:183`).
- Event bus: `conversation_event_bus.publish(EVENT_MESSAGE, contact_id=<respond id>)` pokes open
  threads over Redis pub/sub (`conversation_event_bus.py:244`).
- Scheduler: APScheduler in the worker (`app/scheduler/task_scheduler.py:698 start_scheduler`),
  `ENABLE_SCHEDULER=true` on the batch worker only. Two mechanisms: DB-configured
  `scheduled_tasks` rows through `register_handler` (`:666`), and fixed `scheduler.add_job` ticks
  (`_chatbot_delegated_sweep_tick`, every minute). Per-tick DB session: `scheduler_session`.
- No cache, no 429 / Retry-After handling, no call counter anywhere on the Respond client.

## 3. Design (simplest thing that works)

### R1 Local first (`conversation_thread_service.fetch_thread_page`)
- If the contact has at least one `chat_histories` row on its channel, the page is served from the
  local keyset lane. The Respond client is not called on the request path.
- If the contact has no local row: today's behaviour (live Respond page, then stored), so a
  first open of a never-ingested contact still renders the real thread.
- `before` (scroll past the oldest stored row) when the local lane runs dry: the local page is
  returned and a delta fetch "older than the oldest stored id" is scheduled (R2), which fills the
  rows the next scroll reads. `has_more_older` stays true while the sync cursor says the oldest
  Respond page was not yet reached.

### R2 Delta sync state (new table `chat_thread_sync_state`, additive)
- One row per `(channel, contact_id)`: `oldest_reached`, `last_activity_at`, `last_synced_at`,
  `last_error`, `last_error_at`. The newest / oldest stored message ids are NOT copied here:
  `chat_histories` is the truth for those (n8n, the webhook and a CRM send all write rows
  directly, and a copied cursor would lag every one of them).
- `sync_newer(db, contact, client)`: ONE `list_messages(cursor=f"-{newest stored id}")` call,
  `persist_messages`, publish `EVENT_MESSAGE` when rows were written, stamp `last_synced_at`.
  `sync_older(db, contact, client)`: ONE call with `cursor=<oldest stored id>`, same store, sets
  `oldest_reached` when fewer than 50 came back.
- Newer: queued from `fetch_thread_page` on an in-process 2-thread pool after the local page is
  built (never blocks the render), at most once per 30 s per contact
  (`SYNC_MIN_INTERVAL_SECONDS`, a constant: one preference does not need a setting), with a
  conditional UPDATE on the state row as the race guard between processes. Older: runs INLINE in
  the scroll-back request that would run past the oldest stored row, because the page being
  asked for is the data being fetched; it is user-driven, never a poll, and the rows it fills are
  kept for ever.

### R3 Direct Respond.io webhook
- `POST /api/v1/public/respond/webhook` (`app/api/v1/public/respond_webhook.py`), under the
  public router because Respond.io cannot send the CRM's `X-API-Key`: auth is the webhook's own
  signature (HMAC-SHA256 of the raw body with `RESPOND_WEBHOOK_SECRET`, header
  `x-respond-signature` or `x-webhook-signature`, hex or base64) or, for a webhook set up with a
  custom header, `X-Respond-Webhook-Secret` equal to the secret. Unset secret = 503. The sandbox
  could not reach `docs.respond.io`, so the header names are the documented convention; the
  setup doc asks the owner to confirm them on the Respond.io page.
- Maps `message.received` / `message.sent` to the same row the n8n ingest writes through one
  shared writer (`app/services/chat_history_ingest_service.py`), so dedupe with the n8n lane is
  the existing partial unique index. Secret in the environment rather than on the workspace
  row: one deployment has one Respond.io webhook today; the second workspace pays for the
  per-row generalisation.
- Owner-side setup steps: `documentation/reference/RESPOND-WEBHOOK-SETUP.md`.

### R4 Background reconcile
- A `scheduled_tasks` row `chat_history_reconcile` (the existing DB-configured scheduler,
  `app/scheduler/task_scheduler.py` `register_handler`, seeded by the migration like
  `chat_message_resolver` in 291): every 5 minutes (the row's interval), contacts whose
  `chat_thread_sync_state.last_activity_at` is within `activity_days` (task metadata, default 7)
  get `sync_newer`, `concurrency` (metadata, default 2) calls in flight per workspace key, with
  `respond_rate_limit.py` backoff: `Retry-After` honoured, else 1, 2, 4 ... 60 s doubling per
  consecutive 429; 5xx and transport errors arm the same window; a 404 does not.
- `last_activity_at` is stamped by every lane that writes a row (n8n, webhook, CRM send mirror,
  delta reads) and seeded from the last 7 days at deploy, so load scales with contacts that had
  activity, never with viewers. A contact whose every feed is silent for `activity_days` drops
  out of the window until it is opened or a message lands.

### R5 Local gaps (additive migration on `chat_histories`)
- `media_url`, `media_type`, `media_file_name`, `sender_source`, `sender_user_id`. Filled by
  the delta/reconcile path (Respond items carry them), the direct webhook, and n8n when it sends
  them (new optional fields on `ChatHistoryMessageIngestRequest`). `_row_to_item` renders an
  attachment block and `sender.source` from the columns. Old rows fill in as the reconcile
  re-reads them (fill-if-null upsert), no one-shot script.

### R6 Observability
- `respond_call_counter`: every `RespondClient` HTTP call (one `_http()` builder with an httpx
  request hook) increments a per-minute counter (Redis `INCR`, 15 min TTL, in-process fallback)
  and logs at INFO with method and path. Read through
  `GET /api/v1/system/chat-history/respond-io-calls` (`system.chat_history.view`) so the hand
  test can show "open = at most 1, polls = 0".

### R7 UI
- No new screen. Portal and CRM inbox both read through `_thread_page_for_contact`.

### R8 Tests
- `tests/test_chat_local_first.py` (service: local-first, empty-local fallback, delta cursor
  newer/older, sync throttle, `_row_to_item` media/sender), `tests/test_respond_webhook_ingest.py`
  (signature, dedupe against n8n row, media columns), `tests/test_chat_reconcile.py` (429 backoff,
  Retry-After, concurrency cap, activity window).

## 4. Out of scope
- Rate limiting the thread routes per token (ticket in PLAN-sales-conversation-view-30sep.md).
- Configuring Respond.io itself (owner does that from the setup doc).

## 5. Build notes

- Files: migration `alembic/versions/clf_0001_chat_local_first.py`; models `chat_history.py`
  (5 columns), `chat_thread_sync_state.py`; services `conversation_thread_service.py`
  (local-first `fetch_thread_page`, `_row_to_item` media + sender, `persist_messages` fill-if-null,
  `_fill_older_if_needed`), `chat_thread_sync_service.py`, `respond_rate_limit.py`,
  `respond_call_counter.py`, `chat_history_ingest_service.py`; routes
  `public/respond_webhook.py`, `external/chat_history.py` (refactored onto the shared writer),
  `system/chat_history.py` (counter read); `scheduler/task_scheduler.py` (handler);
  `config.py` (`respond_webhook_secret`); `schemas/external/chat_history.py` (optional media and
  sender fields for n8n).
- Tests: `tests/test_chat_local_first.py` (A, B, E), `tests/test_respond_webhook_ingest.py` (C),
  `tests/test_chat_reconcile.py` (D). 56 tests. Existing thread, ingest, portal, inbox and
  Respond client suites re-run green.
- No frontend change: both the portal thread and the CRM inbox read through
  `sla_service._thread_page_for_contact`; media renders through the existing
  `describeMessageAttachments` shapes (`message.attachment.{type,url,fileName}`).
- Deviation from the ticket's first wording: the older read on scroll-back runs inline rather
  than in the background (section 3, R2) because a background fill would leave the requested page
  empty and the client with no reason to ask again.
- Process note: the migration, service and tests were written in one session (cloud sandbox,
  crew lane) rather than by separate tester / coder agents; the reviewer and security-reviewer
  passes ran as Opus agents (Phase 3) before the PR left draft.
