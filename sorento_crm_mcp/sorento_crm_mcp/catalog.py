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
    module: str = ""  # Module key (e.g. "order"); empty for legacy unbound tools
    external: bool = False  # When true, the tool is registered by a custom handler
    # (not via the HTTP-backed _compile_tool template). Still appears in the
    # persisted `mcp_tools` catalog so admins can assign it to an AI assistant.
    internal: bool = False  # When true, skipped from FastMCP registration unless
    # MCP_EXPOSE_INTERNAL=1. Use for admin / back-office tools that should not
    # appear in the n8n agent's tool catalog.
    domain: str = ""  # Logical domain ("products", "orders", "procurement", ...).
    # Used by crm_list_domains and the n8n RAG layer to filter retrieval by domain.
    related_tools: tuple[str, ...] = ()  # Hand-curated cross-references emitted by
    # crm_describe_tool so the agent can pivot between related list/get/by-product tools.
    escalation_team: str = ""  # When the response is non-ok (needs_clarification,
    # not_found, error), the envelope advertises this team as escalation target.
    # Allowed: "sales" | "support" | "warehouse" | "procurement" | "".


# Paths match [sorento_crm_backend/app/api/v1/__init__.py](sorento_crm_backend/app/api/v1/__init__.py) prefixes.
# Comment to rebuild
CATALOG: tuple[ToolSpec, ...] = (
    # --- master-data ---
    ToolSpec(
        "crm_master_products_list",
        (
            "List structured product master rows (SKU / code / name / description / brand / category / "
            "price / dimensions) with filters and pagination. NOT for document/PDF requests: if the "
            "user asks for the product CATALOGUE, CATALOG, MASTER CATALOGUE, COMPANY BROCHURE, or "
            "PRICE LIST PDF, route to crm_resource_attachments_list instead; for per-SKU brochure / "
            "datasheet / spec sheet of a named product, use crm_master_product_attachments_by_product. "
            "FILTER BY UUID: pass `product_ids` as csv / JSON list of canonical product UUIDs. "
            "Resolve free-text refs (codes, names, descriptions) FIRST via `crm_find_entity`, then "
            "pass the returned UUIDs here. `category_id` and `brand_id` are canonical UUIDs. "
            "PRICE: price_min, price_max (MYR). "
            "DIMENSIONS (all in millimetres): per-axis length_min/length_max, width_min/width_max, "
            "height_min/height_max. For axis-agnostic 'any side > X' queries (e.g. 'products with dimensions "
            "over 300mm'), use any_dimension_min / any_dimension_max — these match when ANY of L/W/H falls "
            "in range. These are FILTERS only — NOT valid `sort` values. "
            "EXACT vs FUZZY: bare numbers ('365', 'L600', '460×330×140') are EXACT — set min == max == value, "
            "do NOT widen the range. Apply ±5 mm tolerance ONLY when the user hedges with words like "
            "'around', 'about', '~', 'approx', 'roughly', 'near'. "
            "SORT KEYS for `sort=`: created_at, updated_at, product_code, product_name, list_price (alias: "
            "price), cost_price, invoice_price, is_active, dimensions_length (alias: length), "
            "dimensions_width (alias: width), dimensions_height (alias: height), largest_dimension "
            "(GREATEST of L/W/H — use for 'biggest product on any side'), smallest_dimension. "
            "Combine with dir=asc|desc. NULL dimensions sort to the bottom either way. "
            "Each row also returns `currency` (default MYR) — render prices using that code, never $. "
            "Each row may include `field_attachments` — a map of product field name (e.g. `weight`, "
            "`dimensions_length`) to an array of linked docs ({id, original_filename, file_path, "
            "mime_type, attachment_type}). When the user asks about a value that has linked docs, "
            "answer from the value AND surface the doc in one go instead of fetching "
            "`crm_master_product_attachments_*` separately."
        ),
        "/api/v1/master-data/products",
        (),
        (
            "page",
            "limit",
            "product_ids",
            "status",
            "price_min",
            "price_max",
            "item_type",
            "length_min",
            "length_max",
            "width_min",
            "width_max",
            "height_min",
            "height_max",
            "any_dimension_min",
            "any_dimension_max",
            "sort",
            "dir",
        ),
        domain="products",
        related_tools=("crm_master_products_get", "crm_master_product_attachments_by_product", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_master_products_get",
        (
            "Get one product by canonical UUID. Pass the product's UUID as `product_id` path "
            "param. Resolve free-text product refs FIRST via `crm_find_entity`. Response may "
            "include `field_attachments` — a map of product field name (e.g. `weight`, "
            "`dimensions_length`) to an array of linked docs."
        ),
        "/api/v1/master-data/products/{product_id}",
        ("product_id",),
        (),
        domain="products",
        related_tools=("crm_master_products_list", "crm_find_entity"),
        escalation_team="sales",
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
        (
            "List per-SKU product↔attachment links. Use for documents tied to a SPECIFIC product "
            "(named SKU + document): BROCHURE, SPEC SHEET, DATASHEET, PRODUCT MANUAL, "
            "INSTALLATION GUIDE, CERTIFICATE.\n\n"
            "FILTER BY UUID: pass `product_ids` (canonical product UUIDs) and / or "
            "`attachment_ids` (canonical attachment UUIDs). Resolve free-text refs FIRST via "
            "`crm_find_entity`."
        ),
        "/api/v1/master-data/product-attachments",
        (),
        ("page", "limit", "sort", "dir", "product_ids", "attachment_ids"),
        domain="products",
        related_tools=("crm_master_product_attachments_by_product", "crm_master_products_list", "crm_find_entity"),
        escalation_team="sales",
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
        (
            "All attachment links for ONE product by canonical UUID. Use for BROCHURE / SPEC "
            "SHEET / DATASHEET / PRODUCT MANUAL / INSTALLATION GUIDE / CERTIFICATE questions "
            "about a named SKU. Resolve the product reference FIRST via `crm_find_entity`, then "
            "pass its UUID as `product_id` path param."
        ),
        "/api/v1/master-data/product-attachments/product/{product_id}",
        ("product_id",),
        (),
        domain="products",
        related_tools=("crm_master_product_attachments_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    # --- lookup sets ---
    ToolSpec(
        "crm_lookup_options",
        "List active options + keywords for a dropdown configured in CRM. "
        "Use this to learn the canonical values and synonyms before sending a write. "
        "Returns [{value,label,keywords:[..],is_active}].",
        "/api/v1/lookup/{set_key}/options",
        path_params=("set_key",),
        query_params=("include_inactive",),
        module="master_data",
    ),
    ToolSpec(
        "crm_lookup_resolve",
        "Resolve a raw user keyword into the canonical option value for a set. "
        "Body: {set_key, raw, locale?}. Returns {value,label,matched_keyword,match_type,score} or 404. "
        "Use this whenever a user gives a free-text value for a CRM dropdown field — translate first, "
        "then send the canonical value to the matching write API.",
        "/api/v1/lookup/resolve",
        method="POST",
        body_params=("set_key", "raw", "locale"),
        module="master_data",
    ),
    # --- marketing ---
    ToolSpec(
        "crm_marketing_promotions_list",
        (
            "List promotions (summary fields + linked attachments inline; no product lines). "
            "Each row already carries its `attachments` array — no second tool call needed for "
            "promotion documents. Default returns ACTIVE promotions (is_active=true AND today "
            "within start_date/end_date); when a narrowing filter yields zero active matches, "
            "falls back to INACTIVE matches automatically and sets fallback_used=true on the "
            "response. Pass active=false to fetch historical-only (no fallback). Use period_from "
            "/ period_to (YYYY-MM-DD) to scope by overlap with the promotion's [start_date, "
            "end_date] window. For product lines use crm_marketing_promotion_products_list.\n\n"
            "REQUIRED — at least ONE of these narrowing filters must be supplied or the tool "
            "returns an empty page:\n"
            "  • `promotion_ids` (canonical promotion UUIDs, csv / JSON list / repeated)\n"
            "  • `product_ids` (canonical product UUIDs — narrows to promotions containing any)\n"
            "  • `query` (free-text across promotion name / description / metadata)\n"
            "Resolve free-text refs (promotion name, product reference) FIRST via "
            "`crm_find_entity`, then pass returned UUIDs here. If `crm_find_entity` returns no "
            "promotion / product candidates, do NOT call with empty `*_ids` — report 'no "
            "matching promotion' instead.\n\n"
            "ACCESS LEVELS: `access_levels` filters promotions to those whose `access_levels` "
            "JSONB overlaps the supplied names. Names match the active contact-access-type catalog "
            "(case-insensitive). `access_levels` is NOT a narrowing filter on its own — it must "
            "accompany a `*_ids` / `query` filter.\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO ANY OTHER PARAM. Phrases like `sorento "
            "dealer`, `mocha office`, `end user` are `access_levels` only."
        ),
        "/api/v1/marketing/promotions",
        (),
        ("page", "limit", "promotion_ids", "product_ids", "active", "period_from", "period_to", "sort", "dir", "access_levels"),
        domain="promotions",
        related_tools=("crm_marketing_promotions_get", "crm_marketing_promotion_products_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotions_get",
        (
            "Get one promotion by canonical UUID: metadata, groups (FOC tiers), AND linked "
            "attachments inline. No second tool call needed for attachments — they come back on "
            "the same response. Does NOT include product lines by default; set include_products=true "
            "only if you need nested SKU lines.\n\n"
            "Pass the promotion's UUID as `promotion_id` path param. Resolve free-text refs FIRST "
            "via `crm_find_entity`.\n\n"
            "ACCESS LEVELS: `access_levels` filters to a promotion whose `access_levels` JSONB "
            "overlaps the supplied names. Omit to skip the filter."
        ),
        "/api/v1/marketing/promotions/{promotion_id}",
        ("promotion_id",),
        ("access_levels",),
        domain="promotions",
        related_tools=("crm_marketing_promotions_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotion_products_nested",
        (
            "Products linked to a promotion (nested under promotion). Each row also carries the "
            "parent promotion's `promotion_attachments` inline — no second call needed to fetch the "
            "promotion document.\n\n"
            "FILTER BY UUID: pass `promotion_ids` and / or `product_ids` (canonical UUIDs csv/"
            "JSON/repeated). Resolve free-text refs FIRST via `crm_find_entity`.\n\n"
            "ACCESS LEVELS: `access_levels` filters promotions to those whose `access_levels` "
            "JSONB overlaps the supplied names. Omit to skip the filter."
        ),
        "/api/v1/marketing/promotion-products",
        (),
        ("promotion_ids", "product_ids", "page", "limit", "access_levels"),
        domain="promotions",
        related_tools=("crm_marketing_promotion_products_list", "crm_marketing_promotions_get", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotion_products_list",
        (
            "Promotion product lines (paginated). Each row carries the parent promotion's "
            "`promotion_attachments` inline — no second call needed for the promotion document.\n\n"
            "FILTER BY UUID: pass `promotion_ids` and / or `product_ids` (canonical UUIDs csv/"
            "JSON/repeated). Resolve free-text refs FIRST via `crm_find_entity`.\n\n"
            "STRUCTURED FILTERS for product attributes:\n"
            "  • PRICE: price_min, price_max (MYR)\n"
            "  • DIMENSIONS (mm): per-axis length_min/max, width_min/max, height_min/max\n"
            "  • AXIS-AGNOSTIC: any_dimension_min / any_dimension_max — matches when ANY of L/W/H "
            "is in range. Use when the user doesn't say which axis.\n"
            "  • item_type, status=active|inactive|all\n\n"
            "EXACT vs FUZZY: bare number ('365', 'L600', '460×330×140') is EXACT — set "
            "min == max == value. Hedge words ('around', 'about', 'approx') apply ±5 mm tolerance.\n\n"
            "ACCESS LEVELS: `access_levels` filters to product lines under promotions whose "
            "`access_levels` JSONB overlaps the supplied names. Omit to skip the filter."
        ),
        "/api/v1/marketing/promotion-products",
        (),
        (
            "page", "limit", "sort", "dir",
            "promotion_ids", "product_ids",
            "item_type", "status",
            "price_min", "price_max",
            "length_min", "length_max",
            "width_min", "width_max",
            "height_min", "height_max",
            "any_dimension_min", "any_dimension_max",
            "access_levels",
        ),
        domain="promotions",
        related_tools=("crm_marketing_promotion_products_nested", "crm_marketing_promotions_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_list",
        (
            "List / search promotion-attachment links. Use for any BROCHURE / FLYER document.\n\n"
            "REQUIRED — at least ONE of these narrowing filters must be supplied or the tool "
            "returns an empty page:\n"
            "  • `promotion_ids` (canonical promotion UUIDs, csv / JSON list / repeated)\n"
            "  • `attachment_ids` (canonical attachment UUIDs)\n"
            "  • `query` (free-text across promotion / attachment metadata)\n"
            "Resolve free-text refs (promotion name, attachment filename, product reference) "
            "FIRST via `crm_find_entity`, then pass returned UUIDs here.\n\n"
            "ACCESS LEVELS: `access_levels` filters to links under promotions whose "
            "`access_levels` JSONB overlaps the supplied names. Omit to skip the filter. Pass as a "
            "single name (e.g. `\"Sorento Dealer\"`) or JSON array of names (e.g. `[\"Sorento "
            "Dealer\",\"Mocha Office\"]`).\n\n"
            "CRITICAL — phrases like `sorento dealer`, `mocha office`, `end user` are "
            "`access_levels` only. They are NEVER `*_ids` filter values."
        ),
        "/api/v1/marketing/promotion-attachments",
        (),
        ("page", "limit", "sort", "dir", "promotion_ids", "attachment_ids", "access_levels"),
        domain="promotions",
        related_tools=("crm_marketing_promotion_attachments_by_promotion", "crm_marketing_promotions_list", "crm_find_entity"),
        escalation_team="sales",
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
        (
            "All promotion attachments for ONE promotion by canonical UUID. Use for BROCHURE / "
            "FLYER tied to a specific promotion. Resolve the promotion reference FIRST via "
            "`crm_find_entity`, then pass its UUID as `promotion_id` path param.\n\n"
            "ACCESS LEVELS: `access_levels` filters to attachments under a promotion whose "
            "`access_levels` JSONB overlaps the supplied names. Omit to skip the filter. Pass as a "
            "single name (e.g. `\"Sorento Dealer\"`) or JSON array of names.\n\n"
            "CRITICAL — phrases like `sorento dealer`, `mocha office`, `end user` are "
            "`access_levels` only. They are NEVER any other filter value."
        ),
        "/api/v1/marketing/promotion-attachments/promotion/{promotion_id}",
        ("promotion_id",),
        ("access_levels",),
        domain="promotions",
        related_tools=("crm_marketing_promotion_attachments_list", "crm_marketing_promotions_get", "crm_find_entity"),
        escalation_team="sales",
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
        (
            "List file attachments in the global document library. PRIMARY TOOL FOR PRODUCT "
            "CATALOGUE / CATALOG / MASTER CATALOGUE PDF / COMPANY BROCHURE / PRICE LIST DOCUMENT "
            "requests — the full Sorento product catalogue PDF and similar company-wide documents "
            "live here, NOT on per-SKU attachments. For per-SKU brochures/datasheets use "
            "crm_master_product_attachments_list; for the standing Stock List PDF use "
            "crm_resource_attachments_current_stock_list.\n\n"
            "FILTER BY UUID: pass `attachment_ids` (canonical attachment UUIDs csv/JSON/repeated). "
            "Resolve free-text doc references (filename / description / type) FIRST via "
            "`crm_find_entity` — the resolver indexes attachments and returns their UUIDs."
        ),
        "/api/v1/resource-management/attachments",
        (),
        (
            "page",
            "limit",
            "attachment_ids",
            "sort",
            "dir",
            "directory_id",
            "attachment_type_id",
            "uploaded_by",
            "uploaded_at_from",
            "uploaded_at_to",
            "is_deleted",
            "resolve_signed_urls",
        ),
        domain="resources",
        related_tools=("crm_resource_attachments_get", "crm_resource_attachments_current_stock_list", "crm_find_entity"),
        escalation_team="support",
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
        "Get attachment metadata by id (includes linked records: product / promotion / form / etc).",
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
        (
            "Paged active-warehouse stock balances. Exposes quantity_on_hand and Malaysia-time "
            "updated_at only; does not reveal available/reserved/damaged/status. Response uses "
            "Sage-aligned warehouse vocabulary: `system_location` (was warehouse_code), "
            "`system_location_description` (was warehouse_name), `warehouse` (was location).\n\n"
            "ALL PARAMS ARE OPTIONAL. Call with NO arguments to list balances across every "
            "active warehouse. Default behaviour returns paginated rows for all products + all "
            "warehouses — do NOT block the call waiting for a warehouse.\n\n"
            "OPTIONAL NARROWING FILTERS:\n"
            "  • `product_ids` — canonical product UUIDs (csv / JSON list / repeated). Resolve "
            "free-text product refs FIRST via `crm_find_entity`.\n"
            "  • `warehouse_id` — canonical warehouse UUID. Scopes to a single warehouse. "
            "OPTIONAL: omit to span every active warehouse (one row per product+warehouse pair).\n"
        ),
        "/api/v1/inventory/stock/balance",
        (),
        (
            "page",
            "limit",
            "product_ids",
            "sort",
            "dir",
            "warehouse_id",
            "quantity_operator",
            "quantity_value",
            "status",
        ),
        domain="inventory",
        related_tools=("crm_inventory_stock_balance_export", "crm_inventory_warehouses_list", "crm_find_entity"),
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_inventory_stock_dashboard",
        (
            "Active-warehouse stock dashboard sourced from the stock table (matches the Stock listing UI). "
            "Returns total_skus, total_quantity, top warehouses by on-hand, 30-day net movement from "
            "stock_ledger, and latest_stock_list_attachment (the current singleton 'Stock List' attachment "
            "with a signed download URL — older versions are soft-deleted). "
            "Use `limit` (1-50, default 10) to cap stock_by_warehouse — pass `limit=10` from n8n to "
            "avoid pulling all 53 warehouses."
        ),
        "/api/v1/inventory/stock/dashboard",
        (),
        ("limit",),
    ),
    ToolSpec(
        "crm_inventory_stock_alerts",
        "Active-warehouse stock alerts from API.",
        "/api/v1/inventory/stock/alerts",
        (),
        (),
    ),
    ToolSpec(
        "crm_inventory_stock_balance_export",
        (
            "Export active-warehouse stock rows with optional filters. Exposes quantity_on_hand "
            "and Malaysia-time updated_at only. Warehouse keys use Sage-aligned vocabulary.\n\n"
            "FILTER BY UUID: `product_ids` (canonical product UUIDs csv/JSON/repeated). Resolve "
            "free-text product refs FIRST via `crm_find_entity`. `warehouse_id` is a canonical UUID."
        ),
        "/api/v1/inventory/stock/balance/export",
        (),
        ("warehouse_id", "product_ids", "quantity_operator", "quantity_value"),
        domain="inventory",
        related_tools=("crm_inventory_stock_balance_list", "crm_find_entity"),
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_inventory_stock_ledger_by_product_warehouse",
        "Ledger for one product in one active warehouse. Warehouse keys use Sage-aligned vocabulary (system_location, system_location_description, warehouse). Each ledger row carries the warehouse identifiers under a nested `system_location` object (renamed from `warehouse`) with `system_location` (code) and `warehouse` (label). product_id may be UUID or product_code (SKU). warehouse_id accepts UUID or system_location / system_location_description.",
        "/api/v1/inventory/stock/{product_id}/{warehouse_id}/ledger",
        ("product_id", "warehouse_id"),
        ("page", "limit"),
    ),
    ToolSpec(
        "crm_inventory_warehouses_list",
        "List warehouses. Response uses Sage-aligned vocabulary: `system_location` (was warehouse_code), `system_location_description` (was warehouse_name), `warehouse` (was location).",
        "/api/v1/inventory/warehouses",
        (),
        ("page", "limit", "query", "is_active"),
    ),
    ToolSpec(
        "crm_inventory_warehouses_get",
        "Get warehouse by id. `warehouse_id` accepts UUID or system_location / system_location_description. Response uses Sage-aligned vocabulary: system_location, system_location_description, warehouse.",
        "/api/v1/inventory/warehouses/{warehouse_id}",
        ("warehouse_id",),
        (),
    ),
    ToolSpec(
        "crm_inventory_storage_zones_list",
        "List storage zones. `warehouse_id` accepts UUID or system_location / system_location_description.",
        "/api/v1/inventory/storage-zones",
        (),
        ("page", "limit", "warehouse_id"),
    ),
    ToolSpec(
        "crm_inventory_storage_zones_tree",
        "Storage zone tree. `warehouse_id` accepts UUID or system_location / system_location_description.",
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
        "Global active-warehouse stock ledger list. Warehouse keys in the response use Sage-aligned vocabulary (system_location, system_location_description, warehouse). Each row carries the warehouse identifiers under a nested `system_location` object (renamed from `warehouse`) with `system_location` (code) and `warehouse` (label). `product_id` accepts UUID or product_code (SKU). `warehouse_id` accepts UUID or system_location / system_location_description.",
        "/api/v1/inventory/stock-ledger",
        (),
        ("page", "limit", "product_id", "warehouse_id", "transaction_type"),
    ),
    ToolSpec(
        "crm_inventory_stock_batches_list",
        "List stock batches for active warehouses. Warehouse keys in the response use Sage-aligned vocabulary (system_location, system_location_description, warehouse). Each batch row carries the warehouse identifiers under a nested `system_location` object (renamed from `warehouse`) with `system_location` (code) and `warehouse` (label). `product_id` accepts UUID or product_code (SKU). `warehouse_id` accepts UUID or system_location / system_location_description.",
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
        (
            "List orders. Response uses `pickup_time` (was `delivery_time`) for the lorry pickup "
            "time-of-day; `estimated_delivery_date` is not returned; `order_status` is a plain "
            "human-readable string (e.g. \"New\", \"Delivered\"), not an object. "
            "External/AI-agent callers are HARD-CAPPED at limit=10 server-side regardless of the "
            "value sent — narrow via UUID filters and date filters instead of asking for more rows.\n\n"
            "FILTER BY UUID — pass typed canonical UUIDs (csv / JSON list / repeated):\n"
            "  • `order_ids` — specific orders.\n"
            "  • `customer_ids` — customers (matches Order.customer_id, falls back to debtor_name "
            "for legacy rows).\n"
            "  • `product_ids` — orders containing any of these products (joins order lines).\n"
            "  • `transporter_ids` — transporters (matches Order.transporter_id, falls back to "
            "Order.transporter text for legacy rows).\n"
        ),
        "/api/v1/order-management/orders",
        (),
        (
            "page",
            "limit",
            "order_ids",
            "customer_ids",
            "product_ids",
            "transporter_ids",
            "actual_delivery_date_from",
            "actual_delivery_date_to",
            "sort",
            "dir",
        ),
        domain="orders",
        related_tools=("crm_order_management_orders_get", "crm_order_management_orders_by_product_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_order_management_orders_get",
        (
            "Get one order by canonical UUID. Pass the order's UUID as `order_id` path param. "
            "Resolve free-text order number / customer phrase to a UUID FIRST via `crm_find_entity`."
        ),
        "/api/v1/order-management/orders/{order_id}",
        ("order_id",),
        (),
        domain="orders",
        related_tools=("crm_order_management_orders_list", "crm_find_entity"),
        escalation_team="sales",
    ),
    ToolSpec(
        "crm_order_management_orders_by_product_list",
        (
            "List distinct CUSTOMER SALES orders containing a specific product (outgoing / sold, "
            "NOT incoming stock). Endpoint is product-centric — `product_ids` REQUIRED.\n\n"
            "FILTER BY UUID — pass canonical UUIDs (csv / JSON list / repeated):\n"
            "  • `product_ids` — REQUIRED, at least one product.\n"
            "  • `customer_ids` — optional, matches Order.customer_id with debtor_name fallback.\n"
            "  • `transporter_ids` — optional, matches Order.transporter_id with text fallback.\n"
            "Resolve free-text refs FIRST via `crm_find_entity`.\n\n"
            "Translate whatever time window the user gives (today, yesterday, last week, "
            "'February 2026', explicit YYYY-MM-DD range, etc.) into the date range and pass it "
            "on the actual-delivery-date params. Accepts YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, "
            "YYYY/MM/DD, ISO datetime, 'YYYY-MM', 'MM/YYYY', or 'Month YYYY'.\n\n"
            "Use when asked 'which customers bought SKU X', 'pending customer orders for product X', "
            "or to find DO numbers via product+customer+date range. DO NOT use for 'any incoming "
            "for product X' — that's procurement, use crm_incoming_stock_by_product instead."
        ),
        "/api/v1/order-management/orders/by-product",
        (),
        (
            "page",
            "limit",
            "product_ids",
            "customer_ids",
            "transporter_ids",
            "actual_delivery_date_from",
            "actual_delivery_date_to",
            "sort",
            "dir",
        ),
        domain="orders",
        related_tools=("crm_order_management_orders_list", "crm_incoming_stock_by_product", "crm_find_entity"),
        escalation_team="sales",
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
            "FILTER BY UUID: pass `product_ids` (canonical product UUIDs csv/JSON/repeated). "
            "Resolve free-text product refs FIRST via `crm_find_entity`."
        ),
        "/api/v1/incoming-stock/by-product",
        (),
        ("product_ids", "limit"),
        domain="incoming_stock",
        related_tools=("crm_master_products_get", "crm_find_entity"),
        escalation_team="warehouse",
    ),
    ToolSpec(
        "crm_incoming_stock_shipments",
        (
            "Use ONLY for SHIPMENT-CENTRIC questions (not product questions): 'any incoming "
            "shipments this month?' / 'what is arriving with ETA on date X?' / 'list open "
            "shipments from supplier Y'. Do NOT use for 'any incoming for product X' \u2014 use "
            "crm_incoming_stock_by_product instead. Returns shipment headers (shipment_number, "
            "container, ETA, total_remaining_incoming_quantity, distinct_products_incoming, "
            "packing-list attachment).\n\n"
            "FILTER BY UUID: `shipment_ids` (canonical inbound-shipment UUIDs csv/JSON/repeated), "
            "`supplier_ids` (canonical supplier UUIDs). Resolve free-text refs FIRST via "
            "`crm_find_entity`."
        ),
        "/api/v1/incoming-stock/shipments",
        (),
        ("shipment_ids", "supplier_ids", "eta_from", "eta_to", "page", "limit"),
        domain="incoming_stock",
        related_tools=("crm_incoming_stock_by_product", "crm_incoming_stock_shipment_products", "crm_find_entity"),
        escalation_team="warehouse",
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
            "Use ONLY when the user EXPLICITLY asks about GRN / goods received note / receipt "
            "document / 'has a GRN been created?'. Do NOT use for 'any incoming for product X' \u2014 "
            "use crm_incoming_stock_by_product. Returns minimal GRN info (grn_number, grn_date, "
            "grn_status, shipment_number). NO quantities, NO received/rejected counts.\n\n"
            "FILTER BY UUID: pass `shipment_ids` OR `product_ids` (canonical UUIDs csv/JSON/"
            "repeated). One of them required. Resolve free-text refs FIRST via `crm_find_entity`."
        ),
        "/api/v1/incoming-stock/grn",
        (),
        ("shipment_ids", "product_ids", "limit"),
        domain="incoming_stock",
        related_tools=("crm_incoming_stock_shipments", "crm_incoming_stock_by_product", "crm_find_entity"),
        escalation_team="warehouse",
    ),
    # --- procurement (ADMIN / INTERNAL raw data) ---
    # These expose raw receipt data (quantity_received, quantity_rejected, SPO numbers,
    # internal IDs). DO NOT use for user-facing enquiries — use crm_incoming_stock_* tools
    # instead. Kept here for admin / back-office operations only.
    ToolSpec(
        "crm_procurement_packing_lists_list",
        "INTERNAL / ADMIN only: raw inbound shipment headers including received quantities, SPO counts, and internal IDs. For user-facing 'any incoming?' questions use crm_incoming_stock_shipments. `supplier_id` is a canonical UUID.",
        "/api/v1/procurement/packing-lists",
        (),
        ("page", "limit", "query", "supplier_id", "shipment_status", "sort", "dir"),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_packing_lists_get",
        "INTERNAL / ADMIN only: full raw inbound shipment detail including received/rejected quantities, SPO allocations, linked GRNs, and internal IDs. For user-facing 'products in this shipment' use crm_incoming_stock_shipment_products. `shipment_id` must be a canonical UUID.",
        "/api/v1/procurement/packing-lists/{shipment_id}",
        ("shipment_id",),
        (),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_grouped_by_shipment",
        "INTERNAL / ADMIN only: raw SPO allocation aggregates per shipment (receipt_status, counts). For user-facing 'any incoming for product X' use crm_incoming_stock_by_product. `warehouse_id` is a canonical UUID.",
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
        internal=True,
        domain="procurement",
        escalation_team="procurement",
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
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_list",
        "INTERNAL / ADMIN only: flat list of raw SPO allocations with receipt_status, quantity_received, quantity_rejected, SPO numbers. Do NOT use for user enquiries. `shipment_id` and `warehouse_id` are canonical UUIDs.",
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
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_spo_allocations_get",
        "INTERNAL / ADMIN only: single SPO allocation with linked GRNs and raw receipt fields. `allocation_id` is a canonical UUID.",
        "/api/v1/procurement/spo-allocations/{allocation_id}",
        ("allocation_id",),
        (),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_grn_list",
        (
            "INTERNAL / ADMIN only: raw GRN / picking headers list with statuses and totals. "
            "For user-facing 'has a GRN been created?' use crm_incoming_stock_grn. "
            "Pass `product_ids` (canonical UUIDs) to narrow to GRNs whose linked "
            "picking_lines reference any of the given products. Omitting `limit` defaults "
            "to 50; cap is 200."
        ),
        "/api/v1/procurement/grn",
        (),
        ("page", "limit", "product_ids", "picking_status", "inspection_status", "sort", "dir"),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_grn_get",
        "INTERNAL / ADMIN only: full GRN / picking header including picking lines and quantities. `grn_id` is a canonical UUID.",
        "/api/v1/procurement/grn/{grn_id}",
        ("grn_id",),
        (),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    ToolSpec(
        "crm_procurement_picking_lines_list",
        "INTERNAL / ADMIN only: picking lines (receipt lines) with quantities and discrepancies.",
        "/api/v1/procurement/picking-lines",
        (),
        ("page", "limit", "query", "sort", "dir"),
        internal=True,
        domain="procurement",
        escalation_team="procurement",
    ),
    # --- forms ---
    ToolSpec(
        "crm_forms_management_forms_list",
        (
            "List forms.\n\n"
            "REQUIRED — `form_ids` (canonical form UUIDs csv/JSON/repeated) must be "
            "supplied or the tool returns an empty page. Resolve free-text form refs "
            "(code, name, or any phrase that describes the form's purpose — purpose "
            "text can be very long, so semantic matching against meaning is supported) "
            "FIRST via `crm_find_entity`, then pass returned form UUIDs here.\n\n"
            "If `crm_find_entity` returns NO form candidates for the user's reference, "
            "do NOT call this tool with empty `form_ids` — report 'no matching form' "
            "to the user instead."
        ),
        "/api/v1/forms-management/forms",
        (),
        ("page", "limit", "form_ids", "sort", "dir"),
        domain="forms",
        related_tools=("crm_forms_management_forms_get", "crm_find_entity"),
        escalation_team="support",
    ),
    ToolSpec(
        "crm_forms_management_forms_get",
        (
            "Get one form by canonical UUID. Pass the form's UUID as `form_id` path param. "
            "Resolve free-text form refs FIRST via `crm_find_entity`."
        ),
        "/api/v1/forms/{form_id}",
        ("form_id",),
        (),
        domain="forms",
        related_tools=("crm_forms_management_forms_list", "crm_find_entity"),
        escalation_team="support",
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
    # --- system capabilities ---
    ToolSpec(
        "crm_system_tool_capabilities_summary",
        (
            "Dynamic summary of everything this MCP can do right now, grouped into "
            "general enquiries vs form submissions. Use this when users ask "
            "'what can you do?', 'what features do you support?', or request capability overview. "
            "This summary is live (derived from current tool catalog + intents), not hard-coded. "
            "Optional query `include_tools` (true/false) controls whether full tool lists are returned."
        ),
        "/api/v1/system/tool-capabilities/summary",
        (),
        ("include_tools",),
    ),
    # --- portal handoff (replaces the legacy *_submit tools) ---
    ToolSpec(
        "crm_portal_link_get",
        (
            "Mint a 7-day user submission portal link for the active contact. Use this "
            "INSTEAD OF crm_forms_*_submit when the user wants to file a complaint, stock "
            "inquiry, purchase request or sponsorship form. Send the returned `portal_url` "
            "to the user; on the portal they can save drafts, attach files (images and "
            "PDFs, including pasted screenshots), submit, and review status. After 7 days "
            "the link expires and the contact re-verifies via OTP.\n"
            "`payload_json` must be a JSON object with:\n"
            "  - contact_id (string, required)\n"
            "  - space_id (string, required)\n"
            "  - submission_type (string, OPTIONAL but STRONGLY PREFERRED): one of "
            "`complaint`, `stock_inquiry`, `purchase_request`, `sponsorship_form`. "
            "When provided, the portal opens directly on that tab after the user "
            "verifies — no extra clicks. Always infer this from what the user asked "
            "to submit (complaint -> complaint, stock/product enquiry -> stock_inquiry, "
            "purchase request -> purchase_request, sponsorship form -> sponsorship_form).\n"
            "  - base_url (string, optional): override the frontend host."
        ),
        "/api/v1/external/portal-tokens/",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
    ),
    ToolSpec(
        "crm_forms_stock_inquiries_list",
        "List stock inquiries. Supports pagination and query.",
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
        "crm_forms_complaints_list",
        (
            "List complaints.\n"
            "Optional: page (default 1), limit (default 50), query (free-text over delivery_order_number, "
            "customer_name, product_code, defect_description, project_title), status, assigned_to, sort, dir."
        ),
        "/api/v1/complaints-management/complaints/",
        (),
        ("page", "limit", "query", "status", "assigned_to", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_complaints_get",
        "Get one complaint by complaint_id for view/update preparation.",
        "/api/v1/complaints-management/complaints/{complaint_id}",
        ("complaint_id",),
        (),
        method="GET",
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
    # --- commercial: customers (developer cross-check) ---
    ToolSpec(
        "crm_master_customers_list",
        (
            "List / search distinct customers, deduplicated by debtor_name aggregated from the orders table. "
            "The customers master table is not used by the business — the real customer identity lives on "
            "orders.debtor_name / debtor_code. Each row returns debtor_name, debtor_code, and order_count. "
            "Use BEFORE crm_commercial_projects_create_smart to cross-check existing customers and prevent "
            "duplicates from 1-2 char typos. `query` does case-insensitive partial match on debtor_name OR "
            "debtor_code. Sort: debtor_name | debtor_code | order_count (default debtor_name asc). External "
            "AI/MCP callers are HARD-CAPPED at limit=10 server-side."
        ),
        "/api/v1/order-management/orders/debtors",
        (),
        ("page", "limit", "query", "sort", "dir"),
    ),
    ToolSpec(
        "crm_master_customers_get",
        "Get one customer (developer/client) full detail by id.",
        "/api/v1/order-management/customers/{customer_id}",
        ("customer_id",),
        (),
        module="commercial_core",
    ),
    # --- commercial: projects ---
    ToolSpec(
        "crm_commercial_projects_list",
        "List commercial projects. Filters: customer_id, status_id, query (free-text). Default sort latest first.",
        "/api/v1/commercial/projects/",
        (),
        ("page", "limit", "query", "customer_id", "status_id", "sort", "dir"),
        module="commercial_core",
    ),
    ToolSpec(
        "crm_commercial_projects_get",
        "Get one commercial project full detail by id.",
        "/api/v1/commercial/projects/{project_id}",
        ("project_id",),
        (),
        module="commercial_core",
    ),
    ToolSpec(
        "crm_commercial_projects_create_smart",
        "Create a project with smart developer (customer) resolution. Body fields: developer_query OR developer_id OR developer_create, plus project (CommercialProjectCreate; developer_customer_id may be omitted), and force (bool). Returns 409 with near_matches when fuzzy match is ambiguous — caller must re-call with developer_id from the suggestions OR force=true + developer_create.",
        "/api/v1/commercial/projects/smart-create",
        (),
        (),
        method="POST",
        body_params=("payload_json",),
        module="commercial_core",
    ),
    ToolSpec(
        "crm_commercial_projects_edit",
        "Update fields on an existing commercial project. PATCH body matches CommercialProjectUpdate (title, brief, notes, status, dates, project_stage_id, owner_user_id, address fields, etc).",
        "/api/v1/commercial/projects/{project_id}",
        ("project_id",),
        (),
        method="PATCH",
        body_params=("payload_json",),
        module="commercial_core",
    ),
    # ===== User-guides (Outline-backed how-to retrieval) =====
    # These tools call the Outline API directly (not the CRM backend), so they
    # carry external=True and are wired up by `register_user_guide_tools` on
    # the MCP server. They still appear in the persisted catalog so admins can
    # toggle them for an AI assistant just like any other tool.
    ToolSpec(
        "user_guides_read",
        (
            "Single-call how-to tool. Pass the user's natural-language question as `query` "
            "(e.g. 'How do I upload a packing list?'); the tool searches the Sorento CRM "
            "Outline collection ('Sorento CRM') and returns the full markdown body of the "
            "best-matching guide in one round trip — no separate search call is needed. "
            "Use whenever the user asks 'how do I…?', 'how to…?', 'where do I find…?', "
            "'what's the process for…?', 'steps to…?' about CRM features (uploading a "
            "packing list, filing a stock inquiry from the portal, approving a purchase "
            "request, flowing a stock inquiry to purchasing, sending a sponsorship form "
            "for approval, OTP / portal access, etc.). Quote the returned steps verbatim "
            "and preserve inline markdown links exactly when answering the user. "
            "If the caller already has an Outline doc id (UUID) or url-id (e.g. "
            "'portal-overview-aBcDe'), pass it as `query` and the tool fetches the body "
            "directly."
        ),
        "/outline/documents.info",  # synthetic; not hit over HTTP
        (),
        ("query",),
        method="POST",
        module="user_guides",
        external=True,
    ),
    # ===== IT Support intake (single tool, two-call protocol) =====
    # The description is intentionally fat: the AI assistant's RAG selector
    # does embedding similarity over this text, so every common natural-language
    # phrasing of "I have an IT issue" must appear inline so the embedding
    # vector lands close to the user's message.
    ToolSpec(
        "crm_it_support_ticket_create",
        (
            "Submit an IT-support ticket / report a bug / log an issue with "
            "the IT admin team. INVOCATION RULES — VERY IMPORTANT: "
            "1. NEVER ask the user for ANYTHING — not title, not priority, "
            "not category, not description. Infer all ticket fields from the "
            "recent 1-5 turns of conversation; the user has already told you "
            "what is wrong. "
            "2. CALL ONCE with payload_json = JSON object containing "
            "{title, priority (low|medium|high|urgent), category "
            "(bug|feature|question|other), description}. Server creates a "
            "DRAFT ticket and returns a draft_url. "
            "Optionally pass `message_id` (Respond.io message id of the "
            "inbound WhatsApp message that triggered this ticket) at the TOP "
            "LEVEL of the tool arguments — NOT inside payload_json. Omit if "
            "you don't have it; do not fabricate. "
            "3. Reply to the user with ONE short message containing the "
            "draft_url verbatim, e.g. 'I prepared a draft ticket — open "
            "<draft_url> to review and click Submit.' Do NOT echo the "
            "preview fields, do NOT ask for confirmation in chat — the user "
            "confirms by clicking Submit on the draft page. "
            "4. STOP. Do not call this tool again in the same turn. "
            "WHEN TO USE: user is reporting that something is broken / not "
            "working / errored / crashed / slow / can't access / login fails "
            "/ page won't load / data missing, OR explicitly asks to file / "
            "submit / raise a ticket / open a support request / report a "
            "problem / log a complaint with IT / get tech support. "
            "DO NOT USE for how-to questions ('how do I…', 'where is…', "
            "'what are the steps to…') — those belong to user_guides_read."
        ),
        "/api/v1/external/it-support/tickets/",
        (),
        (),
        method="POST",
        body_params=("payload_json", "message_id"),
        module="tickets",
    ),
)
