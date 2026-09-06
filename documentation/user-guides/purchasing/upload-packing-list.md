# 1.2-Purchasing - Upload a packing list

Use this flow when a supplier sends you a packing-list Excel. The primary path reads the file
directly on the Packing Lists page and files a copy in Drive for you; the Drive/n8n route
below is still there as an alternative.

## Steps (primary path)

1. Open **[Procurement → Packing Lists](/procurement-management/packing-lists)** (URL: `/procurement-management/packing-lists`).
2. Click **Upload packing list** - it is the primary button on the toolbar.
3. (Self-serve only) Pick the **Supplier** this packing list is from. If you opened this dialog with a supplier already in context, this step is skipped and the supplier is shown instead.
4. Drag in or browse to the packing-list Excel.
5. (Recommended) Click **Test** to validate the file before importing. Fix any reported errors first.
6. Click **Import packing list**. One shipment is created per container block in the file; re-uploading the same file updates those shipments in place rather than duplicating them.

The uploaded file is filed automatically as an attachment of type **Packing List**, in that
type's default folder (set once by an admin on the attachment type - see
[Manage folders and Quick Access](manage-resource-folders.md)), and linked to the shipment(s)
it created. You don't need a separate trip to Files for this file.

To create a packing list by hand (no file to read) instead, use **Create Packing List** in the
toolbar's **Actions** menu.

## Alternative: upload through Files (Drive/n8n)

Use this route if you'd rather file the document first and let the automated extraction create
the record, or the primary reader does not recognise the file's layout.

1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`).
2. (Optional) Click the folder you want the file filed under (e.g. a supplier-specific folder).
3. Click **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)** in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to your tenant's **Packing List** type.
5. Drag the packing-list Excel into the **Files** drop zone (or click **Select Files** to browse).
6. (Optional) Adjust **[Access Levels](/resource-management/attachment-directories#guide_target=resource-management.files.access-levels)**.
7. Click **[Upload 1 Attachment](/resource-management/attachment-directories#guide_target=resource-management.files.upload-confirm-button)**. A toast confirms the upload.

### What the system does (auto-link)

The packing-list workflow:

1. Parses the Excel (shipment date, ETA, BL number, container number, product lines, quantities).
2. Creates a **Packing List** record (visible at **[Procurement → Packing Lists](/procurement-management/packing-lists)**).

You don't need to do anything extra - the result appears on **[Procurement → Packing Lists](/procurement-management/packing-lists)** automatically once the workflow finishes.

### How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

### Bulk import

For multiple packing lists in one go:

1. Zip the Excel files together.
2. Click **[Bulk import (ZIP)](/resource-management/attachment-directories#guide_target=resource-management.files.bulk-import-button)** in the toolbar instead of **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)**.
3. Set the type to **Packing List** and upload the ZIP.

Every file in the archive is tagged with the type and processed individually.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload SPO](upload-spo.md) - the next step, once a packing list exists
* [Manage folders and Quick Access](manage-resource-folders.md)
