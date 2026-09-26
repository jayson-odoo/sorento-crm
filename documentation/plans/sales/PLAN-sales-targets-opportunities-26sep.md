# PLAN: sales targets, opportunities and the WhatsApp achievement broadcast (#1170)

Status: grilled (round 1 answered by the owner 26 Sep 2026, PR #1260 comment 05:25Z; round 2
questions posted on the PR). Track: full track for every build lane (new tables, migrations, new
permissions, a new module key, a new portal surface). Nothing built beyond slice 1 of the issue
(PR #1177, a sales agent on a customer).
Domain: sales. Classification: **MODULE** `sales` (installable; another tenant with a sales team
would turn it on), tables in `public` with normal FKs (targets and opportunities are durable
business records, so by the uninstall test they stay in `public`).
UAC: `sales-targets-opportunities-26sep-acceptance-criteria.md` alongside (the contract; the
journey J1 to J12 lives there and is not repeated here).
Mockup: `mockups/sales-targets.html` (Targets screen at 1280 and 375, the Set target modal with
scope, validity and commission tiers, the portal opportunity form at 375, the Recipients tab, and
the WhatsApp message two recipients receive).
Grill: section 8 of this file. Each of G1 to G10 now carries a dated **Owner ruling 26 Sep** line
that replaces round 1's recommendation; the question and its options are kept. Round 2 questions
(at most five, each with a recommendation) are in section 9 and on the PR.

## 1. In plain words (for the owner)

Three ideas, and how they fit together.

- **A target** is the number a person is expected to reach, for example "Ali: RM 120,000 of
  sales a month, October to March, counting basins and taps only". Odoo's sales target (its
  Commissions app) is a **plan** with a start and end date and a periodicity (monthly, quarterly
  or yearly); inside that window it holds one target figure per period, and each plan says what it
  measures (amount or quantity, sold or invoiced) and on which products or product categories
  ([Odoo 18 Commissions][odoo-comm]). This plan follows that shape (rulings G3 and G4): every
  target sets its own metric, basis, product scope, start month and number of months.
- **Achievement** is what actually happened, counted from real documents. Odoo lets each plan
  choose which document counts (orders or invoices), and its different screens do not agree
  (the team target counts paid invoices, the gamification "Total Invoiced" goal counts every
  non-cancelled invoice, draft included) ([gamification data][odoo-gami]). Sorento has no customer
  invoice table in the CRM, so a target counts **sales orders**, either as ordered or as delivered,
  chosen per target (ruling G1).
- **An opportunity** is a possible sale being worked on: "Dealer X may order 200 basins for a new
  showroom, about RM 40,000, likely in November". It moves through **stages** as it firms up.
  Odoo's defaults are New, Qualified, Proposition, Won ([crm_stage_data.xml][odoo-stages]); Lost is
  not a stage in Odoo but an archived state with a lost reason ([Odoo lost opportunities][odoo-lost]).
  The common industry shape (Salesforce) is Prospecting, Qualification, ..., Proposal/Price Quote,
  Negotiation/Review, Closed Won, Closed Lost ([Salesforce stages guide][sf-stages]). A **lead**
  in Odoo is an unchecked enquiry that is converted into an opportunity once qualified
  ([Odoo convert leads][odoo-convert]); here New plays that role, so there is no separate lead
  object. Stages are configurable, on the same stage table the Project Sales lead funnel already
  uses (ruling G5).
- **Pipeline vs achievement.** Each stage carries a probability (the chance it closes). Odoo
  multiplies expected revenue by probability to get **prorated (weighted) revenue**
  ([crm_lead.py][odoo-lead]) and groups it by expected closing month in its Forecast view
  ([crm_lead_views.xml][odoo-leadviews], [expected revenue report][odoo-exprev]). That weighted
  figure is the **pipeline**: what is likely to come. It is shown **next to** the target and never
  added into achievement, or a sale would be counted twice (once as a won opportunity, once as
  the order). A common rule of thumb is to hold about 3x the remaining target in pipeline; the
  sharper version is 1 / win rate ([Clari][clari]).
- **Commission and incentive.** The simplest commission is a flat percentage of what was achieved
  (Odoo's "achievement based" plan). Odoo's "target based" plan pays an "On Target Commission" at
  100% and adds levels above and below it ([Odoo 18 Commissions][odoo-comm]); accelerators (a
  higher rate above target) are common in industry ([QuotaPath][quotapath]). Ruling G6 asks for
  the full set: tiers, a higher rate above target, commission on quantity targets, and one-off
  bonuses, all set per target.

Research note: odoo.com and Salesforce help pages were blocked by the network proxy during
research; the Odoo facts above were read from the official Odoo 18.0 documentation source and the
Odoo 18.0 code on GitHub instead (links point at those). The Salesforce, pipeline coverage and
accelerator points come from secondary sources as linked.

[odoo-comm]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/sales/commissions.rst
[odoo-gami]: https://raw.githubusercontent.com/odoo/odoo/18.0/addons/gamification_sale_crm/data/gamification_sale_crm_data.xml
[odoo-stages]: https://raw.githubusercontent.com/odoo/odoo/18.0/addons/crm/data/crm_stage_data.xml
[odoo-lost]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/crm/pipeline/lost_opportunities.rst
[odoo-convert]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/crm/acquire_leads/convert.rst
[odoo-lead]: https://raw.githubusercontent.com/odoo/odoo/18.0/addons/crm/models/crm_lead.py
[odoo-leadviews]: https://raw.githubusercontent.com/odoo/odoo/18.0/addons/crm/views/crm_lead_views.xml
[odoo-exprev]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/crm/performance/expected_revenue_report.rst
[sf-stages]: https://www.salesforceben.com/complete-guide-tutorial-to-salesforce-opportunity-stages/
[clari]: https://www.clari.com/blog/pipeline-coverage-best-practices/
[quotapath]: https://www.quotapath.com/blog/motivational-accelerator-plans/

## 2. Measured facts (read-only, origin/main 46711c61, re-checked 26 Sep round 2)

Backend paths are under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`.

**Sales agents.** `sales_agents` (`app/models/sales_agent.py:43`): code `sales_agent` (:50),
`person_label` (:60, "the captain's 38 codes decompose to 16 people", :56-59), `demand_class`
(:65, NULL until the captain classifies), `is_active` (:52), `company_id` nullable, NULL = shared
row (:73, not `CompanyScopedMixin`), `contact_id` Text FK `respond_contacts.id` ON DELETE SET NULL
(:89-93), documented as the agent's **portal** contact ("allows the portal to scope the debtor
dropdown", :86-88). Agents are not users and not a role (docstring :1-17, ruling 14 Aug 2026). API
`app/api/v1/master_data/sales_agents.py` (list :40, detail :94, annotate :109). Slug
`master_data.sales_agents.*` (`app/rbac/permission_registry.py:219`).

**Contact to agent, already solved once.** `price_tag_request_service.py:2380-2404` resolves a
portal contact to its sales agent (`SalesAgent.contact_id == contact_id`, ordered by code then id,
logs a second link rather than guessing). The portal opportunity form reuses this resolver; it is
lifted into `app/services/sales/portal_agent.py` so both callers share one copy.

**Customers.** `customers` is company scoped (`app/models/order.py:49`), `sales_agent_id` FK ON
DELETE SET NULL (:142-146). Slice 1 exposed it (PR #1177): `app/schemas/order.py:47,57,76-78`,
`_resolve_sales_agent` (`app/services/order_service.py:3446`). There is **no dealer flag** on
`customers`: "dealer" exists only as the sales report's channel, `demand_class == "retail"`
(`app/services/sales_report_service.py:264-265`).

**Sales orders, the achievement source.** `sales_orders` (`app/models/order.py:413`):
`customer_id` (:422), `sales_agent_id` (:433, indexed :490, set from AutoCount's agent code on
ingest, `app/services/document_ingest_service.py:219`), `order_date` Date (:434, **not indexed**),
`demand_class` (:443, retail or project), `status` (:451; open / fulfilled / closed / cancelled,
`document_ingest_service.py:131-154`). `sales_order_lines` (:505): `product_id` (:509),
`qty_ordered` (:511), `qty_delivered` (:512), `line_total` "Total (Inc)" (:526), `line_status`
(:551). **No delivery date exists on a line or anywhere linked to it**: `qty_delivered` is a
running figure AutoCount overwrites on each upload (`document_ingest_service.py:243`). Project
sales orders reach the same table: the project module links its own lines to
`public.sales_order_lines` through `core_sales_order_line_id` (`app/models/project_so.py:542`).
Products carry `category_id` FK `product_categories` (`app/models/product.py:202`); categories
nest through `parent_category_id` (`app/models/product.py:43`).

**The sales report predicate** (`app/services/sales_report_service.py`): `SalesOrder.status !=
"cancelled"`, `SalesOrderLine.line_status != "cancelled"` (:240-247); `confirmed_value` =
`line_total x least(qty_delivered, qty_ordered) / qty_ordered` rounded per line (:202-215). The
target's two bases reuse exactly these two figures (ordered = `line_total`, delivered =
`confirmed_value`), bucketed by `order_date`.

**The configurable stage table (G5).** The status engine: `statuses`
(`app/models/status.py:72`) with `key`, `label`, `sort_order`, `is_initial`, `is_terminal` (:94),
`is_active` (:97, "hidden from pickers, existing records keep them"), `win_probability` (:110,
"on the STATUS so management tunes the forecast with no deploy"), `stale_after_days` (:113), and
`status_transitions` (:160). Entities join by registering a `StatusEntity`
(`app/status_engine/registry.py:85`) from `app/modules/<key>/status_entities.py`, discovered by
`app/status_engine/discovery.py:48`. The **Project Sales lead funnel** is exactly this:
`leads.status_id` (`app/models/projects.py:715`), registered at
`app/modules/projects/status_entities.py:155-177` with no scope resolver ("one lead funnel per
install"), seeded by `seed_default_lead_graph` (`app/services/project_seed_service.py:673`) from
`DEFAULT_LEAD_STATUSES` (:154) and `DEFAULT_LEAD_EDGES` (:164), run at startup
(`app/main.py:475-480`). Admins already edit graphs in System > Status Graphs
(`config/menu.config.tsx:924`, page `app/(protected)/system-management/status-graphs/`, route
`app/api/v1/system/statuses.py`). Transition checks: `initial_status` / `assert_transition_allowed`
(`app/services/status_service.py:115,169`). Lost reasons: the lead disqualify reasons are a
`lookup_sets` row (`app/models/lookup.py:12`, options :33) seeded by
`seed_lead_disqualify_reasons` (`project_seed_service.py:783`), edited on the existing lookup
screen.

**Portal auth (G9).** Contact-token portal, no CRM login: `portal_tokens`
(`app/models/portal.py:27`, `contact_id` :31, OTP-verified `verified_at`), `get_portal_token`
(`app/api/v1/public/portal.py:89`, header `X-Portal-Token`, stamps the acting contact for audit).
Per-contact visibility of a portal kind: `resolve_visible_form_types`
(`app/services/portal_form_visibility_service.py:71`) = the base kinds, plus
`market_segments.portal_form_types` (`app/models/access.py:150`) of the contact's active segments,
plus or minus `contact_portal_form_overrides` (`app/models/price_tag.py:45`, `form_type`,
`is_enabled`). Opt-in kinds are listed in `GRANTABLE_PORTAL_FORM_TYPES`
(`app/services/portal_service.py:83`). Precedent for a dedicated portal kind with its own router:
`price_tag_request`, `app/api/v1/public/portal_price_tag.py` (visibility gate :65), mounted before
the generic portal router (`app/api/v1/public/__init__.py:32-35`); FE pages under
`app/(auth)/portal/price_tag_request/`.

**Respond.io send path (G7, G8).** `respond_contacts` (`app/models/access.py:231`),
`outbound_enabled` kill switch (:258) enforced by `assert_outbound_enabled`
(`app/services/respond_outbound_service.py:34`). Dealer contact link `respond_contact_customers`
(`app/models/access.py:32`, `is_primary` :40). `send_text_or_template(db, *, identifier, text,
use_case, context_vars=None, respond_contact_id=None)` (`app/services/respond_messaging_service.py:545`):
text inside the 24h window, else the template mapped in `respond_template_defaults`
(`app/models/respond_template.py:225`); a new use case joins `TEMPLATE_DEFAULT_USE_CASES` (:37).
Callers write their own `integration_log` row (`app/models/integration.py:114`).

**Per-row schedules on one heartbeat (G7).** `scheduled_tasks` (`app/models/scheduled_task.py:12`)
run by the 10 s heartbeat (`app/scheduler/task_scheduler.py:598-614`) against handlers in
`register_task_handlers` (:566-595); worker only (`ENABLE_SCHEDULER`, `worker.py:74-80`). The
**Automations** feature already runs many independently scheduled rows off one task:
`automations.schedule_type` / `run_time` / `timezone` / `next_run_at`
(`app/models/automation.py:53-60`), the `automation_runner` handler
(`task_scheduler.py:335-337`) dispatching every row whose `next_run_at` is due, and
`_next_run_for_daily` (`app/services/automation_service.py:50`) computing the next local run.
The per-contact broadcast copies this shape.

**Nothing to collide with.** No table named target, quota, commission, incentive, opportunity or
broadcast exists. `projects.leads` is the project (tender) pipeline owned by users (section 5).

**Plumbing.** `_crud` (`app/rbac/permission_registry.py:11-18`); slug prefix to module key map
(`app/modules/runtime/permission_module_map.py:17-35`, no `sales` entry); no `sales` module
today; routers mounted with the guard in `app/api/v1/__init__.py`. List-query adapters:
`app/services/list_query_registry.py:93-175`. Alembic single head: `oisl_0001_suggested_links`.

## 3. Design

### 3.1 Targets: header, periods, product scope (ruling G1, G2, G3, G4)

A target is Odoo-shaped: one header saying **who, what, how counted, on which products, from when
and for how long**, and one row per period holding the number to hit. Four tables, all
`CompanyScopedMixin`, all created in the S1 migration except the tiers (S4).

`sales_targets` (header), `__audit_track__ = True` (a changed target changes a commission, so
edits are exactly what people dispute):

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `target_no` | varchar(20), unique per company | `TGT-000123`, the human id (no UUID in the UI); numbering rule seeded like `seed_lead_numbering_rule` (`project_seed_service.py:644`) |
| `name` | varchar(120) not null | "Ali FY26 H2 basins" |
| `subject_kind` | varchar(16) not null | check `agent` or `dealer` |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE CASCADE, null | required when `agent` (check) |
| `customer_id` | uuid FK `customers` ON DELETE CASCADE, null | required when `dealer` (check) |
| `metric` | varchar(16) not null | check `amount` or `quantity` (G4) |
| `basis` | varchar(16) not null default `ordered` | check `ordered` or `delivered` (G1) |
| `product_scope` | varchar(16) not null default `all` | check `all`, `categories`, `products` (G4) |
| `start_month` | date not null | check day 1 (G3) |
| `months` | smallint not null | check 1 to 36 (G3, "valid for how many months") |
| `periodicity` | varchar(16) not null default `month` | check `month`, `quarter`, `whole`; `quarter` needs `months % 3 = 0` (check) |
| `commission_method` | varchar(16) not null default `none` | check `none`, `marginal`, `retroactive` (G6, S4) |
| `created_by_user_id`, `created_at`, `updated_at` | | |

Derived, never stored: `end_month_exclusive = start_month + months`.

`sales_target_periods` (the Odoo target lines), cascade from the header:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id`, `target_id` | | FK ON DELETE CASCADE |
| `period_start` | date not null | day 1 |
| `period_end` | date not null | exclusive; `period_start < period_end` (check) |
| `target_value` | numeric(15,2) not null | RM or units, per the header's metric |

Unique `(target_id, period_start)`. The service generates the rows from the header on create
(one per month, per quarter, or one for the whole window) with the single value typed in the
modal; each row is editable afterwards (seasonality: a lower December). Changing `start_month`,
`months` or `periodicity` regenerates the rows and keeps the value of any period whose start is
unchanged.

`sales_target_scope` (which products count), cascade from the header:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id`, `target_id` | | FK ON DELETE CASCADE |
| `product_category_id` | uuid FK `product_categories` ON DELETE CASCADE, null | exactly one of category / product (check) |
| `product_id` | uuid FK `products` ON DELETE CASCADE, null | |

Service rules: `product_scope = all` has no scope rows; `categories` needs at least one category
row and no product rows; `products` needs at least one product row and no category rows. A
category counts its sub-categories (a recursive CTE over `parent_category_id`), because a "Basins"
target that silently misses "Basins > Countertop" would read as under-achievement. A quantity
target with `product_scope = all` is allowed (the owner asked for "all" on either metric); the
modal shows a one-line hint that it adds every unit together.

**Overlapping targets are allowed.** An agent may hold an amount target on all products and a
quantity target on basins over the same months, as Odoo lets one person sit in several plans.
Each target is measured and paid independently. The only uniqueness rule is on
`target_no`; a duplicate header is a human choice, not a constraint violation.

**Why these tables and not fewer.** Periods are rows because the owner asked for Odoo style
validity and Odoo keeps one editable figure per period; one `target_value` column on the header
cannot say "RM 80k in December, RM 120k otherwise". Scope is rows because one target can name
several categories or several products (G4 "by product or category"). No generic dimension
table: product scope is the only dimension with a present need. **Trigger for a dimension
engine:** a request to target by a second axis (brand, region, channel) on the same target.

**No stored achievement.** Achievement is computed at read time; sales orders keep arriving and
changing from AutoCount, so a stored figure would go stale. **Trigger for a snapshot:** the
targets screen p95 exceeds 1 s on prod data, or the owner wants a closed period frozen against
later AutoCount edits (then snapshot at period close only). S1 adds `ix_sales_orders_order_date`.

### 3.2 Achievement and roll-up (one service)

`app/services/sales/achievement_service.py`, one query for a whole screen:

- Input: the period rows to show (every period that contains the chosen month). A CTE lists
  `(period_id, target_id, period_start, period_end, subject_kind, sales_agent_id, customer_id,
  metric, basis, product_scope)`; a second CTE expands category scope rows to their descendant
  category ids.
- Join `sales_order_lines` to `sales_orders` on the sales report predicate (`status !=
  cancelled`, `line_status != cancelled`) and `order_date >= period_start and order_date <
  period_end` (null `order_date` never counts).
- Attribution (G2): `agent` matches `sales_orders.sales_agent_id` against the target's agent (see
  round 2 R2 on whether a person's other agent codes also count); `dealer` matches
  `sales_orders.customer_id`, whoever the agent. `demand_class` is never filtered, so an agent's
  project orders count (G10).
- Scope: `all` passes; `categories` requires the product's category in the expanded set;
  `products` requires the product in the scope rows.
- Value by metric and basis:

  | | ordered | delivered |
  | --- | --- | --- |
  | amount | `coalesce(line_total, 0)` | `round(line_total x least(qty_delivered, qty_ordered) / qty_ordered, 2)`, 0 when `qty_ordered = 0` |
  | quantity | `qty_ordered` | `least(qty_delivered, qty_ordered)` |

  Delivered is bucketed by `order_date` too, because no delivery date exists (section 2); it
  reads "of what was ordered in this period, how much has gone out so far". Round 2 R3 asks the
  owner to confirm.
- Output: `{period_id: achieved_value}` plus `unassigned_amount` for the chosen month (orders with
  a null agent, so they are visible, not dropped).
- `pipeline_by_agent(db, *, month)` (S3) returns `{agent_id: (weighted_value, count)}`.

The ordered and delivered expressions are written once as `achievement_value_expr(metric,
basis)`; a test pins them against `sales_report_service`'s own `confirmed_value` and cancelled
rules so the two cannot drift silently.

### 3.3 Commission (ruling G6, slice S4)

`sales_target_commission_tiers`, cascade from the header:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id`, `target_id` | | FK ON DELETE CASCADE |
| `from_pct` | numeric(7,2) not null | achievement % at which the tier starts; 0 is "from the first ringgit" |
| `rate` | numeric(9,4) not null default 0 | amount target: % of achieved amount; quantity target: RM per unit |
| `bonus_amount` | numeric(15,2) null | one-off RM paid once when `from_pct` is reached in the period |

Unique `(target_id, from_pct)`. Computed per period, never stored, in
`app/services/sales/commission_service.py`:

- `marginal` (the accelerator): each tier's rate applies only to the slice of achievement between
  its threshold and the next tier's threshold. "2% up to 100%, 4% above" pays 4% only on the
  part over target.
- `retroactive`: the highest tier reached sets the rate for the whole achievement ("reach 110%
  and everything earns 4%").
- Bonuses: every tier whose `from_pct` is reached pays its `bonus_amount` once per period. The
  round 1 "incentive at 100%" is the tier `from_pct = 100, rate = <same as below>, bonus = 500`.
- Money is rounded half up to 2 dp once per period, after summing tiers.
- `none` returns null commission (a target with no tiers).

The tiers table is justified by the ruling itself (tiers, higher rate above target, quantity
commission, all configurable). No shared "commission plan" reused across targets: each target
holds its own tiers, and **Duplicate target** copies them. **Trigger for a shared plan table:**
the owner edits the same tier set on more than ten targets at once.

### 3.4 Opportunities on the existing stage table (ruling G5, G9)

`sales_opportunities` (S2), `CompanyScopedMixin`, `__audit_track__ = True` (stage history for free
through the existing audit timeline):

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `opportunity_no` | varchar(20) unique per company | `OPP-000123`, numbering rule as above |
| `customer_id` | uuid FK `customers` ON DELETE RESTRICT, null | the buyer when known (same RESTRICT reason as `leads.customer_id`, `projects.py:693`) |
| `prospect_name` | varchar(200) null | required when `customer_id` is null (check): a showroom that is not a customer yet |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE SET NULL, null | portal: the logging contact's agent; CRM: stamped from the customer, editable |
| `title` | varchar(200) not null | |
| `status_id` | uuid FK `statuses` ON DELETE SET NULL, null | the stage, entity type `sales_opportunity` |
| `outcome` | varchar(8) not null default `open` | `open`, `won`, `lost`; set by the service from the terminal stage's key, the same split `leads.outcome` uses (`projects.py:718`) |
| `expected_amount` | numeric(15,2) not null | RM |
| `expected_close_month` | date not null | check day 1 |
| `product_note` | text null | "200 basins, white" |
| `product_category_id` | uuid FK null | optional interest |
| `lost_reason` | varchar(150) null | a value from lookup set `sales_opportunity_lost_reasons`; required on lost |
| `sales_order_id` | uuid FK `sales_orders` ON DELETE SET NULL, null | optional on won, must be the same customer |
| `source` | varchar(8) not null | `portal` or `crm` |
| `created_by_contact_id` | text FK `respond_contacts` ON DELETE SET NULL, null | set on portal creates |
| `created_by_user_id`, `stage_changed_at`, `created_at`, `updated_at` | | |

**Stages reuse the status engine.** `app/modules/sales/status_entities.py` registers
`StatusEntity(entity_type="sales_opportunity", label="Sales Opportunity", module="sales",
model=SalesOpportunity, record_label_attr="title", required_flags=["is_initial", "is_terminal"])`
with no scope resolver, exactly as `_register_project_lead` does
(`app/modules/projects/status_entities.py:155-177`). A startup seed
`seed_default_opportunity_graph` in `app/services/sales/sales_seed_service.py`, modelled on
`seed_default_lead_graph` (`project_seed_service.py:673`), creates the default graph once:

| key | label | win_probability | flags |
| --- | --- | --- | --- |
| `new` | New | 10 | initial, default |
| `qualified` | Qualified | 25 | |
| `proposal` | Proposal | 50 | **`is_active = false`** (G5: "not so applicable for retail trading, but configurable") |
| `negotiation` | Negotiation | 75 | |
| `won` | Won | 100 | terminal |
| `lost` | Lost | 0 | terminal |

Edges: every live stage to the next live stage and to Won and Lost, plus back one step, so
turning Proposal on in System > Status Graphs needs no code. The seed never re-asserts once any
`sales_opportunity` row exists (the lead seed's wholesale guard). Won and Lost are recognised by
`key`, never by label, so an admin may rename them. Lost reasons: lookup set
`sales_opportunity_lost_reasons` seeded like `seed_lead_disqualify_reasons`
(`project_seed_service.py:783`) with Price, Went to competitor, Project cancelled, No response,
Other.

**Pipeline (S3):** `sum(expected_amount x win_probability / 100)` over opportunities whose stage
is not terminal and whose `expected_close_month` falls in the chosen month, grouped by
`sales_agent_id`. An opportunity sitting on a stage with a null `win_probability` counts 0 and is
flagged in the count, never guessed at 50 (the engine's own rule, `status.py:105-109`).

### 3.5 Portal logging for salespeople (ruling G9, G10)

- New portal kind `sales_opportunity`, added to `GRANTABLE_PORTAL_FORM_TYPES`
  (`portal_service.py:83`) and not to the base kinds, so no contact sees it until granted:
  per contact through `contact_portal_form_overrides` (`price_tag.py:45`), or to a group through a
  market segment's `portal_form_types` (`access.py:150`). "Opened to dealer salesperson first"
  (G10) is therefore a grant, not code: the owner grants it to the dealer-channel salespeople first
  (round 2 R1 confirms who they are).
- A second gate: the contact must resolve to an active sales agent through `sales_agents.contact_id`
  (the resolver lifted from `price_tag_request_service.py:2380-2404`); otherwise 403
  `NOT_A_SALES_AGENT`. The agent is taken from the token, never from the request body.
- Router `app/api/v1/public/portal_sales_opportunity.py`, mounted before `portal.router` like
  `portal_price_tag` (`public/__init__.py:32`): list mine, create, get mine, update mine
  (title, amount, close month, note, stage move along allowed edges, lost reason). An agent sees
  only opportunities whose `sales_agent_id` is theirs; anything else is 404, not 403, so ids
  cannot be probed. The customer picker offers only the agent's own customers
  (`customers.sales_agent_id`), plus "not a customer yet" with a prospect name. Company comes from
  the chosen customer, else the agent's company, else the default company.
- FE: `app/(auth)/portal/sales_opportunity/` (list, new, `[id]`), a landing card shown when the
  kind is visible, reusing the portal `AsyncCombobox` and `FormSection` components.
- The CRM side (Sales > Opportunities, customer section) reads and edits the same rows; the sales
  admin can still log on an agent's behalf.

### 3.6 Per-contact WhatsApp broadcast (ruling G6, G7, G8, slice S5)

`sales_target_recipients` (S5), `CompanyScopedMixin`, one row per contact per thing they follow:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `contact_id` | text FK `respond_contacts` ON DELETE CASCADE, not null | who receives |
| `follows_kind` | varchar(16) not null | `agent`, `dealer` or `team` (check) |
| `sales_agent_id` | uuid FK null | required when `agent` |
| `customer_id` | uuid FK null | required when `dealer` |
| `frequency` | varchar(16) not null default `weekly` | `daily`, `weekly`, `monthly` (G7) |
| `weekday` | smallint null | 0 Monday to 6 Sunday, required when weekly; default 0 |
| `day_of_month` | smallint null | 1 to 28, or 0 for "last day", required when monthly |
| `send_time` | time not null default 09:00 | |
| `timezone` | varchar(64) not null default `Asia/Kuala_Lumpur` | |
| `show_commission` | bool not null | G6: default true for `agent`, false for `dealer` |
| `show_pipeline` | bool not null | G8: default true for `agent` and `team`, false for `dealer` |
| `show_breakdown` | bool not null default false | G8: one line per target instead of one combined line |
| `enabled` | bool not null default false | ships off; the owner turns each on after a Send now |
| `next_run_at`, `last_sent_at` | timestamp null | runner bookkeeping |
| `created_at`, `updated_at` | | |

Unique `(contact_id, follows_kind, coalesce(sales_agent_id, nil), coalesce(customer_id, nil))`,
the coalesce pattern of `uq_sales_agents_company_sales_agent` (`sales_agent.py:128-133`).

Why a table and not columns on `respond_contacts`: a contact may follow more than one thing (the
owner follows the team and one key dealer), each with its own schedule, and the rows belong to an
uninstallable module. This is the second-case rule in `PRINCIPLES.md`, not speculation.

- **One runner, many schedules.** A seeded `scheduled_tasks` row `sales_target_broadcast_runner`
  (every 5 minutes, enabled) calls a handler that sends for every enabled recipient whose
  `next_run_at <= now`, then advances `next_run_at` with `next_run_for(frequency, weekday,
  day_of_month, send_time, timezone)`, which extends `_next_run_for_daily`
  (`automation_service.py:50`) to weekly and monthly. The same shape as `automation_runner`
  (`task_scheduler.py:335`). With no enabled recipients it does nothing, so shipping it enabled is
  safe; each recipient is the switch.
- **Content.** `render_progress_message(recipient, rows)` builds one message per recipient: for
  each target the recipient follows that is active in the current month, the period target,
  achieved, %, gap and days left in the period; commission earned only when `show_commission`;
  pipeline only when `show_pipeline`; a `team` recipient gets team totals plus one line per agent.
  A recipient never receives another subject's figures unless it follows `team`.
- **Send.** `send_text_or_template(db, identifier=contact.respond_io_id, text=...,
  use_case="sales_target_progress", context_vars={...}, respond_contact_id=contact.id)`; new use
  case in `TEMPLATE_DEFAULT_USE_CASES`; the owner gets the template approved by Meta (ops gate in
  the S5 DoD). Skip when `outbound_enabled` is false. `integration_log` on success and failure,
  `business_table="sales_target_recipients"`, `business_id=recipient.id`. Idempotency: the runner
  advances `next_run_at` in the same transaction as the log row, and skips a recipient that already
  has a success row for this use case since its previous scheduled time.
- **Send now** on a recipient row sends one message in the request (`sales.targets.edit`).
- Suggested recipients: the Recipients tab offers "Add suggested" rows for every agent with a
  `contact_id` and every dealer target's primary `respond_contact_customers` contact, disabled,
  with the G6 and G8 defaults above.

### 3.7 Module, permissions, menu (ruling G9)

- `app/modules/sales/bootstrap.py` with `MODULE_KEY = "sales"`, an `app_modules_catalog` row,
  `"sales": "sales"` in `permission_module_map.py`, and `app/modules/sales/status_entities.py`.
- `PERMISSION_REGISTRY.extend(_crud("sales", "targets", "Sales Targets"))` and
  `_crud("sales", "opportunities", "Sales Opportunities")`. `sales.targets.edit` is the owner's
  "sales targets: edit"; it also gates tiers, recipients and Send now (no further slug until a
  role needs to split them). Grant sweep in the S1 and S2 migrations: all slugs to admin and
  superadmin; everyone else through the role editor.
- Routers `app/api/v1/sales/targets.py`, `opportunities.py`, `recipients.py` under `/sales`,
  behind `require_module_enabled_with_api_key("sales")`; the portal router in section 3.5.
- FE: a **Sales** sidebar group (`moduleKey: 'sales'`) with Targets and Opportunities. Pages
  `app/(protected)/sales/targets/` (tabs Agents, Dealers, Recipients), `app/(protected)/sales/targets/[id]/`
  (target detail: header, periods, scope, tiers; view and edit are the same layout),
  `app/(protected)/sales/opportunities/` and `[id]`. Services `salesTargetService.ts`,
  `salesOpportunityService.ts`, `salesRecipientService.ts`; hooks on the shared factories.
- List-query adapter `sales_opportunities`. The Targets grid is one row per target period in the
  chosen month (tens of rows), served unpaged.

## 4. Journey value order

The owner sees value at the end of each lane, in this order: targets and live achievement (S1),
salespeople logging opportunities in the portal (S2), pipeline beside the target (S3), commission
(S4), the WhatsApp broadcast (S5). Each slice is one lane, one branch, one PR, so S1 ships before
S2 is started and nothing waits on a bundle.

## 5. Considered and not chosen

- **Reuse `projects.leads` for opportunities.** Project leads belong to the Project Sales module
  (`projects` schema), are owned by a user (`owner_user_id`), and lead to project quotations.
  Dealer opportunities are owned by a sales agent who has no login. Kept apart; only the stage
  **table** is shared, which is what G5 asked for.
- **Fixed stage constant.** Round 1's recommendation; ruled out by G5.
- **A shared commission plan table.** See 3.3 and its trigger.
- **Stored achievement.** See 3.1 and its trigger.
- **One global broadcast schedule in Scheduled Tasks.** Round 1's recommendation; ruled out by G7
  (per contact).
- **Columns on `respond_contacts` for broadcast preferences.** See 3.6.
- **Opportunities over WhatsApp chat.** The portal covers G9; a chatbot intake is a later lane.
  **Trigger:** salespeople report the portal form is too slow in the field.
- **A "My targets" page in the portal.** Not asked; the WhatsApp message carries the figures.
  **Trigger:** the owner asks for salespeople to check progress between messages.

## 6. Slices and lanes

Every slice is its own lane (one branch, one PR), in this order, and runs Phase 1 (FE against a
mock service, all states tuned, browser checked) then Phase 2 (tester writes the UAC tests red,
the one coder makes them green, mock swapped at the service boundary) then Phase 3 once. Track:
full for all five (each has a migration or a new external surface).

### S1. Flexible targets with live achievement in the CRM (UAC S1-1 to S1-16)

- Backend seam: migration (`sales_targets`, `sales_target_periods`, `sales_target_scope`,
  `ix_sales_orders_order_date`, `TGT` numbering rule, grant sweep); models
  `app/models/sales_target.py`; schemas `app/schemas/sales.py`; `achievement_service`,
  `target_service` (create with period generation, update with regeneration, duplicate, delete,
  list for a month); routes `GET/POST /sales/targets`, `GET/PATCH/DELETE /sales/targets/{id}`,
  `PATCH /sales/targets/{id}/periods/{period_id}`, `POST /sales/targets/{id}/duplicate`; module
  bootstrap and permissions.
- Frontend seam: Sales menu group; Targets page (month picker, Agents and Dealers tabs, one row
  per active target period plus "No target" rows for agents without one, Unassigned foot row);
  Set target modal (subject, name, metric, basis, product scope, start month, months,
  periodicity, value per period); target detail page with the periods table (inline edit), scope
  list and deferred-action delete; Duplicate action.
- Tests: pytest golden sets for all four metric x basis cells, scope (all, categories with a
  sub-category, products), period boundaries, attribution, project orders counted, generation and
  regeneration, 403 per route, company scope; vitest for the modal payload and the scope switch;
  agent-browser run.
- DoD: figures on the dev DB (prod copy) for September match the sales report's ordered and
  confirmed columns for the same orders; a non-admin role granted `sales.targets.view` sees the
  page; 375 and 1280.

### S2. Opportunities, logged by salespeople in the portal (UAC S2-1 to S2-14)

- Backend seam: migration (`sales_opportunities`, `OPP` numbering rule, grant sweep); status
  entity registration and default graph seed; lost reason lookup seed; `opportunity_service`;
  CRM routes and list-query adapter; portal router and kind; the shared contact to agent
  resolver.
- Frontend seam: portal landing card, list, form and detail at 375 first; CRM Sales >
  Opportunities DataGrid, opportunity detail with `RecordNavigation`, Opportunities section on
  customer detail (view and edit, empty state + CTA).
- Tests: portal gates (kind not granted 403, contact without agent 403, other agent's row 404,
  agent from token not body), stage moves along engine edges only, lost needs a reason, won SO
  same customer, prospect name when no customer, Proposal off by default and on after an admin
  toggle with no code change; vitest for the portal form; agent-browser run in the portal and CRM.
- DoD: as S1, plus security-reviewer (external ingest surface).

### S3. Pipeline beside the target (UAC S3-1 to S3-4)

- Backend seam: `pipeline_by_agent` joined into the targets list.
- Frontend seam: Pipeline column and KPI, linking to Opportunities filtered to that agent and
  month.
- Tests: weighted golden set with configured probabilities; terminal stages excluded; a null
  probability counts 0 and is flagged; no opportunity ever in achievement.
- DoD: as S1.

### S4. Commission tiers (UAC S4-1 to S4-9)

- Backend seam: migration `sales_target_commission_tiers`; `commission_service`; tiers in the
  target create, update and duplicate payloads; `commission_earned`, `bonus_earned` and
  `commission_breakdown` on each period row.
- Frontend seam: Commission section in the modal and detail (method, tier rows), Commission
  column with a breakdown popover.
- Tests: golden numbers for flat, marginal, retroactive, quantity RM per unit, bonuses at 100%,
  the 99.99% boundary, rounding; vitest for the tier editor.
- DoD: the owner checks one agent's period against their own spreadsheet.

### S5. Per-contact WhatsApp broadcast (UAC S5-1 to S5-13)

- Backend seam: migration (`sales_target_recipients`, runner `scheduled_tasks` row); recipient
  service and routes; `next_run_for`; runner handler; renderer; use case in
  `TEMPLATE_DEFAULT_USE_CASES`; Send now. Worker restart after the handler lands.
- Frontend seam: Recipients tab (DataGrid), recipient modal (contact, follows, schedule, what they
  see), Add suggested, Send now, Preview message.
- Tests: next-run golden table (weekly across a week boundary, monthly last day, timezone), content
  flags (commission hidden, pipeline hidden, breakdown), a dealer never sees another dealer, skip
  rules, log on success and failure, idempotency, permission; agent-browser run.
- DoD: the Meta-approved template is mapped on prod before any recipient is enabled; the owner
  enables their own row after one Send now looks right; security-reviewer (outbound business
  figures to external contacts).

## 7. Risks

- **Attribution depends on AutoCount's agent code.** An order with an unknown code has a null
  agent and counts for nobody; the Unassigned row keeps it visible.
- **One person, several codes.** 38 codes are 16 people (`sales_agent.py:56-59`). A target on one
  code misses that person's orders under their other codes. Round 2 R2.
- **Delivered has no date.** See 3.2 and round 2 R3.
- **Tax inclusive amounts.** `line_total` is Total (Inc); commission on it overpays by the tax
  share. Round 2 R4.
- **Template approval lead time.** Without an approved template every send outside the 24h window
  is skipped; S5 DoD gate.
- **Agent contact coverage.** Portal logging and agent broadcasts need `sales_agents.contact_id`;
  measure the count on prod before S2 and list the gaps for the owner.

## 8. Grill questions and the owner's rulings

The questions and their round 1 options are kept; each recommendation is replaced by the owner's
ruling, quoted from the PR #1260 comment of 26 Sep 2026 05:25Z.

- **G1. What counts as "achieved"?** Options: ordered (every non-cancelled sales order line, as
  soon as the order exists), delivered (only what has gone out), invoiced (not available: the CRM
  has no customer invoice table).
  **Owner ruling 26 Sep:** configurable, "whether we want to measure on ordered or delivered which
  is confirmed". Built as `sales_targets.basis` (`ordered` or `delivered`), delivered = the sales
  report's confirmed figure (3.1, 3.2).
- **G2. Whose sale is it when a customer changes agent?**
  **Owner ruling 26 Sep:** "based on sales order agent"; a dealer target counts all of that
  dealer's orders, whichever agent is on them (3.2).
- **G3. Period.** Round 1 option: monthly only, quarter and year as sums.
  **Owner ruling 26 Sep:** configurable, "this target is valid for how many months, just like Odoo
  sales module style". Built as `start_month`, `months` and `periodicity` with one editable
  target figure per period (3.1).
- **G4. Quantity targets, of what?** A quantity across all products mixes basins with screws.
  **Owner ruling 26 Sep:** amount or quantity, set "by product or category or all"; "very flexible
  in terms of the metrics we use on, the spread of products that the metric is applicable, and the
  date range that the target is eligible". Built as `metric`, `product_scope` with scope rows, and
  the validity above (3.1).
- **G5. Opportunity stages.** Round 1 option: fixed six stages New, Qualified, Proposal,
  Negotiation, Won, Lost at 10, 25, 50, 75, 100, 0; New stands in for lead; Lost stays visible
  with its reason.
  **Owner ruling 26 Sep:** "reuse our stage table for configuration"; "proposal is not so
  applicable for retail trading, but this can stay configurable". Built on the status engine
  (`statuses`), the table the Project Sales lead funnel uses, with Proposal seeded inactive (3.4).
- **G6. Commission rule.** Round 1 option: flat % plus one incentive at 100%, no tiers, no
  commission on quantity targets.
  **Owner ruling 26 Sep:** "as full suite as possible": tier setting, higher rates above target and
  commission on quantity targets, all configurable; whether commission shows in the WhatsApp
  message "is configurable per contact". Built as tiers with marginal or retroactive method and
  per-tier bonuses (3.3), and `show_commission` per recipient (3.6).
- **G7. Broadcast cadence.** Round 1 option: weekly, Monday 09:00 Malaysia time, one global
  schedule, task ships off.
  **Owner ruling 26 Sep:** "set per contact". Built as a schedule on each recipient row, run by
  one heartbeat task, each recipient shipping disabled (3.6).
- **G8. Who receives what?** Round 1 option: agents and dealers receive only their own figures,
  plus a team summary for the owner.
  **Owner ruling 26 Sep:** "configurable per contact". Built as `follows_kind` and the `show_*`
  flags per recipient (3.6).
- **G9. Who sets targets and logs opportunities?**
  **Owner ruling 26 Sep:** targets by admins plus anyone given "sales targets: edit"; "salesperson
  should log their sales opportunities by using portal". Built as `sales.targets.*` and the portal
  kind `sales_opportunity` (3.5, 3.7).
- **G10. Do project sales count?**
  **Owner ruling 26 Sep:** "as long as it is the agent's sales, then should count, this will be
  opened to dealer salesperson first". Built as no `demand_class` filter on agent attribution
  (3.2); the portal kind is granted to dealer-channel salespeople first (3.5).

## 9. Round 2 questions (posted on PR #1260)

- **R1. Who is a "dealer salesperson"?** Recommend: Sorento's own sales agents who sell to dealers
  (the retail channel), each linked to their WhatsApp contact on the Sales Agents master; the
  owner grants them the portal form first and project salespeople later. Not the dealers' own
  shop staff.
- **R2. One person, several agent codes.** Recommend: a target on an agent counts every code that
  shares its person label (for example SEAN I and SEAN III), falling back to the one code when no
  label is set.
- **R3. Delivered has no delivery date in the CRM.** Recommend: a delivered target counts what has
  gone out so far from orders dated inside the period (the sales report's "confirmed" figure).
  Deliveries of older orders do not move into the new period.
- **R4. Tax.** Recommend: keep tax-inclusive amounts (as AutoCount sends them) for targets and
  commission in S1 to S4, and measure on prod whether `unit_price x qty - discount` is a
  trustworthy ex-tax figure before offering an ex-tax option.
- **R5. Tier method default.** Recommend: `marginal` (the higher rate applies only to the part
  above each threshold), with `retroactive` selectable per target.

## 10. Out of scope

A leaderboard, a kanban board for opportunities, opportunities over WhatsApp chat, a portal "My
targets" page, stored snapshots, a shared commission plan table, a dimension engine, and the #1168
stock asks log. Each has its trigger named above; deferred items go to
`documentation/backlogs/backlog.md` once round 2 is answered.
