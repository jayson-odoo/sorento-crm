# UAC - Unified Drive for Resource Management → Files

Acceptance criteria for `PLAN-unified-drive-files.md`. Every item is testable. The
**tester** must mark each PASS/FAIL with evidence (pytest name, vitest name, Playwright
step, or screenshot) before a phase returns to the orchestrator. No phase advances with a
FAIL.

Legend - **Gate**: which phase validates it. BE = backend pytest, FE = vitest, E2E = Playwright, MAN = final manual (user).

---

## A. Navigation & layout

| ID | Criterion | Gate |
|----|-----------|------|
| A1 | Left folder tree still renders, nested, and selecting a node drives the right pane to that folder. | FE, E2E |
| A2 | Right pane shows a **breadcrumb** of the current path (root → … → current). Clicking a crumb navigates there. | FE, E2E |
| A3 | Folders and files appear in the **same** right-pane collection (list view) - not separate panes. | FE, E2E |
| A4 | A **grid/card** view toggle exists; switching shows the same folders+files as cards. | FE, E2E |
| A5 | View mode (list/grid) persists across reloads, per user (localStorage). | FE |
| A6 | Single click on a folder (row or card) drills into it (right pane + breadcrumb update). | FE, E2E |
| A7 | Single click on a file opens its preview (image/PDF inline per existing behavior; others as today). | FE, E2E |
| A8 | Drive **root** shows top-level folders + files with `directory_id IS NULL` only - NOT a flat dump of all files. | BE, E2E |

## B. Search (the core fix)

| ID | Criterion | Gate |
|----|-----------|------|
| B1 | With empty query, the pane shows **immediate children only** (non-recursive browse). | BE, FE |
| B2 | Typing a query searches the current folder **+ all descendant subfolders** (recursive). A file in a sub-subfolder is found without manually drilling. | BE, E2E |
| B3 | Searching at root searches the **whole drive**. | BE |
| B4 | Recursive results include **both** matching files and matching folders. | BE, FE |
| B5 | Each search result shows a **Location/path** column (hidden during plain browse). | FE, E2E |
| B6 | "Reveal in folder" action on a file result navigates to that file's parent folder and clears the search. | FE, E2E |
| B7 | Drilling into a folder **clears** the active search query. | FE |
| B8 | Optional "this folder only" toggle narrows a search to non-recursive. (If shipped - else mark N/A.) | FE |

## C. Sort / filter / export

| ID | Criterion | Gate |
|----|-----------|------|
| C1 | Default sort = Name, **interleaving folders and files** alphabetically as one list. | BE, FE |
| C2 | Sorting by Size/Type/Modified/uploader pushes folders to the **end** of the list. | BE, FE |
| C3 | Any active file-attribute filter (Type/Access/Link status/Uploader/date) or a non-empty search **hides folders**. | BE, FE |
| C4 | Plain browse (no filter, no query) **shows folders**. | BE, FE |
| C5 | Export (xlsx) includes **files only** - folders never appear in the export. | BE |
| C6 | Sort + pagination are correct across the **UNION** (folder+file) result at any folder size; no duplicate/missing rows across pages. | BE |

## D. Data / backend contract

| ID | Criterion | Gate |
|----|-----------|------|
| D1 | New unified endpoint returns discriminated rows (folder vs file) with server sort + server pagination. | BE |
| D2 | File rows carry their `directory_path`; path is resolved in the query (no N+1). | BE |
| D3 | Recursive uses the existing descendant CTE; non-recursive uses exact `directory_id` match. | BE |
| D4 | Every query is **tenant-scoped**; a second tenant's folders/files never appear. | BE |
| D5 | All pre-existing attachment endpoints/features still respond unchanged (regression). | BE |

## E. Move (drag + dialog)

| ID | Criterion | Gate |
|----|-----------|------|
| E1 | Drag a file onto a folder row/card in the right pane moves it into that folder. | E2E |
| E2 | Drag a file/folder onto a breadcrumb crumb moves it there. | E2E |
| E3 | Drag onto the left tree still works (regression). | E2E |
| E4 | Moving a folder into its own descendant is **blocked** (cycle guard) with a clear error. | BE, E2E |
| E5 | A "Move to…" folder-picker dialog performs the same move (universal non-drag path). | FE, E2E |

## F. Selection & bulk "Action" menu

| ID | Criterion | Gate |
|----|-----------|------|
| F1 | Checkboxes allow multi-select of folders and files **together** (mixed). | FE, E2E |
| F2 | All bulk actions live under **one "Action" dropdown** (not separate toolbar buttons): Export, Set access levels, Set attachment type, Resubmit selected, Delete selected, Move. | FE, E2E |
| F3 | On a selection containing a folder, file-only actions (Export, access levels, attachment type, Resubmit) are **disabled/hidden**; shared actions (Move, Delete) stay enabled. | FE, E2E |
| F4 | Bulk **Delete** on a folder cascades soft-delete to its subtree; restore brings it back. | BE, E2E |
| ~~F5~~ | ~~Bulk Download as ZIP~~ - **DROPPED from scope** (no endpoint/task in sorento, not requested). | - |
| F6 | Single-only actions (Rename, Replace) are hidden when selection is multi. | FE |

## G. Card view thumbnails

| ID | Criterion | Gate |
|----|-----------|------|
| G1 | In grid view, `image/*` files show the real image, lazy-loaded (`loading="lazy"` + IntersectionObserver), via the CSP-sandbox serve route. | FE, E2E |
| G2 | Non-image files and folders show a type/folder icon (no broken image). | FE |
| G3 | Off-screen image cards do not fetch bytes until scrolled into view. | FE |

## H. Mobile (≤375px)

| ID | Criterion | Gate |
|----|-----------|------|
| H1 | Left tree collapses to a toggle **drawer**; right pane is full-width. | FE, E2E |
| H2 | Breadcrumb is the primary nav; single-tap opens; long-press opens context menu. | FE |
| H3 | Move uses the "Move to…" dialog (drag disabled on touch). | FE |
| H4 | Grid reflows to 2 columns; no horizontal page overflow at 375px. | FE, E2E |

## I. Preservation (no regression to existing features)

| ID | Criterion | Gate |
|----|-----------|------|
| I1 | Access-levels set/view still works. | BE, E2E |
| I2 | Polymorphic entity-linkages still work. | BE |
| I3 | Attachment-types CRUD + per-type rules still work. | BE |
| I4 | Bulk-import-ZIP still works. | BE |
| I5 | Upload-activity drawer + My-Downloads drawer still work. | E2E |
| I6 | Replace / resubmit (new version append) still works. | BE |
| I7 | Column preferences (`listing_key`) persist for the file columns. | FE |
| I8 | Same-name upload collision → Replace / Keep-both still works. | BE, E2E |

## J. Quality gates

| ID | Criterion | Gate |
|----|-----------|------|
| J1 | `npm run lint` clean; type-check clean. | FE |
| J2 | All new pytest green; full BE suite green (no regressions). | BE |
| J3 | All new vitest green; full FE vitest green. | FE |
| J4 | `e2e/documents-drive.spec.ts` green against real stack. | E2E |
| J5 | `/code-review` findings addressed (or consciously waived with reason). | review |
| J6 | Test Execution Report written: `PLAN-unified-drive-files-test-report.md`. | review |
