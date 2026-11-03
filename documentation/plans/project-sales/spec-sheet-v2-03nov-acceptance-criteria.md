# UAC: SPEC-SHEET-V2 (saved spec sheets, PDF-style reader, per-page designer edit)

**Status:** Draft against mock v2 (owner answers 3 Nov: Q1 draft allowed, Q2 a, Q3 a, Q4 b clean, Q5 a).
Card: `CARD-spec-sheet-v2-03nov.md`. Mock: `documentation/mockups/SPEC-SHEET-V2/index.html`.

## List (tab)

- AC-L1 The Spec sheet tab shows a DataGrid of this quotation's spec sheets, newest first, with No. (`SS<n>`),
  Revision (`<document_no>-<revision_label>`), Templates, Pages, Created (by, at), Last edited (+ last PDF
  export). No UUID is shown anywhere.
- AC-L2 `SS<n>` numbers per document, start at 1, never reused after a delete (max + 1).
- AC-L3 Pages = cover + visible item pages (left-out pages not counted); "N edited" shows when N pages carry
  an override.
- AC-L4 No spec sheets: heading "No spec sheets yet" + hint, no button in the body. No product line at all:
  heading "No lines yet", Create disabled with the reason "Add a line to the quotation first."
- AC-L5 Row click opens View. Row menu: View, Export PDF, Delete.
- AC-L6 Readers without edit rights see the list, View and Export PDF; no Create, Edit page, Delete,
  on-page typing, Leave out or Add accessory.

## Create

- AC-C1 Create spec sheet opens a dialog with Revision, Cover template, Page template, Single item template
  (clearable). Revision lists "Current draft" first (no issue yet, or lines changed after the last issue),
  then every issued revision, newest first. No signature (ours or the customer's) is required.
- AC-C2 Defaults: newest revision; templates from the last spec sheet this user created (any document),
  else blank.
- AC-C3 Template options are published `spec_cover` / `spec_page` templates only. Create refuses (422, shown
  under the field): missing cover or page template; a template of another family or unpublished; a size
  differing from the cover; a revision of another document.
- AC-C4 Create stores the record with the template ids AND their published version ids at that moment, and
  a snapshot of the items (from the issue, or from each scope's current version for a draft) with
  `items_taken_at`. Page rows start clean: AREA = Section heading, nothing left out, quotation order, no
  page edits. Nothing is copied from another spec sheet. Then View opens.
- AC-C5 A draft sheet does not change when the draft's lines change later; it lists as "Draft after R<n>"
  (or "Draft" when nothing was issued) with the time its lines were taken.

## View (reader)

- AC-V1 All pages render stacked in print order (cover first), each through `TagSheetRenderer` at the
  template's size; the toolbar shows page N of M (tracks scrolling), zoom out / in, fit width.
- AC-V2 The rail lists every page; click scrolls to it; drag reorders and saves (as #2103). A left-out page
  sits in the rail and the stack greyed with "Left out of the spec sheet" and Put back, unnumbered.
- AC-V3 AREA / COMMENT / marker click-to-type, Leave out / Put back and Add accessory behave as in #2103,
  saving to THIS spec sheet only (another sheet of the same document is unchanged).
- AC-V4 Prev / next goes between spec sheets of the same document.
- AC-V5 Performance: page images in the reader and rail are preview size; a page's renderer mounts only when
  it is near the viewport; only the export payload signs full-size originals.
- AC-V6 Use latest templates shows only when a newer published version of a used template exists; it moves
  the sheet to the newest versions and keeps page edits.

## Edit page

- AC-E1 Edit page opens `TagCanvasEditor` with the page's layers (its override, else the frozen template
  version's) bound to that page's data.
- AC-E2 Save page stores the layers as an override for that page key on this spec sheet; the template, its
  versions and other spec sheets are unchanged. The page then shows "Edited".
- AC-E3 Reset to template removes the override (5 s deferred reversible countdown).
- AC-E4 Export PDF and View both draw the override.

## Export / delete

- AC-X1 Export PDF queues a `user_downloads` row (source = the spec sheet) on `catalogue_render`; file name
  `spec-sheet-<quotation no>-SS<n>.pdf`; the PDF has exactly the visible pages in order with overrides.
  Prices follow #2103 (only where a template places one; zero blank).
- AC-X2 The print payload route resolves the spec sheet pinned to its document's company (fail closed when
  no company), as #2103 does.
- AC-X3 Delete: deferred 10 s countdown with Cancel, then hard delete. Existing downloads stay listed;
  re-rendering a deleted sheet's download answers 404.

## Data / migration

- AC-D1 New table `projects.quotation_spec_sheets` (company scoped, audit tracked), FK document (cascade) and
  issue (cascade, nullable for a draft); unique (document_id, sheet_no); JSONB `items`, `rows`, `page_edits`.
- AC-D2 Backfill: each document whose `spec_sheet` has cover and page templates set gets `SS1` on its saved
  issue (else newest issue; none: skipped), with its rows, its items snapshot and the templates' current
  published versions.
  Idempotent; downgrade drops the table.
- AC-D3 A template re-published after create does not change an existing spec sheet's pages (frozen version).

## Rights

- AC-R1 List / view / preview / export: project read (or API key, as #2103). Create / update / page edit /
  delete: project edit permission + write access to the project (as #2103's PUT).
- AC-R2 Every route checks the sheet belongs to the document in the path and the document to the project;
  a sheet id from another document answers 404.
