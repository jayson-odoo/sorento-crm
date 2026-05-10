# Marketing — Upload a marketing form

Use this flow to upload a marketing-form submission (e.g. event registration, product-feedback form, lead-capture form returned by a partner). The system stores the file, fires the **Marketing Form** integration workflow, and creates the related lead / submission records automatically.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar (e.g. *Marketing*) so the file is filed there.
3. Click [**Upload**](/resource-management/attachment-directories?guide_target=resource-management.files.upload-button) in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to **Marketing Form** (your tenant's configured marketing-form type — ask an admin to add it under **[Resource Management → Attachment Types](/resource-management/attachment-types)** if it's missing).
5. Drag the form file into the **Files** drop zone, or click **Select Files** to browse.
6. (Optional) Adjust **Access Levels**.
7. Click **Upload N Attachments**.

## What the system does (auto-link)

After upload, the backend fires a webhook to **n8n** with the file URL and the **Marketing Form** type. The marketing-form workflow:


1. Parses the file (extracts the submitted answers).
2. Creates the form-submission / lead records in the relevant module (typically **Forms Management** or **Workflow Forms**, depending on your tenant configuration).
3. Calls back into the CRM to attach the original file to the submission record.

You don't need to copy data out of the file by hand — the integration handles it.

## How you'll be notified

* **Immediately:** in-app toast confirming the upload.
* **When the integration finishes:** in-app and/or email notification (depending on tenant configuration). The new submission appears in the relevant Forms module.
* **On parser failure:** an integration log is recorded under **[System Management → Integration Logs](/system-management/integration-logs)**.

## Bulk import

For uploading multiple marketing-form files at once:


1. Zip the files together.
2. Click [**Bulk import (ZIP)**](/resource-management/attachment-directories?guide_target=resource-management.files.bulk-import-button) instead of [**Upload**](/resource-management/attachment-directories?guide_target=resource-management.files.upload-button).
3. Set the type to **Marketing Form** and upload the ZIP.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload promotion](upload-promotion.md)
