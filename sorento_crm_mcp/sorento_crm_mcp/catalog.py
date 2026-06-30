"""Read-only GET endpoint catalog → MCP tools.

UUID-first contract: data tools filter by canonical UUID lists (`<entity>_ids`,
accepting csv / JSON array / repeated query params) plus structured filters
(price, dimensions, dates, status). Free-text fuzzy `query` search is intentionally
NOT exposed — callers (the n8n / RAG layer) resolve names → UUIDs upstream and pass
the UUIDs in.
"""
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
    module: str = ""  # Module key (e.g. "order"); empty for legacy unbound tools
    external: bool = False  # When true, the tool is registered by a custom handler
    # (not via the HTTP-backed _compile_tool template). Still appears in the
    # persisted `mcp_tools` catalog so admins can assign it to an AI assistant.
    internal: bool = False  # When true, skipped from FastMCP registration unless
    # MCP_EXPOSE_INTERNAL=1. Use for admin / back-office tools that should not
    # appear in the n8n agent's tool catalog.
    domain: str = ""  # Logical domain ("products", "orders", "procurement", ...).
    related_tools: tuple[str, ...] = ()  # Cross-references (surviving tools only).
    escalation_team: str = ""  # "sales" | "support" | "warehouse" | "procurement" | "".


# Paths match [sorento_crm_backend/app/api/v1/__init__.py](sorento_crm_backend/app/api/v1/__init__.py) prefixes.
CATALOG: tuple[ToolSpec, ...] = (
    # --- master-data ---
    ToolSpec(
        "crm_master_products_list",
        (
            "List structured product master rows (SKU / code / name / description / brand / category / "
            "price / dimensions) with filters and pagination. "
            "FILTER BY UUID: pass `product_ids` as csv / JSON list / repeated of canonical product UUIDs. "
            "`category_id` and `brand_id` are canonical UUIDs. "
            "PRICE: price_min, price_max (MYR). "
            "DIMENSIONS (millimetres): per-axis length_min/max, width_min/max, height_min/max; "
            "axis-agnostic any_dimension_min / any_dimension_max (match when ANY of L/W/H is in range). "
            "EXACT vs FUZZY: bare numbers are EXACT (min == max == value); apply ±5 mm only when the user "
            "hedges ('around', 'about', '~', 'approx'). "
            "SORT KEYS: created_at, updated_at, product_code, product_name, list_price (alias price), "
            "cost_price, invoice_price, is_active, dimensions_length (alias length), dimensions_width "
            "(alias width), dimensions_height (alias height), largest_dimension, smallest_dimension; "
            "combine with dir=asc|desc. Each row returns `currency` (default MYR) — render prices with that "
            "code, never $. Rows may include `field_attachments` (map of product field → linked docs). "
            "ATTACHMENTS: pass `attachment_type_ids` (canonical AttachmentType UUIDs, csv / JSON / repeated) "
            "to nest each product's files of those types under `attachments[]` (e.g. Product Photos, "
            "Technical Specifications). Omit it for a plain price/spec listing with NO attachments."
        ),
        "/api/v1/master-data/products",
        (),
        (
            "page", "limit", "product_ids", "status",
            "price_min", "price_max", "item_type",
            "length_min", "length_max", "width_min", "width_max",
            "height_min", "height_max", "any_dimension_min", "any_dimension_max",
            "attachment_type_ids",
            "sort", "dir",
        ),
        domain="products",
        related_tools=("crm_master_product_attachments_list", "crm_inventory_stock_balance_list"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_master_brands_list",
        (
            "List brands with pagination. FILTER BY UUID: `brand_ids` (canonical brand UUIDs) and / or "
            "`product_ids` (returns the brands of those products). Both accept csv / JSON list / repeated."
        ),
        "/api/v1/master-data/brands",
        (),
        ("page", "limit", "brand_ids", "product_ids"),
        domain="products",
    ),
    ToolSpec(
        "crm_master_product_categories_list",
        (
            "List product categories with pagination. FILTER BY UUID: `category_ids` (canonical category "
            "UUIDs) and / or `product_ids` (returns the categories of those products). csv / JSON / repeated."
        ),
        "/api/v1/master-data/product-categories",
        (),
        ("page", "limit", "category_ids", "product_ids"),
        domain="products",
    ),
    ToolSpec(
        "crm_master_units_of_measure_list",
        (
            "List units of measure with pagination. FILTER BY UUID: `uom_ids` (canonical UOM UUIDs) and / or "
            "`product_ids` (returns the base UOMs of those products). csv / JSON / repeated."
        ),
        "/api/v1/master-data/units-of-measure",
        (),
        ("page", "limit", "uom_ids", "product_ids"),
        domain="products",
    ),
    ToolSpec(
        "crm_master_product_attachments_list",
        (
            "List per-SKU product↔attachment links (BROCHURE / SPEC SHEET / DATASHEET / MANUAL / "
            "INSTALLATION GUIDE / CERTIFICATE for a specific product). FILTER BY UUID: `product_ids` "
            "(canonical product UUIDs), `attachment_ids` (canonical attachment UUIDs), and / or "
            "`attachment_type_ids` (canonical AttachmentType UUIDs — narrows to a doc class such as "
            "brochure or spec sheet). All three accept csv / JSON list / repeated query params."
        ),
        "/api/v1/master-data/product-attachments",
        (),
        ("page", "limit", "sort", "dir", "product_ids", "attachment_ids", "attachment_type_ids"),
        domain="products",
        related_tools=("crm_master_products_list",),
        escalation_team="sales",
    ),
    # --- lookup sets ---
    ToolSpec(
        "crm_lookup_resolve",
        (
            "Resolve a raw user keyword into the canonical option value for a CRM dropdown set. "
            "Body: {set_key, raw, locale?}. Returns {value,label,matched_keyword,match_type,score} or 404. "
            "Use whenever a user gives a free-text value for a CRM dropdown field — translate first, then "
            "send the canonical value to the matching write API."
        ),
        "/api/v1/lookup/resolve",
        method="POST",
        body_params=("set_key", "raw", "locale"),
        module="master_data",
    ),
    # --- marketing ---
    ToolSpec(
        "crm_marketing_promotions_list",
        (
            "List promotions (summary fields + linked attachments inline; no product lines). Each row carries "
            "its `attachments` array. Default returns ACTIVE promotions (is_active=true AND today within "
            "start/end); when a narrowing filter yields zero active matches it falls back to INACTIVE and sets "
            "fallback_used=true. Every row carries `is_expired` (true = not currently live: flag off or today "
            "outside start/end) — when true, tell the user the promotion was FOUND but is EXPIRED; never "
            "present an is_expired row as live. Pass active=false when the user explicitly asks for "
            "inactive / expired / historical promotions. period_from / period_to (YYYY-MM-DD) "
            "scope by date; `date_mode` picks which promotion date the window tests:\n"
            "  • `overlap` (default) — promo active any time during window ('valid/running during X')\n"
            "  • `started` — start_date within window ('released/launched/new in last X days')\n"
            "  • `ended` — end_date within window ('ended/expired in X')\n"
            "  started/ended automatically include BOTH active and historical rows (no active gate); "
            "do not pass `active` with them unless the user explicitly narrows to one state.\n\n"
            "OPTIONAL narrowing filters (call without any to get the latest 10 active promotions):\n"
            "  • `promotion_ids` (canonical promotion UUIDs, csv / JSON / repeated)\n"
            "  • `product_ids` (canonical product UUIDs — promotions containing any)\n"
            "  When BOTH `promotion_ids` and `product_ids` are supplied, they combine\n"
            "  via OR: a promotion is returned if it is in `promotion_ids` OR contains\n"
            "  any product in `product_ids` (no AND option).\n\n"
            "Unfiltered MCP calls are auto-capped to limit=10 newest-first so open questions like "
            "\"what is sorento's latest promo\" return a bounded page instead of the full catalog.\n\n"
            "ACCESS LEVELS: `access_levels` filters promotions whose `access_levels` JSONB overlaps the "
            "supplied names (case-insensitive). Phrases like `sorento dealer`, `mocha office`, `end user` "
            "are `access_levels` ONLY — never `*_ids` values."
        ),
        "/api/v1/marketing/promotions",
        (),
        ("page", "limit", "promotion_ids", "product_ids", "active", "period_from", "period_to", "date_mode", "sort", "dir", "access_levels"),
        domain="promotions",
        related_tools=("crm_marketing_promotion_products_list", "crm_marketing_promotion_attachments_list"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotion_products_list",
        (
            "Promotion product lines (paginated). Each row carries the parent promotion's "
            "`promotion_attachments` inline, plus `is_expired` — true when the parent promotion "
            "is NOT currently live (is_active off OR today outside its start/end window). When "
            "is_expired is true, tell the user the line was FOUND but its promotion is EXPIRED; "
            "never present an is_expired row as a live promotion.\n\n"
            "REQUIRED — at least ONE narrowing filter or the tool returns an empty page:\n"
            "  • `promotion_ids` (canonical promotion UUIDs)\n"
            "  • `product_ids` (canonical product UUIDs)\n\n"
            "STRUCTURED FILTERS: PRICE price_min/max (MYR); DIMENSIONS (mm) length_min/max, width_min/max, "
            "height_min/max; axis-agnostic any_dimension_min/max; item_type; status=active|inactive|all. "
            "EXACT vs FUZZY: bare number is EXACT (min == max == value); hedge words apply ±5 mm. "
            "ACCESS LEVELS: `access_levels` filters by parent promotion access overlap.\n\n"
            "PARENT-PROMOTION ACTIVITY (`active`, NOT product status): default returns lines whose "
            "promotion is currently active, falling back to inactive-promotion lines (fallback_used=true) "
            "when a narrowing filter yields zero active matches — same active-first behavior as "
            "crm_marketing_promotions_list. Pass active=false for inactive / expired / historical "
            "promotion lines only."
        ),
        "/api/v1/marketing/promotion-products",
        (),
        (
            "page", "limit", "sort", "dir",
            "promotion_ids", "product_ids",
            "item_type", "status", "active",
            "price_min", "price_max",
            "length_min", "length_max",
            "width_min", "width_max",
            "height_min", "height_max",
            "any_dimension_min", "any_dimension_max",
            "access_levels",
        ),
        domain="promotions",
        related_tools=("crm_marketing_promotions_list",),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_list",
        (
            "List / filter promotion-attachment links (BROCHURE / FLYER documents). Each row carries "
            "`is_expired` — true when the parent promotion is NOT currently live (is_active off OR today "
            "outside its start/end window). When is_expired is true, tell the user the document was FOUND but "
            "its promotion is EXPIRED; never present an is_expired row as a live promotion.\n\n"
            "REQUIRED — at least ONE narrowing filter or the tool returns an empty page:\n"
            "  • `promotion_ids` (canonical promotion UUIDs)\n"
            "  • `attachment_ids` (canonical attachment UUIDs)\n\n"
            "ACCESS LEVELS: `access_levels` filters by parent promotion access overlap. Pass a single name "
            "(e.g. \"Sorento Dealer\") or a JSON array. Phrases like `sorento dealer`, `mocha office`, "
            "`end user` are `access_levels` ONLY — never `*_ids` values.\n\n"
            "PARENT-PROMOTION ACTIVITY (`active`): default returns attachments whose promotion is currently "
            "active, falling back to inactive-promotion attachments (fallback_used=true) when a narrowing "
            "filter yields zero active matches — same active-first behavior as crm_marketing_promotions_list. "
            "Pass active=false for inactive / expired / historical promotion attachments only."
        ),
        "/api/v1/marketing/promotion-attachments",
        (),
        ("page", "limit", "sort", "dir", "promotion_ids", "attachment_ids", "access_levels", "active"),
        domain="promotions",
        related_tools=("crm_marketing_promotions_list",),
        escalation_team="sales",
    ),
    # --- resource-management ---
    ToolSpec(
        "crm_resource_attachments_list",
        (
            "List file attachments in the global document library. PRIMARY TOOL for PRODUCT CATALOGUE / "
            "CATALOG / MASTER CATALOGUE PDF / COMPANY BROCHURE / PRICE LIST DOCUMENT requests; for per-SKU "
            "brochures use crm_master_product_attachments_list; for the standing Stock List PDF use "
            "crm_resource_attachments_current_stock_list.\n\n"
            "FILTER BY UUID: `attachment_ids` (canonical attachment UUIDs csv / JSON / repeated), "
            "`directory_id`, `attachment_type_id`, `uploaded_by` (all canonical UUIDs). "
            "Set resolve_signed_urls=true to include signed preview/download URLs in the response."
        ),
        "/api/v1/resource-management/attachments",
        (),
        (
            "page", "limit", "attachment_ids", "sort", "dir",
            "directory_id", "attachment_type_id", "uploaded_by",
            "uploaded_at_from", "uploaded_at_to", "is_deleted", "resolve_signed_urls",
        ),
        domain="resources",
        related_tools=("crm_resource_attachments_current_stock_list",),
        escalation_team="support",
    ),
    ToolSpec(
        "crm_resource_attachments_catalogue",
        (
            "DOMAIN: catalogue. Narrow attachment lookup pre-filtered to "
            "AttachmentType=catalogue (Sorento product catalogue PDFs / catalog "
            "documents only). Use when the n8n flow has already resolved one or "
            "more catalogue attachment UUIDs and needs metadata / signed URLs "
            "for them.\n\n"
            "REQUIRED — `attachment_ids` (canonical attachment UUIDs csv / JSON "
            "/ repeated) MUST be supplied or the tool returns an empty page. "
            "This tool does NOT browse the catalogue library; it resolves a "
            "known set of UUIDs scoped to the catalogue type.\n\n"
            "Set resolve_signed_urls=true to include signed preview/download "
            "URLs in the response. Backend hard-filters by "
            "attachment_type_code=catalogue server-side, so non-catalogue UUIDs "
            "passed in `attachment_ids` are excluded automatically."
        ),
        "/api/v1/resource-management/attachments",
        (),
        (
            "page", "limit", "attachment_ids", "sort", "dir",
            "uploaded_at_from", "uploaded_at_to", "resolve_signed_urls",
        ),
        domain="resources",
        related_tools=("crm_resource_attachments_list",),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_resource_attachments_current_stock_list",
        "Latest Stock List attachment row (singleton) if configured, with a signed download URL.",
        "/api/v1/resource-management/attachments/current-stock-list",
        (),
        (),
        domain="resources",
    ),
    # --- inventory ---
    ToolSpec(
        "crm_inventory_stock_balance_list",
        (
            "Paged active-warehouse stock balances. Exposes quantity_on_hand and Malaysia-time updated_at "
            "only. Response uses Sage-aligned warehouse vocabulary: `system_location` (was warehouse_code), "
            "`system_location_description` (was warehouse_name), `warehouse` (was location).\n\n"
            "ALL FILTERS OPTIONAL — call with none to span every product + active warehouse.\n"
            "FILTER BY UUID: `product_ids` (canonical product UUIDs csv / JSON / repeated); "
            "`warehouse_ids` (canonical warehouse UUIDs csv / JSON / repeated). "
            "quantity_operator / quantity_value filter on-hand; status = critical|low|normal|overstock.\n"
            "Rows whose on-hand is 0 ONLY because the latest stock movement was a SYSTEM_ADJUSTMENT "
            "(e.g. 'missing from full stock take') are always hidden; a genuine 0 is still returned."
        ),
        "/api/v1/inventory/stock/balance",
        (),
        ("page", "limit", "product_ids", "sort", "dir", "warehouse_ids", "quantity_operator", "quantity_value", "status"),
        domain="inventory",
        related_tools=("crm_inventory_warehouses_list",),
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_inventory_warehouses_list",
        (
            "List warehouses. Response uses Sage-aligned vocabulary: `system_location` (was warehouse_code), "
            "`system_location_description` (was warehouse_name), `warehouse` (was location). "
            "FILTER BY UUID: `warehouse_ids` (canonical warehouse UUIDs csv / JSON / repeated). "
            "is_active=true for active-only."
        ),
        "/api/v1/inventory/warehouses",
        (),
        ("page", "limit", "warehouse_ids", "is_active"),
        domain="inventory",
        escalation_team="warehouse",
    ),
    # --- order-management ---
    ToolSpec(
        "crm_order_management_orders_list",
        (
            "List orders. Response uses `pickup_time` (was delivery_time); `order_status` is a plain string. "
            "Rows carry NO UUIDs — identify orders by `order_number`. "
            "External/AI callers are HARD-CAPPED at limit=20 server-side — narrow via UUID + date filters "
            "and paginate via `page` when more results are needed.\n\n"
            "FILTER BY UUID (typed canonical UUIDs, csv / JSON / repeated):\n"
            "  • `order_ids` — specific orders\n"
            "  • `customer_ids` — customers (Order.customer_id, falls back to debtor_name for legacy rows)\n"
            "  • `product_ids` — orders containing any of these products\n"
            "  • `transporter_ids` — transporters (Order.transporter_id, text fallback for legacy rows)\n"
            "Date window: actual_delivery_date_from / actual_delivery_date_to."
        ),
        "/api/v1/order-management/orders",
        (),
        (
            "page", "limit", "order_ids", "customer_ids", "product_ids", "transporter_ids",
            "actual_delivery_date_from", "actual_delivery_date_to", "sort", "dir",
        ),
        domain="orders",
        related_tools=("crm_order_management_orders_by_product_list",),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_order_management_orders_by_product_list",
        (
            "List distinct CUSTOMER SALES orders containing a specific product (outgoing / sold, NOT incoming "
            "stock). A product narrower is REQUIRED — pass `product_ids` (canonical product UUIDs, csv / JSON "
            "/ repeated) or the tool returns an empty page.\n\n"
            "External/AI callers are HARD-CAPPED at limit=20 server-side — narrow via UUID + date filters "
            "and paginate via `page` when more results are needed.\n\n"
            "OPTIONAL UUID FILTERS: `customer_ids`, `transporter_ids` (canonical UUIDs). "
            "Date window: actual_delivery_date_from / actual_delivery_date_to (YYYY-MM-DD). "
            "For 'any incoming for product X' use crm_incoming_stock_by_product instead."
        ),
        "/api/v1/order-management/orders/by-product",
        (),
        (
            "page", "limit", "product_ids", "customer_ids", "transporter_ids",
            "actual_delivery_date_from", "actual_delivery_date_to", "sort", "dir",
        ),
        domain="orders",
        related_tools=("crm_order_management_orders_list", "crm_incoming_stock_by_product"),
        escalation_team="sales",
    ),
    # --- incoming-stock ---
    ToolSpec(
        "crm_incoming_stock_by_product",
        (
            "ONE-SHOT tool for any 'incoming for product X' / 'is SKU X arriving?' / 'how much is pending?' / "
            "'where will this product be stocked?' question. Returns: total_remaining_incoming_quantity; "
            "warehouse_allocation_summary (per warehouse: warehouse_code, warehouse_name, allocated_quantity); "
            "per-shipment breakdown (shipment_number, container, ETA, batch_number, remaining qty, packing-list "
            "attachment, warehouse_allocations); nearest_estimated_arrival_date. Does NOT expose received "
            "quantities, SPO numbers, or internal IDs. FILTER BY UUID: `product_ids` (canonical product UUIDs).\n\n"
            "OPTIONAL ETA WINDOW: `eta_from` / `eta_to` (YYYY-MM-DD, inclusive) narrow to shipments arriving "
            "within the window — e.g. 'is SKU X arriving before month end?'. Applied on top of the product "
            "filter (a product hint is still required); never a standalone filter."
        ),
        "/api/v1/incoming-stock/by-product",
        (),
        ("product_ids", "eta_from", "eta_to", "limit"),
        domain="incoming_stock",
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_incoming_stock_shipments",
        (
            "SHIPMENT-CENTRIC incoming list: 'any incoming shipments this month?' / 'what is arriving with ETA "
            "on date X?' / 'open shipments from supplier Y'. Returns shipment headers (shipment_number, "
            "container, ETA, total_remaining_incoming_quantity, distinct_products_incoming, packing-list "
            "attachment).\n\n"
            "REQUIRED — at least ONE narrowing filter or the tool returns an empty page:\n"
            "  • `shipment_ids` (canonical inbound-shipment UUIDs)\n"
            "  • `supplier_ids` (canonical supplier UUIDs)\n"
            "  • `eta_from` / `eta_to` (ETA window, YYYY-MM-DD)\n\n"
            "For 'incoming for product X' use crm_incoming_stock_by_product instead — do NOT call this tool "
            "without a narrower just to enumerate every open shipment."
        ),
        "/api/v1/incoming-stock/shipments",
        (),
        ("shipment_ids", "supplier_ids", "eta_from", "eta_to", "page", "limit"),
        domain="incoming_stock",
        related_tools=("crm_incoming_stock_by_product",),
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_incoming_stock_list",
        (
            "UNIFIED incoming-stock list — shipment-rooted with nested product lines. Covers BOTH "
            "'any incoming for product X / SKU X?' (pass `product_ids`) AND 'what is arriving this "
            "month / from supplier Y / shipment Z?' (pass `eta_from`/`eta_to`, `supplier_ids`, "
            "`shipment_ids`). Returns one row per still-incoming shipment: "
            "shipment_number, shipping_container_number, estimated_arrival_date, packing-list "
            "attachment, and a `lines[]` array — each line carries product_code, product_name, "
            "batch_number, remaining_incoming_quantity, and warehouse_allocations (warehouse_code, "
            "warehouse_name, allocated_quantity). When `product_ids` is given, lines are filtered to "
            "those products. NO aggregate totals are returned — sum the line quantities yourself for "
            "a product total or per-warehouse summary. Never exposes received/rejected quantities, "
            "SPO numbers, or internal IDs. REQUIRED: at least ONE narrowing filter (product_ids / "
            "shipment_ids / supplier_ids / eta_from / eta_to) or the tool returns an empty page."
        ),
        "/api/v1/incoming-stock/list",
        (),
        (
            "product_ids", "shipment_ids", "supplier_ids",
            "eta_from", "eta_to", "page", "limit",
        ),
        domain="incoming_stock",
        related_tools=("crm_incoming_stock_by_product", "crm_incoming_stock_shipments"),
        escalation_team="warehouse",
    ),
    # --- forms ---
    ToolSpec(
        "crm_forms_management_forms_list",
        (
            "List forms (newest-first by updated_at when sort omitted). Caller-supplied "
            "`limit` is respected verbatim (server max 100). OPTIONAL narrowing filter:\n"
            "  • `form_ids` (canonical form UUIDs csv / JSON / repeated)\n\n"
            "Without `form_ids`, returns the page as requested — use page + limit to paginate."
        ),
        "/api/v1/forms-management/forms",
        (),
        ("page", "limit", "form_ids", "sort", "dir"),
        domain="forms",
        escalation_team="support",
    ),
    # --- sla-management (conversation tracking) ---
    ToolSpec(
        "crm_sla_conversation_tracking_dashboard",
        "SLA conversation-tracking dashboard metrics.",
        "/api/v1/sla-management/conversation-sla-tracking/dashboard",
        (),
        (),
        domain="sla",
    ),
    ToolSpec(
        "crm_sla_conversation_tracking_list",
        (
            "List conversation SLA tracking rows. FILTER BY UUID: `tracking_ids` (canonical SLA tracking "
            "UUIDs csv / JSON / repeated), `policy_id` (canonical UUID). assigned_to accepts a user UUID or "
            "respond_user_id."
        ),
        "/api/v1/sla-management/conversation-sla-tracking",
        (),
        ("page", "limit", "tracking_ids", "policy_id", "sort", "dir", "assigned_to"),
        domain="sla",
    ),
    ToolSpec(
        "crm_sla_conversation_event_logs_list",
        (
            "SLA conversation event logs. FILTER BY UUID: `tracking_id`, `assigned_to_id` (canonical UUIDs). "
            "event_type, assigned_to, date_from / date_to scope the logs."
        ),
        "/api/v1/sla-management/conversation-sla-tracking/event-logs",
        (),
        (
            "page", "limit", "sort", "dir",
            "tracking_id", "event_type", "assigned_to", "assigned_to_id",
            "date_from", "date_to",
        ),
        domain="sla",
    ),
    # --- system capabilities ---
    ToolSpec(
        "crm_system_tool_capabilities_summary",
        (
            "Dynamic summary of everything this MCP can do right now, grouped into general enquiries vs form "
            "submissions. Use for 'what can you do?' / 'what features do you support?'. Live (derived from the "
            "current tool catalog + intents). Optional `include_tools` (true/false) returns full tool lists."
        ),
        "/api/v1/system/tool-capabilities/summary",
        (),
        ("include_tools",),
    ),
    # --- portal handoff ---
    ToolSpec(
        "crm_portal_link_get",
        (
            "Mint a 7-day user submission portal link for the active contact. Use when the user wants to file "
            "a complaint, stock inquiry, purchase request or sponsorship form. Send the returned `portal_url`. "
            "Required: `contact_id` (string) and `space_id` (string). Optional: `submission_type` "
            "(PREFERRED: complaint | stock_inquiry | purchase_request | sponsorship_form — opens the portal "
            "directly on that tab) and `base_url` (host override)."
        ),
        "/api/v1/external/portal-tokens/",
        (),
        (),
        method="POST",
        body_params=("contact_id", "space_id", "submission_type", "base_url"),
    ),
    # --- commercial: customers (debtor aggregation) ---
    ToolSpec(
        "crm_master_customers_list",
        (
            "List / search distinct customers, deduplicated by debtor_name aggregated from the orders table "
            "(the customers master table is not used by the business — real customer identity lives on "
            "orders.debtor_name / debtor_code). Each row returns debtor_name, debtor_code, order_count. "
            "FILTER BY UUID: `customer_ids` (canonical customer UUIDs, csv / JSON / repeated) filters the "
            "source orders by Order.customer_id before aggregation. External AI/MCP callers are HARD-CAPPED "
            "at limit=20 server-side. Sort: debtor_name | debtor_code | order_count."
        ),
        "/api/v1/order-management/orders/debtors",
        (),
        ("page", "limit", "customer_ids", "sort", "dir"),
    ),
    # ===== User-guides (Outline-backed how-to retrieval) =====
    ToolSpec(
        "user_guides_read",
        (
            "Single-call how-to tool. Pass the user's natural-language question as `query` (e.g. 'How do I "
            "upload a packing list?'); searches the Sorento CRM Outline collection and returns the full "
            "markdown body of the best-matching guide in one round trip. Use for 'how do I…?', 'how to…?', "
            "'where do I find…?', 'what's the process for…?', 'steps to…?' about CRM features. Quote the "
            "returned steps verbatim and preserve inline markdown links. If the caller has an Outline doc id "
            "(UUID) or url-id, pass it as `query` to fetch the body directly."
        ),
        "/outline/documents.info",  # synthetic; not hit over HTTP
        (),
        ("query",),
        method="POST",
        module="user_guides",
        external=True,
    ),
    # ===== IT Support intake =====
    ToolSpec(
        "crm_it_support_ticket_create",
        (
            "Submit an IT-support ticket / report a bug / log an issue with the IT admin team. "
            "INVOCATION RULES: 1. NEVER ask the user for anything — infer all fields from the recent 1-5 "
            "turns. 2. CALL ONCE with payload_json = {title, priority (low|medium|high|urgent), category "
            "(bug|feature|question|other), description}. Server creates a DRAFT and returns draft_url. "
            "Optionally pass `message_id` (Respond.io message id) at the TOP LEVEL of the tool arguments — "
            "NOT inside payload_json; omit if unknown. 3. Reply with ONE short message containing the "
            "draft_url verbatim. 4. STOP — do not call again in the same turn. "
            "USE when the user reports something broken / not working / errored / crashed / slow / can't "
            "access / login fails / data missing, OR asks to file / raise a ticket / report a problem. "
            "DO NOT use for how-to questions — those belong to user_guides_read."
        ),
        "/api/v1/external/it-support/tickets/",
        (),
        (),
        method="POST",
        body_params=("payload_json", "message_id"),
        module="tickets",
    ),
)
