# PLAN: After-sales P1, service jobs (send a technician to the site)

Status: implemented (merged to main fc9c5a2977 as #2365, 13 Nov 2026; owner hand test PASS 13 Nov).
PR #2365, retitled to "AFTER-SALES-P1: service jobs". Slices P2 to P4 each go on a new branch and PR.
Owner go: 12 Nov 14:20 MYT ("let's do this and bring the copy for me to test").
UAC: `service-jobs-p1-acceptance-criteria.md` (alongside).
Card: `P1-behaviour-card.md`. Owner-accepted 12 Nov 2026 (~14:26 MYT, "ok for after sales"):
- job numbers look like `SV26/11-0001`;
- the Site is separate address fields, prefilled from the complaint address;
- a job can still be raised on a closed or voided complaint;
- no jobs are backfilled for existing complaints;
- service jobs get new permissions.

Slices 2-4 each go on a new branch and PR after P1 is frozen at hand test. The portal inputs (Malay privacy
notice text, Google Maps key) are asked for as one crew-ask when slice 4 starts.
Source being ported: PR #163 (`worktree-after-sales-warranty`), slices S6 and S7a, plus S1's site columns.

## Journey

CS gets a complaint that needs someone on site. From the complaint they raise a service job. They call the
customer and confirm a date (and who agreed it), then assign a technician. On the day they record On the way,
Arrived and Completed, then Verify the work. If the customer turns the date down, the job goes back to
Proposed and the first try stays in History. The dispatch board shows each day's jobs per technician, with
the jobs still waiting for a date on top.

## Simplest-thing decisions (what #163 had and P1 leaves out)

| #163 | P1 | Trigger to add it back |
|---|---|---|
| Polymorphic job source (`source_entity_type` + `source_entity_id`, no FK) | `service_jobs.complaint_id` FK (NOT NULL). Complaints are the only source today. | A second record type that must raise a job |
| `service_job_assignments` table (one row per try) | `service_jobs.technician_id` column. Earlier tries show in History through the audit trail (old -> new). | A report that needs per-try metrics (S9 reporting) |
| Site copied onto the job | The Site lives on the complaint only, and the job shows the complaint's Site | A job that must go to a different address than its complaint |
| `external_providers`, `case_cost_lines`, charge columns | Not built (no screen asked for them) | Owner keeps G7 (charges and costs) |
| Separate job clocks (`proposed_at`, `confirmed_at`, ...) | `scheduled_from`, `scheduled_to`, `customer_agreed_by`, `arrived_at`, `completed_at`, `verified_at` | - |
| Waiting-on columns (S4a) | Not built (S4a is deferred) | S4a slice |

## Design lessons from project management (how each screen follows them)

The lessons come from the owner standing rules in the brief, and from the project-management rulings in
`documentation/plans/project-sales/` (CARD-*, PLAN-proposal-header-layout-05nov, PLAN-proposal-form-collapse-10nov,
PLAN-project-sales-polish-13oct).

1. **One main action per screen.** On a job page the single filled button is the job's next step: Confirm
   date, Assign technician, On the way, Arrived, Complete or Verify. Everything else sits in the gear menu
   (Cancel, Customer rejected the visit, Revisit needed, Reopen, Open complaint). The Complaint's Service Jobs
   section has one button ("Raise service job"). The lists have "Create" only where a record can be created on
   its own (Technicians). A job is raised from its complaint, so the Service Jobs list has no Create.
2. **Minimal UI; lightbox over inline bloat.** Confirm date and Assign technician each open in a centred
   dialog (the shared `Dialog`), never as inline forms on the page. The job page reads as two cards (Visit,
   Site) plus a History tab. There is no explainer text on any screen.
3. **CRM forms = portal forms, and Edit = Create.** The Technician create and edit dialog is the same
   component. The Site on the complaint is edited in the complaint's existing edit form, in the same field
   order as on the detail page (View and Edit share one layout). A portal form does not exist yet (P4 adds the
   consumer's view of a Site with the same fields in the same order).
4. **One History view.** The job's History tab is the shared `components/audit/AuditTrail.tsx`, which the
   complaint already uses (`ComplaintDetail.tsx:1405`). It is fed by the audit listeners on `service_jobs`:
   who, when, the plain action, and old -> new (status, technician, date, agreed by). There is no separate
   timeline component.
5. **Lists: one line per row, one value per column.** Service Jobs list columns: Job no., Complaint no.,
   Status (pill), Scheduled (dd/mm/yyyy, h:mm am/pm), Technician, City, Customer. Each is its own column,
   sortable on the server; long text is truncated with the full text on hover. Rows open the record. A
   right-click menu (the shared `components/ui/context-menu.tsx`, as in
   `project-sales/[projectId]/components/PurchaseOrdersPanel.tsx`) offers Open complaint and the job's
   next-step actions. There are no icon buttons on rows. Filters are multi-select (Status, Technician) plus a
   Scheduled date range; search covers job no., complaint no., customer and city. Columns can be hidden and
   reordered, and the choice is kept per user (`listing_key`).
6. **dd/mm/yyyy everywhere.** The shared formatters in `lib/helpers.ts` and the shared `DatePicker` (with
   time) for Confirm date and the board's day picker. No browser-native date input (#163 used one on the
   board and in its dialogs).
7. **Plain states, no special logic.** Seven plain states (Proposed, Confirmed, On the way, Arrived,
   Completed, Verified, Cancelled). "Waiting for a date" means only "in Proposed" (no agreed date yet), with
   no windows or buckets. (Review round 1: #163's "Proposed and past its date" can never happen, because a
   Proposed job has no date.)
8. **Reuse existing functions and components.**
   - Numbering: `NumberingService.get_next_number` (`app/services/numbering_service.py:14`) with a seeded
     `service_job` rule `SV{yy}/{mm}-{seq:4}`.
   - Statuses: the status engine (`app/status_engine/registry.py:85`).
   - Lists: DataGrid + `DataGridListToolbar` + `buildDataGridParams` + `lib/list-filters/multiValue.ts` +
     `list_query_registry`.
   - Record page: `PageHeader` + `RecordNavigation` + `DetailActions`.
   - Technician delete: `DeferredActionButton` (a countdown, no confirm dialog); a technician used on any
     job archives instead (sets inactive).
   - Errors: `extractApiError`. Toasts: `lib/toast.ts`.
   - Selects: `SearchableSelect`, clearable when optional.

### Screen by screen

| Screen | Lessons applied |
|---|---|
| Complaint detail: Site card + Service Jobs section | 2, 3 (Site edited in the complaint's edit form, same order), 1 (one "Raise service job" button), 5 (each job is one line: number, status pill, scheduled date, technician; click opens it) |
| Service Jobs list | 5, 6, 8; no Create (raised from a complaint) |
| Service job page | 1 (next-step button), 2 (Confirm / Assign dialogs), 4 (History tab), 6, 7, 8 (PageHeader + prev/next following the list's filter and sort) |
| Dispatch board | 6 (shared date picker, dd/mm/yyyy), 7 (waiting for a date = Proposed), 2 (cards open the job page; no inline editing) |
| Technicians list + dialog | 3 (one dialog for create and edit), 5, 8 (countdown delete, archive when in use) |
| Resolutions master | one "Requires service job" checkbox in the existing dialog, plus a column |

## Data (one additive migration on main's head, re-parented by `scripts/alembic-reparent.sh`; last: `il_0002_integration_log_search`)

- `technicians`: `id` uuid, `name` (not null), `phone`, `employment_type` (employee | contractor), `is_active`
  (default true), `company_id` (company-scoped like complaints), `created_at`, `updated_at`.
- `service_jobs`:
  - `id` uuid; `job_number` (unique, assigned on create); `complaint_id` FK `complaints.id`, not null;
    `status_id` FK `statuses.id`; `technician_id` FK `technicians.id`, nullable.
  - `scheduled_from`, `scheduled_to`, `customer_agreed_by`, `rejection_reason`, `arrived_at`, `completed_at`,
    `verified_at`, `cancel_reason`.
  - `created_by`, `created_at`, `updated_at`, `company_id`.
  - A partial unique index on `complaint_id` WHERE the status is live (not Cancelled and not Verified), so
    two Raise clicks can never make two live jobs. It is implemented as a guard plus a row lock if a partial
    index cannot reference status keys (the status is an FK). The coder picks one and writes a test for each
    race.
- `complaints`: `site_address_line1`, `site_address_line2`, `site_postcode`, `site_city`, `site_state`,
  `site_country`, `site_contact_name`, `site_contact_phone`, `site_latitude`, `site_longitude` (all nullable).
- `complaint_resolutions.requires_service_job` boolean, not null, default false.
- Seeds:
  - the service_job status graph (7 statuses, 12 transitions, copied verbatim from #163
    `service_job_status_graph.py`);
  - the numbering rule `service_job`;
  - permissions `complaint_management.service_jobs.view`, `complaint_management.service_jobs.dispatch` and
    `complaint_management.technicians.manage`, granted to the roles that hold
    `complaint_management.complaints.edit`.
- Seeds also run from `bootstrap_env` (#163's gap: a fresh database had no graph).
- Every new id is a uuid (`tests/test_schema_uuid_id_principle.py`). The revision id is 32 characters or fewer.

## API (`/api/v1/complaints-management`, complaints module guard)

| Method | Path | Permission |
|---|---|---|
| GET | `/service-jobs` (DataGrid params, server-side sort and filter) | service_jobs.view |
| GET | `/service-jobs/board?day=YYYY-MM-DD` | service_jobs.view |
| GET | `/service-jobs/{id}` | service_jobs.view |
| GET | `/complaints/{id}/service-jobs` | service_jobs.view |
| POST | `/complaints/{id}/service-jobs` (raise; returns the live job if one exists, 200 vs 201) | service_jobs.dispatch |
| POST | `/service-jobs/{id}/confirm` `{scheduled_from, scheduled_to?, customer_agreed_by}` | dispatch |
| POST | `/service-jobs/{id}/assign` `{technician_id}` | dispatch |
| POST | `/service-jobs/{id}/transition` `{to: on_the_way, arrived, completed, verified, proposed, cancelled; reason?}` | dispatch |
| GET, POST, PUT, DELETE | `/technicians` (DELETE refused with 409 "in use" when any job references it; archive = PUT is_active=false) | technicians.manage (GET: service_jobs.view) |

- A complaint update accepts the Site fields.
- A resolution create or update accepts `requires_service_job`.
- Setting a resolution with the flag on a complaint raises a job (after commit, idempotent, never deletes).

## Rules (tests come from these; numbered as in the UAC)

See the UAC. Summary:
- Raise is idempotent per complaint.
- Confirm needs both date and agreed-by.
- Assign refuses an inactive technician.
- Only the graph's moves are allowed.
- Rejected / Revisit go to Proposed with a reason.
- Every job is numbered on create.
- Waiting for a date = every job in Proposed, oldest raised first, on top of the board whatever the day.
- The board shows jobs whose `scheduled_from` falls on the day (MYT), unassigned first.

## Review round 1 decisions

- "Raise service job" appears only in the complaint's gear menu, and only while the complaint has no live job.
  The Service Jobs section has no button (one filled button per page; an empty state has no CTA).
- One live job per complaint applies across companies, because complaints are company-global.
- A job cannot go On the way or Arrived without a technician. "Change technician" is offered in the gear on
  Proposed and Confirmed jobs.
- The site pin is stored and returned but is not shown or edited in P1. P4 adds the map.
- A user limited to their own complaints still sees the full technician list (names, phones) when they hold
  service_jobs.view. This is accepted: the technicians are the company's own staff and contractors.

## Owner hand test round (12 Nov ~20:45 MYT)

Owner: "I didn't know we are putting it under complaint. I thought it's a standalone module." and "the phone
number must be same component as the project sales module, like where we verify the phone number".

- **F1, its own module.** What the original plan said:
  - #163's ADR-0009 (`documentation/adr/0009-service-job-is-requester-agnostic.md` on the #163 branch) made
    `service_jobs` its own installable module (deps base, resources) with no FK to complaints.
  - #163's build then mounted it under the complaints module and `/complaint-management/...`.
  - P1 copied that build and added the `complaint_id` FK under the simplest-thing rule.

  What moves now:
  - **Module:** a new module `after_sales` ("After-Sales Service"), deps `base` + `complaints` (the FK stays:
    complaints are the only requester today).
  - **Screens:** a sidebar section "After-Sales Service" with Service Jobs, Dispatch Board and Technicians.
    The routes become `/after-sales/service-jobs`, `/after-sales/service-jobs/{id}`,
    `/after-sales/dispatch-board` and `/after-sales/technicians`.
  - **API:** everything moves under `/api/v1/after-sales/...` behind the `after_sales` module guard.
  - **Permissions:** renamed to `after_sales.service_jobs.view`, `after_sales.service_jobs.dispatch` and
    `after_sales.technicians.manage`.
  - **What stays on complaints:** the Site fields, the Service Jobs section linking to the job, and the gear
    "Raise service job".
- **F2, one phone field.** Every phone field in after-sales uses the same frontend input and backend check as
  project sales:
  - Fields: the technician phone and the complaint Site contact phone.
  - Frontend: `components/common/PhoneInput.tsx`, as wired in
    `project-sales/_shared/components/PartyContactDialog.tsx`, with its error text.
  - Backend: `clean_phone` (`app/services/project_party_contact_service.py:80`), which stores E.164 or
    returns a 422.
  - Display: one local format, as `display_phone` / `formatPhone` do.

## Owner ruling 12 Nov ~20:49 MYT (binding, supersedes the complaint parts above)

"The after sales shouldn't affect how our current complaints work because our current complaint is for
project. So I want to not affect what's live now for the complaint."

**Zero change to the live Complaints module.** That covers its screens, menus, statuses, permissions, data,
notifications and exports.

After-sales is the standalone `after_sales` module, with its own tables, routes (`/after-sales/...`,
`/api/v1/after-sales/...`) and menu section ("After-Sales Service"). Shared components are reused read-only
and never changed in behaviour.

**What this removes from the design above:**
- the Site fields on complaints;
- the Service Jobs section and the gear "Raise service job" on the complaint page;
- "Requires service job" on resolutions and its auto-raise;
- every complaint-scope coupling (view_own, brand scope).

**The new shape:**
- **Creating a job.** A service job is created from After-Sales Service > Service Jobs > Create. Create and
  Edit use one dialog. It carries its own details:
  - Customer name (required)
  - Contact on site
  - Contact phone (the project-sales `PhoneInput` + `clean_phone`)
  - Site address
  - Problem
- **Related complaint.** An optional reference on the job side only (`service_jobs.complaint_id`, nullable).
  It is picked read-only from the existing complaints list, and nothing on the complaint side reads it. One
  live job per related complaint still applies.
- **Visibility.** The after_sales permissions plus company scope.
- **Guard tests.** These pin main's complaints routes, complaint and resolution schemas, and model columns,
  plus main's Complaints menu. They also check that no complaints code imports after-sales.

## Out of P1 (named)

- Not taken by the owner: G4 WhatsApp the customer, G5 send the job to the technician, G6 completion report,
  G7 charges and costs, G8 job sheet PDF, G10 alert for jobs waiting for a date, G11 week view, G12 reports,
  G13 assistant, G14 Excel export.
- "Reported by" column + filter (decision 5): it needs a source for the value, which arrives with P4 (the
  portal lodge).

## Assistant coverage (PRINCIPLES DoD 6-8)

The service job list and record need an assistant registry entry (`app/services/assistant_registry/`), with
two eval prompts: "service jobs scheduled today" and "status of the job for complaint X". If the registry
shape does not fit in this lane, the PR says why and names the follow-up.

## User guide

`documentation/user-guides/` gets a new service jobs page (raise, confirm, assign, board, technicians).

## Phases

1. Plan + UAC (this file).
2. Tester: red pytest + vitest from the UAC.
3. Coder: green.
4. Reviewer + security-reviewer (new permissions) + browser passes at 1280 and 375 px.
5. Hand test (`laneboard/scripts/2365.md`), then freeze.
