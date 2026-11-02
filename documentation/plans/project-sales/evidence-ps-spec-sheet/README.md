# PS-SPEC-SHEET browser evidence (cloud sandbox, 2 Nov 2026)

Stack: sandbox Postgres (throwaway DB, bootstrapped from the models), backend :8000, `next dev` :3000,
RQ worker. Seeded case (masked): one issued quotation with a WC product set (pan + angle valve +
hose), a basin, a bottle trap and a floor trap; two spec templates at 338.7 x 190.5 mm.

Walk (agent-browser, session `spec`): sign in, Project Sales > Projects (sidebar), the project,
Quotation tab, the quotation, Spec sheet tab (tab strip ends with Spec sheet). Picked the cover and
page templates (Export turned on), typed Area `unit & podium facilities` via the create row
(saved upper case), Marker `*`, picked the bottle trap under the basin (its row left the list,
pages renumbered), switched Print off on the floor trap ("Off"), paged the Preview (Page 1-3 of 3).

- `01-tab-cover-preview-1280.png`: the tab at 1280px with the cover in the preview.
- `02-wc-page-with-accessories.png`: WC page, two accessory rows, title block (ref, area, prepared by, date).
- `03-basin-page-picked-accessory.png`: basin page, hand-picked bottle trap as accessory 1, accessory 2 row hidden (`show_when`).
- `04-tab-375.png`: 375px, no horizontal scroll (document scrollWidth 360).
- `spec-sheet-sample.pdf` / `05-pdf-page-2.png`: the print page rendered to PDF at the template size: 3 pages, 338.7 x 190.5 mm, no price text.

Notes:
- The sandbox's Python Playwright expects a different Chromium build than the one installed, so the
  worker's render step failed there (`Executable doesn't exist ... chromium_headless_shell-1248`) and
  marked the download failed as designed; the PDF above was rendered from the same print URL and page
  size with the preinstalled Node Playwright. The worker path up to Chromium (download row, queue,
  page size) ran.
- Sidebar navigation needed the throwaway DB's tenant modules and Super Admin permissions seeded;
  the first screenshots before the brand/product company fix showed blank brands because the seed
  rows had no company (real rows always do).

## Canvas flow (mock v5, 3 Nov)

- `06-v5-wc-page.png`: the tab with no table: pickers, the page strip (cover, items, a left-out page
  greyed with "-"), the open page with Leave out / Add accessory.
- `07-v5-area-typed.png`: the AREA spot clicked on the open page; it started as the Section heading
  `UNIT` (stored area empty), typed `unit & podium facilities`, Enter: saved as
  `UNIT & PODIUM FACILITIES` (DB row checked) and the page re-rendered with it.
- Put back on the left-out page: the thumbnail got its number back (`4 SRTFT...`).
- Not verified in this browser: drag in the strip. A keyboard attempt did nothing because the handle
  was not focusable (fixed in 95f990d82f with `tabIndex={0}`), and the dev server then hit the
  sandbox's background time limit. Crew's browser pass should drag one thumbnail.

## Strip drag fix (crew browser pass step 14, 3 Nov)

Crew's pass at 5fc832fe4f: dragging a page in the strip did nothing (mouse or keyboard). Cause: the
pages were wrapped in a `<div>` inside the shared `Sortable`, whose `DragOverlay` clones the dragged
item from its DIRECT children; the overlay was empty (zero size), and dnd-kit measures collisions
with the overlay, so no page was ever "over". Fix: the pages are direct children, the flex layout
moves to `Sortable`'s `className`.

`dnd/harness.tsx` renders the shared `Sortable` twice, once wrapped (old) and once direct (new);
`dnd/drive.js` builds it with Vite and drags both in real Chromium (Playwright library, run as a
script, not a committed spec, per the standing order). Result:

    old mouse -> wc,basin,trap | keyboard -> wc,basin,trap      (nothing moves)
    new mouse -> basin,wc,trap | keyboard -> basin,trap,wc      (both reorder)
    page errors: none

The tab test `QuotationSpecSheetTab.dnd.test.tsx` (real `Sortable`) pins the structure: it fails
on the old tab and passes on the fix.

## Sandbox browser pass on steps 3 and 14 at 07c5618bca (3 Nov)

- `08-step3-insert-field-1280.png`, `09-step3-insert-field-375.png`: Tag Templates > the spec page
  template > a text layer > Insert field: a "SPEC SHEET" group; search "Project title" finds
  `{{doc.project_title}}`. No sideways scroll at 375.
- `10-step14-reordered-1280.png`, `11-step14-375.png`: the page strip after reordering. At both widths
  a real mouse drag (agent-browser `drag`, basin onto WC) gave `2 basin, 3 WC`, and the keyboard
  (Space, ArrowLeft, Space on the WC handle) moved it back; each order survived a reload and was
  stored in the document's rows.
