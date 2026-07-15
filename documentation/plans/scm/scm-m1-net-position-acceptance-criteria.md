# UAC — SCM M1: Net-Position Dashboard (visibility layer)

> Given/When/Then contract for milestone M1. Parent umbrella: `scm-reorder-copilot-acceptance-criteria.md`.
> Depends on M0 (schema + views + seed). Governs: `PRINCIPLES.md` + `ADR-PRODUCT-STANDARDS.md`.

**Slug:** `scm-m1-net-position` · **Domain:** scm · **Milestone:** M1 · **Status:** DRAFT (grilled, pre-code)

## Scope
The **visibility layer** — no recommendations, no engine. One dashboard that mirrors the buyer's
mental model and **reconciles net position to reality**, earning trust before the engine speaks.
Attention-first: the buyer instantly sees which SKUs/warehouses/suppliers need eyes.

## Locked decisions (from M1 grill)

| # | Decision |
|---|---|
| M1-D1 | **Position-only, honest (path A).** Real at M1: on-hand, on-order, committed, **net position**, **stock valuation**, last-movement, stockout/dead status, incoming-PO timeline. **Deferred (prototyped but rendered "—")**: avg-daily-demand, days-of-cover, ROP, low/reorder-due, overstock, ABC/XYZ — they light up in M2/M3. **No fake numbers.** |
| M1-D2 | **Grain = SKU aggregated across a selected warehouse set, expandable to per-warehouse** (path B). Server-paginated/sorted/filtered via `buildDataGridParams`. Aggregation is meaningful under network buying; the aggregated row **flags imbalance** so a per-warehouse stockout isn't masked by another warehouse's surplus. |
| M1-D3 | **One dashboard, a Product / Warehouse / Supplier perspective toggle** (shared filters) — not three pages. |
| M1-D4 | **Warehouse perspective = box grid** — one card per warehouse, colour = health state; at-a-glance "where to look." |
| M1-D5 | **Health-state vocabulary + colours** (dataviz: diverging, accessible in light AND dark): stockout=red **(M1)**, dead=grey **(M1)**, healthy=green **(M1)**, incoming=blue badge **(M1)**, low/reorder-due=amber **(M3)**, overstock=purple **(M2)**. Prototype all six; wire four at M1. |
| M1-D6 | **Overstock = days-of-cover > a configurable ceiling** (`overstock_days` on `reorder_policy`) → **M2** (needs demand). No max-stock-level field today; do NOT invent one. |
| M1-D7 | **Stock valuation** (renamed from "cash tied up") = `on_hand × products.cost_price`, **per SKU×warehouse**, with warehouse subtotal + grand total. |
| M1-D8 | **Roll-ups (stat tiles):** total stock valuation, dead-stock valuation, stockout count, incoming-PO timeline = **M1-real**. Below-ROP count + overstock valuation = **deferred M2/M3** ("—"). |
| M1-D9 | **Filters (M1):** warehouse-scope (multi), product class, colour/variant, supplier — all `SearchableSelect`/`SearchableMultiSelect`. **ABC/XYZ filter deferred to M2.** |
| M1-D10 | **Attention signal** = "stockout WITH committed demand" → **priority badge + default sort** (stockout-with-committed → stockout → low → dead). Not a new colour. |
| M1-D11 | **last-movement** = `max(stock_ledger.created_at)` per SKU×warehouse. **Export** via `scm.dashboard.export` (reuse DataGrid export). |
| M1-D12 | **DataGrid registration** — `list_query_registry` adapter `scm_net_position` mapping to `scm_net_position_v`, serializer, `view_slug='scm.dashboard.view'`. |
| M1-D13 | **Three-phase.** Phase 1 = prototype whole dashboard on mocks (drive **frontend-design** + **dataviz** skills). Phase 2 = wire to M0 views, **test-first**. Phase 3 = review. |
| M1-D14 | **SO management ships in M1** (no-orphan-tables matrix). `sales_order`/`sales_order_line` CRUD list (DataGrid + modal create/edit + confirm-delete) + **create-DO-from-SO** function (soft link, stamps `qty_delivered`). SO is the committed-demand business record; it belongs with the first UI. `order_type` (lookup) + `priority` + customer (`market_segment` drives demand_nature) captured on the SO. Reuse shared DataGrid/bulk-action/modal-CRUD components. |

## Acceptance criteria

### Correctness (reconciliation)
- **AC-M1.1** GIVEN a demo SKU with seeded stock + open PO + open SO WHEN the grid renders THEN `net_position = on_hand + on_order − committed`, matching hand-computed seed values.
- **AC-M1.2** GIVEN a SKU stocked in ≥2 warehouses WHEN the aggregated row renders THEN it sums across the **selected** warehouse set and expands to a correct per-warehouse breakdown; an **imbalance flag** shows when one warehouse is stocked out while another has surplus.
- **AC-M1.3** GIVEN a warehouse WHEN valuation computes THEN per-SKU valuation = `on_hand × cost_price`, warehouse subtotal = Σ, grand total = Σ warehouses; roll-up tiles match.
- **AC-M1.4** GIVEN `dead_stock_days` WHEN a SKU has no outbound movement beyond it THEN status=dead; GIVEN on_hand=0 with prior demand THEN status=stockout.

### Visibility / UX
- **AC-M1.5** GIVEN the dashboard WHEN loaded THEN a Product/Warehouse/Supplier toggle switches perspective with shared filters; **every section renders even when empty** (explicit empty state + CTA).
- **AC-M1.6** GIVEN the Warehouse perspective THEN one card per warehouse shows its health colour; colours are legible in **light and dark** and meet contrast (dataviz).
- **AC-M1.7** GIVEN deferred columns/states (demand, DoC, ROP, low, overstock, ABC/XYZ) WHEN M1 renders THEN they show "—"/disabled with a "available in a later step" affordance — **never a fabricated number**.
- **AC-M1.8** GIVEN the default sort THEN rows order attention-first (stockout-with-committed → stockout → low → dead); the "stockout with committed demand" badge shows on qualifying rows.
- **AC-M1.9** GIVEN filters WHEN applied THEN warehouse/class/colour/supplier narrow the set server-side via `buildDataGridParams`; dropdowns are `SearchableSelect`.

### SO management (M1-D14)
- **AC-M1.14** GIVEN the SO list WHEN opened THEN it renders `sales_order` rows (DataGrid, server-paginated), create/edit via modal, hard-delete with confirm dialog; `order_type` (lookup/`SearchableSelect`), `priority`, and customer are captured; no UUIDs shown.
- **AC-M1.15** GIVEN an open SO WHEN "create DO from SO" runs THEN a DO is created, the SO line's `qty_delivered` is stamped (soft link, no hard constraint), and the dashboard's `committed` for that SKU drops accordingly.
- **AC-M1.16** GIVEN an SO's customer WHEN saved THEN its `market_segment` (→ demand_nature) is resolvable, so M2 can channel-tag committed demand.

### Conventions / plumbing
- **AC-M1.10** GIVEN a big catalog THEN the grid is server-paginated/sorted (no client-side full load); DataGrid uses `tableLayout:{width:'fixed',columnsResizable:true}`, explicit `size`, truncate+title.
- **AC-M1.11** GIVEN the module dormant THEN the dashboard is reachable by admin only (guard short-circuit); normal roles see no sidebar entry. **No UUIDs shown** — SKU/warehouse/supplier by human-readable identifier.
- **AC-M1.12** GIVEN the views WHEN read THEN they hit only canonical `public` tables (decoupling test); FE uses `extractApiError`; layering hooks→service→api-client.
- **AC-M1.13 (verify)** Playwright: sidebar → SCM dashboard → toggle all three perspectives → expand a warehouse breakdown → apply a filter → assert correct `/api/v1/*` calls + console clean, at 375px AND 1280px.

## Tests (test-first — TDD; use `tdd` skill)
- **pytest:** view/endpoint correctness vs hand-computed seed (net position, valuation, status, aggregation, imbalance flag); auth denial; decoupling test.
- **vitest:** each component's loading/empty/error/data states; perspective toggle; deferred-column "—" rendering; attention sort/badge.
- **playwright:** AC-M1.13 flow.

## Deferred to later milestones
avg-daily-demand, days-of-cover, ROP, low/reorder-due status, overstock (+`overstock_days`), ABC/XYZ
filter → M2/M3. Recommendations / Accept-Adjust-Dismiss → M4.
