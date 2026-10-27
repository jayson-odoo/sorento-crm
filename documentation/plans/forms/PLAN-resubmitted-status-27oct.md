# PLAN - Resubmitted status (submit after a rejection)

Status: SCOUTING - behaviour card pending owner answers. Track: TBD (likely M: migration + shared helper).
Lane: RESUBMITTED-STATUS
Slug: `resubmitted-status-27oct`

## Ask (owner, 27 Oct)

"we need to change our submit after rejected to be called resubmitted across all forms and also change
our audit trail so the record for this complaint can show it is resubmitted with also the changes".
Kay: "change to Resubmitted/Appealed" (CMP26-0219 rejected twice, customer resubmitted each time and
the status just went back to Submitted).

Out of scope here: the audit-trail display ("Resubmitted" label on rejected -> submitted + field diff)
is lane AUDIT-TRAIL-DIFF (PR #1924). This lane adds the real status value.

## Scout

### Complaints (verified)

- Column: `complaints.status` is a plain `String(50)` with no CHECK and no enum (`app/models/complaints.py:50`).
  Adding a value needs no DDL.
- Reject: `ComplaintService.decide_complaint` (`app/services/complaints_service.py:2109-2186`), only from
  `responded`. It sets `status='rejected'` plus `rejection_reason/rejected_at/rejected_by`.
- Resubmit path 1, portal contact: `PortalService.submit_draft` (`app/services/portal_service.py:1118-1123`),
  `draft|rejected -> submitted`. It does NOT clear `rejected_at`, so `status='submitted' AND rejected_at IS NOT NULL`
  identifies every past resubmit (a candidate backfill rule).
- Resubmit path 2, chatbot/integration "edit via submit": `POST /complaints` with an update identifier is allowed
  only on `rejected` (`app/api/v1/complaints/complaints.py:1066-1105`). It calls `update_complaint` with the payload,
  so status stays whatever the payload carries (`rejected` if none). To check: whether n8n sends a status.
- Team notification: `notify_team_complaint_external_created(is_resubmission=True)` already says
  "Complaint resubmitted" (`complaints_service.py:1199-1206`), fired from `portal_service.py:1929-1935`.
- Consumers keyed on `submitted` that must accept `resubmitted`:
  - Response gate `ALLOWED_RESPONSE_STATUSES["complaint"]` (`app/services/response_gate.py:90`). Without it the
    technical team could NOT respond to a resubmitted complaint. FE follows `response_write_allowed` from the API
    (`ComplaintDetail.tsx:197`), so no FE copy.
  - Primary-CTA emphasis `complaint.status === 'submitted'` (`ComplaintDetail.tsx:568`).
  - Void allow-list is a block-list (`complaints_service.py:2433`), so resubmitted stays voidable.
  - Chatbot tool description lists known statuses (`app/services/mcp_tool_capability_service.py:1665`).
  - Labels: FE `lib/complaint-status.ts` (pill + label, shared by staff view and portal), portal
    `SUBMISSION_STATUS_LABELS` (`app/(auth)/portal/lib/portal-client.ts:1012`), shared `lib/status-pill.ts:11`,
    `lib/status-badge.ts:62`; BE contact wording `form_action_notify._STATUS_LABELS` (`form_action_notify.py:155`).

### Other forms

Two groups. Group A: after a resubmit the status literally goes back to `submitted`. Group B: it goes
back into a workflow stage that the approve and reject gates are keyed on.

Group A (status reads "Submitted" again):

- Purchase request / sponsorship form: `status` and `approval_status` are both plain `String(50)`
  (`app/models/procurement.py:1183,1193`). Portal resubmit sets `status='submitted'` and clears
  `approval_status` (`portal_service.py:1184-1195`). Staff "Change to pending" and "Reject" buttons
  require `status === 'submitted'` (`PurchaseRequestDetail.tsx:567-583`). Display rule is duplicated in
  `getDisplayStatus` (`PurchaseRequestsList.tsx:61-76`), `form_action_notify._pr_display_status`
  (`form_action_notify.py:171-205`) and `record_context_service.py:85-101`. Portal revision config
  `allowed_statuses` seeds `("submitted","approved")` (`alembic/versions/portal_rev_0001_...py:47-48`).
  Existing gap: the external upsert (`procurement_service.py:8322`) never moves `status` off `rejected`.
- New product application: `status` `String(20)` with CHECK `ck_new_product_applications_status`
  (`app/models/new_product_application.py:63,110-112`), so it NEEDS A MIGRATION. Resubmit (staff applicant or
  portal contact) sets `SUBMITTED` (`new_product_application_service.py:376`). Approve/reject require
  `SUBMITTED` (`:395,:407`), `LOCKED` (`:67`), revise "withdrawn" (`:454`), approver notify `_EVENTS["submitted"]`
  (`:1028`). FE: `NewProductApplicationsList.tsx:51`, `NewProductApplicationDetail.tsx:372-373,587`, portal
  `NewProductApplicationForm.tsx:206-208`.

Group B (status goes back into a stage, never "Submitted"):

- Stock inquiry: resubmit sets `pending_project_sales` (`portal_service.py:1134`); approve/reject require it
  (`procurement_service.py:6961,7035`); staff buttons gate on it (`StockInquiryDetail.tsx:631`).
- Project registration: `approval_state` back to `pending` (`project_registration_service.py:670`); approve/reject
  require it (`:898,:971`); 422 allow-list `projects.py:57`.
- Quotation approval and dealer-kit edition: status rows in the shared `statuses` / `status_transitions` tables,
  rejected -> draft -> `pending_approval` (`project_quotation_approval_service.py:396-403`, `edition_service.py:240,295-301`).

No same-record resubmit after a rejection: sample requests, workflow forms (rejected is terminal), onboarding,
price tag requests, order inquiry rows, GRNs, cost price change sets ("returned", not rejected), tickets.

Word already in use: portal revision history has a `resubmission` kind labelled "Resubmitted"
(`portal_revision_service.py:2001`); notification event types `resubmitted` / `external_resubmitted`.

Shared label maps a new value goes in: FE `lib/status-pill.ts`, `lib/status-badge.ts` (keyword fallback would
NOT match `resubmitted`), `lib/complaint-status.ts`, portal `SUBMISSION_STATUS_LABELS`. BE has no single map
(copies in `form_action_notify`, `response_gate`, `stock_inquiry_pdf_service`, `record_context_service`,
`reports/datasets/sponsorship_forms`, NPA `STATUS_LABELS`).

## Behaviour card

Posted to the PR as a crew-ask; answers recorded here once received.
