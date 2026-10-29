# PLAN: chat delivery status resolver (lane CHAT-DELIVERY-RESOLVER)

Status: in progress (small fix track: backend only, one additive column)

## Problem (measured on prod, main 02bc416d9e)

- `chat_message_resolver` (scheduled, every 60 s) is the only writer of `not_sent`
  (`app/services/chat_message_resolver.py`). Each 404 from
  `GET /v2/contact/{id}/message/{messageId}` bumped `resolve_attempts`; the 5th 404 wrote
  `not_sent` with no reason and the row was never re-checked. Five ticks = about 5 minutes
  after the send, so a respond.io lag became a permanent `not_sent` (owner's own bot replies,
  29 Oct 22:17-22:20 MYT).
- The resolver never wrote a positive status: it required a top-level `timestamp` in the
  response. Respond.io v2 returns `status` as a LIST of `{value, timestamp(ms), message?}`
  (the shape already recorded in `tests/test_respond_window_state.py`,
  `tests/test_respond_webhook_ingest.py`, `app/services/respond_messaging_service._message_timestamp`).
  Since 1 Jul prod has 0 sent/delivered/read rows.

## Fix

1. Parse the real shape: highest lifecycle value of `status[]` (pending < sent < delivered < read;
   `failed` wins) lands in `delivery_status`; `delivered_ts` / `read_ts` from those entries;
   `respond_ts` = earliest entry (creation), as `_message_timestamp` already does.
   `pending` alone writes nothing (the row stays open).
2. Non-terminal rows (NULL, `pending`, `sent`, `delivered`, `not_sent`) keep being polled on
   a backoff schedule anchored on the send time (`respond_ts or sent_at`): attempts due at
   +1, +2, +5, +15, +30, +60 min, +4 h, +12 h, +24 h (a late tick skips ahead to the next
   slot). Crew evidence 29 Oct: respond.io 404s a message until it DISPATCHES it (four bot
   replies sat in its outbound queue ~25 min). So a 404 inside the first 60 min writes only
   the reason; from 60 min it writes `not_sent`, which stays upgradable by a later 200 until
   the 24 h slot. `read` and `failed` are terminal.
3. `failed` from respond.io writes `delivery_status='failed'` with respond.io's
   `status[].message` as the reason.
4. Two new nullable columns (additive migration `cdr_0001_chat_delivery_trace`):
   `delivery_trace` JSONB = respond.io's `status[]` as returned; `delivery_error` String 512
   = `HTTP 404: <respond.io error text>` or the failed entry's `message`. Cleared on a
   positive status.
5. Only outgoing rows are polled for delivery status; incoming rows only when `respond_ts`
   is missing. Rows sent more than 48 h ago are never picked up, so this lane does not
   silently backfill the 48,861 historical NULL rows (a backfill is the owner's call).

## Out of scope

- Prod data backfill. UI (the viewer already renders `delivery_status`; a reason tooltip
  would be a separate ask).

## Tests

`tests/test_chat_message_resolver.py`, red first, recorded v2 shapes, fake client, no network.
