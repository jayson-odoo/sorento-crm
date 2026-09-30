# PLAN: conversation thread reads local first; Respond.io only for delta sync and backfill

Lane: CHAT-LOCAL-FIRST. Owner approved 30 Sep 2026 ("go for the chat histories lane").
Status: in progress. Track: feature (migration, new external ingest surface: security reviewer runs).
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

### R2 Delta sync cursor (new table `chat_thread_sync_cursors`, additive)
- One row per `(channel, contact_id)`: `newest_message_id`, `newest_sent_at`,
  `oldest_message_id`, `oldest_sent_at`, `oldest_reached` (bool), `last_synced_at`,
  `last_error`, `last_error_at`, `updated_at`.
- `sync_newer(db, contact, client)`: ONE `list_messages(cursor=f"-{newest_message_id}")` call
  (or the newest page when no cursor), `persist_messages`, publish `EVENT_MESSAGE` when rows were
  written, advance the cursor. `sync_older(db, contact, client)`: ONE call with
  `cursor=oldest_message_id`, same store, sets `oldest_reached` when fewer than 50 came back.
- Triggered from the thread page routes as a FastAPI `BackgroundTask` after the local page is
  returned (never blocks the render). Throttled per contact through the cursor row's
  `last_synced_at` (a poll within `chat_sync_min_interval_seconds`, default 30 s, schedules
  nothing) so a 10 s poll costs zero Respond calls.

### R3 Direct Respond.io webhook
- `POST /api/v1/external/chat-history/respond-webhook`, mounted beside the n8n ingest, auth by
  Respond's webhook signature (`X-Webhook-Signature`, HMAC-SHA256 of the raw body with the
  workspace signing key; the exact header name is verified against Respond's docs in the build
  and recorded in section 6) with a shared-secret header as the fallback when no signing key is
  configured. Maps the `message.received` / `message.sent` event body to the same row
  `ingest_chat_message` writes (one shared function `_upsert_chat_history_row`), so dedupe with
  the n8n lane is the existing partial unique index.
- Owner-side setup steps documented in `documentation/reference/RESPOND-WEBHOOK-SETUP.md`.

### R4 Background reconcile
- Fixed APScheduler tick `_chat_history_reconcile_tick` every `chat_reconcile_interval_minutes`
  (default 5): contacts with a `chat_histories` row in the last `chat_reconcile_activity_days`
  (default 7) get `sync_newer`, `chat_reconcile_concurrency` (default 2) at a time per workspace
  token, with exponential backoff on 429 honouring `Retry-After` (`respond_rate_limit.py`).
- Load scales with contacts that had activity, never with viewers.

### R5 Local gaps (additive migration on `chat_histories`)
- `media_url`, `media_type`, `media_file_name`, `sender_source`, `sender_user_id`. Filled by
  the delta/reconcile path (Respond items carry them), the direct webhook, and n8n when it sends
  them (new optional fields on `ChatHistoryMessageIngestRequest`). `_row_to_item` renders an
  attachment block and `sender.source` from the columns. Old rows fill in as the reconcile
  re-reads them (fill-if-null upsert), no one-shot script.

### R6 Observability
- `respond_call_counter`: every `RespondClient` HTTP call increments a per-minute counter
  (Redis `INCR` with 120 s TTL, in-process fallback) and logs at INFO with the path. Read through
  `GET /api/v1/system/respond-io-calls` (admin) so the hand test can show "open = 1, polls = 0".

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
(filled as work lands)
