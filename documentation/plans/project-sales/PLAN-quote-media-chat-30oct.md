# PLAN: Drawing and photo requests use the chat escalation flow

Status: Phase 2 (red tests, then wiring); standard track (expected diff over 300 lines), no migration, no setup.

Follow-up to #1983 (merged; plan archived at
`documentation/plans/_archive/project-sales/PLAN-quote-drawing-escalate-29oct.md`). Owner hand test
30 Oct 22:50: the PIC's panel had no way to answer the salesperson. A drawing or photo request
must feel like a chat escalation: the salesperson gets a WhatsApp acknowledgement, the PIC sees
the conversation and replies in it (a reply is the Respond), and resolving is the same as
resolving a chat ticket. One UX, no parallel flow.

Owner answers (30 Oct 23:15) on the ask card:

- Q1 merge #1983, build this as a new PR off main.
- Q2 acknowledgement wording as proposed (below).
- Q3 "it should be separate request just like now": one ticket per requester, as chat
  escalations are today.
- Q4 no linked WhatsApp contact: today's panel, Respond button, in-app and email notices.
- Q5 drop the requester's H2/H4 WhatsApp; in-app and email stay.

## What changes for the 1a model

1a was "one task per product per kind". Q3 makes it one task per product, kind AND requester: a
second salesperson asking for the same drawing opens their own ticket with the PIC, while the
same salesperson asking again (another quotation, a second click) joins their own open ticket,
so 1a's "no duplicate task" still holds per person.

## Behaviour

- **B1 One ticket per requester.** `escalate` looks for an open task of this kind for this product
  whose requester is the caller; found means join (the quotation is added to "Waiting on this"),
  not found means a new task on the same general-enquiries route. The advisory lock key gains the
  requester: `<source>:<product>:<user>`.
- **B2 The ticket is on the requester's WhatsApp contact.** A new task stores the requester's
  `users.respond_contact_id` (when it points at an existing contact) as `respond_contact_id`, the
  contact's phone as `contact_phone_number`, and `source_message_text` =
  `Technical drawing for <product code> (<quotation no>)` or `Product photo for <product code>
  (<quotation no>)`. No contact: the contact and phone stay empty (the source text is still
  set, it names the request in the panel) and the task behaves as in #1983 (Q4).
- **B3 Acknowledgement (Q2).** A new task with a contact queues ONE WhatsApp to that contact on the
  `respond_io` queue:
  `Your project request: technical drawing for <product code> (<quotation no>). Routed to your PIC, they will reply shortly.`
  (`product photo` for a photo). A join sends nothing. No contact: nothing.
- **B4 The PIC replies in the conversation.** A drawing or photo task with a contact is accepted by
  the chat ticket endpoints the panel uses: ticket detail, conversation (and its page and search),
  ticket send, ticket comments, reply draft. Today they refuse every form-SLA row; the guard
  becomes "form-SLA row and not a media task with a contact". A send marks the task responded
  (the same `mark_ticket_responded`), so a reply is the Respond.
- **B5 Panel.** `MediaRequestDrawer` keeps its facts block (product, Waiting on this, Upload in
  Resources; its description line reads `From <requester> · With <assignee>`) and, when the task has a conversation, mounts the same `TicketConversationPanel` the
  chat drawer uses, with no Respond button (the reply is the Respond). Without a contact it is
  today's panel with Respond (Q4). "Following" goes: a ticket has one requester, named in the
  description line.
- **B6 Resolve.** `media-resolve` on a task with a contact also does what a chat resolve does:
  queues the `ticket_resolved` WhatsApp (excerpt = the source text) and closes the Respond
  conversation when no other open ticket shares the contact (the existing helpers, not copies).
- **B7 Notices (Q5).** The requester's H2 (responded) and H4 (resolved) keep in-app and email and
  never send WhatsApp. H1 and escalation notices to the PIC are unchanged. H3 (a file linked in
  Resources) tells the assignee of EVERY open task of that kind for the product.
- **B8 The quotation tile is per viewer.** It shows the viewer's own open task (Escalated /
  Replied); with none it offers Escalate even when a colleague has one open. The hover drops "by
  N people" (one requester per ticket).

## Not in scope

- The chatbot's own handling of the salesperson's WhatsApp replies (unchanged: after the PIC's
  first panel reply n8n is told a human answered, as for chat tickets).
- A reply typed in the Respond app does not stamp Respond on these tasks (the agent-replied
  fallback is contact-keyed and excludes form rows). The panel is the path.
- No backfill: #1983 is merged but not released, so no task in production carries several
  requesters.

## Tests (red first)

Backend (`tests/test_product_drawing_request.py`, `tests/test_product_drawing_routes.py`,
`tests/test_project_quotation_images.py`):

1. A and B escalate the same product and kind: two tasks, one requester each. A again from a
   second quotation: still A's one task, two quotations.
2. The lock parameter carries the requester.
3. New task stores the requester's contact id, phone and the exact source text (drawing and photo);
   a requester with no contact leaves them empty.
4. The acknowledgement is queued once with the exact text on a new task with a contact; not on a
   join; not without a contact.
5. Ticket detail, conversation and ticket send accept a media task with a contact (send marks it
   responded); they still refuse one without a contact.
6. `media-resolve` with a contact queues the resolved message and the conversation close; without a
   contact it queues neither.
7. H2 and H4 to the requester never carry WhatsApp; in-app is written.
8. H3 reaches the assignees of two open tasks for the same product and kind.
9. The tile state is the viewer's own: B sees no open task while A has one.
10. The media detail says whether the task has a conversation.

Frontend: `InterventionTicketDrawer.media.test.tsx` (conversation panel mounted and no Respond
button when the task has a conversation; today's panel otherwise), `MediaEscalation` /
`QuotationLineFileCell` tests for the hover without "by N people".
