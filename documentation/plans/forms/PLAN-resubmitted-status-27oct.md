# PLAN - Resubmitted status (submit after a rejection)

Status: IN REVIEW - all 7 forms built red-first; reviewer round 1 fixed, security review clean, browser pass 8/8 + 375px; awaiting owner hand-test (PR #1925). Track: L (owner, 27 Oct: crosses 7 workflows; migration resub_0001).
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

## Behaviour card and owner rulings (27 Oct ~22:05)

Rule: a submission that answers a rejection gets status **Resubmitted**, on every form with a
reject -> amend -> submit-again path, and behaves exactly like the stage it stands in for. The
send button reads **Resubmit** (portal and staff) on a rejected form.

| Q | Ruling |
|---|---|
| Q1 scope | (b) all 7 forms: complaint, PR/SF, NPA, stock inquiry, project registration, quotation approval, dealer-kit edition |
| Q2 word | "Resubmitted" everywhere, staff and portal |
| Q3 lists | own filter option and own pill colour (cyan, beside Submitted's sky); counted with awaiting work |
| Q4 notifications | say "resubmitted" on every form |
| Q5 existing rows | relabel where the data proves a resubmission; reversible; dry-run counts first on a crew-run copy |

## Design calls (made in build, flagged for review)

- One helper per side: `app/services/submission_status.py` (`status_on_submit`, `is_awaiting_review`,
  `awaiting_review_statuses`) and `sorento_crm_frontend/lib/submission-status.ts` (`isAwaitingReview`,
  `submitVerb`). No per-form copies.
- Stock inquiry: `resubmitted` stands in for `pending_project_sales` only. An API resubmit that names
  `new` (not submitted yet) or `pending_purchasing` (skips that review) keeps the stage it named.
  Staff Reopen is not a submission and still restores `rejected_from`.
- Project registration: `approval_state='resubmitted'`; the board keeps it in the Awaiting approval
  lane; the code slot reads "Resubmitted" (`project_label` BE / `projectCodeLabel` FE stay mirrored).
- Quotation and Edition (status graphs): a real `resubmitted` rung copied from `pending_approval`, plus
  edges draft -> resubmitted, resubmitted -> approved, resubmitted -> rejected (so the engine, not code,
  stays the authority). If an admin deletes the rung, the press lands on pending as before.
- Edition resubmit is detected by the rejection reason Reopen deliberately keeps until the next submit.
- Revision eligibility (`portal_revision_configs.allowed_statuses`, admin data) reads `resubmitted` as the
  adapter's review stage, so no settings data migration.
- Backfill (`scripts/backfill_resubmitted_status.py`): complaint (rejected_at kept), NPA (reject_reason
  kept), PR/SF and stock inquiry (newest audited status change was from rejected), quotation (the
  approval event before the newest request was a rejection). Project registrations and Editions keep no
  proof, so they are left as they are.

## Gates widened (file:line, as built)

Backend:
- `app/services/portal_service.py:1124` complaint, `:1138` stock inquiry, `:1191` PR/SF: submit lands on resubmitted
- `app/services/complaints_service.py:1782` chatbot edit of a rejected complaint (`resubmit_rejected_complaint`); `app/api/v1/complaints/complaints.py` calls it
- `app/services/response_gate.py:91` complaint response stage accepts resubmitted
- `app/services/procurement_service.py:6176` SI API resubmit; `:6967` / `:7043` project-sales approve / reject; PR list filter `resubmitted`; PR notify wording
- `app/api/v1/procurement/stock_inquiries.py:421` create notify condition
- `app/services/portal_revision_service.py:792` revision eligibility
- `app/services/new_product_application_service.py:72` LOCKED, `:380` submit, `:398` approve/reject, `:467` withdrawn notice, `:473` cancel, `_EVENTS["resubmitted"]`
- `app/services/project_registration_service.py:260` duplicates, `:672` submit, `:928` approve, `:982` reject, notify "resubmitted"
- `app/services/project_service.py:434` approver read access, `:915` may-edit, `_NOT_APPROVED_MESSAGES`, `project_label`
- `app/api/v1/projects/projects.py` `_APPROVAL_FILTERS`
- `app/services/project_quotation_approval_service.py:73` AWAITING_KEYS, `:76` LOCKED_KEYS, `move()` lands on the rung, `notify_requested` wording
- `app/api/v1/projects/quotation_documents.py:556` withdrawn notice on revise
- `app/services/dealer_kit/edition_service.py` OPEN_STATUS_KEYS, `submit()` target; `page_service._bypass_message`
- labels: `form_action_notify._STATUS_LABELS`, `record_context_service._pr_display_status`, `stock_inquiry_pdf_service`, `reports/datasets/sponsorship_forms.STATUS_LABELS`, chatbot tool text (`mcp_tool_capability_service`, `sorento_crm_mcp/catalog.py`)

Frontend:
- `lib/status-pill.ts`, `lib/status-badge.ts`, `lib/complaint-status.ts`, portal `SUBMISSION_STATUS_LABELS` + `submitVerb`
- `ComplaintDetail.tsx` primary CTA; `ComplaintsList.tsx` filter
- `PurchaseRequestDetail.tsx:569`, `PurchaseRequestsList.tsx` pill + filter, `PurchaseRequestDocumentEditCard.tsx`
- `NewProductApplicationDetail.tsx:374,588`, `NewProductApplicationsList.tsx`, portal `NewProductApplicationForm.tsx:209`
- `StockInquiryDetail.tsx:632`, `stockInquiry.types.ts` labels
- `ProjectDetailClient.tsx:189`, `ApprovalStatePill.tsx:15`, `PipelineBoard.tsx` lane, `PipelineClient.tsx` filter, `projectCode.ts`
- `quotationDecision.ts:66-90`, `QuotationApprovalPanel.tsx:28`, `QuotationDocumentClient.tsx` send label, `useQuotationDocuments.ts` toast
- `EditionDetail.tsx:134` + Resubmit for approval label
- Portal `SubmissionForm.tsx` and NPA forms: Submit -> Resubmit on a rejected form

## Browser pass (agent-browser, sandbox stack, 27 Oct)

All PASS at 1280px, plus 375px spot-checks on the complaint detail and the quotation document. Evidence:
`documentation/plans/forms/evidence/resubmitted-status/`.

| # | Form | Checked |
|---|---|---|
| 1 | Complaint | cyan Resubmitted pill (list + detail), list filter option, Edit technical team response is the primary button |
| 2 | Portal complaint (rejected) | button reads "Resubmit complaint", dialog "Resubmit this complaint?" (cancelled) |
| 3 | Purchase request | list pill + filter option, Change to pending approval + Reject on detail |
| 4 | Stock inquiry | pill, Approve (send to purchasing) + Reject |
| 5 | New product application | label, filter option, Approve + Reject |
| 6 | Project registration | Awaiting approval lane, "Resubmitted" in the code slot, Approval filter option, Approve + Reject |
| 7 | Quotation | Resubmitted standing, "with a manager for approval" banner, Approve + Reject |
| 8 | Dealer-kit edition | Resubmitted pill, Approve + Reject |
