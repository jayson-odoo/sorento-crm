# Inventory - Data analysis for the AI assistant

Reference for answering natural-language questions about inventory. It maps each entity to its fields, filters, and date columns, and gives example questions per entity.

> **Numerics are answered via SQL, not embeddings.** Stock and order quantities are deliberately **not** written to the vector store - they change too often and must be exact. Answer "how much", "below X", "between dates", "expiring in N days" by querying the live tables / list endpoints, never from semantic recall. Use embeddings only for fuzzy text (product names, notes), then resolve to exact rows.

The five entities and their backing tables: **Warehouse** (`warehouses`), **Storage Zone** (`storage_zones`), **Stock** balance (`stock`), **Stock Batch** (`stock_batches`), **Stock Ledger** entry (`stock_ledger`).

---

## Warehouse - `warehouses`

A storage location. Everything else hangs off a warehouse.

**Fields:** `id`, `warehouse_code` (unique code; UI label **System Location**), `warehouse_name` (UI label **System Location Description**), `location` (physical address; UI label **Warehouse**), `manager_id`, `is_active` (only active ones appear in pickers), `created_at`, `updated_at`. Response also includes computed `zones_count` and `stock_count`.

**Date columns:** `created_at`, `updated_at`.

**Filters (list endpoint):** `query` (matches code/name), `is_active`, `warehouse_ids`.
**Sortable:** `warehouse_code`, `warehouse_name`, `location`, `is_active`, `created_at`, `updated_at`, `zones_count`, `stock_count`. Default sort `created_at` ascending.

**Example questions**

* "How many active warehouses do we have?"
* "List warehouses with no storage zones." (`zones_count = 0`)
* "Which warehouse holds the most distinct products?" (sort by `stock_count` desc)
* "Show inactive warehouses."
* "What's the code for the Selangor Main DC?"
* "Which warehouses were created this year?"

---

## Storage Zone - `storage_zones`

A named area inside a warehouse (shelf / rack / bin / pallet) with a capacity.

**Fields:** `id`, `warehouse_id` (FK → `warehouses`), `zone_code` (unique per warehouse), `zone_name`, `zone_type` (free text; UI form offers **Shelf**, **Rack**, **Bin**, **Pallet**), `capacity` (integer), `created_at`. Utilization shown in the UI is derived, not a stored column.

**Date columns:** `created_at`.

**Filters (list / tree endpoint):** `warehouse_id`. (No registered sort columns.)

**Example questions**

* "How many zones does the KL warehouse have?"
* "List all cold / pallet zones." (filter `zone_type`)
* "What's the total capacity of warehouse WH-001?"
* "Which warehouse has the highest zone utilization?"
* "Show zones with capacity over 1000."
* "Does warehouse X have a zone called ZONE-12?"

---

## Stock balance - `stock`

The live on-hand position. **One row per `(product, warehouse)`** (enforced unique). This is the table for "how much of product X do we have".

**Quantity fields:**

* `quantity_on_hand` - physical stock (UI **Total**).
* `quantity_reserved` - allocated to orders (UI **Reserved**).
* `quantity_available` - **generated column** = `quantity_on_hand − quantity_reserved` (UI **Available**). Filter/threshold on this for "available" questions.
* `quantity_damaged` - damaged units (UI **Damaged**; shown on the detail page only).
* `reorder_point` - threshold driving the status.

**Computed `status`** (not stored - derived from `quantity_available` vs. the product's reorder level):
`critical` (available ≤ 0) · `low` (0 < available < reorder level) · `normal` · `overstock` (available > reorder level × 2).

**Other fields:** `id`, `product_id` (FK → products), `warehouse_id` (FK → warehouses), `zone_id`, `last_count_date`, `created_at`, `updated_at`.

**Date columns:** `last_count_date`, `created_at`, `updated_at`.

**Filters (`/inventory/stock/balance`):** `query` (product code/name), `product_id` / `product_ids`, `warehouse_id` / `warehouse_ids`, `status` (`critical|low|normal|overstock`), and a numeric pair `quantity_operator` (`gt|gte|lt|lte|eq`) + `quantity_value` filtering **`quantity_available`**.
**Sortable:** `product_code`, `product_name`, `category_name`, `reorder_level`, `warehouse_name`, `available`, `reserved_quantity`, `quantity`, `status`.

**Example questions**

* "What's the on-hand quantity of product SRT-100 in warehouse WH-001?"
* "Show all stock below 10 available for warehouse Selangor Main DC." (`quantity_operator=lt`, `quantity_value=10`, `warehouse_id=…`)
* "List every product with status Critical." (`status=critical`)
* "Which items are low on stock right now?" (`status=low`)
* "Current on-hand by warehouse for product X." (filter `product_id`, group by warehouse)
* "How much is reserved vs available for product Y across all warehouses?"
* "What's overstocked?" (`status=overstock`)
* "Total available units of category Beverages." (filter via `category_name`, sum `available`)

> "Current on-hand by zone" is **not** directly answerable from the balance table - `stock.zone_id` is optional and rarely populated; zone-level quantity is not tracked on the balance. Answer at warehouse granularity and say so, or fall back to batches if the question is batch-specific.

---

## Stock Batch - `stock_batches`

A lot of one product in one warehouse, with dates and a lifecycle status. The table for expiry and lot questions.

**Fields:** `id`, `product_id` (FK → products), `warehouse_id` (FK → warehouses), `batch_code` (globally unique), `quantity`, `manufactured_date`, `expiry_date`, `received_date`, `status`, `created_at`.

**Status enum:** `AVAILABLE`, `RESERVED`, `DAMAGED`, `EXPIRED`, `RETURNED`.

**Date columns:** `manufactured_date`, `expiry_date`, `received_date`, `created_at`. **`expiry_date` is the one for expiry math** (the UI flags anything due within 30 days).

**Filters (list endpoint):** `product_id`, `warehouse_id`. (Status is filtered in the UI; no other registered sort columns.)

**Example questions**

* "Which batches expire in the next 30 days?" (`expiry_date BETWEEN today AND today+30d`)
* "List expired batches we still hold." (`status=EXPIRED` or `expiry_date < today`)
* "Batches of product X by expiry date, soonest first."
* "How many units are in available batches for warehouse WH-001?" (`status=AVAILABLE`, sum `quantity`)
* "What was received this month?" (filter `received_date`)
* "Show batch ABC-123 - its quantity, dates, and status."
* "Total quantity in reserved batches for product Y."
* "Any batches manufactured before 2024 still in stock?"

---

## Stock Ledger entry - `stock_ledger`

Append-only audit trail of quantity changes. The table for "what moved / history / who changed it".

**Fields:** `id`, `product_id` (FK → products), `warehouse_id` (FK → warehouses), `transaction_type`, `quantity_change` (signed: + inbound, − outbound), `previous_quantity`, `new_quantity`, `reference_type`, `reference_id`, `notes`, `created_by`, `created_at`.

**`transaction_type` values currently written:** `BULK_IMPORT` (balance created/updated by a stock import) and `SYSTEM_ADJUSTMENT` (balance zeroed because the product was missing from a full-snapshot import). `reference_type` seen: `bulk_import`, `stock_snapshot_import`.

**Date columns:** `created_at` (default sort, newest first).

**Filters (list endpoint):** `product_id`, `warehouse_id`, `transaction_type` (exact match).

**Example questions**

* "Show ledger movements for product Z in warehouse WH-001 between 1 Jan and 31 Mar." (filter `product_id` + `warehouse_id` + `created_at` range)
* "What was the last change to product X's balance and who made it?"
* "List all SYSTEM_ADJUSTMENT entries this week." (`transaction_type=SYSTEM_ADJUSTMENT`)
* "How many units came in via imports for product Y this month?" (sum positive `quantity_change` where `transaction_type=BULK_IMPORT`)
* "What was the on-hand of product X before and after its most recent movement?" (`previous_quantity` / `new_quantity`)
* "Show every movement against warehouse WH-002 today."
* "Which products had stock zeroed by a snapshot import?" (`reference_type=stock_snapshot_import`)

---

## Cross-entity notes

* **Joins:** `stock`, `stock_batches`, and `stock_ledger` all carry `product_id` + `warehouse_id`; `storage_zones` carries `warehouse_id`. Resolve a product/warehouse name to its ID first (exact code match preferred), then filter the numeric tables.
* **Available is derived** (`on_hand − reserved`); never sum reserved into available.
* **No UUIDs in answers.** Resolve IDs to product codes / warehouse codes / batch codes before replying.
* **Dates are stored naive UTC; the ledger UI renders Malaysia time.** Be explicit about the timezone when quoting timestamps.

## See also

* [Inventory - Understand stock levels](understand-stock-levels.md)
* [Inventory - Stock batches and expiry](stock-batches-and-expiry.md)
* [Inventory - Read the stock ledger](read-the-stock-ledger.md)
