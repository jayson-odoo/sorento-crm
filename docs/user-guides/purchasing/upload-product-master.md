# Purchasing — Upload the product master

Use this flow to bulk-create or update products from an Excel/CSV file. This is **Pattern B** — a module-specific structured import — distinct from the generic attachment upload.

## Steps

1. Open **Master Data Management → Products** (URL: `/master-data-management/products`). The page is titled **Products**.
2. Click **Upload** in the toolbar.
3. The **Template Upload** dialog opens. Download the template if you don't already have it.
4. Fill the template with your products. The expected columns are:
   - **Item Code**
   - **Description**
   - **Desc 2**
   - **Item Group**
   - **Item Brand**
   - **Price**
   - **Is Active**
5. Drag the filled file in or click to browse, then confirm.
6. The system queues a background import job (`product_import`) and toasts a confirmation.

## How you'll see progress

The Products page shows a **Latest products import** panel above the table while a job is running. It displays the current status (queued, running, completed, failed) and the row counts. Refresh the page or check **System → Import Logs** for full history.

## How you'll be notified

- **Immediately:** in-app toast confirming the job was queued.
- **On completion:** the import job updates the panel with the result (rows created, rows updated, rows failed). Email notifications fire if your tenant has them configured for product imports.

## What you cannot do here

- This page does **not** upload product *attachments* (datasheets, manuals). For those, see [Upload product attachments](upload-product-attachments.md).
- Errors on individual rows do not abort the whole import — failed rows are reported in the import-job result.

## See also

- [Upload product attachments](upload-product-attachments.md)
- [Upload SPO](upload-spo.md)
