"""Read-only GET endpoint catalog → MCP tools (1:1 with CRM list/detail/search GETs in scope)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    path: str
    path_params: tuple[str, ...] = ()
    query_params: tuple[str, ...] = ()
    method: str = "GET"
    body_params: tuple[str, ...] = ()


# Paths match [sorento_crm_backend/app/api/v1/__init__.py](sorento_crm_backend/app/api/v1/__init__.py) prefixes.
# Comment to rebuild
CATALOG: tuple[ToolSpec, ...] = (
    # --- master-data ---
    ToolSpec(
        "crm_master_products_list",
        "List products with filters and pagination. `query` filters by code/name/description; omit it for a general paged list. `category_id` accepts UUID or category_code/name. `brand_id` accepts UUID or brand_code/name.",
        "/api/v1/master-data/products",
        (),
        (
            "page",
            "limit",
            "query",
            "category_id",
            "brand_id",
            "status",
            "price_min",
            "price_max",
            "item_type",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_master_products_get",
        "Get one product full detail record. `product_id` accepts UUID or product_code (SKU). For keyword searches like 'bathtubs' or product names, use crm_master_products_list with query.",
        "/api/v1/master-data/products/{product_id}",
        ("product_id",),
        (),
    ),
    ToolSpec(
        "crm_master_products_select",
        "Lightweight product list for dropdowns (active only, optional search).",
        "/api/v1/master-data/products/select",
        (),
        ("query",),
    ),
    ToolSpec(
        "crm_master_brands_list",
        "List brands with pagination.",
        "/api/v1/master-data/brands",
        (),
        ("page", "limit", "query"),
    ),
    ToolSpec(
        "crm_master_brands_select",
        "Brands for select controls.",
        "/api/v1/master-data/brands/select",
        (),
        ("query",),
    ),
    ToolSpec(
        "crm_master_brands_get",
        "Get one brand by id. `brand_id` accepts UUID or brand_code/name.",
        "/api/v1/master-data/brands/{brand_id}",
        ("brand_id",),
        (),
    ),
    ToolSpec(
        "crm_master_product_categories_tree",
        "Product category tree.",
        "/api/v1/master-data/product-categories/tree",
        (),
        (),
    ),
    ToolSpec(
        "crm_master_product_categories_list",
        "List product categories.",
        "/api/v1/master-data/product-categories",
        (),
        ("page", "limit", "query"),
    ),
    ToolSpec(
        "crm_master_product_categories_select",
        "Categories for select controls.",
        "/api/v1/master-data/product-categories/select",
        (),
        ("query",),
    ),
    ToolSpec(
        "crm_master_product_categories_get",
        "Get one product category by id. `category_id` accepts UUID or category_code/name.",
        "/api/v1/master-data/product-categories/{category_id}",
        ("category_id",),
        (),
    ),
    ToolSpec(
        "crm_master_units_of_measure_list",
        "List units of measure.",
        "/api/v1/master-data/units-of-measure",
        (),
        ("page", "limit", "query"),
    ),
    ToolSpec(
        "crm_master_units_of_measure_select",
        "UOMs for select controls.",
        "/api/v1/master-data/units-of-measure/select",
        (),
        ("query",),
    ),
    ToolSpec(
        "crm_master_units_of_measure_get",
        "Get one UOM by id.",
        "/api/v1/master-data/units-of-measure/{uom_id}",
        ("uom_id",),
        (),
    ),
    ToolSpec(
        "crm_master_product_attachments_list",
        "List product–attachment links with filters. `product_id` accepts a product UUID or exact product code.",
        "/api/v1/master-data/product-attachments",
        (),
        ("page", "limit", "sort", "dir", "product_id", "attachment_id", "user_type"),
    ),
    ToolSpec(
        "crm_master_product_attachments_get",
        "Get one product attachment link by id.",
        "/api/v1/master-data/product-attachments/{product_attachment_id}",
        ("product_attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_master_product_attachments_by_product",
        "All attachment links for a product. `product_id` accepts a product UUID or exact product code.",
        "/api/v1/master-data/product-attachments/product/{product_id}",
        ("product_id",),
        ("user_type",),
    ),
    # --- marketing ---
    ToolSpec(
        "crm_marketing_promotions_list",
        "List promotions (summary: promo fields and products_count only; no product lines). For lines use crm_marketing_promotion_products_list or nested products tool.",
        "/api/v1/marketing/promotions",
        (),
        ("page", "limit", "query", "user_type", "status", "promo_type", "sort", "dir"),
    ),
    ToolSpec(
        "crm_marketing_promotions_get",
        "Get one promotion metadata and groups (FOC tiers, etc.). Does NOT include product lines by default; set include_products=true only if you need nested SKU lines.",
        "/api/v1/marketing/promotions/{promotion_id}",
        ("promotion_id",),
        ("user_type", "include_products"),
    ),
    ToolSpec(
        "crm_marketing_promotion_products_nested",
        "Products linked to a promotion (nested under promotion). Optional page/limit (default limit 1000, max 5000).",
        "/api/v1/marketing/promotions/{promotion_id}/products",
        ("promotion_id",),
        ("page", "limit"),
    ),
    ToolSpec(
        "crm_marketing_promotion_products_list",
        "Promotion product lines (paginated). Optional promotion_id (UUID or promo_code) scopes to one promotion. Optional query does text search by SKU/product name/promo code and can be used without promotion_id to find which promotions a product appears in.",
        "/api/v1/marketing/promotion-products",
        (),
        ("page", "limit", "sort", "dir", "query", "promotion_id"),
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_list",
        "List/search promotion–attachment links. Optional promotion_id scopes one promotion (UUID or promo_code). Optional query searches promotion header details, product code/name, promotion group name, and attachment metadata.",
        "/api/v1/marketing/promotion-attachments",
        (),
        ("page", "limit", "sort", "dir", "query", "promotion_id", "attachment_id"),
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_get",
        "Get one promotion attachment link by id.",
        "/api/v1/marketing/promotion-attachments/{promotion_attachment_id}",
        ("promotion_attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_by_promotion",
        "All promotion attachments for a promotion. promotion_id may be UUID or promo_code (ambiguous if duplicate codes exist—use UUID).",
        "/api/v1/marketing/promotion-attachments/promotion/{promotion_id}",
        ("promotion_id",),
        (),
    ),
    ToolSpec(
        "crm_marketing_campaigns_list",
        "List marketing campaigns.",
        "/api/v1/marketing/campaigns",
        (),
        ("page", "limit"),
    ),
    ToolSpec(
        "crm_marketing_campaigns_get",
        "Get one campaign by id.",
        "/api/v1/marketing/campaigns/{campaign_id}",
        ("campaign_id",),
        (),
    ),
    ToolSpec(
        "crm_marketing_campaign_types_list",
        "List campaign types.",
        "/api/v1/marketing/campaign-types",
        (),
        (),
    ),
    ToolSpec(
        "crm_marketing_campaign_types_get",
        "Get one campaign type by id.",
        "/api/v1/marketing/campaign-types/{type_id}",
        ("type_id",),
        (),
    ),
    # --- resource-management ---
    ToolSpec(
        "crm_resource_attachments_list",
        "List file attachments (filters: query, entity, directory, trash).",
        "/api/v1/resource-management/attachments",
        (),
        (
            "page",
            "limit",
            "query",
            "sort",
            "dir",
            "entity_type",
            "entity_id",
            "directory_id",
            "is_deleted",
            "resolve_signed_urls",
        ),
    ),
    ToolSpec(
        "crm_resource_attachments_current_stock_list",
        "Latest Stock List attachment row if configured.",
        "/api/v1/resource-management/attachments/current-stock-list",
        (),
        (),
    ),
    ToolSpec(
        "crm_resource_attachments_get",
        "Get attachment metadata by id (includes linked entities).",
        "/api/v1/resource-management/attachments/{attachment_id}",
        ("attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_resource_attachments_download",
        "Download attachment bytes (binary; may be large). Prefer metadata tool when possible.",
        "/api/v1/resource-management/attachments/{attachment_id}/download",
        ("attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_resource_attachments_metadata",
        "Attachment metadata only (same as get for most fields).",
        "/api/v1/resource-management/attachments/{attachment_id}/metadata",
        ("attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_resource_attachments_preview_url",
        "Signed preview URL for an attachment.",
        "/api/v1/resource-management/attachments/{attachment_id}/preview-url",
        ("attachment_id",),
        (),
    ),
    ToolSpec(
        "crm_resource_attachment_types_list",
        "List attachment types.",
        "/api/v1/resource-management/attachment-types",
        (),
        ("page", "limit", "query", "sort", "dir"),
    ),
    ToolSpec(
        "crm_resource_attachment_types_get",
        "Get attachment type by id.",
        "/api/v1/resource-management/attachment-types/{type_id}",
        ("type_id",),
        (),
    ),
    ToolSpec(
        "crm_resource_directories_list",
        "List directories under optional parent_id.",
        "/api/v1/resource-management/directories",
        (),
        ("parent_id",),
    ),
    ToolSpec(
        "crm_resource_directories_tree",
        "Directory tree; use deleted=true for trash tree.",
        "/api/v1/resource-management/directories/tree",
        (),
        ("deleted",),
    ),
    ToolSpec(
        "crm_resource_directories_get",
        "Get one directory by id.",
        "/api/v1/resource-management/directories/{directory_id}",
        ("directory_id",),
        (),
    ),
    # --- inventory ---
    ToolSpec(
        "crm_inventory_stock_balance_list",
        "Paged stock balances (warehouse, product, quantity filters, status). `product_id` accepts UUID or product_code (SKU). `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/stock/balance",
        (),
        (
            "page",
            "limit",
            "query",
            "sort",
            "dir",
            "warehouse_id",
            "product_id",
            "quantity_operator",
            "quantity_value",
            "status",
        ),
    ),
    ToolSpec(
        "crm_inventory_stock_dashboard",
        "Stock dashboard aggregates.",
        "/api/v1/inventory/stock/dashboard",
        (),
        (),
    ),
    ToolSpec(
        "crm_inventory_stock_alerts",
        "Low-stock style alerts from API.",
        "/api/v1/inventory/stock/alerts",
        (),
        (),
    ),
    ToolSpec(
        "crm_inventory_stock_balance_export",
        "Export all stock rows (no pagination) with optional filters; requires export permission on act-as user. product_id accepts UUID or product_code (SKU).",
        "/api/v1/inventory/stock/balance/export",
        (),
        ("warehouse_id", "product_id", "quantity_operator", "quantity_value"),
    ),
    ToolSpec(
        "crm_inventory_stock_ledger_by_product_warehouse",
        "Ledger for one product in one warehouse. product_id may be UUID or product_code (SKU).",
        "/api/v1/inventory/stock/{product_id}/{warehouse_id}/ledger",
        ("product_id", "warehouse_id"),
        ("page", "limit"),
    ),
    ToolSpec(
        "crm_inventory_warehouses_list",
        "List warehouses.",
        "/api/v1/inventory/warehouses",
        (),
        ("page", "limit", "query", "is_active"),
    ),
    ToolSpec(
        "crm_inventory_warehouses_get",
        "Get warehouse by id. `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/warehouses/{warehouse_id}",
        ("warehouse_id",),
        (),
    ),
    ToolSpec(
        "crm_inventory_storage_zones_list",
        "List storage zones. `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/storage-zones",
        (),
        ("page", "limit", "warehouse_id"),
    ),
    ToolSpec(
        "crm_inventory_storage_zones_tree",
        "Storage zone tree. `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/storage-zones/tree",
        (),
        ("warehouse_id",),
    ),
    ToolSpec(
        "crm_inventory_storage_zones_get",
        "Get storage zone by id.",
        "/api/v1/inventory/storage-zones/{zone_id}",
        ("zone_id",),
        (),
    ),
    ToolSpec(
        "crm_inventory_stock_ledger_list",
        "Global stock ledger list. `product_id` accepts UUID or product_code (SKU). `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/stock-ledger",
        (),
        ("page", "limit", "product_id", "warehouse_id", "transaction_type"),
    ),
    ToolSpec(
        "crm_inventory_stock_batches_list",
        "List stock batches. `product_id` accepts UUID or product_code (SKU). `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/inventory/stock-batches",
        (),
        ("page", "limit", "product_id", "warehouse_id"),
    ),
    ToolSpec(
        "crm_inventory_stock_batches_get",
        "Get stock batch by id.",
        "/api/v1/inventory/stock-batches/{batch_id}",
        ("batch_id",),
        (),
    ),
    # --- order-management ---
    ToolSpec(
        "crm_order_management_orders_list",
        "List orders (customer, status, has_order_lines, ORDER DATE filters, optional actual delivery date filters, search). For complaint DO discovery, prefer `order_date_from`/`order_date_to` (order date range) together with customer/product hints. Parameter `query` matches order number, debtor name/code, and customer name/code. `customer_id` accepts UUID or customer_code/name. `order_status_id` accepts UUID or status_code/name.",
        "/api/v1/order-management/orders",
        (),
        (
            "page",
            "limit",
            "query",
            "customer_id",
            "order_status_id",
            "has_order_lines",
            "has_actual_delivery_date",
            "order_date_from",
            "order_date_to",
            "actual_delivery_date_from",
            "actual_delivery_date_to",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_order_management_orders_get",
        "Get one order by id (includes order lines in response). `order_id` accepts UUID or order_number.",
        "/api/v1/order-management/orders/{order_id}",
        ("order_id",),
        (),
    ),
    ToolSpec(
        "crm_order_management_orders_by_product_list",
        "List distinct CUSTOMER SALES orders containing a specific product (outgoing / sold, NOT incoming stock). For complaint DO discovery, prefer `order_date_from`/`order_date_to` (ORDER DATE range), not delivery date range. Use when asked 'which customers bought SKU X' or 'pending customer orders for product X'. DO NOT use for 'any incoming for product X' / 'is product X arriving' — that is procurement, use crm_procurement_spo_allocations_grouped_by_shipment instead. Parameter `query` matches product code, name, description, order number, and debtor name. `product_id` accepts UUID or product_code (SKU).",
        "/api/v1/order-management/orders/by-product",
        (),
        (
            "page",
            "limit",
            "query",
            "product_id",
            "has_actual_delivery_date",
            "order_date_from",
            "order_date_to",
            "actual_delivery_date_from",
            "actual_delivery_date_to",
            "sort",
            "dir",
        ),
    ),
    # --- incoming-stock (user-facing, business-rule compliant) ---
    # These are the PRIMARY tools the AI should use for "any incoming?" questions.
    # They redact quantity_received / quantity_rejected / SPO numbers / internal IDs, and
    # compute remaining_incoming_quantity + warehouse allocation summary for the user.
    ToolSpec(
        "crm_incoming_stock_by_product",
        (
            "ONE-SHOT tool for any 'incoming for product X' / 'is SKU X arriving?' / 'how much is pending for this product?' / 'where will this product be stocked?' question. "
            "This single call returns EVERYTHING the user needs: "
            "(1) total_remaining_incoming_quantity = sum of (quantity_shipped - quantity_received) across still-incoming lines, auto-excludes fully-received lines; "
            "(2) warehouse_allocation_summary aggregated per warehouse from SPO allocations \u2014 each entry has warehouse_code, warehouse_name, allocated_quantity; "
            "(3) per-shipment breakdown: shipment_number, shipping_container_number, estimated_arrival_date, batch_number, remaining_incoming_quantity, packing-list attachment (if any), and warehouse_allocations for that shipment; "
            "(4) nearest_estimated_arrival_date. "
            "DO NOT also call crm_incoming_stock_shipments, crm_incoming_stock_shipment_products, crm_incoming_stock_shipment_attachment, or crm_incoming_stock_grn when answering a product-incoming question \u2014 this tool already includes their data. "
            "Does NOT expose received quantities, SPO numbers, or internal IDs. "
            "`product_id` accepts UUID or product_code (SKU). Provide either product_id OR a free-text `query`."
        ),
        "/api/v1/incoming-stock/by-product",
        (),
        ("product_id", "query", "limit"),
    ),
    ToolSpec(
        "crm_incoming_stock_shipments",
        (
            "Use ONLY for SHIPMENT-CENTRIC questions (not product questions): 'any incoming shipments this month?' / 'what is arriving with ETA on date X?' / 'list open shipments from supplier Y'. "
            "Do NOT use this for 'any incoming for product X' \u2014 use crm_incoming_stock_by_product (which already includes per-shipment breakdown). "
            "Returns shipment headers (shipment_number, shipping_container_number, estimated_arrival_date, total_remaining_incoming_quantity, distinct_products_incoming, packing-list attachment). "
            "`query` searches shipment_number / container / BOL / invoice."
        ),
        "/api/v1/incoming-stock/shipments",
        (),
        ("query", "eta_from", "eta_to", "page", "limit"),
    ),
    ToolSpec(
        "crm_incoming_stock_shipment_products",
        (
            "Use ONLY when the user asks 'what products are on shipment X?' with a SHIPMENT NUMBER (not a product). "
            "Do NOT use this for 'any incoming for product X' \u2014 use crm_incoming_stock_by_product. "
            "Returns still-incoming products on the shipment with product_code, product_name, batch_number, remaining_incoming_quantity, warehouse allocation per product, and shipment header. "
            "`shipment_id` accepts UUID, shipment_number, container number, BOL, or invoice number."
        ),
        "/api/v1/incoming-stock/shipments/{shipment_id}/products",
        ("shipment_id",),
        (),
    ),
    ToolSpec(
        "crm_incoming_stock_shipment_attachment",
        (
            "Use ONLY when the user EXPLICITLY asks for the packing-list file / shipment document for a SHIPMENT (by shipment number or container). "
            "Do NOT use for product questions \u2014 crm_incoming_stock_by_product already includes the per-shipment attachment. "
            "Returns filename, file_path (URL), mime_type, or null. `shipment_id` accepts UUID, shipment_number, container, BOL, or invoice."
        ),
        "/api/v1/incoming-stock/shipments/{shipment_id}/attachment",
        ("shipment_id",),
        (),
    ),
    ToolSpec(
        "crm_incoming_stock_grn",
        (
            "Use ONLY when the user EXPLICITLY asks about GRN / goods received note / receipt document / 'has a GRN been created?'. "
            "Do NOT use for 'any incoming for product X' questions \u2014 the user is asking about what's still coming, not what has been received. "
            "Returns minimal GRN info (grn_number, grn_date, grn_status, shipment_number). NO quantities, NO received/rejected counts. "
            "Requires `shipment_id` or `product_id` (either accepts UUID or business code)."
        ),
        "/api/v1/incoming-stock/grn",
        (),
        ("shipment_id", "product_id", "limit"),
    ),
    # --- procurement (ADMIN / INTERNAL raw data) ---
    # These expose raw receipt data (quantity_received, quantity_rejected, SPO numbers,
    # internal IDs). DO NOT use for user-facing enquiries — use crm_incoming_stock_* tools
    # instead. Kept here for admin / back-office operations only.
    ToolSpec(
        "crm_procurement_packing_lists_list",
        "INTERNAL / ADMIN only: raw inbound shipment headers including received quantities, SPO counts, and internal IDs. For user-facing 'any incoming?' questions use crm_incoming_stock_shipments. `supplier_id` accepts UUID or supplier_code/name.",
        "/api/v1/procurement/packing-lists",
        (),
        ("page", "limit", "query", "supplier_id", "shipment_status", "sort", "dir"),
    ),
    ToolSpec(
        "crm_procurement_packing_lists_get",
        "INTERNAL / ADMIN only: full raw inbound shipment detail including received/rejected quantities, SPO allocations, linked GRNs, and internal IDs. For user-facing 'products in this shipment' use crm_incoming_stock_shipment_products. `shipment_id` accepts UUID, shipment_number, BOL, container #, or invoice #.",
        "/api/v1/procurement/packing-lists/{shipment_id}",
        ("shipment_id",),
        (),
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_grouped_by_shipment",
        "INTERNAL / ADMIN only: raw SPO allocation aggregates per shipment (receipt_status, counts). For user-facing 'any incoming for product X' use crm_incoming_stock_by_product. `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/procurement/spo-allocations/grouped-by-shipment",
        (),
        (
            "page",
            "limit",
            "query",
            "product_code",
            "warehouse_id",
            "receipt_status",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_grouped_by_spo",
        "INTERNAL / ADMIN only: SPO allocations grouped by SPO number.",
        "/api/v1/procurement/spo-allocations/grouped-by-spo-number",
        (),
        (
            "page",
            "limit",
            "query",
            "product_code",
            "warehouse_id",
            "receipt_status",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_list",
        "INTERNAL / ADMIN only: flat list of raw SPO allocations with receipt_status, quantity_received, quantity_rejected, SPO numbers. Do NOT use for user enquiries. `shipment_id` accepts UUID or shipment_number / BOL / container / invoice. `warehouse_id` accepts UUID or warehouse_code/name.",
        "/api/v1/procurement/spo-allocations",
        (),
        (
            "page",
            "limit",
            "query",
            "shipment_id",
            "warehouse_id",
            "receipt_status",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_get",
        "INTERNAL / ADMIN only: single SPO allocation with linked GRNs and raw receipt fields. `allocation_id` accepts UUID or spo_number.",
        "/api/v1/procurement/spo-allocations/{allocation_id}",
        ("allocation_id",),
        (),
    ),
    ToolSpec(
        "crm_procurement_grn_list",
        "INTERNAL / ADMIN only: raw GRN / picking headers list with statuses and totals. For user-facing 'has a GRN been created?' use crm_incoming_stock_grn.",
        "/api/v1/procurement/grn",
        (),
        ("page", "limit", "query", "picking_status", "inspection_status", "sort", "dir"),
    ),
    ToolSpec(
        "crm_procurement_grn_get",
        "INTERNAL / ADMIN only: full GRN / picking header including picking lines and quantities. `grn_id` accepts UUID or picking_number.",
        "/api/v1/procurement/grn/{grn_id}",
        ("grn_id",),
        (),
    ),
    ToolSpec(
        "crm_procurement_picking_lines_list",
        "INTERNAL / ADMIN only: picking lines (receipt lines) with quantities and discrepancies.",
        "/api/v1/procurement/picking-lines",
        (),
        ("page", "limit", "query", "sort", "dir"),
    ),
    # --- forms ---
    ToolSpec(
        "crm_forms_management_forms_list",
        "List forms. Each row includes form_type. Optional form_type query param filters by type; query searches code, name, purpose, and form_type.",
        "/api/v1/forms-management/forms",
        (),
        ("page", "limit", "query", "language", "status", "form_type", "sort", "dir"),
    ),
    ToolSpec(
        "crm_forms_management_forms_get",
        "Get form by id.",
        "/api/v1/forms-management/forms/{form_id}",
        ("form_id",),
        (),
    ),
    # --- workflow-forms ---
    ToolSpec(
        "crm_workflow_forms_definitions_list",
        "List workflow form definitions. Use q for search (tool also accepts query alias and maps it to q).",
        "/api/v1/workflow-forms/definitions",
        (),
        ("page", "limit", "q", "is_active"),
    ),
    ToolSpec(
        "crm_workflow_forms_definitions_published_for_submission",
        "Published definitions for users who submit (narrow list).",
        "/api/v1/workflow-forms/definitions/published-for-submission",
        (),
        (),
    ),
    ToolSpec(
        "crm_workflow_forms_definitions_get",
        "Workflow definition by id.",
        "/api/v1/workflow-forms/definitions/{definition_id}",
        ("definition_id",),
        (),
    ),
    ToolSpec(
        "crm_workflow_forms_definitions_preview",
        "Preview draft or published schema. source=draft|published.",
        "/api/v1/workflow-forms/definitions/{definition_id}/preview",
        ("definition_id",),
        ("source",),
    ),
    ToolSpec(
        "crm_workflow_forms_definitions_published_schema",
        "Published schema for building submissions.",
        "/api/v1/workflow-forms/definitions/{definition_id}/published-schema",
        ("definition_id",),
        (),
    ),
    ToolSpec(
        "crm_workflow_forms_definitions_flow_graph",
        "Flow graph nodes/edges for a definition.",
        "/api/v1/workflow-forms/definitions/{definition_id}/flow-graph",
        ("definition_id",),
        ("source",),
    ),
    ToolSpec(
        "crm_workflow_forms_submissions_list",
        "List workflow submissions.",
        "/api/v1/workflow-forms/submissions",
        (),
        ("page", "limit", "definition_id", "state_code"),
    ),
    ToolSpec(
        "crm_workflow_forms_submissions_get",
        "Workflow submission by id (includes lines/logs).",
        "/api/v1/workflow-forms/submissions/{submission_id}",
        ("submission_id",),
        (),
    ),
    ToolSpec(
        "crm_workflow_forms_submissions_allowed_transitions",
        "Allowed transitions for a submission for the act-as user.",
        "/api/v1/workflow-forms/submissions/{submission_id}/allowed-transitions",
        ("submission_id",),
        (),
    ),
    # --- sla-management ---
    ToolSpec(
        "crm_sla_policies_list",
        "List SLA policies.",
        "/api/v1/sla-management/sla-policies",
        (),
        ("page", "limit", "query", "status", "sort", "dir"),
    ),
    ToolSpec(
        "crm_sla_policies_get",
        "SLA policy by id.",
        "/api/v1/sla-management/sla-policies/{policy_id}",
        ("policy_id",),
        (),
    ),
    ToolSpec(
        "crm_sla_policies_tiers",
        "Tiers for a policy.",
        "/api/v1/sla-management/sla-policies/{policy_id}/tiers",
        ("policy_id",),
        (),
    ),
    ToolSpec(
        "crm_sla_conversation_tracking_dashboard",
        "SLA tracking dashboard metrics.",
        "/api/v1/sla-management/conversation-sla-tracking/dashboard",
        (),
        (),
    ),
    ToolSpec(
        "crm_sla_conversation_tracking_list",
        "List conversation SLA tracking rows.",
        "/api/v1/sla-management/conversation-sla-tracking",
        (),
        ("page", "limit", "policy_id", "query", "sort", "dir", "assigned_to"),
    ),
    ToolSpec(
        "crm_sla_conversation_event_logs_list",
        "SLA event logs with filters (tracking_id, event_type, dates, assignee).",
        "/api/v1/sla-management/conversation-sla-tracking/event-logs",
        (),
        (
            "page",
            "limit",
            "sort",
            "dir",
            "tracking_id",
            "event_type",
            "assigned_to",
            "assigned_to_id",
            "date_from",
            "date_to",
        ),
    ),
    ToolSpec(
        "crm_sla_conversation_tracking_get",
        "Single conversation SLA tracking record.",
        "/api/v1/sla-management/conversation-sla-tracking/{tracking_id}",
        ("tracking_id",),
        (),
    ),
    # --- form-submission tools (callable) ---
    ToolSpec(
        "crm_forms_stock_inquiries_submit",
        (
            "Submit a Stock Inquiry to the purchasing team. CALL ONLY AFTER all required "
            "fields are collected AND the user has explicitly confirmed (CONFIRM / OK / "
            "YES / CORRECT).\n"
            "The API enforces this: include `\"user_confirmed\": true` in payload_json only "
            "on the same turn as that explicit confirmation; otherwise the request is rejected.\n"
            "`payload_json` must be a JSON object with these fields:\n"
            "REQUIRED:\n"
            "  - user_confirmed (boolean, must be true)\n"
            "  - product_code (string, e.g. SRTW2048)\n"
            "  - item_description (string)\n"
            "  - quantity (string or number)\n"
            "  - delivery_date (string, DD/MM/YYYY)\n"
            "  - project_customer (string, end customer / company name)\n"
            "  - project_name (string)\n"
            "  - salesperson (string)\n"
            "OPTIONAL:\n"
            "  - remark (string)\n"
            "  - additional_remark (string)\n"
            "  - inquiry_number (string; set ONLY when resubmitting a rejected inquiry, "
            "otherwise omit)"
        ),
        "/api/v1/external/stock-inquiries/",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
    ),
    ToolSpec(
        "crm_forms_stock_inquiries_list",
        "List stock inquiries for current authenticated scope. Supports pagination and query.",
        "/api/v1/procurement/stock-inquiries",
        (),
        ("page", "limit", "query", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_stock_inquiries_get",
        "Get one stock inquiry by inquiry_id for view/update preparation.",
        "/api/v1/procurement/stock-inquiries/{inquiry_id}",
        ("inquiry_id",),
        (),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_purchase_requests_submit",
        (
            "Submit a Purchase Request OR Sponsorship Form. CALL ONLY AFTER all required "
            "header fields AND at least one complete product line are collected AND the "
            "user has explicitly confirmed (CONFIRM / OK / YES / CORRECT).\n"
            "The API enforces this: include `\"user_confirmed\": true` in payload_json only "
            "after that confirmation.\n"
            "First ask the user whether it is a PURCHASE REQUEST or SPONSORSHIP FORM; "
            "required fields differ.\n"
            "`payload_json` must be a JSON object with these fields:\n"
            "HEADER REQUIRED (both types):\n"
            "  - user_confirmed (boolean, must be true)\n"
            "  - request_type ('purchase_request' | 'sponsorship_form')\n"
            "  - customer_name (string)\n"
            "  - purpose (string, short reason)\n"
            "  - requested_by (string, user's own name)\n"
            "  - products (array; at least 1 item, see LINE FIELDS)\n"
            "HEADER REQUIRED for purchase_request:\n"
            "  - project_title (string)\n"
            "  - expected_delivery_date (string, DD/MM/YYYY)\n"
            "HEADER REQUIRED for sponsorship_form:\n"
            "  - sponsor_subject (string)\n"
            "  - date_of_delivery (string, DD/MM/YYYY)\n"
            "HEADER OPTIONAL:\n"
            "  - delivery_address, expected_po_date (string or free text), "
            "total_project_value, requested_at (DD/MM/YYYY, defaults to today), "
            "project_title (sponsorship only), purpose (free text)\n"
            "LINE FIELDS (each element of `products`):\n"
            "  - item_code (string, REQUIRED)\n"
            "  - quantity (string or number, REQUIRED)\n"
            "  - unit_price (optional; required for sponsorship_form grand-total)\n"
            "  - total (optional; auto = quantity * unit_price)\n"
            "  - remark (optional string)\n"
            "Include `request_number` ONLY when updating an existing rejected request."
        ),
        "/api/v1/external/purchase-requests/",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
    ),
    ToolSpec(
        "crm_forms_purchase_requests_list",
        "List purchase requests and sponsorship forms. Supports request_type, approval_status, query, and pagination.",
        "/api/v1/procurement/purchase-requests",
        (),
        ("page", "limit", "query", "request_type", "approval_status", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_purchase_requests_get",
        "Get one purchase request or sponsorship form by request_id.",
        "/api/v1/procurement/purchase-requests/{request_id}",
        ("request_id",),
        (),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_complaints_submit",
        (
            "Submit a product/delivery complaint against one or more delivery orders. "
            "CALL ONLY AFTER at least one delivery order number is known AND all required "
            "complaint fields are collected AND the user has explicitly confirmed "
            "(CONFIRM / OK / YES / CORRECT).\n"
            "The API enforces this: include `\"user_confirmed\": true` in payload_json only "
            "after that confirmation (required for API key / integration requests).\n"
            "PREREQUISITE: If the user has not given a delivery-order number yet, FIRST "
            "use the order-lookup tools to find matching DO(s) from customer name, "
            "product, and order-date range, present a numbered list, and have the "
            "user pick. DO NOT call this submit tool until at least one DO is "
            "selected.\n"
            "`payload_json` must be a JSON object with these fields:\n"
            "REQUIRED:\n"
            "  - user_confirmed (boolean, must be true)\n"
            "  - delivery_order_numbers (string, comma-separated DO numbers)\n"
            "  - date_of_complaint (string, DD/MM/YYYY)\n"
            "  - customer_name (string)\n"
            "  - contact_number (string, 8-15 digits after stripping symbols)\n"
            "  - product_code (string)\n"
            "  - quantity (string or number, positive)\n"
            "  - complaint_type (string, e.g. Broken/Damage, Leak, Missing parts)\n"
            "  - defect_description (string, free text)\n"
            "  - defect_discovered_when (DD/MM/YYYY or N/A)\n"
            "  - sales_person (string)\n"
            "  - address (string)\n"
            "  - customer_type (Dealer/Project/SMC/E-commerce/End User/Other)\n"
            "  - within_warranty (Yes/No/Not sure)\n"
            "  - product_type (string)\n"
            "  - contact_person (string)\n"
            "  - project_title (string)\n"
            "OPTIONAL:\n"
            "  - customer_type_other, contact_id, space_id, attachments\n"
            "After the complaint is submitted successfully, ask the user if they want to "
            "attach photos/videos; use `crm_forms_entity_attachments_link` for each file "
            "with entity_type='complaint' and entity_id set to the returned complaint id."
        ),
        "/api/v1/complaints-management/complaints/",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
    ),
    ToolSpec(
        "crm_forms_entity_attachments_link",
        "Create and link attachment to complaint, stock_inquiry, or purchase_request. Provide payload_json with entity_type, entity_id, and file fields.",
        "/api/v1/external/entity-attachments/",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
    ),
)
