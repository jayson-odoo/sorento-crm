# CARD: PS-QUOTE-MATRIX v3 (2 Nov 2026)

Status: Plan. Card v3 + mock v3 (`mockups/quote-matrix.html`) after the owner's Lavish notes on v2. Code starts after
PS-PROPOSAL-QUOTATION #2097 merges (same services and models; #2097 acked: `copy_line` stays the single line-copy
point). Track: full (L): migration, grid editor, PDF + Excel + sign page, customer suggestions become feedback notes.

Owner, 2 Nov ~21:55: "they have this quotation format where they define the level and the type. I need us to be able
to cater that. We can handle multiple sheets with a scope, but I need us to handle this kind of two-dimensional table
also. That is a very normal quotation format in project business. The technical drawing is optional. We got the column
header, column shoulder, so it's fine."

**Owner answers (2 Nov ~22:00), applied below:** Q1 no "No. of units": the real quantity is punched into each cell.
Q2 no style switch: ONE generic capability that always shows totals per column header and per column. Q3 same product
on several rows: yes, summed by product for PO / SO / spec sheet. Q4 sign page: suggestions per row AND per cell. Q5 no
Excel import, users use the system. And: "I want our quotation to be backward compatible with what we have now. It is a
very generic engine." So a plain scope IS a grid with one quantity column; existing quotations render and behave exactly
as today with no data conversion.

**Owner notes on mock v2 (2 Nov 23:11), applied below:** (1) "All these are configurable right?" Yes: headers and
columns are set per scope (answered on the mock page). (2) "brand product code rate only complete set all those need to
retain": every existing line column stays around the grid (rule 4). (3) "These are sections in our system right?
Existing": yes, "Bathroom" is today's `band_label` section heading (answered on the page). (4) "Can this configuration be
on the same table, dont need separate screen": columns are edited in the table header itself; the Columns dialog is
gone (rule 11). (5) "Dont need accept anymore, it is a feedback mechanism, the salesperson will act on it in a very
flexible way, not like accept or reject": the customer leaves feedback notes per item or per cell; the salesperson
reads them and edits the draft however they like, at most ticking a note as handled (rules 19-22). This replaces
today's Accept / Reject / Apply for EVERY quotation, not only grid scopes: one mechanism.

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main 6f1d3027 and #2097 head 9275c753. The real case is the owner's workbook, anonymised (public repo): no
customer, developer, person, phone or real price here or in the mock; rates and counts are made up. Dev data is not
reachable from this cloud sandbox, so the examples are the workbook's own shapes.

## How it works today (facts)

- A quotation document has ordered **scopes** (sheets/tabs), each with **versions** (revisions), each with **lines**
  (`BE/models/projects.py:1516` scope, `:1574` version, `total_amount` `:1602`, `:1618` line).
- A line holds ONE `quantity` (`:1679`), a `band_label` heading printed before it (`:1676`), one photo, an optional
  drawing (`:1662`), `is_rate_only` (printed, not summed, `:1685`). `unit_type` (`:1681`) is reference only.
- Writable line fields `LINE_FIELDS` (`BE/services/project_quotation_service.py:67-89`); revise copies the version and
  its lines (`:371-456`; on #2097 through `copy_line`); version total skips rate-only (`_recalculate_total` `:510`).
- `scope_total` (`BE/services/project_quotation_document_service.py:79`); grand total sums every scope (`:112`,
  issue snapshot `:584-613`).
- PDF: fixed `_COLUMNS` (`BE/services/project_quotation_pdf_service.py:77`), one table per scope (`_scope_html`
  `:501`), A4 landscape (`:726`). Excel: one sheet per scope (`BE/services/project_quotation_excel_service.py:553`,
  `_write_scope` `:359`, `_COLUMNS` `:372`).
- Editor: `FE/[projectId]/components/QuotationLinesGrid.tsx`, fixed columns `:1009-1150`, on
  `@/components/ui/data-grid`, which already renders grouped 2-row headers (`components/ui/data-grid-table.tsx:1358-1391`).
- Sign page suggestions: one row per (line, field), field in `quantity | unit_price | remove`
  (`AMENDMENT_FIELDS` `BE/models/projects.py:1324`, row model `QuotationAmendmentRequestRow` `:1378`, `field`
  String(16) `:1399`); the salesperson accepts / rejects each, Apply writes the accepted values into the next revision
  (`apply_request` `BE/services/quotation_amendment_service.py:581`); FE `(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx:329-405`.
- #2097 `qty_over_quotation` (`project_po_service.py` on #2097) sums `line.quantity` per product key over the current
  version of every scope, so repeated rows of one product already add up.

## Rules

**One engine, backward compatible**
1. Every scope has a column layout. A scope with no columns defined (every scope today, and every new scope) has ONE
   implicit quantity column, "Qty", and looks, prints, exports and totals exactly as today. No migration of data, no
   toggle, no "Grid" mode: defining columns is what makes a scope two-dimensional.
2. Columns are **column headers** (owner's word; a unit type like `TYPE A - 1 BH` or a level like `LEVEL 9`), ordered,
   each with ordered **column shoulders** (an area like `KITCHEN`, a room like `SURAU M`). A header with no shoulders is
   one quantity column under its own label (`BREAK TANK`).
3. Columns belong to the scope's **version**: a revision freezes its columns with its lines; a draft revision may add,
   rename, reorder or delete columns. Revise and make-quotation copy them.
4. Rows stay product lines exactly as today, and EVERY existing line column stays where it is around the grid (owner
   note 2): #, photo, drawing, product code, description, technical spec, brand, UOM, rate, complete set, rate only,
   section heading (`band_label`, owner note 3). Only the single Qty column is replaced by the quantity columns. The
   existing column picker still hides any of them for the screen; the PDF keeps today's printed columns.

**Quantities and totals (always the same rules, no switch)**
5. Each cell is the real quantity of that line in that column, punched in as needed (120, 250 ...). Blank = 0.
   Decimals as `quantity` (12,2), no negatives.
6. The line's `quantity` = the sum of its cells, computed on every save; with columns defined the Qty cell is
   read-only. Line total, version / scope / grand totals, price floors and approval, PO checks (#2097 qty-over), SO
   draft, sample request and spec sheet keep reading that one number. Every scope counts in the grand total.
7. Row totals, printed and shown:
   - after each header that has 2 or more shoulders, when the scope has 2 or more headers: that header's `Qty` and
     `RM` for the row (TYPE A's qty and amount);
   - at the end of the row, always: `Total qty` and `Amount (RM)`.
   A header with one column, or a scope with one header, gets no per-header pair: it would repeat the row total.
8. Footer rows, shown when columns are defined: `Total qty` under every quantity column and per-header Qty column (per
   room, per type); `Total (RM)` under every per-header RM column (per type / per level); then the scope total.
   A scope with no columns keeps today's single TOTAL line.
9. A header pair where every cell of the row is blank prints `-` (the workbook's "Type A has no common bath").
10. A rate-only line prints its rate and cells and adds to no total, as today.

**Editing**
11. **Columns are edited in the table header itself** (owner note 4), on a draft version: click a header or column
    label to rename it in place; drag a header's handle to reorder headers, drag a column label to reorder within its
    header; the x on a label removes it; a narrow "+" after a header's columns adds a column; "+ Column header" at the
    far right adds a header. Removal is a deferred action shown in the header itself (it turns red, counts down, Undo
    in place; no confirm); its quantities leave the totals when it commits. "Copy columns from" on the table toolbar
    copies another scope's headers and columns (not quantities). No separate screen or dialog.
12. Adding the first column moves each line's current quantity into it, so no total changes. Deleting the last column
    leaves each line with its summed quantity: back to today's layout.
13. Column keys are generated ids, never the label, so a rename keeps the cells.
14. **Paste from Excel**: with a quantity cell selected, a block copied from a spreadsheet fills right and down; `-` and
    blanks paste as blank; a non-number refuses the whole paste with one toast naming the first bad cell. Paste never
    creates rows (products are picked first).
15. Same product on several rows is allowed, each row with its own note and cells; PO, SO and spec sheet add them up
    by product (#2097 already sums by product key).

**Output**
16. PDF: a scope with columns prints a 2-row header (header over shoulder) repeated on every page, rows never split;
    when the columns would not fit the landscape page, quantity columns shrink to a minimum width and their headings
    turn vertical. A scope without columns prints exactly as today.
17. Excel (one sheet per scope, as today): same 2-row header with merged header cells, quantities as numbers, live
    `=SUM()` formulas for row totals, per-header totals and footers.
18. Sign page: the section card is unchanged (items, total, then document total). A section with columns expands to the
    grid, read-only, first column pinned, sideways scroll on a phone.

**Customer feedback (owner Q4 + note 5: per item AND per cell, no accept / reject)**
19. On the sign page the customer can leave a feedback note on a whole item or on one cell (tap the cell). A note may
    carry an optional hint: suggested quantity (item or cell), suggested price (item), or "remove this item". Scopes
    without columns: item notes as today's per-line suggestions, plus the free note.
20. Nothing is accepted, rejected or applied. The salesperson sees a **Customer feedback** tab: each note with where it
    points (scope, item, cell), the hint next to today's value, and "Show in Lines". The only action is **Handled**
    (who and when recorded, unticking reopens). The tab badge counts open notes. Open notes mark their cell / item
    in the Lines grid (amber corner / dot).
21. The salesperson acts by editing: Revise to edit, change whatever they see fit, issue the next revision (today's
    flow). Issuing a revision does not close notes; they stay until ticked handled.
22. Data: the existing `QuotationAmendmentRequestRow` becomes a feedback row: add `cell_key` (nullable) and `note`
    (text); `handled_at` / `handled_by` replace the pending / accepted / rejected decision; `field` gains `note`
    (a note without a hint). Apply (`apply_request`), the decision endpoints and the Accept / Reject UI are retired.
    Existing rows read as open feedback with their value as the hint; existing decided rows read as handled.

**Out of scope (owner: no import)**
- Excel import of existing workbooks: not built (owner Q5). Paste from Excel (rule 14) covers the quantity block.
- Per-scope terms / REF suffix: scope `notes` carries it; build when the owner asks for it printed.
- Reporting per room / level: JSONB edits and prints; normalise only when a report needs it.

## Examples (made-up rates and counts in the workbook's shapes)

| # | Case | Expect |
|---|---|---|
| E1 | UNIT scope, headers `TYPE A - 1 BH`, `TYPE B - 2 BH`, `TYPE C - 3 BH`, each with shoulders `<n> BH`, KITCHEN, YARD, BALCONY. Row "floor trap" rate 45.00: A `1 BH` 120, BALCONY 120; B `2 BH` 500, BALCONY 250; C `3 BH` 399, BALCONY 133. | Row: A Qty 240 / RM 10,800.00; B 750 / 33,750.00; C 532 / 23,940.00; Total qty 1,522; Amount 68,490.00. `quantity` = 1,522. |
| E2 | UNIT row "basin (COMMON BATH)": A all blank, B 250, C 266, rate 180.00. | A pair prints `-` / `-`; Total qty 516, Amount 92,880.00. |
| E3 | LEVEL 9 scope, headers LEVEL 9 (11 shoulders), LOBBY A (LEVEL 1) (4), LOBBY B (LEVEL 2) (4), BREAK TANK (none). Row "WC" rate 600.00: 7 in LEVEL 9 rooms, 3 in LOBBY A, 3 in LOBBY B. | Pairs LEVEL 9 7 / 4,200.00, LOBBY A 3 / 1,800.00, LOBBY B 3 / 1,800.00; BREAK TANK gets no pair (one column); Total qty 13, Amount 7,800.00. |
| E4 | GUARD HOUSE and RECYCLE & BIN, no columns (and every quotation already in the system). | Byte-for-byte today's screen, PDF and Excel; grand total = sum of all four scopes. |
| E5 | Angle valve on three UNIT rows (bath inlets, basin group, sink inlet). PO orders more than the three rows together. | #2097 qty-over compares with the SUM of the three rows. |
| E6 | Customer leaves a note on the sink row's TYPE C / KITCHEN cell ("needs 140", hint 140) and a note on the whole floor trap item. | Both appear on Customer feedback, open, with an amber mark in Lines; no total changes. The salesperson revises, types 140 in the cell, issues Rev B, ticks the first note Handled. |

## Edge cases

- A header whose shoulders are all deleted becomes a one-column header; the deleted shoulders' cells are dropped (the
  countdown said how many).
- A version issued with columns, then revised: columns + cells copied; editing columns in the draft never touches the
  issued version or the customer's link.
- A note on a cell whose column was later removed in a draft: the note stays and says "(column removed)" next to
  where it pointed.
- 375 px: grid scrolls inside its card, # / item pinned; no page-level horizontal scroll.
- Very wide scopes (LEVEL 9: 20 quantity columns + 3 pairs + 2 totals = 28 numeric columns): screen scrolls; PDF uses
  vertical headings and minimum widths (rule 16).

## What this touches that other PS lanes also touch

- #2097 PS-PROPOSAL-QUOTATION: `copy_line` + `make_quotation` version copy (add the two JSONB fields),
  `project_quotation_document_service.py`, PDF / Excel services, `models/projects.py`. No change to `qty_over_quotation`
  is needed any more (no per-unit scopes). Build after it merges.
- #2103 PS-SPEC-SHEET: reads line quantity only. Later nice-to-have: prefill its per-page "Area" from the shoulders
  where the line has a quantity. Not in this lane.
- #2094 QUOTE-COVER-DESIGN: shares the PDF service and the migration queue (one migration PR at a time).
- Sign page / amendments (QUOTE-CUSTOMER-AMEND): `quotation_amendment_service.py`, `QuotationSignScopes.tsx`.

## Data (smallest that keeps every reader working)

- `projects.quotation_versions.matrix_columns` JSONB NULL: `[{"key", "label", "cols": [{"key", "label"}]}]`.
  NULL or `[]` = no columns (today).
- `projects.quotation_lines.qty_cells` JSONB NULL: `{"<shoulder key, or header key for a one-column header>": "<decimal>"}`.
- `projects.quotation_amendment_request_rows`: `cell_key` VARCHAR(40) NULL, `note` TEXT NULL, `handled_at` TIMESTAMP
  NULL, `handled_by` FK users NULL (rule 22). The decision column is left in place, no longer written.
- `quantity` stays and is derived from the cells when columns exist (rule 6). The line field joins `LINE_FIELDS` and
  `copy_line`; the version field joins the revise and make-quotation copies. Issues point at versions, so nothing new
  to snapshot.
- One migration, three nullable columns, no backfill.

## Questions left

- Q6. The customer's feedback note may carry an optional hint (suggested quantity / price / remove), shown next to
  today's value. (a) keep the optional hints; (b) free text only. **Recommend (a)**: "140" next to "now 133" is faster
  to act on than reading it out of a sentence, and today's sign page already collects these values.
