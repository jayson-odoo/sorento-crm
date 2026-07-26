# UAC — Project Sales Pipeline (module `projects`)

**Status:** S0, S1, S2, S2b and S2c built (2026-07-26). Groups B, C, D, G, J, N and O
are implemented and browser-verified except where noted below; A is implemented apart from
the Excel import. Remaining slices S3-S6 unstarted.

**Verified against a running stack, not asserted:** every AC below marked ✅ was exercised
either by a test that fails without it or in the browser at localhost:3010/:8010. ACs that
did NOT ship are marked ⏸ with the reason, rather than being quietly left ambiguous:

- ⏸ **AC-C9 / AC-C9a (Excel import).** Needs its own intra-batch duplicate detector — rows
  grouped within the sheet, BOTH sides of a repeated `(developer, normalised_title)` failed.
  Half of that is worse than none: it would create exactly the silent duplicate the module
  exists to prevent.
- ⏸ **AC-H1 / AC-H2 (activities adapter).** Partly un-deferred by S2b: creating or
  completing a task now advances `last_meaningful_activity_at` (AC-N8), which is the first
  entry in the AC-H2 whitelist. The quotation and sample events still wait for S3/S4, and
  the shared activity FEED (notes, mentions) is untouched.
- ⏸ **AC-N5a (link a task to a quotation version / sample / Project PO).** The columns, the
  schema and the API accept the link, but there is no picker in the UI: none of the three
  targets exists before S3/S4, so the picker would have nothing to offer.
- ⏸ **AC-G10 (delete blocked by a Project PO).** The guard ships and is written against
  `information_schema`, so it is already correct — but the `project_purchase_orders` table
  arrives in S4, so it currently has nothing to find.
- ⏸ **AC-G2 (board default per role).** The Board/Grid toggle and per-user persistence ship;
  defaulting Board for sales and Grid for management needs the role read, deferred with the
  rest of the role-aware UX.
**Slug:** project-sales-pipeline
**Source:** `Sorento Project Management Process Flow.pdf` (6pp) + client feedback on
registration roles + grill decisions recorded in `documentation/CONTEXT.md` and
`documentation/adr/0001..0004`.

Glossary is binding: see `documentation/CONTEXT.md`. Where this document and the PDF
disagree, the deviation is called out inline with a **[DEVIATION]** tag and a reason.

---

## Group A — Module, scope, tenancy

- **AC-A1** `projects` exists in `app_modules_catalog` with `is_core=false`, dependencies
  `["product", "order", "procurement"]`, and every route wrapped in
  `require_module_enabled_with_api_key("projects")`.
- **AC-A2** All module tables live in `public` with normal FKs to `products`, `customers`,
  `brands`, `users`, `attachments`.
- **AC-A3** `projects` and every owned child table carry `CompanyScopedMixin`. A user in
  MOCHA context sees zero SRT projects; a leak test asserts this for every table in the module.
- **AC-A4** Disabling the module hides the "Project Sales" sidebar group and 403s its routes,
  while the existing "Project Sales Admin" group (Purchase Requests, Sponsorship Forms,
  guarded by `procurement`) continues to work unchanged.

## Group B — Status engine (ships as slice 1, ahead of the module)

- **AC-B1** `statuses` and `status_transitions` exist as CORE tables; a code-side
  `StatusEntity` registry backs `GET /api/v1/status-entities`. `workflow_stages` is dropped.
- **AC-B2** Cross-template reporting groups by `statuses.key`, which is stable per
  `entity_type` and part of the `(entity_type, tenant_id, scope_id, key)` unique constraint —
  so a forked graph's "Sampled" rung carries the same key as the default's. `category` stays
  nullable and cosmetic (the source model marks it legacy). A test asserts two forked graphs
  roll up correctly by key.
- **AC-B2a** Statuses are **global** — no `company_id`, not `CompanyScopedMixin`. All ported
  PKs and FKs are `UUID(as_uuid=False)`, never `String`.
- **AC-B3** An entity has a default graph. A Project Template that overrides forks a full
  copy of the graph (copy-on-write) scoped to that template; templates that never override
  resolve to the default. Changing the default afterwards does **not** alter a forked graph.
- **AC-B4** A transition not present in the graph is rejected server-side with 422, regardless
  of what the client sends. Dragging a card to an illegal column shows the error and the card
  returns to its origin.
- **AC-B5** Deleting a status that records reference is blocked; the API offers migrate-records
  to another status instead.
- **AC-B6** The slice is provably additive: a grep-backed test asserts **no code path reads
  `workflow_stages`** (which is then dropped), and that no existing status column on
  complaints / PR-SF / stock inquiries / orders is read from or written to by the new engine.
  No behavioural regression suite is claimed — nothing in those flows is touched.
- **AC-B7** Prereq: `feat/promo-expiry-rule-engine` is merged (carries `app/rule_engine`), and
  `aggregates.py` + a `lazy_registry` helper are ported.

## Group C — Project types, templates, registration

- **AC-C1** Project Types are configurable records (seeded: Property Development, Hotel,
  Commercial Fitout, Renovation, Institutional). Adding a type needs no deploy.
- **AC-C2** A Project Template belongs to a type and owns its Stakeholder role list and,
  optionally, a forked status graph. A Project is created **from** a template.
  **[DEVIATION]** The PDF assumes property developments only; ~half the existing free-text
  project names are hotels, fitouts and renovations, so type is configurable.
- **AC-C3** Registration captures: developer (Project Party FK), registered company/SPV,
  project title, location, architect, main contractor, estimated sales value, brands
  (multi-select from `brands`), assigned salesperson, project launch date, project type +
  template.
- **AC-C4** Launch date is required for Property Development type and optional otherwise;
  non-development types require an explicit expected delivery window instead.
- **AC-C5** Creating a registration runs a `pg_trgm` similarity check against registrations of
  the same developer in the same company. `developer_party_id` and `normalised_title` live on
  **`projects`** so the DB unique constraint `(company_id, developer_party_id,
  normalised_title)` is enforceable in one table. A GIN `gin_trgm_ops` index backs the
  similarity query; the threshold is a system setting.
- **AC-C6** Only projects whose derived outcome is **open** block the create. A match that is
  lost or dormant is shown as context ("previously pursued by Ali, lost on price, Mar 2024")
  and the registration proceeds — a re-tender must not be blocked forever by an old loss.
- **AC-C6a** On a blocking collision the create is refused. The response renders the incumbent:
  owner name, current status, last activity date, brands, estimated value.
- **AC-C7** From the collision screen the user can *Request to join as collaborator* (owner or
  manager approves; on approval they gain edit rights) or *Dispute / request takeover*
  (routes to the sales manager with a mandatory reason). Both raise a notification.
- **AC-C8** Project code is generated by the existing `NumberingService` as a **configurable
  numbering rule** — prefix, padding and any date segment are editable in Settings without a
  deploy. Seeded default `PRJ-000123`. Unique, and shown wherever the project is referenced.
  No UUID appears in the UI. `numbering_rules.doc_type` is unique with no company column, so
  the sequence is **shared across companies** and codes are globally unique — MOCHA's first
  project may be `PRJ-000247`. Accepted.
- **AC-C9** A bulk Excel import creates projects through the *same* validation path.
  Collisions are reported as job errors in the upload-activity drawer; nothing is silently
  created or silently skipped.
- **AC-C9a** The importer also detects **intra-batch** duplicates: rows are normalised and
  grouped within the sheet, and a repeated `(developer, normalised_title)` fails **both** rows
  with an error naming the row numbers. Neither is created — import order never decides
  ownership.

## Group D — Parties and stakeholders

- **AC-D1** `project_parties` is an organisation master with `party_type` ∈ developer,
  architect, main_contractor, trading_house, consultant, and an optional `customer_id` bridge
  set only when that party actually issues a PO.
- **AC-D2** A party is reusable across projects, and its detail page lists every project it
  appears on with outcome — this is what makes "which architects to prioritise visiting"
  answerable.
- **AC-D3** `project_stakeholders` is per project: person name, phone, email, optional
  `party_id` (their firm), `role_id` (from the template's role list), influence, is_primary,
  notes. A stakeholder with no firm is valid.
- **AC-D4** The same person recorded on two projects may hold different roles on each; there
  is no global person master.
- **AC-D5** Seeded template roles: Decision Maker, Influencer, Info Provider, Architect.
  **[DECISION]** Info Provider carries **no** special visibility — visible to anyone who can
  see the project.

## Group E — Quotations and versions

- **AC-E1** A project has many quotations, each with a scope label (e.g. House Units, Common
  Area / Facilities, Showroom).
- **AC-E2** Editing the current version saves in place and writes an audit-trail entry. It
  does **not** create a version.
- **AC-E3** **Revise** freezes the current version exactly as it stands and opens the next
  version for editing. A frozen version can never be edited again.
- **AC-E3a** There is **no `current_version_id` and no `is_frozen` flag**. Current is
  `MAX(version_no)` per quotation; every lower version is frozen. One fact, no drift.
  `UNIQUE (quotation_id, version_no)`.
- **AC-E4** Lines carry: `product_id` (nullable), snapshot of product code / description /
  image ref / unit price, quantity, UOM, unit type (house unit / bathroom / facility / common
  area), line total. Snapshots mean a later catalog price change never rewrites quoted history.
- **AC-E5** A line whose product's category is not in the nominated Project Series raises a
  **non-standard SKU** alert on the quotation and notifies management. An off-catalog line
  (`product_id IS NULL`) always raises it. Nominating a **parent** category into a series
  covers **all its descendants** (`product_categories.parent_category_id` is a real hierarchy).
- **AC-E6** A line priced below its effective floor raises a **below-minimum price** alert:
  warning to the salesperson, notification to management. The effective floor resolves
  product → its category → that category's **ancestors** → system, and each level may be
  expressed as a **percentage of list price or an absolute amount**.
- **AC-E6a** Management is notified on the **transition into** breach only
  (`is_below_floor` false → true). A line that stays in breach across ten saves notifies once —
  in-place editing must not generate an alert storm.
- **AC-E7** The floor value in force at the time is stored on the line. Changing floor policy
  later never retro-flags an existing quotation.
- **AC-E8** Line image resolves from the product's attachments whose attachment type is an
  image class (`attachment_types.is_image_class`, seeded true for Product Photos), lowest
  `sort_order`; an off-catalog line may upload its own.
- **AC-E9** Outcome lives on the quotation: open | won | lost, with a `loss_reason` lookup
  mandatory on lost. The lookup set is **configurable** (lookup set + binding, client-editable
  without a deploy), seeded with: price · spec locked to competitor · project cancelled or
  deferred · no sample submitted · relationship · lead time · other. **[DEVIATION]** The PDF
  has no lost state at all, yet asks for conversion rate and loss reasons.
- **AC-E10** Project outcome is **derived**: Won if any quotation is won, Lost only when all
  are lost, otherwise Open. It is never directly editable.
- **AC-E10a** Outcome and status are **different axes and must never be conflated**. Status is
  a funnel position describing what has happened (the terminal rung is **"PO Received"**, not
  "Won"); outcome is the commercial result. A project at "PO Received" with an open Common
  Area quotation is Open-with-a-win, and the board shows it as still live. **Every metric —
  conversion rate, win/loss, loss reasons — reads outcome, never status.**

## Group F — Samples, sponsorship, POs

- **AC-F1** A Sample Submission binds to a **quotation version** (not to the quotation), and
  records date submitted, developer feedback / change requests, and salesperson notes. Many
  samples per version.
- **AC-F2** Submitting a sample against a superseded version is blocked with a message
  directing the user to the current version — enforcing the PDF's "update the quotation first"
  rule.
- **AC-F3** The sponsorship form (`purchase_requests`, `request_type='sponsorship_form'`)
  gains a nullable `project_id`. **One form, not two.**
- **AC-F4** A flag on `respond_contacts` controls the field: flagged contacts see a
  **mandatory** project picker and cannot submit without selecting a registered project;
  unflagged contacts see today's free-text behaviour unchanged. (`respond_contacts` because
  that is already how the portal identifies the submitter.)
- **AC-F4a** The picker lists projects of the companies linked to that contact via
  `respond_contact_companies`. Where a contact maps to more than one company, each row shows
  its company.
- **AC-F5** A flagged contact whose project isn't listed is **hard-blocked** — directed to
  register on the web first. **[DECISION]** Explicitly chosen over an inline registration
  modal and over a free-text fallback.
- **AC-F6** Existing sponsorship rows keep `project_title` for display; ~28 real rows are
  linked manually post-migration. No automated fuzzy backfill writes links.
- **AC-F7** Sponsorship spend rolls up per project and per year for management review, with
  sponsorship-to-PO conversion reported.
- **AC-F8** A Project PO records: source (contractor direct | trading house), issuing party,
  PO number, date, amount, lines, and the bound quotation version. It lives in
  `project_purchase_orders` — **never** `purchase_orders` (see ADR-0002).
- **AC-F9** PO validation against the **bound version**: model mismatch and unit-price
  mismatch are **flagged**, not blocked; quantity may differ freely; PO source need not match
  who was quoted. The bound version is the price the contractor was actually last shown, so it
  is the only fair comparison after several revisions.
- **AC-F9a** The PO detail also surfaces **drift from v1** ("v1 RM 412.00 → PO RM 366.00,
  −11%") so management sees total price erosion across the negotiation. **[DEVIATION]** The
  PDF says match "the (initial) quotation"; matching v1 literally would flag every legitimately
  revised PO and the alert would become noise. Two signals instead: a mismatch flag against
  what was shown, and a visible erosion figure against where we started.
- **AC-F10** Recording the first PO on a project auto-transitions its **status** to
  **"PO Received"** (the single auto edge in v1). It does **not** set outcome — outcome is
  derived from quotations per AC-E10.

## Group G — Pipeline UX

- **AC-G1** New sidebar group **Project Sales** (moduleKey `projects`): Pipeline, My Tasks,
  Forecast & Reports, Parties. Quotations / Samples / POs get no sidebar entry — they exist
  only inside a project.
- **AC-G2** Pipeline offers Board and Grid via one toggle, with the choice persisted per user.
  Board defaults for sales roles, Grid for management.
- **AC-G3** Board columns are the configured statuses. Dragging a card requests the
  transition; an illegal move is rejected and the card snaps back.
- **AC-G4** A card shows title, developer, estimated/quoted value, brands, owner, days since
  last activity, and badges for Critical, Unattended, and Next-action overdue.
- **AC-G5** Grid uses the shared DataGrid with `tableLayout: { width: 'fixed',
  columnsResizable: true }`, explicit column sizes, `truncate` + `title` on long text, and
  column preferences via `listing_key`.
- **AC-G6** Project detail is URL-routed tabs: Overview · **Tasks** · Quotations · Samples ·
  Sponsorships · POs · Stakeholders · Activity · Documents. **Every tab renders even when
  empty**, with an explicit empty state and a next-step CTA.
- **AC-G7** `is_critical` (the PDF's "Final Negotiation") is a **flag**, not a column —
  settable at any status, with date moved to critical, management support committed, and
  management notes. **[DEVIATION]** Modelling it as a stage would force a re-quote during
  negotiation to move the card backwards and corrupt stage-duration metrics.
- **AC-G8** Every destructive or detaching action (delete project, remove stakeholder, unlink
  sponsorship) is confirmed via `AlertDialog` / `ConfirmDeleteDialog`. Never `confirm()`.
- **AC-G9** All screens work at 375px width; modals scroll so the submit button is reachable.
- **AC-G10** Deleting a project is **blocked while any Project PO exists** — Archive instead.
  Otherwise hard delete with the standard confirmation copy.

## Group H — Activity, staleness, follow-up

- **AC-H1** Project registers an adapter in `activities_registry`, so the Activities feed,
  `@`-mentions and internal notes work with no new tables.
- **AC-H2** `last_meaningful_activity_at` is maintained separately from `updated_at`. It
  advances on any `kind='user_update'` post and on a whitelist of `system_template` values:
  stage_changed, quotation_created, quotation_revised, sample_submitted, sponsorship_recorded,
  po_recorded. It does **not** advance on ordinary field edits, record views or imports.
- **AC-H3** Next action is **derived** — the due date of the project's earliest open Task.
  There is no `next_action_date` column. Overdue next-action is the primary nudge trigger;
  inactivity is the backstop for projects with no open task. Depends on S2b shipping first.
- **AC-H4** Thresholds are configured per status (a Registered project may go stale in 30 days,
  a Negotiating one in 7). A template that forks the graph **copies** the thresholds at fork
  time; later edits to the default do **not** propagate. An explicit admin "reapply defaults"
  action exists for that — no silent overwrite of a deliberately tuned fork.
- **AC-H5** The staleness sweep is an `automations` row (new `trigger_type`, `conditions_json`,
  `schedule_type='daily'`) — no new scheduler.
- **AC-H6** Ladder: nudge owner → warn owner + copy manager → "Unattended" badge that opens
  the project to takeover requests. **Nothing auto-reassigns.** A manager reassigns explicitly
  with a reason; history retains the original registrant.
- **AC-H7** **"My Tasks"** lists the current user's open tasks across all projects, overdue
  first, then upcoming, with the project and its status on each row.

## Group I — Forecast and reporting

- **AC-I1** Three numbers are reported **separately and never blended**: Pipeline (sum of open
  quotations' current-version totals, falling back to the registration estimate where no
  quotation exists), Weighted (pipeline × per-status probability), Committed (sum of won PO
  amounts).
- **AC-I2** The probability percentage lives on the status record — management tunes it with
  no deploy. It is a **project-level** status applied to each of that project's open
  quotations; three scopes on one project therefore share one percentage.
- **AC-I2a** Year-bucketing applies to **Committed** by default (the PDF's own worked
  example). Pipeline and Weighted may also be bucketed but render in a visually separate
  band labelled speculative — a 3-year-out guess must never sit in the same column as banked
  revenue.
- **AC-I3** Delivery year derives from launch date + a configurable lag (system setting,
  seeded **30 months**), overridable per project by an explicit expected delivery window. The
  override wins wherever set. Changing the lag is a settings edit, never a deploy.
- **AC-I4** Dashboard covers: total projects registered, total potential value, conversion
  rate, loss reasons, delivery forecast by year, salesperson performance, sponsorship
  investment and sponsorship-to-PO conversion, brand intelligence by location and budget band,
  architect intelligence.
- **AC-I5** Conversion rate is computed from quotation outcomes rolled to projects, so a
  partial win (house units won, common area lost) is not counted as a full win.

## Group J — RBAC

- **AC-J1** Permission slugs: `projects.projects.view` / `.create` / `.edit` / `.delete` /
  `.reassign` / `.view_all_financials`, plus `projects.parties.*` and `projects.templates.*`.
- **AC-J2** Any user with `.view` sees **all** projects in their company, read-only. This is
  deliberate — the collision screen depends on it.
- **AC-J3** Edit is restricted to the owner, approved collaborators, and users with
  `.view_all_financials` (management).
- **AC-J4** "Management" has exactly **one** definition in this module:
  `projects.projects.view_all_financials`. It gates price-floor breach detail, management
  notes, and the sponsorship spend rollup. `.reassign` is a separate grant, normally held by
  the same role but never used as a synonym for management.
- **AC-J5** An RBAC denial is verified in-browser for a salesperson attempting to edit another
  owner's project.

## Group K — AI / MCP

- **AC-K1** v1 exposes **read-only** MCP tools: project lookup by name/developer, my pipeline,
  forecast by year, project detail. Descriptions are intent-keyword-loaded, and
  `agent_mcp_tools` links are seeded by the startup hook — not left to an admin.
- **AC-K2** No write-capable project tools ship in v1. AI-assisted quotation updating is a
  later slice with its own grill (confirm-gate, diff preview, version semantics, price-floor
  enforcement on AI-written lines).
- **AC-K3** MCP `updated_at` is emitted as naive Malaysia wall-clock.
- **AC-K4** MCP calls carry no user context, so company scope resolves tri-state: a request
  with no contact sees **all** companies — the existing convention, stated here so it isn't
  rediscovered as a leak.

## Group L — Migration and go-live

- **AC-L1** Day-one migration is a **single consolidated management-run Excel import**, with
  the owner assigned per row in the sheet. Ownership is never decided by import order.
- **AC-L2** The clash lock is enforced from day one; the importer surfaces collisions as job
  errors for a human to resolve.
- **AC-L3** `purchase_requests` (PR) and `complaints` gain `project_id` in a **follow-up
  slice**, using the same nullable-FK-plus-picker pattern. Not in v1.
- **AC-L4** A rollback path exists: disabling the module leaves all `purchase_requests` and
  `complaints` behaviour untouched.

## Group N — Task management (slice S2b, must precede S5)

- **AC-N1** A Project Template owns a **task checklist** (`project_template_tasks`: name,
  description, `task_category`, sort order, default offset days). Creating a Project from that
  template instantiates its tasks.
- **AC-N2** A task carries **two independent axes** — conflating them was a design error caught
  by comparing against ecohub:
  - `task_phase` ∈ `pursuit` | `delivery`. Lifecycle: pursuit = the sales actions needed to win
    (visit architect, submit quotation, deliver sample, chase PO); delivery = post-win execution.
  - `category` = a **work-stream** label supplied by the template (e.g. Spec-in, Sampling,
    Commercial, Logistics), free-form per template. This is what ecohub's `category` is.
- **AC-N3** The Tasks tab **groups by `category` in collapsible sections**, matching ecohub's
  board — each task shows its own status inside its section. It is *not* a status-column kanban.
  The tab defaults to the phase matching the project's state (`pursuit` while open, `delivery`
  once won) with a visible filter to see both.
- **AC-N4** Task status rides the **status engine as entity #2** (`project_task`), configurable
  per template exactly like the project graph. An illegal task transition is rejected 422. The
  **seeded default graph mirrors ecohub's five**: Not Started · In Progress · Escalate · Stuck ·
  Done.
- **AC-N4a** **Escalate and Stuck force their context, ecohub-style** — the status cannot be set
  without it:
  - Choosing **Escalate** opens a dialog requiring a user; the task stores
    `escalated_to_user_id` and the card renders "Escalated to Eric".
  - Choosing **Stuck** opens a dialog requiring a reason; the card renders that reason inline.
  A status change that skips its required dialog is rejected 422 — the guard is server-side, not
  just a UI convention.
- **AC-N5** A task carries assignee, escalated-to, stuck reason, start date, due date,
  completed-at, sort order, phase and category. Editing any of them is audit-trailed.
- **AC-N5a** A task may optionally **link to one project artifact** — a quotation version, a
  sample, or a Project PO — so "deliver sample set" points at the actual sample record.
  Adapted from ecohub's task→invoice link, which has no Sorento analogue at this stage.
  Ecohub's `isServiceTask` flag is deliberately **not** ported (it belongs to their service-job
  domain).
- **AC-N5b** A **task-template admin screen** manages template checklists per template,
  mirroring ecohub's `admin/task-templates`.
- **AC-N6** **There is no `next_action_date` column.** A project's next action is derived from
  its earliest open task. Nothing else records a committed follow-up date.
- **AC-N7** Views at ecohub parity: **list, board, gantt, and a per-task history timeline**.
  History is delivered from the existing audit listeners; a dedicated table is the fallback
  only if the audit trail can't render a clean per-task timeline.
- **AC-N7a** "Gantt" means a **timeline bar chart** of task start/due dates. Ecohub's
  `ProjectTask` has no predecessor links, so there are no dependencies and no critical path.
  Stated so nobody expects one.
- **AC-N11** Removing a template role or template task that existing rows reference is
  **blocked** — deactivate instead. Editing a template's task list or status graph never
  retro-applies to projects already created from it.
- **AC-N8** Completing or creating a task is meaningful activity — it advances
  `last_meaningful_activity_at` (extends the AC-H2 whitelist with `task_created`,
  `task_completed`).
- **AC-N9** "My Tasks" lists the current user's open tasks across every project, overdue
  first, with the project and its status per row. **[NOT AN ECOHUB PATTERN]** Ecohub has no
  cross-project task screen — its tasks live only inside one project, because its user works one
  project at a time. Sorento has 10+ salespeople each holding dozens of concurrent pursuits, so
  a cross-project worklist is the difference between a tool that gets opened and one that
  doesn't. Deliberate addition, not a port.
- **AC-N10** Tasks are company-scoped and obey the same visibility rule as their project:
  everyone with `.view` reads them; owner, collaborators and the assignee can edit.

## Group O — Leads (slice S2c)

- **AC-O1** A Lead records: customer (**required**), developer party (optional), title, source
  + source detail, estimated value, location, notes, owner, status.
- **AC-O2** Creating a Lead is a wizard: **select-or-create Customer** → development info →
  lead detail → confirm. A Customer created this way is marked with a `source` so
  order/invoice pickers can filter prospects out.
- **AC-O3** Leads are **NOT exclusive**. No fuzzy clash check, no block — two salespeople may
  record the same rumour. Near-duplicates are surfaced informationally on the list, never
  enforced.
- **AC-O4** **Qualify** runs the full AC-C5/AC-C6 clash check and creates a Project with
  `lead_id` set. This is the moment ownership locks. If the clash check blocks, the lead stays
  open and the user gets the AC-C6a incumbent screen with join/dispute.
- **AC-O5** One Lead may produce **more than one** Project (a masterplan sighting can yield
  separate phase registrations).
- **AC-O6** **Disqualify** requires a reason from a configurable lookup. Lead→project
  conversion rate and disqualification reasons are reported.
- **AC-O7** Lead status rides the status engine as **entity #3**, consistent with `project`
  and `project_task`.
- **AC-O8** Leads are company-scoped and appear in the "Project Sales" sidebar group.
- **AC-O9** The Customer detail page gains a section listing that customer's **Leads and
  Projects** with status and value — the account view. Renders even when empty.
- **AC-O10** A Project's detail Overview shows its originating Lead (source, who reported it,
  date) when one exists, and states "registered directly" when it does not.

## Group M — Tests (Phase 2, never deferred)

- **AC-M1** pytest: every route (happy path, auth denial, validation error); the clash matcher
  against a fixture set of real-world title variants; floor resolution across all three levels
  and both expression forms; PO/quotation match check; forecast maths; company-scope leak test.
- **AC-M2** vitest: every new component across loading / empty / error / data states; the
  board's illegal-drag rollback; the collision screen.
- **AC-M3** playwright: register → collision blocked → request to join → quote → revise →
  sample → sponsorship link → PO → Won, verified end to end with `browser_network_requests`
  confirming the expected `/api/v1/*` calls.
- **AC-M4** Test cleanup is scoped to marker rows only. No unscoped `DELETE FROM` — the local
  DB is a copy of production data.
