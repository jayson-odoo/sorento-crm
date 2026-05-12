# 2.3-Warehouse — Upload (bulk import) stock balances

Use this flow to bulk-create or update warehouse stock balances from an Excel file. One row per **(product, warehouse)** pair. Quantities are upserted: if a row exists for that pair it is updated, otherwise it is created. A ledger entry of type `BULK_IMPORT` is written for every change.

## Where to upload

Open [**Inventory Management → Stock**](/inventory-management/stock). The page is titled **Stock**.

Toolbar (top right):

* **[Export](/inventory-management/stock#guide_target=inventory-management.stock.export-button)** — download the current stock balances as `stock_balance_export.xlsx`. Use this as your starting template.
* **[Import](/inventory-management/stock#guide_target=inventory-management.stock.import-button)** — opens the upload dialog.
* **Filters** / **Columns** — DataGrid tools.

## Step 1 — Export current balances as your template

1. Click **[Export](/inventory-management/stock#guide_target=inventory-management.stock.export-button)** to download `stock_balance_export.xlsx`.
2. Open the file in Excel. The export contains every product × warehouse pair currently on the page, with the columns described below.

## Step 2 — Edit the Excel

### Columns

| Column (any of these is accepted) | Required | Notes |
|----|----|----|
| **Product Code** / **Item Code** | Yes | Looked up case-insensitively against the product master. Rows with an unknown code are flagged as errors. |
| **Warehouse Code** / **Location** | Yes (or pass **Warehouse** / **Warehouse Name** as a fallback) | Looked up against the warehouse master. **Warehouse Code** wins if both are present. |
| **Total Quantity** / **Quantity** / **On Hand** / **On hand qty** | Yes | Integer. Commas, currency, and dashes are tolerated; empty cell or `-` is treated as `0`. |
| **Reserved Quantity** / **Reserved** | Optional | Integer. Defaults to `0` on creates. |
| **Quantity Damaged** | Optional | Integer. Defaults to `0`. |
| **Reorder Point** | Optional | Integer, used by the low-stock alert. |
| **Zone ID** | Optional | Storage zone UUID (only set this when you know the zone). |
| **ID** | Optional | The stock record UUID. Set this only when you are updating a known row. New rows leave it blank. |
| **Available** | Read-only | Derived (`Total - Reserved`). The system ignores any value you put here on import. |

Rules of thumb:

* Don't duplicate `(Product Code, Warehouse Code)` — the last duplicate wins on create.
* You don't need to include every row from the export; rows you remove from the file are left untouched, not deleted.
* Use **Reserved Quantity** explicitly. If only **Available** is given, the importer assumes `Reserved = 0`.

## Step 3 — Import

1. Click **[Import](/inventory-management/stock#guide_target=inventory-management.stock.import-button)** in the toolbar.
2. Drag in or browse to your stock Excel file.

## Step 4 — Test before committing

Click **[Test](/inventory-management/stock#guide_target=template-upload.test-button)** in the upload dialog. The system runs server-side validation (`validate_only=true`) and shows you:

* A summary: total rows, rows that would create / update / skip, error count.
* Per-row errors (e.g. "Row 5: Product not found (code 'SRT-XYZ')").
* Per-row warnings (e.g. malformed numbers coerced to `0`).

Resolve every error before continuing. Warnings are advisory — they won't block the upload.

## Step 5 — Upload

Click **[Upload](/inventory-management/stock#guide_target=template-upload.confirm-button)**. The import is queued as an async job (`stock_import`). The dialog closes and the toolbar surfaces a status panel.

## How you'll see progress

* **Above the table:** the **Latest stock import** panel updates with `queued` → `running` → `finished` (or `failed`) and row counts.
* **Full history:** [**System Management → Import Jobs**](/system-management/import-jobs) lists every import job, including this one. Click a row to see error details.

## How you'll be notified

* **Immediately:** in-app toast confirming the job was queued.
* **On completion:** in-app notification (bell icon, top right) and email — both link back to the import-job detail.

## What changes in the database

For each successful row the importer either:

* Creates a new `stocks` row with the imported quantities, or
* Updates the existing row's quantities and writes a `StockLedger` entry of type `BULK_IMPORT` showing the before/after.

The **Available** column is recomputed automatically (`Total - Reserved`).

## Permissions

* `inventory.stock.export` — needed to run **Export**.
* `inventory.stock.import` — needed to run **Import** and reach the upload dialog.

## See also

* [Warehouse — Upload GRN](upload-grn.md) — receive incoming stock against a supplier packing list (different flow; updates `incoming_stock`, not balances).
* [Warehouse — Upload Delivery Orders](upload-delivery-orders.md)
