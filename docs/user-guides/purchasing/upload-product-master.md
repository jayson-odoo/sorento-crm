# 1.1-Purchasing — Upload the product master

Use this flow to bulk-create or update products from an Excel file. This is **Pattern B** — a module-specific structured import — distinct from the generic file upload on **Files**.

## Steps


1. Open **[Master Data Management → Products](/master-data-management/products)** (URL: `/master-data-management/products`). The page is titled **Products**.
2. Click **[Upload](/master-data-management/products#guide_target=master-data.products.upload-button)** in the toolbar (the **Import** dropdown contains the upload action).
3. The **Template Upload** dialog opens. Download the template if you don't already have it.
4. Fill the template with your products. The expected columns are:

| Column | Required | Notes |
|----|----|----|
| **Item Code** | Yes | Unique identifier — used as the lookup key for create vs update. |
| **Description** | Optional | Primary product description. |
| **Desc 2** | Optional | Secondary description / sub-name. |
| **Item Group** | Optional | Product group / category. |
| **Item Brand** | Optional | Brand name. |
| **Price** | Optional | Decimal. Currency / commas / `RM` are stripped automatically. |
| **Is Active** | Optional | Boolean (`yes`/`no`, `true`/`false`, `1`/`0`). |


5. Drag the filled file in or click to browse, then click **[Upload](/master-data-management/products#guide_target=template-upload.confirm-button)**.
6. The system will process the import in the background and notify you via email once the process is finished.

## How you'll see progress

The **Products** page shows a **Latest products import** panel above the table while a job is running. It displays the current status (queued, running, completed, failed) and row counts. Refresh the page if you don't see it.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## What you cannot do here

* This page does **not** upload product *attachments* (datasheets, manuals, photos). For those, see [Upload product attachments](upload-product-attachments.md).
* Errors on individual rows do not abort the whole import — failed rows are reported in the import-job result.

## See also

* [Upload product attachments](upload-product-attachments.md)
* [Upload SPO](upload-spo.md)
