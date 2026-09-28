# PLAN: Project Sales quotation form page (add and edit), save creates it with its lines

Status: in review on PR #1343 (build lane, issue #1341, branch `feat/project-sales-quotation-form`). Track:
full lane (diff expected well over 300 lines; no migration; no auth or RBAC change).

UAC: `quotation-form-28sep-acceptance-criteria.md` (beside this file).

Base: `origin/main` at `d79b46c5ea2b000dcdc4e1fef1a722d17b07b84e`. Alembic heads on that base:
one head (quoted in the PR comment). No migration is needed: every column the form writes
already exists.

## Owner's words (28 Sep 18:3x MYT, verbatim)

> "when I add quotation, I should be able to enter the page in which I can add product, put in
> the details, instead you immediately help me create the quotation ah [...] now I am immediately
> in this page already and need to edit to add the product, shouldn't be, I should be able to add
> product straight away and save when I am satisfied, if I want to edit I can click on the gear
> button to edit [...] this table needs to be datagrid"

Addendum: "editing of scope should be done by 'Edit Quotation', not a separate button like this,
Edit quotation means I edit the whole quotation"

## Journey

1. Salesperson opens a project, Quotations tab, presses **Add a quotation**.
2. Lands on `/project-sales/[projectId]/quotation-documents/new`. Nothing exists on the server.
   The page shows the letterhead fields (recipient, attention, your ref, date, subject), then a
   Scopes section already holding one empty scope with its name, series and an empty lines
   datagrid. Add a line / Add a section are right there.
3. They name the scope, add lines (pick a product, the line fills description, brand, UOM, list
   price and the series price), add a second scope, add its lines.
4. **Save** sends ONE request. The server creates the document, its scopes, their version 1 and
   every line in one transaction, and the page lands on the quotation page
   (`/project-sales/[projectId]/quotation-documents/[id]`). **Cancel** goes back to the Quotations
   tab and nothing was ever written.
5. On the quotation page the read view shows the scopes and their lines in the system datagrid.
   The gear holds **Edit quotation**, which opens `/.../quotation-documents/[id]/edit`: the same
   form page, filled, with the same fields in the same order. Save sends ONE PATCH carrying the
   header and every scope (renames, series, new scopes, full line sets) in one transaction and
   lands back on the quotation page. Cancel lands back with nothing changed.

## What is there today (read before building)

- `QuotationsPanel.tsx` Add a quotation calls `create.mutateAsync({})` and pushes to the new
  document: that is the instant draft the owner is objecting to.
- `POST /projects/{id}/quotation-documents` creates the document only; no scope, no line.
- **No code inserts a placeholder line.** Neither `create_document`, `add_scope`,
  `create_quotation` (opens an empty version 1) nor `InlineLineTable` adds a row by itself. The
  struck-through "Item 1, Off-catalog, Qty 1" in the owner's screen is how `InlineLineTable`
  draws a row STAGED FOR REMOVAL in the in-place edit session: a row added with Add a line and
  then removed. The form page removes that path (no in-place session, no staged strike-through),
  and the tests pin that a created scope holds only the lines sent (zero when none).
- The quotation page (`quotation-documents/[documentId]`) runs an in-place edit session
  (`useQuotationEditSession`) opened from the gear, plus a per-scope **Edit scope** button and an
  **Add a scope** control that creates a scope instantly.
- The lines table is `InlineLineTable`, a hand-written `<table>`, not the system DataGrid.

## Slices

- **S1 backend: create and edit in one request.**
  - `ProjectQuotationDocumentCreate` gains optional recipient corrections and
    `scopes: [{scope_label, series_id?, notes?, lines: [ProjectQuotationLineBulkItem]}]`.
  - `ProjectQuotationDocumentUpdate` gains optional
    `scopes: [{id?, scope_label?, series_id?, notes?, lines?}]`.
  - Service `create_document_with_scopes` / `apply_form_scopes` reuse `add_scope`,
    `scope_service.update_quotation` and `scope_service.replace_lines` (same coercion,
    snapshotting, guardrails, rate-only totals, 422 on frozen or issued). The route commits once;
    any refusal rolls the whole save back.
  - Below-floor notifications fire for lines written this way exactly as the bulk line route does.
- **S2 frontend: the lines datagrid.** `QuotationLinesGrid` on `PanelDataGrid` (the component the
  Quotations list uses): resizable columns, column reorder through the listing preferences,
  pagination bar, the search box, band headings via `renderGroupHeader`, the total in the column
  footer. Read mode is plain cells. Edit mode adds Add a line and Add a section in the toolbar,
  and a per-row Edit that opens the row's editor in place (`expanded` +
  `meta.expandedContent`, the reorder planning pattern) with a Remove in it.
- **S3 frontend: the form page.** `/quotation-documents/new` and `/quotation-documents/[id]/edit`
  render `QuotationFormClient` in create or edit mode: letterhead (reusing
  `QuotationDocumentHeader` in its input mode), Scopes (name, series `SearchableSelect`, lines
  grid per scope, Add a scope), and in edit mode the cover letter and terms (they lose their only
  editor when the in-place session goes). One primary CTA (Save quotation) with Cancel beside it,
  no subtitle.
- **S4 frontend: rewire the entry points.** Quotations tab Add a quotation navigates to `/new`.
  The quotation page gear Edit quotation navigates to `/edit` (after the existing revise prompt
  when a scope is with the customer). The in-place session, the per-scope Edit scope button, the
  instant Add a scope and the "Press Edit to price this scope" hint are removed; Record outcome,
  Recheck alerts and Revise to vN stay. The read view's lines table is the new datagrid.

## Decisions

1. **Route.** The issue names `/project-sales/pipeline/[projectId]/quotations/new`. The project
   and its quotation page live at `/project-sales/[projectId]/quotation-documents/[documentId]`
   (there is no `pipeline/[projectId]` segment, and `quotations/[quotationId]` is the older
   per-scope page). So the form lives beside the page it saves into:
   `/project-sales/[projectId]/quotation-documents/new` and `.../[documentId]/edit`. Open
   question Q1 asks the owner to confirm.
2. **One request per save, one transaction.** Create is the existing POST with `scopes`; edit is
   the existing PATCH with `scopes`. No new endpoint: the two already own the document and a
   second route would be a second definition of "save a quotation".
3. **Status rules unchanged.** A scope whose current version is frozen or issued refuses new
   lines with the existing 422 (`quotation_version_issued` / `_frozen`), and the whole save rolls
   back. The form shows such a scope's lines read-only and never sends them. Edit on a quotation
   the customer holds still asks first and opens the next revision (the existing
   `ReviseToEditDialog`), then opens the form.
4. **Scopes missing from an edit PATCH are left alone.** The form cannot delete a saved scope
   (today's page cannot either); a scope added in the form and not yet saved can be removed
   before Save. See Q2.
5. **Recipient on create.** The server still snapshots the recipient off the developer party
   (AC-A3). A recipient value typed in create mode is applied on top of that snapshot in the same
   transaction, the same result as create then edit today. Blank keeps the snapshot.
6. **Cover letter and terms in edit mode only.** On create they are rendered from the company
   templates by the server, as today; the form carries them in edit mode because removing the
   in-place session would otherwise leave them with no editor.
7. **Empty scope in read view** shows the empty datagrid, no hint and no button (addendum).
   A quotation with no scopes keeps its empty state, whose next step is Edit quotation.

## Open questions (for the owner; building continues on the decisions above)

- **Q1** Route: confirm `/project-sales/[projectId]/quotation-documents/new` and `.../edit` in
  place of the issue's `/project-sales/pipeline/[projectId]/quotations/...`.
- **Q2** Should Edit quotation be able to delete a saved scope (only while nothing in it has been
  issued), or does that stay out?
- **Q3** Should Save refuse a quotation with no scope at all, or is a header-only draft fine
  (today it is)?

## Tests (tester first per slice)

- pytest `tests/test_quotation_form_save.py`: create with two scopes and lines in one request;
  a refused line rolls the whole create back (no document row); create with no scopes writes no
  scope and no line; create with an empty scope writes no line; edit applies header, rename,
  series, new scope and full line set in one PATCH; edit sending lines to an issued scope is 422
  and changes nothing.
- vitest: the form in create and edit mode; the lines datagrid (read cells, add line, add
  section, per-row edit, remove, search); the Quotations tab CTA route; the gear Edit entry; the
  read view has no Edit scope button and no empty-scope hint.
- Browser pass at 1280 and 375 on `/new`, `/edit` and the quotation page.
