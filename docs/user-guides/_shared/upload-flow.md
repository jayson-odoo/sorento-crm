# Shared upload flow — Resource Management → Files

This page describes the generic file-upload flow that several departments use (purchasing, warehouse, marketing, project sales). Department guides link here instead of repeating the same steps.

There are **two distinct upload patterns** in the CRM. Use the right one for the task:

| Pattern | When to use | Where |
|----|----|----|
| **A. File upload tagged by Attachment Type** (this page) | Uploading a file that needs to be tagged with an attachment type — packing list, product attachments, promotion, marketing form, etc. The system links it to the right business record automatically. | **[Resource Management → Files](/resource-management/attachment-directories)** |
| **B. Module-specific Excel import** | Bulk-loading structured data into a specific module (products, SPO, GRN, order tracking, stock). | The **Import** / **Upload** button on each module's list page |

If you are uploading **a single file or a folder of files** that the system should link to a product / promotion / packing list / etc., use **Pattern A** (this page). If you are uploading **an Excel spreadsheet of records** to create or update many rows in one shot, use the relevant Pattern B guide instead.


---

## Pattern A — Single-file upload


1. Open **[Resource Management → Files](/resource-management/attachment-directories)** in the left menu (URL: `/resource-management/attachment-directories`). The page is titled **Files**.
2. (Optional) Click a folder in the **Folders** sidebar on the left so the new file is filed under that folder. Otherwise the file lives at the root.
3. Click **Upload** in the top toolbar of the attachments table.
4. The **Create Attachment** dialog opens.
5. Pick the **Attachment Type** from the dropdown (required) — for example *Packing List*, *Product Attachments*, *Promotion*, *Marketing Form*. The list comes from your tenant's configured types. If the type you need is missing, ask an admin to add it under **[Resource Management → Attachment Types](/resource-management/attachment-types)** (the only types seeded by default are *Promotion* and *Complaint Document*).
6. Drag your file(s) into the **Files** drop zone, or click **Select Files** to browse.
7. (Optional) Tick / untick **Access Levels** — these control which contact-access groups (e.g. *End User*, *Dealer*, *Manager*) can see this file from the portal. All three are ticked by default.
8. Click **Upload N Attachments**. A toast confirms the upload, and the file appears in the table.

## Pattern A — Bulk ZIP import


1. Open **[Resource Management → Files](/resource-management/attachment-directories)**.
2. Click **Bulk import (ZIP)** (top toolbar, archive icon).
3. Pick the attachment type — every file inside the ZIP will be tagged with this type.
4. Upload your `.zip`. The system extracts files in the background.
5. The dialog closes when the import job is queued. Progress shows on the same page.

## How files are linked to business records (auto-link)

When you upload an attachment, the backend stores the file and **fires a webhook to the integration layer (n8n)** with the file URL and the attachment-type name. The n8n workflow attached to that type does the work — it parses the file (if it's a packing list, a marketing form, etc.), creates the business records, and **calls back into the CRM** to attach the file to the right product / packing list / promotion / complaint.

You do **not** need to link the file manually after upload. As soon as the integration finishes, the file shows up on the related record (e.g. Product → Attachments, Packing List → Files) automatically.

> **Important:** the columns the parser expects (e.g. ETA, product code, quantity for a packing list) are defined in the n8n workflow for that attachment type, **not** in this CRM codebase. If a parser fails, ask your integrations administrator for the current template.

## How you'll be notified

* **In-app toast** appears immediately when the upload completes (e.g. `Successfully uploaded 1 file(s)`).
* **Asynchronous processing** (parsing + linking) happens after the upload. When the integration workflow finishes, you receive a follow-up notification depending on how the workflow for that attachment type is configured (in-app and/or email).
* If parsing fails, an integration log is recorded — admins can review it under **[System Management → Integration Logs](/system-management/integration-logs)**.

## Folder management

Folder operations live on the same **Files** page, on the left sidebar.

* **Create a top-level folder:** click **Add** at the top of the **Folders** sidebar.
* **Add a subfolder, rename, delete, or adjust access levels:** click **Folder actions** (`⋯`) on the folder row → pick the action.
* **Pin a folder to Quick Access:** **Folder actions** (`⋯`) → **Pin to Quick Access**.
* **Search folders:** type into the **Search folders…** box at the top of the sidebar.

To **rename a single file**, click the pencil icon on the file row in the attachments table — the dialog is titled **Rename file**.

## Quick Access (menu pinning)

The left sidebar has a **Quick Access** section near the top. Click **Add shortcut** to pin a menu item, drag-and-drop to reorder, or click the unpin icon on a shortcut to remove it. Folders can be pinned the same way through their **Folder actions** menu.
