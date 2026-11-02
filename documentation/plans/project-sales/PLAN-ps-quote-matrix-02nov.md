# PLAN: Quotation grid scopes (column headers x shoulders, qty per cell)

Status: Plan (card v2 + mock v2 out to the owner; code waits for #2097 PS-PROPOSAL-QUOTATION to merge). Track: full (L):
one migration (3 nullable columns), new editor behaviour on an existing screen, PDF + Excel + sign page, amendments.
Lane: PS-QUOTE-MATRIX, PR #2108. Card (rules R1-R22, examples, data): `CARD-ps-quote-matrix-02nov.md`.
UAC: `ps-quote-matrix-02nov-acceptance-criteria.md`. Mock: `mockups/quote-matrix.html`.

## Journey
A salesperson quoting a high-rise project types the developer's two-dimensional sheet straight into the quotation:
on the UNIT scope the column headers are the unit types and the shoulders are the areas; on the LEVEL 9 scope the
headers are levels and the shoulders are rooms. They punch a quantity into each cell, see per-column, per-header and
row totals at once, issue it, and the customer gets a PDF / Excel that looks like their own sheet. The customer can
suggest a different quantity for a cell or for the row. Every quotation that exists today is untouched.

## Slices (one branch, one PR)
1. **Data** (migration `pqm_0001_quote_matrix`, after #2097's `ppq_0001`): `quotation_versions.matrix_columns`
   JSONB NULL, `quotation_lines.qty_cells` JSONB NULL, `quotation_amendment_request_rows.cell_key` VARCHAR(40) NULL.
   Model + schema fields; `qty_cells` in `LINE_FIELDS`, `copy_line`; `matrix_columns` in revise and make-quotation
   version copies.
2. **BE engine** (one pure module, `app/services/quotation_matrix.py`): validate columns (keys unique, labels
   non-blank, <= 40 headers x 40 shoulders), validate cells against the version's columns (unknown key 422, negative
   422), derive `quantity` = sum(cells); first column added moves quantities in; last column removed sums them back;
   column delete drops cells. Called from `_write_line` and a new `PUT .../versions/{id}/columns`.
3. **FE editor**: Columns dialog; `QuotationLinesGrid` builds grouped columns from `matrix_columns`, cell inputs, pair
   and total columns, footer rows; paste from Excel.
4. **PDF + Excel**: matrix branch in `_scope_html` and `_write_scope`; no-columns path untouched.
5. **Sign page + amendments**: read-only grid, per-cell suggestion (`cell_key`), row-total split on accept (R21-R22).
6. Guide (`documentation/user-guides/project-sales-rep/work-a-project-quotation.md`), hand-test script.

## Tests (red first, per slice)
- pytest: engine rules (sum, pairs-not-stored, move-in, sum-back, delete drops, validation 422s); revise + make-quotation
  copy columns and cells; scope / grand totals unchanged for a no-columns scope (regression: existing PDF / Excel
  snapshot tests stay green unchanged); PDF has 2-row header + vertical class when wide; Excel merged header + SUM
  formulas; amendments: cell suggestion applies to the cell, row total on multi-cell line needs a split summing to it,
  both on one line refused, suggestion on a deleted column refused.
- vitest: grid column builder (pairs only for 2+ shoulders with 2+ headers), footer sums, paste parser.
- Browser pass (cloud): UNIT + LEVEL 9 typed in, PDF downloaded, sign page cell suggestion, 375 px.

## Not in this lane
Excel import (owner: no). Per-scope terms / REF suffix. Per-room reporting tables.
