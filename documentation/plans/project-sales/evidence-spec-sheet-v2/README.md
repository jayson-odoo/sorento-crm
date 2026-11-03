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
