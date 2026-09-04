# UAC - Optimistic send (agent reply appears in the thread at once)

Status: Built 2026-08-26 (A1-A7, B1-B6 covered by tests); browser evidence pending
Related: PLAN-optimistic-send.md

## End goal (one paragraph)

An agent who presses Send in the ticket drawer or the Conversations inbox sees their message
in the thread immediately, with the WhatsApp "sending" clock, and that bubble turns into the
real message (sent / delivered / read ticks) without them doing anything. Today the bubble
only shows up once Respond.io's outbound webhook has crossed n8n and been mirrored back into
`chat_histories` (2-10 s, unbounded when that lane is degraded), which reads as "did it go?".

## Problem

- The thread renders from local `chat_histories` (`conversation_thread_service`), never from
  Respond.io directly.
- A CRM send writes NOTHING local. The row arrives only via Respond -> n8n -> `POST
  /external/chat-history/messages` (`type=outgoing`). The FE has no optimistic bubble and the
  send mutation deliberately does not insert or invalidate; the composer's `onSent` pulses
  (0 s / 6 s / 15 s) refetch a thread that does not yet hold the row.

## Acceptance criteria

### A. Backend anchor (local outgoing row at send time)

- AC-A1: After a successful in-window text send from `send_ticket_message` or
  `send_contact_message`, a `chat_histories` row exists for the contact with `type='outgoing'`,
  `message_id` = Respond's `messageId` (string), `message` = the text sent, `sent_at` /
  `respond_ts` derived from the id, `channel='whatsapp'`.
- AC-A2: Same for each successfully sent attachment: one row per attachment with the same
  placeholder text the read lane already stores (`"[image] name.jpg"`).
- AC-A3: When the Respond mirror later ingests the same `(contact_id, message_id)`, the ingest
  answers `already_existed` and the thread still shows ONE bubble. The mirror's richer fields
  (`result`, `turn_id`, `state_trace`) still land through the existing COALESCE upsert.
- AC-A4: A Respond acknowledgement whose id is not a plausible timestamp (test doubles, unusual
  channels) writes no row and raises nothing; the send still returns 200.
- AC-A5: A local write failure (DB error) never fails the send: the message reached the contact,
  the response is unchanged, the failure is logged.
- AC-A6: A successful local write publishes the `message` conversation event for the contact,
  so every open drawer / inbox pane on that contact refetches within the live-stream latency.
- AC-A7: A send on a closed window that went out as a TEMPLATE also writes the local row with
  the rendered template body (what the contact received).

### B. Frontend pending bubble

- AC-B1: On Send (drawer and inbox), a bubble with the typed text and the "sending" clock
  appears at the tail of the thread before the request completes.
- AC-B2: After the request succeeds, the thread refetches and the pending bubble is replaced by
  the real row (same text, real receipt ticks). At no point are two bubbles for the one message
  visible.
- AC-B3: If the request fails, the pending bubble is removed and the existing error toast shows;
  the composer keeps the text (existing behaviour).
- AC-B4: A send with attachments shows one pending bubble per file (`"[file] name"` style text
  is acceptable) plus one for the caption when there is one.
- AC-B5: Switching ticket / contact (drawer swaps ticket, inbox row click) discards any pending
  bubbles from the previous conversation.
- AC-B6: Pending bubbles never enter the scroll-back or search windows (they carry no message id).

### C. Non-goals

- No change to the n8n mirror lane or the Respond outbound webhook.
- No delivery-status polling change beyond what exists (`onSent` pulses stay).
- Automated sends (notifications, portal, activities) are not mirrored locally here; the n8n
  lane still covers them.
