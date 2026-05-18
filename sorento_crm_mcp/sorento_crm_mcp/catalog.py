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
            "datasheet / spec sheet of a named product, use crm_master_product_attachments_list. "
            "`entities` is the free-text bag for product references (code, name, partial SKU, "
            "descriptive phrase). ONE ENTITY PER ARRAY ELEMENT. Hybrid resolver (substring → "
            "pg_trgm → RAG semantic). DO NOT pass numeric/range expressions like 'price > 100' or "
            "'dimensions > 300mm' as `entities`; use the dedicated numeric filter parameters below. "
            "`category_id` accepts UUID or category_code/name. `brand_id` accepts UUID or brand_code/name. "
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
            "`crm_product_attachments_*` separately."
        ),
        "/api/v1/master-data/products",
        (),
        (
            "page",
            "limit",
            "entities",
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
    ),
    ToolSpec(
        "crm_master_products_get",
        (
            "Get one product (first match). Pass the product reference via `entities` — code, "
            "name, partial SKU, or descriptive phrase. Resolver: hybrid (substring ILIKE → "
            "pg_trgm typo-tolerant → RAG semantic). The endpoint is the products list with "
            "limit=1; the first row is the answer. ONE ENTITY PER ARRAY ELEMENT. Response may "
            "include `field_attachments` — a map of product field name (e.g. `weight`, "
            "`dimensions_length`) to an array of linked docs."
        ),
        "/api/v1/master-data/products",
        (),
        ("entities", "limit"),
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
            "List per-SKU product↔attachment links with filters. Use this for documents tied to a "
            "SPECIFIC product (named SKU + document): BROCHURE, SPEC SHEET, DATASHEET, PRODUCT "
            "MANUAL, INSTALLATION GUIDE, CERTIFICATE, or 'do you have a document for product X' "
            "question."
            "`product_id` accepts a product UUID or exact product code. "
            "Visibility is gated server-side by the contact's access types — pass the Respond.io "
            "`contact_id` (respond_io_id) and `space_id` (workspace space id); the backend resolves "
            "the contact's access levels automatically (no `access_levels` param needed). "
            "Internal fields (directory_id, storage_provider, uploaded_by id, full_directory_path) "
            "are stripped from the response — caller sees only file_name, public URL, description, "
            "uploaded_by_user_display_name, created_at."
        ),
        "/api/v1/master-data/product-attachments",
        (),
        ("page", "limit", "sort", "dir", "entities", "attachment_id", "contact_id", "space_id"),
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
            "All attachment links for a SPECIFIC product. Use for BROCHURE / SPEC SHEET / "
            "DATASHEET / PRODUCT MANUAL / INSTALLATION GUIDE / CERTIFICATE questions about a "
            "named SKU. Pass the product reference via `entities` — code, name, partial SKU, "
            "or descriptive phrase. Hybrid resolver (substring → pg_trgm → RAG) picks the "
            "matching product(s) and the response includes their linked attachments. Server "
            "filters attachments by the contact's M2M access types (auto-resolved from "
            "`contact_id` + `space_id`)."
        ),
        "/api/v1/master-data/product-attachments",
        (),
        ("entities", "contact_id", "space_id"),
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
    # --- user management / access discovery ---
    ToolSpec(
        "crm_user_management_contact_access_levels_active",
        (
            "Return the contact's CURRENTLY-ACTIVE access levels — `[{name}]`. Call BEFORE any "
            "promotion / promotion-attachment / product-attachment tool when the request is "
            "contact-scoped AND you have not yet established which access_levels apply. Names are "
            "DYNAMIC per contact (never guess from a static enum).\n\n"
            "DECISION TREE for the gated tool:\n"
            "  • Response has 1 entry → skip passing access_levels (backend auto-defaults).\n"
            "  • Response has >1 entries → pass any reasonable variant of one returned `name`. The "
            "backend matcher is forgiving: case-insensitive, name OR underscore-code (`Sorento "
            "Dealer` ≡ `sorento_dealer`), plurals (`Sorento Dealers`), no-space form (`enduser` ≡ "
            "`End User`), single-token subsets (`dealer` resolves uniquely when only one active "
            "name contains it), noisy-phrase matches (`end user as customer` still resolves), AND "
            "admin-curated synonyms stored on the level itself (`customer`, `homeowner`, `b2c` → "
            "`End User`; `reseller`, `retailer` → `Dealer`). When any of these matches >1 active "
            "level, backend returns 403 ACCESS_LEVELS_AMBIGUOUS with a `candidates` map — re-issue "
            "with a more specific name.\n"
            "  • Response is empty → contact has no entitlements; gated tools will return no rows.\n\n"
            "CRITICAL — A user phrase that matches (or partially matches) one of the returned "
            "`name` values is the `access_levels` filter, NEVER the `entities` field of the gated "
            "tool. `entities` is reserved for product/promotion descriptive text (e.g. `kitchen sink`, "
            "`NL series`).\n\n"
            "404 → unknown contact_id / space_id pair."
        ),
        "/api/v1/external/contact-access-types/active",
        (),
        ("contact_id", "space_id"),
        module="user_management",
    ),

    # --- marketing ---
    ToolSpec(
        "crm_marketing_promotions_list",
        (
            "List promotions (summary fields + linked attachments inline; no product lines). "
            "Each row already carries its `attachments` array — no second tool call needed for "
            "promotion documents. Default returns ACTIVE promotions (is_active=true AND today "
            "within start_date/end_date); when a narrowing filter (entities, period) "
            "yields zero active matches, falls back to INACTIVE matches automatically and sets "
            "fallback_used=true on the response. Pass active=false to fetch historical-only "
            "(no fallback). Use period_from / period_to (YYYY-MM-DD) to scope by overlap with the "
            "promotion's [start_date, end_date] window. For product lines use "
            "crm_marketing_promotion_products_list.\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active level "
            "— backend auto-defaults to it. REQUIRED when the contact has >1 active levels; calling "
            "without it returns 422 + `allowed:[{name}]`. Names are DYNAMIC per contact — do NOT "
            "guess from a static enum. To pick safely, call "
            "`crm_user_management_contact_access_levels_active` first; if 1 entry skip passing "
            "access_levels, if >1 map the user's phrasing to one of the returned `name` values and "
            "pass that name. A value not in the live active set → 403 + refreshed `allowed`.\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO `entities`. If the user mentions a phrase "
            "that sounds like a customer-tier / org-role (`sorento dealer`, `dealer`, `mocha "
            "office`, `end user`, `sorento office`, etc.), that phrase is the `access_levels` "
            "filter — NEVER pass it as `entities`. `entities` is for product / promotion descriptive "
            "text only (e.g. `kitchen sink`, `NL series`). When unsure, call the discovery tool first "
            "and check whether the user's phrase fuzzy-matches any returned `name`."
        ),
        "/api/v1/marketing/promotions",
        (),
        ("page", "limit", "entities", "active", "period_from", "period_to", "sort", "dir", "contact_id", "space_id", "access_levels"),
    ),
    ToolSpec(
        "crm_marketing_promotions_get",
        (
            "Get one promotion: metadata, groups (FOC tiers), AND linked attachments inline. "
            "No second tool call needed for attachments — they come back on the same response. "
            "Does NOT include product lines by default; set include_products=true only if you need "
            "nested SKU lines. Visibility is gated server-side from the contact's M2M access types "
            "(`contact_id` + `space_id`); a 404 is returned when the promotion does not overlap the "
            "contact's access types, and inline attachments are filtered the same way.\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active "
            "level — backend auto-defaults to it. REQUIRED when the contact has >1; calling without "
            "it returns 422 + `allowed:[{name}]`. Call "
            "`crm_user_management_contact_access_levels_active` first; if 1 entry skip passing, "
            "if >1 map user's phrasing to one of the returned `name` values and pass it.\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO ANY OTHER PARAM. Phrases like `sorento "
            "dealer`, `dealer`, `mocha office`, `end user` are `access_levels`, never `entities`."
        ),
        "/api/v1/marketing/promotions",
        (),
        ("entities", "limit", "contact_id", "space_id", "access_levels"),
    ),
    ToolSpec(
        "crm_marketing_promotion_products_nested",
        (
            "Products linked to a promotion (nested under promotion). Each row also carries the "
            "parent promotion's `promotion_attachments` inline — no second call needed to fetch the "
            "promotion document. Optional page/limit (default limit 1000, max 5000).\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active level — "
            "backend auto-defaults to it. REQUIRED when the contact has >1 active levels; calling "
            "without it returns 422 + `allowed:[{name}]`. To pick safely, call "
            "`crm_user_management_contact_access_levels_active` first; if it returns 1 entry skip "
            "passing access_levels, if it returns >1 map the user's phrasing to one of the returned "
            "`name` values and pass that name as `access_levels` (string for a single level, e.g. `\"Sorento Dealer\"`; or a JSON array of strings to match any of several, e.g. `[\"Sorento Dealer\",\"Mocha Office\"]`).\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO `entities`. If the user mentions a phrase "
            "that sounds like a customer-tier / org-role (`sorento dealer`, `dealer`, `mocha "
            "office`, `end user`, `sorento office`, etc.), that phrase is the `access_levels` "
            "filter — NEVER pass it as `entities`. `entities` is for product / promotion descriptive "
            "text only (e.g. `kitchen sink`, `NL series`). When unsure, call the discovery tool first "
            "and check whether the user's phrase fuzzy-matches any returned `name`."
        ),
        "/api/v1/marketing/promotion-products",
        (),
        ("entities", "page", "limit", "contact_id", "space_id", "access_levels"),
    ),
    ToolSpec(
        "crm_marketing_promotion_products_list",
        (
            "Promotion product lines (paginated). Each row carries the parent promotion's "
            "`promotion_attachments` inline — no second call needed for the promotion document.\n\n"
            "ENTITY FILTER (`entities`): free-text bag — product codes/SKUs, product names, "
            "promotion references, descriptive phrases. *** ONE ENTITY PER ARRAY ELEMENT. *** "
            "Hybrid resolver (substring → pg_trgm → RAG semantic) maps each entry to its type and "
            "applies the right filter. CORRECT: entities=[\"sorento wash basin\", \"kitchen sink\"]. "
            "WRONG: entities=[\"sorento wash basin kitchen sink\"]. Pass ONLY word-like traits "
            "(nouns/adjectives) — do NOT bury numbers inside `entities`.\n\n"
            "STRUCTURED FILTERS — USE THESE WHENEVER THE USER MENTIONS A NUMBER OR DIMENSION. "
            "Explicit params are faster and more precise.\n"
            "  • PRICE: price_min, price_max (MYR)\n"
            "  • DIMENSIONS (mm): per-axis length_min/max, width_min/max, height_min/max\n"
            "  • AXIS-AGNOSTIC: any_dimension_min / any_dimension_max — matches when ANY of L/W/H "
            "is in range. Use when the user doesn't say which axis (e.g. 'around 600mm')\n"
            "  • category_id (UUID or category_code/name), brand_id (UUID or brand_code/name), "
            "item_type, status=active|inactive|all\n\n"
            "EXACT vs FUZZY — CRITICAL:\n"
            "  • Bare number ('365', 'L600', '460×330×140') = EXACT. Set min == max == value.\n"
            "    Do NOT widen the range. The user gave a precise dimension; treat it as one.\n"
            "  • Hedge words ('around', 'about', '~', 'approx', 'roughly', 'near') = FUZZY. "
            "    Apply a ±5 mm tolerance (or wider if the user says 'around 600mm or so').\n\n"
            "EXAMPLES — copy this pattern:\n"
            "  User says 'basin 365 width'           →  entities=['basin'], width_min=365, width_max=365\n"
            "  User says 'basin around 365 width'    →  entities=['basin'], width_min=360, width_max=370\n"
            "  User says 'cabinet L600'              →  entities=['cabinet'], length_min=600, length_max=600\n"
            "  User says 'wash basin 460×330×140'    →  entities=['wash basin'], "
            "length_min=460 length_max=460 width_min=330 width_max=330 height_min=140 height_max=140\n"
            "  User says 'basin around 600mm'        →  entities=['basin'], any_dimension_min=595, any_dimension_max=605\n"
            "  User says 'sorento wash basin under RM 500' →  entities=['sorento wash basin'], price_max=500\n\n"
            "Pass a promotion reference inside `entities` to scope to one promotion; omit to find "
            "which promotions a product (or trait) appears in.\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active level — "
            "backend auto-defaults to it. REQUIRED when the contact has >1 active levels; calling "
            "without it returns 422 + `allowed:[{name}]`. To pick safely, call "
            "`crm_user_management_contact_access_levels_active` first; if it returns 1 entry skip "
            "passing access_levels, if it returns >1 map the user's phrasing to one of the returned "
            "`name` values and pass that name as `access_levels` (string for a single level, e.g. `\"Sorento Dealer\"`; or a JSON array of strings to match any of several, e.g. `[\"Sorento Dealer\",\"Mocha Office\"]`).\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO `entities`. If the user mentions a phrase "
            "that sounds like a customer-tier / org-role (`sorento dealer`, `dealer`, `mocha "
            "office`, `end user`, `sorento office`, etc.), that phrase is the `access_levels` "
            "filter — NEVER pass it as `entities`. `entities` is for product / promotion descriptive "
            "text only (e.g. `kitchen sink`, `NL series`). When unsure, call the discovery tool first "
            "and check whether the user's phrase fuzzy-matches any returned `name`."
        ),
        "/api/v1/marketing/promotion-products",
        (),
        (
            "page", "limit", "sort", "dir", "entities",
            "item_type", "status",
            "price_min", "price_max",
            "length_min", "length_max",
            "width_min", "width_max",
            "height_min", "height_max",
            "any_dimension_min", "any_dimension_max",
            "contact_id", "space_id", "access_levels",
        ),
    ),
    ToolSpec(
        "crm_marketing_promotion_attachments_list",
        (
            "List/search promotion–attachment links. Use for any "
            "BROCHURE / FLYER document. Pass promotion / product / attachment references "
            "(name, code, descriptive phrase) via `entities` — hybrid resolver picks the matches. "
            "ONE ENTITY PER ARRAY ELEMENT. Server filters results to links whose parent promotion "
            "AND attachment access_levels both overlap the contact's M2M access types (resolved "
            "from `contact_id` + `space_id`). Internal storage fields are stripped from the response.\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active level — "
            "backend auto-defaults to it. REQUIRED when the contact has >1 active levels; calling "
            "without it returns 422 + `allowed:[{name}]`. To pick safely, call "
            "`crm_user_management_contact_access_levels_active` first; if it returns 1 entry skip "
            "passing access_levels, if it returns >1 map the user's phrasing to one of the returned "
            "`name` values and pass that name as `access_levels` (string for a single level, e.g. `\"Sorento Dealer\"`; or a JSON array of strings to match any of several, e.g. `[\"Sorento Dealer\",\"Mocha Office\"]`).\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO `entities`. If the user mentions a phrase "
            "that sounds like a customer-tier / org-role (`sorento dealer`, `dealer`, `mocha "
            "office`, `end user`, `sorento office`, etc.), that phrase is the `access_levels` "
            "filter — NEVER pass it as `entities`. `entities` is for product / promotion descriptive "
            "text only (e.g. `kitchen sink`, `NL series`). When unsure, call the discovery tool first "
            "and check whether the user's phrase fuzzy-matches any returned `name`."
        ),
        "/api/v1/marketing/promotion-attachments",
        (),
        ("page", "limit", "sort", "dir", "entities", "attachment_id", "contact_id", "space_id", "access_levels"),
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
            "All promotion attachments for a promotion. Use for "
            "/ BROCHURE / FLYER tied to a specific promotion. "
            "promotion_id must be the UUID. Server filters to attachments whose parent promotion "
            "AND attachment access_levels both overlap the contact's M2M access types (resolved "
            "from `contact_id` + `space_id`). Internal storage fields are stripped.\n\n"
            "ACCESS LEVELS: `access_levels` is OPTIONAL when the contact has exactly 1 active level — "
            "backend auto-defaults to it. REQUIRED when the contact has >1 active levels; calling "
            "without it returns 422 + `allowed:[{name}]`. To pick safely, call "
            "`crm_user_management_contact_access_levels_active` first; if it returns 1 entry skip "
            "passing access_levels, if it returns >1 map the user's phrasing to one of the returned "
            "`name` values and pass that name as `access_levels` (string for a single level, e.g. `\"Sorento Dealer\"`; or a JSON array of strings to match any of several, e.g. `[\"Sorento Dealer\",\"Mocha Office\"]`).\n\n"
            "CRITICAL — DO NOT ROUTE ACCESS LEVEL NAMES TO `entities`. If the user mentions a phrase "
            "that sounds like a customer-tier / org-role (`sorento dealer`, `dealer`, `mocha "
            "office`, `end user`, `sorento office`, etc.), that phrase is the `access_levels` "
            "filter — NEVER pass it as `entities`. `entities` is for product / promotion descriptive "
            "text only (e.g. `kitchen sink`, `NL series`). When unsure, call the discovery tool first "
            "and check whether the user's phrase fuzzy-matches any returned `name`."
        ),
        "/api/v1/marketing/promotion-attachments/promotion/{promotion_id}",
        ("promotion_id",),
        ("contact_id", "space_id", "access_levels"),
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
            "List file attachments in the global document library (filters: entities, directory, "
            "trash). PRIMARY TOOL FOR PRODUCT CATALOGUE / CATALOG / MASTER CATALOGUE "
            "PDF / COMPANY BROCHURE / PRICE LIST DOCUMENT requests — the full Sorento product "
            "catalogue PDF and similar company-wide documents live here, NOT on per-SKU "
            "attachments. Pass the user keyword (e.g. 'catalogue', 'catalog', 'price list', "
            "'brochure') as a string in `entities`. ONE ENTITY PER ARRAY ELEMENT. For per-SKU "
            "brochures/datasheets use crm_master_product_attachments_list; for the standing Stock "
            "List PDF use crm_resource_attachments_current_stock_list."
        ),
        "/api/v1/resource-management/attachments",
        (),
        (
            "page",
            "limit",
            "entities",
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
        (
            "Paged active-warehouse stock balances. Exposes quantity_on_hand and Malaysia-time "
            "updated_at only for stock quantities; does not reveal available/reserved/damaged/status. "
            "Response uses Sage-aligned warehouse vocabulary: `system_location` (was warehouse_code), "
            "`system_location_description` (was warehouse_name), `warehouse` (was location). Each row "
            "exposes the warehouse identifiers under a nested `system_location` object (renamed from "
            "`warehouse`) containing `system_location` (code) and `warehouse` (label).\n\n"
            "ENTITY FILTER (single bag): pass anything the user names — product codes/SKUs, customer "
            "names, etc. — as STRINGS in `entities`. *** ONE ENTITY PER ARRAY ELEMENT. *** Do NOT "
            "concatenate. Do NOT prefix with type labels. CORRECT: entities=[\"SRTWC101\", \"WESERP10B\"]. "
            "WRONG: entities=[\"product SRTWC101 and WESERP10B\"]. The server resolves each via the "
            "entity_resolver (pgvector RAG over product/customer/order/transporter/... chunks) and "
            "applies PRODUCT matches to Stock.product_id (multiple products → IN). Other resolved "
            "types (customer, order, transporter, ...) are echoed under `resolved_entities` but DO NOT "
            "filter stock rows — stock is keyed by product + warehouse only. If nothing resolves to a "
            "product the response is empty + echo.\n\n"
            "`warehouse_id` (separate from `entities`) accepts UUID or system_location / "
            "system_location_description and still resolves against the underlying warehouse_code/name "
            "columns. Use it for warehouse filtering until warehouse is added to the embedding index."
        ),
        "/api/v1/inventory/stock/balance",
        (),
        (
            "page",
            "limit",
            "entities",
            "sort",
            "dir",
            "warehouse_id",
            "quantity_operator",
            "quantity_value",
            "status",
        ),
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
            "Export active-warehouse stock rows with optional filters. MCP output exposes "
            "quantity_on_hand and Malaysia-time updated_at only for stock quantities. Warehouse "
            "keys use the Sage-aligned vocabulary: system_location, system_location_description, "
            "warehouse. Each row carries the warehouse identifiers under a nested `system_location` "
            "object (renamed from `warehouse`) with `system_location` (code) and `warehouse` (label).\n\n"
            "ENTITY FILTER: pass product codes / customer / etc as separate strings in `entities`. "
            "Only PRODUCT matches narrow the export (Stock.product_id IN ...). Other resolved types "
            "echo back but don't filter. *** ONE ENTITY PER ARRAY ELEMENT ***.\n\n"
            "`warehouse_id` accepts UUID or system_location / system_location_description and stays "
            "as a separate param for warehouse filtering."
        ),
        "/api/v1/inventory/stock/balance/export",
        (),
        ("warehouse_id", "entities", "quantity_operator", "quantity_value"),
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
            "value sent — narrow via `entities` and date filters instead of asking for more rows.\n\n"
            "ENTITY FILTER (single bag): pass anything the user names — customer names/codes, "
            "product codes/SKUs, transporter labels, order numbers — as STRINGS in `entities`. "
            "*** ONE ENTITY PER ARRAY ELEMENT. *** Do NOT concatenate multiple entities into a "
            "single string. Do NOT prefix with type labels like \"transporter\" / \"customer\". "
            "CORRECT: entities=[\"Svind Enterprise\", \"GT Delivery\"]. "
            "WRONG: entities=[\"transporter Svind Enterprise gt delivery\"] — the server treats "
            "that as one phrase and will likely miss both. "
            "Do NOT try to classify the type yourself; the server resolves each entry via the "
            "entity_resolver (exact → prefix ILIKE → semantic embedding) and routes it to the "
            "right filter. Multiple values of the same type are OR'd (IN); different types are "
            "AND'd (intersection). The response includes "
            "`resolved_entities` with `resolved` (what matched), `ambiguous` (multiple candidates "
            "— ask the user to pick), and `unresolved` (no match — tell the user). ALWAYS surface "
            "ambiguous/unresolved back to the user before declaring a result.\n\n"
            "DATE FILTER RULE — pick the param family from the user's verb, not the time window.\n"
            "DELIVERY verbs ('delivered', 'received', 'dropped off', 'for delivery', 'pending delivery', 'arrived', 'delivery date') "
            "=> use `actual_delivery_date_from` / `actual_delivery_date_to`.\n"
            "ORDER verbs ('ordered', 'placed', 'created', 'raised', 'opened', 'booked', 'order date') "
            "DEFAULT to `actual_delivery_date_from` / `actual_delivery_date_to`.\n"
            "Decision table (phrasing => param):\n"
            "  'orders delivered today'              => actual_delivery_date_from = today, _to = today\n"
            "  'orders delivered last week'          => actual_delivery_date_from / _to = last week\n"
            "  'orders delivered yesterday'          => actual_delivery_date_from / _to = yesterday\n"
            "  'what was delivered yesterday for X'  => actual_delivery_date_from / _to = yesterday\n"
            "  'orders pending delivery this week'   => actual_delivery_date_from / _to = this week\n"
            "  'for delivery this week'              => actual_delivery_date_from / _to = this week\n"
            "  'check DO for today'                  => actual_delivery_date_from / _to = today\n"
            "  'DO for product X today'              => actual_delivery_date_from / _to = today\n"
            "  'orders in February' (no verb)        => actual_delivery_date_from / _to = Feb 2026\n"
            "  'orders last week' (no verb)          => actual_delivery_date_from / _to = last week\n"
            "  'orders placed last week'             => order_date_from / _to = last week\n"
            "  'orders created today'                => order_date_from / _to = today\n"
            "  'orders raised in February 2026'      => order_date_from / _to = Feb 2026\n"
            "Do NOT pass both families in one call unless the user explicitly asks for an intersection. "
            "Both date params accept flexible formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, ISO datetime, "
            "'YYYY-MM', 'MM/YYYY', or 'Month YYYY' (e.g. 'February 2026'). "
            "For complaint DO filtering, pass customer + product into `entities` together plus an order date range."
        ),
        "/api/v1/order-management/orders",
        (),
        (
            "page",
            "limit",
            "entities",
            "actual_delivery_date_from",
            "actual_delivery_date_to",
            "sort",
            "dir",
        ),
    ),
    ToolSpec(
        "crm_order_management_orders_get",
        (
            "Get one order (first match). Pass the order reference via `entities` — order "
            "number, customer name, etc. Hybrid resolver (substring → pg_trgm → RAG). Returns "
            "list with limit=1 from the same endpoint as orders_list; first row is the order. "
            "ONE ENTITY PER ARRAY ELEMENT."
        ),
        "/api/v1/order-management/orders",
        (),
        ("entities", "limit"),
    ),
    ToolSpec(
        "crm_order_management_orders_by_product_list",
        (
            "List distinct CUSTOMER SALES orders containing a specific product (outgoing / sold, "
            "NOT incoming stock). Endpoint is product-centric — at least one item in `entities` "
            "MUST resolve to a product, otherwise the response is empty.\n\n"
            "ENTITY FILTER (single bag): pass anything the user names — product codes/SKUs, "
            "customer names/codes, transporter labels, order numbers — as STRINGS in `entities`. "
            "*** ONE ENTITY PER ARRAY ELEMENT. *** Do NOT concatenate multiple entities into a "
            "single string. Do NOT prefix with type labels (\"transporter\", \"customer\", \"product\"). "
            "CORRECT: entities=[\"SRTWC8608\", \"Svind Enterprise\", \"GT Delivery\"]. "
            "WRONG: entities=[\"product SRTWC8608 customer Svind transporter gt delivery\"]. "
            "Do NOT try to classify the type yourself; the server resolves each via "
            "entity_resolver (exact → prefix ILIKE → embedding) and routes to the matching filter. "
            "Partial / suffix variants and loose phrases work: \"SRTWC8608\", \"fira ventures\", "
            "\"yotu\", \"Suncrest\", \"SO-2026-001\" all resolve correctly without pre-canonicalising. "
            "Multiple values of the same type are OR'd (IN); different types are AND'd. The "
            "response echoes `resolved_entities` with `resolved` / `ambiguous` / `unresolved` — "
            "ALWAYS surface ambiguous/unresolved back to the user before declaring a result.\n\n"
            "DATE FILTER RULE: For Delivery-Order (DO) discovery and any bare 'orders in [today/"
            "yesterday/this week/month/period/date range]' question, DEFAULT to "
            "`actual_delivery_date_from`/`actual_delivery_date_to`."
            "Delivery verbs ('delivered', 'received', 'for delivery', 'pending delivery', 'arrived', "
            "'delivery date') and bare time windows ('today', 'this week', 'February 2026') => "
            "`actual_delivery_date_from/_to`. Both date params accept flexible formats: "
            "YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, ISO datetime, 'YYYY-MM', 'MM/YYYY', or "
            "'Month YYYY' (e.g. 'February 2026').\n\n"
            "Use when asked 'which customers bought SKU X', 'pending customer orders for product X', "
            "or to find DO numbers via product+customer+date range (independent of complaint filing "
            "flow). DO NOT use for 'any incoming for product X' / 'is product X arriving' — that is "
            "procurement, use crm_procurement_spo_allocations_grouped_by_shipment instead."
        ),
        "/api/v1/order-management/orders/by-product",
        (),
        (
            "page",
            "limit",
            "entities",
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
            "Pass product references (UUID, product_code/SKU, name, descriptive phrase) via "
            "`entities`. ONE ENTITY PER ARRAY ELEMENT. Hybrid resolver (substring → pg_trgm → "
            "RAG) handles partial codes and typos. Multi-SKU: pass each as a separate element "
            "(e.g. entities=[\"SRTMCB8082-BL\", \"SRTWW8082-C\"])."
        ),
        "/api/v1/incoming-stock/by-product",
        (),
        ("entities", "limit"),
    ),
    ToolSpec(
        "crm_incoming_stock_shipments",
        (
            "Use ONLY for SHIPMENT-CENTRIC questions (not product questions): 'any incoming shipments this month?' / 'what is arriving with ETA on date X?' / 'list open shipments from supplier Y'. "
            "Do NOT use this for 'any incoming for product X' \u2014 use crm_incoming_stock_by_product (which already includes per-shipment breakdown). "
            "Returns shipment headers (shipment_number, shipping_container_number, estimated_arrival_date, total_remaining_incoming_quantity, distinct_products_incoming, packing-list attachment). "
            "Pass shipment references (shipment_number / container / BOL / invoice / supplier "
            "name) via `entities`. ONE ENTITY PER ARRAY ELEMENT."
        ),
        "/api/v1/incoming-stock/shipments",
        (),
        ("entities", "eta_from", "eta_to", "page", "limit"),
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
        ("entities", "limit"),
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
        (
            "INTERNAL / ADMIN only: raw GRN / picking headers list with statuses and totals. "
            "For user-facing 'has a GRN been created?' use crm_incoming_stock_grn. "
            "FUZZY SEARCH: pass `product_query` for a partial product filter on linked "
            "picking_lines (matches product_code/product_name/description, case-insensitive). "
            "When product embeddings exist, shortform codes expand to canonical SKUs (e.g. "
            "`product_query='WC101'` matches 'SRTWC101', 'SRTWC101-RL'). "
            "Omitting `limit` defaults to 50; cap is 200."
        ),
        "/api/v1/procurement/grn",
        (),
        ("page", "limit", "entities", "picking_status", "inspection_status", "sort", "dir"),
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
        "List forms visible to a Respond contact. Query searches code, name, purpose, form_type, and linked attachment filename. Pass form_type to filter department/category.",
        "/api/v1/forms-management/forms",
        (),
        ("page", "limit", "query", "language", "status", "form_type", "contact_id", "space_id", "sort", "dir"),
    ),
    ToolSpec(
        "crm_forms_management_forms_get",
        "Get a form by id if visible to the Respond contact. Returns form_type so the requester knows which department/category the form belongs to.",
        "/api/v1/forms-management/forms/{form_id}",
        ("form_id",),
        ("contact_id", "space_id"),
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
        "List stock inquiries for current authenticated scope. Supports pagination and query.",
        "/api/v1/procurement/stock-inquiries",
        (),
        ("page", "limit", "query", "contact_id", "space_id", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_stock_inquiries_get",
        "Get one stock inquiry by inquiry_id for view/update preparation.",
        "/api/v1/procurement/stock-inquiries/{inquiry_id}",
        ("inquiry_id",),
        ("contact_id", "space_id"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_purchase_requests_list",
        "List purchase requests and sponsorship forms. Supports request_type, approval_status, query, and pagination.",
        "/api/v1/procurement/purchase-requests",
        (),
        ("page", "limit", "query", "contact_id", "space_id", "request_type", "approval_status", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_purchase_requests_get",
        "Get one purchase request or sponsorship form by request_id.",
        "/api/v1/procurement/purchase-requests/{request_id}",
        ("request_id",),
        ("contact_id", "space_id"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_complaints_list",
        (
            "List complaints scoped to the current Respond.io contact_id and space_id.\n"
            "REQUIRED PARAMETERS: `contact_id` AND `space_id`. ALWAYS pass BOTH from the active session/context "
            "— never omit. Calling without them returns 400 'contact_id and space_id are required for external "
            "complaint list/get requests.' Do NOT try to substitute them with `query`; they are separate parameters.\n"
            "Optional: page (default 1), limit (default 50), query (free-text over delivery_order_number, "
            "customer_name, product_code, defect_description, project_title), status, assigned_to, sort, dir."
        ),
        "/api/v1/complaints-management/complaints/",
        (),
        ("contact_id", "space_id", "page", "limit", "query", "status", "assigned_to", "sort", "dir"),
        method="GET",
    ),
    ToolSpec(
        "crm_forms_complaints_get",
        (
            "Get one complaint by complaint_id for view/update preparation.\n"
            "REQUIRED PARAMETERS: `complaint_id` (path) AND `contact_id` AND `space_id` (query). ALWAYS pass "
            "both contact_id and space_id from the active session/context — never omit. Calling without them "
            "returns 400; the lookup also 404s when the complaint exists but is not in the supplied scope."
        ),
        "/api/v1/complaints-management/complaints/{complaint_id}",
        ("complaint_id",),
        ("contact_id", "space_id"),
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
            "ALSO pass `contact_id` (Respond.io contact id — this IS the "
            "conversation reference; Respond.io has one inbox per contact, "
            "so do NOT pass a separate conversation_id), `space_id` "
            "(Respond.io workspace id), and `message_id` (Respond.io message "
            "id of the inbound WhatsApp message that triggered this ticket) "
            "at the TOP LEVEL of the tool arguments — NOT inside payload_json. "
            "These three are forwarded as extra body fields and let the CRM "
            "render an `Open Respond.io conversation` link plus a reference "
            "to the source message on the ticket detail page. Omit any you "
            "genuinely don't have; do not fabricate. "
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
        body_params=("payload_json", "contact_id", "space_id", "message_id"),
        module="tickets",
    ),
)
