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

(scout in progress)
