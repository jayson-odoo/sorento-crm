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
- **AC-QF012** The create form starts with one scope ("Scope 1" until it is named) and its empty
  lines table, so a product can be added straight away. (Round 3: the scope is named, and its
  series set, through the quotation page's Edit scope dialog, see AC-QF070.)
- **AC-QF013** Add a scope appends another scope to the form; a scope added in the form can be
  removed before Save. (Round 3: Add a scope is the + at the end of the scope strip and its name
  dialog, as on the quotation page.)
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
- **AC-QF024** A saved scope left out of the PATCH is untouched. (Deleting one is explicit, see
  AC-QF058.)

## Lines datagrid

**Superseded by round 3 (AC-QF070 to AC-QF073).** AC-QF030 to AC-QF034 described the round 1
`QuotationLinesGrid`, which the owner rejected ("we shouldn't revamp the Lines tab"). It is
deleted; the lines table on the quotation page and in the form is `InlineLineTable` again, as on
origin/main. AC-QF035 (live footer total, rate-only excluded) and AC-QF036 (empty scope reads "No
lines yet." with no "Press Edit" hint) still hold on that table.

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

- **AC-QF040** One primary CTA per page (Save quotation on the form; Send to Customer on the quotation page),
  and no subtitle under the page title.
- **AC-QF041** Every select on the form is the system `SearchableSelect`.
- **AC-QF042** The form and the quotation page are usable with no horizontal page scroll at 375px
  and at 1280px.

## Fix round 2: the owner's rulings (issue #1341 addenda 2 to 4, PR #1343 11:33Z)

Owner, verbatim: "i need this to be under 'Header' tab to align with our system design"; "Lines"
written over the Scopes tab; "this one should be in header details"; on Issue R1: "call this Send
to Customer"; "header stays in header tab"; delete a saved scope: "yes can"; header-only save:
"yes can, header only is fine"; cover letter and terms on create: "show them on create as well".

- **AC-QF050** The quotation page's tabs read Header, Lines, Cover letter, Terms, Signatures, in
  that order, each its own route. Header is first and is the index route; Lines is `/lines`.
- **AC-QF051** The Header tab holds the letterhead card (To with recipient, address and phone,
  Attn, Our Ref, Your Ref, Date, Total). Above the tabs stay only the page title, the status pill,
  the project title and developer lines, the header actions and their hints; the card does not
  appear on any other tab.
- **AC-QF052** Issued by and Opened for each scope's current version are in the Header tab's
  details, beside the refs: one pair of fields for one scope, grouped by scope ("Townhouse v2")
  when there are several. No Issued by / Opened strip sits above the lines table.
- **AC-QF053** No tab, empty state or test names the tab "Scopes"; it is "Lines" everywhere a user
  sees it. The data model and API keep "scope".
- **AC-QF054** The document number is not repeated under the page title, and the subject is not
  repeated as a read inside the Header card (#1336 kept).
- **AC-QF055** The form page (create and edit) has the tabs Header, Lines, Cover letter, Terms, in
  that order, not stacked sections. Header holds recipient name, address, phone, attention, your
  ref, date and subject (plus Issued by / Opened in edit); Lines holds the scopes and their lines.
- **AC-QF056** On create, the Cover letter and Terms tabs are present, prefilled from the company's
  active templates, and editable before the first save; the typed text is saved with the
  quotation and its merge fields are filled against the saved quotation. No template leaves the
  tab empty and editable. Save waits until the templates have answered. A tab left blank takes the
  company template, rendered after the lines are written, so `{{grand_total}}` is the real total.
- **AC-QF057** The quotation page's primary CTA reads "Send to Customer R<n>" (the revision kept,
  as the old label had it). The exports' hint reads "Send it to the customer first". The success
  toast reads "Sent to the customer as <ref>". API and status names are unchanged.
- **AC-QF058** Edit quotation offers Remove scope on a saved scope none of whose versions was
  ever sent to the customer; the removal is staged and sent in the ONE PATCH as
  `remove_scope_ids`, deleting the scope, its versions and lines. Removal is a hard delete, so it
  needs `projects.projects.delete` like the scope DELETE route: without it the form offers no
  Remove on a saved scope and the server answers 403 `quotation_scope_remove_forbidden`. A scope
  named in both `remove_scope_ids` and `scopes` is refused up front (422
  `quotation_scope_removed_and_edited`).
- **AC-QF059** The server refuses to remove a scope any version of which was issued (even after a
  revision) with 422 `quotation_scope_issued`, naming the scope; nothing in that save lands. A
  scope of another document is a 404.
- **AC-QF060** A header-only save is allowed on create (an untouched new scope is not sent, so the
  quotation saves with no scope) and on edit (a PATCH with no scope change). A scope with lines and
  no name is still refused, and the refusal opens the Lines tab.
- **AC-QF061** `/new` opens cleanly for a project with no quotation (no document fetched, no
  draft created), and its Cancel returns to the project's Quotations tab.

## Fix round 3: reuse the existing lines editor (PR #1343, owner hand test 29 Sep 00:2x MYT)

Owner, verbatim: "for #1343, we shouldn't revamp the Lines tab, it was good, we should reuse that,
I am just rearranging the layout, not redesigning the quotation please".

- **AC-QF070** The form's Lines tab (create and edit) is the quotation page's lines editing as it
  was on origin/main before this PR, moved under the tab: the scope strip (`QuotationScopeTabs`)
  with Add a scope at its end (`QuotationNameDialog`), the scope card (name, outcome, series, Edit
  scope via `QuotationDialog`), and under it `QuotationVersionEditor` in its staged edit mode, on
  `InlineLineTable`. The round 2 inline per-line editor (`QuotationLinesGrid`, its per-row Edit,
  the line panel under the grid, Done) does not exist anywhere.
- **AC-QF071** Add a line, Add a section, cell edits, reorder and Remove (struck through, "Removed
  on save", restorable) go through the same `useQuotationEditSession` handlers (`seedScope`,
  `stageScope`, `toggleRemoved`) the quotation page's Edit used, and nothing is written until the
  form's Save, whose ONE request carries the staged lines (removed ones left out).
- **AC-QF072** A saved scope is sent with its lines only when they moved on the form (the rule the
  quotation page's Save kept: the write replaces the whole set). A scope nobody opened, or one the
  customer holds (never staged), is sent without lines. Save no longer waits on every saved
  scope's lines loading.
- **AC-QF073** The minimum adaptation for a scope not saved yet: `QuotationVersionEditor` takes
  `quotation: null`, starts with no lines, reads no version, lines or verdict (only Off-catalog
  shows until Save), and offers no Revise (a revise writes at once; the quotation page's Edit
  quotation already asks to revise first). It takes the form's staged series for the series price
  fill. `QuotationDialog` takes `onSubmit`, so the form stages the scope's name, series and notes
  instead of writing them.

