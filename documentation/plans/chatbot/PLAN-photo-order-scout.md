# PLAN: PHOTO-ORDER-SCOUT - a photo sent before a text arrives after it

Status: blocked on a prod fact (owner ruled A 25 Oct; A is not provably effective on the dispatcher path from the repo alone, see "Prod-path verification"); no build yet

## Problem (prod, 25 Oct 2026 02:34 MYT)

Verified by crew from n8n executions 21638407 / 21638413 of producer `sorento-main`
(`NwMOBEQ1NW7LVky5`):

| Message | respond.io timestamp | Webhook received | Lag |
| --- | --- | --- | --- |
| Photo (image) | 02:34:25.8 | 02:34:34.8 | 9.1 s |
| Text "Check stock" | 02:34:28.8 | 02:34:32.4 | 3.6 s |

The text reached the bot 2.4 s before the photo, so the bot answered "Check stock" from a stale
open task, then answered the photo separately. The photo payload had `isPending=false`.

Owner rulings: no blanket hold on texts, no merge window. Photo-first only IF we can know a
photo is coming.

## Research questions

1. respond.io webhook/event model for incoming media: any earlier event or payload field
   (`isPending=true`, a status event) that fires before the media is ready?
2. Does our n8n producer trigger or the CRM webhook filter or ignore `isPending` / other event
   types?
3. respond.io API: can we list a contact's latest messages (endpoint, auth, rate limits, does a
   pending media message appear before its webhook)?
4. Options: A) signal-gated hold, B) no wait, re-answer the text for a late photo; plus the
   turn-age / state rule for a bare "check stock" reusing a stale open task.

## Findings

Sources: code at main `fe9477165b`; n8n export via `git show feat/s7-producers:...` (repo
`sorento_crm_n8n`, not checked out); dev copy `sorento_cagent_stack`, read-only
(`chat_histories` to 15 Oct, `chatbot.turns` 5 Sep to 16 Oct). No respond.io API call, no
prod read. Contacts are masked A to F; dev row ids are given so crew can re-check.

### 1. respond.io sends no earlier signal for an incoming photo

- Webhook events (help page): New Contact, New Incoming Message, New Outgoing Message, New
  Comment, Contact Updated, Assignee Updated, Tag Updated, Conversation Opened/Closed, Call
  Ended. No pending, placeholder or "media processing" event. "Events are processed in order",
  retries at 30/60/90 s, dropped after 3 min. https://respond.io/help/integrations/webhooks
- `isPending` is not documented on any page we could read. developers.respond.io is a
  Stoplight SPA that serves no content without a browser (curl returned the shell only), so
  the v2 message schema is UNVERIFIED. The field sits on `message.message.attachment`
  (repo sample `tests/chatbot/replay_turns/prod_sample/check-promotion-900000008-chain-001-no-run-id.json:3794`,
  next to `source_url`, `mime`, `size`): it reads as "attachment upload not finished".
- Measured: of 565 stored turn envelopes carrying the field, **0** have `isPending: true`
  (`select count(*) from chatbot.turns where envelope::text ~ '"isPending": *true'`).
  Nothing in our pipeline drops such an event (section 2), so respond.io does not send a
  media `message.received` before the file is ready.
- Measured webhook lag (`ingest_at - sent_at`, incoming, since 6 Oct): text p50 7.1 s /
  p90 15.1 s (n=8276); image p50 7.8 s / p90 16.0 s (n=172). The photo is not late by a
  fixed media delay; both kinds jitter by seconds, so close pairs swap at random.

### 2. Our pipeline filters nothing relevant

- n8n producer: `Respond.io Trigger` accepts `messageType: ["text","attachment"]`
  (`workflow.json`, trigger node params); the plain `Webhook` node passes the body through
  (`nodes/webhook-to-respond-convert.js:2`). No IF on `isPending`, status, type or direction;
  only drops are `If1` (human intervened) and `If` (Redis rate limit 30/s). Both kinds go
  `concat_queue_body.js:4-5` -> RPUSH `q:<contactId>` -> `ready-contacts`. Arrival order, no
  debounce, no send-time ordering. `git grep -i isPending` on the branch: 0 hits.
- CRM webhook: `MESSAGE_EVENTS = {"message.received","message.sent"}`
  (`app/api/v1/public/respond_webhook.py:61`); other event types ignored at `:296-298`.
  `isPending` is never read (0 hits in `app/`). Dedupe by (contact, message id) (`:310`).
- Direct ingress starts a text turn at once and never takes media:
  `direct_ingress.py:188-191` (`not_text`); media stays on the n8n path.
- Send-order already exists: `send_order.py` (CHAT-SEND-ORDER #1838, live since the
  24 Oct 13:40Z release). At the turn's slot, `earlier_unanswered`
  (`send_order.py:178`, called `engine.py:1938`) answers an earlier-sent photo the CRM
  already stored (`_stored_only_media` `:415`, lookback 120 s `:66`). It looks ONCE, at slot
  time. On 25 Oct the photo was stored ~2.4 s after the text turn started, so the rule could
  not see it. The floor `_latest_answered_send_ms` (`:395`) then makes the photo history for
  later turns.

### 3. respond.io API: list messages exists, no help

- `GET /v2/contact/{identifier}/message/list` (limit, cursorId), Bearer token: third-party
  listing only (https://www.withone.ai/knowledge/respond-io?page=2), method UNVERIFIED.
- Rate limits are per organisation, 429 with `Retry-After` / `X-RateLimit-*` headers; numbers
  NOT DOCUMENTED. Whether an in-flight media message appears before its webhook: NOT
  DOCUMENTED. Polling it on every bare text is a hold by another name plus API cost: dropped.

### 4. How often, and what the bot does today (dev copy)

Pairs "photo, then a text within 20 s, same contact": 49 (23 contacts). Arrived in the wrong
order at the CRM: **9 of 49**; among pairs sent at most 4 s apart: **9 of 19**. Every inverted
text was a bare intent ("Got stock?", "Check stock", "This one", "10 unit", "THIS GOT STOCK
X1"). In 8 of the 9 the text was answered first from held products or with a filter ask.

The held products were the contact's LAST topic every time (0 or 1 user message between),
aged 18 s, 37 s, 2.5 min, 3.4 min, 11.5 min, 43 min, 2.5 h, 3.4 h. Held state has no age
rule: `focus` carries products and domains with no TTL (`turn_runtime.py:1091` `load_state`;
`turn/apply.py:3308` reuses `focus.domains`; `Task.touched_at_turn` `turn/task.py:91` only
orders tasks; the only expiry is `OFFER_TTL = 3` `turn/pending.py:313`, escalation offers).
So a turn-count rule would fire on none of the 8; a wall-clock idle rule would catch the
43 min, 2.5 h and 3.4 h cases.

CORRECTED 25 Oct (after the owner ruled A): an earlier draft said "6 of 9 text replies went
out after the photo was stored". That compared the photo's store time with the bot reply's
respond.io delivery time, which includes n8n's send step. Against the text TURN window
(`chatbot.turns.started_at/finished_at`, read in UTC) the real split, all 50 photo-then-text
pairs: photo stored BEFORE the text turn started 46, AFTER it finished 4, DURING it **0**
(average text turn 4.4 s). The 46 are what #1838's slot-time check already answers.

## Behaviour card (filed as one crew `--ask`)

### Options

- **A. Re-check at reply time (signal-gated, no timer).** respond.io gives no early signal,
  but our own store does. Right before a text turn sends its reply, run the same
  `_stored_only_media` check again. If an earlier-sent photo of this contact is stored now,
  drop the text's draft and answer photo first, then the text (what #1838 already does at
  slot time). No photo stored = no wait at all. Cap: the existing `within_bounds` media
  budget. CORRECTED: on dev data it catches 0 of 50 pairs beyond what #1838 already
  catches (see the correction in section 4).
- **B1. Late photo takes the answered text as its caption.** A photo with no caption whose
  send time is before an already-answered text of the same contact, sent at most N s after
  it, and that text named no product of its own: read the photo with that text as its
  caption (existing caption path, `send_order._caption` `:516`, `media_intake.py:272`) and
  reply "Re your photo: ...". Fixes the photo reply in all 9; does not stop a wrong first
  reply.
- **B2. A bare intent after idle does not reuse held products.** A message with no product of
  its own ("check stock", "10 unit") does not carry `focus` products when the contact's
  previous turn finished more than T minutes ago; it asks "Which product?" as if nothing were
  held. Rule sits in `load_state` (`turn_runtime.py:1091`) beside `pending.tick`.

### Examples (dev copy, masked)

1. Contact E, 13 Oct, dev rows 103781/103780. Photo 08:02:20, "Check stock" 08:02:21; text
   stored 1.1 s before the photo. Today: "That would search every stock we have - I need at
   least one filter...", then "I read SRTHD122, SRTSWT3001, Sensor Tap and Clinical Tap from
   that photo. Stock summary...". Photo stored 1.0 s BEFORE the text turn started, so #1838
   (live since 24 Oct) already answers the photo first today; A adds nothing. B1: same
   two replies, the second prefixed "Re your photo:". B2: no change.
2. Contact F, 15 Oct, rows 109304/109303. Photo 03:14:57, "10 unit" 03:15:00. Today:
   "SRTSH22613 x 10: Got stock" (a product from 43 min earlier), then "I read CB85-CR-DIY from
   that photo. How many units of CB85-CR-DIY?" (the 10 is lost; customer retypes). Photo stored 0.7 s
   before the text turn started: #1838 already answers photo first, then "10 unit"; A adds
   nothing.
   B1: wrong first reply stays, second becomes "Re your photo: CB85-CR-DIY x 10: No stock...".
   B2 (T=30): reply 1 becomes "Which product?" instead of the wrong SRTSH22613 answer.
3. Contact G, 11 Oct, rows 95651/95650. Photo 06:04:24, "Got stock?" 06:04:27; photo stored
   2.1 s after the text TURN finished. Today: stock summary for SRTBF11833 (held
   from 2.5 min earlier), then "I read SRTBF11621, SRTMCB21621, SRTWB1150, SRTWT5841-BL and
   SRTW2600 from that photo. Stock summary...". A as a DB re-check: misses (turn over
   before the row landed); a queue peek: UNVERIFIED (n8n receipt time not in the dev copy). B1: second reply prefixed "Re your photo:". B2: no change (2.5 min). Wrong first
   reply stays under every option: the limit of a no-wait design.
4. Contact A, 15 Oct, rows 111517/111518 (text FIRST, photo 1 s later). "Pls check stock"
   was answered with "Couldn't find SRTWC8605-RL. Did you mean..." (read from a photo 4 h
   earlier), then the 11-code stock summary. A and B1: do not apply (text really was first).
   B2: reply 1 becomes "Which product?", then the photo answers stock (owner rule R2).

### Questions

1. Which option set? (a) A + B1 + B2, (b) B1 + B2 (the brief's B), (c) A + B2.
   Recommendation as filed: (c) A + B2 (owner ruled A 25 Oct). CORRECTED basis: the "6 of 9"
   was mis-measured; see "Prod-path verification" for what A needs; B2 is one
   condition and also fixes text-first cases like example 4. B1 adds a third mechanism to
   relabel a reply whose content today is already right (the photo turn inherits the stock
   domain via `turn/apply.py:3308`, seen in examples 1 and 3); its only real gain is the lost quantity (example 2).
2. B2 idle line T: (a) 30 min, (b) 60 min, (c) end of the WhatsApp 24 h window.
   Recommendation: (a) 30 min: catches 43 min / 2.5 h / 3.4 h, spares 18 s to 11.5 min.
3. A, when the photo is found: (a) drop the text's draft, answer photo then text (one
   combined send, as #1838), (b) send the text's draft anyway and answer the photo after.
   Recommendation: (a): (b) is today's wrong reply.
4. If B1 is chosen: window N and wording? (a) N = 20 s, "Re your photo: ...", no apology for
   the earlier reply, (b) N = 20 s plus "(ignore my answer about <code> above)".
   Recommendation: (a): every measured inversion was at most 4 s apart; the pair search used
   20 s.

## Prod-path verification (25 Oct, owner ruled A)

Prod ingress (owner; `PLAN-chat-send-order.md:71`, S7 off, direct ingress off): respond.io ->
n8n producer -> RPUSH `q:{contact}` + `ready-contacts` -> `sorento-dispatcher`
(`77SG9jTdVKhwMwvR`) -> spine -> `/chat/turn`. From the repo exports only:

- Producer RPUSHes every message on arrival, no lock: `concat_queue_body.js:4-5` -> Redis2
  RPUSH `q:<contactId>` (export `live-producer-sorento-main`, branch `feat/s7-producers`).
- Dispatcher: Schedule Trigger every 1 s, `pop-ready-contacts` -> `get-lock` / `incr-lock`
  (`lock:{contact}`, TTL 120 s) -> `call-spine` -> `del-lock` (export `sorento-dispatcher`,
  commit `7aa98131`). The spine pops ONE entry: `workflow.json:4463-4464`
  (`list q:{{contact}}`, `operation pop`, export `live-spine-sorento-consume-main`).
- So while the text turn runs, a photo that reached n8n is in Redis `q:{contact}` for certain.
  It is in `chat_histories` only if the CRM's own respond.io webhook (a separate respond.io
  subscription, `documentation/reference/RESPOND-WEBHOOK-SETUP.md`, writer
  `respond_webhook.py` -> `chat_history_ingest_service.upsert_message_row`) has delivered it;
  that delivery is independent of n8n and of the dispatcher. n8n's own incoming-row write
  sits in the spine, after the pop (`clone-sorento-consume-main-TEST/workflow.json:6270`,
  live export is from 6 Sep: UNVERIFIED for today).
- Dev cases' ingress: every text turn of the 9 inverted pairs has `ingress = 'webhook'`
  (= n8n `/chat/turn`); the dev copy has no `respond_webhook` (direct ingress) turn at all.
  The photo rows' `ingest_at` there is the CRM direct webhook's (or n8n's, whichever wrote
  first; both stamp it, `chat_history_ingest_service.py:142`).
- The CRM backend never reads `q:{contact}` or `ready-contacts` (grep `app/`: 0 hits).
  Whether CRM `REDIS_URL` and n8n's `sorento-redis` credential are the same server: NOT in
  the repo (compose has no redis service; the export carries credential names only).

Consequence for A:
- A as a DB re-check (re-run `_stored_only_media` before the reply): buildable, but dev data
  shows 0 of 50 photos stored during a text turn, so it would add close to nothing over
  #1838. Whether the 25 Oct photo's row landed during the text turn is a prod read (UNVERIFIED).
- A as a queue peek (LRANGE `q:{contact}` before the reply, earlier-sent attachment entry):
  matches the 25 Oct shape (photo at n8n 2.4 s after the text, turns ~4.4 s), but needs the
  CRM to read n8n's Redis and couples the CRM to a queue the turn-engine plan retires
  (`PLAN-chatbot-turn-engine.md:247`). Not buildable until the Redis fact is confirmed.

### Owner checks prepared (25 Oct; owner runs them, crew has no prod access)

1. SQL (crew state, not in the repo): `crew/state/prod-steps/prod-step-photo-order-check.sql`,
   READ ONLY + ROLLBACK, fill the contact id or the last 6+ phone digits once. Q3 prints the
   verdict per photo: BEFORE / DURING / AFTER the text turn. Parsed clean on the local clone
   `sorento_prod_1020` (placeholder left in, 0 rows); functional run on the dev copy (13 Oct
   pair) printed `BEFORE text turn start`, which matches the earlier measurement.
2. Redis: the CRM reads `REDIS_URL` (`app/config.py:227`, `redis_url`), used by
   `app/services/queue_service.py:44` (`redis_conn`), which the chatbot ticket uses
   (`app/services/chatbot/dispatch.py:177`). Compare its host, port and db index with n8n's
   `sorento-redis` credential (Host, Port, Database Number). Prod compose lives on the server
   at `/opt/sorento-crm2/docker-compose.yml` (`.github/workflows/deploy.yml:2071-2073`).

### Not covered (seen while measuring, out of scope)

- Duplicate photo replies (15 Oct 04:14:48 + 04:15:01; rows 96727 02:30:36 +
  02:31:02).
- A brand word read as a product from a photo ("I read SORENTO from that photo"), and a
  quantity in the text ("Check stock 2 pcs") not applied to the photo's codes.
- Prod check owed (crew/owner, not this lane): the 25 Oct text reply time in n8n exec
  21638407, to confirm A would have caught it (reply later than 02:34:34.8 + store time).
