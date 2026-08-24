# PLAN - SCM M0: Foundation

**Slug:** `scm-m0-foundation` · **Domain:** scm · **Milestone:** M0
**UAC:** `scm-m0-foundation-acceptance-criteria.md` · **Umbrella:** `PLAN-scm-reorder-copilot.md`
**Status:** DRAFT (grilled, pre-code) · **Type:** BE-only (schema/infra/seed; no prototype UI)

## Goal
Lay the whole foundation so M1 - M5 are pure feature work: schema split (public core + `scm` brain),
views, module registration (dormant), RBAC, numbering, and a curated demo seed on **real products**.

## 1. Migrations (one revision)
- `op.execute("CREATE SCHEMA IF NOT EXISTS scm")`.
- **public:** create `sales_order`, `sales_order_line`, `purchase_order`, `purchase_order_line` (cols per umbrella §1.2). Alter `product_suppliers` (+moq, order_multiple, unit_cost, currency, is_primary_supplier, lead_time_variability_days); alter `suppliers` (+current_performance_score); alter `picking_lines` (+po_line_id soft FK, qty_accepted, qty_rejected).
- **scm:** create the 13 brain tables, each `__table_args__={"schema":"scm"}`, FKs to `public.*` as normal cross-schema FKs.
- **Views:** create the 5 position/consumption views (regular). **`scm.demand_stat`** table (empty; M2 fills).
- **Gotchas:** `down_revision` = current committed main head (memory `project_migration_downrev_uncommitted_ancestor`); verify `alembic heads`=1 first, `alembic merge` if forked (memory `project_alembic_dual_head_merge`); make schema create idempotent. `downgrade` drops views → scm schema (CASCADE) → public columns → public tables.

## 2. Models
- `app/models/scm.py` - brain tables (schema-pinned). Public SO/PO in `app/models/order.py` (SO next to Order/DO) + `app/models/procurement.py` (PO next to suppliers/PR) for domain consistency. Register in `app/models/__init__.py`.
- Extend `ProductSupplier`, `Supplier`, `PickingLine` in place.

## 3. Views (read-model; decoupling boundary - AC-M0.11)
- `scm_on_order_v` - open PO lines `Σ(qty_ordered−qty_received)` by product×warehouse.
- `scm_committed_v` - open SO lines `Σ(qty_ordered−qty_delivered)` + priority + demand_nature.
- `scm_consumption_v` - DO/`stock_ledger` outbound by product×warehouse×day, channel-tagged.
- `scm_net_position_v` - `stock.on_hand + on_order − committed`.
- `scm_receipt_lead_v` - per seeded PO→GR pair: `receipt_date − issue_date`, qty_accepted/rejected/discrepancy.
- Read **only** canonical `public` tables - never `inbound_shipments`/`spo_allocations`.
- Supporting indexes: PO/SO lines by (product_id, warehouse_id, line_status); stock by (product_id, warehouse_id).

## 4. Module registration
- `MODULE_MANIFEST._RAW["scm"]` = display "Supply Chain & Inventory Optimisation", deps `{base,product,inventory,order,procurement}`.
- `app/modules/scm/bootstrap.py` → `MODULE_KEY="scm"`.
- Catalog seed row `installed=false` (dormant). Sidebar entry gated by module + `scm.dashboard.view`.
- Routes mounted in `app/api/v1/__init__.py` under `require_module_enabled_with_api_key("scm")` (routers arrive with feature milestones; M0 just wires the guard + an empty router if needed).

## 5. RBAC + numbering
- Seed permission slugs (M0-D4) + grant to `admin` + new `purchasing` role (seed the role).
- `DocumentNumberingRule` rows for `sales_order` / `purchase_order`; use `NumberingService.next(doc_type)`.

## 6. Seed script - `scripts/seed_scm_demo.py` (requires DB up)
1. **Pick SKUs:** query real data for representatives  - 
   - fast dealer mover (high steady `stock_ledger` outbound),
   - lumpy project item (bursty outbound),
   - dead (no movement > policy days),
   - stockout (on_hand=0 with prior demand),
   - multi-warehouse (stock in ≥2 warehouses),
   - one that will carry an open PO.
2. **Customers:** top-N by DO line count → seed open SO (committed) with `order_type` (continuous/spike mix) + `priority`.
3. **Suppliers:** seed a few plausible sanitaryware suppliers; `product_suppliers` (extended cols) for demo SKUs; seed PO + GR (`picking_headers` `picking_type='goods_received'`, linked via `source_entity_type='purchase_order'` + `picking_lines.po_line_id`) with staggered issue/receipt dates so lead-time + reject-rate compute.
4. **Policies + budget:** global + one class + one SKU `reorder_policy` (different methods) + one `purchasing_budget`; `demand_nature_map`; `override_reason` + `reason_action_map` starter vocab; `supplier_scoring_policy`.
5. All rows `source_system='seed'`. Idempotent (upsert by natural key / `source_ref`).

## 7. Tests (test-first - TDD, red→green→refactor; use `tdd` skill)
- Migration up/down (AC-M0.1); cross-schema FK integrity (AC-M0.2); `source_system` presence (AC-M0.3).
- Module guard: dormant hides for normal role, resolves for admin (AC-M0.4); manifest topo order (AC-M0.5).
- RBAC denial 403 (AC-M0.6); numbering format (AC-M0.7).
- View correctness vs hand-computed seed (AC-M0.8, AC-M0.11 decoupling); `demand_stat` shape (AC-M0.10).
- Seed coverage assertion - all patterns present (AC-M0.9).
- Golden-set fixture files committed (numbers blessed M3).

## 8. Risks
- **DB must be up** for the seed script (was down at plan time - boot local stack first).
- **Supplier realism** - seed plausible generic suppliers; do NOT fabricate real company identities/records (keep names clearly generic).
- **Dual-head/down_revision** - check before writing the revision.
- **product_suppliers already in public** - extend, don't recreate.

## 8b. Build-time findings (M0, confirmed against the prod-copy - carry into later milestones)
- **⚠ COST/PRICE DATA GAP (client-facing).** Only ~6,175 / 11,415 products have a non-zero `list_price`; **`cost_price` is null/0 on essentially all**, and the high-volume movers (WESERP10B, CWCY605…) are unpriced. Valuation (M1), ABC annual-value + margin (M2), and cash impact/ranking (M4) all need cost data - they will be **thin/zero on real prod until cost data exists**. The demo seed sets plausible `cost_price` on ~20 SKUs; **real value depends on the client supplying cost data.** Raise with the client.
- **`stock_ledger` is snapshot/bulk-import only** (`BULK_IMPORT` + `SYSTEM_ADJUSTMENT`; no per-DO sales rows). So consumption/demand sources from **DO `order_lines`**, not the ledger - `scm.consumption_v` already reads DO. **Update the M2 plan accordingly.**
- **`GRANT CREATE ON DATABASE ... TO <app_role>`** is required before the `scm` schema can be created (the app role has CREATE on `public` but not on the database). **Add this GRANT to the prod deploy steps, before `alembic upgrade`.**
- **Demo seed is prod-guarded** - refuses unless `SCM_DEMO_SEED=1` AND a local DB host. Deploy applies migrations 273/274 + the GRANT only; **never the seed.**
- **`product_suppliers.supplier_id` FK is `ON DELETE RESTRICT` in the live DB but the model declares `CASCADE`** - pre-existing mismatch (not introduced here); note for a future reconciliation.
