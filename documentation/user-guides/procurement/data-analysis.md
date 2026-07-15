# Procurement — Data analysis for the AI assistant

Reference for answering natural-language questions about **procurement**: suppliers, the products they supply, inbound shipments (packing lists), SPO allocations, goods receipts (GRN), picking lines, and stock inquiries. It maps each entity to its backing table, fields, filters, and date columns, and gives example questions per entity.

The procurement chain runs:

```
Supplier → Product-Supplier link
Supplier → Packing List (inbound shipment) → SPO Allocation → GRN (goods receipt) → Picking Line
Stock Inquiry (a separate sales→purchasing question/answer record)
```

> **Reading notes for the assistant**
>
> * **Only the incoming-stock angle has dedicated AI tools.** The MCP read tools cover packing lists / inbound shipments / SPO arrivals **from a "what's incoming?" angle** (`crm_incoming_stock_by_product`, `crm_incoming_stock_shipments`, `crm_incoming_stock_list`). There is **no** MCP tool for Suppliers, Product-Suppliers, GRN, Picking Lines, or Stock Inquiries — see [What the assistant can and can't query directly](#what-the-assistant-can-and-cant-query-directly) below. For those entities, answer from this data-model reference and point power users at the list page / export.
> * **Numerics are answered via SQL / the list endpoints, not embeddings.** Quantities (shipped, allocated, received, picked, discrepancy) change too often and must be exact — never recall them semantically. Use embeddings only for fuzzy text (supplier names, product names, inquiry notes), then resolve to exact rows.
> * **No UUIDs in answers.** Resolve to human-readable identifiers: supplier code/name, product code/name, shipment number, SPO number, GRN (picking) number, inquiry number, warehouse code/name.
> * **Dates are stored naive UTC.** Be explicit about timezone when quoting timestamps; the UI renders Malaysia time (UTC+8).
> * **Status/enum values below are the codes the database stores.** The UI re-labels them (e.g. `in_transit` → "In Transit"); both are given so you can map a user's words to a filter value.

The seven entities and their backing tables: **Supplier** (`suppliers`), **Product-Supplier** (`product_suppliers`), **Packing List / inbound shipment** (`inbound_shipments`, lines in `inbound_shipment_lines`), **SPO Allocation** (`spo_allocations`), **GRN** (`picking_headers` where `picking_type = 'goods_received'`), **Picking Line** (`picking_lines`), **Stock Inquiry** (`stock_inquiries`).

---

## Supplier — `suppliers`

A vendor we buy from. Menu: [**Procurement → Suppliers**](/procurement-management/suppliers).

**Fields:** `id`, `supplier_code` (unique; UI **Supplier Code**), `supplier_name` (UI **Supplier Name**), `contact_name` (UI column **Contact Person** / form **Contact Person**), `email` (UI **Email**), `phone_number` (UI column **Phone** / form **Phone Number**), `website`, `address_line1`, `address_line2`, `city`, `state`, `postal_code`, `country`, `payment_terms_days` (form **Payment Terms (Days)**, defaults 30), `is_active` (UI **Status** → **Active** / **Inactive**), `created_at`, `updated_at`.

**Date columns:** `created_at`, `updated_at`.

**Filters (list endpoint `GET /api/v1/procurement/suppliers`):** `query` (free text — matches supplier code / name). No server-side active-only filter on the main list (the **Status** column is read off `is_active`).
**Sortable:** `supplier_code`, `supplier_name`, `created_at`. Default sort `created_at` ascending.

> The `/suppliers/select` helper endpoint returns active suppliers for pickers; the main list returns all.

**Example questions**

* "List all active suppliers." (filter the returned rows on `is_active = true`)
* "What's the supplier code for {supplier name}?"
* "Show suppliers in {country / city}." (read `country` / `city` off the rows)
* "Which suppliers have 60-day payment terms?" (`payment_terms_days = 60`)
* "List suppliers sorted by name."
* "Who is the contact person for supplier {code}?"
* "How many suppliers do we have?"
* "Show suppliers created this year."

---

## Product-Supplier — `product_suppliers`

A link saying "this **product** can be bought from this **supplier**", with an optional lead time. Menu: [**Procurement → Product-Suppliers**](/procurement-management/product-suppliers). This list is **read-only** in the UI (columns: **Product Code**, **Product Name**, **Supplier Code**, **Supplier Name**).

**Fields:** `id`, `product_id` (FK → products), `supplier_id` (FK → suppliers), `standard_lead_time_days` (optional), `created_at`. The link is **unique per `(product, supplier)`**. Response embeds the product (`product_code`, `product_name`) and supplier (`supplier_code`, `supplier_name`).

**Date columns:** `created_at`.

**Filters (list endpoint `GET /api/v1/procurement/product-suppliers`):** `product_id`, `supplier_id`. A convenience endpoint `GET /api/v1/procurement/product-suppliers/product/{product_id}` returns all suppliers for one product.
**Sortable:** `created_at` only.

**Example questions**

* "Which suppliers can supply product {code}?" (filter `product_id`)
* "What products does supplier {code} supply?" (filter `supplier_id`)
* "What's the standard lead time for product {code} from supplier {code}?"
* "List every product-supplier link for supplier {name}."
* "Does supplier {X} supply product {Y}?" (filter both)
* "How many products does each supplier cover?" (group by `supplier_id`)

---

## Packing List (inbound shipment) — `inbound_shipments`

An inbound shipment from a supplier, with header dates and a `lines[]` of products shipped. Called **Packing List** in the UI (menu: [**Procurement → Packing Lists**](/procurement-management/packing-lists)); the backing table is `inbound_shipments`, lines in `inbound_shipment_lines`. This is the table for "what's arriving / what did supplier X ship".

**Header fields:** `id`, `shipment_number` (UI **Shipment Number**), `supplier_id` (FK; UI **Supplier**), `shipment_date` (UI **Shipment Date**, required), `estimated_arrival_date` (UI **Expected Arrival** / form **Estimated Arrival Date** — the ETA), `actual_arrival_date`, `bill_of_lading_number`, `shipping_container_number` (UI **Container Number**), `invoice_number`, `shipment_status` (UI **Status**), `total_items_shipped`, `total_cartons`, `notes`, `attachment_id` (linked packing-list file), `access_levels`, `created_at`, `updated_at`. List rows also carry `lines_count`, `spo_allocations_count`, `display_total_items` (UI **Items**), `display_total_cartons`.

**Line fields (`inbound_shipment_lines`):** `product_id`, `quantity_shipped`, `uom_id`, `batch_number`, `serial_number_range_from`/`_to`, `carton_number`, `cartons_count`, `weight_per_carton`, `unit_cost`, `spo_allocated_quantity` (qty already allocated to SPOs), `quantity_received`, `line_status`.

**Date columns:** `shipment_date`, `estimated_arrival_date` (ETA), `actual_arrival_date`, `created_at`, `updated_at`.

**Status (`shipment_status`):** stored default `in_transit`; the service recomputes a shipment to `fully_received` when every line is received. UI re-labels: `in_transit` → **In Transit**, `fully_received`/`completed` → **Completed** / **Delivered**, `cancelled` → **Cancelled**, `draft` → **Draft**. *(Persisted set beyond `in_transit` / `fully_received` is partly UI-formatted — see audit flags.)*

**Line status (`line_status`):** `in_transit`, `allocated`, `partially_allocated`, `received`, `partially_received`.

**Filters (list endpoint `GET /api/v1/procurement/packing-lists`):** `query` (free text), `supplier_id`, `shipment_status`.
**Sortable:** `shipment_number`, `shipment_date`, `created_at`, `updated_at`. Default sort `created_at` ascending.

**Example questions**

* "List packing lists from supplier {name} shipped between 1 Jan and 31 Mar." (resolve supplier → `supplier_id`, filter `shipment_date`)
* "Which shipments are still in transit?" (`shipment_status = in_transit`)
* "Show the packing list for shipment number {X}." (`query` or resolve)
* "What's the ETA of container {container number}?" (`query`, read `estimated_arrival_date`)
* "Which shipments arrive (ETA) this month?" (`estimated_arrival_date` window — **also answerable via the incoming-stock tools, preferred**)
* "How many cartons / items are on shipment {X}?" (`display_total_cartons` / `display_total_items`)
* "List shipments with no SPO allocations yet." (`spo_allocations_count = 0`)
* "What products and batches are on shipment {X}?" (read `lines[]`: `product_code`, `batch_number`, `quantity_shipped`)

---

## SPO Allocation — `spo_allocations`

An allocation of part of a shipment line to a **warehouse** against an **SPO number** (the procurement/stock purchase order reference). Menu: [**Procurement → SPO Allocations**](/procurement-management/spo-allocations). This is the table for "how much of SPO X is going where, and how much has arrived".

**Fields:** `id`, `spo_number` (UI **SPO Number**), `spo_line_number`, `inbound_shipment_id` (FK → packing list; UI **Packing List**), `warehouse_id` (FK; UI **Location** / form **Warehouse**), `storage_zone_id`, `product_id` (UI **Product**), `allocated_quantity` (UI **Allocated**), `uom_id`, `receipt_status` (UI **Status**), `quantity_received` (UI **Received**), `quantity_rejected`, `allocation_notes`, `created_at`, `updated_at`. List rows also carry `grn_lines_count` and `linked_grns` (GRN navigation), and the grouped views add the shipment's shipped qty (UI **Shipped**). **Unique per `(spo_number, product_id, warehouse_id)`.**

**Date columns:** `created_at`, `updated_at`. *(No business/PO date column — SPO allocations have no own date field; use `created_at` for time windows.)*

**Status (`receipt_status`):** stored default `pending`; service sets `fully_received` when fully received. UI re-labels: `pending` → **Pending**, `allocated` → **Allocated**, `partially_received` → **Partially Received**, `fully_received` → **Fully Received**. *(Canonical persisted set beyond `pending` / `fully_received` is partly UI-formatted — see audit flags.)*

**Filters (list endpoint `GET /api/v1/procurement/spo-allocations`):** `query` (free text), `shipment_id`, `warehouse_id`, `receipt_status`. Two grouped views also exist — `GET …/spo-allocations/grouped-by-shipment` and `…/grouped-by-spo-number` — which additionally accept `product_code` and `warehouse_id`.
**Sortable:** `spo_number`, `created_at`, `updated_at`. Default sort `created_at` ascending (grouped views default to `shipment_number` / `spo_number`).

**Example questions**

* "List allocations for SPO number {X}." (`query`)
* "Which SPO allocations are still pending receipt?" (`receipt_status = pending`)
* "How much of product {code} is allocated to warehouse {name}?" (filter `warehouse_id` + product, sum `allocated_quantity`)
* "Show allocations on packing list / shipment {X}." (`shipment_id`)
* "How much of SPO {X} has been received vs rejected?" (`quantity_received` / `quantity_rejected`)
* "List fully-received allocations for warehouse {name}." (`receipt_status = fully_received` + `warehouse_id`)
* "Which allocations don't have a GRN yet?" (`grn_lines_count = 0`)
* "Group allocations by SPO number for product {code}." (grouped-by-spo-number view + `product_code`)

---

## GRN (Goods Receipt Note) — `picking_headers` (`picking_type = 'goods_received'`)

A goods-receipt header recording what was physically received against an SPO. Menu: [**Procurement → GRN**](/procurement-management/grn). **The backing table is `picking_headers`; a GRN is a picking header whose `picking_type = 'goods_received'`** — every GRN query is filtered on that. Its lines are [Picking Lines](#picking-line--picking_lines).

**Fields:** `id`, `picking_number` (UI **GRN Number**, unique), `spo_number` (UI **SPO Number**), `picking_type` (always `goods_received` for GRNs), `source_entity_type`, `source_entity_id`, `picking_date` (UI **Picking Date**), `picked_by_user_id`, `inspection_status`, `quality_remarks`, `inspected_by_user_id`, `inspection_date`, `picking_status` (UI **Status**), `total_items_picked`, `total_items_discrepancy`, `total_cost`, `notes`, `created_at`, `updated_at`. List rows add `lines_count` and `items_count` (distinct products; UI **Number of Items**).

**Date columns:** `picking_date`, `inspection_date`, `created_at`, `updated_at`.

**Status (`picking_status`, the UI "Status"):** `draft` → **Draft**, `approved` → **Approved**, `rejected` → **Rejected** (default `draft`). These are the values in the list's **Status** filter (**All statuses** / **Draft** / **Approved** / **Rejected**).
**Inspection status (`inspection_status`):** default `pending` (e.g. `pending` / `passed` / `failed`). Filterable on the list endpoint but **not surfaced as a column or filter control in the list UI** — it shows on the detail page.

**Filters (list endpoint `GET /api/v1/procurement/grn`):** `query` (matches GRN number, SPO number, and linked product code/name), `entities` (free-text entity bag resolved server-side via substring → trigram → RAG; one entity per array element), `product_query` (partial product filter on lines), `picking_status`, `inspection_status`.
**Sortable:** `picking_number`, `picking_date`, `created_at`, `updated_at`, plus `lines_count` and `items_count`. Default sort `created_at` ascending.

**Example questions**

* "List GRNs received between 1 Feb and 28 Feb." (filter `picking_date`)
* "Show GRNs still in Draft." (`picking_status = draft`)
* "Which GRNs are rejected?" (`picking_status = rejected`)
* "Show the GRN for SPO number {X}." (`query`)
* "List GRNs that received product {code}." (`product_query` or `entities`)
* "Which GRNs have the most line items?" (sort `items_count` desc)
* "Show GRN {picking number} — its lines, status, and inspection result."
* "How many GRNs were created this week?"

---

## Picking Line — `picking_lines`

A single received line under a GRN: product, expected vs picked quantity, condition, and the SPO allocation it fulfils. Menu: [**Procurement → Picking Lines**](/procurement-management/picking-lines) — a **read-only** flat list of all GRN lines (columns: **SPO Allocation**, **Product**, **Location**, **Expected**, **Picked**). The list only shows lines whose parent header is a GRN (`picking_type = 'goods_received'`).

**Fields:** `id`, `picking_header_id` (FK → GRN), `spo_allocation_id` (FK → SPO allocation; UI **SPO Allocation** shows the SPO number), `product_id` (UI **Product**), `quantity_expected` (UI **Expected**), `quantity_picked` (UI **Picked**), `quantity_discrepancy` (**DB-generated** = `quantity_expected − quantity_picked`), `uom_id`, `picked_condition` (default `good`), `condition_remarks`, `batch_number_picked`, `expiry_date`, `unit_cost`, `line_total`, `source_warehouse_id`, `destination_warehouse_id` (UI **Location**), `created_at`, `updated_at`.

**Date columns:** `expiry_date` (of the picked batch), `created_at`, `updated_at`.

**Filters (list endpoint `GET /api/v1/procurement/picking-lines`):** `query` only (matches SPO allocation number, product code, product name).
**Sortable:** `spo_allocation` (by SPO number), `product` (by product code), `quantity_expected`, `quantity_picked`. Default sort `spo_allocation` ascending.

**Example questions**

* "List picking lines for SPO allocation {SPO number}." (`query`)
* "Show all received lines for product {code}." (`query`)
* "Which picking lines have a quantity discrepancy?" (rows where `quantity_picked ≠ quantity_expected`)
* "What batch and expiry was picked for product {code}?" (`batch_number_picked`, `expiry_date`)
* "List lines picked into warehouse {name}." (read `destination_warehouse`)
* "Sort picking lines by quantity picked, highest first." (`sort=quantity_picked&dir=desc`)

---

## Stock Inquiry — `stock_inquiries`

A "can we supply this?" question raised by sales, routed through project sales to purchasing, and answered. Menu: [**Procurement → Stock Inquiries**](/procurement-management/stock-inquiries). Separate from the shipment chain — it's a request/answer record with a lifecycle (see [Stock inquiry lifecycle](../purchasing/stock-inquiry-lifecycle-and-next-actions.md)).

**Fields:** `id`, `inquiry_number` (UI **Stock inquiry number**), `salesperson` (UI **Salesperson**), `product_code` (UI **Product Code**), `item_description` (UI **Item Description**), `project_customer` (UI **Project Customer**), `project_name` (UI **Project Name**), `quantity` (UI **Quantity** — **stored as TEXT**, free-form), `delivery_date` (UI **Delivery Date** — **stored as TEXT**, not a real date column), `remark` (UI **Remark**), `additional_remark`, `purchasing_response` (the answer), `status` (UI **Status**), `last_responded_by` / `last_responded_at`, `rejection_reason` / `rejected_at` / `rejected_by` / `rejected_from`, `reopen_reason` / `reopened_at` / `reopened_by`, `contact_id` / `space_id` / `respond_inbox_url` (Respond.io chat), `created_at` (UI **Created**), `updated_at`.

**Date columns:** `created_at` (default sort), `updated_at`, `last_responded_at`, `rejected_at`, `reopened_at`. **`delivery_date` is free TEXT** — do **not** do date-window math on it; treat it as a label.

**Status (`status`) — lifecycle values:**

| Code | UI label | Meaning |
|------|----------|---------|
| `new` | **New** | Just raised, not yet submitted. |
| `pending_project_sales` | **Pending project sales** | Waiting for project sales to review. |
| `pending_purchasing` | **Pending purchasing** | Approved by project sales; waiting on purchasing to answer. |
| `responded` | **Responded** | Purchasing has answered — handled. |
| `rejected` | **Rejected** | Turned down (by project sales or purchasing); can be reopened. |

*(Create accepts only `new`, `pending_project_sales`, `pending_purchasing`; the rest are reached by lifecycle actions. The list filter also shows an **Updated** option — see audit flags.)*

**Filters (list endpoint `GET /api/v1/procurement/stock-inquiries`):** `query` (free text), `status` (**comma-separated** — pass multiple values to match any).
**Sortable:** `inquiry_number`, `product_code`, `item_description`, `project_customer`, `project_name`, `quantity`, `delivery_date`, `remark`, `salesperson`, `status`, `last_responded_at`, `created_at`, `updated_at`. Default sort `created_at` **descending**.

**Example questions**

* "List stock inquiries awaiting purchasing." (`status=pending_purchasing`)
* "Show new and pending-project-sales inquiries." (`status=new,pending_project_sales`)
* "Which inquiries did we reject and why?" (`status=rejected`, read `rejection_reason`)
* "List inquiries for product code {X}." (`query` or sort/filter `product_code`)
* "Show inquiries raised by salesperson {name} this month." (`query`, `created_at` window)
* "Which inquiries has purchasing answered, and who answered?" (`status=responded`, `last_responded_by` / `last_responded_at`)
* "List inquiries for project customer {X}." (`query`)
* "Show inquiries created between 1 Jan and 31 Mar, newest first." (`created_at` window — default sort already desc)

---

## What the assistant can and can't query directly

The AI assistant's read tools only cover procurement **from the incoming-stock angle**. Be honest about the boundary.

**Has dedicated MCP tools (incoming-stock family — packing lists / inbound shipments / SPO arrivals):**

| Tool | Use it for | Required narrower |
|------|-----------|-------------------|
| `crm_incoming_stock_by_product` | "Is SKU X arriving? / how much is pending? / where will it be stocked?" — one-shot per product. Returns total remaining incoming qty, per-warehouse allocation summary, per-shipment breakdown (shipment number, container, ETA, batch, packing-list attachment), nearest ETA. | `product_ids` (optional ETA window `eta_from`/`eta_to`) |
| `crm_incoming_stock_shipments` | "Any incoming shipments this month? / arriving on date X? / open shipments from supplier Y" — shipment headers. | at least one of `shipment_ids`, `supplier_ids`, `eta_from`/`eta_to` |
| `crm_incoming_stock_list` | Unified incoming list — shipment rows with nested product `lines[]` (product code/name, batch, remaining qty, warehouse allocations). Covers both "incoming for product X" and "arriving this month / from supplier Y / shipment Z". | at least one of `product_ids`, `shipment_ids`, `supplier_ids`, `eta_from`/`eta_to` |

These never expose received/rejected quantities, SPO numbers, or internal IDs — they answer the **"what's still coming in"** question, not "what was received".

**Has NO dedicated MCP tool — answer from this reference, don't fabricate a query:**

* **Suppliers**, **Product-Suppliers**, **GRN**, **Picking Lines**, **Stock Inquiries.**

For these, the assistant **cannot directly run a filtered query**. Explain what the data means using this page, and direct power users to the relevant list page (links above) where they can search, filter, sort, and export. Don't claim to have listed/counted rows you couldn't actually fetch.

## See also

* [Upload a packing list](../purchasing/upload-packing-list.md)
* [Upload an SPO](../purchasing/upload-spo.md)
* [Upload a GRN (header + lines)](../warehouse/upload-grn.md)
* [Review a stock inquiry](../purchasing/review-stock-inquiry.md)
* [Stock inquiry lifecycle & what to do at each stage](../purchasing/stock-inquiry-lifecycle-and-next-actions.md)
* [Manage suppliers](manage-suppliers.md)
* [Review and approve a GRN](review-grn.md)
* [Inventory — Data analysis for the AI assistant](../inventory/data-analysis.md) (where received stock lands)
