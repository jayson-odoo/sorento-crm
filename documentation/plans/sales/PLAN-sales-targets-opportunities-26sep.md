# PLAN: sales targets, opportunities and the WhatsApp achievement broadcast (#1170)

Status: planned, draft for owner grill (26 Sep 2026). Track: full track (new tables, a migration,
new permissions, a new module key). Nothing built beyond slice 1 (PR #1177).
Domain: sales. Classification: **MODULE** `sales` (installable; another tenant with a sales team
would turn it on), tables in `public` with normal FKs (targets and opportunities are durable
business records, so by the uninstall test they stay in `public`).
UAC: `sales-targets-opportunities-26sep-acceptance-criteria.md` alongside (the contract; the
journey J1 to J9 lives there and is not repeated here).
Mockup: `mockups/sales-targets.html` (the Targets screen at 1280 and 375, the Set target modal,
and the WhatsApp message an agent and a dealer receive).
Grill questions: the last section of this file, ten of them, each with a recommendation. Every
AC in the UAC is written to the recommended answer.

## 1. In plain words (for the owner)

Three ideas, and how they fit together.

- **A target** is the number a person is expected to reach in a period, for example "Ali: RM
  120,000 of sales in October". Odoo sets targets per salesperson (or per team) for a monthly,
  quarterly or yearly period, measured as amount sold, amount invoiced, quantity sold or quantity
  invoiced ([Odoo 18 Commissions][odoo-comm]). Odoo's older, simpler version is one monthly
  "Invoicing Target" per sales team, compared against paid invoices this month
  ([Odoo sales teams][odoo-teams], [crm_team.py][odoo-crmteam]).
- **Achievement** is what actually happened, counted from real documents. Odoo lets each plan
  choose which document counts (orders or invoices), and its different screens do not agree
  (the team target counts paid invoices, the gamification "Total Invoiced" goal counts every
  non-cancelled invoice, draft included) ([gamification data][odoo-gami]). Sorento has no
  customer invoice table in the CRM, so the plan counts **sales orders** (grill G1).
- **An opportunity** is a possible sale being worked on: "Dealer X may order 200 basins for a
  new showroom, about RM 40,000, likely in November". It moves through **stages** as it firms up.
  Odoo's defaults are New, Qualified, Proposition, Won ([crm_stage_data.xml][odoo-stages]); Lost is
  not a stage in Odoo but an archived state with a lost reason ([Odoo lost opportunities][odoo-lost]).
  The common industry shape (Salesforce) is Prospecting, Qualification, ..., Proposal/Price Quote,
  Negotiation/Review, Closed Won, Closed Lost ([Salesforce stages guide][sf-stages]). A **lead**
  in Odoo is an unchecked enquiry that is converted into an opportunity once qualified
  ([Odoo convert leads][odoo-convert]); here New plays that role, so there is no separate lead
  object.
- **Pipeline vs achievement.** Each stage carries a probability (the chance it closes). Odoo
  multiplies expected revenue by probability to get **prorated (weighted) revenue**
  ([crm_lead.py][odoo-lead]) and groups it by expected closing month in its Forecast view
  ([crm_lead_views.xml][odoo-leadviews], [expected revenue report][odoo-exprev]). That weighted
  figure is the **pipeline**: what is likely to come. It is shown **next to** the target and
  never added into achievement, or a sale would be counted twice (once as a won opportunity,
  once as the order). A common rule of thumb is to hold about 3x the remaining target in pipeline;
  the sharper version is 1 / win rate ([Clari][clari]).
- **Commission and incentive.** The simplest commission is a flat percentage of what was achieved
  (Odoo's "achievement based" plan, e.g. 5% of invoiced amounts). Odoo's "target based" plan pays
  an "On Target Commission" at 100% and can add levels above and below it
  ([Odoo 18 Commissions][odoo-comm]); accelerators above target are common in industry
  ([QuotaPath][quotapath]). This plan starts with a flat % plus one fixed **incentive** (bonus)
  paid when the target is reached, and names the trigger for tiers (grill G6).

Research note: odoo.com and Salesforce help pages were blocked by the network proxy during
research; the Odoo facts above were read from the official Odoo 18.0 documentation source and
the Odoo 18.0 code on GitHub instead (links point at those). The Salesforce, pipeline coverage
and accelerator points come from secondary sources as linked.

[odoo-comm]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/sales/commissions.rst
[odoo-teams]: https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/sales/crm/pipeline/manage_sales_teams.rst
[odoo-crmteam]: https://raw.githubusercontent.com/odoo/odoo/18.0/addons/sale/models/crm_team.py
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

## 2. Measured facts (read-only, origin/main 46711c61)

Backend paths are under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`.

**Sales agents.** `sales_agents` (`app/models/sales_agent.py:43`): code `sales_agent` (:50),
`person_label` (:60), `is_active` (:52), `company_id` nullable, NULL = shared row (:73, not
`CompanyScopedMixin`), `contact_id` Text FK `respond_contacts.id` ON DELETE SET NULL (:89-93), the
agent's WhatsApp identity. Agents are not users and not a role (docstring :1-17, ruling 14 Aug
2026). API `app/api/v1/master_data/sales_agents.py` (list :40, detail :94, annotate :109; no
create or delete). Slug `master_data.sales_agents.*` (`app/rbac/permission_registry.py:219`).
FE `app/(protected)/master-data-management/sales-agents/`, menu `config/menu.config.tsx:695`.

**Customers.** `customers` is company scoped (`app/models/order.py:49`), `sales_agent_id` FK ON
DELETE SET NULL (:142-146), `sales_agent` relationship (:163) with `sales_agent_code` /
`sales_agent_name` properties (:165-180). Slice 1 exposed it (PR #1177): `CustomerCreate` /
`CustomerUpdate` / `CustomerResponse` carry it (`app/schemas/order.py:47,57,76-78`), resolved by
`_resolve_sales_agent` (`app/services/order_service.py:3446`). There is **no dealer flag** on
`customers`: "dealer" exists only as the sales report's channel, `dealer` meaning
`SalesOrder.demand_class == "retail"` (`app/services/sales_report_service.py:264-265`).

**Sales orders, the achievement source.** `sales_orders` (`app/models/order.py:413`):
`customer_id` (:422), `sales_agent_id` (:433, indexed :490, set from AutoCount's agent code on
ingest, `app/services/document_ingest_service.py:219`), `order_date` Date (:434, **not indexed**),
`demand_class` (:443), `status` default `open` (:451; vocabulary open / fulfilled / closed /
cancelled, `document_ingest_service.py:131-154`). No header total, no currency column (MYR is
implicit, `products.currency` default `app/models/product.py:229`). `sales_order_lines`
(:505): `product_id` (:509), `qty_ordered` (:511), `qty_delivered` (:512), `unit_price` (:518),
`line_total` "Total (Inc)", so tax inclusive (:526), `line_status` (:551). Products carry
`category_id` FK `product_categories` (`app/models/product.py:202`).

**The sales report predicate** (`app/services/sales_report_service.py`): filters
`SalesOrder.status != "cancelled"`, `SalesOrderLine.line_status != "cancelled"`, bucket not null
(:240-247); bucket = `coalesce(required_date, order_date)` (:195); `confirmed_value` =
`line_total x least(qty_delivered, qty_ordered) / qty_ordered` rounded per line; `ordered =
confirmed + outstanding`, outstanding only on open order + open line (:202-215). The report has
no agent filter. The target achievement reuses this predicate but buckets by `order_date` (the
day the sale was made, not the day the goods are wanted) and groups by agent or customer.

**Respond.io.** `respond_contacts` (`app/models/access.py:231`), `outbound_enabled` kill switch
(:258), enforced by `assert_outbound_enabled` (`app/services/respond_outbound_service.py:34`).
Dealer contact link `respond_contact_customers` (`app/models/access.py:32`, `is_primary` :40, one
primary per contact per company :56). Send path `send_text_or_template(db, *, identifier, text,
use_case, context_vars=None, respond_contact_id=None)`
(`app/services/respond_messaging_service.py:545`): text inside the 24h window, else the template
mapped in `respond_template_defaults` (`app/models/respond_template.py:225`); a new use case must
be added to `TEMPLATE_DEFAULT_USE_CASES` (:37-126), validated at
`app/services/respond_template_service.py:450`. Callers write their own `integration_log` row
(`app/models/integration.py:114`, `business_id` is a UUID; lesson: log success AND failure).

**Scheduling precedents.**
- Ideation reminder: a hard-coded APScheduler job every 15 min
  (`app/scheduler/task_scheduler.py:660-666`) calling `sweep_idle_ideation_drafts`
  (`app/services/ideation_turn_service.py:1060`), which sends via
  `send_text_or_template(..., use_case="ideation_draft_reminder")` (:946-948) and keeps its
  idempotency marker in `session_vars`.
- Configurable tasks: `scheduled_tasks` rows (`app/models/scheduled_task.py:10`, units seconds /
  minutes / hours / days, `timezone`, `start_at`), run by the 10 s heartbeat
  (`task_scheduler.py:598-614`) against handlers registered in `register_task_handlers`
  (:566-595), seeded by migration (e.g. `alembic/versions/072_seed_scheduled_tasks.py`). Runs on
  the batch worker only (`ENABLE_SCHEDULER`, `worker.py:74-80`).
- Low stock: there is **no scheduled low stock broadcast** in code or history; the only low stock
  surface is the chat-triggered report (`app/services/scm/low_stock_report_service.py`). The
  closest batch-notify precedent is `product_discontinued_check` (`task_scheduler.py:361`,
  `app/services/product_discontinued_notify_service.py:181`). No broadcast table exists.

**Activity log.** `activity_events` (`app/models/activities.py:26`) has adapters only for
`ticket` and `project` (`app/main.py:222,238`). The audit timeline
(`app/services/activity_service.py:89`) already covers `customer`. The #1168 asks log
(`stock_asks`) is planned, not built (`documentation/plans/chatbot/PLAN-chatbot-stock-ask-v2-24sep.md`
S5). This plan needs no activity log: opportunity stage history comes from `__audit_track__`.

**Nothing to collide with.** No table named target, quota, commission, incentive or opportunity
exists. Project Sales has `projects.leads` (`app/models/projects.py:673`) and a project funnel on
the generic status engine (`app/models/status.py:69`, `win_probability` :110); that is the project
(tender) pipeline, owned by users, not the dealer pipeline owned by sales agents (see section 4).

**Plumbing.** `_crud` (`app/rbac/permission_registry.py:11-18`); slug prefix to module key map
(`app/modules/runtime/permission_module_map.py:17-35`, no `sales` entry); module keys come from
`app/modules/*/bootstrap.py` (no `sales` module today); routers mounted with the guard in
`app/api/v1/__init__.py`. List-query adapters: `app/services/list_query_registry.py:93-175`.
Alembic single head today: `oisl_0001_suggested_links`.

## 3. Design

### 3.1 Tables (one migration in S1, one in S4, one seed in S6)

`sales_targets` (S1), `CompanyScopedMixin`:

| column | type | note |
| --- | --- | --- |
| `id` | uuid pk | |
| `company_id` | uuid | mixin |
| `period_month` | date not null | check: day 1. Monthly grain (G3). |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE CASCADE, null | exactly one of agent / customer (check) |
| `customer_id` | uuid FK `customers` ON DELETE CASCADE, null | the dealer target |
| `measure` | varchar(16) not null | check `amount` or `quantity` |
| `product_category_id` | uuid FK `product_categories`, null | required when `measure = quantity` (check) (G4) |
| `target_value` | numeric(15,2) not null | RM or units |
| `commission_pct` | numeric(5,2) null | flat % of achieved amount (G6) |
| `incentive_amount` | numeric(15,2) null | paid once when achieved >= 100% |
| `created_by_user_id`, `created_at`, `updated_at` | | |

Unique index on `(company_id, period_month, coalesce(sales_agent_id, nil), coalesce(customer_id,
nil), measure, coalesce(product_category_id, nil))`, the same coalesce pattern as
`uq_sales_agents_company_sales_agent` (`app/models/sales_agent.py:128-133`). S1 also adds
`ix_sales_orders_order_date` (`order_date` is unindexed and every achievement query is a month
range across the whole team).

**Extensible dimensions without a dimension engine.** The owner asked for room to add dimensions
later (brand, region, channel). Per `PRINCIPLES.md` "Simplest thing", there is no generic
dimension table now: `product_category_id` is the one dimension with a present need (a quantity
target must say quantity of what). A new dimension is one nullable FK column, one extra filter in
the achievement query and one more term in the unique index. **Trigger for a generic
`target_dimensions` table:** a third dimension is requested, or a single target needs two values
of the same dimension.

**No stored achievement.** Achievement is computed at read time with one grouped query per
screen (sum over `sales_order_lines` join `sales_orders`, month range on `order_date`, group by
`sales_agent_id` or `customer_id`). Sales orders keep arriving and changing from AutoCount, so a
stored snapshot would go stale and need its own refresh job. **Trigger for a snapshot table:**
the targets grid p95 exceeds 1 s on prod data, or the owner wants a closed month frozen against
later AutoCount edits (then snapshot at month close only).

`sales_opportunities` (S4), `CompanyScopedMixin`, `__audit_track__ = True` (stage history for
free through the existing audit timeline):

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `opportunity_no` | varchar(20) unique per company | `OPP-000123`, the human id (no UUID in the UI) |
| `customer_id` | uuid FK `customers` ON DELETE CASCADE, not null | |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE SET NULL, null | stamped from the customer at create, editable |
| `title` | varchar(200) not null | |
| `stage` | varchar(20) not null default `new` | check: new, qualified, proposal, negotiation, won, lost |
| `expected_amount` | numeric(15,2) not null | RM |
| `expected_close_month` | date not null | check: day 1 |
| `product_category_id` | uuid FK null | product interest |
| `product_note` | text null | free text interest ("200 basins, white") |
| `lost_reason` | text null | required when stage = lost (service check) |
| `sales_order_id` | uuid FK `sales_orders` ON DELETE SET NULL, null | set on won, must be the same customer |
| `stage_changed_at`, `created_by_user_id`, `created_at`, `updated_at` | | |

Stages and probabilities are a Python constant (`STAGE_PROBABILITY = {new: 10, qualified: 25,
proposal: 50, negotiation: 75, won: 100, lost: 0}`), not rows in `statuses` (G5). The status
engine is built for per-scope configurable funnels; nobody has asked to configure these. **Trigger
for moving to the status engine:** the owner asks for a custom stage or different probabilities.

### 3.2 Achievement and roll-up (one service)

`app/services/sales/achievement_service.py`:

- `achieved_by_subject(db, *, period_month, subject: "agent" | "customer", category_id=None,
  measure)` returns `{subject_id: value}`. Filter: the sales report predicate
  (`status != cancelled`, `line_status != cancelled`) plus `order_date` in
  `[period_month, next_month)`. Amount = `sum(coalesce(line_total, 0))`; quantity =
  `sum(qty_ordered)` joined to `products.category_id` when a category is given. Orders with a null
  `order_date` never count (same rule as the report's S16).
- `pipeline_by_agent(db, *, period_month)` returns `{agent_id: (weighted_value, count)}` over
  opportunities in stages new to negotiation with that close month.
- The targets list endpoint calls both once and joins in Python: two queries per screen, not one
  per row.

The predicate is written once as `achievement_filters()` in this service. The sales report keeps
its own `_common_filters`; they differ on purpose (bucket column), and a test pins both to the
same cancelled rules so they cannot drift silently.

### 3.3 Broadcast (S6)

- Handler `sales_target_broadcast` registered in `register_task_handlers`; `scheduled_tasks` row
  seeded by migration: `interval_unit=days`, `interval_value=7`, `timezone=Asia/Kuala_Lumpur`,
  `start_at` = next Monday 09:00 (G7). The owner can change the cadence in the existing Scheduled
  Tasks screen; no new settings surface.
- Recipients: agent targets go to `sales_agents.contact_id`; dealer targets go to the customer's
  primary `respond_contact_customers` contact (G8). Skip when no contact or `outbound_enabled` is
  false; count skips in the run summary.
- Text built by one function `render_progress_message(target, achieved, days_left)`; sent with
  `send_text_or_template(db, identifier=contact.respond_io_id, text=..., use_case=
  "sales_target_progress", context_vars={...}, respond_contact_id=contact.id)`. A new use case in
  `TEMPLATE_DEFAULT_USE_CASES` plus a Respond.io template the owner must get approved by Meta
  first (a Monday message is almost always outside the 24h window, so without the template every
  send is skipped). This is an ops step outside the code, listed in the S6 DoD.
- `integration_log` on success and failure, `business_table="sales_targets"`,
  `business_id=target.id`. Idempotency: skip a target that already has a success row for this use
  case on today's Malaysia date. No broadcast table.
- Worker only: the scheduler runs on the batch worker; `send-now` runs in the request (one send).

### 3.4 Module, permissions, menu

- `app/modules/sales/bootstrap.py` with `MODULE_KEY = "sales"`, an `app_modules_catalog` row, and
  `"sales": "sales"` in `permission_module_map.py`.
- `PERMISSION_REGISTRY.extend(_crud("sales", "targets", "Sales Targets"))` and
  `_crud("sales", "opportunities", "Sales Opportunities")`. **Grant sweep** in the S1 / S4
  migrations: grant all eight slugs to the admin and superadmin roles; other roles through the
  role editor (G9).
- Routers `app/api/v1/sales/targets.py` and `opportunities.py`, mounted at `/sales` behind
  `require_module_enabled_with_api_key("sales")`.
- FE: a **Sales** sidebar group (`config/menu.config.tsx`, `moduleKey: 'sales'`) with Targets and
  Opportunities. Pages `app/(protected)/sales/targets/` and `app/(protected)/sales/opportunities/`,
  services `services/salesTargetService.ts` and `services/salesOpportunityService.ts`, hooks
  `useSalesTargets` / `useSalesOpportunities` and mutation hooks on the shared factories.
- List-query adapter `sales_opportunities` in `list_query_registry.py` (the Opportunities
  DataGrid is a normal paged list). The Targets grid is not: it is one row per agent for one month
  (tens of rows), served by one endpoint without paging.

## 4. Considered and not chosen

- **Reuse `projects.leads` for opportunities.** Project leads belong to the Project Sales module
  (`projects` schema), are owned by a user (`owner_user_id`), carry the project status engine and
  lead to project quotations. Dealer opportunities are per customer and owned by a sales agent who
  has no login. Merging them would drag the project module into every dealer screen. Kept apart;
  G10 asks whether project sales orders count toward agent targets.
- **A commission plan table with tiers (Odoo's model).** Two numbers per target (a % and a bonus)
  cover the brief. **Trigger for plans and tiers:** the owner asks for a different rate above
  target, or one plan shared by many agents.
- **Stored monthly achievement.** See 3.1.
- **Opportunities logged by the agent on WhatsApp or the portal.** Agents have no login, and the
  portal is contact-token based (`app/models/portal.py:26`). Worth doing once the CRM flow is
  proven; **trigger:** the owner asks agents to log their own. Out of scope here (G9).

## 5. Slices and lanes

Three lanes, each one branch and one PR, each shippable alone in this order. Slices inside a lane
are commits on that lane's branch (standing rule, 2 Sep 2026).

- **Lane A, targets:** S1, S2, S3.
- **Lane B, opportunities:** S4, S5 (S5 needs Lane A merged).
- **Lane C, broadcast:** S6 (needs Lane A; the Meta template approval can start the day the
  owner signs off the message wording in the mockup).

Every slice runs Phase 1 (FE against a mock service, all states tuned, browser checked) then
Phase 2 (tester writes the UAC tests red, coder makes them green, mock swapped at the service
boundary) then Phase 3 once per lane.

### S1. Agent amount targets with live achievement (UAC S1-1 to S1-10)

- Backend seam: migration `sales_targets` + `ix_sales_orders_order_date` + grant sweep; model
  `app/models/sales_target.py`; schemas `app/schemas/sales.py`; `achievement_service`,
  `target_service` (create, update, delete, list month with every active agent); routes
  `GET/POST /sales/targets`, `PATCH/DELETE /sales/targets/{id}`; module bootstrap and permissions.
- Frontend seam: Sales menu group; Targets page with month picker, Agents tab grid (Target,
  Achieved, %, Pipeline placeholder hidden until S5, Commission placeholder hidden until S3); Set
  target modal; deferred-action delete.
- Tests: pytest golden set S1-4 (every cancelled and date edge), 403 per route, company scope,
  409 duplicate; vitest for the modal payload and the "No target" row; agent-browser run.
- DoD: real data on the dev DB (prod copy) for September; grant sweep verified with a non-admin
  role; 375 and 1280.

### S2. Copy last month, dealer targets, quantity targets (S2-1 to S2-7)

- Backend seam: `POST /sales/targets/copy`; dealer subject in list and create; quantity measure
  with the category filter.
- Frontend seam: Copy last month button; Dealers tab and Add dealer target modal; Measure switch
  revealing the category select.
- Tests: copy idempotency; both-or-neither 422; quantity golden set by category; vitest for the
  measure switch.
- DoD: as S1.

### S3. Commission and incentive (S3-1 to S3-3)

- Backend seam: `commission_earned` and `incentive_earned` computed in the list serializer
  (no column).
- Frontend seam: Commission column and its breakdown.
- Tests: golden numbers S3-2 including the 99.99% boundary and rounding.
- DoD: owner checks one agent's figure against their own spreadsheet.

### S4. Opportunities on the customer (S4-1 to S4-8)

- Backend seam: migration `sales_opportunities` + grant sweep; model, schemas, `opportunity_service`
  (create with agent stamped from customer, stage change rules, won to SO same-customer check);
  routes; list-query adapter.
- Frontend seam: Opportunities section on `CustomerDetail` (same position in view and edit, empty
  state + CTA); Sales > Opportunities DataGrid; opportunity detail page `/sales/opportunities/[id]`
  with `RecordNavigation`; Log / edit modal; stage change with Lost reason and Won SO select.
- Tests: stage rules, cross-customer SO 422, filters, permissions; vitest for the stage form;
  agent-browser run.
- DoD: as S1; customer detail still renders every other section unchanged.

### S5. Pipeline roll-up on targets (S5-1 to S5-3)

- Backend seam: `pipeline_by_agent` joined into the targets list.
- Frontend seam: Pipeline column, linking to the filtered Opportunities list.
- Tests: weighted golden set; won and lost excluded; no opportunity ever in `achieved_value`.
- DoD: as S1.

### S6. Scheduled WhatsApp broadcast (S6-1 to S6-9)

- Backend seam: `sales_target_broadcast_service` (recipient resolution, render, send, log,
  idempotency); handler registration; seed migration for the `scheduled_tasks` row; use case in
  `TEMPLATE_DEFAULT_USE_CASES`; `POST /sales/targets/{id}/send-now`.
- Frontend seam: Send now in the row menu; disabled with its reason when there is no contact.
- Tests: golden message text; skip rules; log on success and failure (stub the Respond client);
  same-day idempotency; permission on send-now. Worker restart after the handler lands.
- DoD: the Meta-approved template is mapped in Respond template defaults on prod before the task
  is enabled; the seeded task ships **disabled** and the owner enables it after one Send now to
  themselves looks right.

## 6. Risks

- **Attribution depends on AutoCount's agent code.** `sales_orders.sales_agent_id` is set from
  the ingest's `agent_code`; an order with an unknown code has a null agent and counts for nobody.
  S1 shows an "Unassigned" total row so the gap is visible rather than silent.
- **Tax inclusive amounts.** `line_total` is Total (Inc). Commission on a tax inclusive figure
  overpays by the tax share. G1 asks; if the owner wants ex-tax, the only honest source is
  `unit_price x qty_ordered - discount`, and whether that is ex-tax must be measured on real rows
  first.
- **Template approval lead time.** Without an approved template the broadcast silently becomes
  "skipped" for everyone outside the 24h window. The DoD makes this an explicit ops gate.
- **Agent contact coverage.** The broadcast only reaches agents with `contact_id` set. Measure the
  count on prod before S6 and list the gaps for the owner.

## 7. Grill questions for the owner

At most ten; each carries a recommendation, and the UAC is written to it.

- **G1. What counts as "achieved"?** Options: ordered (every non-cancelled sales order line, as
  soon as the order exists), delivered (only what has gone out), invoiced (not available: the CRM
  has no customer invoice table). **Recommend: ordered value, by order date, tax inclusive as
  AutoCount sends it**, because it is what the agent controls and it is visible the same day.
  Delivered can be shown as a second column later.
- **G2. Whose sale is it when a customer changes agent?** **Recommend: the agent on the sales order
  itself** (the AutoCount agent code at the time of the sale). Reassigning a customer then moves
  future orders, never history. A dealer target counts that customer's orders whoever the agent.
- **G3. Period.** **Recommend: monthly only.** Quarter and year views are sums of months, added
  when asked; a quarterly-only target would need a second grain in the table.
- **G4. Quantity targets, of what?** A quantity across all products mixes basins with screws.
  **Recommend: a quantity target must name one product category;** an amount target may not
  (it counts everything).
- **G5. Opportunity stages.** **Recommend: fixed six stages, New, Qualified, Proposal,
  Negotiation, Won, Lost, with fixed probabilities 10, 25, 50, 75, 100, 0.** New stands in for
  "lead"; no separate lead record. Lost stays visible with its reason rather than hidden.
- **G6. Commission rule.** **Recommend: a flat % of the whole achieved amount, plus one fixed
  incentive paid when the target reaches 100%.** No tiers or accelerators yet; no commission on
  quantity targets. Is commission shown to the agent in their WhatsApp message (recommend yes,
  it is the motivator) and never to the dealer?
- **G7. Broadcast cadence.** **Recommend: weekly, Monday 09:00 Malaysia time, current month to
  date.** Daily is noise; month end only is too late to act on. Changeable later in Scheduled
  Tasks without code.
- **G8. Who receives what?** **Recommend: each agent receives only their own figures; each dealer
  with a target receives only their own figures, on their primary WhatsApp contact.** Nobody
  receives a leaderboard of others. Should the manager also receive a one-message team summary
  (recommend yes, same schedule, to the owner's own contact)?
- **G9. Who sets targets and logs opportunities?** **Recommend: targets by admins and anyone given
  `sales.targets.edit` in the role editor; opportunities logged by CRM users (the sales admin) on
  the agent's behalf.** Agents logging their own over WhatsApp or the portal is a later slice.
- **G10. Do project sales count?** Sales orders carry `demand_class` project or retail.
  **Recommend: an agent target counts both** (a sale is a sale), and Project Sales leads stay in
  Project Sales rather than appearing as opportunities here. Say if project orders should be
  excluded or targeted separately.

## 8. Out of scope

Agent self-service logging, commission plan tiers, stored monthly snapshots, quarterly or yearly
grain, a leaderboard, kanban board for opportunities, and the #1168 stock asks log. Each has its
trigger named above; defer items go to `documentation/backlogs/backlog.md` when the owner rules.
