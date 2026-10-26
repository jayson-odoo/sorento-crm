# PLAN: Outbox row attachments can be downloaded and previewed (OUTBOX-ATTACHMENT)

Status: merged (PR #1879, 4b56708771, 26 Oct 2026; small fix track). Reviewer READY,
security-reviewer CLEAN, browser pass 1280/375 PASS, owner hand test PASS.

UAC: `documentation/plans/_archive/email/outbox-attachment-acceptance-criteria.md`

## Journey

The owner checks an Order Inquiry handover email in System Management > Email Outbox. The row
detail dialog shows the Metadata JSON with `extra_attachments: [{filename: "OI-2609-0042.xlsx",
storage_key: ..., storage_provider: "r2", optional: true}]`, but there is no way to open the file
to compare it with the email body. Owner ask (26 Oct): "in the outbox you need to let me download
or preview the attachment so I can double check".

## What exists (measured)

- An outbox row carries attachments from two places, read in this order by the drainer
  (`sorento_crm_backend/app/tasks/email_outbox_tasks.py` `_attachments_for`):
  1. the row's own columns `attachment_filename` / `attachment_storage_provider` /
     `attachment_storage_key` (`app/models/email_outbox.py:52-54`);
  2. `metadata_json["extra_attachments"]`, each `{filename, storage_key, storage_provider,
     optional}` (container request supplier list, OI handover files).
- Bytes are read with `storage_router.get_backend(provider).download_file(key)`
  (`_fetch_attachment`, which also maps the extension to a mime type).
- The detail dialog is `EmailOutboxList.tsx` ("Outbox row detail"), fed by
  `GET /api/v1/system/email-outbox/{row_id}` behind `system.email_outbox.view`.
- `components/common/AttachmentPreviewModal.tsx` already previews Excel (sheet grid) and PDF
  from a same-origin byte route (`downloadUrl` read through `apiFetch`) and carries its own
  Download button. `lib/save-blob.ts` `saveBlobAs` saves fetched bytes.

## ARCHITECTURE

- Layer: backend system API (`app/api/v1/system/email_outbox.py`) + the drainer's attachment
  walk; frontend email-outbox feature folder (service -> hook-free direct call from the dialog,
  same as the existing preview modal callers).
- Shared mechanism: ONE walk over a row's attachments, `attachment_refs(row)` in
  `email_outbox_tasks.py`, used by both the drainer (`_attachments_for`) and the API, so the
  dialog lists exactly what the email sends, in the same order.
- Classes fixed: every outbox event that carries files (column attachment and every
  `extra_attachments` producer), not only the OI handover.

## Design

Backend
- `attachment_refs(row) -> list[dict]`: `{filename, storage_provider, storage_key, optional}` for
  the column attachment (if a key is set) then each well-formed `extra_attachments` entry.
  `_attachments_for` iterates it (behaviour unchanged).
- `EmailOutboxRowResponse.attachments: list[{index, filename}]` built from `attachment_refs` (no
  storage IO, no keys exposed).
- `GET /api/v1/system/email-outbox/{row_id}/attachments/{index}` behind
  `require_permission("system.email_outbox.view")`. The object served is
  `attachment_refs(row)[index]`; there is no key parameter, so only a key the row itself carries
  can be served. Unknown row or index out of range -> 404. Storage reports the object missing ->
  404 "Attachment file not found in storage". Other storage failure -> 502. Bytes returned with
  the mapped mime and `content_disposition(filename)`.

Frontend
- `EmailOutboxRow.attachments?: {index, filename}[]`.
- Service `downloadEmailOutboxAttachment(rowId, index)` -> Blob (errors via `extractApiError`), and
  `emailOutboxAttachmentUrl(rowId, index)` for the preview modal's `downloadUrl`.
- Dialog: an "Attachments" block (only when the row has any) listing each filename with a
  Preview button (Excel/PDF only, the kinds the modal renders from bytes) and a Download button.
  Download saves via `saveBlobAs`; failure toasts the server message. Preview opens
  `AttachmentPreviewModal` at that file. Images are Download only: the modal renders images from
  a public URL, and this route is authenticated (no new signed-URL surface for one screen).

## Tests (red first)

Backend `tests/test_email_outbox_attachment_download.py` (MagicMock DB + TestClient, the
`test_email_outbox_bulk.py` pattern):
1. detail response lists column + extra attachments as `{index, filename}` in drainer order.
2. download index 0 / 1 returns the right bytes, mime and filename; the backend was asked for the
   row's own key.
3. index out of range -> 404, storage never called.
4. missing row -> 404.
5. storage "not found" -> 404 with the clear message.
6. no `system.email_outbox.view` -> 403.
7. malformed `extra_attachments` (non-string key / filename) never 500 the row.

Frontend `EmailOutboxAttachments.test.tsx` + `emailOutboxService.test.ts` (vitest):
1. dialog shows each attachment filename with Download; no block when none.
2. Download calls the service with (row id, index) and saves the blob under the filename.
3. Download failure toasts the server message.

## Out of scope

- Image preview in the modal (needs a public or signed URL); Download covers it.
- Showing attachments in the list grid.
