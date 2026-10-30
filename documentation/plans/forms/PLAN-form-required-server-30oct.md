# PLAN: server enforces required fields on form submit (FORM-REQUIRED-SERVER)

Status: Merge-ready (small fix track: no migration, no RBAC change, no new ingest surface;
backend only). Lane FORM-REQUIRED-SERVER, PR #2008. UAC: `form-required-server-acceptance-criteria.md`.

## Problem

Found by PORTAL-P4-REQUESTS (#1953) while building the owner's "happy and not happy path of
all form submission" regression (30 Oct). For stock_inquiry, complaint, purchase_request and
sponsorship_form the server did not enforce required fields: a blank draft could be
submitted (200, status submitted, number assigned, SLA started, team notified). Only
SubmissionForm's required flags stopped it, in the browser, and the portal is a public
token-reached surface.

## Where the required flags live

- SubmissionForm: `sorento_crm_frontend/app/(auth)/portal/components/SubmissionForm.tsx`
  `FIELDS` (`required: true` per field), plus the complaint "At least one product" added in
  `collectMissingRequired` as `product_lines`. No server form definition carried them.
- Project registration already had its own server list
  (`project_registration_service.REQUIRED_ON_SUBMIT`), untouched.
- The external / chatbot / MCP create paths have their own, stricter contracts
  (`complaints_service.py` `_complaint_submission_required_fields`,
  `procurement_service.py` `_STOCK_INQUIRY_SUBMISSION_REQUIRED_FIELDS`,
  `_PR_REQUIRED_FIELDS_BY_TYPE`), untouched.

## Decision (crew answer (a), 30 Oct)

The server list `sorento_crm_backend/app/services/portal_required_fields.py` is canonical.
`tests/test_form_required_server.py` parses SubmissionForm's FIELDS and fails if the two
differ, so there is one truth enforced by CI. FE and BE build from separate Docker contexts,
so a shared file was not an option.

Follow-up (b), after #1953 merges: expose the list as `required_fields` on `GET /me` and let
SubmissionForm read it instead of its own flags.

## Fix

- `portal_required_fields.require_complete(kind, row)`: 422,
  `message = "Fill in the required fields before submitting."`,
  `detail = <missing names, comma separated>`, `code = VALIDATION_ERROR` (the body project
  registration answers with, and the shape `portal-client.ts` `throwSubmissionError` reads).
- `PortalService.submit_draft`: called in each kind's branch after its status guard (so
  "Cannot submit X with status Y" still wins) and before any write; `portal_draft_at = None`
  moved below the branches so a refusal leaves the row as it was.
- `PortalRevisionService.revise`: called after the payload is applied, beside the
  sponsorship unit-price check, skipping the adapter's `frozen_on_revise` fields
  (security-review finding: the requestor is frozen, so demanding it would refuse a row
  created without one on every revise with no way out).
- Draft saves are never checked.

## Entry points and integrations checked

- `submit_draft` has one caller, the portal route (`api/v1/public/portal.py`). #1953 mounts the
  same route body on `/api/v1/my-requests`, so it inherits the check.
- n8n, MCP and the chatbot create through the external routes, which never call
  `submit_draft`; none starts failing.
- Existing data: a stored draft or a rejected row missing a required field now needs that
  field filled before it can be (re)submitted, which is what the form asks for anyway.

## Tests

- Red 7f5ebcde, fix 00e202df + 0daf0bb5, revise frozen-field skip f2ec101b.
  `tests/test_form_required_server.py` 28 tests.
- 71 existing tests submitted incomplete forms; their fixtures (9 files) now carry the
  required fields (no assertion changed). Portal set 1789 passed; wider set 4584 passed,
  5 failed, all 5 failing on main too.
- Reviewer READY (kill tests per code path and per form drift); security reviewer CLEAN.
- Diff is about 510 lines, but about 90 are app code; the rest is tests and docs, so the small
  fix track holds in spirit.
