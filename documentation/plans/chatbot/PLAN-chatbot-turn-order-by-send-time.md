# PLAN: a contact's turns are answered in WhatsApp send order, not arrival order

Status: implemented, fix lane round 2 done (reviewer B1, S1 to S3, N1 to N3), awaiting review. Track: feature by line count (product code is ~480 lines
including docstrings, over the ~300 small-fix line), otherwise small-fix shaped: no migration,
no auth / RBAC change, no new ingest surface, no frontend. One lane, one PR.
UAC: `chatbot-turn-order-by-send-time-acceptance-criteria.md`.
Source: issue #1262 round 3 (Mr Loo, sections 1 and 3) and the owner's two chat
rulings of 26 Sep 2026: "this fix of waiting few seconds is very fragile ... the order supposed
to be photo -> stock" and "yeah go for one lane". Owner ruling of 26 Sep on #1262: no
stale-focus guard (round 3 N6 / R3-6 rejected). Nothing drops carried focus on a calendar-day or
clock rule; only the ordering is fixed, and a bare "Stock" on yesterday's focus answers from it,
as on main.

## Evidence

- Mr Loo sent a PHOTO at 14:57:25 (UTC+8, owner's WhatsApp screenshot) and "Stock" at 14:57:29
  (`message.message.timestamp` 1790405849000 in the turn 378 envelope). The CRM ran "Stock" as
  turn 378 and the photo as turn 379.
- Turn 378 finished before the photo reached the CRM (round 3 section 1: Received 53 ms and
  125 ms, so no queue wait). About 23 s of the photo's 29 s went on n8n's own media intake
  (`sub-media-intake` calls `/external/media/process` and waits for the extraction) before it
  called `/chat/turn` (round 3 section 3). A text is forwarded at once. So a text overtakes the
  photo it was sent after, and the per-contact ticket (`dispatch.py`), which orders by ARRIVAL,
  cannot see it.
- The CRM does know the photo exists when "Stock" arrives: n8n's `/external/media/process` call
  wrote the `contact_media_usage` ledger row and queued the extraction job seconds before.
- respond.io puts the send time on every envelope as `message.message.timestamp` (ms). The
  media ledger does not store it.

## Design (no timer)

When a turn gets its slot, it first answers every earlier-sent message of this contact that the
CRM already knows about and has not answered, then itself (`app/services/chatbot/send_order.py`):

1. **Queued turn rows** (both messages reached `/chat/turn`, the later-sent one first). Rows are
   inserted at stage `queued` when a ticket was taken. A row whose send time is earlier than
   this turn's is claimed with one conditional UPDATE (`stage queued -> received`) and answered
   first. The waiting request claims its own row when its ticket comes up; if that fails, a
   predecessor answered it and it replays the answer as `duplicate: true` (also when its wait
   ran out, so it never sends the generic error beside the real answer).
2. **Photos still in n8n's media intake** (today, until plan S6 is promoted). A ledger row with
   no turn row, accepted, whose job is still `queued` or `running`, written before this turn
   arrived, before this turn's own send time, and after this contact's previous turn. It is rebuilt as the attachment envelope and
   answered first; its intake replays the same ledger row and job (idempotency key: contact,
   message id, modality), so nothing is extracted or charged twice. The only wait is the
   existing bounded media poll on that job, which the photo's own turn would have waited too.
   When n8n then delivers the photo, it is a D15 duplicate and n8n sends nothing.

Each earlier message runs as its own turn on its own row with its own trace; its actions are
put ahead of this turn's in the one response n8n executes in order. "Stock" then reads the
focus the photo left.

Bounds, all states and none of them clocks: a queued row counts only if it arrived after the
contact's latest answered turn (a row whose request died in a deploy is history); a ledger row
only if its job is still queued or running and it was written after the contact's previous turn.
The whole pre-step is best effort: a failure in it costs the ordering, never this turn and never
an answer already given, including when an earlier message's stages raise and closing its row
raises too. A test turn (dry run) never claims or answers a live message (D14). Every lookup is
filtered to this contact, so one customer's turn never answers another's message.

Bounded per turn, by counts and the existing per-item wait (review round 2, S1): at most 2
earlier messages (`send_order.MAX_EARLIER_PER_TURN`), and the worst-case media waits taken on,
this turn's own included, stay below n8n's 90 s `chat-turn` timeout (below
`chatbot_turn_wait_seconds` when turns are offloaded). The first message that does not fit ends
the take; it and everything after it go to their own deliveries. This turn's `received` trace
record says how many were answered ahead, how many were left, and which bound left them.

A ledger photo is answered ahead only once it has been READ (review round 2, S2): the pre-step
first takes the existing bounded wait on its job, and a job that fails or outlives the wait is
left alone, with no turn row and nothing sent. n8n's own `media-route` reply arm owns that
outcome today, so the customer never gets two messages, and a later delivery of the photo runs
as its own turn. The row answered ahead records the message whose response carried it
(`answered_ahead_by_message` in its first trace record's facts, the carrying turn id in `raw`).

Not covered, and accepted:

- A message the CRM has not seen at all when a later one is answered stays uncovered until n8n
  S6 is live. After S6 that window is the time between two respond.io webhooks.
- One response carries up to two earlier turns plus this one. The media waits stay under the
  bound above, but LLM calls are not counted, so a slow provider can still push a request past
  n8n's timeout. If the request carrying the answers dies, the earlier answers die with it, and
  those messages' own deliveries are duplicates that send nothing.

## n8n steps for the owner (plan S6, not touched by this lane)

From `PLAN-chatbot-media-into-turn.md` S6. The CRM side (media intake inside `/chat/turn`) is on
main since #1139.

1. Main workflow `THfmMmYcGzDDXBu4`: delete nodes `media-intake` and `media-gate`; wire
   `redis-pop-main-message-list` straight to `tf-message`.
2. Same workflow: delete `if-message-is-audio`; both of its outputs go to `chat-turn` and the
   save-message call.
3. `chat-turn` HTTP body: `{envelope: <message>}`. Drop the `media` key entirely (with it
   present the CRM skips its own intake, `media_intake.patched_upstream`). Timeout stays 90 s.
4. `sub-respond-save-message-redis`: for an attachment message store the caption as `message`
   (empty string when none).
5. Draft on the clone first; smoke one photo-only, one photo with caption, one voice note, one
   denied number; then promote.
6. Archive `sub-media-intake` (`B3rBMtABou6FpY69`).

Until step 1 is live every photo still pays n8n's extraction wait before `/chat/turn`; this
lane makes that wait harmless to ordering, not shorter.
