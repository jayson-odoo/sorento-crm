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
2. Non-terminal rows (NULL, `sent`, `delivered`) keep being polled on a backoff schedule
   anchored on the send time (`respond_ts or sent_at`): attempts due at +1, +3, +8, +23,
   +83 min, +4 h, +12 h, +24 h. Only a 404 on the last attempt (24 h after the send) writes
   `not_sent`. `read`, `failed`, `not_sent` are terminal.
3. `failed` from respond.io writes `delivery_status='failed'` with respond.io's
   `status[].message` as the reason.
4. Reason: new nullable column `chat_histories.delivery_error` (String 512, additive
   migration). Written on `failed` and `not_sent`: `HTTP 404: <respond.io error text>`.
5. Only outgoing rows are polled for delivery status; incoming rows only when `respond_ts`
   is missing. Rows sent more than 48 h ago are never picked up, so this lane does not
   silently backfill the 48,861 historical NULL rows (a backfill is the owner's call).

## Out of scope

- Prod data backfill. UI (the viewer already renders `delivery_status`; a reason tooltip
  would be a separate ask).

## Tests

`tests/test_chat_message_resolver.py`, red first, recorded v2 shapes, fake client, no network.
