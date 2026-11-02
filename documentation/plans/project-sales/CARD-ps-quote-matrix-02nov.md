# CARD: PS-QUOTE-MATRIX v1 (2 Nov 2026)

Status: Plan. Card + mock (`mockups/quote-matrix.html`) out for owner answers Q1-Q5. Code starts after
PS-PROPOSAL-QUOTATION #2097 merges (same services and models; crew-note posted there). Track: full (L): migration,
new grid editor, PDF + Excel + sign page, totals rule change.

Owner, 2 Nov ~21:55: "they have this quotation format where they define the level and the type. I need us to be able
to cater that. We can handle multiple sheets with a scope, but I need us to handle this kind of two-dimensional table
also. That is a very normal quotation format in project business. The technical drawing is optional. We got the column
header, column shoulder, so it's fine."

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main 6f1d3027 and on #2097's head 9275c753. The real case is the owner's workbook, anonymised: no customer,
developer, person, phone or real price appears here or in the mock (public repo). Dev data is not reachable from the
cloud sandbox this lane runs in, so the examples below are the workbook's own shapes with made-up rates; a
`crew-data-request:` goes out only if the owner wants a dev project dressed as the case.

## How it works today (facts)

- A quotation document has ordered **scopes** (the client's sheets/tabs), each with **versions** (revisions), each
  with **lines** (`BE/models/projects.py:1516` scope, `:1574` version with `total_amount` `:1602`, `:1618` line).
- A line holds ONE `quantity` (`:1679`), a `band_label` heading printed before it (`:1676`), one photo and an optional
  drawing (`:1662`), `is_rate_only` (printed, not summed, `:1685`). `unit_type` (`:1681`) is reference only and prints
  nowhere: it is NOT a column axis.
- Writable line fields `LINE_FIELDS` (`BE/services/project_quotation_service.py:67-89`); revise builds the next
  `ProjectQuotationVersion` and copies every line field by field (`:371-456`); version total skips rate-only lines
  (`_recalculate_total` `:510`). #2097 adds `make_quotation`, which copies via `scope_service.copy_line`.
- Scope total and grand total: `scope_total` (`BE/services/project_quotation_document_service.py:79`), grand total
  sums every scope (`:112`, issue snapshot `:584-613`).
- PDF: one fixed column set `_COLUMNS` (`BE/services/project_quotation_pdf_service.py:77`), one table per scope
  (`_scope_html` `:501`), A4 landscape already (`:726`). Excel: one sheet per scope (`build_issue_workbook`
  `BE/services/project_quotation_excel_service.py:553`, `_write_scope` `:359`, same `_COLUMNS` `:372`).
- Editor: `FE/[projectId]/components/QuotationLinesGrid.tsx` (1822 lines), fixed columns `:1009-1150` (# , Photo,
  Drawing, Product, Description, Brand, Qty, UOM, Rate, Total), on `@/components/ui/data-grid`. The DataGrid already
  renders grouped (2-row) headers: `components/ui/data-grid-table.tsx:1358-1391` walks `getHeaderGroups()`.
- Sign page: per scope, per line, the customer may suggest a quantity, a price, or removal
  (`AMENDMENT_FIELDS` `BE/models/projects.py:1324`; `(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx:329-405`);
  accepted suggestions are written into the next revision (`apply_request`
  `BE/services/quotation_amendment_service.py:581`).
- PO check on main compares model + price only (`BE/services/project_po_service.py:302-327`). #2097 adds
  `qty_over_quotation`, which SUMS `line.quantity` per product key over the current versions of every scope (so a
  product on three rows counts three times, which is right) and compares the PO total.

## Rules (my recommended answers in place)

**Shape**
1. A scope is **Plain** (today, unchanged) or **Grid**. Set in the scope's settings; a new scope is Plain.
2. A Grid scope has ordered **column groups** (owner: "column header"; a unit type like `TYPE A - 1 BH` or a level like
   `LEVEL 9`), each with ordered **sub-columns** (owner: "column shoulder"; an area like `KITCHEN` or a room like
   `SURAU M`). A group may have no sub-columns (`BREAK TANK`): it is then one quantity column under its own label.
3. Columns belong to the scope's **version**, so a revision freezes its columns with its lines and a later revision may
   add, rename, reorder or delete columns. Revise and make-quotation copy them.
4. Rows stay product lines, exactly as today: product or set, photo, optional drawing, description, rate, band heading,
   rate-only. Product, Brand and UOM columns are unchanged in the editor; the print hides what the sheet does not use,
   as today.

**Quantities and totals**
5. Each cell is the line's quantity in that room/area. Blank = 0. Cells take decimals like `quantity` (12,2), no
   negatives.
6. A group may carry **No. of units** (Q1). The line's `quantity` = sum over groups of (sum of the group's cells x the
   group's units, blank units = 1). It is computed on every save; in a Grid scope the Qty cell is read-only.
   Everything that reads one quantity keeps working: line total, version/scope/grand total, price floors and approval,
   #2097's qty-over check, SO draft, sample request, spec sheet.
7. **Per-unit scope**: a Grid scope with group totals on (rule 9) where any group has blank units is printed
   "Prices per unit" and is **left out of the document grand total** and out of #2097's qty-over quoted sum, because
   its numbers are per apartment, not per project. The screen and the PDF say so under the scope total. Fill in the
   units and it counts again. (Owner Q1.)
8. A row's group with every cell blank prints `-` in that group's total column (the workbook's "Type A has no common
   bath").
9. **Group totals** switch per scope (Q2): on = after each group a `Qty` and `RM` column (the UNIT sheet: qty and amount
   per ONE unit of that type) and a footer row `Total each type (RM)`; with units filled a second footer row
   `x units` and `Total all units (RM)`. Off = only one `Total qty` and one `Amount (RM)` column at the end (the
   LEVEL 9 sheet) and footer `Total amount`.
10. A rate-only line still prints its rate and cells and adds to no total, as today.

**Editing**
11. **Columns** button on the Lines tab of a Grid scope opens a dialog: list of groups (label, No. of units), each
    with its sub-columns; add, rename, drag to reorder, delete (deferred-action countdown, as every destructive
    action). **Copy from scope** fills it from another scope of the same document (the LEVEL 9 groups again).
12. Deleting a column with quantities in it: the countdown names how many cells it clears; those quantities leave the
    line totals when it commits.
13. Switch Plain -> Grid: each line's current quantity is put in the first sub-column, so no total changes until
    someone edits. Grid -> Plain: cells are dropped, each line keeps its summed quantity (blank units = 1).
14. **Paste from Excel**: select a cell and paste a block copied from the workbook's quantity area; tab/newline
    separated numbers fill right and down; `-` and blanks paste as blank; text that is not a number refuses the paste
    with one toast naming the first bad cell. Rows are not created by paste (products are picked first).
15. Same product on several rows is allowed (Q3), each row its own description note and cells; PO, SO and the spec
    sheet add them up by product (#2097's qty-over already sums by product key).

**Output**
16. PDF: a Grid scope prints a 2-row header (group over sub-column), narrow quantity columns, header repeated on every
    page (`thead`), landscape as today. When the table would be wider than the page (LEVEL 9 = 20 quantity columns
    plus totals), quantity columns shrink to a minimum width and the header text turns vertical (rotated 90 degrees).
    Never split a row's groups over two pages.
17. Excel: the sheet gets the same 2-row header with merged group cells, numbers in cells (not text), and live
    formulas for row totals and footers (`=SUM(...)`), so the customer's spreadsheet stays right when they edit it.
18. Sign page: unchanged card (each section: items, total; then the document total). A per-unit scope shows its total
    with "per unit" and is not in the document total. Expanding a Grid section shows the grid read-only.
19. Customer suggestions on a Grid row (Q4): price and removal only. The quantity box is not offered on a Grid row,
    because one total cannot be mapped back to rooms; the customer writes quantity changes in the existing comment and
    the salesperson edits the cells.

**Out of scope (named triggers)**
- Excel import of a whole workbook into a quotation: phase 2 lane (Q5), trigger = owner wants old workbooks loaded.
- Per-scope terms / per-scope REF suffix (lead time differs by sheet): scope `notes` carries it today; build when the
  owner asks for it printed in the terms block.
- Querying quantities per room/level in reports: JSONB is enough to edit and print; normalise into tables only when a
  report needs it.

## Examples (the owner's workbook, anonymised, made-up rates)

| # | Case | Expect |
|---|---|---|
| E1 | UNIT scope, Grid, group totals on. Groups `TYPE A - 1 BH` (`1 BH`, KITCHEN, YARD, BALCONY), `TYPE B - 2 BH` (`2 BH`, ...), `TYPE C - 3 BH` (`3 BH`, ...). Row "floor trap" rate 45.00: A `1 BH`=1, BALCONY=1; B `2 BH`=2, BALCONY=1; C `3 BH`=3, BALCONY=1. Units blank. | Row group totals A 2 / RM 90.00, B 3 / RM 135.00, C 4 / RM 180.00. Scope prints "Prices per unit", is out of the grand total. Stored `quantity` = 9 (units = 1). |
| E2 | Same as E1 with units A=120, B=250, C=133. | `quantity` = 2x120 + 3x250 + 4x133 = 1,522; line total 1,522 x 45.00 = RM 68,490.00. Footer "x units" row shows 120 / 250 / 133; scope now counts in the grand total and in qty-over. |
| E3 | Row "basin WB248 (COMMON)": A all blank, B `2 BH`=1, C `3 BH`=2. | A's total column prints `-`; B 1, C 2. |
| E4 | LEVEL 9 scope, Grid, group totals off. Groups LEVEL 9 (11 rooms), LOBBY A (LEVEL 1) (4), LOBBY B (LEVEL 2) (4), BREAK TANK (no sub-columns). Row "WC" rate 600.00 with 1 in 13 rooms. | Total qty 13, Amount RM 7,800.00; footer "Total amount". Scope counts in the grand total (no per-unit groups). 20 quantity columns fit by vertical headers. |
| E5 | GUARD HOUSE and RECYCLE & BIN scopes stay Plain. | Unchanged print and totals; grand total = LEVEL 9 + GUARD HOUSE + RECYCLE (+ UNIT only when E2). |
| E6 | Angle valve on three UNIT rows (bath inlets, basin group, sink inlet), units filled. PO orders 2,000 of that code. | #2097 qty-over compares 2,000 with the SUM of the three rows' quantities. |

## Edge cases

- A group with sub-columns removed down to none becomes a single-column group; its cells under the old keys are
  dropped (rule 12 countdown names them).
- Column keys are generated ids, never the label, so a rename keeps the cells.
- A line pasted/created before columns exist: Grid scope with no columns behaves like Plain until the first column is
  added (rule 13 then moves the quantity into it).
- Revise of an issued Grid version: columns + cells copied; editing columns in the draft never touches the issued one.
- Customer suggestion already accepted on a Grid row's price: applied as today (price is per line).
- PO intake reading a PO for a per-unit scope with no units: no qty-over row for those products (rule 7); the
  model/price check still runs.
- 375px: the grid scrolls sideways inside the card with the # / Product columns pinned left, as the Lines grid does.

## What this touches that other PS lanes also touch

- #2097 PS-PROPOSAL-QUOTATION: `project_quotation_document_service.py` (make-quotation copy, grand total),
  `project_po_service.py` (`qty_over_quotation` must skip per-unit scopes), PDF/Excel services, `models/projects.py`.
  Build after it merges.
- #2103 PS-SPEC-SHEET: reads line quantity only; nice-to-have later: prefill its per-page "Area" from the sub-columns
  where the line has a quantity. Not in this lane.
- #2094 QUOTE-COVER-DESIGN: shares the PDF service and the migration queue; one migration PR at a time.

## Data (smallest that keeps every reader working)

- `projects.quotation_versions.matrix_columns` JSONB NULL:
  `{"group_totals": bool, "groups": [{"key", "label", "units": int|null, "cols": [{"key", "label"}]}]}`.
  NULL = Plain scope. On the VERSION (rule 3).
- `projects.quotation_lines.qty_cells` JSONB NULL: `{"<col key or group key>": "<decimal string>"}`.
- `quantity` stays and is derived (rule 6). Both new fields join `LINE_FIELDS`/revise/`copy_line`; the version field
  joins the revise and make-quotation version copy. Issue snapshots already point at versions, so nothing to snapshot.
- One migration, two nullable columns, no backfill.

## Questions for the owner (max 5, recommendation first)

1. **Unit counts.** The UNIT sheet prices ONE unit of each type; the number of units is not in the sheet.
   (a) optional "No. of units" per type: filled = quantities and amounts roll up to the project and PO/SO checks use
   them; blank = the scope prints "per unit" and stays out of the grand total; (b) per-unit only, never rolled up.
   **Recommend (a)**: the PO for 503 units must tally with the quotation, which (b) can never do.
2. **Per-type totals.** (a) a per-scope switch: on for unit types (Qty + RM after each type, UNIT style), off for
   levels (one total at the end, LEVEL 9 style); (b) always; (c) never. **Recommend (a)**, it reproduces both sheets.
3. **Same product on several rows** (angle valve for the WC inlet and again for the sink). (a) allowed, each row its
   own note and cells, PO/SO/spec sheet add them up by product; (b) one row per product. **Recommend (a)**: that is
   how the salespeople write it.
4. **Customer suggestions on a grid row.** One total quantity cannot be split back into rooms. (a) price and removal
   only on a grid row, quantity changes go in the comment and the salesperson edits the cells; (b) a suggested
   quantity per cell. **Recommend (a)**: (b) puts a 20-column editor on the customer's phone.
5. **Importing existing workbooks** (each sheet -> scope, header rows -> columns, rows matched by product code).
   (a) phase 2 after the grid ships, with paste-from-Excel of the quantity block now; (b) in this lane.
   **Recommend (a)**: the grid has to exist before an import has something to fill.
