# UAC: PO and delivery schedule redesign (issue #1167)

Plan: `documentation/plans/projects/PLAN-po-schedule-redesign-24sep.md`. Evidence:
`AUDIT-po-schedule-flow-24sep.md` and its screenshots (PR #1183, branch
`docs/po-schedule-ux-audit`). Mockups: `documentation/plans/projects/mockups/`.

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` recorded agent-browser run (no new Playwright spec),
`[T]` text or copy check. Every AC traces to a journey step (J1 to J6).

## Journey

Actor: a project salesperson (or their manager) at Sorento who has a customer PO or a delivery
schedule PDF in hand, or who needs to clear what the system flagged.

Rewritten after the lavish review (24 Sep 2026): there is no cross-project Needs attention list
(R17). Every upload and every review starts from the existing Project listing.

- **J1. First screen.** From `/`, they expand Project Sales and click **Pipeline**. They click
  **Start** on their project's row; a small menu offers **Upload PO** and **Upload delivery
  schedule**, already scoped to that project. Two clicks to Pipeline, one more to Start.
- **J2. Upload.** They click Upload PO (or Upload delivery schedule) from that row's Start menu.
  The project is already fixed by the row, so the dialog has no project field; everything else is
  today's dialog. They drop the PDF.
- **J3. Review.** The upload lands them on the full-page review screen for that record (PO
  review, or schedule review), laid out per the approved mockup: facts in the header, one primary
  button, two tabs (the lines or matrix table, and Documents), the thing that needs a look shown
  first. A Documents tab that cannot find its file renders a plain "This PDF is not available yet"
  state, never an error code.
- **J4. Findings.** Wherever findings exist (PO, schedule, sales order) they read them on the row
  of the table they belong to: a Flag cell in the three severities, one verb "Dismiss with a
  reason", duplicates collapsed. There is no separate Findings tab or list to cross-reference
  against a line number.
- **J5. Confirm and return.** They click Confirm (or Publish). They land back where they came from
  (the Pipeline row they clicked Start on, or the project tab), with that row restored.
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

## S2. Start menu on the Project listing

Rewritten after the lavish review: the Needs attention list is dropped (R17); every upload starts
from the existing Project listing (Project Sales > Pipeline).

- **S2-1 [FE] (J1)** Every project row on Pipeline, in both the Board and the Grid view, carries a
  "Start" button.
- **S2-2 [FE] (J1)** Start opens a small menu with two items, "Upload PO" and "Upload delivery
  schedule". A vitest asserts both items and that no project picker renders anywhere in the menu
  or the dialogs it opens.
- **S2-3 [FE] (J2)** "Upload PO" opens `POIntakeUploadDialog` scoped to that row's project id, and
  posts to the existing `POST /projects/{project_id}/purchase-orders/upload`; the dialog has no
  project field and behaves exactly as today's per-project dialog (existing tests stay green,
  unedited).
- **S2-4 [FE] (J2)** "Upload delivery schedule" does the same for `DeliveryScheduleUploadDialog`:
  scoped to that row's project immediately, with today's Purchase order / Revision of / Issued by
  fields already narrowed to it.
- **S2-5 [FE] (J3)** A successful upload lands the user on that document's review page (PO review
  or schedule review), exactly as today's per-project upload flow does.
- **S2-6 [E2E] (J1, J2)** From `/`: expand Project Sales, click Pipeline, click a project row's
  Start, click Upload PO, see the dropzone already scoped to that project. Same for Upload
  delivery schedule. At 1280 and 375.

## S3. Inline row findings, one Dismiss per row, one list

Rewritten after the lavish review: findings render on the row of the table they belong to, never
a separate Findings tab, list or card (supersedes the "one shared `FindingsList` component" shape;
R3's other terms -- one severity set, one verb, duplicates collapsed, the gate unchanged -- stand).

- **S3-1 [FE] (J4)** On each review screen (the schedule matrix, the PO lines table, the SO lines
  list), a row with an open finding carries a Flag cell in the three severities: "Blocks publish"
  (hard), "Needs acknowledgement" (warn), "Info" (info), styled as the shared `Badge` `status`
  pill.
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
  (`GET /purchase-orders/{po_id}/schedule-findings`) render as rows of the SAME Lines table, each
  row naming its source. `ScheduleFindingsSection` and the three cards of
  `SalesOrderFindingsSection`, plus the retired `FindingsList`, are removed, not left beside it.
  There is no tab literally labelled "Findings" anywhere in project-sales.
- **S3-7 [FE] (J4)** On the schedule review page, the per-column verdicts render as a Flag column
  of the SAME Schedule tab's matrix, not a separate tab, blocked as "Blocks publish" and warning
  as "Needs acknowledgement", mirroring `buildColumnStates`.

## S4. Return after Confirm

Rewritten after the lavish review: the origin a review page returns to is the Pipeline row a
Start-driven upload was launched from, or the originating project tab; there is no Needs
attention list to return to.

- **S4-1 [FE] (J5)** A review page opened via Start on a Pipeline row, or via a project tab,
  carries a `from` describing the origin (list state per `appendListState` for the Pipeline grid,
  or `?tab=` for the project).
- **S4-2 [FE] (J5)** After a successful Confirm on the PO review page (today: stays on the page,
  toast only) the user is navigated to the origin. Same for Confirm schedule (today: closes the
  dialog, stays) and Publish on the SO page.
- **S4-3 [FE] (J5)** With no origin (deep link, bookmark) the user stays on the page, as today.
- **S4-4 [FE] (J5)** Back on Pipeline, the project row named by `from` scrolls into view and
  highlights (DESIGN-LANGUAGE section 7).
- **S4-5 [FE] (J3)** After an upload via Start on a Pipeline row, the review page's origin is that
  Pipeline row, so the Confirm that follows returns there.
- **S4-6 [E2E] (J5)** Pipeline -> Start -> Upload PO -> PO review -> Confirm -> back on Pipeline,
  the row highlighted.

## S5. Delivery schedule review screen (per approved `mockups/delivery-schedule-review.html`)

Rewritten after the lavish review: two tabs only, no Findings tab (R20); Changes since vN,
Re-dating and Notes move into a secondary History panel rather than tabs of their own.

- **S5-1 [FE] (J3)** Header per the mockup: number and version, status pill, the meta line,
  record navigation, one primary button (Confirm schedule); the "This schedule is confirmed, so
  nothing here can be changed" sentence is gone.
- **S5-2 [FE] (J3)** Two tabs, Schedule (default) and Documents; no tab literally labelled
  "Findings", "Changes", "Re-dating" or "Notes". A secondary "History" button on the Schedule
  tab's toolbar opens those three (changes since the previous version, re-dating proposals,
  document notes) in one panel.
- **S5-3 [FE] (J3)** The separate reconciliation table is gone; a column with an open finding
  carries a Flag cell and one "Dismiss with a reason" action on its own matrix row -- no click
  needed to open a separate card to see or clear it.
- **S5-4 [FE] (J3)** While unconfirmed, the matrix opens filtered to rows carrying a flag; "By
  area / By date" toggle works as today's "By phase / By date".
- **S5-5 [FE] (J3)** The Documents tab renders the schedule file, or, when it cannot be found, a
  plain "This PDF is not available yet" state with an upload action -- never an error code or a
  raw status number (R13).
- **S5-6 [FE] (J3)** Every section renders when empty, with `-` per ADR 1e.
- **S5-7 [E2E] (J3)** HQ/26/01/121 v2 at 1280 and 375 matches the approved mockup's callouts.

## S6. PO review screen (per approved `mockups/po-review.html`; page renamed from "PO confirm")

Rewritten after the lavish review: two tabs only, no left/right split pane (R14(b)); the PDF and
the rejected-note reasons move together into Documents, always present (R18).

- **S6-1 [FE] (J3)** Header per the mockup: status trail pills Confirmed > Approved > Countersigned
  with who and when; document total vs our sum on one line; "Back to the project" removed.
- **S6-2 [FE] (J3)** Two tabs, Lines (default) and Documents; the PDF viewer is never shown beside
  the lines table, at 1280 or at 375 -- Lines takes the full page width in both.
- **S6-3 [FE] (J3)** Lines opens on "Lines identified" (today's "Show only these" filter, on by
  default while unconfirmed); "Show all lines (N)" is one click away.
- **S6-4 [FE] (J3)** A line with an open finding carries a Flag cell and one "Dismiss with a
  reason" action on its own row; there is no separate Findings tab or card.
- **S6-5 [FE] (J3)** The Documents tab renders the PDF viewer, or, when it cannot be found, the
  S5-5 empty state (R13), with the rejected-note reasons (R7, `POIntakeAnnotationsGrid`) directly
  below it, both in the one tab, always present.
- **S6-6 [E2E] (J3)** HQ/26/01/121 v1 at 1280 and 375 matches the approved mockup.

## S7. Sales order review screen (per approved `mockups/sales-order-review.html`; page renamed
from "SO findings")

Rewritten after the lavish review: one lines list, not a Lines tab plus a Findings tab (R16).

- **S7-1 [FE] (J4)** Header per the mockup with Area group and customer PO version in the meta
  line; the "Publishing is refused" banner is replaced by the count under Publish.
- **S7-2 [FE] (J4)** Two tabs, Lines (default while any finding is open) and AutoCount
  differences; Activity is a plain link in the meta line, not a tab.
- **S7-3 [FE] (J4)** Lines is one `DataGrid`; a line with an open finding, from this sales order or
  from the schedule it was split from, carries a Flag cell naming its source and one "Dismiss with
  a reason" action on its own row. There is no tab literally labelled "Findings" and no separate
  findings card.
- **S7-4 [FE] (J4)** Summary card renders `-` for unknown values (ADR 1e).
- **S7-5 [E2E] (J4)** PSO-000003 at 1280 and 375 matches the approved mockup.

## Out of scope (rulings)

- **OOS-1** Any active-company indicator on lists (R8).
- **OOS-2** A unified findings page, or moving findings off their entity (R3, R20).
- **OOS-3** Any change to extraction, reconciliation, drafting or the publish gate services.
- **OOS-4** The PDF viewer 404 (R9) until the owner has checked production.
- **OOS-5** A cross-project pending list ("Needs attention"): dropped in full by R17, not
  deferred.
