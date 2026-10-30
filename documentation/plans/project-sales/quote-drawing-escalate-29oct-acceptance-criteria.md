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
- **AC-3 One task per product and kind.** Escalating a product with no open task of that kind
  (`drawing` or `photo`) creates exactly one task (`source_entity_type = product_drawing |
  product_photo`, `source_entity_id = product id`) on the general-enquiries route the WhatsApp bot
  uses for product attachment asks: access agent `general_enquiries`, the team set the chatbot
  domain `product_attachment` names, the tier-1 team of that set in the product's company, a
  round-robin assignee narrowed by the product's brand, the team set's SLA policy, deadlines on
  the working calendar, assignee notified. Nothing is configured per feature and no team, agent or
  policy is named in code. A tier escalation keeps the brand.
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
- **AC-9 Not routable.** When the route has a missing piece (agent, domain row, team, member,
  policy, tier), Escalate returns 409 "The marketing product team has no members for this
  company" and creates nothing; the detail is only in the log. Escalating a product that has a
  drawing (drawing kind) or any photo (photo kind) returns 409 and creates nothing.
- **AC-10 Permission.** The escalate endpoint returns 403 without view or view_own, and 404 for a
  quotation outside the caller's own scope. Respond and resolve follow the existing form-SLA task
  actor rules (assignee, or the team chain).
- **AC-11 No setup.** There is no Form SLA type, step or event for drawing or photo requests; the
  Form SLA config dialog does not offer them.
- **AC-14 Photo.** A saved catalogue line whose product has no photo at all (photo cell state
  "no photos") shows the same Escalate tile in the Photo column (kind `photo`, own task, own
  state, own Respond/Resolve row "Product photo"). A product with photos that are not chosen
  shows today's photo cell and no Escalate. Linking a photo to a product with an open photo task
  notifies its assignee and closes nothing; resolving names the kind in the requesters' notice.
- **AC-12 WhatsApp and email at every hand-off** (owner, 30 Oct 10:00). Opening the task (to the
  assignee), each tier escalation (to the new assignee), a drawing linked while open (to the
  assignee) and resolve (to every requester) each create in-app, email and WhatsApp deliveries
  through the existing notification service, email and WhatsApp gated by the recipient's
  per-event toggles (`notify_*_on_assignment`, `notify_*_on_escalation`) and a linked WhatsApp
  contact. Tests assert the delivery rows; no test sends a message.
- **AC-13 Minimal UI** (owner, 30 Oct 10:00). Only the states in mock v3; no new banner, badge,
  dialog, step or page.
