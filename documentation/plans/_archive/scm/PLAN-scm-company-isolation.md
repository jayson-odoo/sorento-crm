# PLAN - SCM company isolation

**Status:** C0-C4b DONE (4 Aug 2026), C5 remaining. Migration 332, 12 tests.

> Planning in Sorento must be based on Sorento's warehouses, products and orders. Mocha may
> own warehouses too.

## Why this is not already true

The multi-company isolation filter runs on **ORM execution only** (`app.services.company_scope`
`do_orm_execute`). The SCM planning path is raw SQL over views, and no `scm.*` table carries a
`company_id` at all - 0 of 20 base tables, 0 of 5 views. So today:

- `_planning_rows` selects from `scm.net_position_v` joined to `products` and `warehouses` with
  no company predicate. An unscoped daily run enumerates **every** company's positions.
- `_resolve_warehouse_ids(None)` lists every active warehouse in the database.
- Product-code resolution finds every company's copy: 11,390 codes exist twice.

It is inert **only** because Mocha owns 0 warehouses, so `net_position_v` yields Sorento rows
alone. The day Mocha gets a warehouse, a Sorento plan silently includes Mocha's stock, and the
buy quantities are wrong in the direction that suppresses purchases (more apparent cover than
exists).

Two of these were already fixed at the resolver level (commit `8b7634fda`, ORM lookups). This
plan closes the rest.

## The rule

**Company is a property of the LOCATION, and every SCM fact hangs off a location.** Stock is at
a warehouse; a sales-order line is delivered from one; a PO line arrives at one; an allocation
names one. So the scope is applied **once**, at the warehouse set, and everything downstream
inherits it.

That gives three classes of table, and the class decides the mechanism:

| class | tables | mechanism |
| ----- | ------ | --------- |
| **A. Positions and facts** keyed by warehouse (and/or product) | the 5 views, `demand_stat`, `item_classification` | **Derived.** Filter by joining `warehouses` / `products`. No new column: a denormalised `company_id` on a row that already names its warehouse would only be a second copy of the same fact, free to disagree with it. |
| **B. Planning artefacts** | `reorder_run`, `reorder_recommendation`, `order_summary_row`, `recommendation_override`, `purchasing_budget`, `scm_analytics_run`, `market_research_run` | **Stamped `company_id`**, `CompanyScopedMixin`. A run is a company's plan, not a fact about a location. `reorder_recommendation.warehouse_id` is NULL on a network run, so it cannot be derived at all. |
| **C. Policy and reference** | `reorder_policy`, `abc_xyz_policy`, `cash_ranking_policy`, `supplier_scoring_policy`, `priority_policy`, `demand_nature_map`, `override_reason`, `reason_action_map` | **Shared with override**: nullable `company_id`, NULL meaning "the default for every company", a company row winning where present. Mirrors `__company_shared__` (attachments). |
| **D. Market intelligence** | `market_research_topic`, `market_signal` | **Global.** A tile price trend in Guangdong is a fact about the world, not about a company. No column. |
| **E. Supplier behaviour** | `supplier_performance` | **Derived** from `suppliers.company_id`, which already exists. |

### Why C is shared-with-override rather than strictly per-company

Strictly per-company means Mocha's first plan finds no reorder policy and fails closed, and the
migration has to invent a Mocha copy of five policy tables before anything works. Shared-with-
override means today's single set becomes the default the day Mocha is switched on, and Mocha
overrides only what it actually wants to differ on. It is also the more reversible direction:
tightening later is a migration, loosening after a fail-closed launch is an incident.

## The worker problem, which is the reason a run stamps its company

`run_reorder` executes in an RQ work-horse that receives **only a run id**. There is no request,
no bearer token, and therefore no company scope: `get_company_scope(db)` returns UNSET, and
UNSET **fails closed** - every ORM read returns nothing. So a naive "just rely on the isolation
filter" would leave the daily plan silently producing zero recommendations.

The run therefore carries `company_id`, and `run_reorder` re-establishes the scope from the row
before it reads anything. That makes the scope an explicit, auditable property of the run rather
than an ambient one, which is also what makes a past run reproducible under the right company.

## Slices

- **C0. `stock` IS already company-scoped** - the table is `stock`, singular, and it carries
  `company_id` with `CompanyScopedMixin`. An earlier reading of this plan said otherwise from a
  lookup against the non-existent table name `stocks`. That matters in the good direction: the
  opening balance of every timeline is read through the ORM and is therefore already scoped, so
  the position path is protected once the warehouse set is. Recorded because the wrong name is
  an easy check to repeat.
- **C1. Scope the warehouse set.** `_resolve_warehouse_ids` (already ORM, so already scoped) plus
  `CoverageService.availability_warehouse_ids` and `pool_members`, which are ORM and therefore
  scoped once a scope exists - the gap is the raw-SQL readers below.
- **C2. Scope the raw-SQL planning readers.** `_planning_rows`, `_last_movement_map`, and every
  raw reader in `dashboard_service` / `analytics_service`, via
  `company_sql_predicate(db, "w.company_id")` on the joined `warehouses` (and `p.company_id` for
  the product side). The helper already exists and reproduces the four-state predicate.
- **C3. Stamp the class-B tables** (migration + `CompanyScopedMixin`), backfilling every existing
  row to Sorento, which is correct because every existing row is Sorento's.
- **C4. Persist the run's company and re-apply it in the worker.**
- **C5. Nullable `company_id` on the class-C policy tables**, with resolution "company row else
  the NULL row". `uq_scm_priority_policy_one_active` becomes per-company - and it must be written
  as `(coalesce(company_id, <nil-uuid>), is_active) WHERE is_active`, because Postgres treats
  NULLs as distinct in a unique index and two global rows would otherwise both be allowed.
- **C6. Tests.** Two companies, each with a warehouse, the same product code in both, and stock
  in both. The property under test is that a plan scoped to A never names B's warehouse, B's
  product, or B's stock - asserted on the recommendations a run actually produces, not on the
  source text.

## What "done" looks like

A run under company A, with company B holding a warehouse, stock, open orders and its own copy
of every product code, produces recommendations that reference A's warehouses only, whose
quantities are unchanged from what A would have got if B did not exist. That last clause is the
one that matters: a leak that adds rows is visible, and a leak that adds cover is not.


### What C1-C4 actually changed (done)

Beyond the plan, two more raw-SQL run pickers turned up, and both decide **which plan a screen
opens on**:

- `today_or_latest_run` - the reorder page's own "today's plan". Unscoped, it opens on whichever
  company ran most recently: another company's plan wearing this company's chrome, with every
  figure on it about stock this company does not hold.
- `ScmDashboardService._latest_completed_run_id` - the source of the dashboard's low-stock
  signal. Unscoped, it warns about stock this company does not hold.

Both now carry `company_sql_predicate`. Same class of defect as `_planning_rows`, invisible for
the same reason: raw SQL is not reached by the ORM filter, and while one company owns every
warehouse the wrong answer and the right answer are the same row.

### C4b. Stamping the column is only half of it - the read gate (done)

Stamping `company_id` on a run makes the run's OWNER knowable. It does not stop another
company reading it, because ~30 raw-SQL reads of a run's children are keyed by `run_id`
alone: recommendations, decisions, the explainer's aggregates, the frozen order-summary
rows. A caller holding a run id could read all of them. `GET /scm/reorder-runs` listed
every company's runs outright.

Fixed at the gate rather than at each read: `reorder_run_service.assert_run_visible(db,
run_id)` resolves the id under the company predicate and raises **404** (not 403 - another
company's run must not be distinguishable from one that never existed), and every route
that accepts a caller-supplied run id calls it first: run detail, recommendations, budget,
overview, chat, past-plans, decisions, reset-decisions, market-proposal. Nine call sites,
one rule. The list endpoint carries the predicate directly.

Three reads are NOT covered by that gate and carry their own predicate, each for a reason:

- `explain_recommendation_net` is keyed by a RECOMMENDATION id, not a run id.
- `query_past_plans` and the previous-plan lookup in the run comparison are cross-run **by
  design** - they deliberately reach past the gated run into every completed run, so the
  gate says nothing about what they may read.

`scm_analytics_run` was the one owned table still written by raw SQL, which left
`company_id` NULL on every analytics run and hid it from the scoped read of the same table.
The write now stamps it and the run-log list filters on it. The resolution rule is shared
with the ORM auto-stamp (`company_scope.resolve_write_company_id`) rather than copied, so
the two cannot drift.

### C5, still open

Per-company policy (`reorder_policy`, `abc_xyz_policy`, `cash_ranking_policy`,
`supplier_scoring_policy`, `priority_policy`, `demand_nature_map`, `override_reason`,
`reason_action_map`) is deliberately NOT built yet. There is exactly one set of policy rows today
and every company reads it, which IS the shared case of shared-with-override - so nothing is
wrong until somebody wants Mocha to differ. Building the column now would add a migration, a
resolution rule and a partial-index rewrite for a capability nobody has asked for. The
`uq_scm_priority_policy_one_active` note above is the trap to remember when it is built.
