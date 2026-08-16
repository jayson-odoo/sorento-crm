# PLAN - Multi-company reply clarity, backend half

**Status:** in progress on `fm/mc-label-backend` (2026-08-16).
**UAC:** `documentation/plans/multi-company/multi-company-reply-clarity-acceptance-criteria.md`
**Classification:** CORE (touches core list endpoints + the MCP presenter). No migration,
no new permission, no FE.
**Source of truth for the defect:** scout report `multicompany-response-clarity/report.md`
(firstmate data dir). Reproduced: `list_stock` queries all the caller's companies with one
`IN` predicate but rows carry no company identity, so n8n cannot attribute rows or name
the companies searched.

## Journey

See the UAC `Journey` section. Short form: a two-company contact asking for a code that
exists in both companies gets every row labelled `Company: X` and, on an empty result,
an intro plus `lookup_companies` naming the companies searched. A code that exists in one
company only gets today's reply, byte for byte, even for a two-company caller.

## Rules (captain, 2026-08-16)

1. Rollout (c): every company-scoped presenter tool, in this one PR.
2. Label iff `companies(resolved product_ids) UNION companies(returned rows)` has size > 1.
   Never key on the caller's access list.
3. Simplest thing that works: mirror the attachments company-stamp precedent
   (`app/api/v1/resources/attachments.py:213-227` + `resources_service.company_name_map`),
   `_PASSTHROUGH_KEYS`, `_Builder.item` None-dropping. ONE small shared helper, no new
   service module, no flag, no config.
4. This PR does NOT touch n8n.

## Design

### 1. Shared schema

`app/schemas/common.py` `ListResponse`: add

```python
lookup_companies: Optional[List[Dict[str, Any]]] = None
```

`PromotionServingListResponse` inherits it. The incoming-stock endpoints return raw dicts
(no `ListResponse`); they set the same key directly. The name is `lookup_companies`
everywhere (matches the report and the n8n follow-up).

Note on the wire: `ListResponse` already emits `resolved_entities: null` when unset, so
`lookup_companies: null` on a single-company reply is the same shape convention. The MCP
envelope drops null passthrough keys (`_filled`), so the RENDERED reply stays
byte-identical (AC-C4).

### 2. Shared helper (one place, reused by every service)

Add to `app/services/company_scope.py` (already the company-scoping module; imports
`Company` lazily like `company_name_map` does):

```python
def stamp_lookup_companies(
    db, payload: dict, rows, *, product_ids=None, row_company_id=None
) -> None:
    """Label a list payload per company iff the lookup spans >1 company.

    lookup = {Product.company_id for product_ids}  (scoped ORM query, so an id the
             caller cannot see contributes nothing)
          | {row company_id for rows}
    If len(lookup) <= 1: return, touching nothing.
    Else: ONE Company.id/name query over lookup; for each row set company_id (str)
    and company_name; payload["lookup_companies"] = [{"id","name"}] sorted by name.
    Best-effort: any exception -> warn + return (labelling is additive, never fatal).
    """
```

- `rows` may be ORM instances (setattr `company_name`; `company_id` already there),
  plain dicts (set both keys), or Pydantic models that declare both fields (setattr).
- `row_company_id` is an optional callable for rows whose company lives elsewhere than
  `.company_id` (e.g. the incoming raw dicts, where the service captures
  `InboundShipment.company_id` / `Product.company_id` while building the row).
- Called AFTER the page of rows is fetched and BEFORE the payload is returned, on the
  with-data path AND on the empty path of every tool below (the empty path is the case
  that matters). Early returns that fire before any product resolved need nothing.
- Postgres proof for AC-B6: the `Product.company_id` query runs on the scoped session
  (`do_orm_execute` listener, `company_scope.py:255`), so an out-of-scope product id
  is filtered before it can count. Test it, do not assume it.

### 3. Row schemas

Add `company_id: Optional[str] = None` and `company_name: Optional[str] = None` (with the
UUID -> str `field_validator` pattern from `AttachmentResponse`, `schemas/resources.py:331`)
to: `StockResponse` (`schemas/inventory.py:159`), `ProductResponse`
(`schemas/product.py:273`), `ProductAttachmentResponse` (`:514`), `CertificateResponse`
(`schemas/certificate.py:192`), `PromotionListItemResponse` (`schemas/marketing.py:261`),
`PromotionProductResponse` (`:406`), `OrderResponse` (`schemas/order.py:181`),
`OrderSimpleRef` (`:169`). Incoming-stock rows are hand-built dicts: no schema change.

`company_id` fills from the mixin via `from_attributes` on ORM rows; `company_name` only
via the helper. `Certificate` rows are already Pydantic (`serialize_many`), so the helper
stamps the Pydantic objects while reading company ids off the ORM rows the service still
holds at `certificate_query_service.py:282`.

### 4. Services: one call site each

| Tool | Service (file:line, from the map) | product-id set | row company |
|---|---|---|---|
| stock_balance | `inventory_service.list_stock` :612, payload :854, empty paths :665/:692/:704 need nothing (no product resolved) but the `total == 0` path through :854 does | `resolved_input_product_ids` (:676) | `Stock.company_id` |
| incoming_stock_list | `incoming_stock_service.incoming_list` :491, payload :681, empty :597 | `resolved_pids` (:525) | `InboundShipment.company_id` (capture while building rows) |
| incoming_stock_by_product | `incoming_for_product` :187, payload :354, empty :289 | `resolved_ids` (:227) | `Product.company_id` (row root) |
| incoming_stock_shipments | `incoming_shipments` :403, payload :486, empty :470 | none | `InboundShipment.company_id` (add to the select) |
| master_products_list | `product_service.list_products` :502, payload :614, empty :583 | kwarg `product_ids` | `Product.company_id` |
| master_product_attachments_list | `list_product_attachments` :2533, payload :2698 | `_scoped_product_ids` (:2571) | `ProductAttachment.company_id` |
| certificates_list | `certificate_query_service.list_certificates` :156, payload :286 | `product_ids` (capture before :202) | `Certificate.company_id` |
| marketing_promotions_list | `marketing_service.list_promotions` :595, payload :741 | kwarg `product_ids` | `Promotion.company_id` |
| marketing_promotion_products_list | `list_promotion_products` :1275, payload :1603 | `product_ids_filter` | `PromotionProduct.company_id` |
| orders_list | `order_service.list_orders` :57, payload :473 | `_product_uuid_filter` (:106) | `Order.company_id` |
| orders_by_product_list | `list_orders_by_product` :1063, payload :1425 | `_product_uuid_filter` (:1091) / resolved `product_ids` (:1197) | `Order.company_id` |

Rows-only tools (`incoming_stock_shipments`, and any tool that takes no product
ids at all) take their company set from the CURRENT PAGE's rows - a deliberate
decision: there is no requested product set to widen it with, so their empty
result carries no `lookup_companies` and page 2 can name a different set than
page 1.

Every early return that fires AFTER the requested product set is known stamps
its own empty payload too (review round F1), so an empty answer names the
companies searched no matter which guard produced it. The exception is a guard
that fires BECAUSE nothing resolved (the two incoming-stock product guards):
the requested set is empty there, so there is no company to name.

The routes need no change: `ListResponse` declares the key, and the alternatives
`JSONResponse` bypass paths already pass the raw dict through.

### 5. MCP presenter (`sorento_crm_mcp/sorento_crm_mcp/presenters.py`)

- `_PASSTHROUGH_KEYS` (:91) += `"lookup_companies"`.
- Each affected builder gets a LEADING 3-tuple
  `("company_name", "Company", row.get("company_name"))` (dropped by `_Builder.item`
  when None): `_orders_list` :290, `_orders_by_product` :319, `_incoming_list` :373
  (from the shipment `s`), `_incoming_by_product` :409 (from the product `p`),
  `_incoming_shipments` :452, `_promotions` :476, `_promotion_products` :494,
  `_products` :515, `_product_attachments` :535, `_certificates` :633, `_stock` :749.
- `present_response` intro (:923-928): when `not has_result` and
  `data.get("lookup_companies")` is filled, `"No matching results found for {names}."`
  with names joined ", " and a final " or ".
- `server.py` sanitizer: check every slimmer on the affected tools
  (`_slim_orders_list_response`, `_strip_products_list_confidential`,
  `_strip_promotions_list_row_ids`, `_slim_promotion_products_response`,
  `_slim_stock_nested_warehouse`, `_relabel_warehouse_keys`) keeps `company_name` on rows
  and `lookup_companies` at top level. Fix any allow-list that drops them.

### 6. Tests (test-FIRST, Postgres only)

Backend, `sorento_crm_backend/tests/test_multi_company_lookup_labels.py` (one file, or a
small file per domain if it reads better), modelled on
`tests/test_attachment_company_stamp_in_list.py`: `blank_session`, seeded Mocha
(`00000000-0000-0000-0000-000000000002`), pinned two-company scope via the
`apply_company_scope` override, own data chain per test. Cover UAC AC-B1/B2/B4 per tool,
AC-B3/B5 on stock + incoming list, AC-B6/B7 on the helper.

MCP, `sorento_crm_mcp/tests/test_presenters.py`: AC-C1 to AC-C4; the byte-identical proof
is `present_response(payload_with_null_keys) == present_response(payload_without_keys)`.

### 7. Deploy note (PR body)

FastMCP registers presenters at startup: restart the MCP process after merge (same
gotcha as sorento_crm_mcp PR #109). n8n half is a separate follow-up (report PR-B).

## Out of scope / backlog

- `crm_order_analytics` blended aggregates (report 5.2).
- n8n `crossdomain-zeroset` first-wins-by-code and `_IDENTITY_KEYS` (report 5.3, 5.4).
- Non-presenter scoped tools (`crm_master_brands_list`, `..._customers_list`,
  `crm_inventory_warehouses_list`): the `ListResponse` key is reusable when they need it.
