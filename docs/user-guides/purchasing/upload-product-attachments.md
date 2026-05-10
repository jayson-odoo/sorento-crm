# Purchasing — Upload product attachments (datasheets, photos, drawings)

Use this flow to upload technical product documents (datasheets, manuals, spec sheets, drawings, product photos) that should be linked to a product in the master data.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar (e.g. a brand-specific or product-specific subfolder) so the file is filed under it.
3. Click **Upload** in the top toolbar of the attachments table.
4. In the **Create Attachment** dialog, set **Attachment Type** to your tenant's product-attachment type — usually **Product Attachments** (for datasheets, drawings, etc.) or *Product Photo* (for marketing-grade product images), depending on your tenant configuration.
5. Drag the file(s) into the **Files** drop zone, or click **Select Files** to browse. You can upload several at once.
6. (Optional) Adjust **Access Levels** (*End User*, *Dealer*, *Manager*) — these control who can see the file from the portal.
7. Click **Upload N Attachments**.

## Linking is automatic

You do **not** need to link the file to its product manually. The system fires a webhook to **n8n** with the file URL and the attachment-type name; n8n reads the filename / file metadata, finds the matching product, and calls back into the CRM to attach the file to the product record.

After the integration finishes you'll see the file on **Master Data Management → Products → (the product) → Attachments** without any extra step. If a file does **not** auto-link (e.g. the filename does not match any item code), it stays visible on the **Files** page so you can rename it and re-trigger, or link it manually as a fallback.

## Bulk import

For uploading many product attachments at once:


1. Zip the files together (e.g. one ZIP per brand or product family).
2. Click **Bulk import (ZIP)** in the toolbar.
3. Set the attachment type (e.g. **Product Attachments**) and upload the ZIP.
4. Each file inside the archive is processed individually and auto-linked the same way as a single upload.

## How you'll be notified

* **Immediately:** in-app toast on successful upload.
* **When the integration finishes:** in-app and/or email notification (depending on tenant configuration). Successful links appear on the product detail page.
* **On parser failure:** the integration log is recorded under **[System Management → Integration Logs](/system-management/integration-logs)**.

## Folder management

Attachments can be filed into folders for easier browsing. See the [folders guide](manage-resource-folders.md) for how to create, rename, and pin folders to Quick Access.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload product master](upload-product-master.md) — for adding new products in the first place
* [Upload packing list](upload-packing-list.md)
