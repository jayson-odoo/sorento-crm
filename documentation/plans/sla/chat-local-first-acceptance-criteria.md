# UAC: chat local first (lane CHAT-LOCAL-FIRST)

Plan: `PLAN-chat-local-first-30sep.md`.

## A. Local first
- AC-LF1 A thread page for a contact with stored rows is served from `chat_histories` and makes
  zero Respond.io HTTP calls on the request path.
- AC-LF2 A thread page for a contact with no stored rows fetches one live Respond page, stores it,
  and returns it (today's behaviour).
- AC-LF3 A Respond.io failure (timeout, 5xx, 429) on the AC-LF2 path still returns the (empty)
  local page with `source: local`; the request never 500s.
- AC-LF4 The 10 s poll (portal thread, CRM inbox thread) costs zero Respond.io calls while the
  contact's cursor was synced within the last `chat_sync_min_interval_seconds`.

## B. Delta sync
- AC-DS1 Opening a thread schedules at most ONE Respond.io delta call (newer than the stored
  cursor) after the local page has been returned.
- AC-DS2 New rows from a delta fetch are upserted by `(contact_id, message_id)` and a `message`
  event is published on the conversation event bus for that contact.
- AC-DS3 Scrolling past the oldest stored row schedules at most one Respond.io call older than
  the stored oldest id; when fewer than a full page returns, `oldest_reached` is set and no more
  older calls are made for that contact.
- AC-DS4 The cursor row records `last_synced_at`, `newest_message_id`, `oldest_message_id`.

## C. Direct webhook
- AC-WH1 A Respond.io message webhook with a valid signature writes the same row the n8n ingest
  writes; the same message arriving from both lanes resolves to one row.
- AC-WH2 An invalid or missing signature (and no matching shared secret) is 401 and writes nothing.
- AC-WH3 A webhook carrying an attachment stores `media_url`, `media_type`, `media_file_name`;
  a webhook from a bot / agent stores `sender_source` (and `sender_user_id` for a user).
- AC-WH4 A new row from the webhook publishes the `message` event; a duplicate does not.

## D. Reconcile
- AC-RC1 The reconcile tick selects contacts with a `chat_histories` row within
  `chat_reconcile_activity_days` and runs `sync_newer` for each.
- AC-RC2 At most `chat_reconcile_concurrency` Respond.io calls are in flight per workspace token.
- AC-RC3 A 429 with `Retry-After: N` pauses that token for N seconds; without the header the
  wait doubles per consecutive 429 (1, 2, 4, ... capped at 60 s) and resets on success.
- AC-RC4 The tick never raises out of the scheduler; a failing contact is recorded on its cursor
  row (`last_error`, `last_error_at`) and the next contact still runs.

## E. Local row fidelity
- AC-RF1 `_row_to_item` renders an attachment block (`message.type`, `message.attachment.url`,
  `type`, `fileName`) from the new columns when present, text otherwise.
- AC-RF2 `_row_to_item` renders `sender.source` from `sender_source` (`contact` for incoming
  rows with no stored source, as today).
- AC-RF3 A row stored before this lane (no media columns) is filled on the next delta/reconcile
  read of that message (fill-if-null), not by a one-shot script.

## F. Observability
- AC-OB1 Every Respond.io HTTP call increments a per-minute counter and logs its path.
- AC-OB2 `GET /api/v1/system/respond-io-calls` returns the current and previous minute's counts.
- AC-OB3 Hand test: opening a portal thread with history reads instantly, the counter shows at most
  1 call for the open and 0 for the following polls.

## G. Migration
- AC-MG1 One additive migration: new columns on `chat_histories`, new table
  `chat_thread_sync_cursors`, three settings columns on `system_settings`. Single alembic head.
