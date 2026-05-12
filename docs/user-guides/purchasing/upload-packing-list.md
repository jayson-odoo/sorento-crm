# 1.2-Purchasing — Upload a packing list

Use this flow when a supplier sends you a packing-list Excel. The CRM stores the file and the reads it to create the **Packing List** record (with item lines).

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`).
2. (Optional) Click the folder you want the file filed under (e.g. a supplier-specific folder).
3. Click **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)** in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to your tenant's **Packing List** type.
5. Drag the packing-list Excel into the **Files** drop zone (or click **Select Files** to browse).
6. (Optional) Adjust **[Access Levels](/resource-management/attachment-directories#guide_target=resource-management.files.access-levels)**.
7. Click **[Upload 1 Attachment](/resource-management/attachment-directories#guide_target=resource-management.files.upload-confirm-button)**. A toast confirms the upload.

## What the system does (auto-link)

The packing-list workflow:


1. Parses the Excel (shipment date, ETA, BL number, container number, product lines, quantities).
2. Creates a **Packing List** record (visible at **[Procurement → Packing Lists](/procurement-management/packing-lists)**).

You don't need to do anything extra — the result appears on **[Procurement → Packing Lists](/procurement-management/packing-lists)** automatically once the workflow finishes.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## Bulk import

For multiple packing lists in one go:


1. Zip the Excel files together.
2. Click **[Bulk import (ZIP)](/resource-management/attachment-directories#guide_target=resource-management.files.bulk-import-button)** in the toolbar instead of **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)**.
3. Set the type to **Packing List** and upload the ZIP.

Every file in the archive is tagged with the type and processed individually.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload SPO](upload-spo.md) — fallback for direct SPO Excel imports
* [Manage folders and Quick Access](manage-resource-folders.md)
