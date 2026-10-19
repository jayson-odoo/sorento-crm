# PLAN: portal file picker follows the attachment type's allowed extensions (ATTACH-ACCEPT)

Status: built, in review (small fix track, size S: no migration, no auth/RBAC change, no new ingest surface)

## Journey

Owner, 19 Oct: the "Portal Submission" attachment type allows xlsx and csv, but on a portal form
(the "Requested by" form, attachments box "Drop a file here, paste a screenshot or text, or
Choose file / Paste from clipboard") the OS file picker greys out .xlsx and .csv. Only images,
videos, PDFs and .txt can be chosen.

## Root cause (measured)

- The picker's list is hard-coded: `accept="image/*,video/*,.pdf,.txt"` at
  `sorento_crm_frontend/app/(auth)/portal/components/AttachmentDropzone.tsx:394`. It never reads
  the attachment type.
- The server checks the real list: `POST /api/v1/public/portal/attachments`
  (`sorento_crm_backend/app/api/v1/public/portal.py:1472`) looks up the type by code
  `portal_submission` (`app/services/portal_service.py:102`, `:1923`) and `_check_quota`
  (`portal.py:1243-1258`) rejects any extension outside `AttachmentType.allowed_extensions`
  (`app/models/resources.py:47`, comma string, no dots).
- No portal endpoint tells the browser that list, so the two drifted the moment the admin
  added xlsx/csv.
- One type serves every portal kind (`portal.py:1532`), so one list covers every portal box.

Same component, same bug: `AttachmentDropzone` renders on `SubmissionForm.tsx:2090` (every
generic portal form, incl. the one in the screenshot) and `PriceTagRequestForm.tsx:2171`,
`:2713`. All three are fixed by the one change below.

Out of scope, noted for the report:
- `AIExtractDialog.tsx:465` keeps `image/*,video/*,.pdf,.txt`: that list is what the AI
  extractor can read, not the attachment type.
- `ResponseAttachmentDropzone.tsx:20` (staff complaints, `response_attachment` type) holds a
  hand-copied list of its own type; same drift risk, separate type and screen.

## Fix (one source of truth)

Backend:
1. `parse_allowed_extensions(raw) -> list[str]` in `portal.py`: split on comma, strip,
   lowercase, drop a leading dot, drop blanks, sorted unique. `_check_quota` uses it, so the
   check and what the browser is told cannot disagree.
2. `GET /api/v1/public/portal/me` (`PortalMeResponse`, `portal.py:314`) gains
   `attachment_allowed_extensions: list[str]`, read from the `portal_submission` type. Missing
   type row => `[]` (the upload route already 400s on its own; `/me` must not).

Frontend:
3. `PortalContact.attachment_allowed_extensions?: string[]` (`portal-client.ts:63`).
4. `AttachmentDropzone` takes it as an `allowedExtensions` prop. The forms pass it off the
   `/me` they already fetch, so a `/new` page still makes exactly one `/me` (D7 r3,
   `SubmissionForm.visibility.test.tsx:70`): `SubmissionForm` from its `contact`;
   `PriceTagRequestForm` now reads `/me` on an existing draft too (the visibility check
   stays `/new`-only). The dropzone:
   - `accept` = `.ext` per allowed extension; no `accept` until the list is known or when it
     is empty (server stays the authority, never a wrong list).
   - Never stuck: a dropped, pasted or picked file whose extension is not allowed is refused
     at once (before buffering or upload) with a toast naming it and the allowed types,
     matching the server's wording; the other files still go through.

## Tests (red first)

- pytest `tests/test_portal_attachment_accept.py`:
  - `/me` returns the type's list normalized (seed `"jpg, PNG,.xlsx,csv"` =>
    `["csv","jpg","png","xlsx"]`).
  - `/me` returns `[]` when the type row is missing, still 200.
  - upload of `stock.xlsx` and `stock.csv` accepted when the type lists them; `.exe` refused
    with "Allowed: ..." naming the same list `/me` returned.
- vitest `SubmissionForm.attachAccept.test.tsx`, `PriceTagRequestForm.attachAccept.test.tsx`:
  the list from `/me` reaches the picker, `/me` called once.
- vitest `AttachmentDropzone.accept.test.tsx`:
  - file input `accept` equals `.csv,.jpg,.png,.xlsx` from the mocked `/me`.
  - picking `stock.xlsx` uploads it; picking `setup.exe` does not upload and toasts
    "Allowed: csv, jpg, png, xlsx".
  - pending mode (no submission yet): a refused file is not buffered.

## Verification

Browser pass on the crew test copy, 1280 and 375: on the "Requested by" portal form pick an
.xlsx and a .csv, both attach. Hand-test script `laneboard/scripts/<PR>.md`.
