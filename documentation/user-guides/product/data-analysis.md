# Product Management — Data analysis for the AI assistant

Reference for answering natural-language questions about the product catalogue (master data). It maps each entity to its fields, filters, status/active flags, and date columns, and gives example questions per entity.

> **Products ARE embedded for semantic search.** Active products are written to the vector store, so fuzzy text lookups ("the stainless 12L mixing bowl", "anything for outdoor LED lighting") resolve to product rows by name/description without an exact code. Categories, brands, UoM, and product-attachment links are **not** embedded — match those by code/name. **Numerics (prices, dimensions, reorder levels, counts) are answered via SQL / the list endpoints, never from semantic recall** — embeddings find the row, then quote exact figures from the table.

The five entities and their backing tables: **Product** (`products`), **Product Category** (`product_categories`), **Brand** (`brands`), **Unit of Measure** (`units_of_measure`), **Product Attachment** link (`product_attachments`).

---

## Product — `products`

The catalogue item. The hub everything else (stock, orders, promotions, suppliers, attachments) hangs off of.

**Identity / classification:** `id`, `product_code` (unique SKU — the lookup key, UI **Product Code**), `product_name` (UI **Product Name**), `description`, `category_id` (FK → `product_categories`, **required**), `brand_id` (FK → `brands`, optional), `base_uom_id` (FK → `units_of_measure`, **required**), `item_type` (`product` | `bundle` | `service` | `other`, nullable).

**Pricing:** `list_price` (required), `cost_price` (nullable, **hidden from non-privileged viewers**), `invoice_price` (nullable, **hidden from non-privileged viewers**), `currency` (defaults `MYR`).

**Specifications:** `weight`, `dimensions_length`, `dimensions_width`, `dimensions_height` (mm), `warranty_months`, `has_serial_tracking` (bool), `has_batch_tracking` (bool), `reorder_level`, `reorder_quantity`.

**Status / lifecycle flags:**
* `is_active` (bool) — the catalogue active/inactive toggle. Inactive products are hidden from pickers. UI **Status** = **Active** / **Inactive**.
* `is_discontinued` (bool) — set by the import / discontinued-batch process, **not** a manual form field. UI **Discontinued: Yes/No** on the detail page.
* `discontinued_notified_at` / `discontinued_notify_batch_id` — watermark + batch id used by the "products discontinued" notification deep link; not user-facing values.

**Audit:** `created_by`, `updated_by`, `created_at`, `updated_at`.

**Date columns:** `created_at`, `updated_at`.

**Filters (product list endpoint):**
* `query` — substring match over `product_code`, `product_name`, **and** `description`.
* `category_id` — accepts a category **id, code, or name** (resolved).
* `brand_id` — accepts a brand **id, code, or name** (resolved).
* `status` — `active` | `inactive` | `all` (maps to `is_active`).
* `item_type` — exact (`product` | `bundle` | `service` | `other`).
* `price_min` / `price_max` — on `list_price`.
* `length_min/max`, `width_min/max`, `height_min/max` — per-axis (mm).
* `any_dimension_min/max` — matches when **any** of L/W/H is in range (use for "dimension > 300mm" regardless of axis).
* `discontinued_batch_id` — restricts to products reported in one discontinued batch.
* `product_ids` — explicit id set.
* Advanced filter (list-query, resource key `products`): column-level conditions on **any** product field.

**Sortable:** `created_at` (default, **asc**), `updated_at`, `product_code`, `product_name`, `list_price` (alias `price`), `cost_price`, `invoice_price`, `is_active`, `dimensions_length` (alias `length`), `dimensions_width` (alias `width`), `dimensions_height` (alias `height`), `largest_dimension`, `smallest_dimension`.

**Example questions**
* "List products in category Beverages." (`category_id=Beverages`)
* "Show all products for brand Bosch with their list prices." (`brand_id=Bosch`)
* "Which products are discontinued?" (filter on `is_discontinued = true`)
* "How many active SKUs do we have?" (`status=active`, count)
* "Find the stainless 12-litre mixing bowl." (semantic match on name/description → exact row)
* "Products over RM 500, cheapest first." (`price_min=500`, sort `list_price` asc)
* "What's the biggest product by dimension?" (sort `largest_dimension` desc)
* "List service-type items." (`item_type=service`)
* "Which products use batch tracking?" (`has_batch_tracking = true`)
* "Show inactive products in category X created this year." (`status=inactive`, `category_id=X`, `created_at` this year)

> Do **not** quote `cost_price` / `invoice_price` to users without margin/cost visibility — they're hidden from ordinary viewers in the UI.

---

## Product Category — `product_categories`

How products are classified. Self-referential — categories can nest via `parent_category_id`.

**Fields:** `id`, `category_code` (unique, UI **Category Code**), `category_name` (UI **Category Name**), `description`, `parent_category_id` (FK → `product_categories`, nullable; null = top-level), `is_active` (bool, UI **Active**), `display_order` (ordering within a level), `created_by`, `created_at`, `updated_at`. Responses may include computed `product_count`.

**Date columns:** `created_at`, `updated_at`.

**Filters:** the UI presents categories as a searchable tree (search by code/name) and exposes them as a `category_id` picker on the product list. Resolve a category name/code to its id, then filter `products.category_id`.

**Example questions**
* "How many categories do we have?"
* "List top-level categories." (`parent_category_id IS NULL`)
* "What are the sub-categories of Power Tools?" (children of that `parent_category_id`)
* "Which category has the most products?" (sort by `product_count`)
* "Show inactive categories." (`is_active = false`)
* "How many products are in category CAT-001?" (resolve code → id → count `products`)

---

## Brand — `brands`

The manufacturer / brand a product belongs to. Optional on a product.

**Fields:** `id`, `brand_code` (unique, UI **Code**), `brand_name` (UI **Name**), `manufacturer`, `website`, `description` (UI **Description**), `logo_url`, `is_active` (bool, UI **Active**), `access_levels` (JSON array of visibility codes, e.g. `["dealer","end_user"]` — scopes portal/promotion product visibility), `created_by`, `created_at`, `updated_at`. Responses may include computed `product_count`.

**Date columns:** `created_at`, `updated_at`.

**Filters:** search by name/code; UI status filter **all** / **active** / **inactive**. Exposed as a `brand_id` picker on the product list (resolves id/code/name).

**Example questions**
* "List all brands and how many products each has." (sort by `product_count`)
* "Which brands have no products?" (`product_count = 0`)
* "Show active brands only." (`is_active = true`)
* "Who manufactures brand X?" (`manufacturer`)
* "Products by brand Y." (filter `products.brand_id = Y`)
* "Which brands are visible to dealers?" (`access_levels` contains `dealer`)

---

## Unit of Measure — `units_of_measure`

The units products are stocked/sold in. Self-referential — a derived unit points to its base via `base_uom_id` with a `conversion_factor`.

**Fields:** `id`, `uom_code` (unique, UI **UOM Code**), `uom_name` (UI **UOM Name**), `base_uom_id` (FK → `units_of_measure`, nullable; null = standalone base unit; UI **Base UOM**), `conversion_factor` (numeric, how many base units = 1 of this unit; UI **Conversion Factor**), `description`, `is_active` (bool, UI **Status**), `created_at`, `updated_at`. Responses may include computed `product_count`.

**Date columns:** `created_at`, `updated_at`.

**Filters:** search by code/name. Every product has a required `base_uom_id`; resolve a UoM code → id to find products using it.

**Example questions**
* "List all units of measure."
* "How many products use UOM 'Each'?" (resolve code → id → count `products.base_uom_id`)
* "Which units are derived from another unit?" (`base_uom_id IS NOT NULL`)
* "What's the conversion factor for Box?" (`conversion_factor`)
* "Show inactive units of measure." (`is_active = false`)
* "What is the base unit of CARTON?" (follow `base_uom_id`)

---

## Product Attachment link — `product_attachments`

Join rows linking a product to a file (datasheet / manual / photo). One product can have many; one file can be linked to many products. The pair `(product_id, attachment_id)` is unique.

**Fields:** `id`, `product_id` (FK → `products`), `attachment_id` (FK → `attachments`), `is_primary` (bool; UI **Primary** / **Secondary**), `sort_order` (ordering of secondary files), `access_levels` (JSON visibility codes), `created_at`, `created_by`. The joined attachment exposes `original_filename` (UI **Attachment Filename**) and `attachment_type.type_name` (UI **Attachment Type**).

**Date columns:** `created_at`.

**Filters:** the listing endpoint is searchable; resolve by product code/name to find a product's files. There is no separate status flag — presence/absence of a row is the signal.

**Example questions**
* "Which products have no attachments?" (products with zero `product_attachments` rows)
* "Products by brand Y that have no attachments." (filter `products.brand_id=Y`, anti-join `product_attachments`)
* "What's the primary image/datasheet for product SRT-100?" (`is_primary = true` for that `product_id`)
* "List all datasheets." (filter joined `attachment_type.type_name`)
* "How many products have at least one attachment?" (distinct `product_id` count)
* "Show the files linked to product X in display order." (sort by `sort_order`)

---

## Cross-entity notes

* **Joins:** `products.category_id` → `product_categories.id`; `products.brand_id` → `brands.id`; `products.base_uom_id` → `units_of_measure.id`; `product_attachments.product_id` → `products.id`. Resolve a name/code to its id first (exact code match preferred), then filter.
* **No UUIDs in answers.** Resolve ids to product codes / category codes / brand codes / UOM codes before replying.
* **`is_active` vs `is_discontinued`** are independent. "Active" is the catalogue toggle; "discontinued" is an import-driven lifecycle flag. Answer "active" questions from `is_active` and "discontinued" questions from `is_discontinued` — don't conflate them.
* **Cost/invoice price are restricted.** Don't surface them to viewers without cost visibility.
* **Dates are stored naive UTC; the UI renders Malaysia time.** Be explicit about the timezone when quoting timestamps.

## See also

* [Manage products](manage-products.md)
* [Product categories & brands](product-categories-and-brands.md)
* [Units of measure](units-of-measure.md)
* [Product attachments](product-attachments.md)
* [Upload the product master](../purchasing/upload-product-master.md)
