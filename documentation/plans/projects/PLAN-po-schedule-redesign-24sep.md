# PLAN: PO and delivery schedule redesign (issue #1167)

Status: approved by the owner 24 Sep 2026 (lavish review, "yeah all good for me"), R22 design
constraint binding; tickets S1 #1203, S2 #1204, S3 #1205, S4 #1206, S5 #1207, S6 #1208, S7 #1209;
nothing built. Track per slice: S1 small fix; S4 small fix; S2, S3, S5, S6, S7 full track.

UAC: `documentation/plans/projects/po-schedule-redesign-24sep-acceptance-criteria.md`.
Evidence: `documentation/plans/projects/AUDIT-po-schedule-flow-24sep.md` and 42 screenshots
under `documentation/plans/projects/evidence/po-schedule-audit-24sep/` (PR #1183, branch
`docs/po-schedule-ux-audit`). Mockups (open from a file, 1280 and 375 frames, numbered callouts
tied to the audit friction list and the rulings; redrawn after the lavish review, see the
"Lavish review" rulings below -- `needs-attention.html` is retired, `po-confirm.html` and
`so-findings.html` are renamed):

| Mockup | Screen | Slice |
| --- | --- | --- |
| `mockups/project-listing-start.html` | Project Sales > Pipeline (Grid view), one top-right Start menu (Register a project / Upload PO / Upload delivery schedule), Upload PO dialog | S2 |
| `mockups/delivery-schedule-review.html` | `[projectId]/delivery-schedules/[versionId]` | S5 (and S3 first use) |
| `mockups/po-review.html` | `[projectId]/purchase-orders/[versionId]` (renamed from `po-confirm.html`) | S6 (and S1's R7 fix) |
| `mockups/sales-order-review.html` | `[projectId]/sales-orders/[psoId]` (renamed from `so-findings.html`) | S7 (and S3) |

Core or module: part of the existing `projects` module (`moduleKey: 'projects'`). No new module,
no new schema, no migration, no new permission.

## Scope

Screens and navigation only. The extraction, reconciliation, SO drafting and publish-gate
services are not redesigned (task brief; R3 "the two-tier publish gate is unchanged"). The lavish
review (R17) drops the Needs attention list, which was this plan's only backend addition; there
is no new endpoint, no new service and no new route anywhere in this plan. Every slice is
frontend-only.

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

### Lavish review, 24 Sep 2026 (binding, quoted)

The owner reviewed the first mockup drawing in one lavish session (R5's method) and found it too
complex; these rulings supersede R2 (the Needs attention page) and part of R3 (one shared findings
component as a separate surface) and replace R5's un-numbered mockups with the four redrawn ones
above. A follow-up ruling (R21) after seeing the redrawn `project-listing-start.html` moves Start
from a per-row button (R14(a)) to one page-level button. The owner then approved the whole set
(R22), closing R9's production check and setting a standing design constraint (its own section
below). R23 closes the finding-collapse open question as a reading of that approval. R10's slice
order and R6/R7/R8 stand unchanged.

> R11 [round 1] "imo the mockups are way too complicated, it is very taxing for the users, please
> simplify that."
>
> R12 [round 1, page defect, not a design ruling] "and I can't see them fully, they are shrunk,
> please display them fully" -- fixed by re-rendering the mockups at full size for this review.
>
> R13 [R9 follow-up] "if 404 just show properly don't show too technical message" -- a missing PDF
> renders a plain empty state ("This PDF is not available yet" plus an upload action), never a raw
> error or status code, on every screen that embeds a PDF.
>
> R14 [round 2] "ok you see, this is going to be uploaded by project sales coordinator, okay, so by
> that time, the project should be in already, so, as a project sales admin, what does he need to
> do, he needs to upload PO right, so why don't he go to the project listing, and click Start as a
> CTA, so for project sales coordinator access, it can select upload PO / upload delivery schedule
> in the dropdown, so when he upload, he choose the project, then upload, then go to the PO
> verification page, personally, i don't like our current page cause too narrow, 1 on the left 1,
> 1 on the right, eat up too much space, we should just show what we have matched, and for its
> documents, put it in another tab." Three rulings in one: (a) the entry point is the existing
> Project listing, a Start button per row opening a small menu, Upload PO / Upload delivery
> schedule, already scoped to that row's project; (b) no left/right split pane on the PO review
> page, the lines table takes the full width, focused on what matched; (c) the PO document moves to
> its own Documents tab.
>
> R15 [round 2] "the entry point of delivery schedule review should be from the project listing"
> and "this page should comes from Project listing > Start > Upload PO, and I need it to be focused
> on the lines identified" -- the schedule review page shares R14(a)'s entry point; "focused on the
> lines identified" restated for the PO review page.
>
> R16 [round 2] "actually until today, I still dont know why we need two table for SO, why not just
> 1 table sales order" -- the sales order page becomes one lines list, not a Lines tab plus a
> Findings tab.
>
> R17 [round 3] "i don't really needs 'Needs attention', everything just come from pipeline" -- the
> Needs attention sidebar page (R2) is dropped in full; every upload and every review starts from
> the existing Project listing (R14(a)).
>
> R18 [round 3] "the PO document should always be at its own tab" -- restates R14(c) as an
> absolute: the PO review page carries a Documents tab always, not only when the lines panel is
> short of room.
>
> R19 [round 3] "i need the findings to be more tabulated, like in a list view where the user can
> clear off 1 by 1" -- a finding is a row with one clear action, not a card.
>
> R20 [round 3] "i think using Lines will do, don't need findings"; "consolidate lines and findings
> into 1 so the user don't need to look at two tabs" (PO review); "consolidate matrix and findings
> into 1 so the user don't need to toggle tabs" (schedule review). Supersedes R3's "one shared
> findings component" as its own surface: a finding now renders on the row of the table it belongs
> to (the schedule matrix row, the PO line row, the SO line row), never a second table or a
> Findings tab. R3's other terms stand as written: one severity set, one verb "Dismiss with a
> reason", duplicates collapsed, the two-tier publish gate unchanged.
>
> R21 [follow-up, after seeing the redrawn mockup] "the start button should be at top right, so it
> is start -> register a project, upload PO, upload delivery schedule." Supersedes R14(a)/R17's
> "Start button per row": Start is ONE page-level primary button, top right of the Project listing
> (the `PageHeader` action slot), not one per row. Its menu has three items in this order: Register
> a project, Upload PO, Upload delivery schedule. Register a project opens the existing project
> create flow unchanged (folding today's separate button into the Start menu). Upload PO and
> Upload delivery schedule open the upload dialog with a required project `SearchableSelect` first
> (clearable, searchable, per the earlier ruling "when he upload, he choose the project, then
> upload"), then the file, then straight to that document's review page, exactly as before. Rows
> lose the Start button.
>
> R22 [approval, after R21] "yeah all good for me, just make sure we keep it as simple as
> possible, as guided as possible when we are designing the UI, currently the UI for the entire
> project management is too sloppy and messy, information overload, visual fatigue, the PDF check
> is small matter, as long as the PDF shows and when it is not found we show a proper not found
> page then is okay for me." Approves the four redrawn mockups and R21 as they stand. Sets a
> standing design constraint for every screen this plan touches (own section below). Closes R9:
> the R13 "This PDF is not available yet" empty state is enough, no separate production check is
> owed.
>
> R23 [reading, not a direct quote] Closes the finding-collapse open question from the mockup
> review: a hard SO finding and the schedule finding that causes it collapse into one row (one
> card), naming both codes, with one Dismiss action. Reading of the owner's "all good" (R22),
> which covered the in-page recommendation shown during the lavish review; revisit if the owner
> objects.

Reading (the plan's own summary, not a quote): the Needs attention list is dropped; the entry
point for every upload is ONE Start button, top right of the Project listing (Project Sales >
Pipeline, Grid view), opening a menu of three items, Register a project, Upload PO, Upload
delivery schedule, in that order (R21). Upload PO and Upload delivery schedule ask for the project
first, a required, clearable, searchable `SearchableSelect`, since Start no longer reads the
project off a row. Each review screen is one page: the schedule matrix, the PO lines table, or the
SO lines list, with the finding shown and cleared on its own row (a Flag cell plus one "Dismiss
with a reason" action), plus a Documents tab (the uploaded file, and for the PO also the
rejected-note reasons) that is always present. No Findings tab anywhere, no left/right split pane;
the table takes the full page width. One primary button per page (Confirm schedule / Confirm this
PO / Publish). A missing PDF is a plain empty state, never an error code.

## Design constraint (R22)

Every screen in this plan is built simple and guided: one table, one primary action, no
explanatory text on screen, no information the user does not act on. This is not a new rule so
much as R22 naming, in the owner's own words, the standard PRINCIPLES and DESIGN-LANGUAGE already
set ("no feature explanations inside the UI", the frequency gate, one primary button per record)
and holding this plan to it explicitly, because the owner named the wider project management UI as
"too sloppy and messy, information overload, visual fatigue" today. Each slice's Definition of
Done carries the line: reviewer checks the screen against R22: fewer elements than the mockup is
fine, more is a defect.

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
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect.

### S2. One Start button on the Project listing (full track)

Rewritten per R21: Start is a page-level button, top right of the Project listing header, not one
per row; its menu is Register a project, then Upload PO, then Upload delivery schedule, and the
two uploads ask for the project since a page-level Start no longer has a row to read it from.

- **Backend seam:** none. `POIntakeUploadDialog` and `DeliveryScheduleUploadDialog` already accept
  an optional `projectId` / `project` prop; Start's page-level call site simply omits it, which is
  the same "no `projectId` passed" branch the dialogs already need to support a project picker, so
  there is nothing to add on the server.
- **Frontend seam:** one Start button in the Pipeline page's `PageHeader` action slot (top right,
  replacing today's standalone "Register a project" button), opening a `DropdownMenu` with three
  items in order: Register a project, Upload PO, Upload delivery schedule. Register a project
  opens the existing `RegisterProjectDialog` unchanged. Upload PO and Upload delivery schedule open
  their existing dialogs with a required project `SearchableSelect` (clearable) shown first; once a
  project is picked, the rest of each dialog behaves exactly as today's per-project call (schedule
  upload's Purchase order / Revision of / Issued by fields narrow to the chosen project). The
  picker lists projects with `can_edit` (same guard S2 always carried). `PipelineBoard.tsx` and
  `ProjectsGrid.tsx` lose the per-row Start action drawn in the first pass of this slice; row
  click still opens the project, unchanged. On a successful upload the dialog pushes straight to
  the version's review page (PO or schedule), exactly as today's per-project upload already does.
- **Tests:** vitest for the page-level Start button and its three-item menu (order asserted,
  Register a project opens the existing dialog, Upload PO / Upload delivery schedule open their
  dialogs with a required project field rendered this time, no project field only when the dialog
  is opened from inside a project's own tab); existing dialog tests stay green unedited except the
  ones asserting "no project field ever renders", which flip to "renders when opened without a
  `projectId`" (the S2 call site never carries one). Recorded agent-browser run for S2-8: from `/`,
  expand Project Sales, click Pipeline, click Start (top right), click Upload PO, pick Setia Alam,
  see the dropzone. Same for Upload delivery schedule. At 1280 and 375.
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect.

### S3. Inline row findings, one Dismiss per row, one list (full track, mostly FE)

- **Backend seam:** none. The acknowledge endpoints
  (`POST /sales-orders/{pso_id}/findings/{finding_id}/acknowledge`,
  `POST .../schedule-findings/{finding_id}/acknowledge`) and the column dismissal are called as
  today.
- **Frontend seam:** no `FindingsList` component and no Findings tab anywhere (supersedes R3's
  "one shared findings component" as its own surface, per R20). Two small shared pieces instead:
  (1) a collapse utility, `collapseFindings(findings)` in `PS/_shared/lib/findings.ts`, the same
  same-code/same-subject key from UAC S3-3, returning one row per distinct key with its member ids
  and a count; (2) one dialog, `DismissReasonDialog.tsx` (renamed in place from
  `SalesOrderAcknowledgeDialog`), a reason input (3-character minimum) and a button naming the
  count, calling `onDismiss(ids, reason)`. Each screen's own table (the schedule matrix in S5, the
  PO lines grid in S6, the SO lines list in S7) renders a Flag cell using the same three-severity
  pill (`Agrees` / `Blocks publish` / `Needs acknowledgement`, a `Badge` `status`) and, on a
  flagged row, one "Dismiss with a reason" action opening `DismissReasonDialog`. There is never a
  second findings surface live beside the table it describes.
- **Tests:** vitest for `collapseFindings` (collapse key precedence per S3-3, no collapse without
  a key) and `DismissReasonDialog` (3-character minimum, the count in the button label, fires
  `onDismiss` once per underlying id with one reason, verb text). The existing pytest for
  `_refresh_status`, `publish` and the manage-permission override run unedited (S3-5).
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect. Includes R23: a hard SO finding and the schedule finding causing it collapse into one
  row naming both codes, with one Dismiss.

### S4. Return after Confirm (small fix track, FE only)

- **Backend seam:** none.
- **Frontend seam:** the Project listing (a Start-driven upload, R21) and the project tab panels
  already link into a review page; their hrefs carry `from` through `appendListState` (list,
  naming the row for whichever project was picked in the Start dialog) or the originating `?tab=`.
  The PO review page, schedule review and SO page read it with `useHrefWithListState`, and on a
  successful Confirm / Confirm schedule / Publish `router.push` there; with no origin they stay
  (today's behaviour). The upload dialogs (from Start, or from a project's own tab) forward the
  origin into the review URL they push to.
- **Tests:** vitest per page: confirm with origin navigates, without origin stays; upload
  forwards origin. Browser pass S4-6.
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect.

### S5. Delivery schedule review screen (full track, FE only; first of the three; per approved
`mockups/delivery-schedule-review.html`)

- **Backend seam:** none; same queries and mutations.
- **Frontend seam:** `DeliveryScheduleReviewClient.tsx` recomposed: `PageHeader` with the meta
  line and `RecordNavigation`; two tabs, Schedule (default) and Documents. Schedule is the
  existing matrix (`DeliveryScheduleMatrix` / `DeliveryScheduleByDateMatrix`) with
  `DeliveryScheduleReconciliationList` folded into it as a Flag column and an inline Dismiss
  action per S3, using `DeliveryScheduleProductPicker` for the fix action on a flagged row; "Only
  rows with a flag" is the default filter while the version is unconfirmed. `DeliveryScheduleRevisionDiff`,
  `DeliveryScheduleRevisionProposals` and `DeliveryScheduleNotes` move into a secondary "History"
  button on the Schedule tab's toolbar, opening a `Sheet`, instead of three separate tabs -- kept
  reachable rather than removed, since the lavish review's ask (R20) was to stop toggling between
  the matrix and its findings, not to drop revision history. Documents renders the schedule file
  (the PDF viewer, or the R13 empty state) with an upload action.
  `DeliveryScheduleColumnCards` stays the 375 rendering of the matrix.
- **Tests:** vitest on the recomposed client (two tabs only, default filter while unconfirmed, a
  flagged row shows the full customer code and a Dismiss action, the History sheet opens with the
  three existing sections, the missing-PDF empty state on Documents); existing matrix tests stay
  green. Browser pass S5-6 at 1280 and 375.
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect.

### S6. PO review screen (full track, FE only; renamed from "PO confirm"; per approved
`mockups/po-review.html`)

- **Backend seam:** none.
- **Frontend seam:** `POIntakeConfirmClient.tsx` recomposed: header status trail (Confirmed /
  Approved / Countersigned) and the document-total-vs-our-sum line replace the three-cell stamp
  card and the banner; two tabs, Lines (default) and Documents -- no PDF beside the lines table
  (R14(b)). Lines is the existing `POIntakeLinesGrid` with a Flag column and an inline Dismiss
  action per S3, opening on "Lines identified" (today's "Show only these" filter, on by default
  while unconfirmed) with "Show all lines (N)" one click away (R14(b)/R15). Documents holds the
  PDF viewer (unchanged component, or the R13 "This PDF is not available yet" empty state with an
  upload action instead of a raw 404) with `POIntakeAnnotationsGrid` (R7's full-text reason)
  directly below it -- both concerns about the uploaded file in the one tab, always present, per
  R18.
- **Tests:** vitest on the recomposed client (trail states, two tabs only, default filter, Lines
  identified vs Show all lines, Documents renders the PDF and the annotations grid together, the
  R13 missing-PDF empty state renders no error code); browser pass S6-4.
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect.

### S7. Sales order review screen (full track, FE only; renamed from "SO findings"; per approved
`mockups/sales-order-review.html`)

- **Backend seam:** none.
- **Frontend seam:** `SalesOrderDetailClient.tsx` recomposed: header meta with area group and PO
  version, gate count under Publish replacing the refusal banner; two tabs, Lines (default while
  anything is open) and AutoCount differences; Activity becomes a plain link in the meta line, not
  a tab. R16 ("why not just 1 table sales order") is answered by merging Lines and Findings into
  the one table this slice ships; AutoCount differences stays a separate tab because it compares
  against a different system, not a duplicate of the line list. Lines is one `DataGrid` with a
  Flag column and an inline Dismiss action per S3, rendering both the sales order's own findings
  and the schedule-level findings (`GET /purchase-orders/{po_id}/schedule-findings`) as rows, each
  naming its source; summary facts render `-` for unknowns.
- **Tests:** vitest on header, default tab, and the merged Lines table (rows from both finding
  sources, Flag column, Dismiss inline, AutoCount differences stays a separate tab); browser pass
  S7-4.
- **DoD:** reviewer checks the screen against R22: fewer elements than the mockup is fine, more is
  a defect. Includes R23's collapse for a blocking SO finding and its causing schedule finding.

## Open questions for the mockup review

The owner approved the redrawn mockups in full (R22, "yeah all good for me"), which closes two of
the three questions below; one remains open.

1. CLOSED by R23. Should a hard SO finding and the schedule finding that causes it (for example
   CB1178A "the schedule only places 0" and the unmapped column BUI-HB-CB1178ASS) also collapse,
   as two codes for one cause? This plan had collapsed same code + same subject only; R23 extends
   S3-3's collapse rule for this specific pairing: one row (one card), both codes listed, one
   Dismiss. This is a reading of the owner's blanket "all good", not a direct answer to the
   in-page question; revisit if the owner objects.
2. Still open. There is no Needs attention list to drop off from any more (R17). A schedule
   confirmed with columns still unreconciled (HQ/26/01/121 v2, 35 of 44) keeps its flagged rows in
   the Schedule tab exactly as any other list row would: visible until a human fixes or dismisses
   each one, with no separate "gone" state. This plan assumes that is the intended behaviour; it
   was not a named ruling.
3. CLOSED by R22. Owner check on the PO HQ/26/01/121 v1 PDF viewer in production is no longer
   owed: "the PDF check is small matter, as long as the PDF shows and when it is not found we show
   a proper not found page then is okay for me." The R13 empty state (S5-5, S6-5) is the answer;
   there is no separate bug lane to open even if production shows the same 404 the audit saw
   locally.

## Deferred

- Active-company indicator on lists: dropped by R8, not deferred.
- Order Change Notice and amendment entry points (audit open question 6): not in the rulings.
