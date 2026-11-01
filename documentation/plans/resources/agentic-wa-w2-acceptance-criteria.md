# UAC: AGENTIC-WA-W2 slice 1 - dealer writes on WhatsApp (notes, stock inquiry, my requests)

Plan: `PLAN-agentic-wa-w2-01nov.md`. Scope: a CONTACT principal (Agent switch on, no linked active CRM user).
Linked staff contacts are unchanged in slice 1 (they keep their CRM writes and /my-requests).

## Exposure

- AC-1 A contact principal is offered `crm_my_requests_list`, `crm_my_request_note_add`,
  `crm_my_request_note_remove`, `crm_stock_inquiry_create`, `crm_stock_inquiry_withdraw`. The W1 lists
  (`writes.permitted_writes`, `writes.permitted_user_reads`) stay empty for it.
- AC-2 With the contact's Stock Inquiry form switched off (per-contact override), the two stock inquiry tools are
  not offered, and the list read leaves stock inquiries out. The portal's own gate (`require_form_visible`) is the
  rule; no user slug is consulted.
- AC-3 A contact whose respond.io id sits on more than one contact row is offered no dealer write or read.
- AC-4 A user principal (linked staff contact) is offered none of the five tools in slice 1.
- AC-5 The router lists the dealer tools in the agent's criteria for that contact only when they are offered
  (AC-1..AC-3).

## Proposing (nothing is written)

- AC-6 `crm_stock_inquiry_create` needs `product_code` and `quantity`. A product code that is not an active,
  chat-searchable product in the contact's brand scope is refused ("invalid"), with no row written.
- AC-7 A valid proposal stores one `proposed` action whose `user_id` is empty, and the summary reads
  "Send a stock inquiry to the project sales team: <CODE> (<name>), <qty> pcs[, needed by <date>][, project
  <name>], requested by you." No stock inquiry row exists until the confirm.
- AC-8 `crm_my_request_note_add` on another contact's request, on a draft, or on an unknown id is refused at
  proposal; on the contact's own submitted request it proposes 'Add this note to your <kind> <number>: "<text>"'.

## Confirming (live WhatsApp turn)

- AC-9 The contact's next-turn "yes" (`confirm_action`) creates and submits the inquiry through the portal service:
  `contact_id` = the contact, `salesperson_contact_id` = the contact ("requested by you"), status
  `pending_project_sales`, a document number assigned, one revision-history row. The reply carries, added by
  code, "Stock inquiry <number> is with the project sales team. Reply undo within 10 minutes to withdraw it."
- AC-10 A note confirm writes one form comment authored by the contact (`author_contact_id`).
- AC-11 The audit rows of a confirmed write name the contact (`contact_id`), with `auth_method` = `agent`.
- AC-12 The router keeps the contact's next message on the agent while the contact's OWN proposal is pending
  (reason `pending_action`); a staff user's pending action on the same contact still does not (W1 FR1-F3).
- AC-13 A contact naming `confirm_action` / `cancel_action` with no pending proposal of its own is denied.

## Undo

- AC-14 `crm_my_request_note_remove` deletes the contact's own note; a staff member's note is refused.
- AC-15 `crm_stock_inquiry_withdraw` hard-deletes the contact's own inquiry when ALL hold: first submission (one
  history row), at most 10 minutes since it was submitted, still `pending_project_sales`, no purchasing response,
  responder or response time, no comment by anyone else, no form action, no files, and any SLA stage the submit
  opened is untouched (nobody responded to, took, escalated, resolved or voided it, commented on it, or asked to
  take it over). Deleted with it: its revision row, its in-app notifications, the contact's own notes, its
  untouched SLA stages (their events cascade) and its public view link.
- AC-16 Outside AC-15 the proposal is refused with "It is with the team now, so I can't withdraw it. I can add a
  note to it instead." Another contact's inquiry is refused as not found.

## Console = test (W2-Q3 (a))

- AC-17 A console turn proposes as live does, and its confirm writes nothing (no inquiry, no comment, no delete);
  the step note says "Test turn: nothing was sent."
- AC-17b A contact's live proposal is confirmed or cancelled only from its own WhatsApp turn; the console (route or
  console turn) is refused. A console test proposal is decided only from the console. Neither expires nor answers
  the other, and a turn decides only the proposal it is waiting on (security review rounds 1-2).

## Read

- AC-18 `crm_my_requests_list` returns only the contact's own submitted requests of its visible kinds, newest
  first, at most 20, each with kind, id, number, status, product code, submitted date, and the contact's own
  notes (id, text, time). Drafts and other contacts' rows never appear.

## Router (W2-Q4 (a), owner 1 Nov)

- AC-19 Unchanged: any open bot question, the knowledge-miss escalation offer included, keeps the next message on
  the bot.
