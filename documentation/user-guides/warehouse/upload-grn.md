# 1.2-Warehouse — Upload GRN (Goods Received Note)

Use this flow to record the receiving of incoming stock against a supplier packing list. A GRN consists of a **header** (one document number + receiving date + optional SPO link) and a set of **lines** (product + warehouse + quantity received). Both are uploaded as separate Excel files.

## Where to upload

Open **[Procurement → GRN](/procurement-management/grn)** (URL: `/procurement-management/grn`). The page is titled **GRN**.

Toolbar:

* **[Import options](/procurement-management/grn#guide_target=procurement.grn.import-options-button)** (the upload-icon button on the toolbar) — opens a dropdown with **Upload GRN** (header) and **Upload GRN Lines** (lines).
* **Create GRN** — manual single-record creation.
* **Filters** / **Export** / **Columns** — DataGrid tools.

## Step 1 — Upload GRN header


1. Click **[Import options](/procurement-management/grn#guide_target=procurement.grn.import-options-button)** → **Upload GRN**.
2. Drag in or browse to your GRN-header Excel file.
3. (Recommended) Click **[Test](/procurement-management/grn#guide_target=template-upload.test-button)** to validate first; resolve errors before uploading.
4. Click **[Upload](/procurement-management/grn#guide_target=procurement.grn.import-confirm-button)**. The job is queued (`grn_listing_import`). Toast: confirmation that the job started.

### GRN header columns

| Column (any of these is accepted) | Required | Notes |
|----|----|----|
| **Doc Number** / **Doc No.** / **Doc. Number** / **GRN Number** | Yes | The GRN's picking number. Used as the unique key for upserts. |
| **Transfer From** / **SPO Number** / **From Doc No.** / **From Document No.** | Optional | Links the GRN to a source SPO. |
| **Date** / **Picking Date** | Optional | If missing, defaults to today. Accepted formats: ISO, `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`. |

## Step 2 — Upload GRN lines

After the header import finishes:


1. Click **[Import options](/procurement-management/grn#guide_target=procurement.grn.import-options-button)** → **Upload GRN Lines**.
2. Drag in or browse to your GRN-lines Excel.
3. (Recommended) Click **[Test](/procurement-management/grn#guide_target=template-upload.test-button)** to validate.
4. Click **[Upload](/procurement-management/grn#guide_target=procurement.grn.import-confirm-button)**. The job is queued (`grn_lines_import`).

### GRN line columns

| Column (any of these is accepted) | Required | Notes |
|----|----|----|
| **Doc No** / **Doc Number** / **GRN Number** | Yes | Must match an existing GRN header from step 1. |
| **Item Code** / **Product Code** | Yes | Looked up case-insensitively against the product master. |
| **Location** / **Warehouse** / **Warehouse Code** | Yes | Looked up against the warehouse master. |
| **Qty** / **Quantity** | Yes | Integer, must be greater than `0`. |
| **Transfer From** / **SPO Number** / **From Doc No.** | Optional | Line-level override of the header's SPO link. |

The SPO number a line states is kept on the line even when its SPO allocations have not been uploaded yet - the line shows the number with an **Unmatched** badge, and the link is made automatically when that SPO's allocations are imported later. Upload order between the GRN and SPO files does not matter.

## How you'll see progress

The **GRN** page shows two status panels above the table while jobs are running:

* **Latest GRN listing import** — for `grn_listing_import` (header).
* **Latest GRN lines import** — for `grn_lines_import` (lines).

Each panel updates with `queued` → `running` → `finished` (or `failed`) and row counts.

## Status flow

A GRN moves through: **Draft** → **Approved** (or **Rejected**). Newly imported GRNs land in **Approved** automatically

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## See also

* [Upload Delivery Orders (Order Tracking)](upload-delivery-orders.md)
* [Purchasing — Upload SPO](../purchasing/upload-spo.md)
* [Purchasing — Upload packing list](../purchasing/upload-packing-list.md)
