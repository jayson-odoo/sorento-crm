# Behaviour card: "Last activity" column, sortable, on every form list (FORMS-LAST-ACTIVITY)

Base: origin/main 2cb4c734. Size M, lead pattern. All names below are fake.

Owner ask (12 Nov): "I need like a last activity column so the user can sort by that so all with
latest activity can appear at the top, this applies to all form".

## Scope: which lists count as "forms"

A "form" = a request a salesperson or portal contact submits that then moves through review /
approval / handling and carries its own record page. Seven lists qualify (all sort server-side
today, `manualSorting`):

| # | List | FE list (path under `sorento_crm_frontend/app/(protected)/`) | BE sort map | Table |
|---|------|------|------|------|
| 1 | Complaint | `complaint-management/complaints/components/ComplaintsList.tsx:78` | `services/complaints_service.py:510-531` | `complaints` |
| 2 | Purchase Request | `procurement-management/purchase-requests/components/PurchaseRequestsList.tsx:170` | `services/procurement_service.py:9466-9490` | `purchase_requests` |
| 3 | Sponsorship | `procurement-management/sponsorship-forms/page.tsx` (reuses list 2) | same as 2 | `purchase_requests` (`request_type='sponsorship_form'`) |
| 4 | Price Tag Request | `dealer-kit/price-tag-requests/components/PriceTagRequestsList.tsx:81` | `services/price_tag_request_service.py:2899-2910` | `price_tag_requests` |
| 5 | Sample Request | `project-sales/sample-requests/components/SampleRequestsList.tsx:98` | `services/sample_request_service.py:1272` | `sample_requests` |
| 6 | New Product Application | `procurement-management/new-product-applications/components/NewProductApplicationsList.tsx:96` | `services/new_product_application_service.py:1402` | `new_product_applications` |
| 7 | Stock Inquiry | `procurement-management/stock-inquiries/components/StockInquiriesList.tsx:319-336` (already has a "Last activity" column) | `services/procurement_service.py:5696` | `stock_inquiries` |

Plus, see Q5: the configurable **Workflow form submissions** list
(`workflow-forms-management/components/WorkflowSubmissionsList.tsx:57,167`, table
`workflow_submissions`), which today shows "Updated" sorted newest first.

Not forms (out of scope): marketing form definitions (`forms-management/forms`, `models/forms.py:11`),
chatbot stock asks, onboarding requests.

## Today (code)

- Every record page's History tab is the shared `components/audit/AuditTrail.tsx` reading ONE table,
  `audit_logs` (`api/v1/audit/audit_logs.py:298` -> `services/audit_service.py:543`): rows of the
  record itself plus child rows rolled up by `root_entity_type/root_entity_id` (lines, via
  `__audit_parent__`). It shows create, edits, status changes (`audit_logs.py:205-213`) and
  attachment upload/delete/rename (`audit_logs.py:215-225`).
- Auditing is opt-out (`audit_service.py:94-103`), so all 7 tables above (and `workflow_submissions`)
  already write `audit_logs` rows, including Price Tag Request, whose page has no History tab yet.
- Each audit row records WHO: `actor_type` = user | contact | integration | worker | scheduler |
  public_link | system | legacy (`models/audit.py:75`).
- Form comments are NOT in `audit_logs`: they live in `entity_conversation_messages`
  (`scope='form_comment'`, `models/entity_conversation.py:22-23`, `__audit_skip__`) and show in the
  Comments tab (`sla-management/_shared/FormDetailWithSLATabs.tsx:40-56`).
- Stock Inquiry's current "Last activity" = `coalesce(last_revised_at, created_at)`, shown as
  "Revised <date>" when revised (`StockInquiriesList.tsx:319-336`). It ignores status changes,
  edits, comments.
- `updated_at` is not a clean signal: it is missing on `complaints`, and is bumped by non-activity
  writes (e.g. `portal_draft_at`).
- Nothing stores a per-record "last activity" time; sorting by the newest audit row live means
  aggregating `audit_logs` (the biggest table) on every list load.

## Rules (proposed)

1. **One source for every form:** Last activity = the time of the newest event the record's History
   shows (any `audit_logs` row on the record or rolled up to it: create, edit, status change,
   approval/rejection, line change, attachment) **plus** a new form comment (Q3). No second activity
   log.
2. **Who counts:** a person's action only: staff (`actor_type` user, impersonation included) and
   portal/public-link contacts. Background jobs, schedulers, ERP/AutoCount sync and system rows do
   not move it (Q2). A new record starts at its created time.
3. **Stored, not recomputed:** each form table gets one nullable column `last_activity_at` (indexed),
   set by the existing audit flush listener whenever it writes a person's row for that record (and by
   the form-comment insert). One additive migration backfills it from `audit_logs` (newest person row,
   else `created_at`). Server-side sort on that column, same on page 2.
4. **Column:** header "Last activity", one line, `dd/mm/yyyy, h:mm am/pm` through the shared
   `formatDateTimeInMalaysia` (`lib/helpers.ts:446`, the standing date-time rule), sortable,
   hideable/reorderable in Columns, date-range filter with the shared date picker.
5. **Default sort:** newest activity first on every form list; a user's own remembered sort
   (LIST-FILTER-MEMORY-4) wins once they pick another column (Q1).
6. **Stock Inquiry:** its existing column switches to this rule; the "Revised" prefix goes (one value
   per column; the revision number is its own column already).
7. **Prev/next** on a record follows the list's order, so it follows Last activity when that is the sort.

## Examples (shapes, fake names)

| # | Record | Events | Last activity shown | Why |
|---|------|------|------|------|
| 1 | PR26-0101, Salesman A, created 03/11/2026 9:10 am, approved by Manager B 05/11/2026 2:40 pm, CS marks Processed 10/11/2026 11:05 am | create, approve, processed | 10/11/2026, 11:05 am | newest person event |
| 2 | Complaint CP26-0042, created 01/11/2026 4:00 pm, nothing since | create only | 01/11/2026, 4:00 pm | falls back to created |
| 3 | Price Tag Request PT26-0077, Salesman C comments "please use A3" 11/11/2026 3:15 pm after approval 09/11/2026 | approve, comment | 11/11/2026, 3:15 pm | comment counts (Q3 a) |
| 4 | Sample Request SR26-0050, last person edit 06/11/2026 10:00 am; nightly SLA job re-stamps due date 12/11/2026 2:00 am | edit, scheduler row | 06/11/2026, 10:00 am | scheduler does not count (Q2 a) |
| 5 | Stock Inquiry SI26-0300, revised by portal Contact D 08/11/2026 5:30 pm, purchaser replies 12/11/2026 9:45 am | revision, response | 12/11/2026, 9:45 am (today shows "Revised 08/11/2026") | the reply now counts |

Real dev shapes requested separately (crew data request), to confirm example 4's actor types and the
backfill size.

## Edge cases

- No events since create: shows created time; never blank.
- Bulk action on 20 records (e.g. bulk status change): each of the 20 gets the same time; ties break by
  record number desc so page 2 is stable.
- Bulk ORM writes that skip the flush listener (`audit_service.py:512`, imports): no audit row today,
  so no bump; the import path that creates the record still sets created time.
- Deleted comment: last activity does not move back (the comment did happen; deletion of your own
  comment is not a new activity). Deleted attachment: the delete itself is a History row and counts.
- Viewing, printing, exporting a record: not activity (no History row).
- A line edit (e.g. PR line qty) rolls up via `__audit_parent__` and counts.
- Voided / closed records keep their last time; they sort like any other.

## Questions (answer by letter)

- **Q1 Default sort.** (a) newest activity first on all 7 lists, user's remembered sort wins once
  changed / (b) keep each list's current default (created / submitted / delivery date), Last activity
  only on click. **Rec (a):** your ask is "latest activity at the top".
- **Q2 What counts.** (a) people only: staff and portal contacts / (b) also system: SLA jobs, ERP sync,
  automations. **Rec (a):** a nightly job would otherwise float every open form to the top.
- **Q3 Comments.** Comments sit in the Comments tab, not History. (a) a new comment counts as activity
  / (b) History rows only. **Rec (a):** a comment is the clearest "someone touched this" signal; no
  new log, the column is just stamped on insert.
- **Q4 Cell.** (a) date-time only "12/11/2026, 9:45 am" (the standing date-time format; the brief's
  24-hour HH:mm would break it) / (b) same plus a hover tooltip with the event ("Approved by Manager B").
  **Rec (a):** minimal, and the History tab already says what happened; (b) needs a second stored
  field per form.
- **Q5 Workflow forms.** The configurable Workflow form submissions list already sorts by "Updated"
  newest first. (a) rename it to "Last activity" under the same rule / (b) leave it. **Rec (a):** "this
  applies to all form", one name everywhere.

Column name "Last activity" (already used on Stock Inquiry) is assumed unless you say otherwise.
