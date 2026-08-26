# UAC - Ticket-resolved closing message (one per ticket)

Status: Draft 2026-08-26, decision taken in session (CRM owns the message; n8n keeps only the
contact-level housekeeping on the last open ticket)
Related: PLAN-ticket-resolved-closing-message.md

## End goal (one paragraph)

Every time a conversation ticket is resolved, the contact gets a WhatsApp message saying that
THIS enquiry is resolved, worded by an admin in the WhatsApp Templates screen, whether the 24h
window is open (free text) or closed (approved template). A contact with three open enquiries
hears three times, once per enquiry, as each is resolved. The Respond-side housekeeping
(unassign, bot resumes) still happens only when the LAST open ticket is resolved, unchanged.

## Problem

Today the closing message is sent by n8n `respond-close-convo`, which the CRM only calls when
the resolved ticket was the contact's last open one, so resolving ticket 1 of 3 sends nothing.
The wording ("your conversation is marked as closed") is also wrong per ticket.

## Acceptance criteria

### A. Trigger

- AC-A1: Resolving a conversation-scope ticket from the CRM (drawer, list, dashboard) enqueues
  one `send_ticket_resolved_message` job for that ticket on the `respond_io` queue.
- AC-A2: A resolve that arrives by API key (n8n's Respond-app-close lane resolving each open
  ticket) enqueues the same job per ticket. The CRM is the only sender, on every lane.
- AC-A3: Resolving one of several open tickets for a contact enqueues for that ticket only; the
  siblings get theirs when they are resolved.
- AC-A4: A form-SLA stage row (`source_entity_type` in the form types) enqueues nothing.
- AC-A5: Re-resolving an already resolved ticket (the short-circuit) enqueues nothing.
- AC-A6: The enqueue is post-commit and best-effort: a queue failure is logged and the resolve
  still succeeds.

### B. The message

- AC-B1: New template use case `ticket_resolved` in the admin WhatsApp Templates list, with the
  same in-window / out-of-window contract as `sla_*` use cases: in-window sends the configured
  default body rendered over the variables (or the built-in fallback text when none is
  configured); out-of-window sends the mapped approved template.
- AC-B2: Variables available to the template: `contact_name` (the CONTACT), `message` (the
  enquiry excerpt, first 120 chars of the ticket's source message, or "your enquiry"),
  `entity_number` (the contact name again - a conversation ticket has no number; kept so a
  template mapped with the SLA convention still fills).
- AC-B3: Built-in fallback text: `Hi <contact_name>, your enquiry "<excerpt>" has been
  resolved. If there is anything else we can help with, just reply here.` (without the quoted
  excerpt when the ticket has none).
- AC-B4: The send is logged in the Respond outbox (integration log, success or failed) against
  `conversation_sla_tracking` / the ticket id, like every other Respond send.
- AC-B5: The sent message appears in the CRM thread at once (local `chat_histories` row via the
  same mirror the composer uses), not only after the n8n echo.
- AC-B6: A ticket whose contact has no Respond.io id sends nothing and the job ends `skipped`.

### C. n8n

- AC-C1: `respond-close-convo` no longer sends its own closing message (the
  `sorento-sub-respond-sendmsg-respond` node is disconnected); unassign + `is_human_intervened
  = false` stay on the last-open lane. Draft edited by the agent, promoted by the user.

### D. Non-goals

- Form-SLA closing messages (owned by the form flows).
- Changing when the Respond conversation is closed / unassigned.
