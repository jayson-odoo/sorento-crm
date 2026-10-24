# PLAN: n8n to direct ingress - migration gap map

Status: research (size S, no code); one crew `--ask` filed 25 Oct 2026, waiting on owner.
Origin: owner 25 Oct 05:25 after PHOTO-ORDER-SCOUT (`documentation/plans/_archive/chatbot/PLAN-photo-order-scout.md`):
no B2, the Redis queue peek rejected as coupling the CRM to n8n internals; map what it takes
for the CRM to own the whole chatbot ingress, so the photo-order fix can live in the CRM's
own queue.

## Sources and staleness

| Workflow | id | Export read | Export date | Nodes |
| --- | --- | --- | --- | --- |
| producer `sorento-main` | `NwMOBEQ1NW7LVky5` | `live-producer-sorento-main/` @ `8dd137e7` | 6 Sep 2026 | 17 |
| dispatcher `sorento-dispatcher` | `77SG9jTdVKhwMwvR` | `sorento-dispatcher/` @ `7aa98131` | 8 Sep 2026 | 15 |
| spine `sorento-consume-main S7` | `THfmMmYcGzDDXBu4` | `spine-s7/` @ `7aa98131` | 8 Sep 2026 | 34 |
| subs the spine calls | | `sub-sendmsg` @ `a686d4e3` (23 Aug), `sub-send-attachments-live` @ `3d4c79c6` (30 Aug), `sub-media-intake-live` @ `f57a1392` (30 Aug), `sub-error-logger-live` @ `b60dd163` (8 Sep) | | |

Repo: `/Users/tehjayson/Documents/foundryx/sorento_crm_n8n`, paths under
`n8n-workflows-init/export/`, read with `git show <rev>:<path>` (no checkout, no live n8n, no
prod). **Every export is 7 to 9 weeks old and may be stale against live.** Known since:
media intake folded into the CRM turn (22 Sep), the CRM chat-history feed (CHAT-LOCAL-FIRST,
30 Sep), direct ingress (#1766), the media guard (#1845). The dispatcher export names its
sub "RS-1a" while the node value is the S7 id: check live before any cutover. Never
exported, so UNVERIFIED: `sub-respond-findcontact-respond` (`D62_NHUOrugeULSFwfjEJ`),
`sub-respond-save-message-redis` (`UrETd-jm46tFj3Xw7w8vL`), `sub-add-comment-respond`
(`2l8egTLJbyGOPvG-DbtDX`).

CRM side read at main `fe9477165b`. Abbreviations: DI = `app/services/chatbot/direct_ingress.py`,
CT = `app/tasks/chat_turns.py`, RW = `app/api/v1/public/respond_webhook.py`, IS =
`app/services/integration_service.py` (all under `sorento_crm_backend/`).

## Today

```
respond.io --webhook--> n8n producer --RPUSH q:{c}, ready-contacts--> n8n dispatcher (1 s tick, lock:{c})
          --> n8n spine: media intake --> POST /external/chat/turn --> action Switch --> respond.io API
respond.io --webhook--> CRM RW (stores chat_histories; DI starts a text turn for listed contacts
          --> POST actions to n8n `chatbot-sender` --> respond.io API)
```

Direct ingress (#1766) already runs the same engine for texts of listed contacts
(`chatbot_direct_ingress_mode` off | contacts | all, `models/user.py:755-761`, read DI:127,
DI:137). n8n's copy of every message still reaches `/chat/turn` and comes back
`duplicate: true` (D15, `engine.py:2815`), so n8n is the fallback today.

## Gap table

| # | Job | n8n today (node, export) | CRM today | Work to close | Risk |
| --- | --- | --- | --- | --- | --- |
| 1 | Webhook auth | none seen: path-only `Webhook`, `Respond.io Trigger` (producer) | **yes**: HMAC-SHA256 over raw body RW:111, 401 RW:348; DI needs a real body HMAC DI:166 | none | low |
| 2 | Event / type filters | trigger `messageType [text, attachment]` (producer) | **yes**: RW:296-298; incoming DI:174, WhatsApp DI:176, staff senders denied DI:58, DI:180 | none | low |
| 3 | Human takeover gate | `If1` drops `is_human_intervened` (producer) | **yes**: respond.io contact GET, skip DI:264, DI:319 | none (one respond.io GET per message; org rate limit numbers undocumented) | low |
| 4 | Rate limit + notice | `Redis1` INCR TTL 1 s, over 30 -> `save-ratelimit-incoming` -> sendmsg notice (producer) | **partly**: 30/s skip DI:53, DI:204-235, no notice | send the notice from the CRM, or drop it | low |
| 5 | Stale message | none | **yes**: 120 s DI:50, DI:182, DI:306 | none | low |
| 6 | Dedupe | CRM's `duplicate` flag, spine head-arm | **yes**: DI:171, `engine.py:2815` | none | low |
| 7 | Failover when the webhook is down | `in-failover?` + `failover_watermark` (producer) + poller `CYNq34WZx83POLQ5` -> `sorento-main-INJECT` (`PLAN-chatbot-turn-engine.md:258`) | **partly**: `chat_history_reconcile` every 5 min stores missed rows (`app/tasks/chat_reconcile_tasks.py:37`), starts no turn | an injector that turns unanswered fresh incoming rows into turns, or keep n8n's copy as the fallback | high (missed or double answers at switch, AC-714) |
| 8 | Concat / batching | none: one popped item = one turn (`nodes/concat_queue_body.js` wraps `{message, contact}`) | none by design: own turn per message; `send_order` answers up to 2 earlier ones first (`send_order.py:70`) | none | none |
| 9 | Per-contact order | dispatcher `lock:{c}` INCR TTL 120 s around `call-spine`, spine pops one (`spine workflow.json` `redis-pop-main-message-list`) | **yes**: Redis ticket `dispatch.py:53-110`, `:243`; every turn of a covered contact takes it `engine.py:2796-2803` | retire dispatcher + lists (`PLAN-chatbot-turn-engine.md:247`) | med: dispatcher caps ~1 turn/s today; CRM pool is 8 threads per API process (CT:75) |
| 10 | Pool full | n/a | **partly**: busy -> skip, n8n copy answers (CT:143-144) | without n8n behind it, busy must queue (RQ) instead of skip | high (silent drop) |
| 11 | Media detect + read (image, voice) | `sub-media-intake`: `detect-media.js`, POST `/external/media/process` 40 s, poll 6 s x 2, `media-route` continue/reply/poll/silent, wording copy in `media-route.js` | **partly**: engine reads media itself `media_intake.py`, `engine.py:4199`, `:4347`, wait `media_sync_wait_seconds` default 30 (`models/user.py:623`), 8 concurrent waits (`media_intake.py:48`); **DI refuses media** DI:188-191 | accept media in DI; keep the media wait off the text pool; check the webhook envelope fits `detect` (UNVERIFIED, `media_intake.py:120-170`) | high (a 30 s wait holds a thread and the contact's ticket) |
| 12 | Run the turn | `chat-turn` POST `/external/chat/turn`, 90 s, no retry (spine) | **yes**: same engine, DI:324 `run_turn(offload=False)` | none | low |
| 13 | Send text: chunks + quick replies | `sub-sendmsg`: `Code in JavaScript` splits 1800 chars (1000 with buttons), buttons on the last part via `POST api.respond.io/v2/contact/id:<id>/message` `quick_reply` | **no**: "the CRM never sends" (D9, `contracts.py:411`); DI POSTs actions to n8n `chatbot-sender` (DI:334, DI:358-437); `IS:409` `send_message` has no chunking or buttons | either keep the thin n8n sender, or port the chunker (n8n has `tests/unit/sendmsg-quickreply-chunk.test.js`) + quick replies to a CRM executor | high (owner-visible format) |
| 14 | 24 h window fallback | `Wait 1s` -> `Find a Message` -> failed -> `Send Template` (sendmsg) | **partly**: `respond_messaging_service.py:568` `send_text_or_template` | wire into a CRM executor (only if 13 moves) | med |
| 15 | Send attachments | `sub-send-attachments`: POST `/external/presigned-url` (1 h), one respond.io node per mime, onError continue | **partly**: `IS:414` `send_attachment` | port (only if 13 moves) | med |
| 16 | assign_conversation | respond.io native node (spine `assign-action`) | **partly**: `IS:583` `set_conversation_assignee` | wire (only if 13 moves) | low |
| 17 | add_comment | sub `2l8egTLJbyGOPvG-DbtDX`, not exported | UNVERIFIED (no comment client found) | find the respond.io call, port (only if 13 moves) | med |
| 18 | update_contact_fields (clears takeover) | spine contact-field write | **partly**: `IS:738` `update_contact` | wire (only if 13 moves) | low |
| 19 | chat_histories rows | `sub-respond-save-message-redis` (not exported) on incoming + every outgoing part | **partly**: incoming RW:309; outgoing via respond.io `message.sent` webhook (UNVERIFIED) | outgoing rows must carry `chatbot_turn_id` (`models/chat_history.py:79`) for quoted replies | med |
| 20 | Error reply | `sub-error-logger` sends a fixed "Sorry, I couldn't process that just now..." | **yes** for a failed turn (`engine.py:3040-3047`); a failed sender POST is logged only (DI:445-504) | none while the n8n sender stays | low |
| 21 | Retry button | n/a | **partly**: re-posts to the n8n inject webhook (`dispatch.py:415`, `chatbot_retry_ingress_url`) | re-inject into the CRM's own queue | low |
| 22 | Test / dry-run egress | `dry_run`, `is_test`, Redis `test:egress:<run>` in spine + subs | **partly**: `is_test` (`models/chatbot_turn.py:86`), console ingress | eval runners that read `test:egress` need a CRM-side capture | med (eval harness) |
| 23 | Typing, labels, close | none found in the three exports | none | none | none |

## Photo order once the CRM owns the queue

The fix is the owner's option A inside the CRM: right before a direct-ingress text turn hands
its reply over (today the POST to the sender, DI:334), run `send_order.earlier_unanswered`
again (`send_order.py:178`, the check #1838 runs once at slot time, `engine.py:1938`). It reads
only CRM state: the photo's `chat_histories` row (RW:309, written on arrival) and its queued
turn row. If an earlier-sent photo is there, drop the text's draft, answer the photo, then the
text, in one hand-over. No photo = no wait. Cap = the existing `within_bounds` media budget.

Measured on the dev copy, the 50 photo-then-text pairs of PHOTO-ORDER-SCOUT (read-only,
`chat_histories.ingest_at` = arrival at the CRM's own webhook, `chatbot.turns` windows in UTC):

| When the photo reached the CRM | Today, n8n path (measured turn windows) | Direct ingress (model) | Caught by |
| --- | --- | --- | --- |
| before the text turn started | 46 | 47 | the slot check (#1838, live) |
| while the text turn ran | 0 | 3 | only the pre-send look-ahead |
| after the text reply | 4 | 0 | nothing without a wait |

Why the 4 are lost today: in all four, n8n's copy of the TEXT started its turn before the
CRM's own webhook had even stored the text (turn start minus the text's CRM arrival: -1.9,
-14.9, -3.9, -1.9 s), so the CRM could not see a photo that its webhook delivered later.
Across the 50 pairs the n8n path starts the text turn a median 2.4 s after the text's CRM
arrival (mean 3.0 s). Direct ingress starts it ~2.3 s after the CRM webhook
(`PLAN-chat-send-order.md:93`) and never before it, so the model above uses start = text's
CRM arrival + 2.3 s and each turn's measured duration (UNVERIFIED as a forecast: respond.io's
own delivery lag, p90 ~16 s for both kinds, still puts some photos after a reply, and those
stay unanswered-first under the no-wait ruling).

So the look-ahead is what turns direct ingress into a photo-order fix (3 of the 50 need it),
and it needs neither media in DI nor a CRM sender: it can ship first.

## Rollout (uses #1766's listed-contacts switch)

| Slice | What | Size | Depends on |
| --- | --- | --- | --- |
| 1 | Pre-send look-ahead in DI (above), red tests on the three timing shapes in the table | S (~150 lines + tests) | none |
| 2 | Media in DI: drop the `not_text` skip, own small pool for media turns so text turns never wait behind a read, envelope check | M | 1 |
| 3 | Pool full -> queue (RQ), not skip; Retry re-injects into the CRM | S-M | 2 |
| 4 | Failover injector (rows the webhook missed become turns), retire poller + `failover_watermark` | M | 3 |
| 5 | CRM executor for all five action kinds (rows 13-19), retire n8n `chatbot-sender` | L | owner Q1 |
| 6 | Unpublish producer, dispatcher, spine once `all` runs clean | S (n8n, owner) | 1-4 |

Switch order: `contacts` with the owner's own number -> a few active dealers -> `all`.
While the producer still runs, n8n's copy stays the D15 fallback (a skipped or failed direct
turn is answered by n8n), so each step is reversible by editing the contact list.

## What stays in n8n

- After slice 6: the thin `chatbot-sender` (`documentation/n8n/chatbot-sender.md`) unless
  slice 5 is built, and every non-chatbot workflow (for example `sla-scheduled-escalation`).
- Nothing of the three chatbot workflows.

## Owner questions (filed as one `--ask`)

1. Reply sending: (a) keep the thin n8n `chatbot-sender` as the only n8n piece (no queue, no
   order, no state), (b) the CRM sends itself (slice 5, reverses D9). Recommendation: (a) now:
   it already works for direct ingress, holds none of the queue coupling the owner rejected,
   and slice 5 is the largest, most visible slice; build (b) when there is a reason.
2. Media pool: (a) a second small pool for media turns, same inline wait, (b) one bigger shared
   pool, (c) photos stay on n8n until later. Recommendation: (a): a 30 s read never blocks a
   text turn, and it reuses the existing wait.
3. Failover: (a) keep the n8n producer as the fallback copy until `all` has run clean for two
   weeks, then decide, (b) build the CRM injector (slice 4) before `all`, (c) no failover, alert
   only. Recommendation: (a): D15 already makes the double copy safe.
4. Pilot gate: (a) own number 3 days -> 5 active dealers 1 week -> `all`, gate = zero
   `busy` / `failed` direct skips and no reply answered by n8n's copy, (b) own number then
   `all`. Recommendation: (a).
