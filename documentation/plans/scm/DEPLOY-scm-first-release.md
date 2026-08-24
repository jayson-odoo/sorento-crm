# SCM first production release - deployment plan (demo)

> Status: DRAFT 2026-07-18. First-time production deployment of the ENTIRE SCM module
> (M0 - M8), branch `feat/scm-reorder-copilot`. Goal: **zero regression, zero visible change
> for existing (non-SCM) users**, + a live-safe demo seed covering buy & allocation.

## 0. What is actually shipping

Not just the recent review fixes. `feat/scm-reorder-copilot` forked from `main` at migration
`271` and carries the **whole SCM module**: 246 files / ~47k insertions. SCM is **not yet on
main** (`git ls-tree main … app/(protected)/scm` = 0). So merge+deploy ships all of SCM to prod
for the first time.

## 1. Zero-regression analysis (audited 2026-07-18)

### 1a. Migrations - SAFE (additive)
- Every new table is in the **`scm.*` schema** (invisible to existing modules).
- Additive ALTERs on **6 shared tables**, all nullable or NOT NULL + `server_default` (backfilled):
 - `273`: `suppliers`, `product_suppliers`, `customers` (`market_segment_code`), `market_segments`
    (`demand_nature`), `picking_lines`. `Supplier.is_primary_supplier` NOT NULL **with
    server_default=false** → safe.
 - `275`: `sales_orders.requested_delivery_date` (nullable date).
 - `285`: `scm.market_signal.sources` (JSONB, scm schema).
- `ADD COLUMN` on nullable / default-false is a fast, brief lock in Postgres. Deploy runs during a
  low-traffic window (blue/green, see §4) so the lock is a non-issue.
- **No existing column, type, or constraint is changed or dropped.**

### 1b. Backend shared code (13 files) - SAFE (all additive)
New router mounted behind `require_module_enabled_with_api_key("scm")`; new models + nullable cols;
**2 new AI prompt keys** (`scm_recommendation_explainer`, `scm_market_advisory`) - no existing prompt
touched, so existing assistant answers are unchanged; **2 new scheduler handlers**
(`scm_analytics`, `scm_reorder_run`) registered additively and failure-guarded (a failed SCM run
cannot crash the heartbeat); 1 new optional config key (`anthropic_api_key`, default None). No
existing function/field/relationship/RBAC grant/scheduled task modified.

### 1c. Frontend shared code
| File | Verdict | Note |
|------|---------|------|
| `config/menu.config.tsx` | SAFE | adds one "Supply Chain" group gated by `moduleKey:'scm'` + SCM permissions; existing entries/order/permissions untouched |
| `css/config.reui.css` | SAFE | only new `--scm-*` / `--color-scm-*` tokens; no existing selector/var redefined |
| `lib/route-module-map.ts` | SAFE | one new `/scm → scm` entry |
| `components/ui/tooltip.tsx` | **REVIEW** | global default change: base z-index `z-50→z-[70]` + `TooltipPrimitive.Portal` wrap. Applies to **every** tooltip app-wide. Low functional risk but must get a 5-min visual smoke across a couple of existing pages (tooltip vs dialogs/popovers stacking + positioning) before deploy |
| `system-management/ai-assistant/AIAssistantSettingsForm.tsx` | additive UX | existing admin page gains a visible "Anthropic API key" field. Expected/benign, but it IS a new field on an existing page |

### 1d. "New columns invisible to existing users" ✓
- All new `scm.*` tables + the additive shared-table columns are **not surfaced in any existing
  module UI** (no existing grid/form/list was changed). The reorder page and every new column live
  entirely under the `/scm` route (module- + permission-gated).
- **Nav/permission gate is the guarantee:** SCM routes require `scm.*` permissions
  (`scm.dashboard.view`, `scm.reorder.run`, …). Existing roles do **not** hold these, so existing
  users get no SCM nav entries and 403 on SCM APIs. → Only the demo account (granted an SCM role)
  sees SCM. **Verify at deploy:** existing roles unchanged; SCM permissions granted only to the demo
  role.
- Residual visible-to-all changes: the tooltip render (§1c) and the admin AI-key field. Everything
  else is invisible.

## 2. Pre-commit hygiene (blockers)
1. `git rm --cached sorento_crm_frontend/tsconfig.tsbuildinfo` - tracked on main + modified; the new
   `.gitignore` does not untrack it.
2. `git rm --cached -r sorento_crm_frontend/playwright-report/` - same.
3. Delete stray `sorento_crm_frontend/sorento_crm/` (a mis-created nested `node_modules` copy;
   untracked, must never be `git add`ed). Add a `.gitignore` guard.
4. Green gate before merge: `pytest` (backend SCM + regression), `npm run test`, `tsc --noEmit`,
   `npm run build` (prod build catches RSC/type errors), tooltip visual smoke.

## 3. Alembic dual-head fix (HARD BLOCKER)
- SCM chain `273→…→285` forked at `271`; main advanced `271→…→c1d2e3f4a5b6`. Merging = **two heads**.
- On deploy the new backend container's `start.sh` runs `alembic upgrade head` before gunicorn. Two
  heads → "Multiple head revisions" → container never healthy → **blue/green aborts** (old color
  keeps serving = safe, but the demo does not ship).
- **Fix:** after merging into main, `alembic merge -m "merge scm chain into main" c1d2e3f4a5b6
  285_market_signal_sources`, commit the merge revision, `alembic heads` must show **one** head.
- Forked SCM migrations are already idempotent (273 `IF NOT EXISTS`, 278 `_has_column`) → re-runnable.

## 4. Merge + deploy mechanism (blue/green, zero-downtime)
1. PR `feat/scm-reorder-copilot → main`, review, merge.
2. Add + commit the alembic merge revision (§3) → single head.
3. Push to main → CI `.github/workflows/deploy.yml`: build backend/frontend/mcp images,
   smoke-import (`app.main`, worker scheduler chain, mcp), `scp` deploy bundle to
   `/opt/sorento-crm2`, run `scripts/blue_green_deploy.sh`.
4. New color's backend `start.sh` auto-runs `alembic upgrade head` (273 - 285 + merge) before it
   reports healthy. Migration failure → unhealthy → deploy aborts, **old color unaffected**.
5. Traffic switches to the new color only after all three containers are healthy → zero downtime,
   built-in rollback.
- `module_guard_strict` defaults **false** in prod → SCM APIs reachable once permission-gated
  (no per-tenant enable needed). If strict is on later, enable `scm` in `tenant_modules`.
- Worker container `ENABLE_SCHEDULER=true` → the daily `scm_reorder_run` + `scm_analytics` crons
  activate (SCM-only, guarded). Configure the reorder-run time via its `scheduled_tasks` row.

## 5. Post-deploy LIVE seeding (must BUILD - the current seed is NOT live-safe)

**Problem:** `scripts/seed_scm_demo.py` **mutates real rows** (`products.cost_price`,
`customers.market_segment_code`, `market_segments.demand_nature`) and selects real SKUs; it is
hard-guarded to `localhost` only. It **cannot** run on prod. Deploy applies migrations only, never
this script. → Prod SCM tables are **empty** after deploy; prod has **no "Demo" suppliers**.

**Build a new additive-only seed** `scripts/seed_scm_live_demo.py`:
- **Isolation boundary:** one dedicated warehouse `warehouses.warehouse_code = 'SCM-DEMO-WH'`. All
  demo stock/consumption lives here → trivial, physical reversibility.
- **Net-new entities only, never mutate a real row.** Tag by stable prefix `SCM-DEMO-` on
  `product_code` / `customer_code` / `supplier_code` / `picking_number`, **plus**
  `source_system='scm_demo'` on `sales_orders`/`purchase_orders`/`scm.*` (real column) for a
  belt-and-braces filter.
- **Realistic supplier names (no "Demo"):** e.g. `Kilang Seramik Klang Sdn Bhd`,
  `Selangor Sanitaryware Trading`, `Foshan Ceramic Fixtures Co., Ltd` (CNY, exercises currency +
  long lead), `Johor Bathware Distributors Sdn Bhd`, `Guangzhou Sanitary Imports Ltd`,
  `Penang Tile & Fixtures Sdn Bhd`.
- **Scenarios (drive the engine off demo-only stock + demo-only DO history):**
 - **Buy (~6):** low `on_hand` in SCM-DEMO-WH + `product_suppliers.unit_cost` set + recent frequent
    DO history (orders/order_lines over last 60 - 90d) → `net ≤ ROP` → costed buy.
 - **Stockout + committed (~2):** `on_hand=0` + recent demand + open `sales_order` line → net
    negative → strongest buy.
 - **Overstock / hold (~3):** high `on_hand` + light recent demand → `days_of_cover > 120`.
 - **Dead / discontinue (~2):** `on_hand>0` + one DO line >180d ago, nothing since →
    `last_movement_days > 180`.
- **Mandatory post-seed:** run `analytics_service.run_analytics(db)` - without it `scm.demand_stat`
  is empty, `demand_rate=0`, and **no buys emit**. Then trigger a reorder run (Manual plan / API) to
  produce the recommendations the demo shows.
- **Promote rows:** the engine only ever emits `discontinue`/`hold` (never `promo`). To show
  Promote/actionable allocation, run `scripts/simulate_stock_allocation.py` against the produced run
  (flips a few hold rows → promote/discontinue). Demo-only, reversible (`--reset`).
- **Idempotent:** cleanup-then-insert keyed by the prefix/warehouse in FK-safe order
  (order_lines→orders, sales/purchase lines→headers, picking_lines→picking_headers, stock,
  product_suppliers, then products/customers/suppliers/warehouse, then `scm.* WHERE
  source_system='scm_demo'`). Safe to relax past the localhost guard **because it never touches real
  rows**; still gate behind an explicit env flag (e.g. `SCM_LIVE_DEMO_SEED=1`).
- **Run on prod:** ssh to server → exec the script inside the backend container against the prod DB,
  env-flag gated → run `run_analytics` → trigger reorder run → (optional) simulate allocation.
  Additive → safe; reversible via cleanup.

## 6. Verification + rollback
- **Existing modules smoke (regression):** open a delivery order + a PO (unchanged), hover a tooltip
  (renders correctly, §1c), confirm an existing user with no SCM role sees **no** Supply Chain nav +
  403 on `/api/v1/scm/*`.
- **SCM smoke:** demo account → reorder page opens to today's plan, **Buy + Stock allocation both
  populated**, assistant answers + sources render.
- **Rollback:** blue/green switch back to the old color. Migrations are additive → **no schema
  rollback needed** (new columns are harmless under reverted code). Demo data reversible via the
  seed's cleanup-by-prefix.

## 7. Open decisions
1. Confirm the realistic supplier name set (§5).
2. Demo run: let the cron auto-generate today's plan, or trigger manually right after seeding?
3. Build `seed_scm_live_demo.py` now (recommended, it's the long pole)?
4. Grant which existing role the SCM permissions for the demo account (or a dedicated demo role)?
