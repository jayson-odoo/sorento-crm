# 1.1-Purchasing - Upload the product master

Use this flow to bulk-create or update products from an Excel file. This is **Pattern B** - a module-specific structured import - distinct from the generic file upload on **Files**.

## Steps


1. Open **[Master Data Management → Products](/master-data-management/products)** (URL: `/master-data-management/products`). The page is titled **Products**.
2. Click **[Upload](/master-data-management/products#guide_target=master-data.products.upload-button)** in the toolbar (the **Import** dropdown contains the upload action).
3. The **Template Upload** dialog opens. Download the template if you don't already have it.
4. Fill the template with your products. The expected columns are:

| Column | Required | Notes |
|----|----|----|
| **Item Code** | Yes | Unique identifier - used as the lookup key for create vs update. |
| **Description** | Optional | Primary product description. |
| **Desc 2** | Optional | Secondary description / sub-name. |
| **Item Group** | Yes | Product group / category. Created automatically if it does not exist yet. |
| **Item Brand** | Optional | Brand name. Created automatically if it does not exist yet. |
| **UOM** | Optional | Unit of measure (also accepted: `Unit`, `Unit of Measure`). Created automatically if it does not exist yet. Left out, products get the default unit (`EA`). |
| **Price** | Optional | Decimal. Currency / commas / `RM` are stripped automatically. |
| **Is Active** | Optional | Boolean (`yes`/`no`, `true`/`false`, `1`/`0`). |

You do **not** have to create categories, brands or units of measure before the
upload. An **Item Group** / **Item Brand** / **UOM** the system has never seen is
created for you, using the value in the file as both its code and its name, and
the row imports normally. The **Test** step lists exactly what will be created
("3 new categories will be created: ..."), and the finished import job reports
the counts. Rename them later in **[Product Categories](/master-data-management/product-categories)**
or **[Brands](/master-data-management/brands)** if you want tidier display names.


5. Drag the filled file in or click to browse.
6. (Recommended) Click **[Test](/master-data-management/products#guide_target=template-upload.test-button)** first to run server-side validation only. Fix any reported errors, then continue.
7. Click **[Upload](/master-data-management/products#guide_target=template-upload.confirm-button)**.
8. The system will process the import in the background and notify you via email once the process is finished.

## How you'll see progress

The **Products** page shows a **Latest products import** panel above the table while a job is running. It displays the current status (queued, running, completed, failed) and row counts. Refresh the page if you don't see it.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## What you cannot do here

* This page does **not** upload product *attachments* (datasheets, manuals, photos). For those, see [Upload product attachments](upload-product-attachments.md).
* Errors on individual rows do not abort the whole import - failed rows are reported in the import-job result.

## See also

* [Upload product attachments](upload-product-attachments.md)
* [Upload SPO](upload-spo.md)
