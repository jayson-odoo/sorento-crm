# 1.2-Purchasing - Upload a packing list

Use this flow when a supplier sends you a packing-list Excel. The primary path files it
straight from the Packing Lists page, the same way you'd file it in Files, and the automated
extraction creates the shipment record; a manual reader is available as an alternative when you
want to read the file's lines yourself instead.

## Steps (primary path)

1. Open **[Procurement → Packing Lists](/procurement-management/packing-lists)** (URL: `/procurement-management/packing-lists`).
2. Click **Upload** - it is the primary button on the toolbar.
3. The **Create Attachment** dialog opens with **Attachment Type** already set to **Packing List** and locked, and the type's default folder preselected.
4. Drag the packing-list Excel into the **Files** drop zone (or click **Select Files** to browse).
5. (Optional) Adjust **Access Levels**.
6. Click **Upload 1 Attachment**. A toast confirms the upload.

The file is filed as an attachment of type **Packing List**, in that type's default folder (set
once by an admin on the attachment type - see [Manage folders and Quick Access](manage-resource-folders.md)).
The automated extraction reads it and creates the shipment record; you don't need a separate trip
to Files for this file, and this is the same upload you'd get from **Resource Management → Files**
with the type already chosen for you.

### What the system does (auto-link)

The packing-list workflow:

1. Parses the Excel (shipment date, ETA, BL number, container number, product lines, quantities).
2. Creates a **Packing List** record (visible at **[Procurement → Packing Lists](/procurement-management/packing-lists)**).

You don't need to do anything extra - the result appears on **[Procurement → Packing Lists](/procurement-management/packing-lists)** automatically once the workflow finishes.

### How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

### Bulk import

For multiple packing lists in one go, use **Resource Management → Files** instead of the
Packing Lists page - the Packing Lists Upload button covers one file at a time:

1. Zip the Excel files together.
2. Open **[Resource Management → Files](/resource-management/attachment-directories)** and click **[Bulk import (ZIP)](/resource-management/attachment-directories#guide_target=resource-management.files.bulk-import-button)** in the toolbar.
3. Set the type to **Packing List** and upload the ZIP.

Every file in the archive is tagged with the type and processed individually.

To create a packing list by hand (no file to read) instead, use **Create Packing List** in the
toolbar's **Actions** menu.

## Alternative: read the file yourself (Upload supplier documents)

Use this route when you'd rather read the file's lines yourself before a shipment is created -
for example to confirm which container each line belongs to, or the automated extraction does
not recognise the file's layout. This also covers a proforma invoice alongside the packing
list in the same pass.

1. Open **[Procurement → Packing Lists](/procurement-management/packing-lists)**.
2. Open the toolbar's **Actions** menu and click **Upload supplier documents**.
3. (Self-serve only) Pick the **Supplier** this packing list is from. If you opened this dialog with a supplier already in context, this step is skipped and the supplier is shown instead.
4. Drag in or browse to the packing-list Excel (and, optionally, its proforma invoice).
5. (Recommended) Click **Test** to validate the file before importing. Fix any reported errors first.
6. Click **Import packing list**. One shipment is created per container block in the file; re-uploading the same file updates those shipments in place rather than duplicating them.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload SPO](upload-spo.md) - the next step, once a packing list exists
* [Manage folders and Quick Access](manage-resource-folders.md)
