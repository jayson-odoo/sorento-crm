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
(R17). Every upload and every review starts from the existing Project listing, via ONE Start
button, top right of the page (R21), not one per row.

- **J1. First screen.** From `/`, they expand Project Sales and click **Pipeline**. They click
  **Start**, top right of the page; a menu offers **Register a project**, **Upload PO** and
  **Upload delivery schedule**, in that order. Two clicks to Pipeline, one more to Start.
- **J2. Upload.** They click Upload PO (or Upload delivery schedule) from the Start menu. The
  dialog asks for the project first (a required, clearable, searchable project field), since Start
  is no longer tied to a row; everything else is today's dialog. They pick the project and drop
  the PDF.
- **J3. Review.** The upload lands them on the full-page review screen for that record (PO
  review, or schedule review), laid out per the approved mockup: facts in the header, one primary
  button, two tabs (the lines or matrix table, and Documents), the thing that needs a look shown
  first. A Documents tab that cannot find its file renders a plain "This PDF is not available yet"
  state, never an error code.
- **J4. Findings.** Wherever findings exist (PO, schedule, sales order) they read them on the row
  of the table they belong to: a Flag cell in the three severities, one verb "Dismiss with a
  reason", duplicates collapsed. There is no separate Findings tab or list to cross-reference
  against a line number.
- **J5. Confirm and return.** They click Confirm (or Publish). They land back on Pipeline, or the
  project tab they came from, with the project row they were working on restored.
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

## S2. One Start button on the Project listing

Rewritten after the lavish review: the Needs attention list is dropped (R17); every upload starts
from the existing Project listing (Project Sales > Pipeline), via ONE Start button top right of
the page, not one per row (R21).

- **S2-1 [FE] (J1)** Pipeline's `PageHeader` carries one "Start" button, top right, in both the
  Board and the Grid view; today's separate "Register a project" button is gone (folded into the
  Start menu). No project row carries a Start button.
- **S2-2 [FE] (J1)** Start opens a menu with three items, in this order: "Register a project",
  "Upload PO", "Upload delivery schedule". A vitest asserts the order.
- **S2-3 [FE] (J2)** "Register a project" opens the existing `RegisterProjectDialog` unchanged
  (existing tests stay green, unedited).
- **S2-4 [FE] (J2)** "Upload PO" opens `POIntakeUploadDialog` with a required project
  `SearchableSelect` (clearable) shown first; after a project is picked, the dialog posts to the
  existing `POST /projects/{project_id}/purchase-orders/upload`. Opened from inside a project's
  own POs tab (unchanged call site), the field does not render and the dialog behaves exactly as
  today (existing tests for that call site stay green).
- **S2-5 [FE] (J2)** "Upload delivery schedule" does the same for `DeliveryScheduleUploadDialog`:
  project first, then today's Purchase order / Revision of / Issued by fields narrowed to that
  project once picked.
- **S2-6 [FE] (J2)** The project picker offers only projects the user can edit (`can_edit` on the
  project row); the upload endpoint's own edit check is unchanged and still decides.
- **S2-7 [FE] (J3)** A successful upload lands the user on that document's review page (PO review
  or schedule review), exactly as today's per-project upload flow does.
- **S2-8 [E2E] (J1, J2)** From `/`: expand Project Sales, click Pipeline, click Start (top right),
  click Upload PO, pick Setia Alam, see the dropzone. Same for Upload delivery schedule. At 1280
  and 375.

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
  Reviewer note, 25 Sep 2026: this round added the project-sales-wide text check for
  "Override with a reason" and "Clear with a reason" (`dismissVerb.guard.test.ts`). The third
  string, "Dismiss as false signal", is still live on purpose in
  `DeliveryScheduleReconciliationList.tsx` - it is S5's to rename.
- **S3-3 [FE] (J4)** Findings with the same `code` about the same subject render as one row with
  a count. Subject key, first present wins: `line_id`, then `detail_json.customer_code_raw` (a
  schedule column; the unmapped-column finding carries one row per area), then
  `detail_json.product_code`, then `detail_json.line_no`. Dismissing the row calls the existing
  acknowledge endpoint once per underlying finding with the same reason. A finding with none of
  these keys never collapses.
  25 Sep 2026: `collapseFindings()` shipped with no caller yet, and R23's cross-code collapse is
  not implemented in it; both carried to S5 (schedule matrix) and S7 (SO lines list).
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

Rewritten after the lavish review: the origin a review page returns to is the Pipeline list a
Start-driven upload was launched from (the project chosen in the dialog, per R21, is what names
the row to restore), or the originating project tab; there is no Needs attention list to return
to.

- **S4-1 [FE] (J5)** A review page opened via Start (Upload PO or Upload delivery schedule), or
  via a project tab, carries a `from` describing the origin (list state per `appendListState` for
  the Pipeline grid, naming the row for the project picked in the dialog, or `?tab=` for the
  project).
- **S4-2 [FE] (J5)** After a successful Confirm on the PO review page (today: stays on the page,
  toast only) the user is navigated to the origin. Same for Confirm schedule (today: closes the
  dialog, stays) and Publish on the SO page.
- **S4-3 [FE] (J5)** With no origin (deep link, bookmark) the user stays on the page, as today.
- **S4-4 [FE] (J5)** Back on Pipeline, the project row named by `from` scrolls into view and
  highlights (DESIGN-LANGUAGE section 7).
- **S4-5 [FE] (J3)** After an upload via Start, the review page's origin is the Pipeline list and
  the project picked in the dialog, so the Confirm that follows returns there with that row
  highlighted.
- **S4-6 [E2E] (J5)** Pipeline -> Start -> Upload PO -> pick Setia Alam -> PO review -> Confirm ->
  back on Pipeline, the Setia Alam row highlighted.

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

  Owner hand test 25 Sep: the Lines grid was cut off at the right edge at 1280 with no way to
  reach the Amount column. It now scrolls horizontally inside its own container (the grid's
  shared `DataGridTable` scroller, not a one-off wrapper) at both 1280 and 375; the two-tabs,
  full-page-width contract itself is unchanged.
- **S6-3 [FE] (J3)** Lines opens on "Lines identified" (today's "Show only these" filter, on by
  default while unconfirmed); "Show all lines (N)" is one click away.

  Owner hand test 25 Sep: renamed to "Need attention (N)" / "All lines (N)" -- "this should be
  Need attention and All lines, simple as that." Default-on-while-unconfirmed behaviour
  unchanged.
- **S6-4 [FE] (J3)** A line with an open finding carries a Flag cell and the row's own corrective
  action (edit the line, cancel it, or accept/reject the handwritten note); there is no separate
  Findings tab or card, and no Dismiss action on a PO line.

  Amended by reviewer judgment (a), 25 Sep 2026: at PO review time a line's mismatch is not a
  persisted `SODraftFinding` row - those are written only at SO draft time as HARD findings whose
  text says correct the line on the PO version. Correcting the line is the designed resolution and
  the grid already offers it. A Dismiss would need a new persisted field on `projects.po_lines`
  (migration + PATCH), contradicting "Backend seam: none", and the later hard finding would still
  stand unless the draft service learned to skip it (OOS-3). No seam is the smallest correct
  answer.

  Owner hand test 25 Sep: the handwritten-note cards that used to stay expanded under a flagged
  line ("Amend code / Page 1", "Amend description / Page 2", "Cancel line", plus "Skip to the
  next unreviewed line") read as "messy and bulky, like so many expanded sections." A line's
  notes are now one compact indicator in the Flag cell -- a note icon with the count, amber
  while unreviewed -- that opens a popover on click with the same accept/edit/reject actions in
  one line each, page included. Row height stays one line. The header's "Review them" link opens
  the first unreviewed line's popover directly rather than merely scrolling to it. The
  "Skip to the next unreviewed line" link inside the old card is gone; accepting or rejecting a
  note still auto-advances the reader to the next unreviewed line.
- **S6-5 [FE] (J3)** The Documents tab renders the PDF viewer, or, when it cannot be found, the
  S5-5 empty state (R13), with the rejected-note reasons (R7, `POIntakeAnnotationsGrid`) directly
  below it, both in the one tab, always present.

  Owner hand test 25 Sep: "why does this exist? just show me the entire document." The
  annotations grid (#, State, Reading, Note, Handwriting) is removed; the Documents tab shows
  only the PDF viewer, which now takes the tab's full height (was a short fixed-height strip) so
  every page is reachable by scrolling the viewer itself. The R13 empty state is unchanged.
  `POIntakeAnnotationsGrid` itself is trimmed to the `describeAnnotationEffect` helper the S6-4
  popover still uses; the grid component and its own test file are deleted as dead code.

  Assumption flagged for the owner to overrule: a note naming no line (a signature, "Continue To
  Next Page", delivery instructions) had its only surface in the grid just removed. With nowhere
  left to review it, it no longer blocks Confirm and is not counted in the header's unreviewed
  tally. A note naming a line still blocks Confirm exactly as before, through that line's S6-4
  indicator.
- **S6-6 [E2E] (J3)** HQ/26/01/121 v1 at 1280 and 375 matches the approved mockup.

  Owner hand test 25 Sep 2026 stands in place of this AC for this fix round: the owner's own
  screenshots on HQ/26/01/121 v2 named the four defects S6-2 through S6-5 amend above. A fresh
  E2E capture against the mockup is still owed once this round lands.

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

  Implementation notes, 26 Sep 2026 (S7 lane), applying the S6 owner lessons: a row's Flag is
  one compact pill (most severe open item, plus a count when there are several) that opens a
  popover with one entry per item, its source and its "Dismiss with a reason"; row height stays
  one line. Lines opens on "Need attention (N)" beside "All lines (N)"; every row holding a
  publish blocker is in Need attention. The count under Publish and the server's refusal share
  one rule, `publishBlockers` in `_shared/lib/findings.ts` (this order's hard findings with no
  `acknowledged_at`, the filter `blocking_findings` applies); a schedule-level finding is shown
  but never counted, because the server never lets it block. R23's pairing (an unmapped schedule
  column folded into the `schedule_short` finding for the product it names) is in
  `buildFlagItems`. Assumption flagged for the owner: the per-order allocation grid now shows only
  on a published order, so a draft's Lines tab is one table (R16).

  Open for the owner, R22 (PR #1264 review SF3): the mockup's lines table has 6 columns (#,
  Product, Qty, Value, Flag, Action); the shipped grid has 12 (#, Product, Flag, Description,
  Qty, UOM, Unit price, Amount, Delivery, Area, Source line, Stock location), and the Lines tab
  keeps the stock-location bulk-apply control. All of these predate S7 (they come from main),
  and the edit view mirrors the same 12 headers by rule, so the S7 lane kept them rather than
  cut working fields under R22 on its own call. Until the owner rules, R22 reads as unmet on
  these extras; a trim is its own slice (read and edit columns together).

  Review fixes, 26 Sep 2026 (PR #1264): a Flag pill, read and edit, leads with the most severe
  open item (`leadFlagItem`), never the first raised; "All lines (N)" counts finding-only rows
  too, so it equals the rows the view shows (lesson (c)); R23 pairs a product code with a
  schedule column only where the code starts one of the column's segments and is at least 3
  characters, the same floor the server's `_code_candidates` uses.

  Owner hand test, 26 Sep 2026 ~07:15Z on :3081 (PR #1264, five binding notes), applied:
  (1) the Lines table is one plain row per line in line order: no set heading row, no collapse,
  no indented companion; a zero-priced set part reads "Part of #N" in its price cell (the
  server's `parent_line_id`). Area, From PO line and Stock location leave BOTH the read and the
  edit view, which closes the SF3 question above for those three; the nine left are the
  editable fields plus #, Flag and Amount. (2) No Reorder lines toggle: every row carries its
  handle while the order may be reordered, and a drop saves at once. (3) No "Stock location for
  all lines" bar: the server derives the order's location from its customer's sales agent's
  location group (`BRW-<group>`, master site from `project_allocation_brw_warehouse_code`) and
  the header states it; a missing link is a "No stock location" flag naming it. (4) The project's
  Sales orders list keeps every row one line; To review is one pill in the Flag pill's words.
  (5) The three chips are gone; a footer row sums Value (labelled Page total past one page).
  Evidence: `evidence/pr1264-owner-notes/` (1280 and 375, cloud-lane stack seeded from the test
  builders, sidebar navigation, a real drag that saved).

## Out of scope (rulings)

- **OOS-1** Any active-company indicator on lists (R8).
- **OOS-2** A unified findings page, or moving findings off their entity (R3, R20).
- **OOS-3** Any change to extraction, reconciliation, drafting or the publish gate services.
- **OOS-4** a production check of the PDF viewer 404 is not owed (R22); the PO review page shows
  the plain not-found state (S6-5) and that is the whole requirement.
- **OOS-5** A cross-project pending list ("Needs attention"): dropped in full by R17, not
  deferred.
