# PLAN: n8n to direct ingress - migration gap map

Status: research (size S, no code). Owner 25 Oct: 05:35 Q1 (a) keep the thin n8n sender, no pilot, one switchover; 05:45 burst Q3 NOT accepted, the CRM must own a real queue. Section "CRM-owned queue" filed as one crew `--ask`, waiting on owner.
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

## Owner's design: remove the dispatcher's queue, the CRM queues (25 Oct 05:35)

CRM half SUPERSEDED by "CRM-owned queue" below (owner 05:45: the synchronous ticket with its
30 s clamp is not accepted for bursts). The n8n facts and the S6 analysis here still hold.

Question: "can I just remove the queue from the dispatcher and let the CRM handle the
queue?" Answer: **yes, and the CRM half is already built.** This is the turn-engine plan's S7
(`PLAN-chatbot-turn-engine.md:231-248`, AC-714 at `:252-256`): the injectors stop handing the
message to the dispatcher and call the spine themselves; the CRM's per-contact ticket orders
the turns.

### What already exists in the CRM

- S7 switch `system_settings.chatbot_ordering_enabled` (`models/user.py:747-753`, read
  `engine.py:9881-9897`, `app/api/v1/external/chat.py:19-22`): every `/chat/turn` takes the
  per-contact ticket (`engine.py:2796-2803`, `dispatch.py:243`) and the CRM owns the tail
  (`/complete` answers 410). Precondition: every lane the CRM may delegate is in
  `chatbot_completed_lanes`, or such a turn fails (`engine.py:7751-7770`).
- Dev copy (read-only): `chatbot_ordering_enabled = true`, 13 completed lanes, and 0
  `delegated` turns since 1 Oct (10,431 done). So the CRM side of S7 looks ON already;
  prod value UNVERIFIED (Settings screen shows it).
- With the dispatcher in front, the ticket never sees two turns of one contact at once,
  which is why it changes nothing today.

### What the dispatcher does today (all of it)

`sorento-dispatcher` export @ `7aa98131`, 15 nodes: a 1 s Schedule Trigger pops ONE contact
from `ready-contacts`, takes `lock:{contact}` (INCR, TTL 120 s), calls the spine with
`contact` and waits, deletes the lock, re-arms if `q:{contact}` still has items. Nothing
else: no concat, no media, no send, no retry, no logging. Side effect: new turns start at
about 1 per second machine-wide (`PLAN-chatbot-turn-engine.md:231-233`).

### Exact changes

n8n (owner clicks, about 10 minutes):

1. `sorento-main` (`NwMOBEQ1NW7LVky5`): copy the dispatcher's `call-spine` node (Execute
   Workflow -> `sorento-consume-main S7` `THfmMmYcGzDDXBu4`) into the producer. Set its input
   `contact` to `{{ String($('If1').first().json.id) }}` (the same value `push-ready` pushes
   today) and turn **Wait for sub-workflow completion OFF**. Rewire `Redis2 -> push-ready` to
   `Redis2 -> call-spine`, delete `push-ready`. Publish.
2. `sorento-main-INJECT` (`sk0zN90Cas4Y6Y2w`, the failover poller's injector, also the
   Retry target): the same two edits, same minute.
3. Leave `Redis2` (RPUSH `q:{contact}`) in place: the spine's first node already pops
   `q:{contact}` (`spine-s7` `redis-pop-main-message-list`), so **the flip itself needs no spine change**.
   Each message is pushed once and popped once by the spine run that was started for it.
4. After `ready-contacts` is empty (the dispatcher drains what was queued at the switch),
   deactivate `sorento-dispatcher` (`77SG9jTdVKhwMwvR`).
5. **Fold in plan S6** (spine stops reading media; owner steps verbatim in
   `PLAN-chatbot-turn-order-by-send-time.md:101-118`), only if the live spine still has a
   `media-intake` node (the owner believes n8n no longer reads photos; the exports and
   `send_order.py:18-19` say it still did; live UNVERIFIED, one glance at the spine settles
   it): delete `media-intake` and `media-gate` and wire `redis-pop-main-message-list` to
   `tf-message`; delete `if-message-is-audio` (both outputs to `chat-turn` and the save call);
   `chat-turn` body `{envelope: <message>}` with NO `media` key (with it the CRM skips its own
   read, `media_intake.patched_upstream`, `engine.py:4198`, `:4320-4330`); save-message stores
   the caption; archive `sub-media-intake` (`B3rBMtABou6FpY69`). Their step 5 (clone smoke:
   photo only, photo + caption, voice note, denied number) stays: a test, not a pilot.

Unchanged in n8n: auth-less webhook + trigger, rate limit (`Redis1`/`If`), takeover drop
(`If1`), failover gate + poller, findcontact, the rest of the spine (`/chat/turn`, action
Switch, send subs, 24 h template fallback, error logger, chat-history save), the thin
`chatbot-sender`.

CRM (one small lane, small fix track, ~150 lines + tests): the **pre-send look-ahead**.
Before a turn returns its reply, run `send_order.earlier_unanswered` once more
(`send_order.py:178`; today it runs once, at the slot, `engine.py:1938`). With S6 folded in,
the photo's own `/chat/turn` arrives within about a second of n8n getting it and waits on the
ticket as a queued turn row, so the EXISTING queued-row rule (earlier-sent by respond.io send
time, claimed with one conditional UPDATE, `send_order.py:12-17`, `:125`) finds it; no bound
changes. If found: drop this turn's draft, answer the photo (the engine reads it in-turn,
`media_intake.run` `media_intake.py:266`, called `engine.py:4347`, on the RQ `media` worker
`media_extract/service.py:435`, `:454-471`, waiting up to `media_sync_wait_seconds` 30 s),
then re-run this message, one response (card Q3 (a)). Nothing found = no wait. Cap:
`within_bounds` (n8n's 90 s). Without S6 the look-ahead would instead have to widen the
ledger rule to photos whose n8n read started after this turn arrived
(`send_order.py:318-322`), and could still only take a photo n8n has finished reading, because
n8n's `media-route` replies on its own when its read fails or outlives its wait
(`engine.py:2009-2012`); that is the double-reply guard.

### Where the photo is read

The CRM's RQ `media` worker reads it either way (`media_extract/service.py:435`, `:454-471`);
the question is who WAITS for that read before `/chat/turn`. Today n8n's
`sub-media-intake` calls `/external/media/process` and waits (about 23 s per the crew's
measurement) before `/chat/turn`, and the CRM skips its own intake (`patched_upstream`).
With S6 the spine calls `/chat/turn` at once and the engine waits inside the turn.

Does S6 alone (dispatcher still on) shrink the photo-arrives-late window? **No, not for the
inverted case.** The dispatcher's `lock:{contact}` keeps the photo's spine from starting until
the text's spine has finished, so the photo stays invisible to the CRM's queue (only its
`chat_histories` row from the CRM webhook exists, which the dev copy showed lands during a
text turn in 0 of 50 pairs on today's timing). S6 alone only removes n8n's wait from the
photo's own path when the photo is popped first. It pays off together with the injector
flip: the photo's `/chat/turn` then reaches the CRM about a second after n8n gets it.

25 Oct case with flip + S6: text `/chat/turn` about 02:34:32.6, turn runs ~4.4 s; photo
`/chat/turn` about 02:34:35 waits on the ticket as a queued row (sent 02:34:25.8, before the
text's 02:34:28.8); the text's pre-send look-ahead at about 02:34:37 claims it, reads it,
answers the photo, re-runs "Check stock" on the photo's products, one response. The photo's
own request later comes back `duplicate: true` (D15) and sends nothing. On the dev copy the
same timing model gives 47 / 3 / 0 (section "Photo order once the CRM owns the queue"; CRM
webhook arrival used as a proxy for n8n's).

### What would break or must move

| Thing | Effect | Action |
| --- | --- | --- |
| ~1 new turn/s cap (dispatcher tick) | gone: a burst of dealers hits `/chat/turn` at once | CRM capacity: 4 uvicorn workers (`gunicorn.conf.py:44`), in-process turns, offload off (`config.py:182-186`, measured trigger ~250 concurrent not reached); n8n concurrency limit UNVERIFIED. Watch the first busy hour |
| One contact's long burst | ticket wait is clamped to 30 s (`config.py:174-181`); a 4th+ message of a long photo burst may run before its predecessor finishes (out of order). The dispatcher's lock held regardless | accept, or raise the n8n timeout and the clamp together |
| Concat / batching | none today, none after | none |
| Media intake (S6) | the read wait moves from n8n onto the API process inside `/chat/turn`: at most 8 concurrent waits (`media_intake.py:48`), up to 30 s each; the RQ `media` worker must be up | watch the first busy hour; a photo that cannot get a wait slot takes the "could not read in time" arm |
| Claimed photo whose own request outwaits the ticket | the photo's request waits behind text turn + photo read + text re-run (~40 s) but the ticket wait is clamped to 30 s, so it may start while the claimer is still answering it | build check (red test): a claimed queued row must come back `duplicate`, never run twice |
| Typing / labels | none in the exports | none |
| Retries / error path | unchanged (spine `sub-error-logger`; no retry) | none |
| Failover poller | posts to `sorento-main-INJECT`, flipped in step 2 | none beyond step 2 |
| Pool-full path `chat_turns.py:143` | direct ingress only; stays off in this design | none |
| A message left with both edges | if `push-ready` is kept AND `call-spine` added, the dispatcher's spine run pops an empty list | delete `push-ready` in steps 1-2 |

### Switchover and rollback

1. Deploy the CRM look-ahead (inert while the dispatcher is on). Confirm on Settings that
   chatbot ordering (S7) is ON. Check whether the live spine still has `media-intake`.
2. If it does: draft step 5 (S6) on the n8n clone and run its four smoke messages.
3. Publish steps 1, 2 (and 5) in n8n together. 4. Deactivate the dispatcher once
   `ready-contacts` is empty. 5. Owner test: photo then "check stock" within 3 s, and a voice
   note.

Rollback, under a minute: in n8n, restore the previous version of `sorento-main`,
`sorento-main-INJECT` (and the spine, if S6 was published) from workflow history, un-archive
`sub-media-intake` if it was archived, and re-activate `sorento-dispatcher`. Nothing is
lost either way: every message is RPUSHed once and popped by whichever spine run takes it.
The CRM look-ahead can stay; it finds nothing with the dispatcher back in front.

### Owner questions (filed as one `--ask`)

1. Photo reading in the same switchover: (a) fold S6 in (spine media step off, CRM waits
   for the read in-turn), (b) leave n8n's media step, widen the look-ahead to ledger rows.
   Recommendation: (a) (REVISED 25 Oct on crew input): the look-ahead then uses the existing
   queued-row rule unchanged, the photo is read and waited on in one place, and the n8n
   reply arm that forces the "only a photo already read" guard (`engine.py:2009-2012`) is
   gone. If the live spine has no `media-intake` node any more, S6 is already done and only
   the injector flip remains.
2. Rollback mechanism: (a) n8n workflow history restore + re-activate the dispatcher,
   (b) build an IF toggle node in both injectors now. Recommendation: (a): no extra node to
   build, and the previous version is exactly today's.
3. (Owner 05:45: NOT accepted, see "CRM-owned queue".) Long single-contact bursts beyond the 30 s ticket wait: (a) accept, (b) raise n8n's
   `chat-turn` timeout and `chatbot_queue_wait_seconds` together. Recommendation: (a): the
   photo fix targets photo + text pairs; revisit if a burst reorders in the first week.

## CRM-owned queue (owner 25 Oct 05:45)

Owner: "CRM side should have queueing also to handle long burst of msg; if I turn off the
dispatcher there will be burst cases." Requirement: per-contact FIFO in respond.io send-time
order with no clamp reordering; survives a long single-contact burst and a global burst
across many contacts (the dispatcher's ~1 new turn/s cap is gone); never loses or
double-answers a message; survives a CRM restart mid-burst.

### Why the synchronous spine cannot meet it

- n8n waits on `/chat/turn` at most 90 s (spine `chat-turn` timeout 90000; mirrored as
  `send_order.N8N_CHAT_TURN_TIMEOUT_SECONDS`, `send_order.py:74`). A message queued behind its
  contact's earlier turns spends that budget waiting; the 30 s clamp (`config.py:174-181`,
  `dispatch.max_queue_wait_seconds` `dispatch.py:124`) exists only because of it. Ten photos
  at ~10 s a turn put the tenth past 90 s whatever the clamp says.
- On a timeout n8n takes its error arm (`chat-turn[1] -> sub-error-logger`, fixed "Sorry,
  I couldn't process that just now..." text) while the CRM may still finish the turn, and
  nobody sends that reply: one wrong message plus one lost answer.
- A CRM restart (every blue/green deploy) kills every waiting request the same way; the
  queued rows survive but their callers are gone, so nothing answers them.

So FIFO without a clamp, and surviving a restart, both need the CRM to ACCEPT the message
and answer it LATER. Direct ingress already has that shape: it accepts on the respond.io
webhook, runs the turn on its own pool and POSTs the actions to the thin n8n sender
(DI:13-26, DI:324, DI:358-437).

### Options

| | 1. Sync, bigger budget | 2. Async CRM inbox (recommended) | 3. Hybrid |
| --- | --- | --- | --- |
| How | as "Owner's design", plus a longer n8n `chat-turn` timeout and clamp | every copy of a message enqueues once and returns at once; a CRM drain per contact answers in send order and posts to the thin sender | sync while the contact's queue is empty, async otherwise |
| Long one-contact burst | still bounded by the n8n timeout | yes: nobody waits on HTTP, no clamp | yes |
| Global burst | 4 uvicorn workers hold every waiter (`gunicorn.conf.py:44`) | rows wait in Postgres; the pool bounds concurrency | yes |
| CRM restart mid-burst | waiters lost, "Sorry" sent | rows durable, drains re-armed | yes, two paths to recover |
| Never double-answer | D15 key | D15 key at enqueue + per-contact mutex + send log check | same, across two paths |
| CRM size | S | L (~700 lines + tests, no migration expected) | L+ |
| Meets the requirement | no | yes | yes, with more ways to go wrong |

**Option 2 in detail (all reuse unless marked new):**

- **Enqueue (new, small).** Every injector of a message (the CRM's respond.io webhook, n8n's
  `/chat/turn`, the failover `sorento-main-INJECT`, Retry) inserts its turn row at status
  `queued` once; the unique key (`models/chatbot_turn.py:63`) makes a second copy a no-op.
  The webhook still answers respond.io 200 within its 5 s; `/chat/turn` answers n8n at once
  with no actions, so the spine's action loop sends nothing and needs no edit. `is_test` and
  console turns stay synchronous (the eval runners read replies inline).
- **Drain (new, the core).** One drain per contact on the existing direct-turn pool (8
  threads per API process, CT:75): take the contact's oldest `queued` row by respond.io send
  time (`send_order.send_key_ms`, `send_order.py:105-122`; index
  `ix_chatbot_turns_contact_status_created` `chatbot_turn.py:50`), check takeover at run time
  (DI:264), run the turn (`run_turn(offload=False)`, DI:324), POST its actions to the sender
  (DI:358-437), mark it done, take the next. Per-contact exclusivity is a Redis liveness key
  with heartbeat, the pattern `dispatch.py` already uses (`ALIVE_TTL_SECONDS` `:94`), as a
  mutex, not a ticket: no clamp, no reorder.
- **Photo look-ahead.** Before posting a reply, the drain checks for a `queued` row of the
  same contact with an EARLIER send time (the late photo that arrived during this turn). If
  there is one: drop the draft, answer that row, then re-run this one (card Q3 (a)). With
  the CRM webhook as an injector the photo's row exists from its CRM arrival, so n8n's media
  step plays no part (dev-copy model 47 / 3 / 0, section "Photo order once the CRM owns the
  queue").
- **Global burst.** Rows wait durably; at most 32 drains run (8 x 4 processes); photo reads
  stay capped at 8 waits per process (`media_intake.py:48`) and run on API threads, so the
  RQ `media` worker never waits on itself.
- **Restart.** A sweeper (at start-up and every few seconds) re-arms a drain for every
  contact with `queued` rows and no live mutex. A row left `processing` by a dead process is
  re-run only if the sender log (`integration_logs`, channel `chatbot_sender`, DI:63, DI:445)
  shows its POST never went out; otherwise it is closed and flagged on the trace screen.
- **Sender order.** The n8n `chatbot-sender` webhook answers `onReceived`
  (`documentation/n8n/chatbot-sender.workflow.json`), so two back-to-back POSTs for one
  contact could send interleaved. It must answer "When Last Node Finishes", and the CRM's
  sender timeout (10 s, DI:62) must cover a chunked send.
- **Principle reversed, on this ruling.** The turn-engine plan said "The CRM inbox row stays a
  record and a trace, never a queue" (`PLAN-chatbot-turn-engine.md:248`). Option 2 makes it
  the queue; the evidence is the owner's burst requirement plus the restart case above.

Why the drain runs on the API pool and not on RQ: `chat` and `media` share the `fast` worker
role (`worker.py:127`, `:134`), so a turn running on that worker would wait on its own
photo read. RQ would need dedicated chat worker containers (Q2 (b)).

### n8n clicks and switchover (option 2)

1. Deploy the CRM build with the queue switch off (inert).
2. n8n `chatbot-sender`: import it if it is not live yet (`documentation/n8n/chatbot-sender.md`),
   set its Webhook to respond "When Last Node Finishes", set its credentials; paste its URL
   and key on the CRM workspace (same doc, "CRM side").
3. n8n spine `THfmMmYcGzDDXBu4`: S6 (steps 5 of "Owner's design"), clone smoke first, so n8n
   stops reading photos and its media reply arm stops answering them on its own.
4. Flip the CRM queue switch on. From then every copy enqueues and the CRM answers.
5. Producer, dispatcher and spine need NO rewiring: their copies are deduped by message id
   and they double as the failover injector. Deactivate them any later day.

Rollback: flip the CRM switch off. `/chat/turn` answers synchronously again (S7 ticket, as
today); rows already queued keep draining through the sender, so none is lost. n8n
untouched (S6 stays; the sync path reads photos in-turn by design).

Option 1 clicks, for comparison: "Owner's design" steps 1-5 plus a longer `chat-turn`
timeout (and the CRM mirror) - more n8n edits, and it still fails the burst and restart cases.

### Owner questions (filed as one `--ask`)

1. Which option: (a) 2, async CRM inbox, reply via the thin sender, (b) 1, sync with a bigger
   budget, (c) 3, hybrid. Recommendation: (a): the only one that meets the requirement with a
   single delivery path, and the smallest n8n switchover (no producer or dispatcher rewiring).
2. Where drains run: (a) the API process pool, as direct ingress does, (b) dedicated RQ `chat`
   worker containers. Recommendation: (a): no compose change, and the sweeper covers a deploy
   restart, which (b) needs too.
3. A crash between a send and its done mark: (a) re-send only when the sender log proves the
   POST never went out, otherwise flag it for staff, (b) always re-send (at-least-once, a
   duplicate reply is possible). Recommendation: (a): never double-answer, as the owner asked.
