# Shared upload flow — Resource Management → Attachments

This page describes the generic file-upload flow that several departments use (purchasing, marketing, project sales). Department guides link here instead of repeating the same steps.

There are **two distinct upload patterns** in the CRM. Use the right one for the task:

| Pattern | When to use | Where |
|---|---|---|
| **A. Generic attachment upload** (this page) | Uploading a file that needs to be tagged with an attachment type — packing list, product attachment, promotion, product photo, marketing form, etc. | Resource Management → Attachments |
| **B. Module-specific Excel import** | Bulk-loading structured data into a specific module (products, SPO, GRN, order tracking, stock). | The upload button on each module's list page |

If you are uploading **a single file or a folder of files** that the system links to a product/promotion/packing list/etc., use **Pattern A** (this page). If you are uploading **an Excel spreadsheet of records** to create or update many rows in one shot, see the module-specific guide instead.

---

## Pattern A — Single-file upload

1. Open **Resource Management → Attachments** in the left menu (URL: `/resource-management/attachments`).
2. Click **Create Attachment** (top toolbar, plus icon).
3. In the dialog, select the **Attachment Type** from the dropdown (required). The list comes from your tenant's configured types — for example *Promotion*, *Complaint Document*, etc. If the type you need is missing, ask an admin to add it under **Resource Management → Attachment Types**.
4. (Optional) Pick a **folder** if you want the file filed under a specific directory.
5. (Optional) Set **access levels** — controls which contact-access groups can see this file.
6. Drag your file(s) into the drop zone, or click to browse. You will see a per-file progress bar while uploading.
7. Click **Upload**. A toast confirms `Successfully uploaded N file(s)`.

## Pattern A — Bulk ZIP import

1. Open **Resource Management → Attachments**.
2. Click **Bulk import (ZIP)** (top toolbar, archive icon).
3. Choose the attachment type — every file inside the ZIP will be tagged with this type.
4. Upload your `.zip`. The system extracts files in the background.
5. The dialog closes when the import job is queued. Progress is visible from the same page.

## How files are processed and what's "captured"

When you upload an attachment with a given **Attachment Type**, the backend stores the file and fires an outbound webhook to the integration layer (n8n) with the attachment metadata, signed file URL, and the type name. The integration workflow attached to that type is what reads the file and creates the corresponding business records (e.g. parses a packing-list Excel into shipment lines).

> **Important:** the columns the parser expects (e.g. ETA, product code, quantity for a packing list) are defined in the n8n workflow for that attachment type, not in this CRM codebase. Ask your integrations administrator for the current template if you are unsure of the expected columns.

## How you'll be notified

- **In-app toast** appears immediately when the upload completes (`Successfully uploaded N file(s)`).
- **Asynchronous processing** (parsing, linking) happens after the upload. When the integration workflow finishes, you receive a follow-up notification depending on how the workflow for that attachment type is configured (in-app and/or email).

## Folder management

Folder operations live on **Resource Management → Attachment Directories** (URL: `/resource-management/attachment-directories`).

- **Add subfolder** — click the row's `⋯` menu → **Add subfolder**.
- **Rename folder** — `⋯` menu → **Rename**.
- **Delete folder** — `⋯` menu → **Delete**.
- **Pin folder to Quick Access** — `⋯` menu → **Pin to Quick Access** (handy for folders you visit often).
- **Adjust access levels** — `⋯` menu → **Adjust access levels**.

To **rename a file**, open the attachment row in **Resource Management → Attachments** and click the pencil icon in the actions column. The dialog is titled **Rename file**.

## Quick Access (menu pinning)

The left sidebar has a **Quick Access** section. Click **+ Add shortcut** to pin any menu item; reorder by drag-and-drop; click the unpin icon to remove. Pinning a folder is done from the folder's `⋯` menu (above).
