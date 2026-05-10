# Marketing — Upload a promotion

Use this flow to upload a promotion file (flyer, brochure, campaign artwork, promotion details). The system stores the file, fires the **Promotion** integration workflow, and creates the promotion record automatically.

## Steps


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar (e.g. *Marketing*) so the file is filed there.
3. Click [**Upload**](/resource-management/attachment-directories?guide_target=resource-management.files.upload-button) in the top toolbar.
4. In the **Create Attachment** dialog, set **Attachment Type** to **Promotion** (this is one of the two attachment types seeded by default — `code = 'promotion'`).
5. Drag the promotion file into the **Files** drop zone, or click **Select Files** to browse.
6. (Optional) Adjust **Access Levels** (*End User*, *Dealer*, *Manager*) — these decide who can see the promotion through the portal.
7. Click **Upload N Attachments**.

## What the system does (auto-link)

After upload, the backend fires a webhook to **n8n** with the file URL and the **Promotion** type. The promotion workflow:


1. Parses the file (extracts promotion title, validity dates, target audience, product list).
2. Creates a **Promotion** record (visible at **[Marketing Management → Promotions](/marketing-management/promotions)**).
3. Links it to **Promotion Products** as needed (visible at **[Marketing Management → Promotion Products](/marketing-management/promotion-products)**).
4. Calls back into the CRM to attach the original file to the Promotion record.

You don't need to create the promotion record by hand — the integration handles it. If anything is missing or wrong (e.g. a product code didn't match), open the promotion and edit it.

## How you'll be notified

* **Immediately:** in-app toast confirming the upload.
* **When the integration finishes:** in-app and/or email notification (depending on tenant configuration). The new Promotion appears on **[Marketing Management → Promotions](/marketing-management/promotions)**.
* **On parser failure:** an integration log is recorded under **[System Management → Integration Logs](/system-management/integration-logs)** — admins can review and re-run.

## Bulk import

For uploading multiple promotion files at once:


1. Zip the files together.
2. Click [**Bulk import (ZIP)**](/resource-management/attachment-directories?guide_target=resource-management.files.bulk-import-button) instead of [**Upload**](/resource-management/attachment-directories?guide_target=resource-management.files.upload-button).
3. Set the type to **Promotion** and upload the ZIP. Each file is processed individually.

## See also

* [Shared upload flow](../_shared/upload-flow.md)
* [Upload marketing form](upload-marketing-form.md)
