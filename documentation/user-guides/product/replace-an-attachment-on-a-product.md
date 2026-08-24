# Product Management - Replacing an attachment on a product

Use this flow when a file already linked to a product is out of date - a revised datasheet, a corrected certificate, a new product photo - and you want to swap in the new version **without breaking the existing link**. The replacement keeps the same attachment record, so the product's link (and its **Primary** flag, sort order, and any field links) stays valid, and the system re-runs the same downstream processing on the new file.

> **Replace, don't re-link.** If you upload the new file under a *different* name, the system treats it as a brand-new attachment - you'd end up with two files linked to the product and would have to delete the old one manually. To truly replace in place, keep the filename identical (see the steps below).

## Steps

1. Open **[Resource Management → Files](/resource-management/attachment-directories)** (URL: `/resource-management/attachment-directories`). The page is titled **Files**. This is where the actual file bytes live; the product's **Attachments** tab only shows the *links* to those files.
2. Find the file you want to replace. Click into the same folder in the **Folders** sidebar where the file was originally uploaded, or use **Search** in the attachments table. (Tip: the file's folder is shown on the product's detail page under the **Attachments** tab, grouped by folder path.)
3. Click **[Upload](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button)** in the top toolbar of the attachments table. The **Create Attachment** dialog opens.
4. Set **Attachment Type** to the **same type** the existing file uses (e.g. *Product Attachments*, *Certification*). Keeping the type consistent means the same downstream workflow re-processes the new file.
5. Drag your new file into the **Files** drop zone, or click **Select Files** to browse. **The new file must have the same filename as the file you're replacing** - that is how the system recognises it as the same file. Make sure you're in the **same folder** as the original, too.
6. Click **[Upload 1 Attachment](/resource-management/attachment-directories#guide_target=resource-management.files.upload-confirm-button)**.
7. Because a file with that name already exists in the folder, a **File already exists in this folder** dialog appears:
   > *An attachment named **&lt;filename&gt;** already exists. Replace the existing file (its links to packing lists, promotions, products and forms stay valid) or upload a renamed copy?*
8. Click **Replace existing** (the red button). The new file's bytes, size, and upload date overwrite the existing attachment record.
   * **Create copy** instead uploads the new file under an auto-renamed name and leaves the old file untouched - use this only if you actually want two files.
   * **Cancel** aborts without changing anything.

## What happens after you Replace

* **The link is stable.** The attachment keeps the same identity, so the product stays linked to it - no need to re-link on the product's **Attachments** tab. The **Primary** flag, sort order, access levels, and any field-level links (e.g. a file backing **AI Extract** on the Specifications tab) all carry over.
* **Downstream processing re-runs.** The system re-fires the same integration webhook (as a *replacement* event) so the n8n workflow for that attachment type re-parses the new file and updates the linked product record - you don't have to trigger anything manually.
* **Notification.** You get the usual in-app confirmation when the upload completes, and any follow-up notification the workflow is configured to send once re-processing finishes (bell icon, top right, and/or email).

## If you don't see the replace prompt

* **No dialog appeared and a new row was added instead** - the new file's name didn't match the existing file exactly, or you uploaded it into a different folder. Delete the accidental duplicate, then re-upload with the **identical filename** into the **same folder**.
* **You only want to change the file's display name, not its contents** - don't re-upload. Use the pencil (**Rename file**) icon on the file's row in the **Files** table instead.
* **The file isn't linked to the product yet** - replacing swaps bytes on an *existing* file. To add a brand-new attachment and let it auto-link to the product, follow [Upload product attachments](../purchasing/upload-product-attachments.md).

## See also

* [Product attachments](product-attachments.md) - how files get linked to a product
* [Upload product attachments](../purchasing/upload-product-attachments.md)
* [Shared upload flow](../_shared/upload-flow.md)
