# UAC - SCM M0: Foundation (schema, views, module, seed)

> Given/When/Then contract for milestone M0. Test report keys back to these ids. Parent umbrella:
> `scm-reorder-copilot-acceptance-criteria.md`. Governs: `PRINCIPLES.md`.

**Slug:** `scm-m0-foundation` · **Domain:** scm · **Milestone:** M0 · **Status:** DRAFT (grilled, pre-code)

## Scope

Foundation only - no engine, no dashboard yet. Deliver: the `scm` Postgres schema + brain tables,
public `sales_order`/`purchase_order`, extensions to `product_suppliers`/`suppliers`/`picking_lines`,
position views + demand-stat table structure, module registration (dormant), RBAC, numbering, a
curated **demo seed on real products**, and golden-set fixture files (structure; numbers blessed in M3).

## Locked decisions (from M0 grill)

| # | Decision |
|---|---|
| M0-D1 | **Schema split:** public = `sales_order`, `sales_order_line`, `purchase_order`, `purchase_order_line`, + alters to `product_suppliers`/`suppliers`/`picking_lines`. `scm` schema = the 13 brain tables. Cross-schema FKs `scm.*` → `public.*` (Postgres-native). |
| M0-D2 | **One Alembic revision:** `CREATE SCHEMA IF NOT EXISTS scm`; create brain + public tables; alter the three existing. `down_revision` = current **committed** main head (verify `alembic heads`=1; `alembic merge` if forked). Idempotent schema create. |
| M0-D3 | **Module reg:** add `scm` to `MODULE_MANIFEST` (deps `base`,`product`,`inventory`,`order`,`procurement`) + `bootstrap.py` `MODULE_KEY="scm"` + catalog seed row **`installed=false`** (dormant). All routes `Depends(require_module_enabled_with_api_key("scm"))`. |
| M0-D4 | **RBAC slugs:** `scm.dashboard.view`, `scm.reorder.run`, `scm.recommendation.manage`, `scm.policy.manage`, `scm.config.manage`. Granted to `admin` + new `purchasing` role. |
| M0-D5 | **Numbering:** `DocumentNumberingRule` doc_types `sales_order` (`SO-YYYY/MM-####`) + `purchase_order` (`PO-YYYY/MM-####`) via `NumberingService`. |
| M0-D6 | **Views:** position views (`scm_net_position_v`, `scm_on_order_v`, `scm_committed_v`, `scm_consumption_v`, `scm_receipt_lead_v`) = **regular/live** SQL views + supporting indexes. **Demand rate = stored** in a `scm.demand_stat` table (written by the M2 job; M0 creates the table only). |
| M0-D7 | **`source_system`/`source_ref`** on every new table; `'seed'` for demo rows, `'manual'` for future UI rows. |
| M0-D8 | **Seed = curated set A.** Build-time query of real data picks ~15 - 25 representative products by movement pattern (fast dealer mover, lumpy project, dead, stockout, multi-warehouse, one-with-open-PO). |
| M0-D9 | **SO seed from real customers** - pick customers with the most DOs (`orders`/`order_lines`); create plausible open SO (committed) for them over the demo SKUs, with `order_type` + `priority`. |
| M0-D10 | **Suppliers seeded** (none exist yet) - a few plausible Sorento-sanitaryware suppliers; `product_suppliers` rows (extended cols: moq/order_multiple/unit_cost/currency/is_primary/lead_time_variability) for demo SKUs; seed PO + GR (`picking_headers` goods_received) history so measured lead time + quality compute. |
| M0-D11 | **Policies + budget seeded** - at least one `reorder_policy` per scope level (global + one class + one SKU) exercising different methods; one `purchasing_budget`. |
| M0-D12 | **create-DO-from-SO / create-GR-from-PO deferred** to M1/M4 (their consumer UI). M0 seeds rows directly. |
| M0-D13 | **Golden-set fixture files** created (structure + the curated SKUs) in git; expected ROP/SS/net/qty **blessed in M3**, not M0. |
| M0-D14 | **Admin drives the demo** (module guard short-circuits for superadmin/admin) while module stays dormant for normal roles. Deal close → flip `installed=true` + grant `purchasing`. |

## Acceptance criteria

- **AC-M0.1** GIVEN the migration WHEN run on a copy of prod THEN `scm` schema + all tables exist, the three existing tables gain their columns, `alembic heads` = 1, and `downgrade -1` cleanly drops the schema + columns.
- **AC-M0.2** GIVEN a `scm.*` brain table with an FK to `public.products`/`suppliers` WHEN a row is inserted with a bad ref THEN the cross-schema FK rejects it (integrity preserved, not deferred to service layer).
- **AC-M0.3** GIVEN every new SCM table WHEN inspected THEN it has `source_system` + `source_ref`; all seeded rows carry `source_system='seed'`.
- **AC-M0.4** GIVEN SCM disabled for a tenant WHEN a normal-role user browses THEN no SCM sidebar entry/route resolves; WHEN a superadmin/admin browses THEN SCM resolves (dormant-but-demoable).
- **AC-M0.5** GIVEN the module manifest WHEN install resolves THEN `scm` topo-sorts after its deps (base/product/inventory/order/procurement).
- **AC-M0.6** GIVEN the RBAC slugs WHEN seeded THEN admin + `purchasing` hold the SCM view/manage grants and a role lacking them is denied (403) on SCM routes.
- **AC-M0.7** GIVEN `NumberingService` WHEN a SO/PO number is requested THEN it returns `SO-YYYY/MM-####` / `PO-YYYY/MM-####` monotonic per period.
- **AC-M0.8** GIVEN the position views WHEN queried for a demo SKU THEN `scm_net_position_v` returns `on_hand + on_order − committed` matching hand-computed values from the seed; `scm_receipt_lead_v` returns `receipt_date − issue_date` per seeded PO→GR pair.
- **AC-M0.9** GIVEN the seed WHEN loaded THEN the ~15 - 25 curated SKUs cover every target pattern (fast/lumpy/dead/stockout/multi-warehouse/open-PO), SO tie to real high-DO customers, and seeded suppliers + product_suppliers + PO + GR exist for them.
- **AC-M0.10** GIVEN `scm.demand_stat` WHEN created THEN it holds the stored-rate columns (per SKU×warehouse: avg_daily_demand, variability, window, channel-adjusted, computed_at) - populated by M2, empty at M0.
- **AC-M0.11 (decoupling)** SUPERSEDED 6 Aug 2026, narrowed. Originally: the position/consumption views read only canonical `public` tables and never `inbound_shipments`/`spo_allocations`. The domain says the SPO allocation IS the incoming stock (chain PO -> SPO -> GRN), so `scm.on_order_v` now reads it by design (migration 337). GIVEN the DEMAND and CONSUMPTION views (`committed_v`, `consumption_v`, `net_position_v`, `receipt_lead_v`) WHEN inspected THEN they reference neither `inbound_shipments` nor `spo_allocations`, AND `on_order_v` DOES reference `spo_allocations` and does NOT reference `purchase_order_lines` - counting both would double every shipped order, since `spo_allocations.po_line_id` is NULL on every existing row.

## Build steps (three-phase)
1. **Phase 2 (BE-only milestone - no prototype UI):** models (public + `scm`), one migration, views, module manifest + bootstrap + catalog seed, RBAC seed, numbering rules, `demand_stat` table.
2. **Seed script** (`scripts/seed_scm_demo.py`): connect to real DB, pick representative SKUs + high-DO customers, seed suppliers/product_suppliers/SO/PO/GR/policies/budget with `source_system='seed'`. **Requires the DB up.**
3. **Tests:** pytest - migration up/down, cross-schema FK integrity, module-guard dormant-vs-admin, RBAC denial, numbering format, view correctness vs hand-computed seed, decoupling test. Golden-set fixture files committed.

## Deferred to later milestones
create-DO-from-SO / create-GR-from-PO functions (M1/M4); demand-stat population (M2); dashboard (M1);
golden expected-number blessing (M3); broad synthetic backfill (post-trust).
