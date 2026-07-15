# 1.3-Purchasing — Upload SPO allocations (direct Excel)

Use this flow to bulk-import **SPO allocations** from an Excel file. SPO allocations link products and warehouse destinations to a supplier packing list so that incoming stock can be matched against the right SPO.

## Steps


1. Open **[Procurement → SPO Allocations](/procurement-management/spo-allocations)** (URL: `/procurement-management/spo-allocations`). The page is titled **SPO Allocations**.
2. Click the **[Import options](/procurement-management/spo-allocations#guide_target=procurement.spo-allocations.import-options-button)** button in the toolbar (upload icon).
3. Pick **Import SPO** from the dropdown.
4. The **SPO Import** dialog opens. Drag in or browse to your SPO Excel file.
5. (Recommended) Click **[Test](/procurement-management/spo-allocations#guide_target=template-upload.test-button)** to validate the file before importing. Fix any reported errors first.
6. Click **[Import](/procurement-management/spo-allocations#guide_target=procurement.spo-allocations.import-confirm-button)** to queue the import job.

## What the system captures (column reference)

The filename (without extension) is used as the **SPO number**. Each row in the Excel becomes one SPO allocation:

| Column (any of these header names is accepted) | Required | Notes |
|----|----|----|
| **Item Code** / **Product Code** | Yes | Looked up case-insensitively against the product master. |
| **Location** / **Warehouse** / **Warehouse Code** | Yes | Looked up against the warehouse master. |
| **Qty** / **Quantity** / **Allocated** / **Allocated Quantity** | Yes | Integer. |
| **Loading Date** | Yes | Date of loading. Text after the first space in this cell is interpreted as the **shipping container number**. |
| **Transfer From** / **SPO Number** / **From Doc No.** / **From Document No.** | Optional | Used to override the SPO number per row, or to link a row to a specific source document. |

Rows are grouped by `(SPO number, product, warehouse)` — duplicate rows for the same combination are summed into a single allocation.

## How you'll see progress

Once a job is queued, the **SPO Allocations** page shows a **Latest SPO import** panel above the table. It updates with the job status (queued, running, completed, failed) and row counts in real time. Refresh the page if you don't see it.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## See also

* [Upload packing list](upload-packing-list.md) — the first step is to upload packing list first
* [Upload product master](upload-product-master.md) — products must exist before SPO allocations can be created
