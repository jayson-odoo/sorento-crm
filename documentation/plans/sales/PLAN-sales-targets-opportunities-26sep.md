# PLAN: sales targets, opportunities and the WhatsApp achievement broadcast (#1170)

Status: grilled, round 4 (owner's second Lavish review folded in, PR #1260 comment 06:01Z;
round 4 questions Q1 to Q5 posted on the PR as comment 5843826713). Earlier rounds: round 1 answered by the owner
26 Sep 2026, PR #1260 comment 05:25Z; round 2 questions posted on the PR; round 3 folded in the
owner's first Lavish review, comment 05:35Z, and its questions T1 to T5 are comment 5843719967.
Track: full track for every build lane (new tables, migrations, new permissions, a new module
key, a new portal surface). Nothing built beyond slice 1 of the issue (PR #1177, a sales agent on
a customer). **Build order after round 4: S6 (sales teams), S1, S7 (dealer targets), S2, S3,
S4, S5** (section 6).
Domain: sales. Classification: **MODULE** `sales` (installable; another tenant with a sales team
would turn it on), tables in `public` with normal FKs (targets and opportunities are durable
business records, so by the uninstall test they stay in `public`).
UAC: `sales-targets-opportunities-26sep-acceptance-criteria.md` alongside (the contract; the
journey J1 to J14 lives there and is not repeated here).
Mockup: `mockups/sales-targets.html`. Round 4 redraws it to the owner's second Lavish review:
the Targets landing as a list of teams (1280 and 375), the team form view, the Sales Teams setup
page and team modal, the target form view, the Set target modal with standard dropdowns and a
plain date range, the portal opportunity form with one customer-or-prospect search and product
lines, the Sales updates tab on a contact's record, and the WhatsApp message.
Grill: section 8 of this file. Each of G1 to G10 carries a dated **Owner ruling 26 Sep** line;
the first Lavish review (L1 to L4) carries "Owner ruling 26 Sep (Lavish)" lines; the second
Lavish review (N1 to N13) carries "Owner ruling 26 Sep 06:01 (Lavish)" lines. Round 2 questions
are section 9, round 3 section 10, round 4 section 11.

## 1. In plain words (for the owner)

Three ideas, and how they fit together.

- **A target** is the number a person is expected to reach, for example "Ali: RM 120,000 of
  sales a month, October to March, counting basins and taps only". Odoo's sales target (its
  Commissions app) is a **plan** with a start and end date and a periodicity (monthly, quarterly
  or yearly); inside that window it holds one target figure per period, and each plan says what it
  measures (amount or quantity, sold or invoiced) and on which products or product categories
  ([Odoo 18 Commissions][odoo-comm]). This plan follows that shape (rulings G3 and G4): every
  target sets its own metric, basis and product scope. **Round 4 (Owner ruling 26 Sep 06:01
  (Lavish), N6 and N7):** the validity is a plain date range, a start date and an end date, so a
  week, a month, 2.5 months or a year are all just ranges. There is no fixed quarter and no
  "runs for N months". Splitting a range into smaller periods, each with its own figure, is
  optional and free (every N days, weeks or months), off by default (round 4 Q1).
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
- **A sales team** (Owner ruling 26 Sep (Lavish), L2) is a named group of sales agents, for
  example "North" with Ali and Mei. A team can hold its own targets, set in the same modal, and
  its achievement is the sum of its agents' orders counted by that target's own rules. Odoo also
  keeps a target on the sales team itself (the team's invoicing target mentioned above), typed on
  the team and not derived from its members' targets; this plan does the same (round 3 T3).
  Round 4 (N5) makes teams the **first thing the Targets screen shows**: a list of teams with
  their targets, one line each; clicking a team opens that team's page with its agents and their
  targets, one line each; clicking a target opens the target's own page, which holds every detail.

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

**The existing teams tables (round 3, L4).** `teams` (`app/models/access.py:518-552`) is a
company-scoped team **of CRM users** "for round-robin assignment" (:525), with a `parent_team_id`
hierarchy (:538-542) that carries access: "a member of a parent team can see + act on the work of
all descendant teams" (:532-537), computed by `descendant_team_ids`
(`app/services/user_service.py:2793`) and used for SLA and coverage scope
(`sla_service.py:1392-1404`, `coverage_subscription_service.py:85-98`). `team_members`
(:555-586) links `team_id` to `user_id` FK `users.id` (:561), with round-robin `sort_order` and
`include_in_round_robin` (:562-569) and market segments (:576-580). `agent_teams` (:589-648)
binds AI access agents to a team per team-set code and tier with an SLA policy, and
`agent_team_round_robin_cursors` (:651-667) rotates assignees. Procurement emails a team's members
through `AgentTeam` (`procurement_service.py:4888-4898`). Admin: Users & Access > People > Teams
(`config/menu.config.tsx:690-693`), routes `app/api/v1/user_management/teams.py` (CRUD :15-78,
members :95-166), slugs `user_management.teams.*` (`permission_registry.py:37`), module `base`.
Sales agents are not users (`sales_agent.py:1-17`), so none of these tables can hold one today.

**The sidebar (round 3, L1, L3).** `MENU_SIDEBAR` already has a `SALES` heading
(`config/menu.config.tsx:78`) holding Project Sales (:80, `moduleKey: 'projects'`), Delivery
Orders and Marketing. Sales Agents sits under Users & Access > People (:694-698, permission
`master_data.sales_agents.view`) and again in `MENU_SIDEBAR_COMPACT` (:1561-1565). Its route is
owned by module `product` (`lib/route-module-map.ts:14`, `/master-data-management`; backend
`permission_module_map.py:23` maps `master_data` to `product`). The sidebar filter hides an item
whose own `moduleKey` is off and recurses into children, dropping a group only when every child
is gone (`app/components/layouts/demo1/components/sidebar-menu.tsx:78-86`), so children of one
group may carry different module keys (precedent: `scm` children under `procurement`, :301-331).

**The design system round 4 builds on** (re-read 26 Sep round 4; paths under
`sorento_crm_frontend/`).

- **Standard dropdown (N8, N9).** `SearchableSelect` (`components/common/SearchableSelect.tsx:142`,
  props :42-120, `clearable` :87, default false for required fields :149) and
  `SearchableMultiSelect` (`components/common/SearchableMultiSelect.tsx:86`). CLAUDE.md: "Every
  dropdown is `SearchableSelect`/`SearchableMultiSelect`"; `PRINCIPLES.md` "Design mandates": an
  optional select is `clearable`. Round 3's segmented buttons (metric, counts, applies to, target
  for, how tiers pay, how often) become these.
- **"+N" pill (N4).** `PillOverflow` (`components/common/PillOverflow.tsx:75`, contract :40-73):
  shows as many pills as the cell's measured width fits, folds the rest into one "+N" pill, and
  any pill opens one popover with the whole list; it re-measures when a DataGrid column is
  resized. Used today by the project-sales fulfilment board
  (`app/(protected)/project-sales/fulfilment-planning/components/FulfilmentBoardMatrix.tsx`).
- **The Teams page concept (N2).** Users & Access > Teams: `app/(protected)/user-management/teams/`.
  List page = `PageHeader` + one card (`page.tsx:11-21`) with a search box and **Create team**
  in the card header (`components/team-list.tsx:42-57`), one row per team with its name, a member
  count that opens a member popover, and a link to the team's own page
  (`components/team-tree.tsx:205`, :259-268); create and edit are one dialog
  (`components/team-edit-dialog.tsx:36`); the team's own page lists its members in a
  `PanelDataGrid` titled Members with **Add member** and an empty state
  (`[id]/page.tsx:16-37`, `[id]/components/team-members-list.tsx:174-189`). Sales Teams copies
  this shape (list, one modal, a team page with Members); it does not copy the tree and drag
  nesting, because sales teams have no parent (3.8).
- **The Internal Contacts page (N12).** The sidebar item is labelled **Internal Users**
  (`config/menu.config.tsx:684-688`, page `app/(protected)/user-management/contact-access-agents/page.tsx:12-35`),
  which renders the shared contacts list (`contacts/components/ContactsList.tsx`); a row opens the
  contact's record (`rowHref`, `ContactsList.tsx:185-188`) at
  `app/(protected)/user-management/contacts/[id]/`, whose layout holds the tabs Profile, Access,
  Routing and Chat (`contacts/[id]/layout.tsx:78-107`). The Access tab already stacks per-contact
  settings sections (media access, field reveals, chatbot:
  `contacts/[id]/access/page.tsx:25-50`). That record is the one place a contact's settings
  live today, for internal users and for dealer contacts alike.
- **Product lines with a quantity in the portal (N11).** The complaint form's product table:
  `ComplaintLinesTable` (`app/(auth)/portal/components/SubmissionForm.tsx:2510`), one row per
  product with the portal's `AsyncCombobox` product search (:2570), a quantity input (:2607),
  **Add product** (:2638) and the empty state "No products yet" (:2562).
- **Date range input (N6).** `DateRangePicker` (`components/ui/date-range-picker.tsx:114`, props
  :103-113, emits `{from, to}` as `YYYY-MM-DD` together), already used by report filters and the
  sales orders grid.
- **Where Sales Agents sits today (N1).** Users & Access > People (`config/menu.config.tsx:694-698`)
  and the compact menu's User Management group (:1561-1565). The live menu has no "Master Data"
  group; the owner's note was written against the round 2 mockup, which drew one (commit
  2f5ece4f, line 115). The page's URL starts with `/master-data-management/` (route owned by
  module `product`, `lib/route-module-map.ts:14`), which is the only "master data" left, and it is
  not shown in the menu.

**Nothing to collide with.** No table named target, quota, commission, incentive, opportunity or
broadcast exists. `projects.leads` is the project (tender) pipeline owned by users (section 5).

**Plumbing.** `_crud` (`app/rbac/permission_registry.py:11-18`); slug prefix to module key map
(`app/modules/runtime/permission_module_map.py:17-35`, no `sales` entry); no `sales` module
today; routers mounted with the guard in `app/api/v1/__init__.py`. List-query adapters:
`app/services/list_query_registry.py:93-175`. Alembic single head: `oisl_0001_suggested_links`.

## 3. Design

### 3.1 Targets: header, periods, product scope (ruling G1, G2, G3, G4)

A target is Odoo-shaped: one header saying **who, what, how counted, on which products, and over
which dates**, and one row per period holding the number to hit (one period covering the whole
range unless the optional split is on, round 4 N6 and N7). Four tables, all
`CompanyScopedMixin`, all created in the S1 migration except the tiers (S4).

`sales_targets` (header), `__audit_track__ = True` (a changed target changes a commission, so
edits are exactly what people dispute):

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `target_no` | varchar(20), unique per company | `TGT-000123`, the human id (no UUID in the UI); numbering rule seeded like `seed_lead_numbering_rule` (`project_seed_service.py:644`) |
| `name` | varchar(120) not null | "Ali FY26 H2 basins" |
| `subject_kind` | varchar(16) not null | check `agent` or `dealer`; S6 widens the check to `agent`, `dealer` or `team` (Owner ruling 26 Sep (Lavish), L2). Round 4: S1 creates it as `agent` or `team`, S7 adds `dealer` |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE CASCADE, null | required when `agent` (check) |
| `customer_id` | uuid FK `customers` ON DELETE CASCADE, null | required when `dealer` (check); round 4: added by S7's migration |
| `sales_team_id` | uuid FK `sales_teams` ON DELETE CASCADE, null | **added in S6** (round 4: in S1's migration, since S6 now ships first and has no targets); required when `team`; the check becomes "exactly the one subject column that matches `subject_kind` is set" (3.8) |
| `metric` | varchar(16) not null | check `amount` or `quantity` (G4) |
| `basis` | varchar(16) not null default `ordered` | check `ordered` or `delivered` (G1) |
| `product_scope` | varchar(16) not null default `all` | check `all`, `categories`, `products` (G4) |
| `start_date` | date not null | first day counted, any day (Owner ruling 26 Sep 06:01 (Lavish), N6: "can this just be date range?") |
| `end_date` | date not null | last day counted, inclusive; check `end_date >= start_date` (N6) |
| `split_every` | smallint null | optional breakdown (N7, round 4 Q1): null = one period for the whole range; else 1 to 99 |
| `split_unit` | varchar(8) null | `day`, `week` or `month`; set exactly when `split_every` is set (check) |
| ~~`start_month`, `months`, `periodicity`~~ | | round 3 columns, replaced by the four above before anything was built (N6, N7: "why suddetnly got quarter so hard set one? what if i want month, week, year, 2 months, 2.5 months??") |
| `commission_method` | varchar(16) not null default `none` | check `none`, `marginal`, `retroactive` (G6, S4) |
| `created_by_user_id`, `created_at`, `updated_at` | | |

Nothing about the range is derived or stored beyond these columns; a week, a month, 2.5 months
or a year are all just a start and an end date.

`sales_target_periods` (the Odoo target lines), cascade from the header:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id`, `target_id` | | FK ON DELETE CASCADE |
| `period_start` | date not null | any day (round 4) |
| `period_end` | date not null | inclusive (round 4, to match the header); `period_start <= period_end` (check) |
| `target_value` | numeric(15,2) not null | RM or units, per the header's metric |

Unique `(target_id, period_start)`. The service generates the rows from the header on create
with the single value typed in the modal: with no split, one row from `start_date` to
`end_date`; with a split of every N units, consecutive rows of N days, N weeks (7N days) or N
calendar months starting on `start_date` (a start on the 31st steps to the last day of a
shorter month), the last row cut at `end_date` (so 1 Oct to 15 Dec
split every month gives 1 Oct to 31 Oct, 1 Nov to 30 Nov, 1 Dec to 15 Dec). The short last row
gets the same figure as the others and is editable like any row (round 4 Q1 asks the owner to
confirm). At most 104 rows (two years of weeks), 422 above that. Each row is editable afterwards
(seasonality: a lower December). Changing the dates or the split regenerates the rows and keeps
the value of any period whose start is unchanged.

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

- Input: the period rows to show (every period that contains the chosen month; round 4: the
  period of each target that contains the chosen **date**, default today, because periods are no
  longer month aligned). A CTE lists
  `(period_id, target_id, period_start, period_end, subject_kind, sales_agent_id, customer_id,
  metric, basis, product_scope)`; a second CTE expands category scope rows to their descendant
  category ids.
- Join `sales_order_lines` to `sales_orders` on the sales report predicate (`status !=
  cancelled`, `line_status != cancelled`) and `order_date >= period_start and order_date <
  period_end` (null `order_date` never counts). Round 4: `period_end` is inclusive, so the test
  becomes `order_date between period_start and period_end`.
- Attribution (G2): `agent` matches `sales_orders.sales_agent_id` against the target's agent (see
  round 2 R2 on whether a person's other agent codes also count); `dealer` matches
  `sales_orders.customer_id`, whoever the agent. `demand_class` is never filtered, so an agent's
  project orders count (G10). `team` (S6, Owner ruling 26 Sep (Lavish), L2) matches
  `sales_orders.sales_agent_id` against the team's current members (a third CTE over
  `sales_team_members`), each member widened by R2 exactly as an agent target is; an order has one
  agent and an agent has one team (T2), so a team figure never counts an order twice and always
  equals the sum of the same target evaluated per member.
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
- `pipeline_by_agent(db, *, month)` (S3) returns `{agent_id: (weighted_value, count)}`. Round 4:
  it takes the period bounds instead of a month and counts opportunities whose
  `expected_close_date` falls inside the period (3.4).

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
- Team targets (S6 then S4, round 3 T4): tiers on a team target compute one team figure per
  period, shown as "Team pool" on the team row. It is never split to agents or added to an
  agent's commission; who is paid from it is the owner's decision outside the CRM. **Trigger for
  a split rule:** the owner asks the CRM to divide a team pool among members.

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
| `prospect_name` | varchar(200) null | required when `customer_id` is null (check): a showroom that is not a customer yet. Round 4 (N10): set by the form's "Add as a new prospect" option, never by a toggle (3.5) |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE SET NULL, null | portal: the logging contact's agent; CRM: stamped from the customer, editable |
| `title` | varchar(200) not null | |
| `status_id` | uuid FK `statuses` ON DELETE SET NULL, null | the stage, entity type `sales_opportunity` |
| `outcome` | varchar(8) not null default `open` | `open`, `won`, `lost`; set by the service from the terminal stage's key, the same split `leads.outcome` uses (`projects.py:718`) |
| `expected_amount` | numeric(15,2) not null | RM |
| `expected_close_date` | date not null | round 4: a date, not a month, so pipeline can sit inside any target period (N6, N7); was `expected_close_month` |
| ~~`product_note`~~ | | round 3's free text "200 basins, white"; replaced by product lines (N11: "what's this, products?") |
| ~~`product_category_id`~~ | | round 3's optional interest; the product lines say it better (N11) |
| `lost_reason` | varchar(150) null | a value from lookup set `sales_opportunity_lost_reasons`; required on lost |
| `sales_order_id` | uuid FK `sales_orders` ON DELETE SET NULL, null | optional on won, must be the same customer |
| `source` | varchar(8) not null | `portal` or `crm` |
| `created_by_contact_id` | text FK `respond_contacts` ON DELETE SET NULL, null | set on portal creates |
| `created_by_user_id`, `stage_changed_at`, `created_at`, `updated_at` | | |

`sales_opportunity_lines` (S2, round 4, Owner ruling 26 Sep 06:01 (Lavish), N11), cascade
from the opportunity, `CompanyScopedMixin`:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id`, `opportunity_id` | | FK ON DELETE CASCADE |
| `product_id` | uuid FK `products` ON DELETE RESTRICT, not null | picked with the portal product search |
| `qty` | numeric(12,2) not null | check `qty > 0` |
| `sort_order` | smallint not null default 0 | the order the salesperson entered them |

"What they want" in round 3 meant the products the buyer is interested in. N11 asked "what's
this, products?": yes, so it becomes product lines (product and quantity), optional (zero lines
is allowed, an early lead may not know yet), using the portal's existing product table pattern
(`ComplaintLinesTable`, section 2). The expected amount stays a typed figure and is not priced
from the lines, because dealer prices vary by customer and a price the form guessed would be
read as a quote (round 4 Q3). Why a table: one opportunity names several products with a
quantity each, which a column cannot hold. No unit price column. **Trigger for pricing lines:**
the owner asks the expected amount to be computed from the lines.

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
`sales_agent_id`. Round 4: whose `expected_close_date` falls inside the target period shown. An opportunity sitting on a stage with a null `win_probability` counts 0 and is
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
  (`customers.sales_agent_id`), plus a prospect name when the buyer is not a customer yet (round
  4: offered by the search itself, not a toggle, see below). Company comes from
  the chosen customer, else the agent's company, else the default company.
- **One search, no toggle (Owner ruling 26 Sep 06:01 (Lavish), N10:** "why we need this togle?
  it is or not a customer we can know right?"**).** The form has one field, **Customer or
  prospect**, a searchable select. Typing lists the agent's own customers whose code or name
  matches. When no customer of this company has exactly the typed name (case and spaces
  ignored), the last option reads **Add "Seri Indah Renovation" as a new prospect**; picking it
  sets `prospect_name` and leaves `customer_id` empty. When the exact name belongs to another
  agent's customer, that option is replaced by a disabled line "Seri Indah is another agent's
  customer", so a salesperson cannot log a known customer as a prospect by accident. The
  prospect lives on the opportunity only; no customer row is created, because customers arrive
  from AutoCount (round 4 Q2). A prospect that later becomes a customer is linked when the
  opportunity is Won (`sales_order_id`, S2-7). The same field and rule apply on the CRM
  opportunity modal, without the own-customers limit.
- **Products (N11).** An optional **Products** table under the amount: product search and a
  quantity per row, **Add product**, as in `ComplaintLinesTable` (section 2). Stored in
  `sales_opportunity_lines` (3.4).
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
| `sales_team_id` | uuid FK `sales_teams` ON DELETE CASCADE, null | only with `team` (Owner ruling 26 Sep (Lavish), L2): set = that team; null = every agent, the round 2 meaning of `team` |
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

Unique `(contact_id, follows_kind, coalesce(sales_agent_id, nil), coalesce(customer_id, nil),
coalesce(sales_team_id, nil))` (the last term added by round 3), the coalesce pattern of `uq_sales_agents_company_sales_agent` (`sales_agent.py:128-133`).

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
  A recipient never receives another subject's figures unless it follows `team`. With a
  `sales_team_id` (round 3, L2) the team recipient gets that team's own targets plus one line per
  member agent, and never another team's lines.
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
  with the G6 and G8 defaults above. **Round 4 drops this** (Owner ruling 26 Sep 06:01 (Lavish),
  N13, "what's this"). In plain words, it was one button that created a switched-off recipient
  row for every agent who has a WhatsApp contact and every dealer target's main contact, so the
  owner did not have to add them one by one. With the settings moving onto each contact's own
  record (N12, below), a bulk button across many contacts has no home and is not needed: on a
  contact's Sales updates tab, **Add** already presets "Follows" to the agent linked to that
  contact (`sales_agents.contact_id`), or to the dealer when the contact is that customer's
  primary contact and the dealer has a target. **Trigger to bring a bulk add back:** the owner
  sets up more than twenty contacts in one sitting and asks for it.
- **Where the settings live (Owner ruling 26 Sep 06:01 (Lavish), N12:** "can this be configured
  at Internal Contacts page? so we got 1 page to set all things"**).** No Recipients tab on
  Targets. A contact's record (`/user-management/contacts/[id]`, reached from Internal Users and
  from the contacts list, section 2) gains a fifth tab, **Sales updates**, after Chat, added to
  the tab routes in `contacts/[id]/layout.tsx:78-107` as `/user-management/contacts/[id]/sales-updates`.
  It lists that contact's `sales_target_recipients` rows, one line each (Follows, When, Sees as
  pills with "+N", Enabled, Next send), with **Add**, and per row Edit, Preview, Send now and
  deferred delete. The modal is round 3's recipient modal without the contact field (the page
  already names the contact) and with dropdowns (N8). The tab shows only when the `sales` module
  is on and the viewer holds `sales.targets.view`; editing needs `sales.targets.edit`. The table
  and the API stay as above (`GET /sales/recipients?contact_id=...`), because one contact can
  still follow several things; only the screen moved. The Outline guide for Internal Users says
  where to find it (no explanation text in the UI).

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
  Round 4 (N5, N12) changes the pages: Targets has the tabs **Teams** (the landing), **Agents**
  and **Dealers** (S7); the Recipients tab is gone (the settings move to the contact record,
  3.6); `app/(protected)/sales/teams/` and `[id]` hold the team pages (3.8, 3.9).
- List-query adapter `sales_opportunities`. The Targets grid is one row per target period in the
  chosen month (tens of rows), served unpaged. Round 4 (N3, N4): the API still returns one row
  per target period, and the screen folds each subject's rows into **one line** (3.9).
- **Sales Agents moves into the Sales group (S1, Owner ruling 26 Sep (Lavish), L1; round 4
  moves this to the S6 lane, which now ships first, and Owner ruling 26 Sep 06:01 (Lavish), N1,
  "need to move under Sales, not under Master Data anymore").** The round 4 mockup draws the full
  sidebar with Sales Agents under Sales and nowhere else, pinned N1. The URL stays
  `/master-data-management/sales-agents` (bookmarks and the `product` module's route ownership
  keep working); it is not shown in the menu. **Trigger to move the URL:** the owner asks for
  `/sales/agents`. The Sales
  group sits under the existing `SALES` heading (`menu.config.tsx:78`) and carries **no
  group-level `moduleKey`**; each child carries its own: Targets and Opportunities `'sales'`,
  Sales Teams `'sales'` (S6), Sales Agents `'product'` (the module that owns its route,
  `route-module-map.ts:14`). The filter at `sidebar-menu.tsx:78-86` then keeps Sales Agents
  visible when `sales` is off. Sales Agents keeps its path and permission, and is removed from
  Users & Access > People (`menu.config.tsx:694-698`) and from `MENU_SIDEBAR_COMPACT`
  (:1561-1565) so it appears once. No route, page or permission changes. Order in the group:
  Targets, Opportunities, Sales Teams, Sales Agents.
- **Set target CTA (S1, Owner ruling 26 Sep (Lavish), L3).** The Targets page uses the shared
  `PageHeader` with one primary action, **Set target**, at the top right on every tab and at 375,
  shown to `sales.targets.add`. The month picker moves out of the header into the toolbar under
  the tabs, so the CTA stands alone. From the header the modal opens with "Target for" (Agent,
  Team from S6, Dealer) preset to the open tab's kind (Agent on Recipients) and an empty
  searchable subject select; from a "No target" row it opens with that subject filled in and
  read-only, as round 2 drew it. The Recipients tab keeps Add recipient and Add suggested in its
  own toolbar. Round 4: the Recipients tab and Add suggested are gone (N12, N13); "Target for" is
  a `SearchableSelect` (N8) preset to the open tab's kind (Team on the landing), and the team
  page's own **Set target** presets that team.

### 3.8 Sales teams and team targets (Owner ruling 26 Sep (Lavish), L2 and L4, slice S6)

Two new tables in the `sales` module, both `CompanyScopedMixin`, in `public` (by the uninstall
test they are business records of the module; they drop with it and nothing core points at them).

`sales_teams`:

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `name` | varchar(120) not null | unique per company, case-insensitive (`uq_sales_teams_company_lower_name`) |
| `is_active` | bool not null default true | inactive: no "No target" row, not offered for new targets; existing targets still show |
| `created_at`, `updated_at` | | |

`sales_team_members`, `__audit_track__ = True` (a move changes team figures, so moves are exactly
what people will ask about):

| column | type | note |
| --- | --- | --- |
| `id`, `company_id` | | |
| `sales_team_id` | uuid FK `sales_teams` ON DELETE CASCADE, not null | |
| `sales_agent_id` | uuid FK `sales_agents` ON DELETE CASCADE, not null | |
| `created_at` | | |

Unique `(company_id, sales_agent_id)`: one team per agent per company (round 3 T2). The company
term is there because `sales_agents` rows may be shared across companies (`company_id` NULL,
`sales_agent.py:73`); a shared agent can sit in one team per company.

**Why a member table and not a `sales_team_id` column on `sales_agents`.** One team per agent
would normally be a column ("one preference does not need a table"). But `sales_agents` is the
master data of module `product`, and `sales` is an installable module (header): a core table with
an FK into a module table fails the uninstall test in `PRINCIPLES.md` "Modular architecture".
The unique index gives the same one-team rule. **Why not the existing `teams`:** section 2 and
round 3 T1; in short its members are users, its hierarchy grants access, and its rows feed
round-robin, SLA and escalation pickers.

No hierarchy (no parent team), no team leader, no dated membership. **Triggers:** a parent team
when the owner asks for a region above teams; a leader column when a message or screen needs to
name one; dated membership (`valid_from`, `valid_to`) when the owner moves agents between teams
mid-year and wants past periods to stay with the old team (T2).

**Team targets** reuse `sales_targets` with `subject_kind = 'team'` and `sales_team_id` (3.1), so
periods, scope, basis, metric, duplicate, tiers (S4) and recipients (S5) all work unchanged.
Achievement: 3.2. A team target is typed on its own, never derived from or split into agent
targets (T3). **Trigger for a "sum of agents' targets" check column:** the owner finds team and
agent targets drifting apart and asks to see both side by side.

**Service and routes (S6).** `app/services/sales/team_service.py`: create, rename, activate,
set members (moving an agent out of their old team in the same transaction, returning who moved
from where), delete. Routes `app/api/v1/sales/teams.py`: `GET/POST /sales/teams`,
`GET/PATCH/DELETE /sales/teams/{id}`, `PUT /sales/teams/{id}/members`. Targets list takes
`subject=team` and `sales_team_id` (filter the Agents tab by team). Permissions
`_crud("sales", "teams", "Sales Teams")`, grant sweep to admin and superadmin in the S6
migration. FE: `salesTeamService.ts`, hooks on the shared factories, pages
`app/(protected)/sales/teams/` and `[id]`, Teams tab on Targets, team option in the Set target
modal.

**The Sales Teams page, modelled on Users & Access > Teams (Owner ruling 26 Sep 06:01
(Lavish), N2:** "we should have a team view to configure the team, cna refer to how we built our
Teams page, can use similar concept"**).** Same concept, sales agents instead of users:

| Teams page (section 2) | Sales Teams |
| --- | --- |
| `PageHeader` "Teams", one card with a search box and **Create team** (`team-list.tsx:42-57`) | `PageHeader` "Sales teams" with **Add team** as its one primary action (the header CTA rule of L3), search in the card toolbar |
| one row per team: name, member count with a member popover, link to the team page (`team-tree.tsx:205`, :259-268) | one row per team, **one line**: name, agents as pills with "+N" (`PillOverflow`), Active badge, targets now (a count); the whole row opens the team page (`rowHref`) |
| one create and edit dialog (`team-edit-dialog.tsx:36`) | one modal: Name, Agents (`SearchableMultiSelect` of active agents, each labelled with the team they are in now), Active |
| team page: Members `PanelDataGrid` with **Add member** and an empty state (`team-members-list.tsx:174-189`) | team page (3.9): Targets section (from S1) and Agents section with **Add agents**, each with an empty state and a next-step button |
| tree nesting by drag (`team-tree.tsx`) | not copied: sales teams have no parent (triggers above) |

The list is a DataGrid under the listing rules (fixed layout, resizable columns) rather than the
Teams tree, because there is no tree to draw.

### 3.9 Screens after round 4: teams first, one line per row, form views (N3, N4, N5)

Owner ruling 26 Sep 06:01 (Lavish): N3 "too many information"; N4 "i want to keep each row as 1
line, if got more need to use +x pill, the details can be viewed if we go inside"; N5 "i don't
like this view, too many cascading is not so good, i want to see a list of teams first and the
targtes, then only click inside the team to see a list of sale agent, and their target, also
need to provide mockup of form view of target, and also teams".

**One line per row, everywhere in this feature.** A row never wraps and never carries a second
grey line. What round 3 put on two lines moves as follows:

- the target number, name and "Oct 2026 to Mar 2027, monthly" line leave the list; the list names
  the target by its name only (truncated, with the full name in `title`), and the target number,
  dates and split are on the target's own page;
- the Measures chips (Amount, Ordered, All products) become one `PillOverflow` cell: the first
  pill is the metric, the rest fold into "+N"; any pill opens the popover with all three;
- a subject (team or agent) with more than one target active on the date shows **one row**: the
  numeric cells (Target, Achieved, %, Pipeline, Commission or Team pool) are the **first**
  target's, and the Targets cell is a `PillOverflow` of the subject's target names with "+N";
  its popover lists each target on one line with its %, and each opens the target's page. The
  first target is the amount target before quantity ones, then the one ending soonest, then the
  lowest target number, so the order never changes between visits;
- "incl. bonus 500" leaves the Commission cell; the breakdown is on the target's page (S4-9's
  popover shows it too).

**Targets landing = list of teams (N5).** Sales > Targets opens on the **Teams** tab: one line
per active team (Team, Agents as pills with "+N", Targets pills, Target, Achieved, %, Pipeline,
Team pool, row menu). Under the teams, a **No team** line counts the active agents in no team
and opens the Agents tab filtered to "No team"; under that, the **Unassigned** line totals orders
with no agent (S1-14). A team with no target on the date shows "No target" and **Set target**.
The toolbar holds an **Active on** date (default today; round 4 replaces the month picker,
because periods are no longer months) and a search. Clicking a team opens its team page. There
is no grouped, cascading agent list any more.

**Agents tab** stays, flat: one line per active agent (Agent, Team, Targets pills, the numeric
cells), with a clearable Team filter that includes "No team". It is where an agent with no team
is reached, and it is the list a sales admin scans to find one agent. **Dealers tab** (S7): one
line per dealer with a target, same cells.

**Team form view** (`/sales/teams/[id]`, N5 "mockup of form view of ... teams"). Header: the
team name, Active badge and agent count in the meta strip; actions **Set target** (primary,
presets this team), Edit, and a row menu with Delete (deferred); `RecordNavigation` for the
previous and next team. Two sections, in this order, both always rendered:

1. **Team targets**: one line per team target active on the date (name, Measures pills, dates
   as "to 31 Mar 2027", Target, Achieved, %, Team pool); empty state "No team target" with Set
   target.
2. **Agents**: one line per member agent (Agent, Targets pills, Target, Achieved, %, Pipeline,
   Commission); a row opens the agent's first target's page, and a pill opens that target's
   page; an agent with no target shows "No target" and Set target (presets that agent); empty
   state "No agents in this team" with **Add agents**.

View and edit are the same layout: Edit swaps the name for an input in place and gives the
Agents section an **Add agents** multi-select and a remove control per row; nothing moves.

**Target form view** (`/sales/targets/[id]`, N5 "mockup of form view of target"). Header: target
number and name, the subject (a link to the agent, team or dealer), and Created and Updated in
the meta strip; actions Edit, Duplicate, and a row menu with Delete (deferred);
`RecordNavigation` across the list the user came from. Sections in this order, all rendered, the
same layout in view and edit:

1. **Target**: Target for, Who, Name.
2. **What counts**: Metric, Counts (ordered or delivered), Applies to, and the category or
   product list when not all.
3. **Dates**: Start date, End date, Split (Off, or every N days, weeks or months).
4. **Periods**: one line per period (dates, Target, Achieved, %, Commission), the period
   containing today marked; the figure is edited in place (S1-4). With the split off this is one
   line.
5. **Commission** (S4): How tiers pay, and the tier table; empty state "No commission" with Add
   tier.

The Set target modal is the create form for the same fields in the same order (sections 1 to 3,
the target figure, then 5); the periods exist only after save.

## 4. Journey value order

The owner sees value at the end of each lane, in this order: targets and live achievement (S1),
salespeople logging opportunities in the portal (S2), pipeline beside the target (S3), commission
(S4), the WhatsApp broadcast (S5). Each slice is one lane, one branch, one PR, so S1 ships before
S2 is started and nothing waits on a bundle.

Round 3 (Owner ruling 26 Sep (Lavish), L2) adds **S6, sales teams and team targets, built second**,
between S1 and S2. Slice ids are kept stable so no AC is renumbered; the build order is S1, S6,
S2, S3, S4, S5. Why not inside S1: S1's first value is "each agent against a live figure", which
stands without teams, and S1 is already the largest lane (three tables, the achievement query,
the modal, the detail page). Teams add two tables, a CRUD page and a third subject kind; folded
in, they would delay the first screen the owner can use. Why straight after S1 and before
opportunities: it extends the S1 code while it is fresh, and the owner asked for it on the first
screen they reviewed. Round 3 T5 asks the owner to confirm. The Lavish points L1 (menu) and L3
(CTA) are a few lines each and ride in S1.

**Round 4 re-slice (Owner ruling 26 Sep 06:01 (Lavish), N5).** The Targets screen now opens on
a list of teams, so teams must exist before or with the first targets screen. Round 3's order
(S1 then S6) would ship a landing with nothing to list. New order, each still one lane:

1. **S6. Sales teams** (first, and thin): the `sales` module, `sales_teams` and
   `sales_team_members`, the Sales Teams page and modal, the team page with its Agents section,
   and the Sales menu with Sales Agents moved into it (L1, N1). No targets yet. Value: the owner
   puts every agent in a team, which the targets screen then reads.
2. **S1. Targets for teams and agents**: date range targets with the optional split, the
   teams-first landing, the Agents tab, the team page's Team targets section and agents' targets,
   the target form view, the Set target modal and header CTA. The team-target ACs of S6 (S6-4 to
   S6-7, S6-10) build here, because the landing cannot show a team without its target.
3. **S7. Dealer targets** (new, thin): the `dealer` subject and the Dealers tab, split out of S1
   so S1 stays a lane that ships, not a bundle. Dealer targets stand alone (no team, no agent).
4. **S2** opportunities in the portal, **S3** pipeline, **S4** commission, **S5** per-contact
   broadcast on the contact record, as before.

Slice ids stay stable (no AC is renumbered); which lane builds an AC is stated where it moved.
Round 4 Q5 asks the owner to confirm.

## 5. Considered and not chosen

- **Reuse `projects.leads` for opportunities.** Project leads belong to the Project Sales module
  (`projects` schema), are owned by a user (`owner_user_id`), and lead to project quotations.
  Dealer opportunities are owned by a sales agent who has no login. Kept apart; only the stage
  **table** is shared, which is what G5 asked for.
- **Reuse the existing `teams` table for sales teams** (round 3, L4, T1). Its members are CRM
  users (`team_members.user_id` FK `users.id`, `access.py:561`) and sales agents are not users;
  its `parent_team_id` tree grants visibility and action over descendant teams' work
  (`access.py:532-537`, `descendant_team_ids` in SLA and coverage scope); and its rows are what
  round-robin, SLA tiers and escalation routing pick from (`agent_teams`, `access.py:589-648`;
  `procurement_service.py:4888-4898`). Reusing it needs a second, agent-typed member table anyway,
  and every sales team would then show in the Teams admin page and in Team Assignments and SLA
  pickers, where choosing one routes work to a team nobody can log in to. It is also a `base`
  table, while sales teams must drop with the `sales` module. Not chosen.
- **A `sales_team_id` column on `sales_agents`.** See 3.8: a core table pointing into a module.
- **Teams inside S1.** See section 4 and T5.
- **Fixed stage constant.** Round 1's recommendation; ruled out by G5.
- **A shared commission plan table.** See 3.3 and its trigger.
- **Stored achievement.** See 3.1 and its trigger.
- **One global broadcast schedule in Scheduled Tasks.** Round 1's recommendation; ruled out by G7
  (per contact).
- **Columns on `respond_contacts` for broadcast preferences.** See 3.6.
- **A cascading targets list grouped by agent** (round 3's Agents view). Ruled out by N5; the
  landing is a list of teams and each row is one line (3.9).
- **Segmented buttons for metric, counts, scope, target for and tier method.** Ruled out by N8
  and N9; `SearchableSelect` is the standard dropdown (section 2).
- **"Runs for N months" and "one per quarter".** Ruled out by N6 and N7; a date range with an
  optional free split (3.1).
- **A "Not a customer yet" toggle.** Ruled out by N10; the search itself offers the prospect
  (3.5).
- **Creating a customer record for a prospect.** Customers come from AutoCount; a CRM-made
  customer would have no AutoCount debtor behind it (round 4 Q2).
- **A free text "What they want".** Replaced by product lines (N11, 3.4).
- **A Recipients tab on Targets, and Add suggested.** Moved to the contact record and dropped
  (N12, N13, 3.6).
- **One list for teams (setup and figures together).** Round 4 Q4: recommend two entry points,
  Sales Teams for who is in which team and Targets for how each team is doing, both opening the
  same team page.
- **Opportunities over WhatsApp chat.** The portal covers G9; a chatbot intake is a later lane.
  **Trigger:** salespeople report the portal form is too slow in the field.
- **A "My targets" page in the portal.** Not asked; the WhatsApp message carries the figures.
  **Trigger:** the owner asks for salespeople to check progress between messages.

## 6. Slices and lanes

Every slice is its own lane (one branch, one PR), in this order, and runs Phase 1 (FE against a
mock service, all states tuned, browser checked) then Phase 2 (tester writes the UAC tests red,
the one coder makes them green, mock swapped at the service boundary) then Phase 3 once. Track:
full for all seven (each has a migration or a new external surface).

**Build order after round 3: S1, S6, S2, S3, S4, S5** (section 4). The sections below keep their
round 2 order; S6 is written after S5 so no id moves.

**Build order after round 4: S6, S1, S7, S2, S3, S4, S5** (section 4, round 4 Q5). S7 is
written after S6. Where an AC now builds in a different lane than its id says, the slice below
names it.

### S1. Flexible targets with live achievement in the CRM (UAC S1-1 to S1-18)

Round 3 adds to this lane (Owner ruling 26 Sep (Lavish), L1 and L3), no backend change: the Sales
group with Sales Agents moved into it, per-child `moduleKey` (3.7, S1-17); the header **Set
target** CTA, the month picker moved to the toolbar, and the modal's "Target for" subject select
when opened from the header (3.7, S1-18). The S1 migration's `subject_kind` check stays `agent`
or `dealer`; S6 widens it.

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
- **Round 4 (Owner ruling 26 Sep 06:01 (Lavish), N3 to N8), S1 is now built second, after S6:**
  - moves out: the Sales menu move (S1-17) to S6, which ships first; the dealer subject and
    Dealers tab (S1-11, the dealer half of S1-15 and S1-16) to S7;
  - moves in: team targets (S6-4 to S6-7, S6-10), because the landing lists teams;
  - changes: validity is `start_date`, `end_date` and the optional `split_every` and
    `split_unit` (3.1, S1-19, S1-20); the list takes `on=<date>` instead of `month`; the
    landing is the Teams tab, one line per row (3.9, S1-21, S1-22); the team page gains its
    Team targets section and its agents' targets; the target form view (S1-23); every picker is
    `SearchableSelect` (S1-24); the modal takes a date range (S1-25);
  - the S1 migration's `subject_kind` check is `agent` or `team` (S7 adds `dealer`), and it
    adds `sales_targets.sales_team_id` directly, since `sales_teams` exists from S6.
  - Tests add: range boundaries (first and last day counted, the day after not), split golden
    table (2.5 months by month, 10 weeks by 2 weeks, 31 Jan start by month), the 104 period cap,
    one-line rendering (no row taller than one line at 1280), the first-target ordering rule.

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
- Round 4 (N10, N11): the migration adds `sales_opportunity_lines` and uses
  `expected_close_date`; the customer lookup returns own matches plus the prospect option or the
  "another agent's customer" line (S2-15); the form has the Products table (S2-16). Tests add:
  exact-name match suppresses the prospect option, case and spaces ignored, another agent's
  customer blocked, lines with qty 0 rejected, zero lines allowed.
- DoD: as S1, plus security-reviewer (external ingest surface).

### S3. Pipeline beside the target (UAC S3-1 to S3-4)

- Backend seam: `pipeline_by_agent` joined into the targets list.
- Frontend seam: Pipeline column and KPI, linking to Opportunities filtered to that agent and
  month.
- Tests: weighted golden set with configured probabilities; terminal stages excluded; a null
  probability counts 0 and is flagged; no opportunity ever in achievement.
- Round 3 (L2, S3-5): team rows carry the sum of their current members' pipeline.
- Round 4 (N6, N7, S3-6): pipeline counts `expected_close_date` inside the period shown, not a
  month.
- DoD: as S1.

### S4. Commission tiers (UAC S4-1 to S4-9)

- Backend seam: migration `sales_target_commission_tiers`; `commission_service`; tiers in the
  target create, update and duplicate payloads; `commission_earned`, `bonus_earned` and
  `commission_breakdown` on each period row.
- Frontend seam: Commission section in the modal and detail (method, tier rows), Commission
  column with a breakdown popover.
- Tests: golden numbers for flat, marginal, retroactive, quantity RM per unit, bonuses at 100%,
  the 99.99% boundary, rounding; vitest for the tier editor.
- Round 3 (L2, T4, S4-10): tiers on a team target give a "Team pool" figure on the team row,
  never split to agents.
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
- Round 3 (L2, S5-14): `sales_team_id` on recipients; a team recipient follows one team or all
  agents.
- Round 4 (N12, N13, S5-15, S5-16): the frontend seam is the **Sales updates** tab on the contact
  record (`contacts/[id]/layout.tsx:78-107` plus a `sales-updates` route), not a Targets tab;
  Add suggested is dropped and Add presets Follows from the contact's link; every picker in the
  recipient modal is `SearchableSelect` (N8). The backend seam is unchanged except a
  `contact_id` filter on the list, whose response also carries `suggested_follow` (the agent
  linked to the contact, else the dealer it is primary contact for, else null), so no new
  endpoint. The agent-browser run starts from Internal
  Users.
- DoD: the Meta-approved template is mapped on prod before any recipient is enabled; the owner
  enables their own row after one Send now looks right; security-reviewer (outbound business
  figures to external contacts).

### S6. Sales teams and team targets, built second (UAC S6-1 to S6-11)

**Round 4 (Owner ruling 26 Sep 06:01 (Lavish), N1, N2, N5): S6 is built FIRST and is teams
only.** Its lane now carries the `sales` module bootstrap, the permission map entry and
`sales.teams.*` (moved from S1's backend seam), `sales_teams` and `sales_team_members`, the
Sales Teams page modelled on the Teams page (3.8, S6-12), the team page with its Agents section
(3.9, S6-13; the Team targets section arrives with S1), and the Sales menu with Sales Agents
moved in (S1-17, N1). Its team-target ACs (S6-4 to S6-7, S6-10) build in S1. The migration does
not touch `sales_targets`, which S1 creates. DoD: every active agent can be placed in a team on
the dev DB, 1280 and 375, security-reviewer (new slugs and company-scoped tables). The bullets
below are round 3's and are read with this paragraph.

Owner ruling 26 Sep (Lavish), L2 and L4; written to round 3 T1 to T5.

- Backend seam: migration (`sales_teams`, `sales_team_members`, `sales_targets.sales_team_id`,
  the `subject_kind` check widened to `team` and the subject check rewritten, grant sweep for
  `sales.teams.*`); models in `app/models/sales_target.py`; `team_service`; the team CTE in
  `achievement_service`; `subject=team` and `sales_team_id` on the targets list; team routes.
- Frontend seam: Sales > Sales Teams (DataGrid, team modal with a searchable agent multi-select
  labelled with current team, team detail with Members and Targets sections, empty states,
  `RecordNavigation`, deferred delete); Targets page Teams tab and Agents tab Team filter; "Team"
  in the modal's Target for.
- Tests: team golden set (sum of members, non-member excluded, quantity delivered with category
  scope), equality with the per-agent sum, a move changes past periods (current membership), one
  team per agent per company, name uniqueness, inactive team rules, delete cascade leaves agents,
  403 per route, company scope; vitest for the team modal and the subject switch; agent-browser
  run.
- DoD: on the dev DB (prod copy), a team of two real agents shows the sum of their S1 rows for
  September; 375 and 1280. security-reviewer joins, because the diff adds RBAC slugs and
  company-scoped tables (CLAUDE.md "Development methodology" names both).

### S7. Dealer targets, built third (round 4, UAC S1-11, S7-1 to S7-3)

Split out of S1 by round 4 (section 4) so S1 stays thin. Owner ruling 26 Sep 06:01 (Lavish),
N5 (teams first) is why S1 grew; dealers are the part of S1 that stands without teams.

- Backend seam: migration widening `subject_kind` to `agent`, `team` or `dealer` and adding
  `sales_targets.customer_id`; `subject=dealer` on the list; the dealer branch of the
  achievement query (already specified in 3.2).
- Frontend seam: the Dealers tab (one line per dealer with a target, same cells as Agents), and
  "Dealer" in the modal's Target for with a searchable dealer select.
- Tests: S1-11 and S7-1 to S7-3; vitest for the subject switch; agent-browser run.
- DoD: as S1.

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
- **Team figures move with the agent** (round 3 T2). With current membership, moving an agent
  rewrites the team's past periods too. The audit trail on `sales_team_members` shows when; dated
  membership is the named trigger in 3.8.
- **Prospect duplicates** (round 4, N10). A prospect is free text, so "Seri Indah" and "Seri
  Indah Reno" become two prospects. The exact-name check stops the common case only; the CRM
  list can be sorted by prospect name to spot the rest. **Trigger for a prospects list:** the
  owner finds the same prospect logged on three or more opportunities.
- **One line hides the second target** (round 4, N4). A subject's second target is behind a
  "+N" pill, so a low % on it is not visible in the list. The first-target rule (3.9) puts the
  amount target first; the pill popover shows every target's %.
- **Two things called "Teams".** Users & Access > Teams (CRM users) and Sales > Sales Teams (sales
  agents). The label "Sales Teams" and the separate menu group keep them apart; the guide says so.

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

### Owner's Lavish review of the mockup (PR #1260 comment, 26 Sep 2026 05:35Z)

Verbatim and binding. Written after round 2 (commit 2f5ece4f), folded in by round 3.

- **L1. On the Sales Agents nav item.**
  **Owner ruling 26 Sep (Lavish):** "put sales agents under sales also". Built as Sales Agents
  moving into the Sales group, with its own `moduleKey`, path and permission unchanged (3.7,
  S1-17), in S1.
- **L2. On "Team target RM 540,000".**
  **Owner ruling 26 Sep (Lavish):** "need to be able to set multiple sales teams and put the sales
  agents under the team and be able to set team target". Built as `sales_teams`,
  `sales_team_members` and `subject_kind = 'team'` on `sales_targets`; team achievement is the sum
  of its agents' orders under the target's own metric, basis and scope (3.2, 3.8, S6-1 to S6-11),
  in its own slice S6, built second.
- **L3. On "3. SET TARGET MODAL".**
  **Owner ruling 26 Sep (Lavish):** "there should be a CTA Set Target at the top right". Built as
  the one primary action in the Targets page header, every tab, 1280 and 375, opening the modal
  with a subject select (3.7, S1-18), in S1.
- **L4. On "Team target RM 540,000".**
  **Owner ruling 26 Sep (Lavish):** "not sure if we should reuse our teams table in our system".
  Answered as round 3 question T1 (section 10): recommend a new `sales_teams` table, reasons in
  section 2 and section 5.

### Owner's second Lavish review, of the round 2 mockup (PR #1260 comment, 26 Sep 2026 06:01Z)

Verbatim and binding. Written against the round 2 page, before round 3 landed; folded in by
round 4. Each note keeps the owner's words and says how it is built.

- **N1. On "Sales Agents".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "this havne't move?, need to move under Sales, not
  under Master Data anymore". Round 3 already moved it (L1); round 4 makes the mockup show it
  (the full sidebar, Sales Agents under Sales only, pin N1) and moves the menu change into S6,
  which ships first (3.7, S1-17).
- **N2. On "SALES".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "we should have a team view to configure the team, cna
  refer to how we built our Teams page, can use similar concept, that is good". Built as the
  Sales Teams page, list plus one modal plus a team page, mapped row by row onto Users & Access >
  Teams (3.8), on `sales_teams` from T1 (S6-12).
- **N3. On "TGT-000014 FY26 H2 all products Oct 2026 to Mar 2027, monthly" (Target cell).**
  **Owner ruling 26 Sep 06:01 (Lavish):** "too many information". The list shows the target's
  name only; number, dates and split live on the target's page (3.9, S1-21).
- **N4. On the same row's Measures cell.**
  **Owner ruling 26 Sep 06:01 (Lavish):** "i want to keep each row as 1 line, if got more need to
  use +x pill, the details can be viewed if we go inside". Every row is one line; extra items
  fold into a "+N" pill (`PillOverflow`); details only on the target's page (3.9, S1-21).
- **N5. On the cascading Agents view.**
  **Owner ruling 26 Sep 06:01 (Lavish):** "i don't like this view, too many cascading is not so
  good, i want to see a list of teams first and the targtes, then only click inside the team to
  see a list of sale agent, and their target, also need to provide mockup of form view of target,
  and also teams". Built as the Teams tab landing, the team page with its agents and their
  targets, and the target page (3.9, S1-22, S1-23, S6-13); mockups of both form views. Teams
  now ship first (S6) and team targets with the first targets screen (S1) (section 4).
- **N6. On "October 2026 / Runs for (months)".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "can this just be date range?". Yes: `start_date` and
  `end_date` (3.1, S1-19, S1-25).
- **N7. On "One per quarter".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "what's this? why suddetnly got quarter so hard set
  one? what if i want month, week, year, 2 months, 2.5 months??". The quarter and the fixed
  choices are gone; any period is a range. A breakdown inside a range is optional and free,
  every N days, weeks or months, off by default (3.1), asked as round 4 Q1.
- **N8. On "Metric Amount (RM) Quantity / Counts Ordered Delivered".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "use dropdown for these, use our standard dropdown
  component". `SearchableSelect` (section 2) for Metric, Counts, Applies to, Target for, Split
  unit, and the recipient modal's Follows and How often (S1-24).
- **N9. On "None / Higher rate above each threshold only / Highest rate on everything".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "use dropdown for this, our standard dropdwon
  component". How tiers pay is a `SearchableSelect` (S4-11).
- **N10. On "Customer: Search your customers / Not a customer yet".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "why we need this togle? it is or not a customer we
  can know right?". The toggle is gone; one Customer or prospect search infers it and offers
  "Add ... as a new prospect" when no customer matches (3.5, S2-15), asked as round 4 Q2 for
  where the prospect is kept.
- **N11. On "What they want (optional) 200 basins, white".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "what's this, products?". Yes, products: optional
  product lines with a quantity, with the portal's product search (3.4, 3.5, S2-16); the
  expected amount stays typed (round 4 Q3).
- **N12. On the Recipients grid (Follows, When, Sees, Enabled, Next send).**
  **Owner ruling 26 Sep 06:01 (Lavish):** "can this be configured at Internal Contacts page? so
  we got 1 page to set all things". Yes: a Sales updates tab on the contact's record, reached
  from Internal Users; the Recipients tab is removed (3.6, S5-15).
- **N13. On "Add suggested".**
  **Owner ruling 26 Sep 06:01 (Lavish):** "what's this". It created a switched-off recipient row
  for every agent with a WhatsApp contact and every dealer target's main contact in one click.
  Dropped: with settings on each contact's record it has no home, and Add on that record presets
  Follows instead (3.6, S5-16).

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

None of the Lavish points changes R1 to R5; they stand as written. R2 (person label) also widens
each member agent of a team target (3.2).

## 10. Round 3 questions (posted on PR #1260, comment 5843719967)

- **T1. Reuse the existing `teams` table, or a new sales team table?** (Owner's L4.) Recommend: a
  new `sales_teams` with `sales_team_members`. `teams` holds CRM users
  (`team_members.user_id`, `access.py:561`) and sales agents are not users; its parent tree grants
  access to descendant teams' work (`access.py:532-537`); its rows feed round-robin, SLA and
  escalation routing (`agent_teams`, `access.py:589-648`), so a sales team would show in those
  pickers; and it is a `base` table while sales teams belong to the installable `sales` module.
  Cost of the new table: two small tables and one page.
- **T2. How agents sit in teams.** Recommend: one team per agent (per company), and a team's
  figures follow its current members, so moving an agent also moves their past orders to the new
  team. Dated membership is added when a mid-year move needs history kept with the old team.
- **T3. Team target vs the agents' targets.** Recommend: typed on its own, like Odoo's team
  target, never split into or summed from the agents' targets; team achievement is always the sum
  of the agents' orders.
- **T4. Commission on a team target.** Recommend: tiers work as on an agent target and give one
  "Team pool" figure per period on the team row; the CRM does not split it among agents.
- **T5. When teams ship.** Recommend: their own lane S6, built right after S1 and before
  opportunities, so S1 (each agent against a live figure) is not delayed; the Sales menu move and
  the Set target button ride in S1.

## 11. Round 4 questions (posted on PR #1260, comment 5843826713)

- **Q1. A breakdown inside a date range (N7).** Recommend: optional and off by default; when on,
  "every N days, weeks or months" with any N, each period with its own editable figure; the
  short last period (2.5 months split by month) gets the same figure as the others and is
  edited by hand if needed. Alternative: no split at all; a monthly figure is then one target
  per month (Duplicate makes the next one).
- **Q2. Where a prospect is kept (N10).** Recommend: on the opportunity only (`prospect_name`),
  with no customer record made in the CRM, because customers come from AutoCount; when the deal
  is won and AutoCount sends the debtor, the won opportunity is linked to that customer's sales
  order. Alternative: a prospects list of its own, reused across opportunities.
- **Q3. Products and the expected amount (N11).** Recommend: product lines are product and
  quantity only, and the expected amount stays typed by the salesperson; it is not priced from
  the lines, because dealer prices differ by customer and a computed figure would read as a
  quote. Alternative: price each line from the price list and add them up.
- **Q4. Two lists of teams (N2, N5).** Recommend: keep both, Sales > Sales Teams for who is in
  which team (setup, like Users & Access > Teams) and Sales > Targets for how each team is doing,
  both opening the same team page. Alternative: one list only, the Targets landing, with Add team
  beside Set target.
- **Q5. Build order (N5).** Recommend: S6 sales teams first (teams only, thin), then S1 targets
  for teams and agents with the teams-first landing and both form views, then a new thin S7 for
  dealer targets, then S2, S3, S4, S5. Alternative: keep dealer targets inside S1 (one lane
  fewer, a larger first targets lane).

## 12. Out of scope

A leaderboard, a kanban board for opportunities, opportunities over WhatsApp chat, a portal "My
targets" page, stored snapshots, a shared commission plan table, a dimension engine, and the #1168
stock asks log. Round 3 adds: a team hierarchy, a team leader, dated team membership, splitting a
team pool among agents, and a "sum of agents' targets" check column. Round 4 adds: a bulk
"Add suggested" for recipients, pricing opportunity lines, a prospects list, and moving the
Sales Agents URL. Each has its trigger named above; deferred items go to
`documentation/backlogs/backlog.md` once round 4 is answered.
