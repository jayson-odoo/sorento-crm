# PLAN — MCP tool consolidation for deterministic n8n mapping

**Status:** BUILT (4 merges done, verified, tested) — pending code review + commit

## Build log
- ✅ **Incoming** — new `IncomingStockService.incoming_list` + `GET /incoming-stock/list`
  (shipment-rooted, nested lines, no aggregates). New MCP tool `crm_incoming_stock_list`
  (UUID/eta narrowers only — free-text `query` omitted to satisfy the catalog guard).
  Old `by_product` / `shipments` tools kept as aliases. pytest: `test_incoming_list.py`
  (6, green). Verified via MCP client: nested lines, product-filter narrows lines, line
  sums == old aggregates.
- ✅ **Promotions** — MCP fan-out `_enrich_promotions_with_products` nests `products[]`
  under each promo (batched, paginated). Sanitize slims nested products (confidential
  dropped, promotion_price→selling_price) + strips attachment internals; **header
  attachment filename preserved** (removed the promo browse-strip rule). Verified.
- ✅ **Products** — MCP fan-out `_enrich_products_with_attachments` nests `attachments[]`
  (dimensions come from product root → dimensions-gap solved). Added confidential
  `cost_price`/`invoice_price` strip (pre-existing leak). Verified with SRTFC2044 (2
  attachments, filename+type, no internal/cost leak).
- ✅ **Orders** — no-op: `orders_list` already returns full lines (product+warehouse+qty)
  + all WhatsApp fields; `by_product` kept as alias. (Fold its product-search intent into
  the `orders_list` capability when the aliases are retired.)
- Tests: MCP `test_merge_consolidation_sanitizer.py` (4, green); full MCP suite 81 green.
  Backend full suite has **pre-existing** cross-test isolation failures (global SQLAlchemy
  listeners + sqlite) unrelated to this change; all touched files pass in isolation.

## Render envelope (`view=render`) — added
- New `sorento_crm_mcp/presenters.py`: per-tool presenters map each tool's sanitized
  data → ONE uniform, markdown-free envelope
  `{result_type, intro, items[{title,fields[{label,value}],flags}], attachments,
  action_links, last_updated_at, has_result}`.
- **Opt-in**: `view=render` param injected into presenter tools' schema at compile time
  (skipped for body-param tools like portal_link_get). Without `view`, tools return raw
  data unchanged → the AI assistant (still reads raw) is unaffected until it migrates.
- Plumbing: `server._compile_tool` injects `view`; the impl pops it before the backend
  call and applies `present_response` after escalation. Escalation/fallback keys carried
  through into the envelope.
- This moves all per-tool field mapping OUT of the n8n Code node (≈250 lines) INTO Python
  (pytest-covered). n8n becomes a ~25-line generic renderer.
- Tests: `tests/test_presenters.py` (9). Full MCP suite **90 green**.

## Follow-up (later PR)
- Retire the 5 alias tools once n8n is rewired; delete `/orders/by-product`,
  `/incoming-stock/{by-product,shipments}` endpoints if no other consumer.
- Fold `by_product` intent text into `orders_list` ToolIntent at retirement time.


## Resolved open items
1. Incoming shape: **shipment-rooted, nested product lines** (no aggregates).
2. Old 5 paired tools: **kept as aliases** for one n8n migration window; deleted in a
   later follow-up.
3. Incoming impl: **new backend method/endpoint** (single SQL grouped by shipment); both
   incoming endpoints are MCP-only so no FE risk.

Implementation order: (a) incoming backend method + tool, (b) promotions nested handler,
(c) products nested handler, (d) orders = no-op now (by_product kept as alias; fold intent
into orders_list capability later). Verify each via Inspector/curl before the next.

**Owner:** jayson
**Date:** 2026-06-13

## Goal

Consolidate the read-only MCP tools into fewer, fatter, **domain-level** tools whose
responses n8n maps deterministically into structured WhatsApp messages (n8n uses a
direct MCP node; no LLM picks tools or fields). Reduce 12 tools → 8 by merging 4 pairs.

## Decisions (locked with stakeholder)

1. **No caller distinction.** The same tools serve both n8n *and* the AI assistant. The
   assistant will be made to mimic n8n once n8n stabilises, so we do **not** branch
   output by caller. Every consumer gets the same full, granular JSON.
2. **Merge all 4 pairs** (12 → 8 tools).
3. **n8n owns formatting.** MCP returns a stable, granular JSON contract; n8n's Code/Set
   nodes build the WhatsApp text. We do not return pre-formatted strings.

### Principle that falls out of (1)+(3)

> **MCP returns complete granular data; n8n derives summaries.**

So aggregate/convenience fields (e.g. `total_remaining_incoming_quantity`,
`warehouse_allocation_summary`) stay **out** of MCP — n8n sums the per-line rows. This is
consistent with the trims already shipped in commit `2de034ad1`.

### What the sanitizers keep vs drop (unchanged by this plan)

KEEP (business/hygiene, never caller-dependent):
- Confidential pricing: `dealer_cost`, `dealer_discount_percent`,
  `list_to_dealer_margin_amount`, `cost_price`. Dealers must never see these on WhatsApp.
- Hidden stock columns: `quantity_reserved`, `quantity_damaged`, `reorder_point`, etc.
- UUID hygiene: strip row `id`/FK UUIDs the agent/WhatsApp must not echo.
- Vocab renames: `location`→`warehouse`, `warehouse_code`→`system_location`, etc.

DROP from the trimming agenda (superseded — we now return granular):
- Pure "LLM noise" trims that remove fields a WhatsApp template might map. None identified
  as needed-but-missing today; audit per tool during implementation.

## FE-safety constraint (drives the implementation approach)

These backend list endpoints are **shared with the React UI** and MUST NOT change shape:
- `GET /api/v1/order-management/orders` (orders page)
- `GET /api/v1/master-data/products` (master-data products page)
- `GET /api/v1/marketing/promotions` (promotions page)

MCP-only endpoints (safe to retire/repurpose):
- `/orders/by-product`, `/marketing/promotion-products`,
  `/master-data/product-attachments`, `/incoming-stock/by-product`,
  `/incoming-stock/shipments`.

→ **Approach: merge at the MCP layer.** New merged tools fan out to existing backend GETs
and stitch the nested shape in custom handlers (the server already has this pattern:
multi-call stitching + `_sanitize_tool_response`). Shared FE endpoints stay untouched.
No Alembic migrations. No FE changes.

## The 8 tools after consolidation

| # | Tool | Source endpoints | Root shape |
|---|------|------------------|------------|
| 1 | `crm_order_management_orders_list` | `/orders` (as-is) | order → full `lines[]` (product+warehouse+qty) |
| 2 | `crm_marketing_promotions_list` | `/promotions` + `/promotion-products` | promotion → nested `products[]` |
| 3 | `crm_master_products_list` | `/products` + `/product-attachments` | product → nested `attachments[]` |
| 4 | `crm_incoming_stock_list` | `/incoming-stock/{by-product,shipments}` | shipment → nested product `lines[]` |
| 5 | `crm_inventory_stock_balance_list` | unchanged | — |
| 6 | `crm_resource_attachments_list` | unchanged | — |
| 7 | `crm_forms_management_forms_list` | unchanged (name + attachment_id) | — |
| 8 | `crm_portal_link_get` | unchanged | — |

Retired tools: `crm_order_management_orders_by_product_list`,
`crm_marketing_promotion_products_list`, `crm_master_product_attachments_list`,
`crm_incoming_stock_by_product`, `crm_incoming_stock_shipments`.

## Per-merge design

### 1. Orders (NO backend work)
- `orders_list` already accepts `product_ids`/`customer_ids`/`transporter_ids`/date
  filters and returns full `lines[]` carrying nested `product` (code+name) and `warehouse`
  (code+name) + `quantity`, plus order-level driver/lorry/transporter/pickup_time/status.
  All WhatsApp order fields are satisfiable post-sanitizer (verified).
- **Action:** delete the `by_product` ToolSpec from catalog; fold its product-search intent
  into `orders_list`'s `ToolIntent` (capability service). Keep `/orders/by-product`
  endpoint for now (no consumer once tool retired) — remove in a later cleanup.
- n8n "which orders contain product X" = `orders_list?product_ids=…`, then n8n filters
  `lines[]` to that product if it wants matched-only.

### 2. Promotions → promo with nested products[]
- New MCP custom handler for `crm_marketing_promotions_list`:
  1. GET `/promotions` (headers, dates, access_levels, attachments).
  2. GET `/promotion-products?promotion_ids=<page ids>` (one batched call, not N+1).
  3. Group product rows under their `promotion_id`; attach as `products[]`.
- Per product line keep: `product_code`, `product_name`, `selling_price`
  (rename of `promotion_price`), `list_price`, `dimensions_{length,width,height}`,
  `promotion_attachments[]`. Drop confidential margins (existing
  `_PROMO_PRODUCT_DROP_KEYS`).
- WhatsApp promo sample (product_code, promo name, selling+list price, dimensions) →
  satisfiable from `promotions[].products[]`.

### 3. Products → product with nested attachments[]
- New MCP custom handler for `crm_master_products_list`:
  1. GET `/products` (code, name, description, list_price, dimensions, brand, category).
  2. When `product_ids`/narrowing present, GET `/product-attachments?product_ids=…`
     (batched) and group under `product_id` as `attachments[]`.
- Dimensions come from the **product root** → no need to widen `ProductSimple`. Solves the
  gap where `ProductAttachmentResponse.product` omitted dimensions.
- Per attachment keep: `original_filename`, `attachment_type`, `description`. Strip
  attachment internals (existing `_ATTACHMENT_INTERNAL_KEYS`).
- Two WhatsApp templates satisfiable from one tool: list-prices (product fields) and
  product-photos/specs (product + attachments[]).

### 4. Incoming stock → shipment with nested product lines[] (DESIGN CHOICE)
- Single tool `crm_incoming_stock_list`, accepts `product_ids` OR `shipment_ids` OR
  `supplier_ids` OR `eta_from/eta_to` (≥1 required).
- **Recommended shape: shipment-rooted, nested granular lines.**
  ```
  { shipment_number, shipping_container_number, estimated_arrival_date,
    attachment,
    lines: [ { product_code, product_name, batch_number,
               remaining_incoming_quantity,
               warehouse_allocations: [ { warehouse_code, warehouse_name,
                                          allocated_quantity } ] } ] }
  ```
- Serves both: "incoming for product X" (filter shipments by product_ids; n8n keeps the X
  lines and can sum across shipments for a product total) and "shipments this
  month/supplier" (shipment list directly). No aggregates emitted — n8n derives
  `total_remaining` / `nearest_eta` / per-warehouse summary.
- **Trade-off vs today:** loses the product-rooted convenience of `by_product` and the
  `distinct_products_incoming`/`total_remaining` shipment aggregates — both reconstructable
  in n8n. If product-rooted is strongly preferred for the WhatsApp template, the
  alternative is a conditional root (product-rooted when `product_ids`, else
  shipment-rooted) — messier contract; not recommended.
- Implementation: likely one backend service method that returns shipment→lines (the
  current `incoming_for_product` already computes line-level remaining + warehouse
  allocations; re-group by shipment), exposed on a single MCP-only endpoint, OR stitch two
  existing calls at the MCP layer. Decide during build; prefer one backend method since
  both current endpoints are MCP-only (no FE risk).

## Out of scope / unchanged
- `inventory_stock_balance_list`, `resource_attachments_list`, `forms_list`,
  `portal_link_get`. Forms stays minimal (name + attachment_id) per prior decision —
  revisit only if an n8n forms template needs more.

## Methodology note (three-phase loop)
- **Phase 1 (FE prototype): N/A** — no UI; these are MCP/backend tools. Called out per
  CLAUDE.md.
- **Phase 2:** implement merged tools + sanitizers; add tests —
  - `sorento_crm_mcp/tests`: per merged tool, assert nested shape + that confidential/UUID
    fields are absent and WhatsApp-needed fields are present.
  - `pytest` backend: any new incoming endpoint/service method (happy + auth + validation).
- **Phase 3:** `/code-review` the diff before PR.

## Verification
- For each merged tool: run via MCP Inspector (already booted) against a known
  product/promo/shipment; diff the JSON against the WhatsApp sample field list; confirm no
  UUIDs/confidential fields leak.
- Restart MCP after catalog/handler changes (FastMCP re-registers at startup).

## Open items to confirm before build
1. Incoming shape: shipment-rooted nested lines (recommended) vs conditional root?
2. Retire old paired tools immediately, or keep as hidden aliases for one n8n migration
   window?
3. Incoming: one new backend service method (cleaner) vs MCP-layer stitch of the two
   existing endpoints (zero backend change)?
