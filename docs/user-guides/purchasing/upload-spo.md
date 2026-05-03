# Purchasing — Upload SPO allocations (direct Excel)

Use this flow to bulk-import **SPO allocations** from an Excel file. SPO allocations link products and warehouse destinations to a supplier purchase order so that incoming stock can be matched against the right SPO.

> Most of the time you do **not** need this flow — uploading a [packing list](upload-packing-list.md) creates the SPO allocations automatically. Use this direct upload only when the packing-list flow does not apply (e.g. correcting historical data, loading SPO data without a packing list available).

## Steps


1. Open [**Procurement → SPO Allocations**](/procurement-management/spo-allocations) (URL: `/procurement-management/spo-allocations`). The page is titled **SPO Allocations**.
2. Click the **Import options** button in the toolbar (upload icon).
3. Pick **Import SPO** from the dropdown.
4. The **SPO Import** dialog opens. Drag in or browse to your SPO Excel file.
5. Confirm to queue the import job.

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

Once a job is queued, the **SPO Allocations** page shows a **Latest SPO import** panel above the table. It updates with the job status (queued, running, completed, failed) and row counts in real time. Refresh or check [**System Management → Import Jobs**](/system-management/import-jobs) for the full history.

## How you'll be notified

* **Immediately:** in-app toast confirming the job was queued.
* **On completion:** the panel updates with the result. Email notifications fire if your tenant has them configured.

## See also

* [Upload packing list](upload-packing-list.md) — the primary path; creates SPO allocations automatically
* [Upload product master](upload-product-master.md) — products must exist before SPO allocations can be created
