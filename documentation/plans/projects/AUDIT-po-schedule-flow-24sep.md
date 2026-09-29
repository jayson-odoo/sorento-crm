# Screenshot audit: Project Sales PO upload and delivery schedule flows

Status: audit only, no redesign. 24 Sep 2026.

Scope: issue #1167. Read-only walk of the real PO upload and delivery schedule upload flows
against a prod-copy database (`sorento_ai_automation_0923`), on the one project in that database
that carries both a PO and a delivery schedule: PRJ-000001 "Setia Alam" (company "Sorento").
Evidence under `documentation/plans/projects/evidence/po-schedule-audit-24sep/`, all screenshots
under 400 KB, captured at 1280 wide then 375 wide. No file was uploaded, no dialog was confirmed,
nothing was approved or countersigned.

A company-switcher gotcha came up before any of this could be captured: the signed-in test user's
active company defaulted to "Mocha," a second company row in this database with no projects, and
the whole company-scoped listing (`do_orm_execute` predicate in `app/services/company_scope.py`)
silently returned zero rows for every query -- read as "no projects registered" rather than a
wrong-company selection. Switching the header company picker to "Sorento" (the project's actual
`company_id`) surfaced the data. Noted here because a first-time user hitting the same empty state
would have no way to know a company switch was the fix.

## Path walked (click by click, from `/`)

All counts start at the Dashboards home page after login.

1. **To the PO upload dialog:** expand "Project Sales" in the sidebar (1) -> click "Pipeline" (2)
   -> click the "Setia Alam" project row (3) -> click the "POs" tab (4) -> click "Upload a PO
   document" (5). **5 clicks, and the button only exists after already being three levels into a
   project.** There is no PO-upload entry point anywhere in the sidebar itself (step captured
   `01-sidebar-project-sales-*.png`: Pipeline, Leads, Awaiting Acceptance, My Tasks, Stock Claims,
   AutoCount Differences, Parties, Configuration -- no "Purchase orders" or "Upload" item).
2. **To the delivery schedule upload dialog:** same first three clicks, then click the "Delivery
   schedules" tab (4) -> click "Upload a schedule" (5). Also 5 clicks, also only reachable from
   inside a specific project.
3. **To the PO version confirm/extraction page:** the same three clicks into the project (3),
   then the "POs" tab (4), click the PO row "HQ/26/01/121" (5), then click "Open" under the
   Documents heading on the PO detail page (6). **6 clicks and two intermediate pages** (project ->
   PO detail -> PO version) to see the confirmed extraction.
4. **To the delivery schedule review page:** three clicks into the project (3), "Delivery
   schedules" tab (4), then "Open" against the version row (5). **5 clicks**, one fewer than the PO
   path because the schedules tab shows the version list directly rather than routing through an
   intermediate schedule-summary page.
5. **To a sales order's findings:** three clicks into the project (3), "Sales orders" tab (4),
   click a PSO row (5). **5 clicks.**
6. **To AutoCount Differences:** expand "Project Sales" (1), click "AutoCount Differences" (2).
   **2 clicks** -- the one screen in this whole area that IS a direct sidebar entry, because it is
   project-agnostic (a company-wide list), not nested under a project.

Every other screen (PO detail, PO version, delivery schedule review, SO detail) is reached only by
clicking into a specific project first. None of them has a URL a user could navigate to on their
own without already knowing the project.

## Screens

Each line: what the screen shows, what a first-time user would not understand on sight, evidence.

1. **Sidebar, Project Sales expanded** -- eight items (Pipeline, Leads, Awaiting Acceptance, My
   Tasks, Stock Claims, AutoCount Differences, Parties, Configuration). Nothing here says "upload a
   PO" or "upload a schedule" exists; a user has to already know to open a project first.
   `01-sidebar-project-sales-1280.png` / `-375.png`.
2. **Pipeline grid** -- one row for Setia Alam: Code, Project, Developer, Stage ("PO Received"),
   Outcome ("Open"), Estimated, Brands, Owner, Next action ("Nothing open"), Last activity. "PO
   Received" as a pipeline *stage* name reads like a status the system tracks automatically; it is
   actually just wherever someone last dragged/set the project, unrelated to whether a PO
   extraction was confirmed. `02-pipeline-grid-1280.png` / `-375.png`.
3. **Project overview tab** -- "The development," "Value and timing," "Consultants," "Critical /
   final negotiation," "Where this came from," "Access." Functions as the project's front page but
   carries none of the PO/schedule state; a user has to already know which of the eleven tabs holds
   what they want. `03-project-overview-1280.png` / `-375.png`.
4. **POs tab** -- one row, "HQ/26/01/121," with Source ("Contractor direct"), Value, Issued by,
   Dated, Against, "To check" (50 not quoted), "Drift from v1." "To check" and "Drift from v1" are
   both new vocabulary with no inline explanation of what "not quoted" or "drift" means here.
   `04-project-pos-tab-1280.png` / `-375.png`.
5. **"Upload a customer PO" dialog** -- dropzone plus an optional "PO number" field ("Leave blank
   and the extraction fills it"). No mention anywhere in the dialog of what happens next (that it
   queues an extraction job, lands on a confirm screen, needs a human to approve, etc.).
   `05-upload-po-dialog-1280.png` / `-375.png`.
6. **Delivery schedules tab** -- one schedule row for "HQ/26/01/121" with its two versions (v2,
   v1) shown inline: Version, Revision, Issued by, Dated, Reconciliation ("35 of 44 columns
   reconciled" / "37 of 44"), Confirmed date. "Reconciliation" as a fraction is presented before a
   user has seen what a "column" is (that only becomes clear on the review page itself).
   `06-project-schedules-tab-1280.png` / `-375.png`.
7. **"Upload a delivery schedule" dialog** -- Purchase order (pre-filled from context), "Revision
   of" ("A schedule we have not seen before" as the default/placeholder), "Issued by" ("The company
   whose letterhead it carries"), Revision label, dropzone. Four fields before a file is even
   picked; "Revision of" and "Issued by" are both concepts a first-time uploader has not met yet.
   `07-upload-schedule-dialog-1280.png` / `-375.png`.
8. **PO detail page (`pos/[poId]`)** -- header (PO number, "Why this is the next step," "Build the
   sales orders" link), a "Documents" section with a single "Open" link (this is the "strip" the
   code map describes; with only one version uploaded it renders as one link, not a visible
   multi-version strip), then a 52-line "Lines" grid (Our product, Code on the PO, Description,
   Qty, UOM, Ordered at, Total). `08-po-detail-top-1280.png` / `-375.png`,
   `08b-po-detail-lines-1280.png` / `-375.png`.
9. **PO version confirm/extraction page (`purchase-orders/[versionId]`)** -- version badge "v1" +
   status "Confirmed," a banner ("Our sum is RM 4,733.60 below the document total, which is the 1
   cancelled line"), "Confirmed / Approved / Countersigned" status row (Approved: "Not yet",
   Countersigned: "Not yet" -- two more states beyond Confirmed, neither explained), a left-hand
   PDF viewer, and a right-hand Header + Lines panel. Six "Document notes" cards further down, each
   showing a State ("Rejected"), Reading ("A signature" / "Something else") and Note. **Defect:**
   the embedded PDF viewer shows "Error 404 / Object not found" instead of the source document --
   the uploaded file is not reachable from this environment even though the version is marked
   Confirmed, so a reviewer checking the extraction against the original has nothing to check it
   against. Every one of the six annotation cards is marked "Rejected" with no visible reason why,
   which reads as the extraction having failed six times over, though "No line changes" on each
   suggests "Rejected" here means something closer to "not actioned." `09-po-version-top-1280.png`
   / `-375.png`, `09b-po-version-header-lines-1280.png` / `-375.png`,
   `09c-po-version-annotations-1280.png` / `-375.png`.
10. **Delivery schedule review page, top (`delivery-schedules/[versionId]`)** -- "Version 2 · 1 -
    23/7/2026 · Dated 04/03/2026 · Checked against PO version 1 · Read in 1m 46s," a green
    "Confirmed 19/08/2026, 3:16 pm" banner, "Notes on the document," and a "Re-dating proposals"
    card listing twelve phase/date pairs with an "Accepted" pill. Five distinct concepts (schedule
    version, PO version being checked against, notes, re-dating proposal, accepted state) stacked
    in the first screen, before reconciliation is even reached. `10-dsv-top-summary-1280.png` /
    `-375.png`.
11. **Reconciliation section** -- "35 of 44 columns reconciled," "This schedule is confirmed, so
    nothing here can be changed. What follows is what did not agree with the PO at the time it was
    confirmed," then a 9-row table (Code, Status, Schedule qty, Reported total, PO qty, Problem)
    with Blocked/Warning pills. Codes are shown as the customer's own column header
    (`BUI-HB-SRTWC8608-RL...`), truncated in the 1280 layout; no glossary for what "BUI-HB" means
    as a prefix. `11-dsv-reconciliation-1280.png` / `-375.png`.
12. **Matrix (By date view)** -- a wide product-by-date grid with per-cell quantities, row pills
    "Reconciled" / "Not identified · 2 to fix." At 1280 this is a horizontally-scrolling table; at
    375 it re-flows into stacked cards per product with "Our total / Schedule / PO" sub-rows --
    the one section in this whole flow that visibly adapted for the narrow viewport rather than
    just shrinking. `12-dsv-matrix-1280.png` / `-375.png`.
13. **"Changes since the previous version" (was/now revision diff)** -- "0 phases moved · 20
    quantities changed · 222 unchanged," then cards per phase showing `qty: <old, struck through>
    -> <new>`. Clear once read, but the heading gives no indication in advance of how many cards
    follow or that they are grouped by phase. `13-dsv-revision-diff-1280.png` / `-375.png`.
14. **Column card (via "Go to X in the schedule")** -- clicking a reconciliation row's "Go to"
    button switches the matrix to "By date" and highlights the matching row in red with a "2 to
    fix" pill; it does not open a separate dialog or card as the code map's phrase "column card"
    implied going in -- the reconciliation list row and the highlighted matrix row together are the
    "card." `14-dsv-column-card-1280.png` / `-375.png`.
15. **Sales order detail, Blocking** -- "PSO-000003 Blocked," (2030-01-01) · Split by hand ·
    Customer PO HQ/26/01/121," a summary panel (Area group, Billed to, Lines, Value, Sum of the
    lines, Drafted, Published "Not published yet," AutoCount document "Not adopted yet," Reference
    we raised), then "Publishing is refused: 17 findings must be fixed or overridden," then a
    "Blocking" card listing all 17 with "Show line N" and "Override with a reason" per finding.
    "Area group," "Split by hand," and "Reference we raised" are all new terms introduced here for
    the first time. `15-so-blocking-1280.png` / `-375.png`.
16. **Warnings** -- same pattern, "Clear with a reason" instead of "Override with a reason" (two
    different verbs for what reads as the same action: dismissing a finding).
    `16-so-warnings-1280.png` / `-375.png`.
17. **For information / Schedule-PO findings** -- "For information: Nothing else to note" (empty
    state) directly above "Schedule / PO findings · 16 on this purchase order," a *third* findings
    list distinct from Blocking/Warnings/Info, each row naming a schedule column by its raw
    customer code ("The schedule column 'BUI-HB-CB1178ASS' carries 259 against 'Level 2 & 7' but is
    not mapped to a product") with its own "Clear with a reason" button. Nothing on the page
    explains why this is a separate list from the Blocking findings above it, though several of
    those blocking findings are almost the same statement in different words.
    `17-so-info-findings-1280.png` / `-375.png`.
18. **AutoCount Differences (top level)** -- "AutoCount agrees with every published sales order" /
    "Open the pipeline" link. Empty state, expected: this database has zero rows in
    `so_divergences` because no sales order under Setia Alam has been published yet (all three are
    still Blocked). Captured as evidence of the empty state, not as a data gap in the audit itself.
    `18-autocount-differences-empty-1280.png` / `-375.png`.

## Vocabulary met (term -> screen it first appears on)

- PO version, "Confirmed / Approved / Countersigned" -- screen 9 (PO version page).
- "Drift from v1," "To check," "not quoted" -- screen 4 (POs tab).
- Schedule version, "Revision of," "Issued by" -- screen 7 (upload schedule dialog).
- "Columns reconciled" (as a fraction) -- screen 6 (schedules tab), before "column" is defined.
- Blocked / Warning (reconciliation status) -- screen 11.
- "Re-dating proposal," Accepted -- screen 10.
- Phase, area group -- screens 10 and 15 respectively (two different partitioning concepts,
  introduced on two different pages, never tied together on either).
- "Split by schedule area" / "Split by hand" -- screen 15 (sales orders list, seen briefly before
  the detail page; not explained on either).
- Finding, Blocking / Warning / For information, "Override with a reason" / "Clear with a reason"
  -- screen 15/16/17.
- "Schedule / PO findings" (the third findings surface) -- screen 17.
- Divergence -- never reached in this walk (no published SO in this data); only named on the
  sidebar entry "AutoCount Differences" itself (screen 18), which uses "differences," not
  "divergence" -- two names for the same concept depending on which screen you are on.
- Order Change Notice, amendment -- never reached; no entry point found from this project's PO or
  schedule screens in this walk.

That is at least fourteen distinct terms across nine screens before a project ever reaches a
published, AutoCount-adopted sales order.

## Friction list

1. No sidebar entry reaches PO upload or schedule upload. Both are five clicks deep, reachable
   only after already being inside a specific project (`01-sidebar-project-sales-1280.png`,
   Path walked #1-2).
2. Company scoping is silent. The signed-in user's active company defaulted to "Mocha," and the
   entire Pipeline grid read as "No projects registered yet" -- indistinguishable from a genuinely
   empty pipeline. No banner or indicator on the Pipeline page names which company is currently
   active as the reason for an empty list.
3. The PO version's embedded PDF viewer shows "Error 404 / Object not found" on a version marked
   Confirmed (`09-po-version-top-1280.png`). A reviewer re-checking a confirmed extraction against
   the source document cannot see the source document.
4. All six "Document notes" annotation cards read "Rejected," with no visible reason and no visual
   distinction between "the system rejected this" and "nobody has actioned it yet"
   (`09c-po-version-annotations-1280.png`).
5. Findings are split across three visually separate cards on the SO page -- Blocking, Warnings,
   and "Schedule / PO findings" -- with two different dismiss verbs ("Override with a reason" vs.
   "Clear with a reason") for what reads as the same action, and no text anywhere explaining why a
   given finding lands in one card rather than another (`15-so-blocking-1280.png` through
   `17-so-info-findings-1280.png`).
6. "Phase" (delivery schedule review) and "area group" (sales order) both partition the same
   underlying delivery data but are never connected to each other on any screen in this walk
   (`10-dsv-top-summary-1280.png` vs. `15-so-blocking-1280.png`).
7. The sidebar's own label ("AutoCount Differences") does not match the vocabulary used elsewhere
   for the same concept ("divergence" in the code map, PO/SO field names, and route
   `/project-sales/divergences`) (`18-autocount-differences-empty-1280.png`).
8. The PO's "Documents" section renders as a single "Open" link rather than a visible strip when
   there is only one version, so the multi-version affordance described in the code map is not
   discoverable from this project's data alone (`08-po-detail-top-1280.png`).
9. Column codes throughout the reconciliation table and matrix are shown as the customer's raw
   column header (e.g. `BUI-HB-SRTWC8608-RL`), truncated at 1280 width with no visible way to see
   the full string without opening the row (`11-dsv-reconciliation-1280.png`).

## Clipping or breakage at 375

- The matrix (screen 12) is the one section that visibly adapted: it drops the wide table for
  stacked per-product cards. Everything else at 375 is the same layout narrowed, not restructured.
- The PO Lines grid (`08b-po-detail-lines-375.png`) shows only 3 of 7 columns (#, Code on the PO,
  a cut-off "Description") with no visible scroll affordance in the frame; a 51-line, 7-column
  grid on a phone is reachable only by horizontal scroll the screenshot does not show is available.
- No other clipping or overlap observed at 375 across the sidebar, dialogs, PO version page, or SO
  detail page -- text reflows and dialogs stayed within the viewport in every other capture.

## Open questions for the owner

1. Should Pipeline (and every company-scoped list) show which company is active, or warn on an
   empty result while a non-default company is selected, given how easily "wrong company" reads as
   "no data"?
2. Is the PDF-viewer 404 on the confirmed PO version a storage-migration artifact specific to this
   prod copy, or does it also happen in production?
3. What is the intended relationship between "phase" (schedule) and "area group" (sales order) --
   are they meant to be the same grouping under two names, or genuinely different?
4. Is "AutoCount Differences" vs. "divergence" an intentional simplification for the sidebar label,
   or should one of the two names change?
5. What distinguishes a Blocking finding from a "Schedule / PO findings" finding, given several
   read as restating the same problem?
6. Was reaching zero Order Change Notices / amendments / divergence screens in this walk because
   this project's data never produced one, or because there genuinely is no entry point for them
   from the PO/schedule side of a project that has not published a sales order yet?
