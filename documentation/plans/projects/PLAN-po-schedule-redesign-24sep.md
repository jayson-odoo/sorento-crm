# PLAN: PO and delivery schedule redesign (issue #1167)

Status: grilled 24 Sep 2026, mockups pending owner review. No code before the mockups are
approved (R5). Track per slice: S1 small fix; S4 small fix; S2, S3, S5, S6, S7 full track.

UAC: `documentation/plans/projects/po-schedule-redesign-24sep-acceptance-criteria.md`.
Evidence: `documentation/plans/projects/AUDIT-po-schedule-flow-24sep.md` and 42 screenshots
under `documentation/plans/projects/evidence/po-schedule-audit-24sep/` (PR #1183, branch
`docs/po-schedule-ux-audit`). Mockups (open from a file, 1280 and 375 frames, numbered callouts
tied to the audit friction list and the rulings):

| Mockup | Screen | Slice |
| --- | --- | --- |
| `mockups/needs-attention.html` | New Project Sales > Needs attention list, two upload buttons | S2 |
| `mockups/delivery-schedule-review.html` | `[projectId]/delivery-schedules/[versionId]` | S5 (and S3 first use) |
| `mockups/po-confirm.html` | `[projectId]/purchase-orders/[versionId]` | S6 (and S1's R7 fix) |
| `mockups/so-findings.html` | `[projectId]/sales-orders/[psoId]` | S7 (and S3) |

Core or module: part of the existing `projects` module (`moduleKey: 'projects'`). No new module,
no new schema, no migration, no new permission.

## Scope

Screens and navigation only. The extraction, reconciliation, SO drafting and publish-gate
services are not redesigned (task brief; R3 "the two-tier publish gate is unchanged"). The only
backend addition is one read endpoint for the Needs attention list (S2), which reads columns the
existing services already write.

## Rulings (owner grill, 24 Sep 2026, binding, quoted)

> R1 What is messy, all four, in this order: (1) five clicks to any upload, no sidebar entry; (2)
> twelve concepts and three findings surfaces; (3) every upload ejects to a full page; (4) the
> three review screens themselves (PO confirm page with the 52-line grid and cards, the delivery
> schedule matrix, the sales order findings page) are hard to read.
>
> R2 New sidebar page under Project Sales: "Needs attention". One list across projects of POs,
> delivery schedules and sales orders that need a human (to check, unreconciled, blocking
> findings), with a type column, project, status, age, and two buttons Upload PO / Upload
> schedule that ask for the project. Two clicks from / to any upload or review.
>
> R3 Findings stay on each entity (PO, schedule, sales order). One shared findings component
> renders them everywhere: one severity set (blocks publish / needs acknowledgement / info), one
> verb "Dismiss with a reason", duplicates collapsed. The two-tier publish gate is unchanged. No
> unified findings page.
>
> R4 Full-page confirm and review screens stay; Confirm returns the user to where they came from
> (the Needs attention list or the project tab).
>
> R5 All three review screens are redesigned. Method: annotated mockups per screen first (1280
> and 375), reviewed by the owner in one lavish session, then one module plan. No code before the
> mockups are approved.
>
> R6 Renames everywhere (UI labels, docs, user guide): "Phase" becomes "Area" (the SO's area
> group is copied from the schedule phase's area group, one concept); "divergence" becomes
> "AutoCount differences". Keep "PO version", "notice", "amendment".
>
> R7 Small fix: rejected annotation cards show reviewer, date and reason inline (the reason
> exists in action_note, the UI truncates it into a tooltip).
>
> R8 Dropped: an active-company indicator on lists. Not wanted.
>
> R9 Owner check owed: PO HQ/26/01/121 v1 PDF viewer in production (local copy showed a 404 on an
> R2 object).
>
> R10 Order of slices: S1 renames + R7 (small fix track), S2 Needs attention list with uploads, S3
> shared findings component, S4 return-after-confirm, S5 to S7 the three review screens per
> approved mockups (schedule matrix first, then PO confirm, then SO findings).

## Facts this plan rests on (verified against the checkout, 24 Sep 2026)

Paths: `FE` = `sorento_crm_frontend`, `PS` = `FE/app/(protected)/project-sales`, `BE` =
`sorento_crm_backend`.

- **Sidebar.** Project Sales is declared twice in `FE/config/menu.config.tsx`: `MENU_SIDEBAR`
  (block from line 79; breadcrumbs and search read it) and `MENU_SIDEBAR_COMPACT` (block from
  line 1834; the demo6 sidebar renders it via `sidebar-menu-primary.tsx`). AutoCount
  Differences is `{ title: 'AutoCount Differences', path: '/project-sales/divergences',
  permission: 'projects.projects.view' }`. A new item goes in both blocks.
- **Routes.** Project tabs in `PS/[projectId]/components/ProjectDetailClient.tsx` via `?tab=`
  (`pos`, `schedules`, `sales-orders`). PO version: `PS/[projectId]/purchase-orders/[versionId]`
  -> `components/POIntakeConfirmClient.tsx`. Schedule review:
  `PS/[projectId]/delivery-schedules/[versionId]` -> `DeliveryScheduleReviewClient.tsx`. SO:
  `PS/[projectId]/sales-orders/[psoId]` -> `SalesOrderDetailClient.tsx`. Every one needs a
  project id, which is why nothing is reachable without opening a project first (audit
  friction #1).
- **Uploads.** `POIntakeUploadDialog` takes a required `projectId`, posts to
  `POST /api/v1/project-sales/projects/{project_id}/purchase-orders/upload`
  (`BE/app/api/v1/projects/po_intake.py`), then `router.push`es to the version page.
  `DeliveryScheduleUploadDialog` takes `project: Project` and `schedules`, picks the PO inside
  the dialog, posts to `POST /purchase-orders/{po_id}/delivery-schedules/upload`
  (`schedules.py`), then pushes to the schedule version page.
- **Confirm today.** PO "Confirm this PO" stays on the page with a toast
  (`usePOIntake.ts`); its only way out is "Back to the project" with no tab. Schedule "Confirm
  schedule" closes its dialog and stays. There is no `returnTo`/`from` handling in project-sales.
  The product-wide `from=` list state exists: `appendListState` in
  `FE/components/ui/data-grid-table.tsx` and `useHrefWithListState` in
  `FE/components/common/BackToList.tsx`.
- **Rejected notes (R7).** `PS/[projectId]/components/POIntakeAnnotationsGrid.tsx` (a
  DataGrid, not cards) renders "By {actioned_by_name} · {actioned_at}" and truncates
  `action_note` with a `title` tooltip in its Reviewed column. Columns `state`, `actioned_by`,
  `actioned_at`, `action_note` on `ProjectPOAnnotation` (`projects.po_annotations`,
  `BE/app/models/project_so.py`).
- **Findings.** One table, `SODraftFinding` (`projects.so_draft_findings`), severity
  `hard | warn | info`. Schedule/PO-level findings are rows of the same table with
  `project_sales_order_id` null and `purchase_order_id` + `schedule_version_id` set. Rendered by
  `SalesOrderFindingsSection.tsx` (cards Blocking / Warnings / For information; verb "Override
  with a reason" for hard, "Clear with a reason" otherwise) and `ScheduleFindingsSection.tsx`
  (card "Schedule / PO findings", "Clear with a reason"), both mounted in
  `SalesOrderDetailClient.tsx` under a "Publishing is refused" banner. Schedule column verdicts
  are not findings rows: `_verdict()` in `BE/app/services/project_schedule_service.py` and its
  client mirror `buildColumnStates` in `delivery-schedules/lib/scheduleTotals.ts`, dismissed in
  `DeliveryScheduleReconciliationList.tsx` with a third verb, "Dismiss as false signal".
- **Two-tier gate.** `BE/app/services/project_so_draft_service.py`: `_refresh_status` sets
  `blocked` while an unacknowledged hard finding exists, `draft` while any finding is open, else
  `ready`; its docstring states warnings do NOT stop a publish. `blocking_findings` returns the
  unacknowledged hard ones; `acknowledge_finding` needs a reason of at least 3 characters, and a
  hard finding needs `OVERRIDE_PERMISSION = "projects.projects.manage"`.
- **Area.** `ProjectDeliveryPhase.area_group` (`projects.delivery_phases`, not null);
  `_draft_lines` copies it (`area = learned.get(...) or phase.area_group`) and `_persist` saves
  `ProjectSalesOrder(area_group=group_key)`. One concept under two names, as R6 says.
- **Divergence copy.** User-facing strings already say "AutoCount Differences" except the SO
  divergence page, whose metadata title and heading read "AutoCount comparison"
  (`sales-orders/[psoId]/divergence/page.tsx`, `DivergenceReviewClient.tsx`). "divergence"
  survives in routes and identifiers only. No user guide under `documentation/user-guides/`
  covers POs, schedules, phases or divergence today.
- **Lists.** No PO, schedule or SO list exists across projects; each is per project
  (`GET /projects/{id}/purchase-orders` in `samples_pos.py`, `GET /projects/{id}/delivery-schedules`
  in `schedules.py`, `GET /projects/{id}/sales-orders` in `sales_orders.py`). The PO row's
  `model_mismatch_count` / `price_mismatch_count` are computed in
  `BE/app/services/project_po_service.py`; the POs tab's "To check" is their sum.
  `list_query_registry` has no project resources. The nearest precedent is
  `GET /divergences` (`BE/app/api/v1/projects/divergences.py`), a plain paginated service read.
- **Permissions.** The PO intake, schedule and SO routers use `projects.projects.view` to read
  and `projects.projects.edit` to write; per-project edit is `can_edit_project` in
  `BE/app/services/project_service.py` (owner, collaborator or manager), and reading is
  deliberately open inside the company. Company scope is applied by the ORM predicate in
  `app/services/company_scope.py`.

## Slices

### S1. Renames + R7 (small fix track, FE only)

- **Backend seam:** none.
- **Frontend seam:** user-visible strings only. "Phase" -> "Area" in `SalesOrderLinesTable.tsx`,
  `SalesOrderLinesEditor.tsx`, `AmendmentDeltaTable.tsx`, `DeliveryScheduleRevisionProposals.tsx`,
  `SalesOrderRegroupDialog.tsx` ("Unlabeled phase"), `DeliveryScheduleReviewClient.tsx` ("By
  phase"), `DeliveryScheduleConfirmDialog.tsx`, `DeliveryScheduleRevisionDiff.tsx` ("phases
  moved"), `scheduleTotals.ts`, `POToSalesOrderStep.tsx`, and the toast in
  `_shared/hooks/useDeliverySchedules.ts`. Task "Phase" (`TaskFormDialog.tsx`, `TasksPanel.tsx`,
  `setup/components/TemplateChecklistPanel.tsx`) is a different concept and stays. "AutoCount
  comparison" -> "AutoCount differences" in the divergence page and `DivergenceReviewClient.tsx`.
  R7: in `POIntakeAnnotationsGrid.tsx` the `action_note` wraps in full instead of truncating.
  Routes, identifiers, API fields and finding codes (`phase_unmatched`) keep their names: R6 is
  about words people read.
- **Docs:** the grep sweep also covers `documentation/` prose that names the UI (plans excluded;
  they are records). No user guide page exists to rename; the weekly guide batch picks up the new
  words.
- **Tests:** existing vitest files that assert the old strings are updated in the same commit
  (`DeliveryScheduleReviewClient.test.tsx`, `DeliveryScheduleRevisionDiff.test.tsx`,
  `DeliveryScheduleRevisionProposals.test.tsx`, `DeliveryScheduleConfirmDialog.test.tsx` and any
  SO table test the grep finds); new vitest for S1-4 / S1-5 in
  `POIntakeAnnotationsGrid.test.tsx`; a string test for S1-1 / S1-2. Browser pass on the two
  changed screens.

### S2. Needs attention list with uploads (full track)

- **Backend seam:** one route, `GET /api/v1/project-sales/needs-attention`, in a new
  `BE/app/api/v1/projects/needs_attention.py` mounted beside `divergences.py`, guarded by
  `projects.projects.view`. One service function (a new `project_needs_attention_service.py`,
  or a method on the existing PO service if the coder finds it cleaner) runs three plain queries
  and merges them in Python, sorted by `waiting_since` ascending, then paginated:
  POs whose latest `po_versions` row has no `confirmed_at` or whose mismatch count is above zero;
  schedules whose latest `delivery_schedule_versions` row has no `confirmed_at` or
  `reconciled_columns < total_columns`; sales orders with status `blocked` or `draft`, with their
  unacknowledged hard and warn counts. Reuse the existing mismatch-count query in
  `project_po_service.py` rather than a second copy. No registry entry, no view, no table: three
  record types do not need a union abstraction (PRINCIPLES "simplest thing"). Trigger to revisit:
  a fourth record type, or the list becoming slow on real data (measure first).
- **Frontend seam:** new route `PS/needs-attention/page.tsx` (+ `loading.tsx` with
  `ListPageSkeleton`); the menu item in both blocks of `menu.config.tsx`; service
  `PS/_shared/services/needsAttentionService.ts` + hook `useNeedsAttention` via
  `buildDataGridParams`. `POIntakeUploadDialog` gains an optional project picker, shown only when
  no `projectId` is passed; `DeliveryScheduleUploadDialog` likewise loads the chosen project's
  `Project` and schedules after the pick. Both keep their current call sites untouched. The
  picker lists projects with `can_edit`.
- **Tests:** pytest `tests/test_project_needs_attention.py` (on `tests/_pg_fixture.py`, seeding
  its own chain; CI has no data): one test per inclusion branch (S2-2 to S2-4), one per
  exclusion, company isolation, filters, 403 without view, response fields asserted. Vitest:
  menu entries (both blocks), list renders pills and no Open column, both dialogs with and
  without a preset project (existing dialog tests stay green unedited). Recorded agent-browser
  run for S2-12.

### S3. Shared findings component (full track, FE only)

- **Backend seam:** none. The acknowledge endpoints
  (`POST /sales-orders/{pso_id}/findings/{finding_id}/acknowledge`,
  `POST .../schedule-findings/{finding_id}/acknowledge`) and the column dismissal are called as
  today.
- **Frontend seam:** one component, `PS/_shared/components/FindingsList.tsx`, taking a plain
  array of `{ id, severity, code, text, source, subjectKey, acknowledged, onShow? }` plus a
  `onDismiss(ids, reason)` callback. Each screen maps its own data into that array (SO findings,
  schedule-level findings, schedule column verdicts); no adapter registry. Collapse key per UAC
  S3-3. One reason dialog (reusing `SalesOrderAcknowledgeDialog`, renamed in place). It replaces
  `SalesOrderFindingsSection` and `ScheduleFindingsSection` on the SO page in this slice (so
  there is never a second findings UI live), and is mounted on the schedule page by S5 and the
  PO page by S6.
- **Tests:** vitest for `FindingsList` (severity chips and counts, collapse per key and no
  collapse without one, dismiss fires once per underlying id with one reason, 3-character
  minimum, verb text); the retired components' tests move to it. The existing pytest for
  `_refresh_status`, `publish` and the manage-permission override run unedited (S3-5).

### S4. Return after Confirm (small fix track, FE only)

- **Backend seam:** none.
- **Frontend seam:** the Needs attention grid and the project tab panels already link rows;
  their hrefs carry `from` through `appendListState` (list) or the originating `?tab=`. The PO
  version page, schedule review and SO page read it with `useHrefWithListState`, and on a
  successful Confirm / Confirm schedule / Publish `router.push` there; with no origin they stay
  (today's behaviour). The upload dialogs forward the origin into the review URL they push to.
- **Tests:** vitest per page: confirm with origin navigates, without origin stays; upload
  forwards origin. Browser pass S4-6.

### S5. Delivery schedule review screen (full track, FE only; first of the three)

- **Backend seam:** none; same queries and mutations.
- **Frontend seam:** `DeliveryScheduleReviewClient.tsx` recomposed per the approved
  `mockups/delivery-schedule-review.html`: `PageHeader` with the meta line and
  `RecordNavigation`; line `Tabs` (Matrix, Findings, Changes since vN, Re-dating, Notes) wrapping
  the existing `DeliveryScheduleMatrix` / `DeliveryScheduleByDateMatrix`,
  `DeliveryScheduleRevisionDiff`, `DeliveryScheduleRevisionProposals` and
  `DeliveryScheduleNotes`; `DeliveryScheduleReconciliationList` folded into the matrix (status
  column + inline column card using `DeliveryScheduleProductPicker`) and the Findings tab
  (`FindingsList`). `DeliveryScheduleColumnCards` stays the 375 rendering.
- **Tests:** vitest on the recomposed client (tabs and counts, default filter while
  unconfirmed, column card shows the full code, no explanatory confirmed sentence); existing
  matrix tests stay green. Browser pass S5-6 at 1280 and 375.

### S6. PO confirm screen (full track, FE only)

- **Backend seam:** none.
- **Frontend seam:** `POIntakeConfirmClient.tsx` recomposed per the approved
  `mockups/po-confirm.html`: header status trail replacing the three-cell stamp card, sum on
  the meta line, right-panel line `Tabs` around the existing `POIntakeLinesGrid`, header card,
  `FindingsList` and `POIntakeAnnotationsGrid`; the PDF viewer unchanged on the left, a tab at
  375; "Show only these" on by default while unconfirmed.
- **Tests:** vitest on the recomposed client (trail states, default filter, tabs); browser pass
  S6-4.

### S7. Sales order findings screen (full track, FE only)

- **Backend seam:** none.
- **Frontend seam:** `SalesOrderDetailClient.tsx` recomposed per the approved
  `mockups/so-findings.html`: header meta with area group and PO version, gate count under
  Publish replacing the refusal banner, line `Tabs` (Findings default while open, Lines,
  AutoCount differences, Activity), summary facts with `-` for unknowns.
- **Tests:** vitest on header and default tab; browser pass S7-4.

## Open questions for the mockup review (R5 session)

1. Should a hard SO finding and the schedule finding that causes it (for example CB1178A "the
   schedule only places 0" and the unmapped column BUI-HB-CB1178ASS) also collapse, as two codes
   for one cause? This plan collapses same code + same subject only.
2. A confirmed schedule with columns still not reconciled (HQ/26/01/121 v2, 35 of 44): stay on
   Needs attention until every column is reconciled or dismissed, or drop off at confirm?
3. Owner check R9 (PDF 404 in production) is owed before S6; if production is also broken it
   becomes its own bug lane, not part of S6.

## Deferred

- Active-company indicator on lists: dropped by R8, not deferred.
- Order Change Notice and amendment entry points (audit open question 6): not in the rulings.
