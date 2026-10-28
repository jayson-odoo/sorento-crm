# PLAN: complaint appeal wording (COMPLAINT-APPEAL-WORDING)

Status: in review (small fix track: wording only, no migration, no auth change)

## Ask

Owner, 28 Oct 2026, after #1942 went live (a complaint's audit trail reads Rejected /
Resubmitted): "can we change to Appealed and the button to Appeal instead of Resubmitted and
Resubmit".

## Decision

- Complaints only. A complaint shows **Appealed** where it showed "Resubmitted" (status pill,
  list filter, portal landing, audit trail heading and summary) and **Appeal** where it showed
  "Resubmit" (portal send button, confirm dialog, toast).
- Display only. The stored status value stays `resubmitted`: the backend, the status engine,
  the chatbot parser, n8n and every other form share that value
  (`app/services/submission_status.py`), so renaming it is not trivial and would need a
  migration. The label layer maps it.
- Other forms (stock inquiry, purchase request, sponsorship, NPA, ...) keep "Resubmitted" /
  "Resubmit" until the owner decides; the PR lists where they show it.

## Acceptance

1. A complaint with status `resubmitted` reads "Appealed" on the staff list, staff detail, the
   linked-complaints panel and the portal landing; the staff list status filter offers
   "Appealed".
2. A complaint's audit trail heads a rejected -> submitted / resubmitted move "Appealed" and its
   summary reads "Rejected → Appealed".
3. A rejected complaint on the portal shows an "Appeal complaint" button, an "Appeal this
   complaint?" confirm, "Appealing..." while sending and an "Appealed." toast.
4. Every non-complaint form still reads "Resubmitted" / "Resubmit".

## What changed (complaints)

| Surface | Where |
|---|---|
| Status label (staff list, staff detail, linked-complaints panel, portal landing) | `sorento_crm_frontend/lib/complaint-status.ts` `resubmitted: 'Appealed'` |
| Staff list status filter | `ComplaintsList.tsx` option label |
| Audit trail heading + status summary (complaint's own rows only, typed text untouched) | `components/audit/AuditTrail.tsx`, `complaintAppealWording` |
| Portal form: button, confirm, "Appealing...", "Appealed." toast, status badge | `app/(auth)/portal/components/SubmissionForm.tsx` |
| Public complaint view link | `app/(auth)/view/complaint/page.tsx` |
| Team in-app + email notification title / sentence | `complaints_service.py` "Complaint appealed" |
| WhatsApp undo correction to the contact | `form_action_notify.py` `_complaint_status_label` |
| Complaint PDF export | `complaint_pdf_service.py` `_status_text` |
| Chatbot (MCP list_complaints hint, wording only) | `mcp_tool_capability_service.py` |

Left as is, on purpose:
- Email template admin name "Complaint created / resubmitted": frozen in migration seed
  `eml_0002_seed_layouts.py` and pinned by `test_frozen_documents_match_registry`; renaming needs a
  data migration. Staff-only admin label; the mail itself says "Complaint appealed".
- Record-context bubble (`record_context_service.py`) passes the raw status code to the model, as it
  does for every other code.
- Complaints Excel export writes raw status codes for every status (existing pattern).

## Other forms still showing "Resubmitted" / "Resubmit" (owner to decide)

- Shared portal send verb `lib/submission-status.ts` `submitVerb` (stock inquiry, purchase request,
  sponsorship, NPA portal + NPA staff detail) and toasts in `SubmissionForm.tsx` / `NewProductApplicationForm.tsx`.
- Portal status map `app/(auth)/portal/lib/portal-client.ts` `resubmitted: 'Resubmitted'`.
- Audit trail heading for every other entity `lib/audit-fields.ts` (`AuditTrailHeading`).
- Backend: `procurement_service.py` (SI/PR/SF "... resubmitted" notification), `portal_service.py`
  (SI), `form_action_notify.py` `_STATUS_LABELS`, `stock_inquiry_pdf_service.py`,
  `reports/datasets/sponsorship_forms.py`, `record_context_service.py` (PR/SF),
  `portal_revision_service.py` (revision label), `new_product_application_service.py`,
  `project_service.py` / `project_seed_service.py` / `project_registration_service.py` (project
  registration + quotation "Resubmit for approval"), dealer-kit editions.
- Unrelated meanings (not this flow): promotion flyer bulk "Resubmit", attachment n8n webhook "Resubmit".
