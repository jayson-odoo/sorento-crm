# Product Management - Product categories & brands

Manage the **categories** and **brands** that products are classified under. Every product must have a category; a brand is optional.

---

## Product categories

Open **[Product Management → Product Categories](/master-data-management/product-categories)** (URL: `/master-data-management/product-categories`). The page is titled **Product Categories**.

Categories are shown as a **tree** - parent categories can be expanded/collapsed to reveal nested children. Each row shows the category and its product count.

* **Search categories...** - filters the tree.
* **Create Category** - opens the **Create Category** modal.

### Create / edit a category

Click **Create Category**, or use the per-row **Edit** / **Duplicate** action. The modal (**Create Category** / **Edit Category**) has:

* **Category Code \*** - required, up to 50 characters, unique.
* **Category Name \*** - required, up to 150 characters.
* **Description** - optional, up to 500 characters.
* **Display Order** - integer ≥ 0; controls ordering within its level.
* **Active** - switch.

Save with **Create** / **Update**. **Duplicate** opens the create modal pre-filled from an existing category (code suffixed `-COPY`, name suffixed `(copy)`).

> **Setting a parent (nesting):** the category tree displays parent → child hierarchy, but the create/edit **modal does not expose a parent picker**. Nesting (`parent_category_id`) is assigned through the product master / category import or the API, not from this form. Flag this to your admin if you need to re-parent a category from the UI.

### Delete a category

Use the per-row **Delete** action. It opens a confirmation dialog; **delete is a hard delete and cannot be undone.** A category in use by products cannot be deleted while products still reference it.

---

## Brands

Open **[Product Management → Brands](/master-data-management/brands)** (URL: `/master-data-management/brands`). The page is titled **Brands**.

The list columns are **Name**, **Code**, **Description**, **Active**, **Products** (product count).

* **Search brands...** - matches name / code.
* **Status** filter - **All statuses** / **active** / **inactive**.
* **Create Brand** - opens the brand form.

### Create / edit a brand

The brand form fields:

* **Brand Code \*** - required, up to 50 characters; letters, numbers, dashes, underscores only; unique.
* **Brand Name \*** - required, up to 150 characters.
* **Manufacturer** - optional.
* **Website** - optional, must be a valid URL.
* **Logo URL** - optional, must be a valid URL.
* **Active Status** - switch.
* **Description** - optional, up to 2000 characters.
* **Access Levels** - visibility codes (e.g. **dealer**, **end_user**). These scope which contacts can see products of this brand in the portal / promotion product search. Leaving it empty applies no extra visibility restriction.

There is also a brand **detail** page (`/master-data-management/brands/{id}`). Edit and **Duplicate** actions are available on list rows.

### Delete a brand

Use the per-row **Delete** action → confirmation dialog. **Hard delete, cannot be undone.** A product's `brand_id` is cleared (set to null) if its brand is removed - products are not deleted with the brand.

---

## How products reference these

* A product's **Category** is required; its **Brand** is optional. Both are chosen from searchable pickers on the product form (see [Manage products](manage-products.md)).
* The product master import maps the spreadsheet's **Item Group** column to category and **Item Brand** to brand, creating/looking them up by name - see [Upload the product master](../purchasing/upload-product-master.md).

## See also

* [Manage products](manage-products.md)
* [Units of measure](units-of-measure.md)
* [Upload the product master](../purchasing/upload-product-master.md)
* [Product Management - Data analysis for the AI assistant](data-analysis.md)
