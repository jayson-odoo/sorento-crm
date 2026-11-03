# SPEC-SHEET-V2 browser evidence (cloud sandbox, 3 Nov 2026)

Stack: sandbox Postgres DB `sorento_verify` (bootstrapped from the models, seeded by a scratch script: one
project, PRJQ-2026-0027 with the WC set / basin / traps case, PRJQ-2026-0030 with 30 product lines, two
published templates "Catalogue cover" and "Item with accessories" at 338.7 x 190.5 mm), backend :8000,
`next dev` :3000, RQ worker. Product photos point at a fake CDN host (`cdn.zzt.test`), so photo boxes are
empty in the screenshots; the URLs requested are the thumbnail ones.

## Steps 1-4 (agent-browser, sidebar navigation from `/`)

- `01-empty-state-1280.png`: Spec sheet tab, empty state "No spec sheets yet", one CTA "Create spec sheet".
- `02a-create-revision-options-1280.png`: Create dialog, Revision lists "Current draft" first, then the issued revision.
- `02b-create-dialog-filled-1280.png`: dialog filled (revision, cover, page template).
- `03-reader-opened-1280.png`: after Create the reader opens on SS1: cover then pages stacked.
- `04a-rail-jump-page4-1280.png`: rail click jumps to page 4; page N of M follows.
- `04b-zoomed-in-1280.png`, `04c-toolbar-under-header-1280.png`, `04d-scrolled-page2-1280.png`: zoom in, toolbar, scroll.

## Step 9: performance on a 31-page sheet (cover + 30 items), Playwright library script, not a committed spec

Measured at a4b97889 (after fix round 3) (backend restarted on that code; the first measurement ran against a
backend process started before round 3 and got 422 on every preview, which is why this was re-run).

| Action | spec-sheets API requests | Pages with a mounted renderer (of 31) |
|---|---|---|
| Open the reader | 2: `GET /{sheet}` + ONE `GET /{sheet}/preview?key=cover&key=...` (6 keys) | 3 |
| Scroll to page 16 | 1: one preview for that 6-page chunk | 5 (the window around page 16; the top pages unmounted) |
| Scroll back to the top | 0 (cached chunk) | |
| Idle 30 s, then window blur / focus / visibilitychange | 0 | |

- Images requested on open: `.../SRTBIG001/thumb.png`, `.../SRTBIG002/thumb.png` (thumbnails; no originals).
- No per-page request, no refetch on focus, no polling.
- `09a-30page-open-1280.png` (first measurement, shows the 422 toast from the stale backend), `09b-30page-middle-1280.png` (page 16 window rendered).

## Step 10: 375px

- 31-page reader at 375 x 800: `document.scrollingElement.scrollWidth` = 375 (no sideways scroll), 4 pages mounted. `10-30page-375.png`.

## Steps 5-8 (Playwright library script on PRJQ-2026-0027, after the fixes)

SS1 was created from issued revision A through the API (the dialog itself is shown in steps 2 and 6).

- **Step 6, PASS.** Create spec sheet with the dialog's defaults (`06a-create-dialog-defaults-1280.png`):
  - The Revision picker lists `Current draft / changed after A · not issued`, then `PRJQ-2026-0027-A / issued 03 Nov 2026`.
  - Create opens the reader on `SS2 · Draft after A`, sub line `lines taken 03 Nov 2026 15:01` (07:01 UTC shown in MYT), 6 pages (`06b-draft-sheet-reader-1280.png`).
  - It starts clean: 0 left out, 0 edited, AREA = the Section heading `UNIT`.
- **Step 5, FAIL then fixed.**
  - Edit page on the WC set page first opened "The page could not open / Page not found". The design call asked for `pages/set%253A.../design` because the key was encoded twice.
  - Fixed in the edit route (decode the segment once, with a red-first vitest).
  - After the fix the designer opens with `Changes apply to page 2 of SS1 only. The template and other spec sheets stay as they are.` (`05a-edit-page-designer-1280.png`).
  - Save page returns to the reader, and the API lists `SRTWCX6405` as edited (`05b-after-save-edited-badge-1280.png`).
- **Step 7, PASS up to Chromium.** Export PDF shows the toast `Preparing the spec sheet. It will appear in My Downloads.` (`07-export-toast-1280.png`).
  - The worker picked the job up and marked the download failed: `Executable doesn't exist at /opt/pw-browsers/chromium_headless_shell-1248/...`. This sandbox's Python Playwright expects a Chromium build that is not installed, the same limit #2103 recorded.
  - The print payload route for a sheet download is covered by `test_10_*` in `tests/test_project_spec_sheets_v2.py`.
- **Step 8, PASS.** List with SS1 and SS2 (`08a-list-two-sheets-1280.png`).
  - Row menu > Delete on SS2 turns into the toast countdown `Deleting in 9s / Cancel / SS2` (`08b-delete-countdown-1280.png`). No dialog.
  - After the window the list holds only SS1 (`08c-after-delete-1280.png`).
- No API request answered 4xx/5xx during steps 5-8 after the fix.

## F4: every page editable in place (Playwright library scripts, sandbox, 31-page SS1, 3 Nov evening)

Measured at ca7c241b. The cover's page edits were cleared first so each run starts from the template.

| Check | 1280 | 375 |
|---|---|---|
| Live designer canvases mounted | 3 | 3 |
| Sideways scroll (scrollWidth) | 1280 (none) | 375 (none) |
| Click a text layer | selected; inspector shows its fields and "Apply to: Every page" | selected; drawer does NOT open; "Properties" button appears |
| Drag the selected layer | x 26 -> 66, y 26 -> 45 | x 47 -> 87, y 32 -> 51 |
| Autosave after the drag | exactly 1 `PUT .../pages/cover/edit`, "Saved" | exactly 1 PUT, "Saved" |
| Inspector X 140 -> 160 | 1 PUT, "Saved" | |
| Undo | 1 PUT | |

The Tag Templates editor control drag (`/dealer-kit/tag-templates/<id>`) still moves its layer (X 8 -> 28).

Found and fixed during this pass:
- **Round 7d.** Live pages drew blank for layers stored without `visible`. The designer read a missing `visible` as hidden, while the PDF reads it as shown; the reader now normalises layers the way the PDF does.
- **Round 7e.** The hover action bar wrapped onto a second line and shifted every page about 60px, so a press missed its layer. The header is now one fixed line.
- **Round 7f.** On a phone, selecting auto-opened a drawer covering 650 of 812px, including the selected layer. The drawer now opens only from the "Properties" button, is compact (45dvh), and scrolls the layer above itself.

Screenshots: `f4-1280-*.png`, `f4-375-*.png`.

## Crew browser pass r6 fixes (head after 28b90671)

Measured in the cloud sandbox (next dev, Chromium via Playwright), sheet SS1 of PRJQ-2026-0030-A (31 pages).

| Item | Before | After |
|---|---|---|
| (a) Every page + Y box | "Something went wrong", React "Maximum update depth exceeded" in ScrollArea, 2 of 2 | No error 2 of 2; every item page stores the new Y |
| (b) Every page + drag | only the current page saved | one apply-all, no error |
| (c) AREA / COMMENT / marker | click opened a box, drag moved 0 px | click selects with handles, drag moved 30 px, double-click opens the Area box |
| (d) 375 Properties drawer | 80% of the screen, layer hidden | 45% (365 of 812 px); selected layer at y 68-109, drawer from y 447 |
| (e) Rail click | window scrolled ~180 px, last page read "3 of 4" | window scroll unchanged on click; last page reads "31 of 31" |
| (f) List at 1280 | table 1136 px in a 950 px card | table 950 px, no sideways scroll |

Regression: drag at 1280 and 375 still gives exactly 1 PUT and "Saved", no sideways scroll.

Root cause of (a): after an apply, the reader restarted every live canvas, the selected page's included. The new canvas
mounted with an empty selection and reported "nothing selected"; the host cleared its selection, the canvas re-selected
from the host's previous value, and the two ping-ponged. The canvas now starts from the host's selection and reports only
a selection the user made, and the reader restarts only the pages the server changed.

Reviewer round on f88747a6 (READY) follow-ups, re-measured after them: AREA single click selects with handles, a drag
moves 30-34 px, a double-click opens the Area box (2 of 2); Every page + Y box and Every page + drag: no error, one
apply-all. On a live page the AREA / COMMENT / marker buttons stay in the tab order with `pointer-events-none`, so Tab
+ Enter still opens the field from the keyboard.
