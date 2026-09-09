# 1.2-Purchasing - Upload a packing list

Use this flow to file a packing-list Excel as an attachment (the automated extraction reads it and
creates the shipment record), or to create one by hand. A packing list that came from a supplier's
own workbook - one you want read line by line, matched to a proforma invoice - is uploaded on
**Proforma Invoices** instead; see
[Upload a proforma invoice (and its packing list)](upload-proforma-invoice.md). This page's own
**Upload** has no supplier-document reader of its own: a packing list here is born by converting
proforma invoices, or by the **Create Packing List** action below.

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

## Reading a supplier's own workbook instead

Want the file's lines read and matched to a proforma invoice, rather than filed as-is? Upload it on
**Proforma Invoices**, not here - see
[Upload a proforma invoice (and its packing list)](upload-proforma-invoice.md). Our own packing
list then comes from converting those invoices (**Convert to a packing list**, on Proforma
Invoices) rather than from an upload on this page.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload a proforma invoice (and its packing list)](upload-proforma-invoice.md) - a supplier's
  own workbook, read line by line and matched to an invoice
* [Upload SPO](upload-spo.md) - the next step, once a packing list exists
* [Manage folders and Quick Access](manage-resource-folders.md)
