# 1.4-Purchasing — Upload product attachments (certifications)

Use this flow to upload technical product documents (certifications) that should be linked to a product in the master data.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar (e.g. a brand-specific or product-specific subfolder) so the file is filed under it.
3. Click **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)** in the top toolbar of the attachments table.
4. In the **Create Attachment** dialog, set **Attachment Type** to your tenant's **Certification** type
5. Drag the file(s) into the **Files** drop zone, or click **Select Files** to browse. You can upload several at once.
6. (Optional) Adjust **[Access Levels](/resource-management/attachment-directories#guide_target=resource-management.files.access-levels)** — these control who can see the file from the portal.
7. Click **[Upload N Attachments](/resource-management/attachment-directories#guide_target=resource-management.files.upload-confirm-button)**.

## Linking is automatic

You do **not** need to link the file to its product manually. The system reads the filename / file content, finds the matching product, and calls back into the CRM to attach the file to the product record.

After the process finishes you'll see the file on **Master Data Management → Products → (the product) → Attachments** without any extra step. If a file does **not** auto-link (e.g. the filename does not match any item code), it stays visible on the **Files** page so you can link it manually as a fallback.

## Bulk import

For uploading many product attachments at once:


1. Zip the files together (e.g. one ZIP per brand or product family).
2. Click **[Bulk import (ZIP)](/resource-management/attachment-directories#guide_target=resource-management.files.bulk-import-button)** in the toolbar.
3. Set the attachment type (e.g. **Certificate**) and upload the ZIP.
4. Each file inside the archive is processed individually and auto-linked the same way as a single upload.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## Folder management

Attachments can be filed into folders for easier browsing. See the [folders guide](manage-resource-folders.md) for how to create, rename, and pin folders to Quick Access.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload product master](upload-product-master.md) — for adding new products in the first place
* [Upload packing list](upload-packing-list.md)
