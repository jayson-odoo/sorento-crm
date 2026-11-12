# UAC: Last activity column on every form list (FORMS-LAST-ACTIVITY)

Answers (crew, 12 Nov, owner may adjust): Q1 (a), Q2 (a), Q3 (a), Q4 (a), Q5 (a). Card:
`forms-last-activity-behaviour-card.md`.

Forms in scope (audit entity type -> table):
`complaint` -> complaints, `purchase_request` -> purchase_requests (PR + Sponsorship),
`price_tag_requests` -> price_tag_requests, `project_sample_requests` -> sample_requests,
`new_product_application` -> new_product_applications, `stock_inquiry` -> stock_inquiries,
`workflow_submissions` -> workflow_submissions.

Dev data findings (crew, prod clone 12 Nov, counts only):
- Sponsorship header rows were audited as `sponsorship_form` before the model pinned
  `purchase_request`; both types map to `purchase_requests`.
- Sample requests live in the `projects` schema (`projects.sample_requests`, `sr_0001`); raw SQL
  resolves the schema like `sr_0001_sample_requests.py:43` does.
- Pre-stamp rows have `actor_type = 'legacy'` and often `root_entity_type` NULL (complaint 3,757,
  PR 898, SF 126, SI 820). Matching is entity OR root, so they are found.
- Attachment audit rows never carry the form as root; a form's files hang off
  `entity_attachment_links(entity_type, entity_id, attachment_id)` (price tags use the singular
  `price_tag_request` there).
- Backfill timing on the prod clone (audit_logs 589,951 rows): 5-18 ms per table. Plain UPDATE in the
  migration, no job.

## Backend

- U1 Each of the 7 tables has a nullable, indexed `last_activity_at` (timestamp without tz, same
  clock as `audit_logs.changed_at`). Migration is additive and backfills: newest person `audit_logs`
  row whose `root_entity_type/root_entity_id` (or `entity_type/entity_id`) is the record, or newest
  non-system form comment, whichever is later; else `created_at`.
- U1b Backfill counts `legacy` rows (they predate actor stamping and are staff edits) and excludes
  `worker`, `scheduler`, `system`, `integration`; it also counts `entity_attachment_links.created_at`
  for the record's links.
- U5b Linking a file to a form (an `entity_attachment_links` row created or deleted for the form by a
  person) moves `last_activity_at`.
- U2 A new record has `last_activity_at` = its create time (never NULL after create by a person or
  a system path).
- U3 A person's audited change on the record (header edit, status change, approve/reject, line
  add/edit/remove rolled up by `__audit_parent__`, attachment row rooted on the record) sets
  `last_activity_at` to that audit row's time. Person = audit `actor_type` in (`user`, `contact`,
  `public_link`).
- U4 The same change written by a non-person actor (`worker`, `scheduler`, `system`,
  `integration`, or no actor) does NOT move `last_activity_at`.
- U5 A new form comment or reply (`entity_conversation_messages`, scope `form_comment`,
  `is_system` false) by staff or a portal contact sets the form's `last_activity_at`. A system
  comment, a comment edit or a comment delete does not.
- U6 A bulk change through the bulk DML audit path (one statement over N records) stamps each of
  the N records.
- U7 Each list endpoint accepts sort `last_activity_at` asc/desc on the stored column, ties broken
  by `created_at` desc then id, so page 2 continues page 1 with no repeats or gaps.
- U8 Each list endpoint accepts `last_activity_from` / `last_activity_to` (dd range, inclusive whole
  days, Malaysia time like the other date filters) and combines them with the existing filters.
- U9 With no sort param, every form list sorts by `last_activity_at` desc (Q1).
- U10 Each list row returns `last_activity_at` (assert in a response_model test).
- U11 Stock Inquiry: sort `last_activity_at` reads the stored column, no longer
  `coalesce(last_revised_at, created_at)`.
- U12 Workflow submissions: list returns and sorts `last_activity_at`; `updated_at` stays in the
  payload but is no longer the default sort.

## Frontend

- F1 Complaint, Purchase Request, Sponsorship, Price Tag Request, Sample Request, New Product
  Application, Stock Inquiry and Workflow form submissions lists each show a "Last activity" column,
  one line, `dd/mm/yyyy, h:mm am/pm` via `formatDateTimeInMalaysia`, "-" when missing, no tooltip,
  no "Revised" prefix.
- F2 Default sorting on each list is Last activity, newest first; clicking the header cycles
  asc / desc / off and sends `sort=last_activity_at&dir=...` to the server.
- F3 Filters panel on each list has a "Last activity" date range (shared `DateRangePicker`) that
  sends `last_activity_from` / `last_activity_to`; it shows as a removable chip like the other filters.
- F4 The column is listed in Columns (hide/show/reorder) like every other column.
- F5 Workflow submissions: the "Updated" column becomes "Last activity".
- F6 Usable at 375 px and 1280 px; the column never wraps.

## Out of scope

- Price Tag Request History tab (no History tab today; separate lane).
- Tooltip with the event name (Q4 a).
