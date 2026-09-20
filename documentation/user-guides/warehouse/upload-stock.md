# 2.3-Warehouse - Upload (bulk import) stock balances

Use this flow to bulk-create or update warehouse stock balances from an Excel file. One row per **(product, warehouse)** pair. Quantities are upserted: if a row exists for that pair it is updated, otherwise it is created. A ledger entry of type `BULK_IMPORT` is written for every change.

## Where to upload

Open [**Inventory Management → Stock**](/inventory-management/stock). The page is titled **Stock**.

Toolbar (top right):

* **[Export](/inventory-management/stock#guide_target=inventory-management.stock.export-button)** - download the current stock balances as `stock_balance_export.xlsx`. Use this as your starting template.
* **[Import](/inventory-management/stock#guide_target=inventory-management.stock.import-button)** - opens the upload dialog.
* **Filters** / **Columns** - DataGrid tools.

## Step 1 - Export current balances as your template

1. Click **[Export](/inventory-management/stock#guide_target=inventory-management.stock.export-button)** to download `stock_balance_export.xlsx`.
2. Open the file in Excel. The export contains every product × warehouse pair currently on the page, with the columns described below.

## Step 2 - Edit the Excel

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

* Don't duplicate `(Product Code, Warehouse Code)` - the last duplicate wins on create.
* You don't need to include every row from the export; rows you remove from the file are left untouched, not deleted.
* Use **Reserved Quantity** explicitly. If only **Available** is given, the importer assumes `Reserved = 0`.

## Step 3 - Import

1. Click **[Import](/inventory-management/stock#guide_target=inventory-management.stock.import-button)** in the toolbar.
2. Drag in or browse to your stock Excel file.

## Step 4 - Test before committing

Click **[Test](/inventory-management/stock#guide_target=template-upload.test-button)** in the upload dialog. The system runs server-side validation (`validate_only=true`) and shows you:

* A summary: total rows, rows that would create / update / skip, error count.
* Per-row errors (e.g. "Row 5: Product not found (code 'SRT-XYZ')").
* Per-row warnings (e.g. malformed numbers coerced to `0`).

Resolve every error before continuing. Warnings are advisory - they won't block the upload.

## Step 5 - Upload

Click **[Upload](/inventory-management/stock#guide_target=template-upload.confirm-button)**. The import is queued as an async job (`stock_import`). The dialog closes and the toolbar surfaces a status panel.

## How you'll see progress

* **Above the table:** the **Latest stock import** panel updates with `queued` → `running` → `finished` (or `failed`) and row counts.
* **Full history:** [**System Management → Import Jobs**](/system-management/import-jobs) lists every import job, including this one. Click a row to see error details.

## How you'll be notified

* **Immediately:** in-app toast confirming the job was queued.
* **On completion:** in-app notification (bell icon, top right) and email - both link back to the import-job detail.

## What changes in the database

For each successful row the importer either:

* Creates a new `stocks` row with the imported quantities, or
* Updates the existing row's quantities and writes a `StockLedger` entry of type `BULK_IMPORT` showing the before/after.

The **Available** column is recomputed automatically (`Total - Reserved`).

## Permissions

* `inventory.stock.export` - needed to run **Export**.
* `inventory.stock.import` - needed to run **Import** and reach the upload dialog.
* `inventory.stock.autocount_pull` - needed to run **Pull from AutoCount** (below).

## Pull from AutoCount

If your company is connected to AutoCount, you can pull the current stock book straight from AutoCount instead of exporting the workbook and uploading it by hand. You review what would change before anything is applied. Manual Import stays available as the fallback even when this is turned on for your company.

**Who can do this:** anyone holding the **Pull from AutoCount** permission (`inventory.stock.autocount_pull`) - granted automatically to every role that already holds `inventory.stock.import`, plus admin. You need exactly one company selected; with more than one company in scope Sorento refuses with "Select a single company before pulling from AutoCount." and starts nothing.

**The AutoCount connection itself** is not configured here - an admin enters the gateway URL and
API key on the **FoundryX ESB** record under **Integration Management → Integrations** and clicks
**Test** to confirm it (**Connected**, or the reason it isn't). See [AutoCount integration
(ESB)](../system-management/data-analysis.md#autocount-integration-esb---contract-version-21) for
details, including why a wrong-company key can still show Connected there.

### Start a pull

1. With one company selected, open **Stock**.
2. In the **Actions** menu, the same menu that holds **Import**, click **Pull from AutoCount**.
3. Sorento asks AutoCount for a fresh snapshot of the stock book and takes you to the pull's page, showing **Building**. A snapshot for a large company (Mocha) can take up to about half an hour to prepare. You can leave and come back later - the same menu item then reads **Review pull** and takes you straight back to this pull.
4. Once AutoCount finishes, Sorento reads the snapshot and works out what Confirm would do. Nothing in Sorento has changed yet. Status moves to **Preparing**, then **Awaiting confirm**.

### Review before confirming

The pull's page shows a status pill (**Building**, **Preparing**, **Awaiting confirm**, **Confirmed**, **Failed**, **Expired**), the snapshot time and how long it stays valid, a row of counters, and three tabs:

* **Changes** - what Confirm will do: quantities that would move, pairs that would be set to 0, and rows that are not applied (with the reason).
* **Excel view** - the whole pull laid out with the same columns, in the same order, as the manual stock template (**Item Code**, **Item Description**, **Location**, **On Hand Qty**), so you can read it side by side with the AutoCount workbook. **Download Stock List** saves it.
* **Compare with my Excel** - drop the very file you would have uploaded by hand. Sorento lines it up against the pull, keyed by Item Code and Location, and tells you either "100% match" or lists every difference. This is advisory only - it never blocks Confirm and nothing from your file is applied to any stock balance. A duplicated Item Code in your file keeps the last row with that code. The result stays on the page after a reload, and the difference list can be downloaded as xlsx.

**What the counters mean:**

* **Received** - (product, location) pairs AutoCount sent for this pull.
* **Will apply** - pairs whose Location matches a warehouse that is ACTIVE in Sorento; these are what Confirm applies.
* **Not applied, inactive warehouse** - Location matches a warehouse that is inactive in Sorento; left untouched either way.
* **Not applied, unknown location** - Location doesn't match any warehouse Sorento knows; left untouched.
* **Quantity changes** - pairs among "Will apply" whose quantity would actually change.
* **Set to 0** - pairs Sorento currently holds stock for, in an active warehouse, that this pull does not mention; Confirm sets these to 0.
* **Skipped, product not found** - the Item Code doesn't match a product in Sorento.
* **Negative in AutoCount** - AutoCount sent a negative on-hand quantity for this pair.

### Confirm

Click **Confirm**. Only the person who started the pull can confirm it. Sorento applies the rows counted under "Will apply" through the same stock import the manual upload runs: every (product, warehouse) pair in an ACTIVE warehouse that this pull does not mention is set to 0, exactly like a manual stock upload; pairs in an INACTIVE warehouse are left untouched whether or not AutoCount sent them. The applied rows are also saved as the latest **Stock List** file, so the chatbot keeps answering from the current book.

**Confirm is disabled**, with the reason shown on the page, when:

* **No row matched an active warehouse** - "No row matched an active warehouse; nothing to apply." Nothing would be applied, so Confirm stays blocked until AutoCount sends a usable snapshot.
* **AutoCount left out rows that still hold stock** - "AutoCount reports N non-zero excluded pair(s); pull again." Start a fresh pull.

**If a pull sits in Building for about an hour without finishing**, it becomes **Expired**. The page stops checking on it - start a fresh pull from the same **Pull from AutoCount** action.

**Warnings you might see after Confirm:**

* **"Stock List file was not replaced"** - your stock quantities updated correctly, but saving the applied rows as the latest Stock List file did not succeed. Re-run **Export**, or pull again, if the chatbot needs the current file straight away.
* **"Snapshot checksum did not match"** - advisory only; Confirm still applied what you reviewed. If you see it often, tell your integrations admin.

## See also

* [Warehouse - Upload GRN](upload-grn.md) - receive incoming stock against a supplier packing list (different flow; updates `incoming_stock`, not balances).
* [Warehouse - Upload Delivery Orders](upload-delivery-orders.md)
* [Pull products from AutoCount](../product/manage-products.md#pull-from-autocount)
