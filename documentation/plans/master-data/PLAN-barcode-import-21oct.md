# PLAN: Import barcodes from Excel (BARCODE-IMPORT)

Status: building. Track: small fix track (size S+, no migration, no new permission; reuses
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
  (EAN-13 checksum, port of `lib/dealer-kit/barcode.ts`). Apply writes only new + change rows
  in one transaction, one `audit_logs` row per product changed.
- Routes `POST /api/v1/master-data/products/barcode-import/{preview,apply}` (multipart) and
  `GET .../barcode-import/template`; all gated by `master_data.products.edit`.
- FE: Products list > Actions > "Import barcodes" dialog: pick file, Test (preview table with
  counts and per-row status, columns used), Apply, result counts. Template download.

## Tests (red first)

Preview statuses, apply writes only new/change, permission 403 on both, audit rows written.
