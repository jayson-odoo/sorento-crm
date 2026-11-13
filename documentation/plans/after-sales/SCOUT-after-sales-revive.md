# SCOUT: after-sales warranty module revive (PR #163)

Status: scout done, waiting on the owner's answers (crew-ask on PR #2365). No product code.
Lane AFTER-SALES-REVIVE, size L.

## 1. What PR #163 is

PR #163 is open and was never merged. Its branch `worktree-after-sales-warranty` (head `35ef765e7`, 16 Aug)
forked from main on 1 Aug at `3ecb65f27`. Main is now 2,695 commits past that point. The PR has 96 commits:
328 files, +82,573 / -1,113. About 40k of those lines are tests, 22.8k backend, 10.4k frontend, 3.4k
migrations and 5.8k docs.

Screenshots of the branch running in a sandbox on fake data:
https://github.com/jayson-odoo/sorento-crm/pull/163#issuecomment-6814816181

### Per slice

Line counts are non-test lines added. "Tests" counts pytest/vitest functions.

| Slice | What a user gets | New tables / columns | Tests | ~LOC |
|---|---|---|---|---|
| S0 | Nothing visible. Complaints are registered on the status engine (12 states, 18 edges, same strings). | seed only (310) | 48 | 570 |
| F0-F2c (forms platform) | Backend only: form_engine document model, workflow-submission status + line status/disposition, form SLA on submissions, portal submission by a contact, submission attachments. **The builder UI was never updated (F3), so every draft save 422s; the plan calls this a release blocker.** | 311-315: `workflow_submissions.status_id` (drops `current_state_code`), line status/disposition, `form_sla_configs.definition_id`, portal flags | ~390 | 7,500 |
| S1 parties | A complaint gets a Dealer, a Site (address + pin) and a "Reported by" role. Contact kind is derived (technician > staff > dealer > consumer). | 316: `salesman_code_users`; `respond_contacts.customer_id/user_id`; complaint site columns, `reported_by_role` | 50 | 1,180 |
| S2 warranty engine | A deterministic verdict per policy term: kind + purchase date + defect, judged against the policy in force on the purchase date. Policy v15 is seeded (31 kinds, 41 terms, only 2 kind rules). | 317: `warranty_product_kinds`, `warranty_kind_rules`, `warranty_policies`, `warranty_terms` | 73 | 2,100 |
| S2b consumer ledger | Consumer profiles (deduped on phone), purchases and purchase lines, and stored warranty assessments per complaint line. New `consumers` module. | 318: 5 tables; `complaint_product_lines.consumer_purchase_line_id`, `defect_type_id` | 77 | 2,400 |
| S2a attachment validator | Backend only: AI scores an upload against admin guidance, offering Retake / "Use anyway". No UI. | 319: columns on `attachment_types`, `entity_attachment_links` | 64 | 1,015 |
| S4 notification spine | Backend only: a notification addresses a user OR a contact; Respond outbox; call logging; assignment fallback. | 320: `notifications` XOR + partial uniques; `access_agents.assignment_fallback_user_id` | 72 | 1,370 |
| S4a waiting attribution | A "waiting on" banner (cs / customer / dealer / supplier ...) on complaint, PR and stock-inquiry detail, stamped on SLA events. | 321: 3 columns on `conversation_sla_tracking` + event log | 44 | 1,650 |
| Fork 6 PDPA notice | A versioned EN/MS consent notice, stamped on the profile. The Malay wording is still a draft. No admin screen. | 322: `consent_notices` | 17 | 730 |
| S3 consumer lodge | Portal "Report a problem": upload a receipt, AI reads it, the consumer edits the details, picks products, sets the site address (Maps search + pin) and submits. That creates a complaint with lines and warranty verdicts. Also Consumer 360 (list + profile with consent, purchases, complaints), retail-vs-project complaint rendering, and Maps key + extract model settings. | 323, 327, 328: line claim columns, structured site address, settings | ~230 | 6,570 |
| S5 WhatsApp intake | A dealer's WhatsApp burst becomes a complaint (MCP tool, idempotent on burst key). The call path is not built. | 324: `complaints.intake_burst_key`, `intake_transcript` | 30 | 790 |
| S6 service jobs | Service jobs raised from a complaint: list, detail, dispatch board, technicians master. A 7-state graph; confirming needs a date and the customer's agreement; a reject creates a new assignment. | 325, 326: `technicians`, `external_providers`, `service_jobs`, `service_job_assignments`, `case_cost_lines` | ~110 | 5,580 |
| S7a | A resolution flagged "requires service job" raises the job automatically. | 330: `complaint_resolutions.requires_service_job` | 13 | 220 |
| S7b warranty config | Warranty Configuration: Policies / Kinds / Rules tabs, a rule tester, supersede, and policy detail with terms by kind. | 331: check constraint + 8 permission slugs | ~240 | 6,500 |

The PR also fixes some defects that predate it. Two are worth porting on their own:
- The status engine misreported a record that sits outside its own graph (`7cc1f572b`).
- Thirteen complaint test files committed rows into the shared database (`2d0d13fc5`, `5e94b78df`).

Not built at all: goods track / exchange / RMA (S7, S11, S12), feedback survey (S8), reporting (S9), dealer view (S10), technician portal, case-cost panel, outbox screen, consent admin screen.

## 2. What main already has (none of it is after-sales)

No after-sales work has landed on main. None of the PR's 222 new files exists there. Main has only:
- `complaints.within_warranty`, a free-text field: `sorento_crm_backend/app/models/complaints.py:26`
- `products.warranty_months`: `sorento_crm_backend/app/models/product.py:341`
- the word "technician", as wording only: `sorento_crm_backend/app/services/form_skip_registry.py:138`

None of the forms-platform pieces are on main either:
- Workflow submissions still use `current_state_code`: `app/models/workflow_forms.py:103`.
- Submission lines have no status: `:130-145`.
- The portal still has one route per form kind: `app/services/portal_service.py:83`.
- `workflow_submission` is only a label in `FORM_SLA_TYPES`: `app/services/form_sla_service.py:42`.
- Complaints are not registered on the status engine: `app/status_engine/registry.py:85`.

## 3. Staleness

- **Alembic:** 21 linear revisions (310-331) chained on `309_merge_status_engine`, which is now about 800
  revisions deep. Main's single head is `qdp_0001_duplicate_party`. Main has also reused file numbers
  310-332, though the revision ids do not clash. `330_resolution_requires_service_job` is 35 characters,
  over the 32-character limit. Every port needs new migrations on the current head.
- **Overlapping files:** of the 106 existing files the PR modifies, main has changed 95 since 1 Aug. The
  heaviest: the MCP catalog (84 commits), `permission_registry` (82), `menu.config.tsx` (78),
  `portal_service` (35), `portal-client.ts` (33), `sla_service` (24, +2,994/-444), `public/portal.py` (23),
  `complaints_service` (15).
  Main deleted `tests/test_complaint_neighbours.py`.
- **Design conflict:** the PR adds `respond_contacts.customer_id`. Main has since added the
  `respond_contact_customers` link table and records why it rejected that exact column
  (`app/models/access.py:11,20`). The dealer binding has to move onto the link table.
- **ADR numbers:** the PR's ADRs 0008-0013 collide with six ADRs main has added since; they need renumbering.
- **Owner standing rules the PR screens break:**
  - Rows carry action icon buttons (edit/delete/layers) with no right-click menu.
  - Delete uses an AlertDialog confirm instead of the deferred action.
  - Dates show as "01 Jan 2000" (Policies grid) instead of dd/mm/yyyy.
  - The dispatch board and policy dialog use a browser-native date input.
  - Headers are hand-rolled `<h1>` instead of `PageHeader`.
  - There is no History tab and no prev/next on warranty, service-job or technician records.
  - Filters are single-select, and some pages use the label "Add policy" instead of "Create".
  - Three files import `sonner` directly.
  - A new Playwright spec was added.
  - No user guide was written.
- **Shared parts a port should adopt:** `components/common/PageHeader.tsx`, `DeferredActionButton.tsx` with
  `hooks/useDeferredAction.tsx`, `RowActionsMenu.tsx`, `EventTimeline.tsx`, `lib/list-filters/multiValue.ts`,
  `ListSearchInput.tsx`, `lib/toast.ts`, `DatePicker`, `RecordNavigation`.
- **Gaps on a fresh database (found while booting it):**
  - `bootstrap_env` does not seed the complaint or service-job status graphs, so dispatch answers `service_job_graph_missing`.
  - The `consumers` and `warranty` modules must be installed per tenant.
  - Service jobs show "Unnumbered".
  - Staff complaint create answers 500 (`_request_has_valid_external_api_key` is undefined in `complaints.py`; the bug was already on main at the fork).
  - Verdicts read "unknown" unless a complaint line is linked to a purchase.

## 4. Recommended path

**Port onto current main in slices. Do not merge or rebase #163, and do not rebuild from the plan docs
alone.** The backend rules and tests are the expensive, well-thought-out part and port cleanly as new
files. The screens are thin, and each port rebuilds them to today's standing rules using the shared
components. Drop F0-F2c (forms platform) from this lane: its builder was never finished, the PR's own
ADR-0011 contradicts how S3 and S5 were built, and main's portal forms have moved on.

| Order | Port slice | From #163 | Why this order | Size |
|---|---|---|---|---|
| P1 | Service jobs: site address on complaint, technicians, service jobs, dispatch board, "requires service job" resolution | S1 site fields + S6 + S7a | Usable at once by CS on today's complaints, project ones included. Needs no consumer data and no portal. | L (~6k + tests) |
| P2 | Warranty engine + configuration, plus CS entering a purchase date / kind on a complaint line | S2 + S7b + a small new piece | Without a purchase date every verdict is "unknown", so CS needs a way in before the portal exists | L (~8.5k) |
| P3 | Consumer ledger + Consumer 360 | S2b + 360 | The store the portal writes to | M/L (~3.4k) |
| P4 | Portal consumer lodge (receipt read, Maps pin, PDPA notice) | S3 + fork 6 | Customer-facing; needs the Malay notice signed off and a Maps key | L (~7k) |
| later | SLA waiting attribution, notification spine, WhatsApp intake, attachment validator | S4, S4a, S5, S2a | They touch heavily changed core code (SLA, chatbot), which main's semantic-parser rule now governs. Rebuild them against current main when wanted. | M each |
