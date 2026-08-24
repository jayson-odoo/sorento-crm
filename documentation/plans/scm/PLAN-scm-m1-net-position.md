# PLAN - SCM M1: Net-Position Dashboard

**Slug:** `scm-m1-net-position` · **Milestone:** M1 · **UAC:** `scm-m1-net-position-acceptance-criteria.md`
**Umbrella:** `PLAN-scm-reorder-copilot.md` · **Depends:** M0 · **Status:** DRAFT (grilled, pre-code)

## Goal
The visibility layer - one attention-first dashboard, three perspectives (Product / Warehouse /
Supplier), that reconciles net position + stock valuation to reality. No engine, no recommendations.

## Phase 1 - FE prototype (mock-first; drive `frontend-design` + `dataviz` skills)
- Route `/scm` (sidebar entry under an "SCM" group, gated by module + `scm.dashboard.view`).
- **Perspective toggle** (Product / Warehouse / Supplier), shared filter bar.
- **Warehouse perspective:** box grid - one card/warehouse, health colour, warehouse valuation, stockout/dead counts. Reuse stat-tile/card components.
- **Product perspective:** aggregated DataGrid (SKU rows) + expand → per-warehouse breakdown. Columns: SKU, net position, on-hand, on-order, committed, **stock valuation**, last-movement, status badge; deferred columns (avg-daily-demand, DoC, ROP) present but "-".
- **Supplier perspective:** per-supplier SKUs, lead-time (declared), incoming-PO timeline.
- **Roll-up tiles:** total valuation, dead-stock valuation, stockout count, incoming-PO timeline; deferred tiles "-".
- **States:** loading / empty (explicit CTA) / error / partial / data - all mocked.
- **Colour system (dataviz):** diverging ramp for health (stockout→healthy→overstock), accessible light+dark, contrast-checked. **frontend-design** for layout/visual direction.
- Verify in browser (Playwright MCP, sidebar nav), screenshot golden + edge states. Document the API contract at the top of `scmDashboardService.ts`. **No BE, no tests yet.**

## Phase 2 - Wire to M0 views (test-first / TDD)
- **BE:** `list_query_registry` adapter `scm_net_position` → `scm_net_position_v` (+ per-perspective serializers). Endpoints under `require_module_enabled_with_api_key("scm")`:
  - `GET /api/v1/scm/dashboard/net-position` (product perspective, paginated, `buildDataGridParams`)
  - `GET /api/v1/scm/dashboard/warehouses` (warehouse boxes + health + valuation)
  - `GET /api/v1/scm/dashboard/suppliers` (supplier perspective)
  - `GET /api/v1/scm/dashboard/rollups` (stat tiles)
  - export via `scm.dashboard.export`.
- Reads M0 views: `scm_net_position_v`, `scm_on_order_v`, `scm_committed_v`. Status computed in SQL/service: stockout (on_hand=0), dead (last-movement > `dead_stock_days`), healthy, incoming (open PO). Imbalance flag = per-warehouse min stocked-out while another > 0. Attention sort key in the query.
- Valuation = `on_hand × products.cost_price`, per SKU×warehouse, subtotal + grand total.
- **FE:** swap mocks for real hooks/services/`api-client`. Delete mock fixtures (keep any reused by tests).
- **Test-first order (red→green):**
  1. pytest: net-position view returns hand-computed seed values; valuation math; status classification; aggregation + imbalance flag; auth 403; decoupling (no legacy tables).
  2. vitest: component states, perspective toggle, deferred-"-" rendering, attention badge/sort.
  3. playwright: sidebar → dashboard → 3 toggles → expand warehouse → filter → assert `/api/v1/*` + console clean, 375px + 1280px.

## Phase 2b - SO management (no-orphan-tables; M1-D14)
- **BE:** `sales_order`/`sales_order_line` CRUD endpoints (list via `list_query_registry` adapter, create/edit/delete) under `require_module_enabled_with_api_key("scm")`; `create_do_from_so(so_id)` service - creates a DO (`orders`/`order_lines`), stamps `sales_order_line.qty_delivered` (soft link, no hard FK). Numbering via `NumberingService` (`SO-…`).
- **FE:** SO list page (DataGrid + "Add SO" toolbar → modal; edit modal; `ConfirmDeleteDialog`), `order_type` + customer via `SearchableSelect`, `priority` field. "Create DO" row action → confirm dialog. Reuse shared DataGrid/bulk-action/modal-CRUD components.
- **Tests (test-first):** pytest SO CRUD (happy/auth/validation) + `create_do_from_so` (stamps qty_delivered, committed drops); vitest SO list/modal states; playwright SO create → create-DO → dashboard committed updates.

## Phase 3 - Review
`/code-review` → `--fix`/`/simplify` → PR. Checklist: CRUD-UX (every section renders, empty states),
no-UUID, SearchableSelect, extractApiError, buildDataGridParams, fixed table layout, mobile-scroll.

## Reuse (no new one-offs)
DataGrid, stat-tile/card, `SearchableSelect`/`SearchableMultiSelect`, `extractApiError`,
`buildDataGridParams`, mutation/query hook factories. Colour tokens via dataviz palette (light+dark).

## Risks
- **Aggregation masking** - network-aggregated row must surface per-warehouse imbalance (imbalance flag) or a stockout hides. Tested (AC-M1.2).
- **Big-catalog perf** - server-side pagination mandatory; index support from M0.
- **Honesty** - deferred demand/engine columns must read "-", never a placeholder number (AC-M1.7).
- **cost_price nulls** - some products may lack `cost_price`; valuation shows "-" for those + a coverage note, not 0.
