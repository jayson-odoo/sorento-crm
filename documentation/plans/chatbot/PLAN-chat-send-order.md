# PLAN: answer an earlier-sent photo before a later text that reached the CRM first

Status: in progress (Review, reviewer rounds 1 and 2 fixed). Track: small fix (backend only, no migration, no auth / RBAC change,
no new ingest surface, no prompt change).
UAC: `chat-send-order-acceptance-criteria.md`.
Source: prod case 24 Oct ~08:15 MYT: a forwarded product IMAGE (card printed SRTWC2350-P-RL), then
seconds later the TEXT "Pls check stock". The text's turn ran first and answered the product held
from earlier (SRT6638); two replies went out. Owner ruling 24 Oct (option c): KEEP the 26 Sep rule
"no timer, no waiting window" (`send_order.py:8-10`). Every message stays its own turn with its own
reply. NO debounce, NO merge window. Fix ONLY the order: answer by SEND time.

## Evidence (crew scout, origin/main e21e2b61bd, re-read)

- `send_order.earlier_unanswered` (`send_order.py:123-162`) knows an earlier message in two ways
  only: a `queued` turn row, or a media ledger row (`contact_media_usage`) whose extraction job is
  still queued or running (`:225-273`). A photo that has not reached `/chat/turn` and whose n8n
  media intake has not started yet is invisible to both.
- The CRM's own respond.io webhook stores EVERY message in `chat_histories` on arrival
  (`respond_webhook.py:318`, `upsert_message_row`), with `media_url` / `media_type` mapped from the
  attachment (`respond_webhook.py:212-238`) and `sent_at` derived from the message id
  (respond.io's send time in epoch microseconds). This row is the CRM's EARLIEST sight of the
  photo, and the turn path never reads it.
- Dev copy of prod: 10 of 45 image -> text pairs within 15 s had the text reach the CRM first by
  4-7 s; in 8 of them the CRM stored the text's `chat_histories` row 1-5 s before the image's
  (respond.io delivers the image late).
- Queued rows are compared on `message.message.timestamp` (ms, `send_order.sent_at_ms`). That
  value is whole seconds on real envelopes (the #1262 evidence `1790405849000`), so a photo and a
  text sent inside the same second TIE and the earlier-sent one is not answered first. The message
  id carries microseconds and breaks the tie.

## Design (no timer, no merge)

One more source for `send_order.earlier_unanswered`: **a stored-only media message**. A
`chat_histories` row of this contact that is

- incoming, a media message (`media_type` set and `media_url` set: image, audio / voice, file /
  document, sticker, video),
- sent BEFORE this turn's message by respond.io's clock (message id microseconds),
- sent at most `STORED_LOOKBACK_SECONDS` (120 s, the same staleness line direct ingress uses,
  `direct_ingress.STALE_AFTER_SECONDS`) before this turn's message, and after the send time of the
  contact's latest ANSWERED turn (a message the bot never took, e.g. while a human had the chat,
  is history, not a message on its way),
- on this conversation's channel (one contact can write on several),
- with no staff reply (`outgoing`, `sender_source` `user` or `echo`) after it: a person handled
  it (a bot reply in between does not count),
- with NO turn row (it has not reached `/chat/turn`) and NO media ledger row (n8n's media intake
  has not touched it; once it has, the existing ledger rule owns it, unchanged),

is rebuilt as an attachment envelope from this turn's envelope (same contact, channel) and
answered first, on its own turn row, exactly like the #1262 ledger path. Its caption: the
webhook now stores a captioned attachment's `description` as the row's text
(`conversation_thread_service._respond_item_text`, which also shows it in the inbox), and the
row's text counts as a caption only when it is not the typed placeholder (`[image]`,
`[file] a.pdf`), by the thread view's own rule (`_is_media_placeholder`).
A photo or voice note is READ first (`media_intake.run`, the ledger key n8n's intake uses too,
filed under the photo's own turn id, chosen before its row is inserted) and answered ahead only
once read; a read that fails or runs out leaves it to its own delivery
with no turn row, because n8n's `media-route` replies on its own to those (reviewer round 1,
S1). Then it is inserted with its message
id (the D15 unique key; an `IntegrityError` means its own delivery got there first and owns it),
run through the normal stages (the engine's own media intake reads the photo: same ledger
idempotency key, so n8n's later `/external/media/process` call replays it and nothing is charged
twice), its actions put ahead of this turn's in the one response. This turn then reads the focus
the photo left, so "Pls check stock" answers SRTWC2350-P-RL. The photo's own delivery later comes
back `duplicate: true` and sends nothing.

Send order everywhere becomes the message id's microseconds when the id is a respond.io clock,
falling back to `timestamp` (ms) as before. This fixes the same-second tie for queued rows too.

Why this and not a wait: the text's turn never waits for the photo to ARRIVE. With n8n's
dispatcher in front (S7 off, direct ingress off) the photo cannot reach `/chat/turn` while the
text's request holds the contact, so any wait for its arrival is dead time up to the timeout.
Answering it from the stored row needs nothing to arrive. The only time added to the text's
reply is the photo's own turn (its media read is the existing bounded poll,
`media_sync_wait_seconds`, inside `send_order.within_bounds`'s n8n budget), which the customer
would have waited for the photo's reply anyway. Works the same with direct ingress On or Off,
since both copies of the text land in `run_turn` and the stored row is written by the CRM webhook
either way.

## Bounds

- The existing per-turn bounds apply unchanged (`MAX_EARLIER_PER_TURN = 2`, media waits below
  n8n's 90 s `chat-turn` timeout). Worst case added to the text's reply: one photo turn, i.e. the
  media poll (`media_sync_wait_seconds`, dev 10 s) plus its parser call. A photo not read inside
  that poll is still answered on its own row (the engine's own intake outcome, same as its own
  delivery would get), never waited on further.
- No new timeout or heartbeat: nothing new waits. The ticket wait and heartbeat (`dispatch.py`)
  are untouched.

## Not covered, and accepted

- A photo whose webhook has not reached the CRM at all when the text's turn starts is still
  answered after the text. With direct ingress the text starts ~2.3 s after its own webhook, so a
  photo delivered later than that is not seen. Owner ruling 24 Oct: no waiting window, so this
  stays.
- A takeover with no agent reply yet: a photo sent while a human has the chat, handed back
  within 120 s without the agent writing, is answered by the next text's turn.
- Ledger photos still sort on the CRM's first sight (`contact_media_usage.created_at`) while
  queued and stored items sort on respond.io's send time (pre-existing since #1262, review
  round 3 N2 there); a ledger photo and a stored photo in the same window can swap.
- A rebuilt voice note carries no `duration`, so the early `denied_duration` refusal does not
  fire; the extraction enforces the same cap after download.
- A text sent before a later text but delivered after it is not covered (texts are forwarded at
  once on both paths).
