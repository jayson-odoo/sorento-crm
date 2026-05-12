# 1.2-Marketing — Upload a marketing form

Use this flow to upload a marketing-form (e.g. event registration, product-feedback form, dealer signage). The system stores the file, process it, and creates the related lead / submission records automatically.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar (e.g. *Marketing*) so the file is filed there.
3. Click **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)** in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to **Marketing Form**
5. Drag the form file into the **Files** drop zone, or click **Select Files** to browse.
6. (Optional) Adjust **[Access Levels](/resource-management/attachment-directories#guide_target=resource-management.files.access-levels)**.
7. Click **[Upload N Attachments](/resource-management/attachment-directories#guide_target=resource-management.files.upload-confirm-button)**.

## What the system does (auto-link)

The marketing-form workflow:


1. Parses the file.
2. Creates the form records in the relevant module (**Forms Management**).
3. Calls back into the CRM to attach the original file to the form record.

You don't need to create the marketing form out of the file by hand — the integration handles it.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## Bulk import

For uploading multiple marketing-form files at once:


1. Zip the files together.
2. Click **[Bulk import (ZIP)](/resource-management/attachment-directories#guide_target=resource-management.files.bulk-import-button)** instead of **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)**.
3. Set the type to **Marketing Form** and upload the ZIP.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload promotion](upload-promotion.md)
