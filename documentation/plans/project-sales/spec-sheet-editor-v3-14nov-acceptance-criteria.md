# UAC: spec sheet editor v3 (owner hand-test fix round on PR #2349)

Lane SPEC-SHEET-PARITY-B2. Mock: `documentation/mockups/SPEC-SHEET-PARITY-B2/index.html` (v2/v3,
approved by the owner 14 Nov 13:56: Q1 (a) plus "if i click delete in my keyboard also should be
able to work just like google slides", Q2-Q5 (a), "ok all good"; Q6-Q8 taken as the recommended (a)).
Builds on `spec-sheet-designer-parity-b-11nov-acceptance-criteria.md` (B1-B7). One designer: every
table / toolbar change lives in the shared code (`CanvasToolbar`, `TagCanvasEditor`,
`KonvaTagLayer`, `InspectorPanel`, `InsertFieldDialog`, `lib/dealer-kit/table-layout.ts`, print
`TagSheetRenderer`, `spec_sheet_pptx`) and works the same in the tag template designer.

Paths: `SS/` = `app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/spec-sheet/[sheetId]/components/`,
`TT/` = `app/(protected)/dealer-kit/tag-templates/components/`.

## C1 One toolbar row (spec sheet)
- AC-C1.1: the spec sheet shows ONE toolbar row (the shared `CanvasToolbar`): add tools (Text,
  Shape, Image, Badge, Table, Accessories), Undo, Redo, More, Zoom out, zoom %, Zoom in, Fit width,
  Full screen, and the save state. The separate page bar row (`SS/SpecSheetReader.tsx` page bar)
  is gone.
- AC-C1.2: no page counter ("1 of 2") and no previous/next page buttons in the toolbar.
- AC-C1.3: Delete, Duplicate, Group, Ungroup are in the toolbar's "More" menu (and right-click),
  not visible icons, on the spec sheet.
- AC-C1.4: with a text layer selected, its format controls (font, size, bold, italic, align, ALL
  CAPS) show in the same row; with a table selected, the table actions show there instead
  (+ Row, + Column, Merge, Header row, Insert field); with nothing selected neither shows.
- AC-C1.5: at 375 px every tool is reachable (the row scrolls sideways or folds into More); the
  page has no horizontal overflow.

## C2 Pages side bar: navigation, Remove page, Removed pages
- AC-C2.1: page navigation is the left Pages side bar (`SS/PageRail.tsx`): clicking a thumbnail
  scrolls to that page; under the thumbnails it reads "Page N of M" for the current page.
- AC-C2.2: every non-cover thumbnail (auto-made accessory pages included) has a "..." menu and a
  right-click menu with "Remove page". Choosing it sets the page's existing left-out flag (the same
  save the old "Leave out" button made); the page leaves the thumbnail list and the page stack and
  does not print or export.
- AC-C2.3: removed pages are listed at the bottom of the side bar under "Removed pages (N)", each
  with "Put back", which clears the flag and returns the page to its place.
- AC-C2.4: the "Leave out" / "Put back" button above each page is gone.
- AC-C2.5: on a phone the page strip offers the same Remove page (long-press / "..." menu) and the
  Removed pages list.

## C3 Table cells: text + field chips, edited on the page
- AC-C3.1: clicking a table cell selects that cell (outlined); double-clicking it, or typing while a
  cell is selected, opens the in-place editor over that cell (the same rich editor text layers use,
  `TT/InlineTextEditor.tsx`), with `{{fields}}` shown as chips.
- AC-C3.2: the Insert field button (toolbar and right-click) or typing `{` in the cell editor opens
  `InsertFieldDialog`; picking a field inserts its token AT THE CURSOR (not at the start), and the
  chip shows its readable name.
- AC-C3.3: Enter / clicking away saves the cell text; Escape cancels; the edit is one Undo step.
- AC-C3.4: the Inspector's "Cell row" / "Cell column" number boxes and the raw "Content" box are
  gone; the Cell section keeps border (side + colour + width), fill, padding, and adds Row height
  and Column width for the selected cell's row / column.
- AC-C3.5: right-click on a cell offers: Insert field, Insert row above, Insert row below, Insert
  column left, Insert column right, Delete row, Delete column, Merge right, Merge down, Unmerge
  cells, Header row (checked when on).
- AC-C3.6: on the spec sheet, a cell shows chips only while it is being edited; otherwise it shows
  the resolved value (as printed). In the template designer it shows the preview product's value
  when one is picked, else the chip names.
- AC-C3.7: the same C3 behaviour works in the tag template designer (one shared component, no
  fork).

## C4 Header row
- AC-C4.1: the table has a "Header row" on/off (toolbar, right-click). On: row 1 prints bold with a
  light shade (`#f1f5ee`-like, the table's own fill wins when set) on canvas, print and PowerPoint.
- AC-C4.2: the flag is a new optional table prop accepted by every save path (schemas forbid
  unknown props) and absent on old tables (= off).

## C5 Row height, column width, ALL CAPS (the right-edge title block)
- AC-C5.1: a row's height is a minimum that is kept when its cells are empty (e.g. a tall blank
  COMMENT row) and grows only when the text needs more; set from the Inspector (Row height, mm) and
  by dragging a row's bottom edge on the canvas; column width likewise (Column width, edge drag).
- AC-C5.2: an "ALL CAPS" switch on a table (and on a text layer) prints its text in capitals on
  canvas, print and PowerPoint without changing the stored text or field values. New optional
  prop, accepted by every save path; absent = off.
- AC-C5.3: the owner's title block can be built and prints as in mock section I: one column, 7
  rows, green 0.2 mm borders, row 1 = Subject title chip, then "REF : " + Ref, "AREA : " + Area,
  "PREPARED BY : " + Prepared by + Prepared by phone, "DATE : " + Date (dd/mm/yyyy), "COMMENT :",
  and a tall empty row.

## C6 Manage fonts on the spec sheet
- AC-C6.1: the spec sheet Inspector's Font Family (and the text format font list in the toolbar)
  offers "Manage fonts", opening the template designer's `TT/FontUploadDialog.tsx`; an uploaded
  font is selectable at once on the spec sheet and in the template designer (one kit library).
- AC-C6.2: same permission as the template designer's font upload; without it, no "Manage fonts".

## C7 Keyboard Delete
- AC-C7.1: on the spec sheet, with one or more elements selected on a page, Delete or Backspace
  removes them (one Undo restores them), like Google Slides; same in the template designer.
- AC-C7.2: not while typing: in a cell editor, a text editor, the Inspector or any input, Delete /
  Backspace edit the text only.

## C8 Picture that cannot load
- AC-C8.1: an image whose download fails shows "Image not available" (grey box); a picture still
  loading shows "Fetching image"; a loaded one draws. Same in both designers.

## Carried from the held round (cf1d25aa)
- AC-H.1: designer Accessories box with no previewed accessories shows full sample cards (picture,
  BRAND CODE, description) outside Edit card.
- AC-H.2: a PowerPoint export whose builder cannot load ends Failed with a plain reason.

## Standing rules that apply
UI-minimal (extra controls in menus), plain words, dd/mm/yyyy, one main button, no UUIDs, deferred
action rule (Remove page is a reversible flag with Put back, not a delete; no confirm dialog),
reuse functions (list reused file:line in crew-done), 375 + 1280.
