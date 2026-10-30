# UAC: Escalate a missing technical drawing from a quotation line

Plan: `PLAN-quote-drawing-escalate-29oct.md` (card v2, owner answers 30 Oct folded in). Final once
the owner answers N1-N4; written against their recommendations.

## Journey

A salesperson looking at a quotation sees a line whose product has no technical drawing. They
click Escalate on that line. The team configured for drawing requests gets one SLA task for that
product with a deadline. The salesperson sees "Escalated <date>" on the line. The team responds,
uploads the drawing on the product and resolves the task the normal SLA way, and everyone who
escalated it is told.

## Acceptance criteria

- **AC-1 What counts as a drawing.** A product has a drawing when a non-deleted file typed
  "Technical Specifications" is linked to it and is an image or a PDF. An image shows as the
  thumbnail (unchanged); a PDF-only product shows a PDF tile that opens the file, and the printed
  quotation shows no drawing for that line (unchanged).
- **AC-2 Button.** Every saved catalogue line (a SET line through its driver part) whose product
  has no drawing shows Escalate, on draft and issued versions, to anyone who can open the
  quotation (`projects.projects.view` or `view_own`). Off-catalogue and unsaved lines show none.
- **AC-3 One task per product.** Escalating a product with no open task creates exactly one
  form-SLA task (`source_entity_type = product_drawing`, `source_entity_id = product id`) from the
  configured step: its access agent, team set, SLA policy, round-robin tier-1 assignee, deadlines
  on the working calendar, assignee notified. No team, agent or policy is named in code.
- **AC-4 Join, not duplicate.** Escalating a product that already has an open task, from any
  quotation and by anyone, creates no second task and records the caller as a requester. The same
  caller twice is recorded once. Two concurrent escalations create one task.
- **AC-5 Escalated state.** Every saved line whose product has an open task carries
  `technical_drawing.escalation = {opened_at, responded_at, due_at, requester_count,
  last_resolved_at}`; the cell shows "Escalated <date>", or "Replied <date>" once responded (hover "Responded <date>"), as a Join button,
  coloured by the governing deadline (neutral, amber under 4h, red overdue).
- **AC-6 Normal SLA flow.** The task appears on the home Dashboards page, "My pending tasks" (My
  Pending tab for the assignee, My Team tab for their lead), as "Product drawing . <product code>"
  with Respond, then Resolve; responding and resolving run through the step's configured events. Overdue escalation,
  extend and take-over work as for any form-SLA task. The row opens the product page.
- **AC-7 Adding a drawing does not resolve.** Linking a drawing (image or PDF) to a product with an
  open task leaves the task open and sends the assignee one notification.
- **AC-8 Resolve tells the requesters.** Resolving sends every requester one in-app notification
  "Drawing request for <product code> resolved", linking to the quotation they escalated from. If the product still has no drawing, the cell shows Escalate again and a new
  click opens a new task.
- **AC-9 Not set up.** With no active `product_drawing` step, Escalate returns 409 "No team is set
  up for drawing requests" and creates nothing. Escalating a product that has a drawing returns
  409 and creates nothing.
- **AC-10 Permission.** The escalate endpoint returns 403 without view or view_own, and 404 for a
  quotation outside the caller's own scope. Respond and resolve follow the existing form-SLA task
  actor rules (assignee, or the team chain).
- **AC-11 Setup.** SLA Management > Form SLA config offers type "Product drawing" with events
  escalate, respond, resolve; choosing it on a new step pre-fills team set `marketing_product`,
  editable.
- **AC-12 WhatsApp and email at every hand-off** (owner, 30 Oct 10:00). Opening the task (to the
  assignee), each tier escalation (to the new assignee), a drawing linked while open (to the
  assignee) and resolve (to every requester) each create in-app, email and WhatsApp deliveries
  through the existing notification service, email and WhatsApp gated by the recipient's
  per-event toggles (`notify_*_on_assignment`, `notify_*_on_escalation`) and a linked WhatsApp
  contact. Tests assert the delivery rows; no test sends a message.
- **AC-13 Minimal UI** (owner, 30 Oct 10:00). Only the states in mock v3; no new banner, badge,
  dialog, step or page.
