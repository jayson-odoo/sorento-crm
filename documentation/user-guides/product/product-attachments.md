# Product Management - Product attachments

The **Product Attachments** page is a read-only listing of every file linked to a product - datasheets, manuals, photos, spec sheets. It shows the link records, not an upload form.

Open **[Product Management → Products → Product Attachments](/master-data-management/product-attachments)** (URL: `/master-data-management/product-attachments`). The page is titled **Product Attachments**.

## The list

Columns: **Product Code**, **Product Name**, **Attachment Filename**, **Attachment Type**, **Is Primary** (**Primary** / **Secondary**), **Sort Order**.

* **Search product attachments...** - filters the list.
* **Refresh** and **Export** are available in the toolbar.
* Clicking a row opens that product's detail page (so you can manage the link from there).

This page has no create / edit / delete buttons - it reflects links created elsewhere.

## How attachments get linked to a product

There are two routes; both end up as a row on this page:

1. **From the product itself** - open a product, go to the **Attachments** tab (create or edit form, or the detail page's **Attachments** tab) and link a file. You set whether the link is **Primary** and its **Sort Order**.
2. **Via the generic file upload + auto-link** - upload through **Files** with the *Product Attachments* attachment type. The n8n workflow attached to that type parses the file and calls back into the CRM to attach it to the matching product(s). See [Upload product attachments](../purchasing/upload-product-attachments.md). Users do **not** link these files manually after upload.

> **`Attachment Filename` is the file's original upload name** (`original_filename`). Each link also carries `is_primary` and `sort_order` so a product can have one headline image/document and an ordered set of secondary files.

> **Field-level attachments are separate.** A file can also be linked to a *specific field* on a product (e.g. the weight or a dimension) to back **AI Extract** on the Specifications tab. Those are field-attachment links, surfaced on the product detail page, not on this listing.

## See also

* [Manage products](manage-products.md)
* [Upload product attachments](../purchasing/upload-product-attachments.md)
* [Product Management - Data analysis for the AI assistant](data-analysis.md)
