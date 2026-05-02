# Purchasing — Upload technical product attachments

Use this flow to upload technical documents (datasheets, manuals, spec sheets, drawings) that should be linked to a product in the master data.

## Steps

1. Open **Resource Management → Attachments** (URL: `/resource-management/attachments`).
2. Click **Create Attachment**.
3. Set **Attachment Type** to your tenant's *Product Attachment* (or equivalent technical-document) type.
4. (Optional) Pick the folder you want the file filed under, e.g. a brand- or product-specific subfolder.
5. (Optional) Set **access levels** — these control which contact-access groups (e.g. *Dealer*, *End user*) can view the file from the portal.
6. Drag the file into the drop zone and click **Upload**.

## Linking the attachment to a product

Linking is **manual**, not automatic. After upload:

1. Open **Master Data Management → Products** and click into the product.
2. On the product detail page, open the **Attachments** tab.
3. Click the link control to open the **Link attachment** browser, find the file you just uploaded, and confirm. The file is now associated with the product.

To **unlink**, use the unlink control on the same row in the product's Attachments tab.

> The system does **not** auto-match attachments to products by SKU or filename. You must select the file in the Link Attachment dialog.

## How you'll be notified

- **Immediately:** in-app toast on successful upload.
- **Linking** is instant once you confirm in the dialog — no background processing required.
- If the attachment type has an integration workflow attached (e.g. for OCR or auto-tagging), follow-up notifications arrive when that workflow finishes.

## Bulk import

For uploading many product attachments at once:

1. Zip the files together (e.g. one ZIP per brand or product family).
2. Click **Bulk import (ZIP)** in the Attachments toolbar.
3. Set the attachment type to *Product Attachment* and upload the ZIP.

After bulk import, each file still needs to be **linked** to its product via the product detail page (linking is not automatic).

## Folder management

Attachments can be organised into folders for easier browsing. See the [folders guide](manage-resource-folders.md) for how to create, rename, and pin folders to Quick Access.

## See also

- [Shared upload flow](../_shared/upload-flow.md)
- [Upload product master](upload-product-master.md) — for adding new products in the first place
