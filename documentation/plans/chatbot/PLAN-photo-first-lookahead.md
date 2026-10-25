# PLAN: photo-first look-ahead (PHOTO-FIRST-LOOKAHEAD)

Status: PR #1860 open, owner rulings 1a/2b/3 applied; hand test is the owner's prod phone test after release; small fix track (backend only, no migration, no auth change).

## Problem

Prod, 25 Oct 18:29 MYT, owner's test contact: text "check stock" sent at t0, photo at
t0 + 201 ms (WhatsApp uploads a photo before sending it, so a text tapped right after
overtakes it). The text turn was running when the photo row was queued. The inbox drain's
look-ahead (`inbox_queue.checkpoint`) only gives way to an EARLIER-sent queued row, so the
later-sent photo was not taken: the replies went text first, then photo.

## Rule (owner, 25 Oct)

Right before a text turn writes its reply, if a photo row of the same contact is already
queued and unanswered, the photo is answered first, then the text, whatever the respond.io
send times say. No timer, no wait: only rows already queued count. Photo only (owner, 25
Oct): a voice note keeps send order and never jumps ahead of a running text.

## Change

One ordering key for the contact's queued rows, used by both the claim (`_claim_next`) and
the look-ahead (`checkpoint`): photo rows first (send order among them), then every other
row in send order. Same key on both sides, so a text that gave way to a photo is not
re-claimed ahead of it, and a photo never gives way back to the text it overtook.

A photo whose read is still pending is parked and re-claimed ahead of the texts, so a text
(earlier-sent too) can wait behind that read. Owner, 25 Oct ("1a ok"): that wait is capped
at `PHOTO_FIRST_MAX_WAIT_SECONDS` (60 s) from when the photo was queued. Past it the photo
takes its send-order place and the texts behind it are answered. The cap is on an existing
wait, not a new one: no row is held back to wait for anything.

The photo and the text go out as two messages back to back, photo first, not one merged
send (owner, 25 Oct: "2b two msg is ok"). The n8n `/chat/turn` sync path (`send_order`) is
not the drain and keeps pure send order.

Read from one more JSON path on the row (the attachment's type and mime), never the whole
envelope (IQ-33).

## Tests (`tests/chatbot/test_inbox_queue_photo_first.py`)

1. 18:29 shape: text t0 running, photo t0 + 201 ms queued -> photo POST, then text.
2. Photo arriving after the text's look-ahead passed (committed): normal order.
3. Two texts and one photo queued behind the running first text: photo, text 1, text 2.
4. No photo: unchanged, posts at once.
5. A photo of another contact: ignored.
6. `_order_key` alone: an image and an `image/*` file first; voice, text, document, sticker in send order.
7. A voice note queued behind the running text does not go first (owner: "Photo only").
8. A photo queued over 60 s: the running text does not give way, and an earlier text goes
   before it (`_order_key` boundary at 59 s / 61 s too).

## Hand test

The owner's phone test on prod after release (owner, 25 Oct: "3 yeap test in prod"):
`laneboard/scripts/1860.md`.

## UAC

`photo-first-lookahead-acceptance-criteria.md`.
