# UAC - Import source-file retention

**Slug:** `import-source-file-retention`
**Status:** Draft (pre-code → in progress)
**Goal:** Persist the ORIGINAL uploaded file for every file-based import job to the storage
bucket, tied to the import job, so business uploads are retrievable from Import Job Details for
tracing (no need to ask the uploader to re-send the file).

## Scope

File-based import routes that receive an actual `UploadFile` at the backend (raw bytes available):

| job_type | route |
|---|---|
| `order_tracking_import` | `order_management/orders.py::import_order_tracking` |
| `delivery_order_detail_import` | `order_management/orders.py::import_delivery_order_detail` |
| `grn_listing_import` | `procurement/grn.py::import_grn_listing` |
| `grn_lines_import` | `procurement/grn.py::import_grn_lines` |
| `spo_import` | `procurement/spo_allocations.py::import_spo_allocations` (per-file) |

**Out of scope (documented gap):** `product_import` + `warehouse_import` parse the Excel to JSON on
the frontend before upload - no raw file reaches the backend route. Covering them needs a separate
FE change to send the raw blob. Tracked as a follow-up, not in this slice.

## Acceptance criteria

- **AC-1** Given a user uploads an Excel to any in-scope import, When the import job is created,
  Then the ORIGINAL (pre-macro-strip) bytes are uploaded to the bucket under
  `import-sources/{job.id}/{sanitized-original-filename}` and the `import_jobs` row records
  `source_file_key`, `source_file_provider`, `source_file_size`, `source_filename`.
- **AC-2** Given the storage upload fails (creds/network/bucket), When the import runs, Then the
  import still proceeds normally (best-effort), `source_file_key` stays NULL, and a warning is
  logged. Tracing is a side-channel; it must never block a business import.
- **AC-3** Given an import job WITH a stored source file, When the user opens Import Job Details,
  Then a "Download original file" action renders; clicking it fetches a fresh signed URL and opens
  the file.
- **AC-4** Given an import job WITHOUT a stored source file (pre-existing jobs, products/warehouses,
  or a failed upload), When the user opens details, Then no download action renders
  (`has_source_file = false`).
- **AC-5** Given a user who does not own the job and is not admin/superadmin, When they call the
  source-file download endpoint, Then the response is denied (mirrors the existing `get_job`
  ownership check).
- **AC-6** Given an SPO upload with multiple files (one job per file), When jobs are created, Then
  each per-file job stores ITS OWN source file.
- **AC-7** Store the ORIGINAL uploaded bytes, not the macro-stripped/cleaned workbook - tracing
  must reflect exactly what the business sent.

## Non-goals

- Bucket lifecycle / auto-expiry (decision: keep indefinitely; cleanup left to a future bucket
  lifecycle rule).
- Exposing the raw storage key or job UUID in the UI (cursor rule: no UUIDs/keys in UI).
- Products/warehouses raw-file retention (needs FE passthrough - follow-up).
