# PLAN: sales targets, opportunities and the WhatsApp achievement broadcast (#1170)

Status: **building.** Wave 1, S6, is on PR #1260 (wave 1: the `sales` module and schema, Sales Teams with dated
membership, the Sales menu with Sales Agents moved in; section 15). S6 accepted on the owner's
hand test (26 Sep ~13:25Z); fix lane round 2 on the same PR adds the team leader (W1) and lists
a returning agent once (W2), section 15. Track: full. Wave 2: S2
(opportunities) building on its own lane beside S1, contract in section 16. Ready to build since the owner accepted V1 to V3 as recommended (Owner ruling
26 Sep ~09:05, section 14).
Earlier status: grilled, round 5 (the owner's answers to R1 to R5 and T1 to T5, PR #1260 comment
5843775673 of 26 Sep 06:09Z, folded in as "Owner ruling 26 Sep 06:09" lines; section 13 says how
each was applied; round 5 questions V1 to V3 posted on the PR as the "Round 5" comment,
5844053739). **Every slice is
in scope now; nothing is deferred or backlogged** (Owner ruling 26 Sep 06:09, T5: "the point is
we need to do it now and not backlog or defer"). **Build order after round 5: S6, then S1 and S2
in parallel, then S7, S4, S3 and S5** (section 6, "Lanes after round 5").
Round 4 (owner's second Lavish review folded in, PR #1260 comment 06:01Z;
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
**Round 5 (owner question 26 Sep 06:09, "are we doing this in a new schema and module called
sales?"): yes to both, recommended.** A new module keyed `sales`, and its tables in a new
Postgres schema `sales` named after the module key, without the `sales_` prefix
(`sales.targets`, `sales.teams`, ...), on the ADR-0011 precedent the owner set for Project Sales
(ownership visible in `\dn`; purge is a row-level delete, `DROP SCHEMA` is never issued). Full
reasoning and the table name map: 3.7, "Module and schema (round 5)". Where this plan still
writes `sales_targets` and the like, read the mapped name.
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
| `commission_method` | varchar(16) not null default `none` | check `none`, `marginal`, `retroactive` (G6, S4). Owner ruling 26 Sep 06:09 (R5): `marginal` is the default the modal offers once tiers are added; `retroactive` ("Highest rate on everything") stays selectable on any target and is built in S4, not deferred (T5) |
| `parent_target_id` | uuid FK `sales_targets` ON DELETE CASCADE, null | round 5 (Owner ruling 26 Sep 06:09, T3): an agent target that is one line of a team target; the team figure is the sum of these (3.8) |
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
  Round 5 (Owner ruling 26 Sep 06:09, T2): the team CTE matches membership **on the order's
  date** (`valid_from` / `valid_to`, 3.8), not current membership; an order still counts for at
  most one team. With no move inside the period, the team figure still equals the per-member sum.
  Owner ruling 26 Sep 06:09 (R2): accepted as recommended. An agent target, and each member of a
  team, counts every `sales_agents` row with the same non-empty `person_label` in the company
  (plus shared rows), else the one code. For a team, the widening applies inside the member's
  membership window, so SEAN III's orders count for Sean's team only while Sean is in it.
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
  Round 5 (Owner ruling 26 Sep 06:09, R3: "we will have DO integreation as soon as next Monday
  so by that time we will be able to know"): delivered counts **by DO date** once DO data
  exists. Design below ("Delivered, by DO date"); the table above still gives the value per
  unit, and only the date that buckets it changes.

**Delivered, by DO date (round 5, R3).** Measured 26 Sep: delivery orders already exist in core
as `orders` (the DO header, `app/models/order.py:286-358`; `order_date` is the DO date, indexed
:350; `is_cancelled`) and `order_lines` ("Delivery order detail line", :360-405; `order_id` :368,
`product_id`, `quantity` :381), permission `order_management.orders.*` labelled Delivery Orders
(`permission_registry.py:92-97`), menu Sales > Delivery Orders (`menu.config.tsx:141-161`). They
are filled by Excel upload only (`import_tasks.py:2698`), and **no column links a DO line to a
sales order line** (no `sales_order_line_id`, no SO number). The archived AutoCount plan already
mapped AutoCount DOs onto these two tables
(`documentation/plans/_archive/autocount/PLAN-autocount-integration.md:184-191`, phase E).

- **What S1 needs from the DO integration (the seam).** One nullable column,
  `order_lines.sales_order_line_id` uuid FK `sales_order_lines` ON DELETE SET NULL, indexed,
  filled from AutoCount's DO line "transferred from" reference (the SO line the DO delivers).
  Nothing else: the DO date is `orders.order_date`, the quantity `order_lines.quantity`, and a
  cancelled DO is `orders.is_cancelled`. The Monday DO lane owns that column and its ingest;
  this plan does not build DO ingest. If that lane lands DOs in a new table instead, only one
  CTE changes (below). Round 5 question V2 asks the owner to confirm the column.
- **The seam in code.** `achievement_service` reads delivered quantities only through one CTE,
  `delivered_by_date(period_start, period_end)`, returning `(sales_order_line_id, qty)` rows.
  Every delivered figure (agent, team, dealer, amount, quantity) goes through it.
- **The rule, one expression, no switch.** For each sales order line in scope:
  - **by DO:** the sum of linked, non-cancelled DO line quantities whose DO date is inside the
    period;
  - **plus the residual:** `greatest(least(qty_delivered, qty_ordered) - all_linked_do_qty, 0)`
    (`all_linked_do_qty` = every non-cancelled linked DO line, whatever its date),
    the part AutoCount says has gone out but no linked DO line explains, counted by the sales
    order's `order_date` exactly as round 2 R3 did;
  - capped so the line's total across all periods never exceeds `qty_ordered` (the round 2
    over-delivery rule, S1-8): linked DO quantities count in DO date order (a running sum over
    the line's DO lines) until `qty_ordered` is reached, and the rest counts nowhere.
  - Amount = `round(line_total x counted_qty / qty_ordered, 2)`, 0 when `qty_ordered = 0`
    (unchanged).
- **Interim, until DO data arrives.** With no linked DO lines, every line's DO sum is 0 and the
  residual is its whole confirmed quantity, so delivered is exactly round 2's figure (the sales
  report's "confirmed", bucketed by order date). When the DO integration starts linking, each
  line moves to DO dates by itself; deliveries AutoCount made before the integration (no DO
  row) stay on the order date, and nothing is counted twice because the residual subtracts
  every linked DO quantity, whichever period it fell in. No setting, no cutover date. The
  Targets page shows nothing different; the target page's Counts field reads "Delivered (by DO
  date)" from the day any linked DO line exists in the company.
- **Where the line's product and agent come from.** Always the sales order line and its sales
  order (G2, scope 3.1), never the DO's free-text `agent` / `salesman` strings (`order.py`), so a
  DO typed with a different salesman does not move credit.
- **Whichever lands first adds the column.** Expected case: the DO lane merges on Monday 28 Sep,
  while S6 is still being built, and S1 reads `order_lines.sales_order_line_id` as it is. If the
  DO lane has not merged when S1 enters Phase 2, S1's migration adds the same nullable column
  (no ingest, nothing fills it) and the DO lane rebases onto it and only fills it. No runtime
  check for the column, no flag. S1's golden tests (S1-26) seed DO lines both linked and absent.
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
  (title, amount, close month, note, stage move along allowed edges, lost reason; round 4: close date, no note, product lines, section 16). An agent sees
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

#### Module and schema (round 5, the owner's question of 26 Sep 06:09)

The owner asked: "are we doing this in a new schema and module called sales?". **Recommend yes
to both.** Measured on origin/main 46711c61:

- **How modules are organised today.** A module is enablement, not schema (`PRINCIPLES.md:187`):
  a catalog row in `MODULE_MANIFEST` (`app/modules/runtime/module_manifest.py:27`, for example
  `projects` :127, `scm` :103, `dealer_kit` :98, inserted by `installer._ensure_catalog_rows`,
  `installer.py:24-47`), a placeholder `app/modules/<key>/bootstrap.py` with `MODULE_KEY`
  (`app/modules/projects/bootstrap.py:3`), a router mounted behind
  `require_module_enabled_with_api_key("<key>")` (`app/api/v1/__init__.py:98-103` for
  `projects`), and slug prefixes mapped to the key (`permission_module_map.py:17-35`). There is no
  other feature-flag system. Models are one flat file per domain (`app/models/projects.py`,
  `project_so.py`, `scm.py`, `dealer_kit.py`); routes one package per domain under
  `app/api/v1/`; FE pages one folder per module under `app/(protected)/` (`project-sales/`,
  `scm/`, `dealer-kit/`), with the path to module key map in `lib/route-module-map.ts:11-31`
  (`/project-sales` to `projects` :29) and module assets in `modules/registry.ts`.
- **Schemas in use.** Four modules own a schema named after their key: `scm`
  (`app/models/scm.py`, created by migration `273_scm_module_schema.py:42`), `dealer_kit`
  (`app/models/dealer_kit.py:3-7`, migration `309_dealer_kit_module.py:93`), `projects`
  (`app/models/projects.py`, `project_so.py`, moved by `354_projects_schema_move.py:362-366`)
  and `chatbot` (`app/models/chatbot_turn.py:69`, `472_chatbot_turns.py:46`). Alembic already
  handles several schemas (`alembic/env.py`: `include_schemas=True`, and `KNOWN_SCHEMAS` built
  from the models, so a new schema needs no env change).
- **The rule and the owner's own precedent.** `PRINCIPLES.md:192-203` makes the schema an
  independent choice: default `public`, or a schema named after the module for "namespace
  clarity and clean uninstall", split by the uninstall test. ADR-0009 kept Project Sales in
  `public` by that test (its tables are records that must outlive an uninstall); **ADR-0011
  (15 Aug 2026) reversed it at the owner's request**: "they want the boundary between core CRM
  and an installable module to be visible in the database itself ... answered by `\dn`", the
  schema name is the module key, the `project_` prefix is dropped inside it, cross-schema FKs to
  core are normal, and **uninstall purges rows through the ORM and never drops the schema**.
  With that last rule the uninstall test no longer argues against a schema for records.
- **What exists under "sales" today.** No `sales` module key, catalog row, permission prefix,
  schema, API package or FE route (`app/api/v1/sales`, `app/services/sales`, `app/modules/sales`
  are all absent). The sidebar has a **SALES heading** (`menu.config.tsx:78`) holding Project
  Sales (`moduleKey: 'projects'`, :79-139) and Delivery Orders (`moduleKey: 'order'`, :141-161).
  Core tables with "sales" in the name stay where they are and are not part of this module:
  `sales_agents` (module `product`, `app/models/sales_agent.py:43`), `sales_orders` and
  `sales_order_lines` (core orders, `app/models/order.py:413`, :505), `sales_report_service.py`
  (order module), and the project module's `projects.*` sales order mirror
  (`project_so.py:542`).
- **Why yes to a module:** targets, teams, opportunities and the broadcast are a capability
  another tenant with a sales force would switch on, which is the module test in
  `PRINCIPLES.md:182-190`; the key `sales` is free.
- **Why yes to a schema:** it is what the owner asked for on Project Sales for the same reason
  (ADR-0011); every table here is new, so today it costs one `CREATE SCHEMA IF NOT EXISTS sales`
  in S6's migration and a `{"schema": "sales"}` in `__table_args__`, with no data move (ADR-0011
  had to move 47 tables); and it keeps `sales.teams` visibly apart from the core `teams` table of
  Users & Access, the "two things called Teams" risk in section 7. The cost: FK strings from a
  `sales` table to another `sales` table are schema-qualified (`ForeignKey("sales.teams.id")`,
  as `project_so.py:231` does), and raw SQL must name the schema (CLAUDE.md "Lessons learned": backend
  table names are not model class names, grep `__tablename__` first).
- **Not recommended: a `sales` schema holding `sales_agents` or `sales_orders`.** Those are core
  records owned by modules `product` and `order`; moving them would put core behind an
  installable module. They stay in `public`, and `sales.*` tables point at them with normal
  cross-schema FKs.

**What is built, per lane.** S6 (first) creates the module: `app/modules/sales/bootstrap.py`
(`MODULE_KEY = "sales"`), the `sales` entry in `MODULE_MANIFEST` with dependencies `base`,
`product` and `order` (it reads agents, customers, products and sales orders), `"sales":
"sales"` in `permission_module_map.py`, the router package `app/api/v1/sales/` mounted at
`/sales` behind the guard, `CREATE SCHEMA IF NOT EXISTS sales`, `sorento_crm_frontend/modules/sales/`
(`purge_tables.json` listing the `sales.*` tables, as `modules/projects/` does) and `/sales` to
`sales` in `lib/route-module-map.ts`; a purge invariants test like
`tests/test_projects_module_purge_invariants.py`. Models stay one flat file per domain:
`app/models/sales.py` (all module tables; replaces the plan's `app/models/sales_target.py`),
services under `app/services/sales/`, schemas `app/schemas/sales.py`, FE pages under
`app/(protected)/sales/`.

**Table name map** (plan name, then the real name; every later lane uses the right column):

| Plan text says | Built as | Lane |
| --- | --- | --- |
| `sales_teams` | `sales.teams` | S6 |
| `sales_team_members` | `sales.team_members` | S6 |
| `sales_targets` | `sales.targets` | S1 (S7 adds `customer_id`) |
| `sales_target_periods` | `sales.target_periods` | S1 |
| `sales_target_scope` | `sales.target_scope` | S1 |
| `sales_target_commission_tiers` | `sales.target_commission_tiers` | S4 |
| `sales_opportunities` | `sales.opportunities` | S2 |
| `sales_opportunity_lines` | `sales.opportunity_lines` | S2 |
| `sales_target_recipients` | `sales.update_subscriptions` (the screen calls them Sales updates, N12) | S5 |
| `sales_agents`, `sales_orders`, `sales_order_lines`, `customers`, `products`, `statuses`, `respond_contacts`, `orders`, `order_lines` | unchanged, in `public` | none |

The permission slugs stay `sales.targets.*`, `sales.teams.*`, `sales.opportunities.*`; the status
entity type stays `sales_opportunity`; the `integration_log.business_table` value becomes
`sales.update_subscriptions`.

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

**Round 5: membership is dated (Owner ruling 26 Sep 06:09, T2:** "when we move agent to new team,
only new order received in the new team is considred the ales of the new team right?"**).** Yes.
`sales_team_members` gains two columns and changes its uniqueness rule, in the S6 migration
(nothing is built yet, so there is no backfill):

| column | type | note |
| --- | --- | --- |
| `valid_from` | date null | first order date that counts for this team; **null = from the beginning** (the agent's first team, see below) |
| `valid_to` | date null | last order date that counts, inclusive; null = still in the team; check `valid_to >= valid_from` when both set |

- One **open** membership per agent per company: partial unique index
  `uq_sales_team_members_open` on `(company_id, sales_agent_id) WHERE valid_to IS NULL`. It
  replaces round 3's plain unique `(company_id, sales_agent_id)`, which cannot hold history.
- No two memberships of one agent in one company overlap: checked in `team_service` inside the
  same transaction (a Postgres exclusion constraint would need the `btree_gist` extension for one
  rule the service already owns; **trigger for the constraint:** a second writer of memberships
  appears outside `team_service`).
- **A move on date D** (the agent is in team N, the owner adds them to team S): N's row gets
  `valid_to = D - 1`, a new S row gets `valid_from = D`, one transaction, audited. D is
  **Moves on**, a date field that appears in the team modal only when a picked agent is in
  another team, default today, never later than today (a future move is a calendar note, not a
  membership). Orders dated D or later count for S; orders before D stay with N.
- **An agent's first team** (no membership row in this company yet): `valid_from` is null, so
  their earlier orders count for that team too. Without this, the owner's first setup after S6
  ships would leave every team target that starts before the setup day short of the orders
  already taken (round 5 question V1 asks the owner to confirm).
- **Removing an agent from a team** (not moving them): the open row gets `valid_to = today`. The
  history row stays, so past periods keep that agent's orders.
- **Deleting a team** still cascades its membership rows (S6-3): a deleted team has no figures to
  keep.

Team achievement (3.2) joins membership on the order's own date: an order of agent A dated X
counts for team T when A has a `sales_team_members` row for T with `coalesce(valid_from,
'-infinity') <= X` and `X <= coalesce(valid_to, 'infinity')`. Because one agent's memberships in
a company never overlap, an order still counts for at most one team.

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
Round 5 (Owner ruling 26 Sep 06:09, T2): that trigger has arrived; dated membership is built in
S6 as above. No parent team and no leader stay as they were (not asked).
Owner ruling 26 Sep ~13:25Z (W1, S6 hand test): "I need it to be able to set a sales leader,
which is also a sales agent". The leader trigger has arrived: `sales.teams.leader_sales_agent_id`,
one of the team's agents, a current attribute (not dated), held by `trg_sales_teams_leader_is_member`
(section 15). No parent team still (not asked).

**Team targets** reuse `sales_targets` with `subject_kind = 'team'` and `sales_team_id` (3.1), so
periods, scope, basis, metric, duplicate, tiers (S4) and recipients (S5) all work unchanged.
Achievement: 3.2. A team target is typed on its own, never derived from or split into agent
targets (T3). **Trigger for a "sum of agents' targets" check column:** the owner finds team and
agent targets drifting apart and asks to see both side by side.

**Round 5: a team target is the sum of its agents' targets (Owner ruling 26 Sep 06:09, T3:** "I
can set individual on each agent and add up to team ah"**).** The owner sets a figure on each
agent, and the team's figure is what they add up to. Built on the same `sales_targets` table
with one new column, in the S1 migration:

| column | type | note |
| --- | --- | --- |
| `parent_target_id` | uuid FK `sales_targets` ON DELETE CASCADE, null | set only on an **agent** target that belongs to a **team** target (check: `parent_target_id` set implies `subject_kind = 'agent'`; the service checks the parent is a team target) |

- **One form, one save.** Set target with "Target for: Team" shows the team's metric, counts,
  products, dates and split once, then an **Agents** table: one line per agent who is a member of
  the team on the start date or joins before the end date, each with a figure (per period when
  split). The **Team target** figure under the table is the sum, read-only, and updates as the
  owner types. Save creates the team header plus one child agent target per line, each with
  `parent_target_id` set and the team's metric, counts, products, dates and split copied.
- **Children follow the parent.** A child's metric, counts, products, dates and split are
  read-only on the child's page ("set on North FY26 H2", a link); editing them on the team target
  rewrites every child in the same transaction (period regeneration keeps each child's figures
  under the 3.1 keep rule). A child's **figures** are its own and are edited on the child's page
  or on the team target's Agents section, in place.
- **The team figure is always the sum.** Each team period's `target_value` is written by
  `target_service` as the sum of its children's periods with the same bounds, in the same
  transaction as any child edit, add or delete. A direct `PATCH` of a team target's period is 422
  `TEAM_TARGET_IS_SUM`. Stored rather than summed at read time so the achievement query, the
  list, commission (S4) and the message (S5) read one column for every subject kind; a test pins
  the sum after every write path.
- **No team-level override. Recommended, and built that way.** An override would let the team
  figure and the agents' figures disagree, which is the one thing the ruling rules out; a
  stretch goal above the agents' sum is set as a second team target (overlapping targets are
  allowed, 3.1). **Trigger for an override column:** the owner asks for a team figure that
  differs from its agents' sum on the same target.
- **Agents joining and leaving.** A member who joins the team after the team target is created
  is offered on the team target's Agents section as "No figure yet" with **Add figure** (creates
  their child, figure 0 until typed); nothing is created behind the owner's back. A member who
  moves to another team keeps their child target and its figures: the team figure is the sum of
  what was set, and the achieved figure counts that agent's orders only while they were in the
  team (T2).
- **Achieved is not the sum of the children's achieved.** A child is the agent's own target, so
  it counts all of that agent's orders in the range (G2); the team counts each agent's orders
  only while they were a member (T2). With no move in the range, the two agree exactly (S6-5's
  equality test); with a move, the team page shows the member's "Left 14 Oct" pill so the gap
  is explained on screen.
- **An agent may still hold targets of their own** (no parent), for example a basins push. Those
  never add to any team figure.
- **Commission (T4).** Tiers on the team target give the Team pool (3.3). Each child holds its
  own tiers; the team form's Commission section has one **Agent tiers** table that is copied to
  every child on save, and each child's tiers can then be changed on its own page.
- **Deleting.** Deleting the team target deletes its children (cascade), as one deferred action
  whose countdown names the count ("Deleting North FY26 H2 and 2 agent targets in 8s"). Deleting
  one child re-sums the team figure.

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

**Round 5 (Owner ruling 26 Sep 06:09, T5: "the point is we need to do it now and not backlog or
defer").** Every slice is built now, in three waves, with lanes inside a wave running in
parallel (section 6, "Lanes after round 5"): wave 1 S6; wave 2 S1 beside S2; wave 3 S7, S4, S3
and S5 side by side, S5 merging last. What the owner can use at the end of each wave: after wave
1, every agent in a team; after wave 2, live targets for teams and agents (delivered by DO date
once DO data exists) and salespeople logging opportunities in the portal; after wave 3, dealer
targets, commission, pipeline and the WhatsApp updates.

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

### Lanes after round 5 (Owner ruling 26 Sep 06:09, T5)

The owner's words: "the point is we need to do it now and not backlog or defer". Every slice
below is in scope now and is built in this round of work: targets (S1), teams (S6), dealer
targets (S7), opportunities (S2), pipeline (S3), commission tiers including "Highest rate on
everything" (S4), and the per-contact broadcast (S5). Nothing from this plan goes to
`documentation/backlogs/backlog.md`. The slices stay thin (one lane, one branch, one PR each, per
CLAUDE.md "Lane merge discipline"), and they are ordered so the owner can use something at the
end of each wave. A wave's lanes run at the same time in separate worktrees.

| Wave | Lane | Needs merged first | Why here | Can run beside |
| --- | --- | --- | --- | --- |
| 1 | **S6** sales teams, dated membership, the `sales` module, the Sales menu | nothing | every other lane needs the module key, the permission map entry and the Sales menu group; the owner fills the teams while wave 2 is built | none (it is the base) |
| 2 | **S1** team and agent targets, live achievement, delivered by DO date | S6 | the first screen with numbers, the core value | S2 |
| 2 | **S2** opportunities in the portal and the CRM | S6 | salespeople start logging while S1 is built; its tables, status entity and portal router touch nothing S1 touches | S1 |
| 3 | **S7** dealer targets | S1 | a subject kind on S1's table and query | S4, S3, S5 |
| 3 | **S4** commission tiers, both "higher rate above each threshold only" and "highest rate on everything" | S1 | tiers hang off S1's targets | S7, S3, S5 |
| 3 | **S3** pipeline beside each target | S1 and S2 | joins S2's opportunities into S1's rows | S7, S4, S5 |
| 3 | **S5** per-contact WhatsApp updates | S1 (built); S3 and S4 (merged before S5 merges) | the message reads S1's figures, S4's commission and S3's pipeline | S7, S4, S3 |

Merge order inside wave 3: S7, S4 and S3 as each is ready, **S5 last**. S5 is built beside
them against the field names this plan fixes (`commission_earned`, `bonus_earned`,
`pipeline_value`, `pipeline_count` on each period row, S3-1 and S4-7), and rebases onto them
before its PR is marked ready, so its golden message tests (S5-5) run against the real
commission and pipeline figures, not a stub. The Meta template approval (S5 DoD) is started when
wave 1 merges, so the ops lead time runs in parallel with the code.

Why the parallel pairs do not collide: S1 and S2 share only the module bootstrap and the
permission registry line added by S6; S7, S4 and S3 each add their own branch or column to
`achievement_service` and the targets list response, so their merges are small textual conflicts
at most, resolved by the lane merging second (CLAUDE.md "Pre-PR gate"). Each lane's first new
migration is re-parented with `./scripts/alembic-reparent.sh` onto whatever main holds when it
merges, so parallel migrations never leave two heads.

The **DO integration** (delivery orders from AutoCount, the owner's Monday 28 Sep lane) is not a
slice of this plan; S1 reads it through one seam (3.2, "Delivered, by DO date").

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
- **Round 5 (Owner ruling 26 Sep 06:09, R2, R3, R4, T2, T3), S1 runs in wave 2 beside S2:**
  - tables in schema `sales` (3.7 map); `sales.targets.parent_target_id` (T3, 3.8);
  - the team target form: team header plus an Agents table with a figure each, the read-only
    sum, one save creating the children (S1-27); `TEAM_TARGET_IS_SUM` on a team period PATCH;
    parent edits rewrite children (S1-28);
  - the team CTE matches membership on the order date (T2, S6-14);
  - person-label widening for agents and team members (R2, S1-29);
  - delivered by DO date through `delivered_by_date`, with the residual rule and the interim
    behaviour (R3, 3.2, S1-26); `order_lines.sales_order_line_id` added here only if the DO
    lane has not merged first;
  - amounts stay tax inclusive (R4, no change).
  - Tests add: DO golden set (a line half delivered by a linked DO in October and half before
    the integration counts the DO half in October and the rest on the order date; a cancelled DO
    counts nothing; a DO in November moves only its own quantity to November; no linked DO at all
    gives round 2's figure), team sum after every write path, children follow a parent edit,
    person-label widening.

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
- Round 5 (Owner ruling 26 Sep 06:09, R1, T5): wave 2, beside S1; it needs only S6's module.
  R1 accepted: the portal kind is granted to Sorento's own dealer-channel sales agents, each
  resolved through `sales_agents.contact_id`, never to dealers' shop staff. Tables
  `sales.opportunities` and `sales.opportunity_lines` (3.7). Measure the agent contact coverage
  (section 7) at the start of this lane, not before S2.

### S3. Pipeline beside the target (UAC S3-1 to S3-4)

- Backend seam: `pipeline_by_agent` joined into the targets list.
- Frontend seam: Pipeline column and KPI, linking to Opportunities filtered to that agent and
  month.
- Tests: weighted golden set with configured probabilities; terminal stages excluded; a null
  probability counts 0 and is flagged; no opportunity ever in achievement.
- Round 3 (L2, S3-5): team rows carry the sum of their current members' pipeline.
- Round 4 (N6, N7, S3-6): pipeline counts `expected_close_date` inside the period shown, not a
  month.
- Round 5 (T2, T5): wave 3, after S1 and S2 merge. A team row's pipeline sums the opportunities
  of agents who are members on each opportunity's expected close date (the T2 rule applied to
  pipeline), S3-7.
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
- Round 5 (Owner ruling 26 Sep 06:09, R5, T4, T5): wave 3. `marginal` is the default method
  once tiers exist; **`retroactive` ("Highest rate on everything") is built in this lane**, not
  deferred; the team form's Agent tiers table is copied to each child target (3.8); the team
  pool is computed on the summed team figure (S4-12).

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
- Round 5 (T5): wave 3, built beside S7, S4 and S3 and merged after S3 and S4 (section 6,
  "Lanes after round 5"). The table is `sales.update_subscriptions` (3.7). A team subscription's
  per-agent lines list the agents who were members during the period shown (T2).
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

**Round 5 (Owner ruling 26 Sep 06:09, T1, T2, T5, and the module question).** S6 is wave 1 and
also creates the `sales` module and the `sales` schema (3.7). T1 accepted: `sales.teams` and
`sales.team_members`, not the core `teams`. T2: membership is dated (`valid_from`, `valid_to`,
3.8); the team modal shows **Moves on** (default today) when a picked agent is in another team;
removing an agent closes their membership instead of deleting it; the team page's Agents
section lists members on the Active on date, and a member who left during a shown period keeps
a muted line with a "Left 14 Oct" pill (S6-14, S6-15). Tests add: the move golden set (orders
before the move date stay with the old team, orders on and after it go to the new one), no
overlapping memberships, one open membership, first team from the beginning, remove keeps
history.

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
- Round 5 (T5): wave 3, beside S4, S3 and S5. A dealer target's delivered basis uses the same
  DO-date rule (3.2). The column is `sales.targets.customer_id` (3.7).

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
  Round 5 (Owner ruling 26 Sep 06:09, T2): retired; membership is dated, so a move no longer
  rewrites the past. What remains: a move typed with the wrong **Moves on** date shifts orders
  between teams; the audit trail shows who moved whom on which date, and Edit on the membership
  corrects it.
- **DO data arrives after S1 is designed** (round 5, R3). Until the DO integration links DO
  lines to sales order lines, delivered reads as before (by order date). Risk: the DO lane links
  only some lines (for example DOs typed without an SO reference in AutoCount); those lines keep
  the order-date residual, so delivered is still complete, only dated partly by order date.
  Measure the linked share on the dev DB when the DO lane lands and show the owner.
- **Team figure is typed per agent** (round 5, T3). A new member has no figure until the owner
  adds one; the team page shows "No figure yet" with Add figure on that agent's line, so the gap
  is on screen, not silent.
- **Parallel lanes** (round 5, T5). Four lanes in wave 3 touch `achievement_service` and the
  targets list response. Kept small by the one-seam-per-lane split in section 6; the lane merging
  second resolves the conflict and re-runs the full sales test file before its PR is ready.
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

Owner's answers, PR #1260 comment 5843775673, 26 Sep 2026 06:09Z (verbatim, binding):

- **R1. Owner ruling 26 Sep 06:09:** "yeah correct". Accepted as recommended (3.5, S2).
- **R2. Owner ruling 26 Sep 06:09:** "yeah". Accepted as recommended: a target on an agent, and
  each member of a team, counts every code with the same person label (3.2, S1-29).
- **R3. Owner ruling 26 Sep 06:09:** "we will have DO integreation as soon as next Monday so by
  that time we will be able to know". Delivered counts by DO date once DO lines are linked to
  sales order lines; until then, and for any delivered quantity no linked DO explains, it counts
  by order date as recommended (3.2 "Delivered, by DO date", S1-26).
- **R4. Owner ruling 26 Sep 06:09:** "yeah". Accepted as recommended: amounts stay tax
  inclusive; the ex-tax check on real orders stays a measurement, not a slice.
- **R5. Owner ruling 26 Sep 06:09:** "yeah". Accepted as recommended: `marginal` by default, with
  "Highest rate on everything" selectable on any target and built in S4 (3.1, 3.3).

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

Owner's answers, PR #1260 comment 5843775673, 26 Sep 2026 06:09Z (verbatim, binding):

- **T1. Owner ruling 26 Sep 06:09:** "okay can". Accepted: new `sales.teams` and
  `sales.team_members` (3.7 names, 3.8).
- **T2. Owner ruling 26 Sep 06:09:** "hmm when we move agent to new team, only new order
  received in the new team is considred the ales of the new team right?". Yes: membership is dated
  (`valid_from`, `valid_to`); team achievement sums orders by the membership in force on each
  order's date; a move on date D sends orders dated D and later to the new team (3.8, S6-14,
  S6-15). An agent's first team counts from the beginning (round 5 question V1).
- **T3. Owner ruling 26 Sep 06:09:** "I can set individual on each agent and add up to team ah".
  A team target's figure is the sum of its agents' targets for each period, set in one form; no
  team-level override (recommended, 3.8, S1-27, S1-28).
- **T4. Owner ruling 26 Sep 06:09:** "yeap ok". Accepted: tiers on a team target give one Team
  pool figure per period, never split among agents (3.3, S4-10, S4-12).
- **T5. Owner ruling 26 Sep 06:09:** "okay, the point is we need to do it now and not backlog or
  defer". Every slice is in scope now, thin lanes in three waves with parallel lanes (section 4,
  section 6 "Lanes after round 5"); nothing goes to the backlog (section 12).

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

**Round 5 (Owner ruling 26 Sep 06:09, T5).** Nothing in this plan is deferred or backlogged, and
nothing is added to `documentation/backlogs/backlog.md`. Every slice (S1 to S7) is built now.
Dated team membership leaves this list: T2 asked for it and S6 builds it. "Highest rate on
everything" is built in S4. What remains above was never asked for by the owner; it is not a
slice and not a backlog item, only a named trigger so nobody builds it speculatively
(PRINCIPLES.md "Simplest thing that works"). If the owner wants any of it now, it joins a wave.
Round 5 adds none (a team-level override of the summed figure is ruled out by T3, not deferred).

## 13. Round 5: how the owner's answers were applied (PR #1260 comment 5843775673, 06:09Z)

| Answer | Ruling | Applied in |
| --- | --- | --- |
| R1 | accept: own dealer-channel agents get the portal form first | 3.5, S2 note |
| R2 | accept: every code with the same person label counts | 3.2, S1-29 |
| R3 | delivered counts by DO date once DO data exists; order date until then and for unexplained quantity | 3.2 "Delivered, by DO date", S1-26, section 7 |
| R4 | accept: tax inclusive | no change |
| R5 | accept: marginal default, "Highest rate on everything" selectable and built in S4 | 3.1, S4 note |
| T1 | accept: new sales team tables | 3.7 map, 3.8 |
| T2 | dated membership; orders count for the team in force on the order date | 3.2, 3.8, S6-14, S6-15, S3-7 |
| T3 | team target = sum of its agents' targets; no team override | 3.1, 3.8, S1-27, S1-28, S4-12 |
| T4 | accept: team pool, never split | 3.3, S4-10 |
| T5 | every slice now, nothing deferred; thin lanes in waves, parallel where independent | section 4, section 6, section 12 |
| "new schema and module called sales?" | recommend yes to both: module `sales`, schema `sales` (ADR-0011 precedent) | header, 3.7 "Module and schema" |

No criterion was deleted. New UAC criteria: S1-26 to S1-29, S3-7, S4-12, S6-14, S6-15.

## 14. Round 5 questions (posted on PR #1260 as the "Round 5" comment, 5844053739)

- **V1. An agent's first team (T2).** Recommend: when an agent who has never been in a team is
  put in one, their earlier orders count for that team too (`valid_from` empty); only a later
  move starts on a date. Otherwise the owner's first setup after S6 leaves every team target that
  starts before the setup day short. Alternative: the first team also starts on the day it is
  set (a Moves on date for every placement).
- **V2. What the DO integration writes (R3).** Recommend: Monday's DO lane lands AutoCount DOs in
  the existing Delivery Orders tables (`orders`, `order_lines`) and adds one column,
  `order_lines.sales_order_line_id`, from AutoCount's "transferred from" SO line; the targets
  read only that. Alternative: a new DO table, in which case one query in the targets service
  changes and nothing else.
- **V3. The `sales` schema (the owner's own question).** Recommend: yes, module `sales` with its
  tables in a `sales` schema (`sales.targets`, `sales.teams`, ...), as Project Sales moved to
  `projects` in ADR-0011; nothing is built yet, so it costs one line per model. Alternative:
  module `sales` with its tables in `public` under a `sales_` prefix (the round 1 to 4 text).

**Owner ruling 26 Sep ~09:05 (chat, verbatim):** "yeah I am okay with sales target". V1, V2 and V3
are accepted as recommended; the plan is ready to build, S6 (teams) first, on PR #1260.

## 15. S6 build record (26 Sep, PR #1260)

Built exactly to 3.7, 3.8 and the S6 slice: UAC S6-1, S6-2, S6-3, S6-8, S6-9, S6-12, S6-13,
S6-14, S6-15 and S1-17. Team targets (S6-4 to S6-7, S6-10) are S1's and are not here. Decisions
taken while building, each the direct reading of the plan unless it says otherwise:

- **Migration `sales_0001_teams`** on `sb3_company_stock_push_at` (re-parented after main moved): `CREATE SCHEMA IF NOT EXISTS
  sales`, `sales.teams`, `sales.team_members` (with `company_id` NOT NULL, security review), the
  four `sales.teams.*` slugs granted to admin and superadmin, and the `sales` catalog row with no
  `tenant_modules` row: **the module ships dormant**, as `scm` and `dealer_kit` did, and is
  switched on in System > App Store. Downgrade drops both tables and the catalog row, and leaves
  the schema (ADR-0011) and the permission rows.
- **One extra read route**, `GET /sales/teams/agent-options` (gated `sales.teams.view`): the team
  picker lists active agents with the team each is in now, without needing
  `master_data.sales_agents.view`.
- **`PATCH /sales/teams/{id}` also takes `sales_agent_ids` and `moves_on`**, so the team page saves
  the name, Active and the agents in one transaction (review round 1). `PUT .../members` stays.
- **Same-day corrections (review round 1).** No membership ever starts after today. An agent
  removed today and placed in another team today is a move today (the old team keeps everything
  up to yesterday). A move made by mistake today is undone the same day: the same-day stay is
  dropped and the team left yesterday is reopened as one continuous row. A back-dated Moves on
  that would reach across a later stay is 422.
- **"Left" on the team page** means the membership ended on or before the date shown; such a
  line is shown, muted with "Left <date>", only when it ended in the month of that date. S6 shows
  today; S1 wires the Targets page's Active on date through `GET /sales/teams/{id}?on=`.
- **The team page edits in place (S6-13)**; the list's modal is Add team. The modal can also edit
  (S6-12's wording), but no screen opens it in edit mode today, because the team page is the edit
  path and D15 keeps Edit out of the row menu.
- **Both sidebars** (`MENU_SIDEBAR` and `MENU_SIDEBAR_COMPACT`) carry the Sales group, so Sales
  Agents is listed once in each and is not lost from the compact layout.
- **Plan DoD not run here:** "every active agent can be placed in a team on the dev DB (prod
  copy)" needs the prod copy, which this cloud session does not have; the browser pass ran on a
  database built from zero with seven seeded agents.

### Fix lane round 2 (26 Sep, after the owner's hand test; UAC S6-16 to S6-18)

- **Team leader (W1).** Migration `sales_0002_team_leader` on `sales_0001_teams` (single head):
  `sales.teams.leader_sales_agent_id`, nullable, `fk_sales_teams_leader_sales_agent_id` to
  `sales_agents` ON DELETE SET NULL. **The membership rule is a trigger, not a check:** a check
  constraint cannot read another table, and a foreign key cannot target the open-row partial
  index (an agent can have several stays in one team). `trg_sales_teams_leader_is_member` is a
  pair of DEFERRABLE INITIALLY DEFERRED constraint triggers (on `sales.teams` when the leader is
  set, on `sales.team_members` when an open row closes or goes) sharing one function: at commit,
  a team's leader must have an open membership row in that team. Deferred, because one save
  closes the leader's row and clears the leader in either order. The DDL has one copy,
  `app.models.sales.leader_rule_ddl`, used by the migration and by `create_all` (test schemas,
  bootstrap_env). The service keeps the rule true: `save_members_and_leader` adds a leader who
  is not a member to the agents (a Moves on if they come from another team), and `set_members`
  clears the leader when they are left out or move away. `sales.teams.edit` covers it.
- **One line per agent (W2).** The team read orders an agent's stays by start date and keeps
  the latest, so a returning agent shows once, active; history is untouched.
- **Screens.** The leader's pill leads the list row, reading "(Leader)": a word rather than a
  crown icon, because DESIGN-LANGUAGE.md has no icon vocabulary for a role and a bare icon would
  need a legend. The team page names the leader under the team name and tags the row; the modal
  and the in-place edit have a clearable Leader `SearchableSelect` limited to the picked agents.
- **Evidence.** `documentation/plans/sales/evidence/s6-round2/`: agent-browser at 1280 and 375
  on a database built from zero (seven seeded agents; Kim left North on 5 Sep and returned on
  20 Sep, and shows once). A leader changed in place, and a leader moved into a new team (whose
  old team's leader cleared), both committed through the API, so the deferred rule ran at a real
  commit; a direct `UPDATE` naming a non-member as leader was refused by it.

## 16. S2 build contract (wave 2, beside S1; branch `claude/sales-opportunities-s2-32eppn`)

Track: full (migration, new permissions, a new portal ingest surface). Built exactly to 3.4, 3.5,
3.7 and the S2 slice: UAC S2-1 to S2-16. Nothing here touches S1's tables, services or routes;
the Sales menu gains Opportunities only, and S1 adds Targets above it. S3's pipeline join waits
for wave 3. Decisions below are the direct reading of the plan unless marked.

**Phases.** As S6 did: the contract below stands in for the Phase 1 mock contract, because the
plan and mockup already fix every screen; the tester writes the red tests from it, then the coder
builds backend then frontend. Recorded in the PR body.

**Agent contact coverage (section 7, "measure at the start of S2").** Not measurable in this cloud
lane (no prod copy, `documentation/agents/cloud-lanes.md` "The one rule"). Run on the dev DB
before the owner grants the portal kind:
`SELECT count(*) FILTER (WHERE contact_id IS NOT NULL), count(*) FROM sales_agents WHERE is_active;`

### Backend

- **Migration `sales_0003_opportunities`** on `sales_0002_team_leader`: `sales.opportunities`,
  `sales.opportunity_lines` (columns exactly as 3.4, `expected_close_date`, no `product_note` or
  `product_category_id`); check `customer_id IS NOT NULL OR prospect_name IS NOT NULL`; check
  `outcome IN ('open','won','lost')`, `source IN ('portal','crm')`, `qty > 0`; unique
  `(company_id, opportunity_no)`; the four `sales.opportunities.*` slugs granted to admin and
  superadmin; the `OPP-` numbering rule (`doc_type = 'sales_opportunity'`, 6 digits) when absent.
  Downgrade drops both tables, leaves slugs and the rule.
- **Models** in `app/models/sales.py`: `SalesOpportunity` (`__audit_track__`,
  `__audit_entity_type__ = "sales_opportunities"`) and `SalesOpportunityLine` (relationship
  `lines`, ordered by `sort_order`, cascade delete-orphan; attach through the relationship,
  LESSONS 111).
- **Stages** `app/modules/sales/status_entities.py` registers `sales_opportunity` (3.4). Startup
  seed `app/services/sales/sales_seed_service.py` `run(db)`: `seed_default_opportunity_graph`
  (New 10 initial and default, Qualified 25, Proposal 50 `is_active=false`, Negotiation 75, Won
  100 terminal, Lost 0 terminal; edges New to Qualified, Qualified to Proposal, Proposal to
  Negotiation, Qualified to Negotiation, back one step Qualified to New, Proposal to Qualified,
  Negotiation to Proposal, Negotiation to Qualified, and every live stage to Won and to Lost; the
  lead seed's wholesale guard), `seed_opportunity_lost_reasons` (set
  `sales_opportunity_lost_reasons`: price, competitor, project_cancelled, no_response, other) and
  the numbering rule; called from `app/main.py` startup beside the Project Sales seed.
- **Outcome** follows the stage key: `won`, `lost`, else `open`. `stage_changed_at` stamped on
  every move. Lost needs an active option value of the lost reason set (422
  `LOST_REASON_REQUIRED`); leaving Lost is impossible (terminal). Won takes an optional
  `sales_order_id` whose `customer_id` equals the opportunity's (422
  `SALES_ORDER_OTHER_CUSTOMER`); only the CRM sends it. On a prospect (no customer) any
  non-cancelled sales order is accepted and the opportunity takes that order's customer
  (`customer_id` set, `prospect_name` kept as history): the "linked when Won" of 3.5 and round 4
  Q2. The order select then searches all sales orders by number or customer name (`q`). Moves go through `status_service.assert_transition_allowed` (422
  `status_transition_not_allowed` / `status_inactive`).
- **Customer or prospect (S2-15).** Names compare lower-cased with runs of whitespace collapsed
  and ends trimmed. `customer_options(q)` returns
  `{items: [{customer_id, customer_code, customer_name}], prospect: {name} | null,
  blocked: {name, message} | null}`: portal items are the agent's own customers
  (`customers.sales_agent_id`) whose code or name contains `q`; CRM items are all customers.
  `prospect` is the typed name when no customer of the company has it exactly; `blocked` (portal
  only) is set instead when another agent's customer has it exactly, message
  `"<customer name> is another agent's customer"`. A create or update whose `prospect_name`
  matches any customer's name exactly is 422 `PROSPECT_IS_A_CUSTOMER`; `customer_id` and
  `prospect_name` together is 422; neither is 422 `CUSTOMER_OR_PROSPECT_REQUIRED`; a portal
  `customer_id` that is not the agent's own is 422 `CUSTOMER_NOT_YOURS`. No customer row is ever
  created.
- **Lines (S2-16).** `lines: [{product_id, qty}]` on POST and PATCH (PATCH replaces the set when
  sent), stored in entered order (`sort_order` 0..n); qty <= 0 is 422; zero lines valid;
  `expected_amount` required on create, never computed.
- **Agent.** Portal: from the token only (`app/services/sales/portal_agent.py`
  `agent_for_contact(db, contact_id)`, lifted from `price_tag_request_service.py`
  `lookup_debtors_for_agent`, which now calls it). CRM: `sales_agent_id` from the payload when
  sent, else the customer's (null accepted).
- **Company.** Portal: the customer's company, else the agent's, else the first active company
  (`portal_price_tag._resolve_company`); writes run under `company_scope`. CRM: the acting
  company (`team_service.acting_company_id`).
- **Portal router** `app/api/v1/public/portal_sales_opportunity.py`, mounted before
  `portal.router`, prefix `/portal`: `GET /sales-opportunities` (mine, `{items}`),
  `POST /sales-opportunities` (201), `GET|PATCH /sales-opportunities/{id}`,
  `GET /sales-opportunities/customer-options?q=`, `GET /sales-opportunities/meta`
  (`{stages, lost_reasons}`). Gates in order: module `sales` off under strict mode 403
  `MODULE_NOT_ENABLED` (same semantics as `require_module_enabled`), kind not visible 403
  `FORM_TYPE_NOT_VISIBLE` (`require_form_visible`), no active linked agent 403
  `NOT_A_SALES_AGENT`; another agent's id 404. Body fields `sales_agent_id`, `source`,
  `sales_order_id` are not in the portal schemas (ignored). `sales_opportunity` joins
  `GRANTABLE_PORTAL_FORM_TYPES` and `_KIND_LABELS` ("Sales Opportunities"), not the base kinds.
- **CRM router** `app/api/v1/sales/opportunities.py` at `/sales/opportunities`:
  `GET ""` (list: `page, limit, sort, dir, query, status_id, sales_agent_id, customer_id,
  close_from, close_to, outcome`; `ListResponse`), `POST ""` (201), `GET /meta`,
  `GET /customer-options?q=`, `GET /agent-options`, `GET /{id}`, `PATCH /{id}`,
  `DELETE /{id}` (hard), `GET /{id}/sales-order-options?q=` (that customer's non-cancelled sales
  orders, newest first; for a prospect, all non-cancelled orders matching `q`). Slugs view / add / edit / delete. List-query adapter
  `sales_opportunities`.
- **Detail shape** (both sides): `id, opportunity_no, title, customer_id, customer_code,
  customer_name, prospect_name, sales_agent_id, sales_agent_label, status_id, stage_key,
  stage_label, win_probability, outcome, expected_amount, expected_close_date, lost_reason,
  lost_reason_label, sales_order_id, sales_order_no, source, created_by_label, created_at,
  updated_at, stage_changed_at, lines: [{id, product_id, product_code, product_name, qty}],
  available_transitions: [{to_status_id, key, label}]`.
- **Audit (S2-9)** through `__audit_track__`: a portal write carries `actor_contact_id` (set by
  `get_portal_token`), a CRM write the user id.
- **Migration heads.** S1 adds its own migration beside this one; whichever lane merges second
  runs `./scripts/alembic-reparent.sh` so main keeps one head.
- **Purge**: both tables join `PURGE_ORDER` (lines first) and `purge_tables.json`.

### Frontend

- **Portal** `app/(auth)/portal/sales_opportunity/` (list, `new`, `[id]`), mobile first at 375:
  list cards (number, title, customer or prospect, stage `Badge`, amount, close date) with **New**;
  form sections Customer or prospect (one searchable select: own customers, then **Add "..." as a
  new prospect** or the disabled blocked line), Title, Expected amount, Expected close date,
  Products (product search and qty per row, Add product, remove, "No products yet"); detail has
  the same form plus stage buttons from `available_transitions`, Lost revealing a required reason
  select. A **Sales Opportunities** card on the landing only when `visible_form_types` has the
  kind; the kind joins the Market Segments grantable list and the kind labels. No horizontal
  scroll at 375 (S2-10). S2-14 is a recorded agent-browser run (portal at 375, CRM at 1280), no
  new Playwright spec.
- **CRM** Sales > **Opportunities** (`/sales/opportunities`, `sales.opportunities.view`,
  `moduleKey: 'sales'`, both sidebars, above Sales Teams): `PageHeader` with **Log opportunity**;
  DataGrid (fixed layout, resizable, `size` on every column, `truncate` + `title`, scrolls in its
  own container) with Number, Title, Customer or prospect, Agent, Stage `Badge`, Amount, Close
  date, Source (Portal or CRM); filters Stage, Agent, Customer (clearable `SearchableSelect`),
  close date range (`DateRangePicker`), search; `rowHref` to `/sales/opportunities/[id]`. One
  modal to log. Detail page: header (number, title, stage `Badge`; Created and Updated in the meta
  strip), `RecordNavigation`, sections Opportunity, Products, Stage (moves; Lost reason; Won's
  optional sales order select limited to the customer), every section rendered with an empty
  state; Edit in place; Delete deferred. Customer page: an **Opportunities** section in view and
  edit, "No opportunities yet" with **Log opportunity** (modal preset to the customer).
