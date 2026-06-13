"""Build capability documents for MCP Tool-RAG indexing.

The RAG retrieves MCP tools using pgvector cosine similarity over `embedding_chunks`.
For every MCP tool we emit:
  - a rich `body_text` (tool name, category, intent, description, path, params),
  - a set of disjoint `typical_user_questions` modelled after the n8n
    `next_agents/*` prompts (general enquiries, order status, incoming stock,
    marketing/forms, stock inquiries, purchase request/sponsorship, complaint),
  - alias phrases derived from the tool name.

Both the body and the question bank are chunked and embedded, so the tool's real
purpose — not just hand-picked phrases — drives retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import sys
from typing import Any


@dataclass(frozen=True)
class CapabilityDoc:
    source_id: str
    source_key: str
    title: str
    body_text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    description: str
    typical_user_questions: list[str]
    category: str | None = None
    implementation_status: str = "planned"
    required_fields: list[str] | None = None
    optional_fields: list[str] | None = None


@dataclass(frozen=True)
class ToolIntent:
    """Prompt-aligned intent metadata for one MCP tool."""

    category: str
    intent: str
    description: str
    typical_user_questions: tuple[str, ...]
    aliases: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Prompt-aligned intent catalog (next_agents/*)
# ---------------------------------------------------------------------------
# Categories mirror the sub-prompts:
#   general_enquiries.product          → crm_master_products_*
#   general_enquiries.promotion        → crm_marketing_promotions_* / campaign_*
#   general_enquiries.attachment       → crm_resource_* / crm_master_product_attachments_*
#   general_enquiries.stock            → crm_inventory_stock_balance_* / alerts / dashboard
#   general_enquiries.lead_time        → product supplier lead time (see note below)
#   general_enquiries.incoming_stock   → crm_procurement_packing_lists_* / spo_allocations_*
#   order_enquiries                    → crm_order_management_*
#   marketing_agent.marketing_assets   → crm_forms_management_* / crm_workflow_forms_*
#   stock_inquiries.form_submission    → crm_forms_stock_inquiries_*
#   purchase_request.form_submission   → crm_forms_purchase_requests_*
#   complaint.form_submission          → crm_forms_complaints_* / entity_attachments
#   sla_management                     → crm_sla_*
# ---------------------------------------------------------------------------


# Tools that exist in the MCP CATALOG but must NOT be seeded into the
# Tool-RAG embedding pool nor auto-enabled on assistants. Keep the MCP HTTP
# tools available for direct n8n / external callers, but hide them from the
# AI assistant's tool-search noise. Removal driven by ops decision; tools
# are not in active product use.
_EMBEDDING_SKIP_TOOLS: set[str] = {
    "crm_forms_stock_inquiries_list",
    "crm_forms_stock_inquiries_get",
    "crm_forms_purchase_requests_list",
    "crm_forms_purchase_requests_get",
    "crm_forms_complaints_list",
    "crm_forms_complaints_get",
    "crm_commercial_projects_create_smart",
    "crm_commercial_projects_edit",
    "crm_commercial_projects_get",
    "crm_commercial_projects_list",
    "crm_workflow_forms_submissions_list",
    "crm_workflow_forms_submissions_get",
    "crm_workflow_forms_submissions_allowed_transitions",
    # Discontinued — removed from MCP catalog. Skip set keeps the persisted
    # mcp_tools row out of RAG + auto-removes it from ai_assistant_configs
    # enabled_tools on the next `_sync_enabled_tools` pass.
    "crm_incoming_stock_grn",
}


TOOL_INTENTS: dict[str, ToolIntent] = {
    # ==================================================================
    # MASTER DATA — product catalog, brands, categories, UOMs, attachments
    # ==================================================================
    "crm_master_products_list": ToolIntent(
        category="general_enquiries.product",
        intent="Search the structured product master (SKU rows with price, dimensions, brand, category).",
        description=(
            "Search and list rows from the structured product master table (SKU / product_code / "
            "product_name / description / brand / category / price / dimensions). Use this when the "
            "user wants STRUCTURED PRODUCT ROWS — by keyword (e.g. 'matte black kitchen sink'), brand, "
            "category, price range, or physical size."
            "`query` is a free-text LIKE search over product_code/product_name/description ONLY — NEVER pass "
            "numeric or comparison expressions like 'price > 100' or 'dimensions > 300mm' as `query`; use the "
            "dedicated parameters instead. "
            "PRICE: price_min, price_max (MYR). "
            "DIMENSIONS (millimetres, populated from descriptions like '(650x450x210MM)'): per-axis "
            "length_min/length_max, width_min/width_max, height_min/height_max. For axis-agnostic asks like "
            "'products with dimensions over 300mm' or 'anything bigger than 1m on any side', use "
            "any_dimension_min / any_dimension_max — these match when ANY of L/W/H is in range. "
            "FILTERS vs SORT — keep these separate: any_dimension_min/max, length_min/max, width_min/max, "
            "height_min/max, price_min/max are FILTERS (range caps), NOT valid sort keys; passing them as "
            "`sort` falls back to created_at silently. "
            "Sortable fields: created_at, updated_at, product_code, product_name, list_price (alias: price), "
            "cost_price, invoice_price, is_active, dimensions_length (alias: length), dimensions_width "
            "(alias: width), dimensions_height (alias: height), largest_dimension (GREATEST(L,W,H) per row — "
            "use sort=largest_dimension&dir=desc for 'biggest product on any side'), smallest_dimension "
            "(LEAST(L,W,H) per row). Combine with dir=asc|desc. NULL dimensions sort to the bottom either way. "
            "Each row carries an ISO 4217 `currency` (default MYR for all Sorento product rows). "
            "When showing prices to a user, ALWAYS render the currency code from the row "
            "(e.g. 'RM 1,250.00' or 'MYR 1,250.00'). Never assume USD/$. "
            "Each row also carries `is_discontinued` (auto-derived from descriptions that start "
            "with `****`). When True, surface the SKU as discontinued / end-of-life in the answer."
        ),
        typical_user_questions=(
            "What products do you sell?",
            "List all SKUs available in Sorento.",
            "Do you sell matte black kitchen sinks?",
            "Show me bathtubs / toilets / basins / faucets.",
            "What items do you have under the bathroom category?",
            "Find products by brand or category.",
            "Show product list with pricing.",
            "I want to see product information and list price in MYR.",
            "Do you have any products with length between 300 and 500 mm?",
            "Show products with width over 500mm.",
            "Find products with height under 200mm.",
            "Any products with dimensions larger than 1 metre on any side?",
            "Products that are at least 600mm long.",
            "List products by size — anything between 400 and 800mm.",
            "Which products fit within 500mm x 500mm x 500mm?",
            "Show me products under MYR 100.",
            "Products priced between RM500 and RM2000.",
            "Find SKUs by L W H dimensions.",
            "What is the biggest bathtub we have?",
            "Show me the largest product we carry.",
            "Smallest faucet by dimension.",
            "Top 5 products by length.",
            "Sort products by largest side, descending.",
            "Which product has the biggest height?",
        ),
        aliases=(
            "master products list",
            "product master",
            "product SKU search",
            "products we sell",
            "products by size",
            "products by dimensions",
            "products by length",
            "products by width",
            "products by height",
            "filter products by price",
        ),
    ),
    "crm_master_products_get": ToolIntent(
        category="general_enquiries.product",
        intent="Fetch full detail for a single product by its UUID.",
        description=(
            "Get one product record by UUID id, returning code, name, description, brand/category "
            "relations, and full pricing fields. Use AFTER crm_master_products_list has resolved a "
            "product's UUID, or when the user pastes a UUID. For keyword / SKU / name searches use "
            "crm_master_products_list instead. The response includes `is_discontinued` (auto-derived "
            "from descriptions starting with `****`) — surface this in the answer when True."
        ),
        typical_user_questions=(
            "Show full product detail for this product id.",
            "Open this product record and show all fields.",
            "Get the complete profile for this product UUID.",
            "Retrieve pricing and description for this specific product id.",
            "Fetch the product record behind this id.",
        ),
        aliases=("get product by id", "product detail by uuid"),
    ),
    "crm_master_products_select": ToolIntent(
        category="general_enquiries.product",
        intent="Lightweight product picker for dropdowns / typeaheads.",
        description=(
            "Minimal active-only product list intended for dropdown or select-control population. "
            "Prefer crm_master_products_list for user-facing product search. "
            "Rows include `is_discontinued` (auto-derived from descriptions starting with `****`)."
        ),
        typical_user_questions=(
            "Give me a lightweight product list for a dropdown.",
            "I need product options for a select control.",
            "Fetch active products for an autocomplete input.",
        ),
        aliases=("products for dropdown", "product select options"),
    ),
    "crm_master_brands_list": ToolIntent(
        category="general_enquiries.product",
        intent="List brands Sorento carries.",
        description="List brands with pagination and keyword filter. Use for brand discovery questions.",
        typical_user_questions=(
            "What brands do you carry?",
            "List all brands in the system.",
            "Show available brands for filtering products.",
        ),
        aliases=("brand list", "list brands"),
    ),
    "crm_master_brands_get": ToolIntent(
        category="general_enquiries.product",
        intent="Get one brand by id.",
        description="Fetch a single brand record by its UUID id.",
        typical_user_questions=(
            "Show brand details for this id.",
            "Open this brand record.",
        ),
    ),
    "crm_master_brands_select": ToolIntent(
        category="general_enquiries.product",
        intent="Brands for select controls.",
        description="Lightweight brand list for dropdowns.",
        typical_user_questions=("Give me brands for a dropdown.",),
    ),
    "crm_master_product_categories_list": ToolIntent(
        category="general_enquiries.product",
        intent="List product categories.",
        description="Flat list of product categories with pagination and query filter.",
        typical_user_questions=(
            "List the product categories.",
            "What categories are available?",
            "Show me all product categories.",
        ),
    ),
    "crm_master_product_categories_tree": ToolIntent(
        category="general_enquiries.product",
        intent="Hierarchical product category tree.",
        description="Tree structure of product categories including parent/child relationships.",
        typical_user_questions=(
            "Show the category tree.",
            "I want the full product category hierarchy.",
        ),
    ),
    "crm_master_product_categories_get": ToolIntent(
        category="general_enquiries.product",
        intent="Get one product category by id.",
        description="Single category detail record.",
        typical_user_questions=("Show category detail for this id.",),
    ),
    "crm_master_product_categories_select": ToolIntent(
        category="general_enquiries.product",
        intent="Categories for select controls.",
        description="Lightweight product category list for dropdowns.",
        typical_user_questions=("Categories for a dropdown.",),
    ),
    "crm_master_units_of_measure_list": ToolIntent(
        category="general_enquiries.product",
        intent="List units of measure (UOM).",
        description="List UOMs used for products.",
        typical_user_questions=(
            "List all units of measure.",
            "What UOMs do we support?",
        ),
    ),
    "crm_master_units_of_measure_get": ToolIntent(
        category="general_enquiries.product",
        intent="Get one UOM by id.",
        description="Single UOM record.",
        typical_user_questions=("Get this UOM record.",),
    ),
    "crm_master_units_of_measure_select": ToolIntent(
        category="general_enquiries.product",
        intent="UOMs for select controls.",
        description="Lightweight UOM list for dropdowns.",
        typical_user_questions=("UOM options for a dropdown.",),
    ),
    "crm_master_product_attachments_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="Find product attachments (brochures, datasheets, certificates) linked to a product, optionally narrowed by attachment type.",
        description=(
            "List product↔attachment links filtered by product_ids (canonical product UUIDs), "
            "attachment_ids (canonical attachment UUIDs), and / or attachment_type_ids (canonical "
            "AttachmentType UUIDs — narrows to a doc class such as brochure, spec sheet, datasheet, "
            "manual, installation guide, or certificate). Use this when the user asks for product "
            "brochures, datasheets, certificates, test reports, or installation guides tied to a SKU "
            "— combine product_ids + attachment_type_ids to fetch only the SKU's brochure (or only its "
            "spec sheet, etc.). Not for global stock-list documents (use "
            "crm_resource_attachments_current_stock_list) and not for promotion flyers (use "
            "crm_marketing_promotion_attachments_list)."
        ),
        typical_user_questions=(
            "Can I get the brochure for this product?",
            "Send me the datasheet for SKU X.",
            "Find the technical certificate / test report for this product code.",
            "Show attachments for this product.",
            "Is there an installation guide document linked to this product?",
            "Show only the spec sheets for this product.",
            "Give me the brochure attachment type for this SKU, not the certificate.",
            "Filter product documents by attachment type id.",
        ),
        aliases=(
            "product brochures",
            "product datasheets",
            "product attachments by type",
            "product docs filtered by attachment type",
        ),
    ),
    "crm_master_product_attachments_by_product": ToolIntent(
        category="general_enquiries.attachment",
        intent="All attachments for a specific product.",
        description=(
            "Returns every attachment linked to one product, given its UUID or product code. "
            "Preferred when the user is asking for the full set of documents for a specific SKU."
        ),
        typical_user_questions=(
            "Give me all documents for product SKU X.",
            "List every attachment for this product code.",
            "What marketing/technical files do we have for this specific product?",
        ),
    ),
    "crm_master_product_attachments_get": ToolIntent(
        category="general_enquiries.attachment",
        intent="Get one product-attachment link by id; also serves product photo / image / visual look-up requests.",
        description=(
            "Single product-attachment link record. Also the entry point when the user asks to see the "
            "product's photo, image, or how the product looks — the returned attachment carries the "
            "preview/CDN URL the agent renders inline."
        ),
        typical_user_questions=(
            "Get this product attachment link record.",
            "Can I get the photos?",
            "Can I see the photo?",
            "Show me the picture of this product.",
            "How does it look like?",
            "What does this product look like?",
            "Send me an image of this product.",
            "Do you have a photo of this SKU?",
        ),
        aliases=("product photo", "product image", "product picture", "product look"),
    ),
    # ==================================================================
    # MARKETING — promotions, promotion products, promo attachments, campaigns
    # ==================================================================
    "crm_marketing_promotions_list": ToolIntent(
        category="general_enquiries.promotion",
        intent="List and search promotions; defaults to active with auto-fallback to historical when none match.",
        description=(
            "List promotion headers (summary fields + linked attachments inline; no product lines). "
            "Each row carries its `attachments` array — the agent does NOT need to call "
            "crm_marketing_promotion_attachments_* afterwards to get the promotion document. "
            "Default returns ACTIVE promotions (is_active=true AND today within start_date/end_date); "
            "when the caller passes a narrowing filter (query, period_from/period_to, "
            "user_type) and zero active match, the tool automatically falls back to INACTIVE matches "
            "and sets fallback_used=true on the response so the agent can phrase the answer accordingly. "
            "Every row carries `is_expired` (true = not currently live: flag off or today outside "
            "start/end) — when true, tell the user the promotion was FOUND but is EXPIRED; never "
            "present an is_expired row as live. Pass active=false when the user explicitly asks for "
            "inactive / expired / historical promotions (no fallback). Use period_from / period_to "
            "(YYYY-MM-DD) to scope by date; `date_mode` picks which promotion date the window tests: "
            "`overlap` (default) = promotion active any time during the window ('promotions valid/running "
            "during X'); `started` = start_date within the window ('promotions released/launched/new in "
            "the last X days'); `ended` = end_date within the window ('promotions that ended/expired in "
            "X'). started/ended automatically include BOTH active and historical rows — do not pass "
            "`active` with them unless the user explicitly narrows to one state. For SKU coverage / "
            "promotion line items use crm_marketing_promotion_products_list."
        ),
        typical_user_questions=(
            "What promotions are active now?",
            "Any promotions for product PRD123?",
            "Show me current Sorento promotions.",
            "Are there any historical promotions for this product?",
            "List historical promotions between 2025-01-01 and 2025-03-31.",
            "What promotions ran in Q1 2025?",
            "What promotions were released in the last 10 days?",
            "Which promotions expired last month?",
            "Find the promotion with code MIX01.",
            "Did we run a promo for this SKU last year?",
        ),
        aliases=("list promotions", "active promos", "historical promotions", "past promotions"),
    ),
    "crm_marketing_promotions_get": ToolIntent(
        category="general_enquiries.promotion",
        intent="Fetch one promotion's metadata, groups, and attachments by id.",
        description=(
            "Get promotion metadata (name, start/end dates, FOC tiers/groups) AND linked "
            "attachments inline on the same response — no second tool call needed for the promotion "
            "document. Does not include product lines by default — set include_products=true only if "
            "the user is asking specifically about the SKU coverage."
        ),
        typical_user_questions=(
            "Give me the full metadata for this promo.",
            "Open promotion details for this id.",
            "When does this promotion start and end?",
            "Show me the promotion document / attachment for this promo.",
        ),
    ),
    "crm_marketing_promotion_products_list": ToolIntent(
        category="general_enquiries.promotion",
        intent="Paged promotion product lines (which SKUs are under which promo).",
        description=(
            "Promotion product lines, paginated. Each row carries the parent promotion's "
            "`promotion_attachments` array inline — the agent does NOT need to call "
            "crm_marketing_promotion_attachments_* afterwards to surface the promotion document. "
            "Optional promotion_id scopes to one promotion (UUID). Optional query "
            "filters by SKU/name/promotion description and can run without promotion_id to discover which "
            "promotions a product participates in. Use when the user asks for the SKUs included "
            "in a promotion, or which promotions a product participates in."
        ),
        typical_user_questions=(
            "Which products are included in promo MIX01?",
            "List the SKUs under this promotion.",
            "Show the item lines in this promo campaign.",
            "Is product SKU X part of any active promotion?",
        ),
    ),
    "crm_marketing_promotion_products_nested": ToolIntent(
        category="general_enquiries.promotion",
        intent="All product lines for one promotion, nested under the promotion id.",
        description=(
            "Products linked to a promotion, returned nested under the promotion id. Each line "
            "carries the parent promotion's `promotion_attachments` inline so the agent has the "
            "promotion document on the same response — no follow-up tool call required."
        ),
        typical_user_questions=(
            "Give me every product under this one promotion.",
            "Show all SKUs nested under this promo.",
        ),
    ),
    "crm_marketing_promotion_attachments_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="Find promotion attachments (flyers, brochures, sales kits) by promotion or product context.",
        description=(
            "List/search promotion↔attachment links. Optional promotion_id scopes one promotion; "
            "optional query searches promotion header details, product code/name, promotion group "
            "name, and attachment metadata. Use for promo flyers, promotional brochures, campaign "
            "collateral. Not for product datasheets (crm_master_product_attachments_*) and not for "
            "global docs (crm_resource_attachments_*)."
        ),
        typical_user_questions=(
            "Send me the promotion flyer for MIX01.",
            "Do you have the promo brochure for this campaign?",
            "I need the promotion sales kit attachment.",
            "Attach the promotional flyer PDF.",
        ),
    ),
    "crm_marketing_promotion_attachments_by_promotion": ToolIntent(
        category="general_enquiries.attachment",
        intent="All attachments for one promotion.",
        description="Fetch every attachment linked to the given promotion (UUID).",
        typical_user_questions=(
            "Give me every document for this promotion.",
            "List all attachments for promo code MIX01.",
        ),
    ),
    "crm_marketing_promotion_attachments_get": ToolIntent(
        category="general_enquiries.attachment",
        intent="Get one promotion-attachment link by id.",
        description="Single promotion-attachment link record.",
        typical_user_questions=("Get this promotion attachment link record.",),
    ),
    "crm_marketing_campaigns_list": ToolIntent(
        category="general_enquiries.promotion",
        intent="List marketing campaigns.",
        description="List marketing campaign headers.",
        typical_user_questions=(
            "What marketing campaigns are running?",
            "List campaigns.",
        ),
    ),
    "crm_marketing_campaigns_get": ToolIntent(
        category="general_enquiries.promotion",
        intent="Get one marketing campaign by id.",
        description="Single marketing campaign record.",
        typical_user_questions=("Open this campaign.",),
    ),
    "crm_marketing_campaign_types_list": ToolIntent(
        category="general_enquiries.promotion",
        intent="List campaign types.",
        description="Reference list of campaign types.",
        typical_user_questions=("List campaign types.",),
    ),
    "crm_marketing_campaign_types_get": ToolIntent(
        category="general_enquiries.promotion",
        intent="Get one campaign type by id.",
        description="Single campaign type record.",
        typical_user_questions=("Get this campaign type.",),
    ),
    # ==================================================================
    # RESOURCE MANAGEMENT — global attachments & directories (stock list, global docs)
    # ==================================================================
    "crm_resource_attachments_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="Search the global document library (product catalogue PDFs, brochures, price lists, general docs).",
        description=(
            "List file attachments across entities with filters: free-text query, entity_type, "
            "entity_id, directory_id, is_deleted. THIS IS THE PRIMARY TOOL FOR PRODUCT CATALOGUE / "
            "CATALOG / BROCHURE / PRICE LIST DOCUMENT REQUESTS — the full Sorento product catalogue "
            "PDF lives in the global document library, not on individual SKU rows. Use this tool "
            "whenever the user asks for 'the catalogue', 'catalog', 'product catalogue', 'master "
            "catalogue', 'brochure PDF', 'price list document', or any general company document. "
            "Pass the user's keyword (e.g. 'catalogue', 'price list') as `query` to filter. "
            "Only fall through to crm_master_product_attachments_list when the user is asking about "
            "a SPECIFIC SKU's brochure/datasheet/spec sheet (named product + document together); for "
            "the standing 'Stock List' PDF use crm_resource_attachments_current_stock_list."
        ),
        typical_user_questions=(
            "Send me the catalogue.",
            "Do you have a catalog I can look at?",
            "Share the Sorento product catalogue.",
            "I need the latest product catalogue PDF.",
            "Where can I download the master catalogue?",
            "Email me the brochure / company brochure.",
            "Send the price list document.",
            "Do you have the price list PDF?",
            "Search the document library for this keyword.",
            "Find an uploaded file by name.",
            "Do you have a file in the company directory called X?",
        ),
        aliases=(
            "catalogue",
            "catalog",
            "product catalogue",
            "product catalog PDF",
            "master catalogue",
            "company brochure",
            "price list document",
            "document library",
            "global attachments",
        ),
    ),
    "crm_resource_attachments_catalogue": ToolIntent(
        category="general_enquiries.attachment",
        intent="Resolve catalogue attachment UUIDs to metadata / signed URLs (catalogue domain only).",
        description=(
            "DOMAIN-SCOPED catalogue tool. Pre-filtered server-side to "
            "AttachmentType=catalogue (the Sorento product catalogue PDFs). "
            "n8n's catalogue-hinted agent passes one or more known attachment "
            "UUIDs in `attachment_ids` (csv / JSON / repeated) and gets back "
            "the catalogue rows for those UUIDs only — non-catalogue UUIDs are "
            "dropped by the backend code filter. REQUIRED: `attachment_ids`; "
            "without UUIDs the tool returns an empty page (it does NOT browse "
            "the catalogue library). For free-text catalogue / brochure / "
            "price-list discovery use crm_resource_attachments_list instead. "
            "Set resolve_signed_urls=true to include signed preview/download "
            "URLs in the response."
        ),
        typical_user_questions=(
            "Resolve these catalogue attachment UUIDs to file metadata.",
            "Give me the signed download URL for this catalogue document UUID.",
            "Fetch the catalogue PDF row for this attachment id.",
            "Confirm these UUIDs are catalogue documents and return their files.",
            "Get metadata for the catalogue attachments I already identified.",
        ),
        aliases=(
            "catalogue attachment lookup",
            "catalogue by uuid",
            "catalogue domain tool",
            "scoped catalogue resolver",
            "n8n catalogue domain hint",
        ),
    ),
    "crm_resource_attachments_current_stock_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="Fetch the latest published Stock List document.",
        description=(
            "Returns the latest Stock List attachment row when configured. Use whenever the user "
            "asks for 'the stock list', 'current stock list PDF', or 'latest price/stock list doc'."
        ),
        typical_user_questions=(
            "Send me the latest stock list document.",
            "I need the current stock list PDF.",
            "Can you share the latest price/stock list file?",
        ),
        aliases=("stock list document", "latest stock list"),
    ),
    "crm_resource_attachments_get": ToolIntent(
        category="general_enquiries.attachment",
        intent="Get attachment metadata by id (includes linked entities).",
        description="Single attachment record with linked entity references.",
        typical_user_questions=("Show attachment metadata for this id.",),
    ),
    "crm_resource_attachments_download": ToolIntent(
        category="general_enquiries.attachment",
        intent="Download raw attachment bytes (prefer metadata or preview URL tools).",
        description=(
            "Downloads attachment bytes (binary; may be large). Prefer metadata or preview URL "
            "tools for normal user-facing flows."
        ),
        typical_user_questions=("Download the binary contents of this attachment.",),
    ),
    "crm_resource_attachments_metadata": ToolIntent(
        category="general_enquiries.attachment",
        intent="Attachment metadata only.",
        description="Metadata for one attachment (no entity links).",
        typical_user_questions=("Just the metadata of this attachment.",),
    ),
    "crm_resource_attachments_preview_url": ToolIntent(
        category="general_enquiries.attachment",
        intent="Signed preview URL for an attachment.",
        description="Returns a signed URL to preview an attachment.",
        typical_user_questions=(
            "Give me a preview link for this attachment.",
            "I need a signed URL to view this file.",
        ),
    ),
    "crm_resource_attachment_types_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="List attachment types.",
        description="Reference list of attachment types.",
        typical_user_questions=("List attachment types.",),
    ),
    "crm_resource_attachment_types_get": ToolIntent(
        category="general_enquiries.attachment",
        intent="Get one attachment type by id.",
        description="Single attachment type record.",
        typical_user_questions=("Get this attachment type.",),
    ),
    "crm_resource_directories_list": ToolIntent(
        category="general_enquiries.attachment",
        intent="List directories under an optional parent.",
        description="List directories under optional parent_id for folder navigation.",
        typical_user_questions=(
            "List folders under this parent.",
            "Show the document directories.",
        ),
    ),
    "crm_resource_directories_tree": ToolIntent(
        category="general_enquiries.attachment",
        intent="Directory tree, optionally trash.",
        description="Directory tree; use deleted=true for trash tree.",
        typical_user_questions=("Show the directory tree.",),
    ),
    "crm_resource_directories_get": ToolIntent(
        category="general_enquiries.attachment",
        intent="Get one directory by id.",
        description="Single directory record.",
        typical_user_questions=("Open this directory.",),
    ),
    # ==================================================================
    # INVENTORY — stock balance, alerts, dashboard, ledger, batches
    # ==================================================================
    "crm_inventory_stock_balance_list": ToolIntent(
        category="general_enquiries.stock",
        intent="Current stock balance per product and warehouse (how much we have).",
        description=(
            "Paged stock balances with warehouse / product / quantity filters. Use for 'how much "
            "stock do we have', 'stock availability', 'sufficient stock?', warehouse-level balance. "
            "THIS IS NOT FOR TRANSACTION / MOVEMENT HISTORY — use crm_inventory_stock_ledger_list "
            "for stock movement/ledger;"
        ),
        typical_user_questions=(
            "How much stock do we have for this SKU?",
            "Check stock availability by warehouse for this product code.",
            "Is there sufficient stock for 30 units of this item?",
            "Show current on-hand balance per warehouse.",
            "Stock quantity remaining for this product.",
        ),
        aliases=("stock balance", "stock on hand", "stock availability"),
    ),
    "crm_inventory_stock_balance_export": ToolIntent(
        category="general_enquiries.stock",
        intent="Export full stock balance (no pagination).",
        description=(
            "Export all stock-balance rows with optional filters; requires export permission "
            "on the act-as user. Use for 'export stock balance', 'download all stock'."
        ),
        typical_user_questions=(
            "Export the full stock balance.",
            "I need a dump of all stock levels.",
        ),
    ),
    "crm_inventory_stock_dashboard": ToolIntent(
        category="general_enquiries.stock",
        intent="Aggregated stock dashboard metrics.",
        description="Aggregated stock dashboard: totals, KPIs, distribution.",
        typical_user_questions=(
            "Show the stock dashboard summary.",
            "Give me stock KPIs and totals.",
        ),
    ),
    "crm_inventory_stock_alerts": ToolIntent(
        category="general_enquiries.stock",
        intent="Low-stock / reorder alerts.",
        description="Low-stock style alerts from API (items below threshold / approaching minimum).",
        typical_user_questions=(
            "What SKUs are low in stock?",
            "Show reorder / low-stock alerts.",
            "Which items are running out?",
        ),
    ),
    "crm_inventory_stock_ledger_list": ToolIntent(
        category="general_enquiries.stock_ledger",
        intent="Stock transaction / movement history across the whole ledger.",
        description=(
            "Global stock ledger (inventory TRANSACTION HISTORY: IN, OUT, TRANSFER, ADJUSTMENT). "
            "Use ONLY when the user explicitly asks for stock movements, stock history, ledger "
            "entries, or transaction audit trail."
        ),
        typical_user_questions=(
            "Show me the stock ledger transaction history.",
            "List recent stock movements (IN / OUT / transfer / adjustment).",
            "Audit trail of inventory transactions for this SKU.",
            "Stock ledger entries for this warehouse.",
        ),
        aliases=("stock ledger", "stock transactions", "inventory movement history"),
    ),
    "crm_inventory_stock_ledger_by_product_warehouse": ToolIntent(
        category="general_enquiries.stock_ledger",
        intent="Stock ledger for one specific product in one specific warehouse.",
        description=(
            "Ledger (transaction history) for one product in one warehouse. Not for balance — "
            "use crm_inventory_stock_balance_list for current on-hand quantity."
        ),
        typical_user_questions=(
            "Ledger history for this product at this warehouse.",
            "Show transactions for SKU X in warehouse Y.",
        ),
    ),
    "crm_inventory_stock_batches_list": ToolIntent(
        category="general_enquiries.stock",
        intent="List stock batches (lot numbers) by product and warehouse.",
        description="List stock batches (lot / batch number records) with product and warehouse filters.",
        typical_user_questions=(
            "List batch numbers for this SKU.",
            "Show stock batches in this warehouse.",
        ),
    ),
    "crm_inventory_stock_batches_get": ToolIntent(
        category="general_enquiries.stock",
        intent="Get stock batch by id.",
        description="Single batch detail record.",
        typical_user_questions=("Show this batch record.",),
    ),
    "crm_inventory_warehouses_list": ToolIntent(
        category="general_enquiries.stock",
        intent="List warehouses.",
        description="List warehouse records.",
        typical_user_questions=(
            "What warehouses do we have?",
            "List Sorento warehouse locations.",
        ),
    ),
    "crm_inventory_warehouses_get": ToolIntent(
        category="general_enquiries.stock",
        intent="Get warehouse by id.",
        description="Single warehouse record.",
        typical_user_questions=("Open this warehouse.",),
    ),
    "crm_inventory_storage_zones_list": ToolIntent(
        category="general_enquiries.stock",
        intent="List storage zones within warehouses.",
        description="List storage zone records with optional warehouse filter.",
        typical_user_questions=("List storage zones in this warehouse.",),
    ),
    "crm_inventory_storage_zones_tree": ToolIntent(
        category="general_enquiries.stock",
        intent="Storage zone tree.",
        description="Hierarchical tree of storage zones by warehouse.",
        typical_user_questions=("Show the storage zone tree.",),
    ),
    "crm_inventory_storage_zones_get": ToolIntent(
        category="general_enquiries.stock",
        intent="Get storage zone by id.",
        description="Single storage zone record.",
        typical_user_questions=("Open this storage zone.",),
    ),
    # ==================================================================
    # ORDER MANAGEMENT — order status, delivery, logistics, orders by product
    # ==================================================================
    "crm_order_management_orders_list": ToolIntent(
        category="order_enquiries",
        intent="Find and track customer orders by number, debtor, status, or order date, including standalone delivery-order (DO) searches by customer/date filters.",
        description=(
            "List orders with filters (customer_id / order_status_id / has_order_lines / order_date "
            "range / optional actual delivery date / free-text `query` over order_number, debtor_code, "
            "debtor_name, customer name/code). "
            "External/AI-agent callers are HARD-CAPPED at limit=10 server-side regardless of the value "
            "sent — narrow with customer_query / product_query / order_date_from / order_date_to instead "
            "of asking for more rows. "
            "Also supports delivery-order lookup filters: `customer_query` (debtor/customer partial), "
            "`product_query` (product code/name partial), and order_date range. "
            "FILTER REQUIREMENT: customer (customer_id / customer_query), product (product_query), and "
            "order date range (order_date_from / order_date_to) are NOT all required together. ANY ONE "
            "of them is enough — call the tool as soon as the user supplies at least one. Combine more "
            "filters only when the user explicitly provides them. Do NOT block on missing filters. "
            "DEFAULT SORT: results are returned latest order first (sort=order_date, dir=desc) so the "
            "most recent matching order surfaces at the top — do not pass sort/dir unless the user "
            "explicitly asks for a different order. "
            "DATE FILTER RULE: For DO discovery and any bare 'orders in [today/yesterday/this week/"
            "month/period/date range]' question, DEFAULT to actual_delivery_date_from/"
            "actual_delivery_date_to. Only use order_date_from/order_date_to when the user EXPLICITLY "
            "mentions the order/placement date (verbs: 'placed', 'created', 'raised', 'opened', "
            "'booked', or the literal phrase 'order date'). Delivery verbs ('delivered', 'received', "
            "'dropped off', 'for delivery', 'pending delivery', 'arrived', 'delivery date') and bare "
            "time windows ('today', 'yesterday', 'this week', 'February 2026') => "
            "actual_delivery_date_from/_to. Never pass both date families in one call unless the user "
            "asks for an intersection. "
            "Date params accept flexible formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, ISO "
            "datetime, 'YYYY-MM', 'MM/YYYY', or 'Month YYYY' (e.g. 'February 2026'). "
            "Use this tool whenever the user asks to search/find DO numbers from customer OR product OR "
            "date range filters (any one is sufficient). "
            "Use for 'order status', 'track my order', 'delivery date', 'lorry / transporter / driver', "
            "and customer-based order searches. NOT for orders filtered by a specific product — use "
            "crm_order_management_orders_by_product_list for that."
        ),
        typical_user_questions=(
            "What is the status of order ORD-12345?",
            "Track my order.",
            "When will order ORD-2026-001 be delivered?",
            "Show orders for customer ABC Corp / debtor code C001.",
            "Which lorry / transporter / driver is handling this order?",
            "List recent orders for this customer.",
            "Any delayed orders for this account?",
            "Find delivery orders for customer X in February 2026.",
            "Search DO numbers for debtor jayson in Feb 2026.",
        ),
        aliases=(
            "order status",
            "order tracking",
            "find delivery order",
            "find DO",
            "DO lookup",
            "orders in month",
        ),
    ),
    "crm_order_management_orders_get": ToolIntent(
        category="order_enquiries",
        intent="Get one CUSTOMER SALES order by its order_number or UUID.",
        description=(
            "Single customer-sales order detail including order lines. Call this when the user gives "
            "a CODE that the resolver has identified as entity_type=customer_order (e.g. RF2601-025, "
            "ORD-2026-001). Pass the canonical_code from the Resolved references block as "
            "`order_id`; the endpoint accepts either a UUID or an order_number. Do NOT call this "
            "tool with product codes, shipment numbers, SPO numbers, or GRN numbers — use the "
            "corresponding tool for those entity types instead."
        ),
        typical_user_questions=(
            "When is order RF2601-025 delivered?",
            "What is the status of order ORD-2026-001?",
            "Open this order and show its line items.",
            "Full order detail with lines.",
            "Who is the customer for this order?",
        ),
        aliases=("order detail", "order status by number", "track this order number"),
    ),
    "crm_order_management_orders_by_product_list": ToolIntent(
        category="order_enquiries",
        intent=(
            "Find CUSTOMER SALES orders that contain a specific PRODUCT, including standalone delivery-order (DO) searches by product + customer + date range."
        ),
        description=(
            "Distinct CUSTOMER SALES orders matched by product. Call this when the resolver has "
            "classified the code as entity_type=product AND the user is asking who bought / which "
            "sales orders contain this product, or when the user asks to search DO number(s) using "
            "product + customer + order date range filters. Pass the canonical_code (product_code / SKU) as "
            "`product_id`, optionally combined with explicit `customer_query` + `product_query` filters "
            "(or a customer/debtor partial match in `query`) and a "
            "date range. "
            "DATE FILTER RULE: For DO discovery and any bare 'orders in [today/yesterday/this week/"
            "month/period/date range]' question, DEFAULT to actual_delivery_date_from/"
            "actual_delivery_date_to. Only use order_date_from/order_date_to when the user EXPLICITLY "
            "mentions the order/placement date (verbs: 'placed', 'created', 'raised', 'opened', "
            "'booked', or literal 'order date'). Delivery verbs ('delivered', 'received', 'dropped "
            "off', 'for delivery', 'pending delivery', 'arrived', 'delivery date') and bare time "
            "windows ('today', 'yesterday', 'this week', 'February 2026') => "
            "actual_delivery_date_from/_to. Never pass both date families in one call unless the user "
            "asks for an intersection. "
            "Date params accept flexible formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, "
            "ISO datetime, 'YYYY-MM', 'MM/YYYY', or 'Month YYYY' (e.g. 'February 2026'). "
            "Each matched product line carries product_code / product_name, the ordered quantity, "
            "and the warehouse it ships from (warehouse_code / warehouse_name). "
            "This is about OUTGOING orders sold to customers — it is NOT about incoming stock, "
            "inbound shipments, SPO, PO, GRN, or procurement. For 'any incoming for product X' / "
            "'when is product X arriving' use crm_incoming_stock_by_product. For a single order "
            "lookup by order_number, use crm_order_management_orders_get."
        ),
        typical_user_questions=(
            "Which customers bought / ordered this product?",
            "Pending customer sales orders containing this product.",
            "Sales orders / outgoing orders for this SKU.",
            "Delayed customer deliveries for this product.",
            "Search delivery order numbers for customer CHIN KET, product code SCBD701, from 01 January 2026 to 31 January 2026.",
            "User wants to search for a Delivery Order with details: Customer name CHIN KET, Product code SCBD701, Order date from January 2026.",
            "Find the delivery order for customer X who bought product Y last month.",
        ),
        aliases=(
            "customer orders by product",
            "sales orders with a product",
            "who bought this SKU",
            "find delivery order by product",
            "DO lookup with product",
            "search delivery order",
            "search DO",
            "delivery order search",
        ),
    ),
    # ==================================================================
    # INCOMING STOCK — user-facing tools (redacted, business-rule compliant).
    # These are the PRIMARY tools for user enquiries about incoming stock. They hide
    # received/rejected quantities, SPO numbers, internal IDs; they compute
    # remaining_incoming_quantity and warehouse allocation summaries.
    # See: agent-prompt/next_agents/incoming_stock_enquiries.txt
    # ==================================================================
    "crm_incoming_stock_by_product": ToolIntent(
        category="general_enquiries.incoming_stock",
        intent="ONE-SHOT answer for 'any incoming for product X / SKU X' \u2014 returns pending quantity, warehouse allocations, per-shipment breakdown, ETA, and packing-list attachment in a single call.",
        description=(
            "ONE-SHOT tool for ALL product-centric incoming-stock questions. A single call returns "
            "everything the user needs: (1) a per-shipment breakdown \u2014 each entry has "
            "shipment_number, shipping_container_number, ETA, batch_number, remaining_incoming_quantity "
            "(computed as quantity_shipped - quantity_received; fully-received lines are auto-filtered "
            "out), packing-list attachment, and that shipment's warehouse_allocations (warehouse_code, "
            "warehouse_name, allocated_quantity from SPO allocations); (2) nearest "
            "estimated_arrival_date. Quantities and warehouse allocations are reported line-by-line "
            "per shipment \u2014 NOT pre-aggregated into a product total or a combined warehouse summary; "
            "sum across shipments yourself if the user asks for a grand total. Do NOT also "
            "call crm_incoming_stock_shipments, crm_incoming_stock_shipment_products, or "
            "crm_incoming_stock_shipment_attachment when answering a product-incoming question "
            "\u2014 this tool already includes all of their data. Never "
            "exposes received / rejected quantities, SPO numbers, or internal IDs. Accepts "
            "`product_id` (UUID or product_code / SKU) or a free-text `query`."
        ),
        typical_user_questions=(
            "Any incoming for this product / SKU?",
            "How much is pending / still coming for this SKU?",
            "Give me the packing list and ETA for this incoming product.",
            "Which warehouses is this incoming stock allocated to and how many to each?",
            "When is this SKU arriving?",
            "Where will this product be stocked when it arrives?",
        ),
        aliases=(
            "incoming for a product",
            "pending incoming stock for product",
            "arrival summary for SKU",
            "packing list for this product",
            "warehouse allocation for incoming product",
        ),
    ),
    "crm_incoming_stock_shipments": ToolIntent(
        category="general_enquiries.incoming_stock",
        intent="SHIPMENT-level summaries (not product-level): 'any incoming shipments?' / 'what is arriving this month?'.",
        description=(
            "Use ONLY for SHIPMENT-CENTRIC questions where the user has a shipment / container "
            "number or asks about shipments in aggregate. Do NOT use this for 'any incoming for "
            "product X' \u2014 use crm_incoming_stock_by_product, which already includes per-shipment "
            "breakdown. Returns shipment headers (shipment_number, shipping_container_number, "
            "estimated_arrival_date, total_remaining_incoming_quantity, distinct_products_incoming, "
            "packing-list attachment). Filters by `query` (shipment_number / container / BOL / "
            "invoice) and ETA range. Does NOT surface received quantities or internal IDs."
        ),
        typical_user_questions=(
            "Any incoming shipments right now?",
            "What is arriving this month?",
            "Tell me about shipment FJ24041192.",
            "Check container MSCU5475129.",
            "List packing lists still in transit.",
        ),
        aliases=(
            "incoming shipments",
            "inbound shipments overview",
            "pending packing lists",
            "arriving containers",
        ),
    ),
    "crm_incoming_stock_list": ToolIntent(
        category="general_enquiries.incoming_stock",
        intent="UNIFIED incoming stock: shipment-rooted with nested product lines. Covers BOTH 'incoming for product X' AND 'what is arriving this month / from supplier Y'.",
        description=(
            "ONE tool for ALL incoming-stock questions. Shipment-rooted: one row per still-incoming "
            "shipment (shipment_number, shipping_container_number, estimated_arrival_date, "
            "packing-list attachment) with a nested `lines[]` array \u2014 each line carries "
            "product_code, product_name, batch_number, remaining_incoming_quantity, and "
            "warehouse_allocations (warehouse_code, warehouse_name, allocated_quantity). "
            "For 'any incoming for product X / SKU X', pass `product_ids` (UUID or product_code) \u2014 "
            "lines are then filtered to those products. For 'what is arriving this month / from "
            "supplier Y / shipment Z', pass `eta_from`/`eta_to`, `supplier_ids`, or `shipment_ids`. "
            "NO aggregate totals "
            "are returned \u2014 sum the line remaining_incoming_quantity yourself for a product total "
            "or per-warehouse summary. Never exposes received / rejected quantities, SPO numbers, or "
            "internal IDs. At least one narrowing filter is required."
        ),
        typical_user_questions=(
            "Any incoming for this product / SKU?",
            "How much is still coming for this SKU and to which warehouse?",
            "What is arriving this month?",
            "Open shipments from supplier X.",
            "Tell me about shipment FJ24041192 / container MSCU5475129.",
            "Which products are still incoming and when do they arrive?",
        ),
        aliases=(
            "incoming stock",
            "incoming for a product",
            "incoming shipments",
            "what is arriving",
            "pending incoming stock",
        ),
    ),
    "crm_incoming_stock_shipment_products": ToolIntent(
        category="general_enquiries.incoming_stock",
        intent="List still-incoming products on ONE shipment identified by shipment number / container \u2014 not for product-centric questions.",
        description=(
            "Use ONLY when the user has a SHIPMENT NUMBER / container and asks 'what products are "
            "on this shipment?'. Do NOT use for 'any incoming for product X' \u2014 use "
            "crm_incoming_stock_by_product instead. Returns still-incoming products on the "
            "shipment (product_code, product_name, batch_number, remaining_incoming_quantity, "
            "per-product warehouse allocation) plus shipment header and packing-list attachment. "
            "Received / rejected data is hidden. `shipment_id` accepts UUID or any business "
            "reference (shipment_number, container, BOL, invoice)."
        ),
        typical_user_questions=(
            "What products are still incoming on this shipment?",
            "Show me the incoming products in this packing list / container.",
            "Does shipment FJ24041192 contain SKU ABC?",
        ),
        aliases=(
            "products incoming on shipment",
            "still-incoming items in packing list",
            "shipment incoming line items",
        ),
    ),
    "crm_incoming_stock_shipment_attachment": ToolIntent(
        category="general_enquiries.incoming_stock",
        intent="Fetch the packing-list file for ONE shipment identified by shipment number / container \u2014 not for product questions.",
        description=(
            "Use ONLY when the user EXPLICITLY asks for the packing-list file / shipment document "
            "for a specific SHIPMENT (by shipment_number, container, BOL, or invoice). Do NOT use "
            "this for product questions \u2014 crm_incoming_stock_by_product already includes the "
            "per-shipment attachment in its response. Returns filename, file_path (URL), and "
            "mime_type, or null if no attachment."
        ),
        typical_user_questions=(
            "Can I have the packing list file for shipment FJ24041192?",
            "Send me the shipment document for this container.",
            "Download the packing list for MSCU5475129.",
        ),
        aliases=(
            "packing list file for shipment",
            "shipment attachment file",
            "packing list download",
        ),
    ),
    # crm_incoming_stock_grn \u2014 DISCONTINUED. Removed from MCP catalog. GRN
    # lookups now go through `crm_procurement_grn_list` (admin) only; the
    # user-facing question "has a GRN been created?" is answered by
    # `crm_incoming_stock_by_product` (which already exposes per-shipment GRN
    # context in its response).
    # ==================================================================
    # PROCUREMENT — ADMIN / INTERNAL raw data (do NOT use for user enquiries).
    # These expose received/rejected quantities, SPO numbers, internal IDs. Kept
    # for back-office operations only. Category `internal_admin.procurement` keeps
    # them out of user-question retrieval.
    # ==================================================================
    "crm_procurement_packing_lists_list": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — raw packing list / inbound shipment headers with received quantity data.",
        description=(
            "Raw inbound shipment headers including received quantities, SPO allocation counts, "
            "and internal IDs. For user-facing 'any incoming shipments?' use "
            "crm_incoming_stock_shipments instead. Restricted to admin / back-office use."
        ),
        typical_user_questions=(
            "Admin: raw packing list headers with totals.",
            "Back-office: full shipment list with received counts.",
        ),
        aliases=("admin raw packing lists",),
    ),
    "crm_procurement_packing_lists_get": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — raw inbound shipment detail with received quantities, SPO allocations, and linked GRNs.",
        description=(
            "Raw shipment detail including quantity_received, SPO allocations, linked GRNs and "
            "internal IDs. For user-facing 'products still incoming on this shipment' use "
            "crm_incoming_stock_shipment_products instead."
        ),
        typical_user_questions=(
            "Admin: open raw packing list with received counts.",
            "Back-office: full SPO/GRN context for a shipment.",
        ),
        aliases=("admin raw packing list detail",),
    ),
    "crm_procurement_spo_allocations_grouped_by_shipment": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — raw SPO allocation aggregates per shipment.",
        description=(
            "Raw SPO allocation summaries grouped by shipment including receipt_status. For user-"
            "facing 'any incoming for product X' use crm_incoming_stock_by_product instead."
        ),
        typical_user_questions=("Admin: raw SPO aggregates grouped by shipment.",),
        aliases=("admin raw spo by shipment",),
    ),
    "crm_procurement_spo_allocations_grouped_by_spo": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — SPO allocations grouped by SPO number.",
        description="Raw SPO allocation groups by SPO number. Admin / back-office use only.",
        typical_user_questions=("Admin: group raw allocations by SPO number.",),
        aliases=("admin raw spo by number",),
    ),
    "crm_procurement_spo_allocations_list": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — flat list of raw SPO allocation rows with receipt_status and received/rejected quantities.",
        description=(
            "Raw SPO allocation rows exposing spo_number, allocated_quantity, quantity_received, "
            "quantity_rejected, receipt_status. For user-facing incoming-stock enquiries use the "
            "crm_incoming_stock_* tools."
        ),
        typical_user_questions=("Admin: raw SPO allocation rows with receipt data.",),
        aliases=("admin raw spo allocations",),
    ),
    "crm_procurement_spo_allocations_get": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — single raw SPO allocation with linked GRNs and receipt fields.",
        description="Raw SPO allocation detail. Admin / back-office use only.",
        typical_user_questions=("Admin: open one raw SPO allocation with GRN context.",),
        aliases=("admin raw spo detail",),
    ),
    "crm_procurement_grn_list": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — raw GRN / picking header list with statuses and totals.",
        description=(
            "Raw GRN / picking headers with picking_status, inspection_status, totals. For user-"
            "facing 'has a GRN been created?' use crm_incoming_stock_by_product (the per-shipment "
            "breakdown already surfaces GRN linkage)."
        ),
        typical_user_questions=("Admin: raw GRN list with totals.",),
        aliases=("admin raw GRN list",),
    ),
    "crm_procurement_grn_get": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — full raw GRN detail including picking lines and quantities.",
        description="Raw GRN with picking lines, quantity_expected, quantity_picked. Admin only.",
        typical_user_questions=("Admin: open one GRN with picking lines.",),
        aliases=("admin raw GRN detail",),
    ),
    "crm_procurement_picking_lines_list": ToolIntent(
        category="internal_admin.procurement",
        intent="ADMIN ONLY — raw picking (receipt) lines with quantities and discrepancies.",
        description="Raw picking lines. Admin / back-office use only.",
        typical_user_questions=("Admin: raw picking / receipt lines.",),
        aliases=("admin raw picking lines",),
    ),
    # ==================================================================
    # FORMS (marketing agent — marketing assets / application form lookup)
    # ==================================================================
    "crm_forms_management_forms_list": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Find application / marketing forms (flower stand, sponsorship, exhibition, renovation).",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "List application forms with optional query, language, and status filters. "
            "Free-text query matches code, name, and purpose. "
            "Returns ONLY the form name and its attachment_id (no code, purpose, type, language, "
            "version, or active flag) — the name to refer to it, the attachment_id to deliver the file."
        ),
        typical_user_questions=(
            "What forms do you have?",
            "Show me the sponsorship application form.",
            "Do you have an exhibition form?",
            "Flower stand application form.",
            "Annual dinner sponsorship form in English / Chinese / Malay.",
            "Renovation form I can download.",
            "I want to applly for renovation. Can I have the form?"
        ),
        aliases=("application form", "sponsorship form lookup", "flower stand form"),
    ),
    "crm_forms_management_forms_get": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Get one form by id.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Single form record. Supports optional contact_id and space_id scope params for consistency "
            "with other crm_forms_* tools."
        ),
        typical_user_questions=("Open this form by id.",),
    ),
    "crm_workflow_forms_definitions_list": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="List workflow form definitions.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "List workflow form definitions. Use q for search (alias `query` is also accepted and "
            "mapped to q). Different from forms — these drive workflow submissions."
        ),
        typical_user_questions=(
            "List workflow form definitions.",
            "What workflow forms are available?",
            "Search workflow form templates by keyword.",
        ),
    ),
    "crm_workflow_forms_definitions_published_for_submission": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="List workflow forms currently published for user submission.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Published workflow form definitions visible to submitters."
        ),
        typical_user_questions=(
            "What workflow forms can I submit right now?",
            "List active forms I'm allowed to submit.",
        ),
    ),
    "crm_workflow_forms_definitions_get": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Get a workflow form definition by id.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Single workflow form definition record."
        ),
        typical_user_questions=("Open this workflow form definition.",),
    ),
    "crm_workflow_forms_definitions_preview": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Preview a workflow form schema (draft or published).",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Preview draft or published workflow form schema (source=draft|published)."
        ),
        typical_user_questions=(
            "Preview this workflow form schema.",
            "Show me the draft version of this workflow form.",
        ),
    ),
    "crm_workflow_forms_definitions_published_schema": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Published schema for a workflow form (for building submissions).",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Published workflow form schema used to construct submissions."
        ),
        typical_user_questions=("Published schema to build a submission for this form.",),
    ),
    "crm_workflow_forms_definitions_flow_graph": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Flow graph of a workflow form definition.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Flow graph nodes/edges for a workflow form definition."
        ),
        typical_user_questions=("Show the workflow flow graph.",),
    ),
    "crm_workflow_forms_submissions_list": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="List workflow form submissions.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "List workflow submissions with definition_id / state_code filters."
        ),
        typical_user_questions=(
            "List workflow submissions.",
            "Show submissions for this workflow form.",
        ),
    ),
    "crm_workflow_forms_submissions_get": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Get a workflow form submission by id (with lines/logs).",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Workflow submission detail including lines and logs."
        ),
        typical_user_questions=("Open this workflow submission.",),
    ),
    "crm_workflow_forms_submissions_allowed_transitions": ToolIntent(
        category="marketing_agent.marketing_assets",
        intent="Allowed workflow transitions for a submission.",
        description=(
            "Retrieves marketing form. DO NOT use this tool for checking stock, placing orders, or submitting data. "
            "Allowed transitions for a submission for the current act-as user."
        ),
        typical_user_questions=("What transitions can I do on this workflow submission?",),
    ),
    # ==================================================================
    # FORM SUBMISSIONS — stock inquiry (purchasing escalation)
    # ==================================================================
    "crm_portal_link_get": ToolIntent(
        category="user_submission_portal",
        intent="Hand the contact a 7-day portal link for filing complaints, stock inquiries (a.k.a. stock enquiries / product enquiries), purchase requests, or sponsorship forms.",
        description=(
            "POST /api/v1/external/portal-tokens/ with payload_json containing contact_id, space_id, "
            "and (strongly preferred) submission_type — one of complaint, stock_inquiry, purchase_request, "
            "sponsorship_form. submission_type makes the portal open directly on the matching tab after "
            "the contact verifies, so always derive it from the user's request. "
            "Returns a `portal_url` to send to the user. The portal lets them save drafts, attach photos "
            "(including pasted screenshots), submit, and review submission status. After 7 days the link "
            "expires and the contact re-verifies via OTP. Use this tool INSTEAD OF any legacy submit tools "
            "whenever the user asks to submit/file/create a complaint, stock inquiry / stock enquiry / "
            "product enquiry / product inquiry, purchase request, or sponsorship form."
        ),
        typical_user_questions=(
            "I want to file a complaint.",
            "I want to submit a complaint.",
            "Complaint",
            "I want to submit a stock inquiry.",
            "Stock inquiry",
            "I want to submit a stock enquiry.",
            "Stock enquiry"
            "I want to submit a product enquiry.",
            "Product enquiry",
            "I want to submit a product inquiry.",
            "Product inquiry",
            "I want to submit a purchase request.",
            "Purchase request",
            "I want to submit a sponsorship form.",
            "Sponsorship form"
            "Create a purchase request.",
            "Send me the link to my submissions.",
            "Where can I see and edit my drafts?",
        ),
        aliases=(
            "send portal link",
            "submission portal link",
            "submit complaint",
            "file complaint",
            "lodge complaint",
            "submit stock inquiry",
            "submit stock enquiry",
            "submit product inquiry",
            "submit product enquiry",
            "stock enquiry",
            "stock inquiry",
            "product enquiry",
            "product inquiry",
            "create purchase request",
            "submit purchase request",
            "file purchase request",
            "submit sponsorship form",
            "file sponsorship form",
            "create sponsorship form",
        ),
    ),
    # ==================================================================
    # FORM SUBMISSIONS — stock inquiry / purchase request / complaint tools
    # removed from Tool-RAG (per ops decision: not in active use; keeping out
    # of the RAG noise so the assistant doesn't surface them as candidates).
    # MCP catalog entries remain so existing callers / n8n flows still work,
    # but assistants will no longer be auto-enabled for them via the
    # _sync_enabled_tools merge in seed_mcp_tool_capabilities.
    # ==================================================================
    "crm_forms_entity_attachments_link": ToolIntent(
        category="complaint.form_submission",
        intent="Attach photos/videos/files to a complaint, stock inquiry, or purchase request.",
        description=(
            "Complaint / submission evidence upload (not marketing form downloads). DO NOT use this tool if the user is looking for "
            "downloadable templates, blank marketing forms, or marketing attachments. "
            "POST /api/v1/external/entity-attachments/ to create and link an attachment to an "
            "entity (complaint / stock_inquiry / purchase_request). Use AFTER the parent "
            "submission is confirmed — e.g. after a complaint is filed, to attach defect photos "
            "or videos. Not for browsing existing attachments — use crm_resource_attachments_* "
            "or crm_master_product_attachments_* instead."
        ),
        typical_user_questions=(
            "Attach these photos to my confirmed complaint.",
            "Upload a defect video to this complaint case.",
            "Link this file to my stock inquiry submission.",
            "Add supporting attachments to my purchase request.",
            "Send these images as evidence for my complaint.",
        ),
        aliases=("attach file to complaint", "upload complaint evidence", "link attachment to submission"),
    ),
    # ==================================================================
    # SLA MANAGEMENT — internal tooling
    # ==================================================================
    "crm_sla_policies_list": ToolIntent(
        category="sla_management",
        intent="List SLA policies.",
        description="List SLA policies with filters.",
        typical_user_questions=("List SLA policies.",),
    ),
    "crm_sla_policies_get": ToolIntent(
        category="sla_management",
        intent="Get one SLA policy.",
        description="Single SLA policy record.",
        typical_user_questions=("Open this SLA policy.",),
    ),
    "crm_sla_policies_tiers": ToolIntent(
        category="sla_management",
        intent="Tiers for an SLA policy.",
        description="SLA policy tiers.",
        typical_user_questions=("Show tiers for this SLA policy.",),
    ),
    "crm_sla_conversation_tracking_dashboard": ToolIntent(
        category="sla_management",
        intent="SLA conversation tracking dashboard metrics.",
        description="Aggregated SLA tracking dashboard metrics.",
        typical_user_questions=("Show the SLA tracking dashboard.",),
    ),
    "crm_sla_conversation_tracking_list": ToolIntent(
        category="sla_management",
        intent="List conversation SLA tracking rows.",
        description="List SLA conversation tracking rows with filters.",
        typical_user_questions=("List SLA conversation tracking rows.",),
    ),
    "crm_sla_conversation_tracking_get": ToolIntent(
        category="sla_management",
        intent="Get one SLA conversation tracking record.",
        description="Single SLA conversation tracking record.",
        typical_user_questions=("Open this SLA tracking record.",),
    ),
    "crm_sla_conversation_event_logs_list": ToolIntent(
        category="sla_management",
        intent="List SLA event logs.",
        description="SLA event logs with filters.",
        typical_user_questions=("List SLA event logs.",),
    ),
    "crm_system_tool_capabilities_summary": ToolIntent(
        category="general_enquiries.capabilities",
        intent="Summarize the MCP assistant's current capabilities dynamically.",
        description=(
            "Return a live capability overview of all currently available MCP tools, grouped into "
            "general enquiries and form submissions, including category breakdown and (optionally) "
            "tool-level details. Use when user asks what the assistant can do."
        ),
        typical_user_questions=(
            "What can you do?",
            "List your capabilities.",
            "What features are available in this chatbot?",
            "Show all available MCP tools and categories.",
            "Can you summarize general enquiries and form submission capabilities?",
        ),
        aliases=("capability summary", "what can you do", "tool overview", "mcp capabilities"),
    ),
    # ==================================================================
    # COMMERCIAL — projects, leads, tenders, quotations, customer fuzzy match
    # ==================================================================
    "crm_commercial_projects_list": ToolIntent(
        category="commercial",
        intent="List commercial projects with filters (developer/customer, status, free-text).",
        description=(
            "List commercial projects. Filters: customer_id (developer), status_id, query (free-text "
            "over project title / brief / customer name / customer code). Default sort latest first."
        ),
        typical_user_questions=(
            "Show all commercial projects.",
            "List projects for developer ABC Construction.",
            "What projects do we have in progress?",
            "Find projects by name or developer.",
        ),
        aliases=("commercial projects list", "projects for developer", "list projects"),
    ),
    "crm_commercial_projects_get": ToolIntent(
        category="commercial",
        intent="Fetch full detail for one commercial project by id.",
        description="Get one commercial project record by UUID with developer, owner, stages, customer contacts, address.",
        typical_user_questions=(
            "Show full detail for this project id.",
            "Open this commercial project record.",
        ),
        aliases=("get project by id", "project detail"),
    ),
    "crm_commercial_projects_create_smart": ToolIntent(
        category="commercial",
        intent="Create a commercial project with smart developer (customer) resolution and fuzzy matching.",
        description=(
            "Create a project where the developer (Customer) is resolved by one of three modes: "
            "(1) `developer_id` (existing customer UUID) — used directly; "
            "(2) `developer_create` (full customer payload) — creates the customer + project in one call; "
            "(3) `developer_query` (free-text name/code) — fuzzy-matches against existing customers. "
            "WHEN fuzzy match returns multiple candidates OR a single low-confidence match, the endpoint "
            "responds 409 with `{ near_matches: [...], needs_decision: true, missing_developer_fields: [...] }`. "
            "The caller MUST then either re-call with `developer_id` set to one of the suggestions, OR re-call "
            "with `force=true` + `developer_create` populated. "
            "Use `crm_master_customers_list` first to cross-check what developers (clients) already exist before deciding "
            "to create a new one — many developers differ by 1-2 characters, the fuzzy matcher catches close ones but "
            "exact name confirmation should always come from the user."
        ),
        typical_user_questions=(
            "Create a project for developer ABC Construction.",
            "Add a new project — the developer is XYZ Holdings.",
            "Set up a commercial project with this developer name.",
            "Start a project for this client; check if they already exist first.",
        ),
        aliases=(
            "create project",
            "new commercial project",
            "smart create project",
            "add project with developer",
        ),
    ),
    "crm_commercial_projects_edit": ToolIntent(
        category="commercial",
        intent="Update fields on an existing commercial project (title, brief, status, dates, address).",
        description="PATCH /api/v1/commercial/projects/{id}. Supports partial updates of title, brief, notes, status, dates, project_stage_id, owner_user_id, address fields, and project customers.",
        typical_user_questions=(
            "Edit this project's title.",
            "Update the project brief.",
            "Change the project status / stage.",
            "Set the start/end date on this project.",
            "Update the project address.",
        ),
        aliases=("update project", "edit project", "patch project"),
    ),
    "crm_master_customers_list": ToolIntent(
        category="commercial",
        intent="List or search distinct customers/debtors aggregated from the orders table.",
        description=(
            "Distinct customers/debtors derived from orders.debtor_name (the customers master table is not "
            "actively used by the business — the real customer identity is the debtor on each order). "
            "Each row returns debtor_name, debtor_code, and order_count, deduplicated by debtor_name "
            "(case-insensitive trim). `query` is a case-insensitive partial match on debtor_name OR debtor_code. "
            "Sort options: debtor_name, debtor_code, order_count. Use this BEFORE calling "
            "`crm_commercial_projects_create_smart` to cross-check whether a customer already exists and prevent "
            "1-2 char typo duplicates. External AI/MCP callers are HARD-CAPPED at limit=10 server-side."
        ),
        typical_user_questions=(
            "List all customers / developers / clients.",
            "Find customer ABC Construction.",
            "Do we already have this developer in the system?",
            "Show clients by name or code.",
            "Who are our customers?",
            "Top customers by order count.",
            "Search debtors by name.",
            "Find customer V BATH MARKETING.",
        ),
        aliases=(
            "customer list",
            "developer list",
            "search customers",
            "debtor list",
            "search debtors",
            "list debtors",
            "who are our customers",
        ),
    ),
    "crm_master_customers_get": ToolIntent(
        category="commercial",
        intent="Fetch full detail for one customer (developer/client) by id.",
        description="Get one customer record by UUID with code, name, contacts, billing address, profile fields.",
        typical_user_questions=(
            "Show full customer detail.",
            "Open this developer record.",
        ),
        aliases=("get customer by id", "customer detail", "developer detail"),
    ),
    # ==================================================================
    # USER GUIDES (Outline-backed how-to retrieval)
    # ==================================================================
    "user_guides_read": ToolIntent(
        category="user_guides",
        intent=(
            "Answer any 'how do I…?' / 'how to…?' question about a Sorento "
            "CRM UI flow by reading the matching guide in one call (uploading "
            "a packing list, submitting a portal stock inquiry, sending a "
            "purchase request for approval, etc.)."
        ),
        description=(
            "Single-call how-to tool. Pass the user's natural-language "
            "question as `query`; the tool searches the Sorento CRM Outline "
            "collection (doc.foundryx.my) and returns the full markdown body "
            "of the best-matching guide in one round trip. No separate "
            "search call is required. Quote the steps verbatim and preserve "
            "inline markdown links exactly when answering the user."
        ),
        typical_user_questions=(
            "How do I upload a packing list?",
            "How to submit a stock inquiry from the portal?",
            "How do I send a purchase request for approval?",
            "How does the project sales manager approve a purchase request?",
            "How do I flow a stock inquiry to purchasing?",
            "How do I upload a GRN?",
            "How do I upload delivery orders / order tracking?",
            "How do I upload a promotion?",
            "How do I upload a marketing form?",
            "How do I upload product attachments?",
            "How does the rep get the portal link via WhatsApp?",
            "What's the OTP flow for the portal?",
            "How do I save a draft on the portal?",
            "What happens after I submit a complaint?",
            "How does AI Extract work on a complaint?",
            "How do I reject a stock inquiry?",
            "How do I reopen a rejected stock inquiry?",
            "Where do folders live in Files?",
            "How do I pin a folder to Quick Access?",
            "Open this user guide.",
            "Read the full how-to article.",
            "Show me the full guide text.",
            "Get the documentation body.",
        ),
        aliases=(
            "read user guide",
            "open how-to",
            "fetch documentation",
            "read docs",
            "user guide",
            "user guide search",
            "search user guides",
            "find documentation",
            "how to guide",
            "outline docs",
            "outline doc info",
        ),
    ),
    "crm_it_support_ticket_create": ToolIntent(
        category="it_support",
        intent=(
            "Submit (file / raise / open) an IT support ticket to report a "
            "bug or system problem to the IT admin team."
        ),
        description=(
            "Submit an IT-support ticket to the IT admin team. "
            "Used when the user explicitly asks to file / submit / raise a "
            "ticket, report a bug, open a support request, or log a problem "
            "with IT. Triggers on phrases like 'submit ticket', 'raise an "
            "issue', 'file a bug report', 'log a complaint with IT'."
        ),
        typical_user_questions=(
            "Submit a ticket to IT for me.",
            "File a bug report with the IT team.",
            "Raise a ticket for the IT admin.",
            "Open an IT support ticket.",
            "Log an IT support request.",
            "I want to file a ticket.",
            "Report this bug to IT.",
            "Open a support request with IT.",
        ),
        aliases=(
            "submit it ticket",
            "create it ticket",
            "raise it ticket",
            "file bug",
            "report bug",
            "open support request",
            "log complaint with IT",
        ),
    ),
}


def _tool_aliases_from_name(tool_name: str) -> list[str]:
    base = re.sub(r"^crm_", "", tool_name)
    spaced = base.replace("_", " ").strip()
    parts = [p for p in base.split("_") if p]
    phrases: list[str] = [spaced]
    if len(parts) >= 2:
        phrases.append(" ".join(parts[:2]))
    if len(parts) >= 3:
        phrases.append(" ".join(parts[-2:]))
    return list(dict.fromkeys(phrases))


def _extract_category(tool_name: str) -> str:
    intent = TOOL_INTENTS.get(tool_name)
    if intent:
        return intent.category
    parts = tool_name.split("_")
    if len(parts) >= 3 and parts[0] == "crm":
        return parts[1]
    return "general"


def _parse_required_query_hints(description: str) -> list[str]:
    lowered = description.lower()
    hints: list[str] = []
    if "required pattern" in lowered and "promotion_id" in lowered:
        hints.append("promotion_id")
    return hints


def load_tool_definitions(definitions_file: str | None = None) -> list[ToolDefinition]:
    if not definitions_file:
        return []
    path = Path(definitions_file)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    defs: list[ToolDefinition] = []
    for row in payload:
        tool_name = str(row.get("tool_name", "")).strip()
        description = str(row.get("description", "")).strip()
        questions = [str(q).strip() for q in (row.get("typical_user_questions") or []) if str(q).strip()]
        if not tool_name or not description or not questions:
            continue
        defs.append(
            ToolDefinition(
                tool_name=tool_name,
                description=description,
                typical_user_questions=questions,
                category=str(row.get("category")) if row.get("category") else None,
                implementation_status=str(row.get("implementation_status") or "planned"),
                required_fields=[str(x).strip() for x in (row.get("required_fields") or []) if str(x).strip()] or None,
                optional_fields=[str(x).strip() for x in (row.get("optional_fields") or []) if str(x).strip()] or None,
            )
        )
    return defs


def _load_catalog_specs():
    repo_root = Path(__file__).resolve().parents[3]
    mcp_root = repo_root / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    try:
        from sorento_crm_mcp.catalog import CATALOG  # type: ignore
        return CATALOG
    except ModuleNotFoundError:
        # Fallback for environments where package import paths differ
        # (e.g. backend runtime without editable install of sorento_crm_mcp).
        import importlib.util

        catalog_file = mcp_root / "sorento_crm_mcp" / "catalog.py"
        spec = importlib.util.spec_from_file_location("sorento_crm_mcp_catalog_runtime", catalog_file)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "CATALOG")


def _intent_for(tool_name: str) -> ToolIntent | None:
    return TOOL_INTENTS.get(tool_name)


# Envelope-style phrases that the n8n RAG orchestrator emits in its query
# string ("Query type: tool_retrieval\nIntent: X\nDomain: Y\nUser goal: Z").
# Seeding these directly into the body_text for the right tool steers cosine
# similarity in the orchestrator's vocabulary, not just natural language.
_ENVELOPE_MATCH_PHRASES: dict[str, tuple[str, ...]] = {
    "crm_order_management_orders_list": (
        # Abbreviation expansion so embedder ties bare "DO" to delivery order tools.
        "DO = delivery order. DO is the abbreviation for delivery order.",
        "DO short for delivery order; D.O. means delivery order.",
        "Use this tool when the user types DO, D.O., or delivery order.",
        # Bare-verb intent phrasings the orchestrator typically emits.
        "check DO. check DO for customer. check DO for debtor. check DO for date.",
        "find DO. search DO. lookup DO. look up DO. show DO. get DO. checking DO.",
        "DO check. DO lookup. DO search. DO query. DO list. DO listing.",
        "find delivery order. search delivery order. check delivery order.",
        "list DO. list delivery orders. DO numbers. delivery order numbers.",
        # Delivery / outbound shipment status phrasing — outbound customer sales, NOT inbound stock.
        "check delivery status. delivery status. check status of delivery. status of delivery.",
        "check delivery status for order. check delivery status for customer.",
        "where is my delivery. is my order delivered. has order been delivered.",
        "outbound delivery status. customer delivery status. order delivery status.",
        "Delivery status here means OUTBOUND CUSTOMER ORDER delivery (DO), not inbound stock arrival.",
        "Not about incoming stock. Not about inbound shipments. Not about supplier arrivals.",
        # Envelope-style lines the n8n orchestrator emits.
        "Query type: tool_retrieval | Intent: order_enquiry | Domain: order_management | Operation: search | User goal: check DO",
        "Query type: tool_retrieval | Intent: delivery_order_lookup | Domain: order_management | Operation: search | User goal: find DO",
        "Query type: tool_retrieval | Intent: delivery_status | Domain: order_management | Operation: search | User goal: check delivery status",
        "Intent: order_enquiry. Intent: delivery_order_lookup. Intent: delivery_status. Domain: order_management.",
        "User goal: check DO. User goal: find DO. User goal: search delivery order. User goal: check delivery status.",
    ),
    "crm_order_management_orders_by_product_list": (
        # Abbreviation expansion + product-code co-occurrence seeding.
        "DO = delivery order. DO is the abbreviation for delivery order.",
        "DO short for delivery order; D.O. means delivery order.",
        "Use this tool when the user types DO, D.O., or delivery order, alongside a product code or SKU.",
        # Bare-verb intent phrasings paired with product/SKU context.
        "check DO for product. check DO for SKU. check DO for product code.",
        "check DO for <product_code>. check DO for product <SKU>. check delivery order for product.",
        "find DO for product. search DO for product. lookup DO by product. look up DO by SKU.",
        "DO check product. DO lookup product. DO by product. DO for product code.",
        "find delivery order for product. search delivery order for SKU. delivery order by product.",
        "which DO contains this product. which delivery order has this SKU.",
        "customer DO for product. DO for customer and product. DO by customer and product code.",
        # Delivery status for outbound product-level lookup.
        "check delivery status for product. delivery status for SKU. delivery status of product.",
        "check delivery status of order containing this product. delivery status by product.",
        "Delivery status here means OUTBOUND CUSTOMER ORDER delivery (DO) for this product, NOT incoming stock for this product.",
        "Not for incoming/inbound product. Not for supplier shipments. Use crm_incoming_stock_by_product for inbound stock.",
        # Envelope-style lines.
        "Query type: tool_retrieval | Intent: delivery_order_lookup | Domain: order_management | Operation: search | User goal: check DO for product",
        "Query type: tool_retrieval | Intent: order_by_product | Domain: order_management | Operation: search | User goal: find DO for SKU",
        "Query type: tool_retrieval | Intent: delivery_status | Domain: order_management | Operation: search | User goal: check delivery status for product",
        "Intent: delivery_order_lookup. Intent: order_by_product. Intent: delivery_status. Domain: order_management.",
        "User goal: check DO for product. User goal: find DO for SKU. User goal: search DO by product code. User goal: check delivery status for product.",
    ),
    "crm_portal_link_get": (
        # Full-envelope mirror lines: shape the cosine target so the n8n
        # orchestrator's template ("Query type: tool_retrieval\nIntent: ...\n
        # Domain: ...\nOperation: ...\nUser goal: ...") matches portal_link_get
        # directly. Includes the misleading "Domain: warehouse" / "Domain:
        # procurement" variants that the orchestrator actually emits for
        # stock_inquiry / purchase_request flows.
        "Query type: tool_retrieval | Intent: stock_inquiry | Domain: warehouse | Operation: search | User goal: file stock inquiry",
        "Query type: tool_retrieval | Intent: stock_inquiry | Domain: user_submissions | Operation: submit | User goal: file stock inquiry",
        "Query type: tool_retrieval | Intent: stock_enquiry | Domain: warehouse | Operation: search | User goal: file stock enquiry",
        "Query type: tool_retrieval | Intent: product_inquiry | Domain: warehouse | Operation: search | User goal: submit product inquiry",
        "Query type: tool_retrieval | Intent: product_enquiry | Domain: warehouse | Operation: search | User goal: submit product enquiry",
        "Query type: tool_retrieval | Intent: complaint | Domain: warehouse | Operation: search | User goal: file complaint",
        "Query type: tool_retrieval | Intent: complaint | Domain: complaint_management | Operation: submit | User goal: file complaint",
        "Query type: tool_retrieval | Intent: complaint | Domain: forms_submission | Operation: submit | User goal: lodge complaint",
        "Query type: tool_retrieval | Intent: purchase_request | Domain: procurement | Operation: search | User goal: file purchase request",
        "Query type: tool_retrieval | Intent: purchase_request | Domain: forms_submission | Operation: submit | User goal: create purchase request",
        "Query type: tool_retrieval | Intent: sponsorship_form | Domain: marketing | Operation: search | User goal: submit sponsorship form",
        "Query type: tool_retrieval | Intent: sponsorship_form | Domain: forms_submission | Operation: submit | User goal: file sponsorship form",
        # Intent enums emitted by the orchestrator for submission flows.
        "Intent: stock_inquiry",
        "Intent: stock_enquiry",
        "Intent: product_inquiry",
        "Intent: product_enquiry",
        "Intent: complaint",
        "Intent: purchase_request",
        "Intent: sponsorship_form",
        "Intent: sponsorship",
        "Intent: file_submission",
        "Intent: submit_form",
        # Domain pointing at user-facing submission portal (counters "Domain: warehouse").
        "Domain: user_submissions",
        "Domain: portal",
        "Domain: forms_submission",
        # Operation = create / submit, NOT search.
        "Operation: submit",
        "Operation: create",
        "Operation: file",
        # User-goal phrasings.
        "User goal: file stock inquiry",
        "User goal: submit stock inquiry",
        "User goal: file complaint",
        "User goal: submit complaint",
        "User goal: lodge complaint",
        "User goal: create purchase request",
        "User goal: submit purchase request",
        "User goal: file sponsorship form",
        "User goal: submit sponsorship form",
        "User goal: hand me the portal link",
        # Anti-confusion: explicit that these are NOT inventory lookups.
        "Not an inventory lookup. Not a stock balance query. Use this for submission portal.",
    ),
}


_READONLY_LOOKUP_DISCLAIMER = (
    "This tool is a read-only data lookup. It does NOT submit, file, lodge, or create any form.",
    "Do not pick this tool when the user wants to file a stock inquiry, file a complaint, "
    "file a purchase request, or file a sponsorship form. Pick crm_portal_link_get for those.",
)


def _envelope_match_phrases(tool_name: str) -> tuple[str, ...]:
    explicit = _ENVELOPE_MATCH_PHRASES.get(tool_name)
    is_readonly_lookup = (
        tool_name.startswith("crm_inventory_")
        or tool_name.startswith("crm_incoming_stock_")
        or tool_name.startswith("crm_order_management_")
    )
    if explicit is not None:
        # Order/inventory lookup tools with explicit positive seeding still need
        # the anti-submission disclaimer so they don't surface for portal flows.
        if is_readonly_lookup:
            return tuple(explicit) + _READONLY_LOOKUP_DISCLAIMER
        return explicit
    if is_readonly_lookup:
        return _READONLY_LOOKUP_DISCLAIMER
    return ()


def _fallback_intent(tool_name: str, path: str, required_params: list[str], optional_params: list[str]) -> ToolIntent:
    base_required = ", ".join(required_params) if required_params else "none"
    base_optional = ", ".join(optional_params) if optional_params else "none"
    return ToolIntent(
        category=_extract_category(tool_name),
        intent=f"Call {tool_name} to access {path}.",
        description=(
            f"Call {tool_name} to fetch CRM data from {path}. Required params: [{base_required}]. "
            f"Optional params: [{base_optional}]."
        ),
        typical_user_questions=(
            f"Use {tool_name} for this request.",
            "Fetch CRM data relevant to this query.",
            "Retrieve records from this endpoint.",
        ),
        aliases=tuple(_tool_aliases_from_name(tool_name)),
    )


def build_capability_documents(include_planned: bool = True, definitions_file: str | None = None) -> list[CapabilityDoc]:
    docs: list[CapabilityDoc] = []
    from_file = load_tool_definitions(definitions_file)
    if from_file:
        for td in from_file:
            category = td.category or _extract_category(td.tool_name)
            aliases = _tool_aliases_from_name(td.tool_name)
            body_text = (
                f"Tool Name: {td.tool_name}\n"
                f"Category: {category}\n"
                f"Intent: {td.description}\n"
                f"Required Fields: {', '.join(td.required_fields or []) if td.required_fields else 'none'}\n"
                f"Optional Fields: {', '.join(td.optional_fields or []) if td.optional_fields else 'none'}\n"
                f"Aliases: {', '.join(aliases)}\n"
            )
            docs.append(
                CapabilityDoc(
                    source_id=f"{td.implementation_status}::{td.tool_name}",
                    source_key=td.tool_name,
                    title=td.tool_name,
                    body_text=body_text,
                    metadata={
                        "tool_name": td.tool_name,
                        "category": category,
                        "required_params": [],
                        "optional_params": [],
                        "required_fields": td.required_fields or [],
                        "optional_fields": td.optional_fields or [],
                        "aliases": aliases,
                        "typical_user_questions": td.typical_user_questions,
                        "implementation_status": td.implementation_status,
                        "tool_type": "tool_rag_definition",
                    },
                )
            )
        return docs

    for spec in _load_catalog_specs():
        if spec.name in _EMBEDDING_SKIP_TOOLS:
            continue
        required_params = [*spec.path_params]
        optional_params = [*spec.query_params]
        required_params.extend(_parse_required_query_hints(spec.description))
        intent = _intent_for(spec.name) or _fallback_intent(spec.name, spec.path, required_params, optional_params)
        category = intent.category
        aliases = list(intent.aliases) + _tool_aliases_from_name(spec.name)
        aliases = list(dict.fromkeys(aliases))
        typical_q = list(intent.typical_user_questions) if intent.typical_user_questions else []
        envelope_phrases = _envelope_match_phrases(spec.name)
        body_text = (
            f"Tool Name: {spec.name}\n"
            f"Category: {category}\n"
            f"Intent: {intent.intent}\n"
            f"Description: {intent.description}\n"
            f"Tool Spec: {spec.description}\n"
            f"Method: {spec.method}\n"
            f"Path: {spec.path}\n"
            f"Required Params: {', '.join(required_params) if required_params else 'none'}\n"
            f"Optional Params: {', '.join(optional_params) if optional_params else 'none'}\n"
            f"Body Params: {', '.join(spec.body_params) if spec.body_params else 'none'}\n"
            f"Aliases: {', '.join(aliases)}\n"
            f"Typical User Questions: {' | '.join(typical_q) if typical_q else 'none'}\n"
        )
        if envelope_phrases:
            body_text += f"Envelope Match Phrases: {' | '.join(envelope_phrases)}\n"
        docs.append(
            CapabilityDoc(
                source_id=f"implemented::{spec.name}",
                source_key=spec.name,
                title=spec.name,
                body_text=body_text,
                metadata={
                    "tool_name": spec.name,
                    "category": category,
                    "required_params": required_params,
                    "optional_params": optional_params,
                    "aliases": aliases,
                    "typical_user_questions": list(intent.typical_user_questions),
                    "implementation_status": "implemented",
                    "tool_type": _tool_type_for_category(category),
                    "api_path": spec.path,
                    "method": spec.method,
                    "body_params": list(spec.body_params),
                    "when_to_use": intent.intent,
                },
            )
        )

    if include_planned:
        docs.extend(_planned_capabilities())
    return docs


def build_live_capability_summary(*, include_tools: bool = True) -> dict[str, Any]:
    """Build a dynamic summary of current MCP capabilities from live catalog + intents.

    This is intentionally derived from runtime source-of-truth (`CATALOG`, `TOOL_INTENTS`)
    so callers always see the latest capabilities without hard-coding.
    """
    specs = list(_load_catalog_specs())
    groups: dict[str, dict[str, Any]] = {
        "general_enquiries": {
            "group": "general_enquiries",
            "title": "General enquiries and information retrieval",
            "categories": {},
            "tool_count": 0,
            "tools": [],
        },
        "form_submission": {
            "group": "form_submission",
            "title": "Form submissions and action workflows",
            "categories": {},
            "tool_count": 0,
            "tools": [],
        },
    }

    def _bucket(category: str) -> str:
        return "form_submission" if ".form_submission" in category else "general_enquiries"

    for spec in specs:
        intent = _intent_for(spec.name) or _fallback_intent(spec.name, spec.path, list(spec.path_params), list(spec.query_params))
        category = intent.category or _extract_category(spec.name)
        bucket = _bucket(category)
        group = groups[bucket]
        group["tool_count"] += 1
        group["categories"][category] = int(group["categories"].get(category, 0)) + 1
        if include_tools:
            group["tools"].append(
                {
                    "tool_name": spec.name,
                    "category": category,
                    "intent": intent.intent,
                    "description": intent.description,
                    "method": spec.method,
                    "path": spec.path,
                }
            )

    # Stable ordering improves deterministic UI responses / tests.
    for g in groups.values():
        g["categories"] = dict(sorted(g["categories"].items(), key=lambda kv: kv[0]))
        if include_tools:
            g["tools"] = sorted(g["tools"], key=lambda t: str(t.get("tool_name", "")))

    return {
        "summary": {
            "total_tools": len(specs),
            "general_enquiries_tool_count": groups["general_enquiries"]["tool_count"],
            "form_submission_tool_count": groups["form_submission"]["tool_count"],
        },
        "groups": [groups["general_enquiries"], groups["form_submission"]],
        "source": "live_catalog_and_tool_intents",
    }


def _tool_type_for_category(category: str) -> str:
    if category.endswith("form_submission"):
        return "form_submission"
    if category in ("marketing_agent.form_lookup", "marketing_agent.marketing_assets"):
        return "marketing_assets"
    if category == "order_enquiries":
        return "enquiry"
    if category.startswith("general_enquiries"):
        return "enquiry"
    if category == "sla_management":
        return "internal"
    return "enquiry"


def _planned_capabilities() -> list[CapabilityDoc]:
    planned = [
        {
            "tool_name": "submit_workflow_transition",
            "category": "workflow",
            "required_params": ["submission_id", "transition_code"],
            "optional_params": ["comment"],
            "tool_type": "workflow_action",
            "description": "Execute a workflow transition chosen from the allowed transitions on a submission.",
            "typical_user_questions": [
                "Move this workflow submission to the next state.",
                "Approve / reject this workflow submission.",
                "Advance this workflow submission using an allowed transition.",
            ],
        },
    ]
    docs: list[CapabilityDoc] = []
    for row in planned:
        tool_name = row["tool_name"]
        aliases = _tool_aliases_from_name(tool_name)
        body_text = (
            f"Tool Name: {tool_name}\n"
            f"Category: {row['category']}\n"
            f"Intent: {row['description']}\n"
            f"Required Params: {', '.join(row['required_params'])}\n"
            f"Optional Params: {', '.join(row['optional_params']) if row['optional_params'] else 'none'}\n"
            f"Aliases: {', '.join(aliases)}\n"
            "When To Use: Use when the user asks to progress a workflow submission via an allowed transition.\n"
        )
        docs.append(
            CapabilityDoc(
                source_id=f"planned::{tool_name}",
                source_key=tool_name,
                title=tool_name,
                body_text=body_text,
                metadata={
                    **row,
                    "aliases": aliases,
                    "typical_user_questions": row["typical_user_questions"],
                    "implementation_status": "planned",
                },
            )
        )
    return docs
