# UAC: PO and delivery schedule redesign (issue #1167)

Plan: `documentation/plans/projects/PLAN-po-schedule-redesign-24sep.md`. Evidence:
`AUDIT-po-schedule-flow-24sep.md` and its screenshots (PR #1183, branch
`docs/po-schedule-ux-audit`). Mockups: `documentation/plans/projects/mockups/`.

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` recorded agent-browser run (no new Playwright spec),
`[T]` text or copy check. Every AC traces to a journey step (J1 to J6).

## Journey

Actor: a project salesperson (or their manager) at Sorento who has a customer PO or a delivery
schedule PDF in hand, or who needs to clear what the system flagged.

- **J1. First screen.** From `/`, they expand Project Sales and click **Needs attention**. They
  see every PO, schedule and sales order, across projects, that is waiting on a human, with why.
  Two clicks.
- **J2. Upload.** They click **Upload PO** (or **Upload schedule**) on that list. The dialog asks
  for the project first; everything else is today's dialog. The system already knows the company
  and, once the project is picked, its POs and parties. They drop the PDF.
- **J3. Review.** The upload lands them on the full-page review screen for that record (PO
  confirm, or schedule review), laid out per the approved mockup: facts in the header, one
  primary button, tabs with counts, the thing that needs a look shown first.
- **J4. Findings.** Wherever findings exist (PO, schedule, sales order) they read one list in one
  shape: three severities, one verb "Dismiss with a reason", duplicates collapsed.
- **J5. Confirm and return.** They click Confirm (or Publish). They land back where they came from
  (Needs attention or the project tab), with the row they opened restored, and that row gone once
  nothing is left for a human.
- **J6. Words.** On every screen and in the docs they meet "Area" (never "Phase") and "AutoCount
  differences" (never "divergence").

## S1. Renames + rejected-note reason (small fix track)

- **S1-1 [FE][T] (J6)** No user-visible string under `app/(protected)/project-sales/` that refers
  to a delivery-schedule phase says "phase" or "Phase"; each says "area" / "Area". Task-template
  "Phase" (`TaskFormDialog`, `TasksPanel`, `setup/.../TemplateChecklistPanel`) is a different
  concept and is unchanged. A vitest renders `DeliveryScheduleReviewClient` and asserts the view
  toggle reads "By area".
- **S1-2 [FE][T] (J6)** The SO divergence page title and heading read "AutoCount differences"
  (today "AutoCount comparison"); no user-visible string in project-sales says "divergence".
  Route paths (`/project-sales/divergences`, `.../[psoId]/divergence`) and identifiers are
  unchanged.
- **S1-3 [T] (J6)** Toast "Schedule confirmed. Its phases are on the project." reads "... Its areas
  are on the project."
- **S1-4 [FE] (J4)** In `POIntakeAnnotationsGrid`, a note with `action_note` renders the full text,
  wrapping, under "By {name} · {date}" in the Reviewed column; it is not cut to one line and the
  text is readable without hovering. A vitest renders a rejected annotation with a 200-character
  `action_note` and asserts the whole string is in the document and not only in a `title`.
- **S1-5 [FE] (J4)** A rejected annotation with no `action_note` still shows reviewer and date,
  and no empty reason line.
- **S1-6 [E2E] (J6)** Browser pass at 1280 and 375 on the schedule review and PO version pages of
  PRJ-000001: no "Phase" visible, rejected notes show their reason.

## S2. Needs attention list with uploads

- **S2-1 [BE] (J1)** `GET /api/v1/project-sales/needs-attention` returns one row per record with
  `type` (`po` | `schedule` | `sales_order`), a human number, project code and name, `status`,
  `waiting_since`, and the counts behind "Why it is here". Response model declares every field
  (a pytest asserts each, since `response_model` drops undeclared fields).
- **S2-2 [BE] (J1)** A PO appears when its latest version has no `confirmed_at`, or when its
  To check count (`model_mismatch_count + price_mismatch_count`, the POs tab's own sum) is above
  zero. Status is "to_confirm" or "to_check" respectively (to_confirm wins). It disappears once
  neither holds. One pytest per branch plus one for "gone".
- **S2-3 [BE] (J1)** A schedule appears when its latest version has no `confirmed_at`, or has
  `reconciled_columns < total_columns`. Status "to_confirm" or "unreconciled". A version still
  being read (`extraction_state` queued or running) appears as "reading"; a failed read as
  "failed". One pytest per branch.
- **S2-4 [BE] (J1)** A sales order appears when its status is `blocked` or `draft` (the two
  statuses `_refresh_status` sets while findings are open); `ready`, `published` and later do not
  appear. The row carries its unacknowledged hard and warn counts.
- **S2-5 [BE] (J1)** Company scope: a row from another company never appears (seed two companies,
  assert). Reading stays open across owners inside the company, as `can_edit_project` documents.
- **S2-6 [BE] (J1)** Filters `type`, `project_id`, `status`, `query` (number or project name) and
  `page`/`limit` work; auth denial without `projects.projects.view` returns 403; a bad
  `project_id` returns 422 or 404 per `validate_uuid_path`.
- **S2-7 [FE] (J1)** The sidebar shows "Needs attention" under Project Sales, directly after
  Pipeline, in BOTH `MENU_SIDEBAR` and `MENU_SIDEBAR_COMPACT` in `config/menu.config.tsx`, gated by
  `projects.projects.view`. A vitest asserts both entries.
- **S2-8 [FE] (J1)** The page is a `DataGrid` (`tableLayout: { width: 'fixed', columnsResizable:
  true }`, explicit `size`, `truncate` + `title`), type and status as `Badge` pills, standard
  pagination bar always shown, no Open column, row click opens the record's review page.
- **S2-9 [FE] (J2)** "Upload PO" opens `POIntakeUploadDialog` with a required Project
  `SearchableSelect` shown first; after a project is picked, the dialog posts to the existing
  `POST /projects/{project_id}/purchase-orders/upload`. Opened from the project POs tab, the field
  does not render and the dialog behaves exactly as today (existing tests stay green).
- **S2-10 [FE] (J2)** "Upload schedule" does the same for `DeliveryScheduleUploadDialog`: project
  first, then today's Purchase order / Revision of / Issued by fields narrowed to that project.
- **S2-11 [FE] (J2)** The project picker offers only projects the user can edit (`can_edit` on the
  project row); the upload endpoint's own edit check is unchanged and still decides.
- **S2-12 [E2E] (J1, J2)** From `/`: expand Project Sales, click Needs attention (2 clicks), click
  Upload PO, pick Setia Alam, see the dropzone. Same for Upload schedule. At 1280 and 375.

## S3. Shared findings component

- **S3-1 [FE] (J4)** One component, `FindingsList`, renders findings in three severities labelled
  "Blocks publish" (hard), "Needs acknowledgement" (warn), "Info" (info), as filter chips with
  counts plus "Dismissed".
- **S3-2 [FE] (J4)** The only dismiss verb is "Dismiss with a reason". A text check asserts
  "Override with a reason", "Clear with a reason" and "Dismiss as false signal" appear nowhere
  in project-sales.
- **S3-3 [FE] (J4)** Findings with the same `code` about the same subject render as one row with
  a count. Subject key, first present wins: `line_id`, then `detail_json.customer_code_raw` (a
  schedule column; the unmapped-column finding carries one row per area), then
  `detail_json.product_code`, then `detail_json.line_no`. Dismissing the row calls the existing
  acknowledge endpoint once per underlying finding with the same reason. A finding with none of
  these keys never collapses.
- **S3-4 [FE] (J4)** The dismiss dialog requires a reason of at least 3 characters (the service's
  existing rule) and names the count ("Dismiss 7").
- **S3-5 [FE][BE] (J4)** The publish gate is unchanged: a pytest pins that warn findings leave an
  SO `draft` and publishable and hard findings leave it `blocked`; a hard finding's dismiss is
  still refused without `projects.projects.manage` (existing tests stay green, none edited).
- **S3-6 [FE] (J4)** On the SO page, the sales-order findings and the schedule-level findings
  (`GET /purchase-orders/{po_id}/schedule-findings`) render in ONE `FindingsList`, each row naming
  its source. `ScheduleFindingsSection` and the three cards of `SalesOrderFindingsSection` are
  removed, not left beside it.
- **S3-7 [FE] (J4)** On the schedule review page, the per-column verdicts render through the same
  component, blocked as "Blocks publish" and warning as "Needs acknowledgement", mirroring
  `buildColumnStates`.

## S4. Return after Confirm

- **S4-1 [FE] (J5)** A review page opened from Needs attention or a project tab carries a `from`
  describing the origin (list state per `appendListState`, or `?tab=`).
- **S4-2 [FE] (J5)** After a successful Confirm on the PO version page (today: stays on the page,
  toast only) the user is navigated to the origin. Same for Confirm schedule (today: closes the
  dialog, stays) and Publish on the SO page.
- **S4-3 [FE] (J5)** With no origin (deep link, bookmark) the user stays on the page, as today.
- **S4-4 [FE] (J5)** Back on Needs attention, the row named by `from` scrolls into view and
  highlights (DESIGN-LANGUAGE section 7), or is gone if nothing is left for a human.
- **S4-5 [FE] (J3)** After an upload from Needs attention, the review page's origin is Needs
  attention, so the Confirm that follows returns there.
- **S4-6 [E2E] (J5)** Needs attention -> PO version -> Confirm -> back on Needs attention.

## S5. Delivery schedule review screen (per approved mockup)

- **S5-1 [FE] (J3)** Header per mockup 1: number and version, status pill, the meta line, record
  navigation, one primary button; the "This schedule is confirmed, so nothing here can be changed"
  sentence is gone.
- **S5-2 [FE] (J3)** Line tabs Matrix / Findings / Changes since vN / Re-dating / Notes, each with
  its count; tab strip scrolls at 375.
- **S5-3 [FE] (J3)** The separate reconciliation table is gone; status is a matrix column, a row
  click opens the column card with the full customer code, the product picker and Dismiss.
- **S5-4 [FE] (J3)** While unconfirmed, the matrix opens filtered to columns to fix; "By area /
  By date" toggle works as today's "By phase / By date".
- **S5-5 [FE] (J3)** Every section renders when empty, with `-` per ADR 1e.
- **S5-6 [E2E] (J3)** HQ/26/01/121 v2 at 1280 and 375 matches the approved mockup's callouts.

## S6. PO confirm screen (per approved mockup)

- **S6-1 [FE] (J3)** Header per mockup 2: status trail pills Confirmed > Approved > Countersigned
  with who and when; document total vs our sum on one line; "Back to the project" removed.
- **S6-2 [FE] (J3)** Right panel line tabs Lines / Findings / Header / Document notes with counts;
  the PDF viewer stays left at 1280 and becomes a "Document" tab at 375.
- **S6-3 [FE] (J3)** Lines open with today's "Show only these" filter on while unconfirmed.
- **S6-4 [E2E] (J3)** HQ/26/01/121 v1 at 1280 and 375 matches the approved mockup.

## S7. Sales order findings screen (per approved mockup)

- **S7-1 [FE] (J4)** Header per mockup 3 with Area group and customer PO version in the meta
  line; the "Publishing is refused" banner is replaced by the count under Publish.
- **S7-2 [FE] (J4)** Line tabs Findings / Lines / AutoCount differences / Activity; Findings is
  the default while any finding is open.
- **S7-3 [FE] (J4)** Summary card renders `-` for unknown values (ADR 1e).
- **S7-4 [E2E] (J4)** PSO-000003 at 1280 and 375 matches the approved mockup.

## Out of scope (rulings)

- **OOS-1** Any active-company indicator on lists (R8).
- **OOS-2** A unified findings page, or moving findings off their entity (R3).
- **OOS-3** Any change to extraction, reconciliation, drafting or the publish gate services.
- **OOS-4** The PDF viewer 404 (R9) until the owner has checked production.
