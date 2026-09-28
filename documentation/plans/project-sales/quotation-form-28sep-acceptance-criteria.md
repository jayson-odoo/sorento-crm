# UAC: quotation form page (add and edit), issue #1341

Plan: `PLAN-quotation-form-28sep.md`. One AC per behaviour. "The form" is
`/project-sales/[projectId]/quotation-documents/new` (create) and
`/project-sales/[projectId]/quotation-documents/[documentId]/edit` (edit).

## Entry points

- **AC-QF001** On a project's Quotations tab, Add a quotation navigates to the form in create
  mode. It sends no request that writes anything.
- **AC-QF002** On the quotation page the gear holds Edit quotation, which navigates to the form in
  edit mode for that quotation.
- **AC-QF003** On a quotation whose scope is with the customer (issued current version), Edit
  quotation first asks to open the next revision (existing prompt); confirming revises and then
  navigates to the form in edit mode. Cancelling the prompt changes nothing.
- **AC-QF004** The quotation page has no per-scope Edit scope button, no instant Add a scope
  control, and no in-place edit session (no Save quotation / Cancel pair on the read page).
  Record outcome, Recheck alerts and Revise to vN stay.

## Create

- **AC-QF010** Nothing is created before Save: opening the form, typing, adding scopes and lines
  writes no row.
- **AC-QF011** The create form shows the letterhead fields: recipient name, address and phone,
  attention, your ref, date (defaults to today), subject (defaults to the project title).
- **AC-QF012** The create form starts with one scope holding a name field, a series dropdown
  (the system `SearchableSelect`, clearable) and an empty lines datagrid, so a product can be
  added straight away.
- **AC-QF013** Add a scope appends another scope to the form; a scope added in the form can be
  removed before Save.
- **AC-QF014** Save sends ONE request carrying the header, every scope and every line; on success
  the page lands on the new quotation page.
- **AC-QF015** The server creates the document, its scopes, each scope's version 1 and every line
  in one transaction: a line the server refuses (e.g. off-catalog with no description) rolls the
  whole create back, and no document, scope or line row is left.
- **AC-QF016** Cancel returns to the project's Quotations tab and leaves nothing behind.
- **AC-QF017** No placeholder line: a scope saved with no lines has zero lines, and no line is
  ever inserted that the user did not add.
- **AC-QF018** Save refuses (client side, before any request) a scope with no name, and a line
  with neither a product nor a description, naming what is missing.
- **AC-QF019** A recipient typed in create mode is stored; one left blank keeps the snapshot from
  the project's developer.

## Edit

- **AC-QF020** The edit form holds the same sections in the same order as create, filled from the
  saved quotation, plus the cover letter and terms.
- **AC-QF021** Save sends ONE PATCH with the header and every scope (rename, series, full line set
  for editable scopes, new scopes with their lines) and applies it in one transaction; it lands
  on the quotation page.
- **AC-QF022** Cancel returns to the quotation page and nothing is written.
- **AC-QF023** Status rules unchanged: a scope whose current version is issued or superseded
  shows its lines read-only in the form and its lines are not sent; a PATCH that does send lines
  for such a scope is refused with the existing 422 and nothing in the save is written.
- **AC-QF024** A saved scope left out of the PATCH is untouched (the form cannot delete a saved
  scope).

## Lines datagrid

- **AC-QF030** The scope lines table, on the quotation page and in the form, is the system
  DataGrid (`PanelDataGrid`): fixed layout, resizable columns, column order from the listing
  preferences, the pagination bar, no hand-written table markup.
- **AC-QF031** The lines search box filters the lines by product code, description, brand or
  section heading.
- **AC-QF032** Section headings render as band rows above the line that opens them.
- **AC-QF033** In the form, Add a line appends a line and opens its editor; Add a section appends
  a line with its section heading field open.
- **AC-QF034** In the form each row has an Edit control that opens that row's editor in place
  (product, description, tech spec, brand, qty, UOM, unit price, complete set, counts per, rate
  only, section heading, notes) with a Remove; picking a product fills description, brand, UOM,
  list price and the series price.
- **AC-QF035** The Total column's footer shows the scope total off the live lines, rate-only lines
  excluded.
- **AC-QF036** On the quotation page an empty scope shows the empty datagrid with no "Press Edit"
  hint and no button.

## Page rules

- **AC-QF040** One primary CTA per page (Save quotation on the form; Issue on the quotation page),
  and no subtitle under the page title.
- **AC-QF041** Every select on the form is the system `SearchableSelect`.
- **AC-QF042** The form and the quotation page are usable with no horizontal page scroll at 375px
  and at 1280px.
