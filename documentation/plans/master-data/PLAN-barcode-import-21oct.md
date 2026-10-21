# PLAN: Import barcodes from Excel (BARCODE-IMPORT)

Status: in review (PR #1811); audit round (UAC 9-14) + security rounds 2-3 (UAC 15) at 1625dd4f91; final re-review, then crew hand test. Track: small fix track (size S+, no migration, no new permission; reuses
`master_data.products.edit`). Owner request 21 Oct 2026.
UAC: `barcode-import-acceptance-criteria.md`.

## Why

The owner generated an Excel of barcode per product code and wants it bulk-updated. The
existing product bulk import (`POST /master-data/products/bulk-import`) needs item_group and
overwrites name/brand/price, so it cannot be reused for one column.

## Facts (origin/main)

- `products.barcode` String(100), nullable, indexed, NOT unique by design
  (`app/models/product.py:275`, migration `455_products_barcode.py`).
- CRM owns it; AutoCount ESB push overwrites only when non-empty
  (`master_ingest_service.py:627-633`); AutoCount Pull maps no barcode.
- Template: reorder levels preview/apply (`app/api/v1/scm/reorder_levels.py:158-184`),
  upload guard `app/services/scm/upload_intake.read_upload`.

## Build

- BE `app/services/product_barcode_import_service.py`: parse .xlsx/.csv, find the code and
  barcode columns by common header names (case-insensitive), classify each row:
  `new`, `change`, `same`, `unknown_code`, `blank_barcode`, `too_long` (error, >100);
  warnings `duplicate` (barcode on another product or twice in the file) and `not_ean13`
  (EAN-13 checksum, Python port of `lib/dealer-kit/barcode.ts`; the TS copy stays for the tag
  editor). Two extra skip statuses: `repeated_code` (same code twice in the file, first row
  wins) and `ambiguous_code` (code matches more than one product in the caller's company scope). Apply writes only new + change rows
  in one transaction, one `audit_logs` row per product changed.
- Routes `POST /api/v1/master-data/products/barcode-import/{preview,apply}` (multipart), both
  gated by `master_data.products.edit`. The template is generated in the browser (two headers),
  no endpoint.
- FE: Products list > Actions > "Import barcodes" dialog: pick file, Test (preview table with
  counts and per-row status, columns used), Apply, result counts. Template download.

## Tests (red first)

Preview statuses, apply writes only new/change, permission 403 on both, audit rows written.
