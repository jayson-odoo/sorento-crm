# Product Management - Manage products

Create, edit, view, and delete individual products from the product catalogue. For bulk create/update from Excel, use the [product master upload](../purchasing/upload-product-master.md) instead.

Open **[Product Management → Products → All Products](/master-data-management/products)** (URL: `/master-data-management/products`). The page is titled **Products**.

## The list

The list is a DataGrid with these columns: **Product Code**, **Product Name**, **Category**, **Brand**, **List Price**, **Status** (**Active** / **Inactive**), **Created**, **Updated**. List prices render in MYR.

* **Search products...** - matches product code, product name, and description.
* **Filters** (popover) - **Category** (default **All categories**), **Brand** (default **All brands**), **Status** (**All status** / **Active** / **Inactive**). **Clear Filters** resets them.
* **Advanced filters** (toolbar, **More** menu) - opens the list-query builder for column-level conditions on any product field, including **Reorder Planning** (below).
* **Export** - downloads the current filtered/searched list to `products_export.xlsx`.
* Clicking a row opens that product's detail page. Per-row icons: **Edit**, **Duplicate**, **Delete**.

> A banner "Showing only the products from a recent "products discontinued" notification." appears when you arrive via a discontinued-products notification deep link. Click **Clear filter** to see all products again. If your discontinued subscription covers only some brands, the link opens on just those brands (`brand_id` alongside the batch): a link naming several brands leaves the **Brand** dropdown on **All brands** while its own filter narrows the grid, a link naming one selects that brand in the dropdown, and **Clear filter** drops the batch and the brand filter together.

## Create a product

1. Click **Create Product**. This opens the dedicated create page (`/master-data-management/products/new`) - products use a multi-tab form, not a modal.
2. Fill the tabs. Fields marked **\*** are required.

   **Basic Information**
   * **Product Code \*** - unique identifier (letters, numbers, spaces, and `- _ . / ( ) + #`). Cannot be changed after creation.
   * **Product Name \*** - 3 - 255 characters.
   * **Description** - optional, up to 2000 characters.
   * **Price tag description** - optional, multi-line. Prints verbatim on a price tag through the
     `{{product.price_tag_description}}` merge field; left empty, nothing prints for it. See
     [Work a price tag request - In the designer](../marketing/price-tag-requests.md#in-the-designer).
   * **Category \*** - searchable picker (see [Product categories & brands](product-categories-and-brands.md)).
   * **Brand** - optional, searchable picker.
   * **Item Type** - **None**, **Product**, **Bundle**, **Service**, or **Other**.
   * **Active Status** - switch; controls whether the product is active.
   * **Exclude from reorder planning** - switch; see [Exclude a product from reorder
     planning](#exclude-a-product-from-reorder-planning) below.

   **Pricing**
   * **List Price \*** - required, ≥ 0.
   * **Cost Price** - optional. *Internal cost price (hidden from viewers).*
   * **Invoice Price** - optional. *Invoice price (hidden from viewers).*

   **Specifications**
   * **Base Unit of Measure \*** - required (see [Units of measure](units-of-measure.md)).
   * **Weight**, **Length**, **Width**, **Height** - optional positive numbers.
   * **Warranty (Months)** - optional, ≥ 0.
   * **Serial Tracking** - switch; *Track individual serial numbers.*
   * **Batch Tracking** - switch; *Track batches with expiry dates.*
   * **Reorder Level** (default 10) and **Reorder Quantity** (default 50) - integers, ≥ 0.

   **Suppliers** - link suppliers to this product (lead time, minimum order quantity, primary supplier).

   **Attachments** - link datasheets / manuals / photos to this product. See [Product attachments](product-attachments.md).
3. Click **Create Product**. A draft of the form is auto-saved locally every 30 seconds while you edit.

## Edit a product

Open a product, then **Edit** (or the **Edit** icon on the list row). The same tabbed form opens with values loaded. **Product Code** is read-only in edit mode. Save with **Update Product**. Use the prev/next record pager to walk through the filtered list without returning to the table.

## View a product

The detail page (`/master-data-management/products/{id}`) shows the product name as the title, a **Quick Info** sidebar (including **List Price**), and these tabs:

* **Overview** - **Basic Information** (including **Price tag description**), **Pricing Summary** (List / Cost / Invoice price), **Specifications**, **Tracking Flags** (including **Discontinued: Yes/No**), then **Combos** (the catalogue packages this product is sold as, each with its own optional cover picture) and **Sold with** (the packages it is a part of, read-only). See [Catalogue packages on price tags](../marketing/price-tag-packages.md).
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
* **Discontinued** (`is_discontinued`) is a separate flag shown on the detail page's **Tracking Flags**. It is **not** editable on the product form - a description starting with `****` marks the product discontinued automatically, whether the product is created here, edited here, uploaded via the product master, or arrives through the AutoCount integration; a discontinued batch process can also fire a "products discontinued" notification that deep-links back into this list. Treat discontinued as a data-driven state, not a manual switch.
* **Length / Width / Height** left blank are filled in automatically from text like
  `880x450x220MM` in the description, on create and on any edit that changes the name or
  description - the same rule the [product master upload](../purchasing/upload-product-master.md)
  and the AutoCount integration follow. A value you type yourself is never overwritten.
* A brand-new product is linked to the tenant's default supplier (see **Default supplier (new
  products)** under **[User Management → Settings](/user-management/settings)**) - the same link
  the product master upload creates.

## Exclude a product from reorder planning

The **Exclude from reorder planning** switch (create/edit form and the product detail page)
keeps a product out of every reorder plan, even when it is named directly at Start Plan.
Nothing is excluded by default - every product plans until you switch it on by hand.

On the products list, an optional **Reorder Planning** column (hidden by default, reachable
from **Columns**) shows **Included** or **Excluded** for each product, and the same field is
available as a condition under **Advanced filters** so you can find every excluded product at
once. See [Run a reorder plan](../supply-chain/run-a-reorder-plan.md).

## Bulk import

To create or update many products at once from Excel, see [Upload the product master](../purchasing/upload-product-master.md). That flow runs in the background and reports progress in a **Latest products import** panel on this page. Manual Import stays available as the fallback even when Pull from AutoCount is turned on for your company.

## Pull from AutoCount

If your company is connected to AutoCount, you can pull the current items book straight from AutoCount instead of exporting a macro workbook and uploading it by hand. You review what would change before anything is applied.

**Who can do this:** anyone holding the **Pull from AutoCount** permission (`master_data.products.autocount_pull`) - granted automatically to every role that already holds product **Import**, plus admin. You need exactly one company selected; with more than one company in scope Sorento refuses with "Select a single company before pulling from AutoCount." and starts nothing.

### Start a pull

1. With one company selected, open **Products**.
2. In the **Actions** menu, the same menu that holds **Import**, click **Pull from AutoCount**.
3. Sorento asks AutoCount for a fresh snapshot of the items book and takes you to the pull's page, showing **Building**. A snapshot for a large company (Mocha) can take up to about half an hour to prepare. You can leave and come back later - the same menu item then reads **Review pull** and takes you straight back to this pull.
4. Once AutoCount finishes, Sorento reads the snapshot and works out what Confirm would do. Nothing in Sorento has changed yet. Status moves to **Preparing**, then **Awaiting confirm**.

### Review before confirming

The pull's page shows a status pill (**Building**, **Preparing**, **Awaiting confirm**, **Confirmed**, **Failed**, **Expired**), the snapshot time and how long it stays valid, a row of counters, and three tabs:

* **Changes** - what Confirm will do: which items are **new**, which are **changed** (field by field, the current value next to the incoming one), which **failed**, and which AutoCount left out of the snapshot.
* **Excel view** - the whole pull laid out with the same columns, in the same order, as the manual product-master template (**Item Code**, **Description**, **Desc 2**, **Item Group**, **Item Brand**, **Price**, **Is Active**), so you can read it side by side with the AutoCount workbook. **Download xlsx** saves it.
* **Compare with my Excel** - drop the very file you would have uploaded by hand. Sorento lines it up against the pull and tells you either "100% match" or lists every difference (which field, your Excel's value, the pull's value). This is advisory only - it never blocks Confirm and nothing from your file is applied to any product. A duplicated Item Code in your file keeps the last row with that code. The result stays on the page after a reload, and the difference list can be downloaded as xlsx.

**What the counters mean:**

* **Received** - rows AutoCount sent for this pull.
* **New** - would create a new product.
* **Changed** - would update an existing product; see Changes for which fields.
* **Unchanged** - already matches Sorento; not shown as a row.
* **Failed** - could not be applied; see Changes for the reason.
* **Price to 0** - the price would move from a non-zero value to zero.
* **Left out by AutoCount** - AutoCount's own snapshot excluded this item; see Changes for why.

### Confirm

Click **Confirm**. Only the person who started the pull can confirm it. Sorento re-reads the same snapshot and applies it through the same rules as the product-master upload and the AutoCount integration itself: a description starting with `****` marks a product **Discontinued**, blank length/width/height are read from the description, and a brand-new product is linked to the tenant's default supplier. Products created or updated by a pull's Confirm record you as the creator or the last person who updated them.

The pull's page then links to the **apply job** (**View apply job**), which shows the real per-item outcome. You get the same in-app notification and email you already get when any import finishes.

**If a pull sits in Building for about an hour without finishing**, it becomes **Expired**. The page stops checking on it - start a fresh pull from the same **Pull from AutoCount** action.

**If "Snapshot checksum did not match" appears** on the pull's page, Confirm still worked as reviewed - this is advisory only. If you see it often, tell your integrations admin.

## See also

* [Product categories & brands](product-categories-and-brands.md)
* [Units of measure](units-of-measure.md)
* [Product attachments](product-attachments.md)
* [Verify product specifications](verify-product-specifications.md)
* [Run a reorder plan](../supply-chain/run-a-reorder-plan.md)
* [Upload the product master](../purchasing/upload-product-master.md)
* [Upload product attachments](../purchasing/upload-product-attachments.md)
* [Pull stock from AutoCount](../warehouse/upload-stock.md#pull-from-autocount)
* [Product Management - Data analysis for the AI assistant](data-analysis.md)
