# PLAN — Project Sales Pipeline (module `projects`)

**Status:** **In build.** Drafted from grill session 2026-07-25, review rounds 1-2 applied
(numbering / delivery lag / loss reasons made configurable; sponsorship flag pinned to
`respond_contacts`; task management added and decided - see §7).
Built: **S0, S1, S2, S2b, S2c, S3, S4, S5a, S5b, S6a, S6b** — every planned slice (see §4
for what each landed and what it discovered), plus a **hardening pass** over S5/S6 on
`chore/project-sales-hardening` (§5h: nineteen findings, each pinned by a test that fails on
the code as it shipped). Remaining known gaps are listed in the UAC
header and in §6: the Excel import (AC-C9/C9a), brand + architect intelligence (AC-I4 half),
the AC-N5a task-link picker, AC-G2's board-default-by-role, and the ~28 historical sponsorship
rows to be linked by hand (AC-F6).
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

**S0 — Prereq. DONE.** `app/rule_engine` turned out to be on `main` already, so the blocker
was stale; only `aggregates.py` and a shared `lazy_once` needed porting. The
resolver is company-scoped as well as owner-scoped (defense in depth: a fact feeding an
automatic transition must not lean on one layer). `rule_engine/registry.py`'s private
`_lazy_once` now delegates to the shared helper rather than forking it.
*Gate: 11 aggregate tests + 30 dependent tests green, no import cycle.*

**S1 — DONE.** Notes below; original scope statement retained after them.

Four things the build changed or found, worth carrying forward:

1. **A NULL-uniqueness bug in the source.** The upstream
   `UniqueConstraint(entity_type, tenant_id, scope_id, key)` is a **no-op for default
   graphs** on Postgres: NULLs compare distinct, so two `(project, NULL, NULL,
   'registered')` rows both insert. Both unique indexes here are `NULLS NOT DISTINCT`
   (PG 15+; this deployment is 17.5). Verified in both directions: duplicate default keys
   rejected, forks still free to reuse a key.
2. **`scope_attr` could not express a task's graph.** Upstream names a column on the
   record; a project task's graph belongs to its *project's* template, one hop away. The
   registry takes a `scope_resolver` callable instead, covering direct and indirect with one
   mechanism.
3. **`extractApiError` prefers `detail` over `message`.** Any `AppException` carrying a
   `detail` shows the user the detail and hides the message. Two errors here did that: the
   blocked-delete buried its record count behind an internal hint about the migrate
   endpoint, and the conflict handler would have shown a **raw Postgres constraint
   violation**. Both now put everything in `message`, and
   `test_user_facing_errors_never_hide_their_message_behind_detail` pins it.
4. **A duplicate key escaped as an unhandled 500.** The DB index is the guarantee, but on
   its own it surfaces as a Postgres constraint name. The route pre-checks in readable
   language and translates a genuine race to a 409.

Deliberately deferred, so nothing dead ships: time-conditioned auto edges (sorento's
staleness ladder is an `automations` row, which already owns scheduling), self triggers, and
the drag-and-drop graph editor. `derived.py` ships the trigger registry only; evaluation
lands with the one real auto edge in S4. The admin UI creates **manual** transitions only and
renders auto edges read-only, because authoring conditions needs the RuleBuilder.

*Gate: 71 tests green (33 engine, 19 route, 6 additive-proof, 11 aggregate, plus 2 new
error-shape tests); single alembic head; browser-verified through the sidebar (create status,
duplicate-key rejection reaching the toast verbatim, create transition, self-loop excluded
from the picker, both empty states), 0 console errors; **zero regressions** confirmed by
diffing the full suite against `main` (95 pre-existing failures in both trees).*

Original scope: `statuses` + `status_transitions` + StatusEntity
registry + transition service + admin screens. Drop `workflow_stages`. `category` NOT NULL.
Entity-default graph with per-template copy-on-write fork. Manual transitions only.
Regression pass proving no existing status vocabulary changed. → UAC Group B.

**S2 — Registration + parties + stakeholders + pipeline.** — **CORE DONE**, two items
deferred (below). Types, templates, template roles, projects, sales profile, parties,
stakeholders, brands M2M, the `pg_trgm` clash lock with the block/join/dispute flow,
board+grid, detail tabs (empty tabs render), project numbering. → UAC Groups A, C, D, G, J.

*Gate: 61 backend tests green (18 clash matcher, 4 registration, 10 access, 10 lifecycle,
5 status entity, 9 seed, 5 pre-existing engine files unaffected) + 16 vitest; single alembic
head (`310_project_clash_thresholds`); browser-verified through the sidebar with 0 console
errors — register dialog live clash preview blocking + context, sibling phase correctly NOT
blocking, board with 8 seeded columns, detail page 9 tabs all rendering, 375px width with no
page overflow and a reachable submit button.*

**Deferred out of S2, with reasons:**

- **Excel import (AC-C9, AC-C9a).** Needs the intra-batch duplicate detector, which is a
  second matcher entry point (group rows within the sheet, fail BOTH sides of a repeated
  `(developer, normalised_title)`). Shipping it half-done risks the exact silent-create it is
  meant to prevent. Belongs with its own tests.
- **Activities adapter (AC-H1/H2).** `last_meaningful_activity_at` is written and read (the
  board shows "45d quiet"), but nothing advances it yet because the whitelist of
  advancing events is defined by S2b tasks and S3 quotations. Wiring it now would mean
  wiring it twice.

**S2 findings (things the build discovered):**

| # | Finding | Resolution |
|---|---------|------------|
| F1 | Trigram similarity ranks sibling phases (`Phase 3A` vs `3B`, **0.818**) HIGHER than genuine abbreviations (`Ph 3B` vs `Phase 3B`, **0.762**). No single threshold separates them. | Blocking is not a function of similarity alone. Digit-bearing tokens are the discriminator: siblings when neither title's designator set contains the other's. |
| F2 | Symmetric `similarity()` scores a short title against its verbose twin at **0.312** — a real duplicate would sail through, since the live data has titles like `KSL Setia Alam Project  (733 units service apartment)`. | Score is `GREATEST(similarity, strict_word_similarity both directions)`. Containment now scores 1.0. |
| F3 | Calibrating over all **63 distinct live project titles** showed unrelated pairs sharing a generic noun (`IKI Hotel` / `The Jerai Hotel` 0.600, `Kami Residence` / `The Wyn Residence` 0.667) sitting above a single 0.55 bar. | **Two bars**, not one: surface at 0.55 (generous — a missed duplicate is silent), block at 0.70 (strict — a false block fired often teaches users to dismiss the warning). Both are `system_settings` columns per AC-C5. Final calibration on the real corpus: **1 block (the genuine reordered duplicate `Helicopter Centre in Subang` / `Subang Helicopter Centre`), 0 false blocks.** |
| F4 | The title is typed BEFORE the developer is picked, so a developer-scoped check stayed silent on the most common path. | The preview widens to every developer (`include_other_developers`); widened rows are context-only and can never block, since identity needs the developer. |
| F5 | A rename bypassed the lock entirely — register something innocuous, then rename onto a colleague's project. The DB unique index catches only the exact-key case. | The matcher runs on edit as well as create, excluding the project itself. |
| F6 | `tests/_pg_fixture.py` pins `search_path` to the scratch schemas, so `public.similarity` was invisible. | Schema-qualified the call in app code rather than widening `search_path` — that guard is what stops test SQL writing to the real prod-copy tables. |
| F7 | The status-engine test fixtures snapshot `_REGISTRY` BEFORE its lazy population fires, so restoring an empty snapshot permanently emptied the registry for the rest of the session (and `lazy_once` never re-runs). Only visible as another file failing when run after them. | Fixtures force `list_status_entities()` before snapshotting. |
| F8 | A per-type "create if missing" seeder resurrects a project type the team deliberately deleted, on every restart. | Seeding is skipped wholesale once the company has any type — same guard shape as the funnel. Pinned by a test. |
| F9 | Core knowing which modules supply status entities would violate ADR-0001. | Core knows a CONVENTION instead: `app/modules/<key>/status_entities.py` exposing `register()`, discovered generically. |

**S2b — Task management** (§7). **BUILT 2026-07-26.** Template task checklists,
`project_tasks` on the status engine as entity #2, work-stream sections + timeline + per-task
history, "My Tasks", and the template checklist admin screen (Project Sales -> Setup).

**S2b findings (things the build discovered):**

| # | Finding | Resolution |
|---|---------|------------|
| F10 | Escalating a task put it in nobody's worklist. `my_tasks` filtered on `assignee_user_id` only, and escalation deliberately does NOT reassign (it asks for help), so the escalatee never saw it. An escalation nobody can see is not an escalation. | "Mine" now means assigned to me OR escalated to me. Pinned by a test that seeds a task assigned to somebody else and escalated to me. |
| F11 | A task's forced context (escalate target, stuck reason) could not be collected in a second request without a window where the task sat escalated to nobody. | The dialog collects the context and sends it WITH the status id in one call; the server validates before writing. An ordinary rung skips the dialog entirely rather than asking for a confirmation of nothing. |
| F12 | The per-task history rendered the audit stamp 8 hours early: `audit_logs` timestamps are naive UTC and a bare `toLocaleString` treats them as local. | Uses the shared `formatDateTimeInMalaysia`, the same helper the audit list uses. Same family as the MCP `updated_at` bug. |
| F13 | The delete confirm for an in-use checklist item told the user it could not be deleted and then offered a Delete button the server was certain to refuse with a 409. | Two dialogs: the ordinary confirm when nothing has copied the item, and a "cannot delete" notice offering **Deactivate instead** (which is the action the copy recommends) when something has. |
| F14 | AC-N6 says a project's next action is derived from its earliest open task, but nothing surfaced it in the pipeline: the board card and grid predated tasks. | Board card and grid both show it, styled destructive when overdue, with an explicit "N open, none dated" state -- undated open work is not the same as nothing to do. |

**S2c — Leads** (§5a). **BUILT 2026-07-26.** `project_leads` on the status engine as
entity #3, select-or-create Customer wizard, qualify → runs the clash check and creates a
Project, disqualify + reason from a lookup set, lead→project conversion metric, and the
customer portfolio endpoint behind the account view.

**S2c findings (things the build discovered):**

| # | Finding | Resolution |
|---|---------|------------|
| F15 | Ecohub's five-rung project graph does not fit a rumour, and neither terminal rung can be reached by a status move: "qualified" with no project behind it, or "disqualified" with no reason, is a lie the conversion report then repeats. | Short lead funnel (New / Contacted / Qualifying + terminal Qualified / Disqualified). `change_lead_status` refuses the two terminal rungs with a 422 pointing at the Qualify and Disqualify actions, which do the work those rungs mean. The FE excludes them from the dropdown for the same reason. |
| F16 | A customer reaches its projects by TWO routes: its developer party is bridged to it, or a project was qualified out of one of its leads (the informant is often an architect who never buys). A single join under-reports the account. | `customer_portfolio` unions both and dedupes by project id, so a lead recorded against the developer itself does not render twice. |
| F17 | `/customers/select` returned 404 on a perfectly valid request: `customers.router` was mounted BEFORE `customers_select.router`, so `/{customer_id}` captured the literal word "select" and `validate_uuid_path` 404'd it as a missing customer. Pre-existing, and the lead wizard was the first thing to notice. | Mount order swapped, plus `tests/test_route_shadowing.py` asserting no literal leaf (select / metrics / export / my-tasks / ...) sits behind a same-prefix parameterised sibling anywhere in the assembled app. Same family as the `/sla/integration/escalate` bug. |
| F18 | The qualify route 500'd with `serialize_projects() got an unexpected keyword argument 'user_id'` while every service test passed: the lead serializer took `user_id` and the project one took `actor_user_id`, and the route mixed them. | Renamed the lead serializer's argument to `actor_user_id` so the two agree, and added `tests/test_project_lead_routes.py` -- route-level tests through FastAPI, which is the seam the service tests could not cover. Verified by reintroducing the bug and watching the new test fail. |
| F19 | The company-scope resolver runs as a router-level dependency and re-stamps the scope from the REQUEST, so a TestClient with no active company silently overwrote the fixture's pin with UNSET and every route returned 400. | The route-test fixture overrides `apply_company_scope`, which is what a real JWT carrying `active_company_id` does. Documented in the fixture so the next route-test author does not spend the same hour on it. |

**S3 — Quotations** (§5b). **BUILT 2026-07-26.** Quotations per scope, versions
(edit-in-place + Revise-freezes), lines with product snapshots, Project Series (category
allowlist), price floor rules (3 levels x percent|absolute), the two alerts stored on the
line, outcomes + loss reasons from a lookup set, derived project outcome. Pricing policy
gets its own admin screen (`/project-sales/pricing`) rather than a fifth section on Setup.
The management fan-out on a floor breach LOGS today and is wired to notifications in S5.

**S3 findings (things the build discovered):**

| # | Finding | Resolution |
|---|---------|------------|
| F20 | "Current version" as a stored `current_version_id` plus an `is_frozen` flag is two facts that must agree, and they stop agreeing the first time a write half-fails. | Neither column exists. Current is `MAX(version_no)` under `UNIQUE (quotation_id, version_no)`, frozen is anything below it, and both are server-DERIVED for rendering. The FE reads `is_current` and never re-derives it. |
| F21 | A price floor of zero and no floor policy at all are different answers, and a percent rule against a product with no list price is a third. Collapsing them would either block a legitimate free-issue line or silently accept anything. | `resolve_floor` returns `None` for "no policy", and a percent rule with no list price falls THROUGH to the next level rather than resolving to zero. Pinned by a 12-case golden set written failing first. |
| F22 | Recomputing the alerts on read means tightening a floor tomorrow retro-flags a quotation the customer already holds. | Both alerts plus the floor value and its level are STORED on the line at pricing time (AC-E7). A test tightens the policy afterwards and asserts the line does not change. |
| F23 | A level column on `price_floor_rules` could disagree with the keys, and nothing stopped an admin creating three competing company-wide rules. | No level column: it is implied by which key is set. The unique index uses `NULLS NOT DISTINCT`, which makes the system-level rule a singleton per company, and the route UPSERTS per target so editing "the Basins floor" means exactly that. |
| F24 | An off-catalog line with a series looked "standard" because there was no product to compare against the series. | Off-catalog is ALWAYS non-standard (AC-E5), series or no series, and the row says "Off-catalog" rather than showing an empty product cell. |
| F25 | The mutation hook toasted on a successful delete and so did `ConfirmDeleteDialog`, putting two notifications on screen for one action. | The quotation `remove` mutation raises no toast: the dialog owns success and error messaging because it is the only caller. |
| F26 | Resolving the floor in the browser to preview it would be a second implementation of the ancestry walk, and the two would eventually disagree. | The dialog does not evaluate the floor at all. The price is sent, and the answer that comes back is what the line shows -- with the rule that produced it named ("set on a parent category"), so the salesperson knows whose policy to argue with. |

**S4 — Samples, sponsorship link, POs** (§5c). **BUILT 2026-07-26.** Samples bound to
versions with the superseded block; Project POs in their own table with the two mismatch
flags, the erosion figure and the auto edge to PO Received; sponsorship `project_id` +
per-contact rollout flag + mandatory picker with a hard block, plus the spend rollup and
sponsorship-to-PO conversion. → UAC Group F.

**S4 findings (things the build discovered):**

| # | Finding | Resolution |
|---|---------|------------|
| F27 | AC-F2 blocks a sample against a superseded version, but says nothing about a sample recorded BEFORE the revise. Refusing to edit it afterwards would throw away the developer feedback, which normally arrives after the revise and is the one thing the sample exists to capture. | Create is blocked; EDIT is not, unless the binding itself changes (that is a new submission wearing an edit). The row states "Version superseded" rather than merely dropping a badge. |
| F28 | A PO must NOT inherit the sample rule. The contractor buys off the document they were given, which is frequently not the newest one, so refusing a superseded binding would make the PO unrecordable through no fault of the recorder. | POs accept any version, and the picker labels each one Current / Superseded. The sample picker offers only the current one, so it never presents a choice the server will reject. |
| F29 | `po_received` was reachable only from Quoted and Tendering, so AC-F10's auto edge silently did nothing on exactly the projects whose funnel was least well maintained. | Edges added from every live rung, plus `ensure_po_received_edges` -- idempotent and JOIN-shaped, because the funnel seeder is wholesale-guarded and would never reach an install that already has a graph. The move still goes THROUGH the engine; an illegal one records the PO and reports `status_moved_to_po_received: false`. |
| F30 | A freshly recorded PO with no lines and no amount rendered "100.0% below v1", i.e. "we gave the whole thing away". Found in the browser, on the first PO ever recorded. | Drift withholds BOTH numbers when the PO has no figure yet: a delta of -RM 35,000 is the same lie in currency as -100%. |
| F31 | A PO line recorded with only a `product_id` rendered as "Unnamed item" beside a mismatch badge -- useless, because the first question is WHICH item differs. | The product's code and description are snapshotted onto the line, and never overwrite what the PO actually printed: "WC-BLK-01 for our SRT-WC-01" IS the mismatch somebody needs to see. |
| F32 | `contact_to_response_dict` is built by hand, so the new rollout flag reached the DB but never the FE -- the toggle would have rendered its default forever. | Added to the manual dict, pinned by a test. Same family as the `get_user` / `get_me` drop-fields bug already in the lessons list. |
| F33 | `purchase_requests` has no `company_id`, so the conversion metric could not be scoped the way every other project number is. | Scoped through `projects` instead, which is the company that matters anyway; conversion is counted per PROJECT, not per form, so two sponsorships on one development that yields one PO is one conversion rather than two. |

**S5 — Forecast, staleness, worklist.** Split in two, because the forecast maths and the
staleness ladder share nothing but a slice number: the first is a read model over data that
already exists, the second is scheduling.

- **S5a — DONE.** Three-number forecast, per-status probability, configurable delivery lag
  with per-project override, management dashboard (Forecast &amp; Reports). Notes in §5d.
  → UAC Group I.
- **S5b — DONE.** Activity adapter + meaningful-activity whitelist, per-status staleness
  thresholds with fork-copy and reapply-defaults, the daily sweep on the existing scheduler,
  the three-rung ladder, and the notification fan-out S3 and S4 had only logged. Notes in
  §5e. → UAC Group H. **Not built:** "My Follow-ups" as a separate screen, because AC-H7's
  My Tasks (shipped in S2b) already answers "what do I owe, soonest first" and a second
  worklist reading the same tasks would be two places to keep in step.

**S6 — MCP read tools; then PR + Complaint linkage.** Split:

- **S6a — DONE.** Four read-only MCP tools, the resolver probes and UUID-coercion entries
  behind them, and the bootstrap that enables them. Notes in §5f. → UAC Group K.
- **S6b — DONE.** `project_id` on complaints (migration 318), the office-side picker on both
  the complaint and the PR / sponsorship form, and a resolved project CODE on both detail
  pages. Notes in §5g. → UAC AC-L3.

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

## 5b. Quotations (slice S3)

Six tables, and two of them are defined by a column they deliberately do NOT have.

```
project_series(id, company_id, name, brand_id→brands NULL, description, is_active)
project_series_categories(series_id, category_id→product_categories)   -- junction, no id

price_floor_rules(id, company_id, product_id NULL, category_id NULL,
        mode 'percent'|'absolute', value, notes, is_active, created_by)
  -- NO level column: the level IS which key is set.
  -- UNIQUE (company_id, product_id, category_id) NULLS NOT DISTINCT
  --   → the company-wide rule is a singleton, not something to create three of.

project_quotations(id, company_id, project_id→projects, scope_label,
        series_id→project_series NULL, notes, outcome 'open'|'won'|'lost',
        loss_reason, decided_at, created_by)
  -- NO current_version_id.

project_quotation_versions(id, company_id, quotation_id→project_quotations,
        version_no, frozen_at, issued_by→users, issued_on, total_amount, notes)
  -- NO is_frozen.  UNIQUE (quotation_id, version_no)
  -- current = MAX(version_no); frozen = anything below it.

project_quotation_lines(id, company_id, version_id→project_quotation_versions,
        product_id→products NULL, product_code_snapshot, description_snapshot,
        list_price_snapshot, image_attachment_id, unit_price, quantity, uom,
        unit_type, line_total,
        is_non_standard, floor_value_applied, floor_level_applied, is_below_floor,
        sort_order, notes)
  -- the four alert columns are STORED at pricing time, never recomputed on read.
```

**Floor resolution** walks product → its category → each ancestor category, nearest first
→ the company default, taking the first ACTIVE rule that produces a value. A percent rule
against a product with no list price produces nothing and falls through; the ancestry walk
is cycle-guarded and depth-capped. `None` means "no policy", which is not the same as a
floor of zero.

**Scope is the unit of outcome.** House Units and Common Area are won or lost separately,
so the PROJECT's outcome is derived: won if ANY scope is won, lost only when ALL are, open
otherwise -- and no quotations at all is open, not lost. The project's STATUS is never
touched by this (AC-E10a): status is a funnel position, outcome is a commercial result, and
a service that moved both would make the board disagree with the pipeline.

**Admin surface.** Series and price floors live on their own page,
`/project-sales/pricing`, not as two more sections on Setup. They answer the same question
from two sides -- what we are supposed to be selling, and how cheap it may go -- and a
scope can be perfectly on-series and still under-priced, which is only visible when the two
are read together.

## 5c. Samples, customer POs and the sponsorship link (slice S4)

```
project_samples(id, company_id, project_id, quotation_version_id, submitted_on,
        submitted_by, developer_feedback, salesperson_notes)

project_purchase_orders(id, company_id, project_id,
        quotation_version_id NULL ON DELETE SET NULL,   -- a PO outlives the quotation
        po_source 'contractor_direct'|'trading_house',
        issuing_party_id NULL, po_number, po_date, po_amount, notes)
  -- UNIQUE (project_id, po_number): a PO number belongs to its issuer, so it is unique
  --   per issuer at best. Twice on ONE project is the mistake worth stopping.
project_purchase_order_lines(id, company_id, po_id, product_id NULL, product_code,
        description, unit_price, quantity, uom, line_total,
        quoted_unit_price, model_mismatch, price_mismatch)   -- flags STORED, as AC-E7

purchase_requests.project_id NULL ON DELETE SET NULL   -- AC-F3, one form not two
respond_contacts.requires_registered_project BOOLEAN NOT NULL DEFAULT false  -- AC-F4
```

**Three deliberate asymmetries.**

1. **Sample vs PO on a superseded version.** A sample is refused (AC-F2), a PO is not. The
   sample is us sending something out, so we control which price it answers. The PO is
   them sending something in, off whichever document they were given.
2. **Mismatch vs drift.** A mismatch (AC-F9) is an exception to chase and reads as one. The
   erosion from v1 (AC-F9a) is the expected outcome of a negotiation and reads as a plain
   number. Presenting erosion as an alert would make every well-negotiated PO look broken.
3. **Required vs permitted on a sponsorship link.** The per-contact flag decides whether a
   project is REQUIRED. It never decides whether a link may be WRONG: a sponsorship
   attached to somebody else's project corrupts that project's spend rollup either way, so
   ownership is checked for flagged and unflagged contacts alike.

**The rollout is per contact on purpose.** Sorento wants to require a registered project
from the salespeople they have briefed without breaking the form for everybody else on the
same morning. `false` by default is what makes the migration deployable with no flag day.

**Deferred, and named in the UAC:** the ~28 pre-link sponsorship rows are linked BY HAND
(AC-F6). No fuzzy backfill writes a link nobody checked -- a wrong link is worse than no
link, because the rollup then reports a number somebody will act on.

## 5d. Forecast and reporting (slice S5a)

No new tables. The forecast is a **read model** over quotations, POs and the funnel, plus
three configuration dials:

```
statuses.win_probability      NUMERIC(5,2) NULL   -- AC-I2, NULL means "nobody decided"
statuses.stale_after_days     INTEGER NULL        -- AC-H4, consumed by S5b
system_settings.project_delivery_lag_months  INTEGER NOT NULL DEFAULT 30   -- AC-I3
```

**Three numbers, and the separation lives in the LAYOUT, not just the data (AC-I1).**
Committed stands alone and is labelled as banked. Pipeline and Weighted share a visually
distinct dashed band marked "Speculative / Not revenue" (AC-I2a). There is **no total field
in the response schema and no total on the page**, deliberately: a single figure mixing a
signed PO with a 10%-probability rumour is precisely the number this module exists to stop
producing. A vitest asserts the absence, including the arithmetic sum of the fixture, so a
future "helpful" total card fails the suite rather than shipping.

**Why NULL rather than a default probability.** An unconfigured rung has no opinion, and
inventing 50% puts a number in front of management that nobody chose. A status with no
probability contributes zero to Weighted. The seeder does supply a **starting ladder**
(10/25/40/60/75/100, Lost and Dormant a real 0) because a Weighted column that reads zero on
day one is not evaluable, but it fills a NULL only and never overwrites: any value at all,
including a deliberate 0, means somebody expressed an opinion. `ensure_win_probabilities` is
its own idempotent step for the same reason `ensure_po_received_edges` is - the funnel seeder
is wholesale-guarded and would never reach an install that already has its graph.

**Undated money is reported, not dropped.** A project with neither a launch date nor an
explicit delivery window lands in an `undated` band that the page renders as a "No date yet"
row. Dropping it would make the year buckets disagree with the headline totals, and the first
person who adds up the columns stops trusting the report. Same instinct as `rate: null`
instead of `0%` wherever nothing has been decided yet.

**The assumption is printed on the page.** "Launch date plus 30 months, unless a project
states its own window" renders from the live setting, so a forecast nobody can interrogate
does not get argued with in a meeting.

### S5a findings (browser and test)

| # | Finding | Resolution |
|---|---------|------------|
| F34 | The seeder left every `win_probability` NULL, so Weighted read RM 0.00 on a fresh install and the column looked broken rather than unconfigured. | Seeded starting ladder, NULL-only backfill, three tests: the ladder climbs, a tuned 0 survives reseeding, and an existing graph gets backfilled. |
| F35 | A forecast test asserted "no probability contributes nothing" by relying on the seeder leaving NULLs - true until F34, then silently testing the wrong thing. | The test now ARRANGES the NULL explicitly. The behaviour is unchanged; what changed is that the test states its own precondition instead of inheriting it. |
| F36 | `test_the_funnel_is_not_fully_connected` still asserted Identified cannot reach PO Received - an intent S4's F29 deliberately overruled, so it had been red since S4. | Rewritten around what the funnel actually guarantees: the forward ladder is one rung at a time (no skipping to Quoted/Tendering/Specified), and only the three ENDINGS short-circuit it. Asserted as an exact set, so a future stray edge fails. |

## 5e. Staleness ladder and activity events (slice S5b)

No new tables again. The feed reuses `activity_events` through the generic activities registry
(AC-H1); the ladder adds three columns and one cron row:

```
projects.stale_level   INTEGER NOT NULL DEFAULT 0   -- 0 fine / 1 nudge / 2 warn / 3 unattended
projects.stale_since   TIMESTAMP NULL               -- when it ENTERED the ladder
projects.stale_reason  VARCHAR(16) NULL             -- overdue_task | no_activity
scheduled_tasks('project_staleness_sweep', daily)   -- seeded in migration 317
```

**Where AC-H5 was followed in spirit, not to the letter.** The AC says the sweep is an
`automations` row. It is not: `automations.email_template_id` is NOT NULL and `action_type`
defaults to `send_email`, so that table models "send this template to these recipients on a
schedule". The ladder writes state, an activity row, in-app notifications AND emails, and
flips a badge, so putting it there would have meant a dummy email template plus an action type
the runner does not understand. It is a `scheduled_tasks` row instead, on the SAME heartbeat
that already runs `form_sla_overdue_scan` and `takeover_request_commit`. The AC's real
requirement -- **no new scheduler** -- is met, and running it by hand uses the existing
`POST /scheduled-tasks/{id}/run-now`, so there is no bespoke admin route either.

**Two triggers, in priority order (AC-H3).** An overdue next action wins over inactivity: a
project worked on yesterday that carries a task due three weeks ago is not idle, it is late.
A project with an IN-DATE open task is off the ladder entirely regardless of how quiet it has
been -- having a plan is the work, and nagging somebody whose site visit is booked for
Thursday is how a tool teaches people to ignore it.

**One threshold, three rungs.** `stale_after_days` is the nudge point; twice it warns the
owner and copies management; three times marks the project Unattended. Multiples rather than
three configured numbers, so an admin who tunes one number cannot produce a ladder where
level 2 fires before level 1. Seeded 21/30/21/14/7 down the funnel and deliberately absent on
terminal rungs, which therefore never go stale.

**"Management" now means exactly one thing** (`projects.projects.view_all_financials`, G20),
resolved from RBAC in `project_notify_service`. That is what unblocked the two fan-outs S3 and
S4 shipped as log lines: the floor breach (management only -- the person who typed the price
does not need telling what they just did) and the PO mismatch (owner AND management, because
a PO that disagrees with the quotation becomes a delivery dispute). Price erosion from v1
still deliberately does not notify (AC-F9a).

**Nothing auto-reassigns.** Level 3 changes what colleagues are ALLOWED to ask for; the
takeover request UI from S2 is the route, a manager still decides, and the badge copy says so
in as many words.

### S5b findings (browser and test)

| # | Finding | Resolution |
|---|---------|------------|
| F37 | `func.upper(User.status)` passed every test and died on the first real sweep: `function upper("UserStatus") does not exist`. The live column is a Postgres ENUM; the MODEL declares it `String`, so the blank schema built from the models accepted `upper()` happily. | Plain equality, which works for both. Plus a test that runs the recipient query against the REAL schema (read-only, rolled back) -- any query touching a legacy column type needs at least one such exercise, because a model-built test schema cannot see the mismatch. |
| F38 | A failing notification took the whole sweep down with it. The recipient query raised, which poisoned the session, and the sweep's own `db.commit()` then died with `InFailedSqlTransaction` -- so a broken mailer discarded every correctly-identified stale project. "Best-effort" had only ever been tested against a Python exception, never a failed SQL statement. | The ladder commits BEFORE any notification is attempted, and each attempt rolls back a poisoned session so project two is not punished for project one. Pinned by a test that makes `_notify` raise and asserts the level survived. |
| F39 | `begin_nested()` around each notification looked like the right isolation and was not: `NotificationService` commits internally, which closes the savepoint under it (`Can't operate on closed transaction inside context manager`) and turned all three sends into failures. | Per-project try / rollback-if-inactive instead. The savepoint was solving a problem the commit-first ordering had already removed. |
| F40 | Moving the stage cleared the staleness banner instantly but the Activity tab still showed the old events, so the page disagreed with itself about what had just happened. | The feed is keyed on `updated_at` and `stale_level`, not just the project id -- the same rule the SLA banner follows. Verified in the browser: the status POST is followed by a project refetch AND an activities refetch. |
| F41 | The pipeline card guessed staleness with a flat `days_since_last_activity >= 30`, which is simultaneously too slack at Registered (30 days is normal) and far too generous at Tendering (a week of silence is a lost tender). | The card reads the server's stamped rung. Its test moved with it, and now asserts the rung's WORDING rather than a day count. |

## 5f. MCP read tools (slice S6a)

Four read-only tools (`crm_projects_list`, `crm_project_detail`, `crm_project_quotations_list`,
`crm_project_forecast`), all GET, all `module="projects"`.

**Name lookup obeys the UUID-first contract instead of breaking it.** AC-K1 asks for "project
lookup by name/developer", and the obvious way to give it -- a `query` param on the list tool --
is forbidden by the MCP package's own invariant (`test_no_freetext_query_on_data_list_tools`),
for good reason: two phases of one masterplan have near-identical titles, and a fuzzy match
that silently picks one answers a question about the wrong pursuit. So the path is the
established two-call one: `_probe_project` and `_probe_project_party` were added to the entity
resolver (exact, whitespace- and case-insensitive, on project code / title / party name), and
`project_ids` / `project_id` / `developer_party_ids` were registered in
`_UUID_PARAM_ENTITY_TYPES` so the dispatch layer substitutes the resolved UUID into the tool
call. The one non-UUID filter is `status_key`, and that is deliberate: `key` is the documented
stable identity per entity_type (G3), so "tendering" is an identifier, not a search term.

**Errors are answers, not 500s.** An unparseable `developer_party_ids` returns 400 and an
unknown `status_key` returns 422 naming the valid rungs. Both had to be re-raised past the
route's blanket `except`, which was turning them into "internal error" -- an agent told the
server is broken retries, while an agent told its argument is wrong fixes it.

**The forecast tool's description carries the no-blending rule** (AC-I1). A test asserts the
words are still there, because that description is the only place the rule reaches the model:
an agent that reads three numbers with no warning will add them up in prose.

### S6a findings (all four found by CALLING the tools, not by reading code)

| # | Finding | Resolution |
|---|---------|------------|
| F42 | Every project route used `require_permission`, which is JWT-only. The MCP server presents `X-API-Key` with an act-as user, so all four tools returned `401 Authentication required` -- the tools were correct, registered, enabled, and completely unusable. | The four routes the tools call switched to `require_permission_with_api_key` (permission still enforced, against the act-as user). Every WRITE route deliberately keeps plain `require_permission`, so AC-K2 is a property of the API surface and not only of the catalog -- pinned by a test that POSTs with a key and expects 401/403. |
| F43 | 401 then became **403**. Integration principals (`sorento-mcp`, `n8n`, `foundryx-esb`) were seeded with the ADMIN permission set as it stood at THEIR seed time; nothing back-fills a permission a later module introduces. Every project tool would have 403'd forever while looking perfectly configured. | `project_mcp_bootstrap` grants exactly `projects.projects.view`, only to roles an `integrations.act_as_user_id` resolves to, only where missing. Narrow on purpose: a boot that widened a human role would be a security incident waiting to be found. |
| F44 | AC-K1's "seed the `agent_mcp_tools` links" has no target: that table and the tool-to-agent ownership model were removed when n8n took over routing (see the `McpTool` docstring). | The intent -- a shipped tool nobody has to enable -- is met against `AIAssistantConfig.enabled_tools`, which is what the assistant's RAG actually selects from, the same list `it_support_bootstrap` maintains. Recorded here rather than silently reinterpreted. |
| F45 | Locally the backend imports `sorento_crm_mcp` from the MAIN checkout, not from this worktree, so `sync_catalog` reported 35 tools while the worktree catalog has 39. | Environment artifact, not a defect: one tree ships. Verified instead by running the worktree's MCP server on port 8766 and calling every tool over Streamable HTTP -- which is how F42 and F43 surfaced at all. |

## 5g. PR and complaint project linkage (slice S6b)

```
complaints.project_id  UUID NULL  REFERENCES projects(id) ON DELETE SET NULL   -- AC-L3
-- purchase_requests.project_id already existed (S4, AC-F3)
```

**SET NULL, never CASCADE.** A complaint is a customer's problem and a legal record. It has to
outlive the pursuit it happened to be attached to, so deleting a project unlinks its complaints
rather than erasing them -- pinned by a test that deletes the project and asserts the complaint
survives with its typed `project_title` intact.

**The free text stays.** `project_title` is the only project information on thousands of
historical rows and remains the display fallback, exactly as AC-F6 decided for sponsorships. No
fuzzy backfill writes a link nobody checked.

**Both surfaces resolve a CODE.** The picker's option label and both detail pages show
`PRJ-000142 - Residensi Damai`, never a UUID. That is not a UI nicety: the portal already
resolved `project_code` for contacts since S4, and the office-side read did not, so the same
link rendered as a code in one place and as nothing in the other -- which reads as a broken
link rather than as two code paths. Complaints resolve it in `_serialize_complaint`; PRs get it
stamped onto the row in `get_request`.

**One implementation of the picker search**, exported from the complaint feature's service and
re-exported by the PR one. Two copies would drift the first time one of them starts showing the
developer name.

### S6b findings (browser)

| # | Finding | Resolution |
|---|---------|------------|
| F46 | Wrapping `SearchableSelect` in `FormControl` threw `React.Children.only expected to receive a single React element child` and took the whole card down -- the field never rendered at all. `FormControl` is a Radix `Slot`; the component renders a trigger plus its popover. | Render `SearchableSelect` directly under `FormItem`, with `FormMessage` after it. The other complaint-form usages nest it inside another component, which is why the pattern looked safe. |
| F47 | The linked project showed nothing on the complaint detail page after the change was deployed, because :8010 runs WITHOUT `--reload` and was still serving the pre-change serializer. | Restarted. Third time this exact thing has cost a verification round in this module (S4, S5b, here) -- it is in the module memory now, but the honest fix is `--reload` locally. |

## 5h. Hardening pass (self-review, 2026-07-28)

Not a slice: a review of everything S5 and S6 shipped, on its own branch
(`chore/project-sales-hardening`), reading the code against how the rest of the system behaves
rather than against the ACs it was written from. Every finding below is pinned by a test that
fails on the code as it shipped.

**One theme explains most of it: the feature tests only ever ran request-shaped sessions.**
`conftest` defaults a session's company scope to Sorento, so the daily sweep's *unscoped*
session and a second company's user reaching a project by id were never exercised at all. The
guard tests live in `tests/test_project_hardening.py`, `tests/test_project_activity_access.py`
and `sorento_crm_mcp/tests/test_projects_sanitizer.py`.

| # | Finding | Resolution |
|---|---------|------------|
| F48 | The nightly staleness sweep runs from the scheduler on a bare `SessionLocal()`, whose company scope is UNSET. Scoping is fail-closed, so UNSET resolves to `false()`: the sweep selected zero projects, stamped nothing, notified nobody and logged a healthy-looking `scanned: 0` for ever. | `sweep()` calls `set_company_scope(db, None)` before reading anything, the way every other background job does (`export_tasks`, `import_tasks`). Guarded by a test that sets the scope to UNSET first, which is the one thing the harness never does. |
| F49 | Committed summed `po_amount` alone, so a PO entered line by line with no header figure -- which is what the PO lines editor produces -- was valued at exactly zero. Committed is the one number on the page that claims to be banked money. | `_committed_by_project` applies the module's single definition of a PO's value (`po_total`: the lines when there are any, else the header) in two bulk queries, so a hundred POs stay two round trips and the report can never disagree with the PO detail page. |
| F50 | A project whose remaining scopes were lost has outcome `lost`, and the forecast dropped the whole project -- taking its already-banked PO out of Committed with it. The number reporting what was ORDERED went down when something else was lost. | Lost projects that carry a PO are folded back in for Committed only. Pipeline and Weighted still ignore them (no open quotation, and the estimate is suppressed once anything was priced), and `project_count` stays live-only so "how many are we chasing" is not answered with the ones we lost. |
| F51 | The project activities adapter shipped with `can_view=None`. That gate is opt-IN, so any holder of `projects.projects.view` could read and post on ANY project id, including another company's -- `activity_events` is not company-scoped and nothing in the path ever loaded the project. A post also resets the staleness clock, so a foreign post could clear another company's Unattended badge. | `project_activity_service.can_view` resolves the project through the request's SCOPED session, so a project outside the caller's companies simply does not exist to them. Guarded with a real second company, not a hypothetical one. |
| F52 | The MCP project payloads carried nine internal UUIDs (owner, developer, status, company, ...) into the model's context, against the no-UUIDs rule and the promotions-list precedent. | `_slim_project_row` drops them in the MCP server. `id` deliberately stays: `crm_project_detail` and `crm_project_quotations_list` take it. |
| F53 | The below-floor alert deduplicated on the line id alone, and dedup is permanent -- so the FIRST breach on a line silenced every later one. A line re-priced above its floor and later dropped below it again is a new decision somebody has to approve, and it was invisible. | `floor_breach_dedup_key` keys on (line, price) with a normalised Decimal, so the same breach saved twice still dedupes while a different give-away alerts. |
| F54 | `crm_projects_list` advertises `owner_user_ids` as "my pipeline", and nothing in the system could produce that UUID from a name: the entity resolver had no `user` probe, and the (correct) payload slimming means rows carry `owner_name` only. "What is Ali working on" was unanswerable in both directions. | `_probe_user`: exact (whitespace and case insensitive) match on full name or work email, ACTIVE users only, plus `owner_user_ids` / `owner_user_id` in the dispatcher's coercion map. Exact and active-only on purpose: a fuzzy staff match reports one salesperson's numbers as another's, and answering about somebody who left is worse than not finding them. |
| F55 | The dispatcher's fallback resolver passed the arg value to `resolve_references` as a free-text QUERY, so `extract_candidate_tokens` (code-like tokens only) reduced a bare person or company name to nothing. Every name-shaped value returned `[]`: only values already resolved earlier in the turn ever coerced. System-wide, not project-only. | The value is passed as a TOKEN LIST -- it IS the token, there is nothing to extract -- filtered to the param's entity type, with the embedding fallback off so a plausible-but-wrong neighbour cannot silently answer about the wrong record. |
| F56 | The staleness alert deduplicated on `<project>:stale:<level>`, which means the level-1 nudge could fire at most ONCE in a project's lifetime. A project chased back to life and neglected again a quarter later was swallowed as a duplicate. | `stale_dedup_key` carries the episode (the moment the project went quiet), so repeated sweeps inside one episode still dedupe -- the property the key was actually protecting -- while a second period of neglect alerts. |
| F57 | The sweep selected open projects only, and nothing else clears the ladder except a human posting an activity. A project that reached Unattended and was then WON kept `stale_level = 3` for ever: the badge accused the team of neglecting the deal they had just won, and level 3 is the gate that lets colleagues ask to take a project over. | The sweep also selects anything still carrying a rung. `evaluate` already answers "not on the ladder" for a decided project, so those rows fall out through the normal cleared path with no special case. |
| F58 | `_lost_projects_with_committed_money` excluded the live set with `~Project.id.in_(live_ids) if live_ids else True`, handing a bare Python `True` to `filter()` for any company with no live project -- and the exclusion was redundant, since the live set excludes lost projects by definition. | Clause removed. Guarded by a forecast over a company whose only project is lost with a PO, which is a real early-company state. |
| F59 | `delivery_year` loaded the project's sales profile itself, inside the per-project loop, so the report cost one extra SELECT per project on a page a sales manager refreshes all day. | The profile is bulk-loaded once and injected, the same way `lag_months` already was. Pinned as a ratio (doubling the projects must not change the query count), not an absolute count, so a legitimate new query does not fail the test. |
| F60 | `project_notify_service._send` wrapped the WHOLE recipient loop in one try/except, so the first manager whose delivery raised swallowed every remaining manager. Best-effort is meant to be per recipient, not per alert -- a price gets approved below floor because two of three managers never heard about it. | Per-recipient try, with a rollback when a failed statement leaves the transaction aborted so recipient two is not punished for recipient one. The outer try still covers building the service, which works for everybody or nobody. |
| F61 | The Forecast page gated its entire body on `forecast.project_count > 0`. Once F50 made that count live-only, a company with a banked PO and no live pursuit rendered "Nothing to forecast yet" above a real committed figure. | The empty state now tests for money as well as pursuits (`hasMoney`, which reads the decimal STRING as a number -- `"0.00"` is truthy as a string). |
| F62 | Test hygiene, found by being bitten: four fixtures rebound `svc_module.resolve_references` with a bare assignment and never undid it, so the stub stayed installed for every test that ran later in the session. The visible damage was the reverse of a stub's intent -- a WORKING resolution path failed with "lambda() got an unexpected keyword argument", in a file that stubs nothing, only in a full-suite run. Separately, `test_ai_prompt_registry` asserted a hardcoded `11` prompt keys, so every module that adds a node (SCM added two) fails four tests that say nothing about seeding. | All four sites go through `monkeypatch`, plus a `conftest` backstop that restores the symbol after each test (same family as the existing column-type backstop). The prompt-key counts are derived from `PROMPT_KEYS`. |
| F63 | The payload slimming stopped at the two project tools; `crm_project_quotations_list` still carried `project_id` (which the caller passed in to get the list), `current_version_id` (nothing consumes it) and `issued_by` beside the `issued_by_name` the agent should quote. | One shared `_slim_rows(data, drop_keys)` now serves both, so the project and quotation paths cannot drift. The quotation `id` stays: it is the only handle on "the bathroom package quotation" on the next turn. |
| F64 | `can_view` compared the raw path value to a uuid column, so a malformed id raised INSIDE Postgres. The generic gate catches it and answers a correct 404 -- while leaving the transaction ABORTED, so the next statement in that request fails for an unrelated reason. | The id shape is validated before the query, and a failed lookup rolls back an inactive session. Guarded by asserting the session still works after a junk id, which is the half the 404 was hiding. |
| F65 | The Unattended message told the owner "Colleagues can now ask to take it over", and three docstrings called level 3 the gate on takeover requests. There is no such gate: `create_takeover_request` has no stale-level check, because the same endpoint is AC-C7's recourse for a registration this project BLOCKED -- and a blocked registrant cannot wait for somebody else's project to go stale. The system was announcing a permission change that never happened. | Wording corrected on both surfaces (notification body and the FE badge sentence) to say what actually changes: the neglect becomes visible to everyone, and a colleague can ask to take it over -- which was always true. The gate was NOT added: gating it would break AC-C7. AC-H6's "opens the project to takeover requests" is therefore met by the badge, recorded here rather than silently reinterpreted. |
| F66 | S6b resolved the complaint's `project_code` inside `_serialize_complaint`, which the complaints LIST calls once per row -- one extra SELECT per linked complaint. That serializer's whole `*_override` convention exists because a 50-row page used to fire per-row view-token, user and SLA queries, so the fix re-introduced the exact pattern the file warns about. | `_batch_project_display` resolves the page's linked projects in one query and rides in as `project_display_override`; the single-row detail path keeps its own lookup. Pinned as a ratio (more linked rows must not mean more queries), and both perf guards were verified to FAIL with the batching removed rather than trusted because they were green. |

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
- **A deepening breach never re-alerts.** The floor event fires on the TRANSITION into breach
  only (`is_below_floor and not was_below`), so a line moved from 5% below its floor to 60%
  below is silent - deliberately, to avoid an alert storm on the negotiation people are
  concentrating on. Noticed while fixing F53 and left as shipped, because "how much deeper
  counts as a new decision" is a client question, not a code one. If they want it, the trigger
  is a percentage-worsening threshold, and the dedup key already carries the price so the
  alerting side needs no further change.
- **`ai_assistant_configs` is a singleton by convention only** (noticed during the 2026-07-28
  hardening pass, deliberately NOT fixed there). Every reader -- including this module's MCP
  bootstrap -- does `db.query(AIAssistantConfig).first()` with no ORDER BY, so a second row
  would split the assistant's configuration non-deterministically between readers: the same
  class of bug as the `system_settings` duplicate that made settings saves silently disappear
  (migration 253). One row exists today and nothing enforces it. The fix is a unique index on a
  SHARED table, which belongs on a branch that owns that table rather than on a module hardening
  branch, where an extra migration would fork the alembic head.

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
