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
