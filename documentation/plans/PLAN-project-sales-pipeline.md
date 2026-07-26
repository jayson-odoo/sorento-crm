# PLAN — Project Sales Pipeline (module `projects`)

**Status:** Drafted from grill session 2026-07-25. **Pre-code.** Review rounds 1–2 applied
(numbering / delivery lag / loss reasons made configurable; sponsorship flag pinned to
`respond_contacts`; **task management added and decided** — see §7, new slice S2b).
Next: internal grill round on this plan, then implementation.
**Owner:** jayson
**Slug:** project-sales-pipeline
**Classification:** MODULE (`projects`), `public` schema, normal FKs, company-scoped.
**Acceptance criteria:** `UAC-project-sales-pipeline.md` (binding)
**Glossary:** `documentation/CONTEXT.md` (binding)
**Decisions:** `documentation/adr/0001..0004`

---

## 1. Why

Sorento sells sanitary ware into Malaysian property developments through 10+ salespeople
working many concurrent pursuits. Today a "project" is a free-text string typed into three
different tables (`purchase_requests` for both PR and sponsorship forms, and `complaints`),
so nothing links, nothing dedupes, and nothing forecasts.

The client's six stated problems: stop salespeople clashing on the same project; link
registration → quotation → sample → negotiation → sponsorship → PO back to one record; give
management visibility on workload, value, conversion and multi-year delivery forecast; protect
margin and control SKU proliferation; track sponsorship investment against POs won; build
intelligence on brands, locations and architects.

**Prior art warning.** A generic `commercial_core` / `commercial_activity` module (~5,000 LOC)
was built in `c77560009` and deleted unused in `7f0eb94f1`. It was a generic lead → project →
tender → master-quotation CRM with nothing fitted to how Sorento sells. See ADR-0003.

## 2. Shape

Two layers, shipped together (ADR-0003):

**Generic skeleton** — mirrors `dreamz_ems/modules/ems` so the two products converge:
`project_types` · `project_templates` (+ `project_template_roles`) · `projects` ·
`project_stakeholders` · `project_parties` · activities adapter.

**Sorento sales extension** — explicitly named, no pretence of generality:
`project_sales_profile` · `project_quotations` → `project_quotation_versions` →
`project_quotation_lines` · `project_samples` · `project_purchase_orders` (+ lines) ·
`project_series` · `price_floor_rules` · sponsorship link.

## 3. Data model (indicative)

```
project_types(id, company_id, name, is_active)
project_templates(id, company_id, type_id→project_types, name, status_graph_scope_id?)
project_template_roles(id, template_id, name, sort)

projects(id, company_id, project_code, template_id, type_id, title, normalised_title,
         developer_party_id→project_parties,          -- G2: on THIS table, see below
         status_id→statuses, owner_user_id, is_critical, critical_at,
         management_support, management_notes,
         last_meaningful_activity_at, created_by, created_at, updated_at)
  UNIQUE (company_id, developer_party_id, normalised_title)

project_sales_profile(project_id PK, registered_company_name, location, address,
         architect_party_id, main_contractor_party_id, estimated_sales_value,
         launch_date, expected_delivery_from, expected_delivery_to)
project_brands(project_id, brand_id→brands)                       -- M2M

project_parties(id, company_id, party_type, name, registration_no, address,
         phone, email, customer_id→customers NULL)
project_stakeholders(id, project_id, party_id NULL, role_id→project_template_roles,
         person_name, phone, email, influence, is_primary, notes)

project_quotations(id, project_id, scope_label, outcome, loss_reason, created_by)
project_quotation_versions(id, quotation_id, version_no, frozen_at, issued_by,
         total_amount, notes)
  -- G9: NO current_version_id and NO is_frozen boolean. Current = MAX(version_no);
  -- frozen = version_no < MAX. One fact, zero drift.
  UNIQUE (quotation_id, version_no)
project_quotation_lines(id, version_id, product_id NULL, product_code_snapshot,
         description_snapshot, image_attachment_id NULL, unit_price, quantity,
         uom, unit_type, line_total, is_non_standard, floor_value_applied,
         is_below_floor)

project_samples(id, project_id, quotation_version_id, submitted_on,
         developer_feedback, salesperson_notes)

project_purchase_orders(id, project_id, quotation_version_id, po_source,
         issuing_party_id→project_parties, po_number, po_date, po_amount)
project_purchase_order_lines(id, po_id, product_id NULL, product_code, unit_price,
         quantity, model_mismatch, price_mismatch)

project_series(id, company_id, name, brand_id NULL, is_active)
project_series_categories(series_id, category_id→product_categories)
price_floor_rules(id, company_id, level, product_id NULL, category_id NULL,
         mode ∈ percent|absolute, value)
project_collaborators(project_id, user_id, granted_by, granted_at)
project_takeover_requests(id, project_id, requester_user_id, kind ∈ join|dispute,
         reason, status, decided_by, decided_at)
```

Core additions outside the module: `statuses`, `status_transitions` (ADR-0001);
`attachment_types.is_image_class`; `purchase_requests.project_id` (nullable);
per-contact sponsorship rollout flag.

## 4. Slices

**S0 — Prereq.** Merge `feat/promo-expiry-rule-engine` (carries `app/rule_engine`). Port
`aggregates.py` + `lazy_registry`. *No feature work until this lands.*

**S1 — Status engine as CORE** (ADR-0001). `statuses` + `status_transitions` + StatusEntity
registry + transition service + admin screens. Drop `workflow_stages`. `category` NOT NULL.
Entity-default graph with per-template copy-on-write fork. Manual transitions only.
Regression pass proving no existing status vocabulary changed. → UAC Group B.

**S2 — Registration + parties + stakeholders + pipeline.** Types, templates, template roles,
projects, sales profile, parties, stakeholders, brands M2M, the `pg_trgm` clash lock with the
block/join/dispute flow, activities adapter, board+grid, detail tabs (empty tabs render),
project numbering, Excel import. → UAC Groups A, C, D, G, J.

**S2b — Task management** (§7). Template task checklists, `project_tasks` on the status engine
as entity #2, list + board + gantt + history view, "My Tasks". Must precede S5.

**S2c — Leads** (§5a). `project_leads` on the status engine as entity #3, select-or-create
Customer wizard, qualify → runs the clash check and creates a Project, disqualify + reason,
lead→project conversion metric, Customer detail page showing its leads and projects.

**S3 — Quotations.** Quotations, versions (edit-in-place + Revise-freezes), lines with
snapshots, Project Series (category allowlist), price floor rules (3 levels × percent|absolute),
the two alerts, outcomes + loss reasons, derived project outcome. → UAC Group E.

**S4 — Samples, sponsorship link, POs.** Samples bound to versions with the
superseded-version block; sponsorship `project_id` + per-contact flag + mandatory picker with
hard block; Project POs with the match check; PO → Won auto edge. → UAC Group F.

**S5 — Forecast, staleness, worklist.** Three-number forecast, per-status probability,
configurable delivery lag with per-project override, management dashboard, staleness
automation + ladder + takeover requests, My Follow-ups. → UAC Groups H, I.

**S6 — MCP read tools; then PR + Complaint linkage.** → UAC Groups K, L.

## 5. Three-phase execution (per slice)

1. **FE prototype** against mocks — every state (loading / empty / error / partial), verified
   in-browser via Playwright MCP by clicking through the sidebar, never a deep URL. Contract
   documented at the top of the feature service file.
2. **BE wiring + tests** — models, migrations, schemas, services, routes matching the Phase-1
   contract exactly; FE off mocks. pytest + vitest + playwright land here, never deferred.
   TDD: golden-set tests for the clash matcher, floor resolution and forecast maths are
   written failing first.
3. **Review** — `/code-review`, then PR.

## 5a. Leads (slice S2c)

Ecohub's `Client → Lead → Project[]` chain, adapted. `dreamz_ems` expects the same shape —
its `Project` already reserves `lead_id` and `client_id` as soft-ref seams "set on lead Won" —
so this is a convergence point across all three products, not a Sorento-only bolt-on.

```
project_leads(id, company_id, lead_code, customer_id→customers,
        developer_party_id→project_parties NULL, title, source, source_detail,
        estimated_value, location, notes, status_id→statuses,
        owner_user_id, outcome, disqualified_reason,
        qualified_at, created_by, created_at, updated_at)

projects.lead_id → project_leads  (nullable — a project may be registered directly)
```

**Decisions**

- **A Lead is NOT exclusive.** No fuzzy lock, no clash block. Several salespeople may record
  the same rumour; ownership is decided at conversion. Locking hearsay would produce a worse
  land-grab than locking tenders, and a lead often has no developer FK to lock on.
- **`customer_id` is required**, matching ecohub (`Lead.clientId` is non-nullable). The
  create flow is a wizard: select-or-create Customer → development info → lead detail →
  confirm.
- **Qualify** runs the full AC-C5/C6 fuzzy check and creates a Project, carrying `lead_id`.
  That is where ownership locks. One Lead may produce several Projects.
- **Disqualify** records a reason. Lead-to-project conversion rate becomes a real metric.
- Lead status rides the status engine as **entity #3**, consistent with `project` and
  `project_task`.
- Company-scoped like everything else in the module.

**Consequence — accepted, with a mitigation.** This partly reverses the reasoning behind
`project_parties`: we kept organisations out of `customers` to protect a 2,391-row buying
ledger, and now the lead wizard can create customer rows for non-buyers. The real data
supports it (`KHOO SOON LEE REALTY`, `GLOBAL INGRESS`, `DBI CONCEPT DESIGN` are already
customers), so lead-created rows get a `source` marker and order/invoice pickers can filter
prospects out if the noise becomes real.

**Slice placement: S2c**, after S2b. Registration must exist before anything can convert into
it, and leads are purely additive upstream — nothing downstream waits on them.

## 6a. Grill findings and resolutions (round 1, 2026-07-25)

Twenty-two findings from grilling this plan against the code it ports. Resolutions:

| # | Finding | Resolution |
|---|---------|------------|
| G1 | "Won" meant both a status rung and a derived outcome; a project with a PO on one scope and an open quotation on another read as finished | Terminal rung renamed **"PO Received"** — status describes what happened, not that the pursuit ended. Outcome stays derived and is what every metric reads. |
| G2 | `UNIQUE (company_id, developer_party_id, normalised_title)` spanned two tables — unbuildable | `developer_party_id` + `normalised_title` moved onto `projects`. Slight dent in generic purity (EMS leaves it null); the constraint is now real. |
| G3 | ADR-0001 grouped by `category`, which the source model documents as *"LEGACY cosmetic mirror … behavior branches on the trait flags, never here"* | Group cross-template reporting by **`key`** — documented stable per entity_type, and part of the `(entity_type, tenant_id, scope_id, key)` unique constraint. `category` stays nullable and cosmetic. |
| G4 | Status engine carries `tenant_id`; sorento partitions on `company_id`. Never decided | Statuses stay **global** — not `CompanyScopedMixin`. SRT and MOCHA share one pipeline definition. |
| G5 | Ported `statuses.id` is `Column(String)`, violating the uuid-id principle that broke `user_sessions.id` on prod | Port all PKs/FKs as `UUID(as_uuid=False)`. |
| G6 | `product_categories.parent_category_id` exists; floors and series ignored the hierarchy | Both resolve **up the tree**: a price floor checks product → its category → ancestors → system. Nominating a parent category into a Project Series **covers all descendants**. |
| G7 | PDF says PO price matches the *initial* quotation; plan said the bound version, unflagged | Flag against the **bound version** (the price last shown), and additionally surface **drift from v1** so price erosion across the negotiation is visible. Two signals. |
| G8 | Clash check said "live registrations", undefined for lost/dormant | Only projects with outcome **open** block. A lost or dormant match is shown as context ("previously pursued by X, lost on price") but does not block the re-tender. |
| G9 | `current_version_id` + `is_frozen` = two sources of truth | Both removed. Current = `MAX(version_no)`; frozen = below it. |
| G10 | `numbering_rules.doc_type` is unique with no company column | One global sequence; project codes are globally unique across companies. Stated, not changed. |
| G11 | Same-sheet import collisions undefined | The importer normalises and groups **within the batch**; a duplicate key fails both rows as a job error naming the row numbers. Neither is created. |
| G12 | Which company's projects does the sponsorship picker show? | Projects of the companies linked to that contact via `respond_contact_companies`; when more than one, each row shows its company. |
| G13 | Below-floor alert on every in-place save = alert storm | Notify only on the **transition** into breach (`is_below_floor` false → true). Staying in breach is silent. |
| G14 | Staleness thresholds on forked status graphs never get later default changes | Fork copies thresholds; an explicit admin **"reapply defaults"** action exists. No silent propagation. |
| G15 | Which forecast number gets year-bucketed? | **Committed** by default (the PDF's own worked example). Pipeline and Weighted can be bucketed but render as a visually separate speculative band. |
| G16 | Weighted applies a project-level probability to quotation-level values | Stated explicitly: the project's status probability is applied to each of its open quotations. |
| G17 | MCP read tools have no user context | Tri-state company scope, no-contact resolves to all companies — the existing convention. |
| G18 | Template edit/delete semantics | Roles and template tasks are referenced by id: removing one that is in use is blocked (deactivate instead). Graph changes never retro-apply to existing projects. |
| G19 | Project delete undefined | Blocked while any Project PO exists; Archive instead. Hard delete otherwise, with confirmation. |
| G20 | "Management" defined twice (`.reassign` vs `.view_all_financials`) | One definition: management = `projects.projects.view_all_financials`. `.reassign` is a separate grant normally held by the same role. |
| G21 | AC-B6 asked for a regression pass proving a negative | Rewritten: assert no code path reads `workflow_stages`, and that the new tables are purely additive. |
| G22 | Ecohub's `ProjectTask` has no predecessor links | "Gantt" is a **timeline bar chart**, not a dependency/critical-path chart. Stated so expectations match. |

## 6. Open risks

- **Adoption.** Empty pipeline on go-live; mitigated by the day-one consolidated Excel
  migration (AC-L1). If that import doesn't happen, the forecast is meaningless for months.
- **Clash-lock fairness.** Enforced from day one with no amnesty window. Ownership is decided
  in the migration spreadsheet; disputes route to managers. Watch for land-grab behaviour in
  the first month.
- **Category-level Project Series is coarse** — a premium one-off inside a nominated category
  won't flag as non-standard. Accepted knowingly; revisit if the alert proves too quiet.
- **Editable current version.** A sample submitted against the live version can drift if the
  version is edited before Revise. Audit trail covers it; frozen versions are exact.
- **Two similarly-named sidebar groups** ("Project Sales" and "Project Sales Admin").
  Accepted; watch for user confusion in UAT.
- **MOCHA company** owns no products, customers or brands. Company-scoped projects are
  future-proofing; SRT is the only live user in phase 1.

## 7. Task management — added scope, decided

Ecohub's task tooling is proven and substantial: `TaskTemplateSet` → `TaskTemplateItem`
applied to a project as `ProjectTask` (assignee, `escalatedTo`, `stuckReason`, start/end,
`completedAt`, history), driven by a 1,025-line board plus a gantt view.

Two findings that shape how it folds in:

- **It fits the template layer we already have.** `TaskTemplateSet` maps onto
  `project_templates`, which already owns Stakeholder roles — so a template can also own a
  task checklist. "Property Development" ships a standard pursuit checklist, "Renovation" a
  shorter one, an EMS event template ships event-run tasks. No new generic concept, and the
  EMS convergence still holds.
- **It does NOT collide with `tickets`.** A ticket is raised *by* someone about a problem and
  carries SLA response/resolution clocks and Respond.io links; a task is work *I* plan.
- **It DOES collide with `next_action_date`.** If tasks exist, the next action is the earliest
  open task. Two records of the same promise will drift.

### Decisions

1. **Both pursuit and delivery tasks**, separated by `task_category` (`pursuit` = visit the
   architect, submit the quote, deliver the sample, chase the PO; `delivery` = post-win
   execution, ecohub-style). One table, one board, filtered by category — the project detail
   Tasks tab defaults to the category matching the project's outcome (pursuit while open,
   delivery once won).
2. **Task status rides the status engine as entity #2** (`project_task`). Configurable per
   template like the project graph, and it proves the engine on a second entity immediately
   rather than a year later.
3. **`next_action_date` is dropped.** Next action = the earliest open task's due date, derived.
   One source of truth. "My Follow-ups" becomes **"My Tasks"**.
4. **Full ecohub parity** — list, board, gantt, task history, template checklists — as its own
   slice **S2b**, immediately after S2.

```
project_template_tasks(id, template_id, name, description, task_phase, category,
        sort_order, default_offset_days)
project_tasks(id, company_id, project_id, name, description,
        task_phase,          -- pursuit | delivery   (lifecycle axis)
        category,            -- work-stream from the template (ecohub's `category`)
        status_id→statuses, assignee_user_id, escalated_to_user_id, stuck_reason,
        start_date, due_date, completed_at, sort_order, source_template_task_id,
        linked_entity_type, linked_entity_id)   -- quotation_version | sample | po
```

**Ecohub reference pass** (done after the first draft — it corrected three things):

- The board **groups by `category` in collapsible sections** with per-task status, *not* status
  columns. The first draft got this wrong.
- `category` in ecohub is a **work-stream**, a different axis from pursuit/delivery. The first
  draft collapsed both into one field; they are now `category` + `task_phase`.
- Seeded status graph mirrors ecohub's five: Not Started · In Progress · **Escalate** · Stuck ·
  Done. Escalate was missing entirely.
- **Escalate and Stuck force their context** via a dialog (a user to escalate to; a reason) and
  render it on the card. Guarded server-side, not just in the UI.
- Ported: the task-template **admin screen**. Adapted: ecohub's task→invoice link becomes a link
  to a quotation version / sample / PO. Not ported: `isServiceTask` (their service-job domain).
- **"My Tasks" does not exist in ecohub** — tasks live only inside a project there. It is a
  deliberate Sorento addition, justified by 10+ salespeople holding dozens of concurrent
  pursuits.

Task history is delivered as a **view**, backed by the existing audit listeners (which already
capture per-field diffs) rather than a bespoke `project_task_history` table. If the audit trail
can't render a per-task timeline cleanly, a dedicated table is the fallback — decided during
S2b implementation, not now.

### Ordering consequence

Because `next_action_date` is gone, the staleness nudge has nothing to key on until tasks
exist. **S2b must land before S5**, which it does. Between S2 and S2b there is deliberately no
next-action mechanism — that window is registration-only and short.

### Revised slice order

S0 prereq → S1 status engine → S2 registration/pipeline → **S2b task management** →
**S2c leads** → S3 quotations → S4 samples/sponsorship/POs → S5 forecast + staleness →
S6 MCP + PR/complaint linkage.
