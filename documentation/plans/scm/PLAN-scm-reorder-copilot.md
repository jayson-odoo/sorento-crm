# PLAN — SCM Reorder Co-Pilot

**Slug:** `scm-reorder-copilot` · **Domain:** scm · **UAC:** `scm-reorder-copilot-acceptance-criteria.md`
**Classification:** MODULE (installable per tenant). **Split by uninstall lifecycle:** core business records (SO/PO/GR/product_suppliers ext) in **`public`**; reorder *brain* (policy/run/recommendation/override/classification/supplier_perf/budget/market) in a dedicated **`scm`** Postgres schema with **cross-schema FKs** into `public` core (Postgres-native; NOT the old no-FK isolation). Uninstall = drop `scm` schema, business records untouched. Views for source-decoupling.
**Status:** DRAFT (grilled, pre-code) — for day-2 internal team discussion; day-4 demo build.

> Fulfils the UAC above. Three-phase loop per feature slice (FE prototype → BE wiring + tests →
> review). Milestones M0–M5 are the 4-day demo; each is independently demoable.

## 0. Architecture guardrail (three-layer control)

| Layer | Does | Never does |
|---|---|---|
| **Quantitative core** (deterministic code, reads views + `reorder_policy`) | net position, forecast, SS, ROP, qty, ABC/XYZ, cash allocation, supplier scoring | call an LLM; hold business config in code |
| **Judgment layer** (UI + `recommendation_override`) | human accept/adjust/dismiss; override reason capture; apply suggested policy actions | silently discard/auto-apply an override |
| **Semantic layer (LLM)** | explanation prose; classify override reason→code; NL Q&A; market advisory prose | compute or alter any number |

The core↔semantic boundary is the thing most likely to rot. LLM receives computed numbers as input,
emits prose/labels as output. **No path from LLM output to a numeric field.** (UAC D15, AC-M5.3.)

## 1. Data model

### 1.1 Reuse / extend (existing, `public`)
- `products` (variant_of_id = colour-variant granularity; cost_price, currency, reorder_level/qty), `product_categories`, `stock` (per-warehouse on_hand/reserved/available/damaged), `stock_ledger`, `suppliers`, `warehouses`, `lookup_sets`/`lookup_options` (order_type + reason vocab), `scheduled_tasks` (snapshot + market research), `app_modules_catalog`/`tenant_modules` (module enablement), `ai_prompt_versions`/`ai_assistant_*` (LLM registry).
- **Extend `product_suppliers`**: `+ moq, order_multiple, unit_cost, currency, is_primary_supplier, lead_time_variability_days`.
- **Extend `suppliers`**: `+ current_performance_score` (denormalized, nullable).
- **GR reuse**: `picking_headers` where `picking_type='goods_received'`; add `picking_lines.po_line_id` (soft, nullable) + explicit `qty_accepted`/`qty_rejected`; header links PO via existing `source_entity_type='purchase_order'`/`source_entity_id`.

### 1.2 New tables — `source_system`/`source_ref` cols on all; schema split by uninstall lifecycle

**Core business records → `public`** (survive module uninstall; sit with existing procurement/order domain): `sales_order`, `sales_order_line`, `purchase_order`, `purchase_order_line`. (GR = existing `public.picking_headers`; `product_suppliers`/`suppliers` extensions stay `public`.)

**Module brain → `scm` schema** (die with the module; cross-schema FKs into `public` core): `demand_nature_map`, `reorder_policy`, `item_classification`, `supplier_scoring_policy`, `supplier_performance`, `purchasing_budget`, `reorder_run`, `reorder_recommendation`, `recommendation_override`, `override_reason`, `reason_action_map`, `market_research_topic`, `market_signal`.

Migration: `op.execute("CREATE SCHEMA IF NOT EXISTS scm")`; brain models pin `__table_args__={"schema":"scm"}`; FKs to `public.products`/`suppliers`/etc. are normal cross-schema FKs.

```
-- public (core records)
sales_order(id, so_number, customer_ref, order_date, order_type /*lookup*/, priority,
            status, source_system, source_ref)
sales_order_line(id, sales_order_id, product_id, warehouse_id,
                 qty_ordered, qty_delivered, priority /*inherit/override*/, line_status)

purchase_order(id, po_number, supplier_id, issue_date, expected_date, status,
               currency, source_system, source_ref)
purchase_order_line(id, purchase_order_id, product_id, warehouse_id,
                    qty_ordered, qty_received, unit_cost, currency, expected_date,
                    moq_snapshot, order_multiple_snapshot, line_status)

-- scm schema (module brain; cross-schema FKs into public)
demand_nature_map(id, order_type_option_id, demand_nature /*continuous|spike*/)  -- configurable

reorder_policy(id, scope_type /*sku|product_class|abc_xyz_cell|global*/, scope_ref,
               policy_type /*reorder_point|periodic_review|min_max*/,
               service_level, safety_stock_method /*statistical|fixed_days|manual*/,
               safety_days, review_period_days, forecast_window_days,
               baseline_source /*continuous_only|all*/, spike_handling /*committed_only|statistical|ignore*/,
               buy_scope /*network|warehouse*/, dead_stock_days,
               factor_toggles jsonb, factor_weights jsonb,
               min_override, max_override, is_active, priority)

item_classification(product_id, warehouse_id, abc_class, xyz_class,
                    annual_value, demand_cv, computed_at)

supplier_scoring_policy(id, delivery_weight, quality_weight, min_sample_size, is_active)
supplier_performance(id, supplier_id, product_id, period_start, period_end,
                     on_time_delivery_rate, avg_lead_time_days, lead_time_variance,
                     reject_rate, fill_rate, composite_score, sample_size, computed_at)

purchasing_budget(id, period_start, period_end, budget_amount, currency,
                  scope_type /*global|supplier|category*/, scope_ref, set_by, note)

reorder_run(id, created_by, created_at, status, warehouse_ids jsonb, buy_scope,
            budget_id, policy_snapshot_ref)
reorder_recommendation(id, run_id, product_id, warehouse_id, supplier_id,
                       net_position, reorder_point, forecast_daily_demand, days_of_cover,
                       recommended_qty, rounded_qty, unit_cost, cash_impact, currency,
                       urgency_score, priority_score, confidence_band, triggered_reason,
                       explanation /*LLM*/, market_advisory /*LLM*/, funding_status /*funded|deferred*/,
                       status /*proposed|accepted|adjusted|dismissed*/, created_at)
recommendation_override(id, recommendation_id, original_qty, override_qty,
                        reason_text, reason_code /*LLM-classified*/, reason_confidence,
                        suggested_action /*deterministic*/, action_applied bool,
                        overridden_by, overridden_at)   -- append-only, never mutates recommendation

override_reason(id, reason_code, label, is_active)     -- master vocabulary
reason_action_map(id, reason_code, suggested_action, target_policy_field, adjustment)  -- deterministic

market_research_topic(id, label, category_ref, currency, query_template, is_active)  -- configurable
market_signal(id, topic_id, category_ref, currency, value, trend, summary,
              source_url, captured_at)
```

### 1.3 Views (source-decoupling — engine reads these, AC-M0.3)
- `scm_consumption_v` — realized outflow per SKU/warehouse/day, channel-tagged (from DO/`stock_ledger`).
- `scm_committed_v` — open SO `Σ(qty_ordered−qty_delivered)` with priority + demand_nature.
- `scm_on_order_v` — open PO `Σ(qty_ordered−qty_received)`.
- `scm_net_position_v` — on_hand + on_order − committed per SKU/warehouse.
- `scm_receipt_lead_v` — per-line `gr.receipt_date − po.issue_date` + quality (accepted/rejected/discrepancy) driving supplier snapshots.

## 2. The engine (deterministic; UAC D10)

```
net_position   = on_hand + on_order − committed
avg_daily_demand = channel_adjusted_outflow(window) / window        # policy: baseline_source
projected_demand(h) = statistical_baseline(per baseline_source) + committed_SO(per spike_handling)
SS  = Z(service_level)·√(LT·σ_d² + d²·σ_LT²) | avg_daily_demand·safety_days | manual   # policy
ROP = avg_daily_demand · measured_lead_time + SS                    # measured overrides declared
trigger: net_position ≤ ROP | periodic review | net_position ≤ min  # policy_type
qty = order_up_to − net_position ; rounded = roundup(qty, order_multiple, floor=moq)
```
Supplier scoring: `composite = delivery_weight·on_time − quality_weight·reject_rate` (policy),
supplier×product, fallback supplier-level under `min_sample_size`. Feeds ROP (avg_lead_time), SS
(lead_time_variance), supplier pick (reject_rate/on_time).

Cash: if `Σ cash_impact > budget`, rank by `factor_weights`·(urgency/DoC, margin, ABC, SO priority,
committed) → fund down the list; unfunded = `funding_status='deferred'` with visible stockout risk.

Policy resolution: SKU → ABC/XYZ cell → product_class → global; most-specific active wins.

## 3. LLM usage (semantic only; UAC D13/D15)
- **Reason classifier** — new `ai_prompt` key; schema-forced output `{reason_code, confidence}` over the `override_reason` vocab; human-correctable. Generalized NLP, not keyword (memory `feedback_no_overfit_llm_nlp`).
- **Explanation** — prose from the recommendation's numbers; numbers passed as structured input, echoed unchanged (AC-M5.1 test).
- **Market advisory** — condenses latest `market_signal` rows to one sentence per recommendation.
- **NL Q&A** — answers over displayed numbers only.
- Reuse existing prompt registry (immutable versions + movable labels) + governance/trace infra.

## 4. Market research service (backend, no n8n; UAC D14)
- `MarketResearchService`: iterate active `market_research_topic` → **backend web search** → parse → write `market_signal`. **Dependency:** a backend web-search capability (Anthropic web-search tool or a search-API key) — provision + wrap; flag in PR.
- Trigger: `scheduled_task` (cadence) + manual "Run research" button. Advisory-only.
- Visualize `market_signal` in a dashboard panel (trend table).

## 5. Module registration
- `app_modules_catalog` entry `scm`; routes under `Depends(require_module_enabled_with_api_key("scm"))`; ship **dormant** (disabled for existing tenant) → zero UX change (AC-M0.1). Sidebar entry gated by module + permission.

## 6. Frontend (in-platform; hooks→service→api-client)
- **Dashboard** (`/scm`): net-position DataGrid (filters: warehouse/class/colour/supplier/ABC-XYZ), roll-ups (cash in stock, dead-stock trapped cash, below-ROP, stockout, incoming-PO timeline), market-signal panel.
- **Reorder run**: create run (SearchableMultiSelect warehouses, buy_scope, budget) → recommendation view: qty, cash impact, DoC, confidence, LLM explanation, market advisory, **Accept / Adjust / Dismiss**; Adjust → override capture (reason text → LLM code → suggested action → Apply).
- **Config**: `reorder_policy` CRUD (modal), `order_type→demand_nature` map, `supplier_scoring_policy`, `purchasing_budget`, `market_research_topic`.
- Conventions: `SearchableSelect`, `extractApiError`, `buildDataGridParams`, fixed table layout, **no UUIDs in UI**, `AlertDialog` confirm on every destructive/detach action, mobile-scrollable modals.

## 6a. Per-milestone plans (each grilled 1-by-1 before code)

This file is the **umbrella**. Each milestone gets its own grilled UAC + PLAN in `documentation/plans/scm/`, refined one at a time:

| M | Milestone plan | UAC | Status |
|---|---|---|---|
| M0 | `PLAN-scm-m0-foundation.md` | `scm-m0-foundation-acceptance-criteria.md` | **grilled ✓ (ready)** |
| M1 | `PLAN-scm-m1-net-position.md` | `scm-m1-net-position-acceptance-criteria.md` | **grilled ✓ (ready)** |
| M2 | `PLAN-scm-m2-demand-classification-supplier-perf.md` | `scm-m2-demand-classification-supplier-perf-acceptance-criteria.md` | **grilled ✓ (ready)** |
| M3 | `PLAN-scm-m3-reorder-engine.md` | `scm-m3-reorder-engine-acceptance-criteria.md` | **grilled ✓ (ready)** |
| M4 | `PLAN-scm-m4-cash-copilot.md` | `scm-m4-cash-copilot-acceptance-criteria.md` | **grilled ✓ (ready)** |
| M5 | `PLAN-scm-m5-semantic-market.md` | `scm-m5-semantic-market-acceptance-criteria.md` | **grilled ✓ (ready)** |

Umbrella locks cross-cutting decisions (schema split, LLM boundary, factor model); per-milestone
plans lock the mechanics (migrations, views, endpoints, seed data, RBAC, tests).

## 6b. No-orphan-tables contract (every entity gets a frontend)

Every new table ships a frontend (CRUD list or read-only grid, per the CRUD UX standard — DataGrid +
bulk-action + modal-CRUD, reused, no one-offs). Each list is built in the milestone that owns its
lifecycle:

| Entity | UI | Milestone |
|---|---|---|
| net-position / warehouse health | dashboard perspectives | M1 |
| `sales_order` + lines | CRUD list + create-DO-from-SO | M1 |
| `product_suppliers` (extended) | CRUD list | M2 |
| `market_segments` (+demand_nature), `abc_xyz_policy`, `supplier_scoring_policy` | config CRUD | M2 |
| `demand_stat`, `item_classification`, `supplier_performance` | read-only grids / scorecard | M2 |
| `scm_analytics_run` | read-only run history | M2 |
| `reorder_policy` | config CRUD | M3 |
| `reorder_run` + `reorder_recommendation` | run + results | M3 read-only → M4 interactive |
| `purchase_order` + lines | list + bulk Confirm (draft→active) + create-GR-from-PO | M4 |
| `cash_ranking_policy`, `purchasing_budget` | config CRUD | M4 |
| `override_reason`, `reason_action_map` | config CRUD | M4 |
| `recommendation_override` | read-only history + Policy-suggestions panel | M4 |
| `market_research_topic` | config CRUD | M5 |
| `market_signal` | read-only viz | M5 |

## 7. Build sequence (three-phase per milestone)

Each milestone: **Phase 1** FE prototype on mock fixtures (states: loading/empty/error/partial) →
**Phase 2** BE models+migrations+services+routes to the documented contract, FE off mocks, **tests
land here** (pytest endpoints happy/auth/validation + service maths; vitest components/hooks;
playwright FE→BE→DB) → **Phase 3** `/code-review` then PR.

- **M0** schema + views + module reg + golden-set fixtures skeleton.
- **M1** net-position views + dashboard (real data).
- **M2** demand model + ABC/XYZ + supplier snapshot (scheduler + on-GR hook).
- **M3** engine + `reorder_policy` resolution + `reorder_run` + **golden-set CI** (AC-M3.1).
- **M4** cash ranking + recommendation view + override + reason-classify + suggested-action.
- **M5** LLM explanation + market research (web-search dependency) + advisory panel.

## 8. Risks / open provisioning
- **Backend web-search capability** (M5) — newest infra; provision early or M5 slips to fast-follow.
- **Stock-ledger depth** — caps forecast history; MA on available window is acceptable; reconstruction deferred.
- **`stock.quantity_reserved`** may already encode a committed signal — reconcile vs SO-committed during M1 (avoid double subtraction).
- **4-day scope** — M0–M4 is the deterministic deal-closer; M5 (LLM + market) is the "wow" but the riskiest. If web-search provisioning stalls, demo M0–M4 + stub M5 explanation, market research fast-follow.
- **Doc debt** — update `PRINCIPLES.md` + `CLAUDE.md` core/module doctrine to the corrected definition (memory `project_core_vs_module_schema`).
