# UAC: Escalate a missing technical drawing from a quotation line

Plan: `PLAN-quote-drawing-escalate-29oct.md`. Draft against the card's recommendations; final once
the owner answers Q1-Q5.

## Journey

A salesperson building a quotation sees a line whose product has no technical drawing. They click
Escalate on that line. The team that owns product drawings gets one task with a deadline. The
salesperson sees "Escalated <date>" on the line, and when the drawing is added they are told, and
the line shows it.

## Acceptance criteria

- **AC-1 Button.** A saved line whose Drawing cell state is `no_drawings` shows an Escalate tile to
  a user with `projects.projects.edit`; a user without it sees "no drawing". Lines with a drawing,
  off-catalogue lines and unsaved lines show no Escalate.
- **AC-2 One request per product.** Escalating a product with no open request creates exactly one
  form-SLA tracker (`source_entity_type = product_drawing`, `source_entity_id = product id`),
  assigned by round-robin in the configured stage's tier-1 team, with response and resolution
  deadlines from the stage's SLA policy.
- **AC-3 Join, not duplicate.** Escalating a product that already has an open request, from any
  quotation and by anyone, creates no second tracker and records the caller as a requester. The
  same caller escalating twice is recorded once. Two concurrent escalations create one tracker.
- **AC-4 Escalated state.** Every saved line of every quotation whose product has an open request
  reads `technical_drawing.escalation = {opened_at, due_at_resolution, requester_count}`; the cell
  shows "Escalated" with the opening date, coloured by the resolution deadline (neutral, amber
  under 4h, red overdue).
- **AC-5 Self-close.** Linking an image typed "Technical Specifications" to the product, or
  retyping an image already linked to it, resolves the open request. Linking a PDF, or an image of
  another type, does not.
- **AC-6 Tell the requesters.** On self-close, every requester gets one in-app notification
  "Drawing added for <product code>" linking to the quotation they escalated from. No WhatsApp,
  no email.
- **AC-7 Manual close.** The assignee can resolve the request with the existing SLA resolve
  action; requesters are not told a drawing was added.
- **AC-8 Not set up.** With no active `product_drawing` stage configured, Escalate returns 409
  "No team is set up for drawing requests" and creates nothing.
- **AC-9 Permission.** The escalate endpoint returns 403 without `projects.projects.edit`, and
  404 for a quotation line the caller cannot see.
- **AC-10 Frozen versions.** Lines on superseded or issued versions show the escalated state but
  are never changed by the drawing arriving.
