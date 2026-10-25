# PLAN: photo-first look-ahead (PHOTO-FIRST-LOOKAHEAD)

Status: in progress, small fix track (backend only, no migration, no auth change).

## Problem

Prod, 25 Oct 18:29 MYT, owner's test contact: text "check stock" sent at t0, photo at
t0 + 201 ms (WhatsApp uploads a photo before sending it, so a text tapped right after
overtakes it). The text turn was running when the photo row was queued. The inbox drain's
look-ahead (`inbox_queue.checkpoint`) only gives way to an EARLIER-sent queued row, so the
later-sent photo was not taken: the replies went text first, then photo.

## Rule (owner, 25 Oct)

Right before a text turn writes its reply, if a media row (photo or voice note) of the same
contact is already queued and unanswered, the photo is answered first, then the text,
whatever the respond.io send times say. No timer, no wait: only rows already queued count.

## Change

One ordering key for the contact's queued rows, used by both the claim (`_claim_next`) and
the look-ahead (`checkpoint`): media rows first (send order among them), then every other
row in send order. Same key on both sides, so a text that gave way to a photo is not
re-claimed ahead of it, and a photo never gives way back to the text it overtook.

Read from one more JSON path on the row (the attachment's type and mime), never the whole
envelope (IQ-33).

## Tests (`tests/chatbot/test_inbox_queue_photo_first.py`)

1. 18:29 shape: text t0 running, photo t0 + 201 ms queued -> photo POST, then text.
2. Photo arriving after the text's look-ahead passed (committed): normal order.
3. Two texts and one photo queued behind the running first text: photo, text 1, text 2.
4. No photo: unchanged, posts at once.
5. A photo of another contact: ignored.

## UAC

`photo-first-lookahead-acceptance-criteria.md`.
