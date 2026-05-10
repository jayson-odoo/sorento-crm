# Purchasing — Upload a packing list

Use this flow when a supplier sends you a packing-list Excel. The CRM stores the file and the integration workflow reads it to create the **Packing List** record (with shipment lines) and link the SPO allocations automatically.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`).
2. (Optional) Click the folder you want the file filed under (e.g. a supplier-specific folder).
3. Click **Upload** in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to your tenant's **Packing List** type. (If it's missing, ask an admin to add it under **[Resource Management → Attachment Types](/resource-management/attachment-types)** — only *Promotion* and *Complaint Document* are seeded by default.)
5. Drag the packing-list Excel into the **Files** drop zone (or click **Select Files** to browse).
6. (Optional) Adjust **Access Levels**.
7. Click **Upload 1 Attachment**. A toast confirms the upload.

## What the system does (auto-link)

After upload, the backend fires a webhook to **n8n** with the file URL and attachment type. The packing-list workflow:


1. Parses the Excel (shipment date, ETA, BL number, container number, product lines, quantities).
2. Creates a **Packing List** record (visible at **[Procurement → Packing Lists](/procurement-management/packing-lists)**).
3. Creates / matches **SPO allocations** for each line, linking the inbound shipment to the right SPO numbers.
4. Calls back into the CRM to attach the original file to the Packing List record.

You don't need to do anything extra — the result appears on **[Procurement → Packing Lists](/procurement-management/packing-lists)** automatically once the workflow finishes.

## How you'll be notified

* **Immediately:** in-app toast confirming the upload.
* **When parsing finishes:** in-app and/or email notification (depending on tenant configuration). The new Packing List shows up on the list page.
* **On parser failure:** an integration log is recorded — admins can review it under **[System Management → Integration Logs](/system-management/integration-logs)** and re-run if needed.

## Bulk import

For multiple packing lists in one go:


1. Zip the Excel files together.
2. Click **Bulk import (ZIP)** in the toolbar instead of **Upload**.
3. Set the type to **Packing List** and upload the ZIP.

Every file in the archive is tagged with the type and processed individually.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload SPO](upload-spo.md) — fallback for direct SPO Excel imports
* [Manage folders and Quick Access](manage-resource-folders.md)
