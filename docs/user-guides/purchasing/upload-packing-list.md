# Purchasing — Upload a packing list

Use this flow when a supplier sends you a packing-list Excel for an inbound shipment. The CRM stores the file and an integration workflow reads it to create the inbound shipment lines and SPO allocations automatically.

## Steps

1. Open **Resource Management → Attachments** (URL: `/resource-management/attachments`).
2. Click **Create Attachment**.
3. Set **Attachment Type** to your tenant's *Packing List* type. (If you don't see it in the dropdown, ask an admin to add it under **Resource Management → Attachment Types** — only *Promotion* and *Complaint Document* are seeded by default.)
4. Drag the packing-list Excel into the drop zone (or click to browse).
5. Click **Upload**. The dialog shows a progress bar per file and toasts `Successfully uploaded N file(s)` on completion.

## What the system captures

The uploaded file is parsed into an **inbound shipment** record with shipment lines. The destination model captures:

- Shipment-level: `shipment_date`, `estimated_arrival_date` (ETA), `bill_of_lading_number`, `shipping_container_number`.
- Per line: `product_id`, `quantity_shipped`, `batch_number`, `serial_number_range_from` / `serial_number_range_to`.

Each parsed packing list is also linked into **SPO allocations**, which link the inbound shipment to its purchase orders and warehouse destinations.

> **Column names in your Excel:** the exact column headers expected in the file are defined by the n8n workflow attached to the *Packing List* attachment type, not by the CRM codebase. Ask your integrations admin for the current template if the parser fails or skips lines.

## How you'll be notified

- **Immediately:** in-app toast on successful upload.
- **When parsing finishes:** the integration workflow sends a notification (in-app and/or email, depending on tenant configuration). If parsing fails, an integration log is recorded — admins can review it under **System → Integration Logs**.

## Bulk import

The system supports bulk ZIP import: zip multiple packing-list files together, click **Bulk import (ZIP)** instead of **Create Attachment** in step 2, set the type to *Packing List*, and upload the ZIP. Every file in the archive is tagged with the chosen type and processed individually.

## See also

- [Shared upload flow](../_shared/upload-flow.md)
- [Manage folders and quick access](manage-resource-folders.md)
