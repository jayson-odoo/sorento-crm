# UAC: ticket resolving reply-to (quoted message) with WhatsApp gestures (#1317)

Plan: `PLAN-ticket-reply-to-27sep.md`

## Journey

1. Staff (a ticket assignee, several escalations open for one contact at once) opens a ticket
   from the worklist drawer or the SLA detail "Chat Records" sheet. The conversation shows every
   message from that contact, across all their enquiries.
2. They pick the customer message they are answering:
   - desktop: hover the bubble, a chevron-down appears at its top corner; click it, or right-click
     anywhere on the bubble. The menu reads Reply, Copy.
   - phone: swipe the bubble to the right. It follows the finger a short way, a reply arrow fades
     in behind it; letting go past the threshold starts the reply, letting go early snaps it back.
     A long press opens the same Reply / Copy menu.
3. The composer (Reply tab) shows a quoted preview above the text box: who wrote the quoted
   message, its first lines, and an X to dismiss. The text box takes focus.
4. They type and Send. The customer receives one WhatsApp message: the quoted line on top (as
   `> quoted text`, which WhatsApp renders as a quote), their answer below.
5. The CRM thread renders that sent message with a quoted block (sender, quoted text) above the
   answer, never the raw `>` line. Tapping the block scrolls to the quoted message and flashes it.
6. Internal Comments never carry a quote; the preview is only shown on the Reply tab.

## ACs

### Menu (desktop)

- **AC-RT-1** [FE] Given the ticket conversation panel, when the pointer hovers a message bubble,
  then a "Message actions" chevron button is rendered at the bubble's top corner (hidden on
  touch-only devices via `(hover: hover)`), and clicking it opens a menu whose items are exactly
  Reply, Copy, in that order.
- **AC-RT-2** [FE] Given a bubble, when it is right-clicked, then the same menu (Reply, Copy)
  opens at the pointer (Radix ContextMenu, the system component).
- **AC-RT-3** [FE] Given the menu, when Reply is chosen, then the panel switches to the Reply tab
  (if Comment was active) and the composer shows the quoted preview for that message.
- **AC-RT-4** [FE] Given the menu, when Copy is chosen, then the bubble's displayed text (without
  any quote prefix) is written to the clipboard and a "Copied" toast shows.
- **AC-RT-5** [FE] Given a ticket where replying is not possible (resolved, no send rights), then
  the menu offers Copy only (no Reply). Internal-note bubbles get no menu at all.
- **AC-RT-6** [FE] (revised by owner answer 3, fix lane round 2) Given ANY thread surface (ticket
  drawer, SLA Chat Records sheet, Conversations inbox pane, complaint / stock-inquiry /
  purchase-request Chat Records, the portal draft review, the chatbot console transcript and the
  contact page's Chat history), then every bubble carries the same chevron + right click + long
  press menu through one shared component (`MessageBubbleActions`), with no opt-in. Where the
  viewer can reply there, the menu is Reply + Copy and swipe right starts a reply; on a read-only
  surface (no message box) it is Copy only and a swipe moves nothing. A pending (still sending)
  bubble has no menu.
- **AC-RT-6b** [FE] (owner answer 2) Given a quoted reply, then the sent quote line is at most 160
  characters plus an ellipsis, and the quoted block on the bubble is compact: small text, at most
  two lines with the rest clipped (full text on hover), the reply text at the bubble's own size
  and outside the block.

### Gestures (phone)

- **AC-RT-7** [FE] Given a touch pointer on a bubble, when it moves right, then the bubble
  translates with the finger, capped at 80px, and a reply arrow's opacity grows with the
  distance.
- **AC-RT-8** [FE] Given the swipe, when released at or past 56px, then Reply fires once for that
  message and the bubble returns to rest.
- **AC-RT-9** [FE] Given the swipe, when released short of 56px (or cancelled, or moved left, or
  moved mostly vertically), then Reply does not fire and the bubble snaps back to 0.
- **AC-RT-10** [FE] A vertical scroll of the thread is never captured as a swipe (direction lock:
  the gesture only engages when horizontal travel exceeds vertical travel past a 10px slop), and
  a mouse drag never swipes.
- **AC-RT-11** [FE] Long press on a bubble (touch) opens the Reply / Copy menu (Radix ContextMenu
  touch long-press). Page text selection and the iOS callout are suppressed on coarse pointers
  only, so desktop text selection still works.
- **AC-RT-12** [UX] Snap back uses `--duration-fast` and `--ease-standard`; under
  `prefers-reduced-motion` the return is instant. While the finger is down there is no
  transition (the bubble tracks 1:1).

### Composer preview

- **AC-RT-13** [FE] Given a reply target, the Reply composer renders a preview above the text box
  with the sender name (the contact's name for an incoming message, the sender label or
  "Sorento" for an outgoing one), the quoted text clamped to 2 lines, and a "Cancel reply"
  button.
- **AC-RT-14** [FE] Clicking "Cancel reply" removes the preview; the next send carries no quote.
- **AC-RT-15** [FE] A media message with no text is quoted by its placeholder (`[image]`,
  `[file] quote.pdf`), never an empty line.
- **AC-RT-16** [FE] Switching to the Comment tab hides the preview and a comment never carries the
  quote; switching back to Reply shows it again. Opening a different ticket clears it.

### Send (wire format, recovered)

- **AC-RT-17** [FE] Given a reply target and typed text "body", when Send is pressed, then the
  text handed to the send is `> {excerpt}\n{body}` where excerpt is the quoted text with
  whitespace collapsed, clipped at 160 characters plus an ellipsis (the pre-16-Aug
  `buildQuotedReplyText`, byte for byte), and `reply_to_message_id` / `reply_to_excerpt` ride
  along for the audit trail. After a successful send the preview clears (only if it is still the
  target that send carried). Outside the 24h window (template send) the quote and answer are
  flattened onto one line and the composer's one-line warning shows.
- **AC-RT-18** [BE] Given `POST /{tracking_id}/ticket/send` with JSON `{text: "> q\nbody",
  reply_to_message_id, reply_to_excerpt}`, then Respond receives exactly that text, unchanged,
  and the ticket's response-clock event reason records `reply_to_message_id=<id>` and
  `quoted_reply=true`. Same for the multipart lane.
- **AC-RT-19** [FE] Given no reply target, the send text is exactly what was typed (no prefix) and
  no `reply_to_*` field is sent.

### Rendering

- **AC-RT-20** [FE] Given an OUTGOING message whose text starts with `>` lines, then the bubble
  renders a quoted block (the `>` lines, prefix stripped) above the remaining body; the raw `>`
  text never shows. An INCOMING message starting with `>` renders verbatim (7b18bbb72 rule).
- **AC-RT-21** [FE] The quoted block names the sender of the quoted message when an earlier
  loaded message matches the excerpt (the contact's name, or the outgoing sender label), and
  reads plain "Replying to" when nothing matches.
- **AC-RT-22** [FE] Given a matched quote, when the block is clicked, then the thread scrolls to
  the original message and flashes it. An unmatched quote is a plain label, not a button.
- **AC-RT-23** [FE] A structured inbound `replyTo` (the contact quoting us, AC-L6) still takes
  precedence: one quote block per bubble, never two.

### Hand test

- **AC-RT-24** [E2E] Owner hand test: desktop chevron + right click, phone swipe + long press, and
  two concurrent escalations for one contact answered with two quoted replies that read
  unambiguously on the handset.
