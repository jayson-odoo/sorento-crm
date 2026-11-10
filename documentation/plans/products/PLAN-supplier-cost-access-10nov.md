# PLAN: Supplier tab and cost data restricted to purchasing and management

Status: Merge-ready pending owner hand test and three crew rulings (PR #2319). Track: full
(RBAC change + data migration).

Lane: SUPPLIER-COST-ACCESS. Source: owner + management meeting 9 Nov 2026, relayed 10 Nov.

## Decisions (owner relayed)

1. The product Supplier tab (suppliers, unit costs, last purchase / PO costs) is visible only to
   purchasing and management roles. Marketing and sales roles do not see it. Dealers never see cost.
2. History still shows THAT a cost / supplier change happened (who, when, which field), but the
   values are masked for users without the cost permission. Raw JSON stays admin-only.

## Why sales sees the Supplier tab today

The tab is already gated (`ProductDetail.tsx:85`, `ProductForm.tsx:99`) on
`procurement.product_suppliers.view`, but migration `cpc1_supplier_cost_lists.py:76-81`
(`_PRODUCT_ROLE_SWEEP`) granted that slug to every role holding `master_data.products.view`,
so every products viewer (sales, marketing) holds it. Admin/superadmin bypass every check
(`user_service.py:1591`).

## Answers (crew + owner, 10 Nov 2026)

- Q1 (a): new `products.cost.view`, additive. Q3 (a): invoice price stays visible. Q4 (a): the
  whole Purchase History tab is hidden without it. Q5 (a): Procurement > Product-Suppliers and the
  supplier Costs tab also need it.
- Q2, owner confirmed ("I am fine with the cost access rules"): grant by slug to admin, director,
  purchasing_manager, purchasing, purchasing_executive (superadmin bypasses). Not granted:
  salesperson, retail:salesperson, portal_user, customer_service, project.customer.service (holds
  product_suppliers.view + cost_price_changes.view today and loses cost), project_sales_coordinator,
  project_sales_manager, marketing_executive, marketing_manager, warehouse_manager,
  warehouse_executive, technical executive, guest. No sweep from an existing slug for that reason.
- Integrations: none granted. `integration_foundryx_esb` reads cost through its own raw master
  read (`app/services/master_read_service.py:92`, `app/api/v1/external/ingest.py:92`), unchanged,
  and is the system that writes cost. MCP and the chatbot never receive cost (MCP strips it;
  the chatbot's PO last cost keeps its per-contact field reveal on the plain-key path).
- Dealer portal: the 9 Nov decision replaces PQ1's "the portal sees cost".

## Surfaces (file:line, current gate -> new gate)

Backend (`sorento_crm_backend/`):

| # | Surface | file:line | Today | After |
|---|---|---|---|---|
| B1 | Product list + detail (`cost_price`, also list-query column/filter/sort/export) | `app/api/v1/master_data/products.py:115,286`; `app/schemas/product.py`; `list_query_registry.py:118`; `product_service.py:525` | login | `cost_price` returned as null without the permission; filter/sort/export on it refused; create/edit ignore a `cost_price` sent by a non-holder (the form would otherwise wipe it) |
| B2 | Product purchase history (PO unit cost, supplier, last-cost summary) | `products.py:303`; `product_purchase_history_service.py:44,114` | login | 403 without the permission |
| B3 | Product-supplier links + cost rows | `app/api/v1/procurement/product_suppliers.py:29,56,128,194-223` | `procurement.product_suppliers.*` | also requires the cost permission |
| B4 | PO last-cost lookup, staff session | `app/api/v1/procurement/purchase_orders.py:37` | API-key reads only | staff session needs the cost permission; contacts keep field reveal |
| B5 | Product History (audit `old_values`/`new_values` of `cost_price`) | `app/api/v1/audit/audit_logs.py:291,373` | any products viewer sees values | values replaced by `"hidden"` for non-holders; field name, who, when kept |
| B6 | Portal new product application (dealer) `cost_price` | `app/api/v1/public/portal_new_product_application.py:77`; `new_product_application_service.py:1658` | contact owns record | `cost_price` never returned to a contact |
| B7 | Staff AI assistant `cost_price` field | `assistant_registry/products.py:12,44` | `procurement.cost_price_changes.view` | the cost permission |
| B8 | Analytics connector product rows | `analytics_connector/reused_tools.py:430` | raw route response | covered by B1 (acts as the user) |
| B9 | MCP / chatbot product + promotion tools | `sorento_crm_mcp/server.py:917,1025` | always dropped | unchanged |
| B10 | MCP / chatbot last PO cost | `chatbot/agent/tools.py:120`; `contact_field_reveal_service.py:64,103` | contact field reveal | unchanged |
| B11 | SCM reorder, PO book last cost, order sheet export | `scm/reorder_runs.py:864,1040`; `scm/purchase_order_service.py:902`; `scm/order_summary.py:119` | `scm.dashboard.view` (purchasing) | unchanged (purchasing-only screens) |
| B12 | Cost price change sets | `procurement/cost_price_changes.py:73-220` | `procurement.cost_price_changes.*` | unchanged |

Frontend (`sorento_crm_frontend/app/(protected)/`):

| # | Surface | file:line | After |
|---|---|---|---|
| F1 | Product detail Suppliers tab | `master-data-management/products/[id]/components/ProductDetail.tsx:85,330,632` | hidden without the permission |
| F2 | Product detail Purchase History tab | `ProductDetail.tsx:322,621` | hidden |
| F3 | Overview "Cost Price" + "Last purchase price" card | `ProductDetail.tsx:413-470` | hidden |
| F4 | Product form Suppliers tab + Cost Price input | `products/components/ProductForm.tsx:99,337,683,1065` | hidden |
| F5 | Products list cost price column | list-query metadata | column not offered |
| F6 | Product History tab | `components/audit/AuditTrail.tsx`, `lib/audit-fields.ts:77` | "Cost price changed", values "hidden" |
| F7 | Procurement > Product Suppliers menu, Supplier detail Costs tab | `config/menu.config.tsx:445`; `suppliers/[id]/components/SupplierDetail.tsx:36` | also need the permission |

## Tests (red first, both ways per surface)

With and without `products.cost.view`: B1 detail + list (null vs value), B1 sort/filter refused,
B2 403 vs 200, B3 403 vs 200, B4 staff 403 vs 200, B5 masked vs raw, B6 contact never sees it,
B7 assistant field refused, migration grants (purchasing name, derived, management slug, not
sales). Vitest: F1-F4, F6.
