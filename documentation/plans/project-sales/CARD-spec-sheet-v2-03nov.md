# CARD: SPEC-SHEET-V2, saved spec sheets + PDF-style viewer (3 Nov 2026)

**Status:** Behaviour card, asked (crew-ask on PR #2124). Track: L (new table, new routes).
Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend`. Code read on main c7ee22cf.

## The owner's ask (3 Nov ~11:35)

Four pickers on the tab are not the system design. Wanted: a TABLE of spec sheets created; Create
spec sheet picks the revision; no waiting for the customer to sign back; View scrolls like a PDF;
edit / amend each page in the designer we have.

## How it works today (#2103, facts)

- **One spec sheet per document, no record.** Settings are one JSONB column
  `projects.quotation_documents.spec_sheet` (`BE/models/projects.py`, migration `pss_0001_spec_sheet`):
  `{cover_template_id, page_template_id, single_page_template_id, issue_id, rows[]}`
  (`BE/services/project_spec_sheet_service.py:86-95`). Exports are `user_downloads` rows of kind
  `quotation_spec_sheet_pdf` (`:41, :725-757`); nothing lists them on the document.
- **Revision rule: ANY issued revision, no customer signature.** `issue_for` takes the asked id, else the
  saved pick, else the newest issue, with no status filter (`project_spec_sheet_service.py:206-220`); the
  picker lists every issue (`BE/api/v1/projects/spec_sheet.py:103-121` -> `list_issues`,
  `BE/services/project_quotation_document_service.py:562-569`, no filter). The customer counter-signature
  is `quotation_issues.customer_signature_id`, documented as "null is a legitimate resting state"
  (`BE/models/projects.py:1396-1400`) and never read by the spec sheet. What IS required: an issue row,
  and issuing needs OUR signature (`project_quotation_document_service.py:606-613`, "Sign this quotation
  before issuing it"). So the owner's "must be signed back by the customer" is not today's rule; the
  likely trigger is the empty state "No issued revision yet / Issue a revision first"
  (`FE/.../QuotationSpecSheetTab.tsx:135-138`) on a document whose Sign step had not happened.
- **Revision label bug (small):** the picker labels revisions with `quotation_no(document_no, issue_no)`
  (`spec_sheet.py:113`), not the issue's own `revision_label`, so a proposal's `A` / `B` revisions show
  as `R1` / `R2`. v2 uses `revision_label` (as `our_ref_text` does at issue,
  `project_quotation_document_service.py:633`).
- **Pages:** cover + one page per item (product / set), set parts as accessories, Leave out / Put back,
  AREA (default = Section heading) / COMMENT / marker typed on the page, hand-picked accessories, drag
  order, no prices unless the template places one, all templates the cover's size
  (`project_spec_sheet_service.py:366-459, 520-541`). Drawn by `TagSheetRenderer`; PDF via the
  `catalogue_render` worker.
- **Reusable pieces:** `PanelDataGrid` (`FE/components/common/PanelDataGrid.tsx`, used by
  `.../[projectId]/components/SalesOrdersPanel.tsx`), `FormDialogScaffold`
  (`FE/components/common/FormDialogScaffold.tsx`), `DeferredActionButton`
  (`FE/components/common/DeferredActionButton.tsx`), `PdfViewer` (page counter, zoom, continuous scroll;
  `FE/components/common/pdf-viewer/*`), `TagCanvasEditor` with `boundData` + `onLayersChange` +
  `specSheet` (`FE/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor.tsx:384-515`).

## Rules (proposed)

1. **Tab = list.** The Spec sheet tab is a `PanelDataGrid` of this document's spec sheets, newest first:
   No. (`SS1`, `SS2` ... per document), Revision (`PRJQ-2026-0007-R2`), Templates (cover / page / single),
   Pages (printed count, cover included), Created by + at, Last edited. Row click = View. Row actions:
   View, Export PDF, Delete. Empty state: heading "No spec sheets yet", hint, no button; the ONE CTA
   "Create spec sheet" sits in the tab header (`DESIGN-LANGUAGE.md` section 6).
2. **Create = dialog** (`FormDialogScaffold`): Revision (`SearchableSelect`, every issued revision, newest
   first, labelled by `revision_label`; no customer signature needed), Cover template, Page template,
   Single item template (clearable; blank = the page template). Defaults: newest revision; templates
   from the last spec sheet this user created, else blank. Create saves a record and opens View.
3. **A spec sheet is a saved record**: new table `projects.quotation_spec_sheets` (document, issue, sheet
   no, the three template ids AND the published version ids at create, the item rows, per-page
   overrides, page count, created / updated by + at, company_id). The revision is already frozen by the
   issue; the record freezes the templates and the page settings, so a sheet already sent does not move
   when a template is re-published or the next revision is issued.
4. **Page settings carry forward.** A new spec sheet starts its rows (order, AREA, COMMENT, marker, Leave
   out, picked accessories) from the newest spec sheet of the same document, by item key (product /
   `set:<id>`), exactly as #2103 carries them across revisions. Items new in this revision append in
   quotation order. The first spec sheet of a document starts from the #2103 column (see rule 10).
5. **View = PDF-style reader.** Full-width continuous vertical scroll of every page at the template size
   (cover first), page N of M, zoom (fit width / 50-200%), a thumbnail rail on the left (click jumps, drag
   reorders, #2103 order rules). Same `TagSheetRenderer` the PDF prints with, so screen = PDF.
6. **On-page actions stay (#2103):** click AREA / COMMENT / marker to type; Leave out / Put back (a left-out
   page stays in the reader greyed with "Left out", is not printed and not counted); Add accessory.
7. **Edit page = the designer.** Each page has "Edit page", opening `TagCanvasEditor` on that page's layers
   bound to that page's data. Save stores an OVERRIDE on this spec sheet for this page only (the template
   is untouched). An edited page shows "Edited" and offers "Reset to template". The cover is editable the
   same way. Export prints overrides.
8. **Export PDF** from the list or the reader: queues the PDF from the saved record (same worker, same
   My Downloads flow, file `spec-sheet-PRJQ-2026-0007-R2-SS1.pdf`). The list shows the latest export
   time.
9. **Delete** = hard delete with the deferred countdown (`DeferredActionButton`), no confirm. Exports
   already in My Downloads stay.
10. **Existing data:** the migration turns each document whose #2103 column has both templates set into
    `SS1` (its picked revision, else the newest), so nothing set up on prod is lost; the column is then no
    longer read (dropped in a later lane, trigger: v2 merged and the backfill checked on prod).
11. **Rights:** list / view / export = project read (as #2103); create / edit / delete = project edit + write
    access (as #2103's PUT, `spec_sheet.py:138-155`). Company scoped like `quotation_issues`.

## Kept from #2103 unchanged

Canvas flow, Leave out / Put back, AREA / COMMENT / markers, set parts + hand-picked accessories, no
price unless the template places one (zero prints blank), same-size templates (422 otherwise), print
pipeline and page size, `is_accessible` badge.

## Real examples (dev data)

The sandbox cannot reach the dev DB (crew contract), so these are the cases #2103 recorded:

- **PRJQ-2026-0007** (owner's prod case, 3 Nov): the four-picker tab; it becomes one row `SS1` if its
  templates were set (rule 10), else an empty list with Create spec sheet.
- **PRJQ-2026-0027 on PRJ-000002** (crew, R1 issued): WC set SRTWC6405 (pan SRTWCX6405 + tank SRTWCY6405
  + seat cover SRTWC6405-SC) under Section `UNIT`, basin SRTWB1413-GY, bottle trap SRTKSBT001, floor trap
  SRTFT205. As `SS1` on R1: cover + 4 pages; picking the trap under the basin makes it 3 pages.
- **Same document after R2** (one line added): Create picks R2; `SS2` starts with SS1's AREA / COMMENT /
  order; the new item appends last. SS1 still prints R1 as sent.
- **A proposal** with revisions `A`, `B`: the dialog lists `... -B`, `... -A`, not `R2`, `R1`.
- **Edited page**: page 3 of SS2 edited (photo enlarged, a note layer added): SS2's PDF shows it, SS1 and
  the template do not change.

## Edge cases

- No issued revision: Create spec sheet is disabled with the reason "Issue a revision first" (tooltip);
  list shows the empty state.
- A template unpublished or deleted after create: the sheet keeps printing from its frozen version.
- An overridden page whose item leaves a later revision: not possible, a spec sheet is pinned to one
  revision; a new sheet starts without overrides.
- Revision deleted (if a revision can ever be deleted): its spec sheets go with it (FK cascade).
- Two people editing one spec sheet: last save wins per field (same as #2103's PUT); not locking.
- 375px: the list scrolls inside the grid; the reader fits width, rail hidden behind a "Pages" button;
  the designer needs desktop width (same as Tag Templates today).

## Questions (max 5, each with a recommendation)

- **Q1 Revision.** (a) any issued revision (today's rule; issuing needs only OUR signature, not the
  customer's); (b) also allow the unissued draft, so the catalogue can be built before Issue.
  **Recommend (a)**: it is already the rule, the sheet then matches the exact R the customer holds, and
  the flow is Sign -> Issue -> Create spec sheet -> send both.
- **Q2 Templates pinned.** When a template is re-published after a spec sheet is made: (a) the sheet keeps
  the version it was made with (what was sent stays as sent); (b) it follows the latest published.
  **Recommend (a)**, with "Use latest templates" on the sheet to refresh on purpose.
- **Q3 Page edit scope.** "Edit page" in the designer changes: (a) this page of this spec sheet only;
  (b) the template for every sheet. **Recommend (a)**: the template stays in Dealer Kit > Tag Templates
  where it is edited today; an "Open template" link sits next to Edit page.
- **Q4 Starting point of a new sheet.** (a) copy page settings from this document's newest sheet;
  (b) start clean every time. **Recommend (a)**: SS2 on R2 is mostly SS1 again; page overrides are NOT
  copied (they are tied to that sheet's layout).
- **Q5 Old settings.** (a) backfill each set-up document into `SS1`; (b) start every document empty.
  **Recommend (a)**: PRJQ-2026-0007 and any other set-up quotation keep their work.
