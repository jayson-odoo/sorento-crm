# Product Management — Manage products

Create, edit, view, and delete individual products from the product catalogue. For bulk create/update from Excel, use the [product master upload](../purchasing/upload-product-master.md) instead.

Open **[Product Management → Products → All Products](/master-data-management/products)** (URL: `/master-data-management/products`). The page is titled **Products**.

## The list

The list is a DataGrid with these columns: **Product Code**, **Product Name**, **Category**, **Brand**, **List Price**, **Status** (**Active** / **Inactive**), **Created**, **Updated**. List prices render in MYR.

* **Search products...** — matches product code, product name, and description.
* **Filters** (popover) — **Category** (default **All categories**), **Brand** (default **All brands**), **Status** (**All status** / **Active** / **Inactive**). **Clear Filters** resets them.
* **Advanced filters** (toolbar, **More** menu) — opens the list-query builder for column-level conditions on any product field.
* **Export** — downloads the current filtered/searched list to `products_export.xlsx`.
* Clicking a row opens that product's detail page. Per-row icons: **Edit**, **Duplicate**, **Delete**.

> A banner "Showing only the products from a recent "products discontinued" notification." appears when you arrive via a discontinued-products notification deep link. Click **Clear filter** to see all products again. If your discontinued subscription covers only some brands, the link opens on just those brands (`brand_id` alongside the batch): a link naming several brands leaves the **Brand** dropdown on **All brands** while its own filter narrows the grid, a link naming one selects that brand in the dropdown, and **Clear filter** drops the batch and the brand filter together.

## Create a product

1. Click **Create Product**. This opens the dedicated create page (`/master-data-management/products/new`) — products use a multi-tab form, not a modal.
2. Fill the tabs. Fields marked **\*** are required.

   **Basic Information**
   * **Product Code \*** — unique identifier (letters, numbers, spaces, and `- _ . / ( ) + #`). Cannot be changed after creation.
   * **Product Name \*** — 3–255 characters.
   * **Description** — optional, up to 2000 characters.
   * **Category \*** — searchable picker (see [Product categories & brands](product-categories-and-brands.md)).
   * **Brand** — optional, searchable picker.
   * **Item Type** — **None**, **Product**, **Bundle**, **Service**, or **Other**.
   * **Active Status** — switch; controls whether the product is active.

   **Pricing**
   * **List Price \*** — required, ≥ 0.
   * **Cost Price** — optional. *Internal cost price (hidden from viewers).*
   * **Invoice Price** — optional. *Invoice price (hidden from viewers).*

   **Specifications**
   * **Base Unit of Measure \*** — required (see [Units of measure](units-of-measure.md)).
   * **Weight**, **Length**, **Width**, **Height** — optional positive numbers.
   * **Warranty (Months)** — optional, ≥ 0.
   * **Serial Tracking** — switch; *Track individual serial numbers.*
   * **Batch Tracking** — switch; *Track batches with expiry dates.*
   * **Reorder Level** (default 10) and **Reorder Quantity** (default 50) — integers, ≥ 0.

   **Suppliers** — link suppliers to this product (lead time, minimum order quantity, primary supplier).

   **Attachments** — link datasheets / manuals / photos to this product. See [Product attachments](product-attachments.md).
3. Click **Create Product**. A draft of the form is auto-saved locally every 30 seconds while you edit.

## Edit a product

Open a product, then **Edit** (or the **Edit** icon on the list row). The same tabbed form opens with values loaded. **Product Code** is read-only in edit mode. Save with **Update Product**. Use the prev/next record pager to walk through the filtered list without returning to the table.

## View a product

The detail page (`/master-data-management/products/{id}`) shows the product name as the title, a **Quick Info** sidebar (including **List Price**), and these tabs:

* **Overview** - **Basic Information**, **Pricing Summary** (List / Cost / Invoice price), **Specifications**, and **Tracking Flags** (including **Discontinued: Yes/No**).
* **Stock** - on-hand / reserved / available by warehouse.
* **Purchase History** - past purchases of this product.
* **Attachments** - files linked to this product.
* **Suppliers** - linked suppliers.
* **Promotions** - promotions covering this product.
* **Variants** - linked product variants.
* **Audit Trail** - change history (the product model is audit-tracked).
* **Specifications** - the product's structured specification values: every value with where it came from, editable in place, **AI Extract** to propose values from an attached document, and the verification block. See [Verify product specifications](verify-product-specifications.md).

Every section renders even when empty.

## Delete a product

Use the **Delete** row icon (single) or select rows and use the **Delete** bulk action. Both open a confirmation dialog; the bulk dialog includes the count. **Delete is a hard delete and cannot be undone.**

## Active vs. discontinued

* **Active Status** (`is_active`) is the toggle you control on the form. Inactive products are hidden from pickers and most pages.
* **Discontinued** (`is_discontinued`) is a separate flag shown on the detail page's **Tracking Flags**. It is **not** editable on the product form — it is set by the product master import / discontinued-batch process, which can fire a "products discontinued" notification that deep-links back into this list. Treat discontinued as a data-driven state, not a manual switch.

## Bulk import

To create or update many products at once from Excel, see [Upload the product master](../purchasing/upload-product-master.md). That flow runs in the background and reports progress in a **Latest products import** panel on this page.

## See also

* [Product categories & brands](product-categories-and-brands.md)
* [Units of measure](units-of-measure.md)
* [Product attachments](product-attachments.md)
* [Verify product specifications](verify-product-specifications.md)
* [Upload the product master](../purchasing/upload-product-master.md)
* [Upload product attachments](../purchasing/upload-product-attachments.md)
* [Product Management — Data analysis for the AI assistant](data-analysis.md)
