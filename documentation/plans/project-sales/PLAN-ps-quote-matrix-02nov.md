# PLAN: Quotation grid scopes (column headers x shoulders, qty per cell)

Status: Build, fix round 1 (mock v3 approved 2 Nov 00:05; built on #2097's branch, rebase after it merges). Track: full (L):
one migration (nullable columns only), new editor behaviour on an existing screen, PDF + Excel + sign page, amendments.
Lane: PS-QUOTE-MATRIX, PR #2108. Card (rules R1-R22, examples, data): `CARD-ps-quote-matrix-02nov.md`.
UAC: `ps-quote-matrix-02nov-acceptance-criteria.md`. Mock: `mockups/quote-matrix.html`.

## Journey
A salesperson quoting a high-rise project types the developer's two-dimensional sheet straight into the quotation:
on the UNIT scope the column headers are the unit types and the shoulders are the areas; on the LEVEL 9 scope the
headers are levels and the shoulders are rooms. They punch a quantity into each cell, see per-column, per-header and
row totals at once, issue it, and the customer gets a PDF / Excel that looks like their own sheet. The customer can
leave a feedback note on an item or a cell, which the salesperson reads and acts on freely. Every quotation that exists today is untouched.

## Slices (one branch, one PR)
1. **Data** (migration `pqm_0001_quote_matrix`, after #2097's `ppq_0001`): `quotation_versions.matrix_columns`
   JSONB NULL, `quotation_lines.qty_cells` JSONB NULL, `quotation_amendment_request_rows` + `cell_key`, `note`,
   `hint_text`, `handled_at`, `handled_by` (all NULL).
   Model + schema fields; `qty_cells` in `LINE_FIELDS`, `copy_line`; `matrix_columns` in revise and make-quotation
   version copies.
2. **BE engine** (one pure module, `app/services/quotation_matrix.py`): validate columns (keys unique, labels
   non-blank, <= 40 headers x 40 shoulders), validate cells against the version's columns (unknown key 422, negative
   422), derive `quantity` = sum(cells); first column added moves quantities in; last column removed sums them back;
   column delete drops cells. Called from `_write_line` and a new `PUT .../versions/{id}/columns`.
3. **FE editor**: `QuotationLinesGrid` keeps every existing column and builds grouped quantity columns from
   `matrix_columns`, cell inputs, pair and total columns, footer rows; column editing in the header itself (rename in
   place, drag, remove countdown, + column, + header, Copy columns from); paste from Excel.
4. **PDF + Excel**: matrix branch in `_scope_html` and `_write_scope`; no-columns path untouched.
5. **Sign page + feedback**: read-only grid; feedback notes per item or cell with optional hint; staff Customer
   feedback tab with Handled; Accept / Reject / Apply retired for every quotation (R19-R22).
6. Guide (`documentation/user-guides/project-sales-rep/work-a-project-quotation.md`), hand-test script.

## Tests (red first, per slice)
- pytest: engine rules (sum, pairs-not-stored, move-in, sum-back, delete drops, validation 422s); revise + make-quotation
  copy columns and cells; scope / grand totals unchanged for a no-columns scope (regression: existing PDF / Excel
  snapshot tests stay green unchanged); PDF has 2-row header + vertical class when wide; Excel merged header + SUM
  formulas; feedback: item and cell notes stored with hint, handled toggles who/when, no endpoint changes a line, legacy
  decided rows read as handled.
- vitest: grid column builder (pairs only for 2+ shoulders with 2+ headers), footer sums, paste parser.
- Browser pass (cloud): UNIT + LEVEL 9 typed in, PDF downloaded, sign page cell suggestion, 375 px.

## Not in this lane
Excel import (owner: no). Per-scope terms / REF suffix. Per-room reporting tables.

## Contract (Phase 2, agreed before code; tests are written against this)

### Data (migration `pqm_0001_quote_matrix`, down_revision `ppq_0001_proposal_quotation`)
- `projects.quotation_versions.matrix_columns` JSONB NULL.
- `projects.quotation_lines.qty_cells` JSONB NULL.
- `projects.quotation_amendment_request_rows`: add `cell_key` VARCHAR(40) NULL, `note` TEXT NULL, `hint_text`
  VARCHAR(200) NULL, `handled_at` TIMESTAMP NULL, `handled_by` VARCHAR(100) FK users ON DELETE SET NULL.
  CHECK on `field` widened to `('quantity','unit_price','remove','model_swap','note')`. Unique
  `uq_quotation_amendment_rows_line_field` replaced by a unique INDEX on
  `(request_id, line_id, field, COALESCE(cell_key, ''))`. Backfill: rows with `decision <> 'pending'` get
  `handled_at = COALESCE(decided_at, created_at)`, `handled_by = decided_by`. The partial unique index
  `uq_quotation_amendment_requests_open` is DROPPED (a customer may send feedback more than once). Downgrade reverses
  all of it (rows with the new fields kinds deleted first).

### Columns (engine: `app/services/quotation_matrix.py`, pure functions + one writer)
- Shape: `[{"key": str, "label": str, "cols": [{"key": str, "label": str}]}]`; `[]`/NULL = no columns.
- Keys match `^[a-z0-9][a-z0-9_-]{0,39}$`, unique across ALL headers and cols of the version. Labels trimmed,
  1..60 chars. Max 40 headers, max 60 cols per header, max 200 leaves.
- Leaves (the quantity columns), in order: for each header, its cols' keys, or the header's own key when it has none.
- Errors: 422 `quotation_columns_invalid` (message names the problem).
- `PUT /api/v1/projects/quotation-versions/{version_id}/columns` body `{"columns": [...]}` (EDIT permission,
  editable version only, same refusal as line writes). Returns `{"version": <version response>, "lines": [<line
  responses>]}`. Effects, in one transaction:
  - from none to some: each line's `quantity` moves into the FIRST leaf (`qty_cells = {first: quantity}`);
  - from some to none: `qty_cells = NULL`, `quantity` keeps its sum;
  - otherwise: cells under keys no longer leaves are dropped, `quantity` re-summed;
  - line totals and the version total recomputed (rate-only rules unchanged).
- `ProjectQuotationVersionResponse.matrix_columns: list` (default `[]`).

### Cells on a line
- `qty_cells: {leaf_key: number|string}` writable on create / update / bulk (`LINE_FIELDS`). Stored normalised:
  Decimal strings with 2 dp, zero and blank dropped, `{}` stored as NULL.
- Version WITH columns: unknown key 422 `quotation_cells_invalid`; negative or > 9,999,999.99 422 same code;
  `quantity` = sum of cells (0 when none) and any `quantity` in the payload is ignored.
- Version WITHOUT columns: `qty_cells` in the payload 422 `quotation_cells_invalid` unless empty/null; `quantity`
  as today.
- `ProjectQuotationLineResponse.qty_cells: dict` (default `{}`).
- `copy_line` copies `qty_cells`; `revise` and `make_quotation` copy `matrix_columns` to the new version.

### Totals derived for display (never stored)
- Row pair per header when the version has >= 2 headers and that header has >= 2 cols: qty = sum of its cells,
  amount = qty x unit_price (0 for rate-only).
- Footer: qty per leaf, qty + amount per pair header, scope total = version total.
- One helper `matrix_summary(columns, lines)` in the engine returns these, used by PDF, Excel and tests; the FE
  computes the same in `_shared/lib/quotationMatrix.ts`.

### PDF / Excel
- No columns: output unchanged (existing snapshot tests stay green).
- With columns: the QTY column is replaced by: one column per leaf under a 2-row header (header label spanning
  its leaves, leaf label below; a header with no cols spans 2 rows), then per pair header QTY + AMOUNT (RM),
  then TOTAL QTY; GRAND TOTAL stays last; footer rows TOTAL QTY (per leaf / per pair QTY / overall) and TOTAL
  (RM) (per pair AMOUNT); scope total row as today. PDF: header in `<thead>` (repeats), leaf headings get class
  `vert` when the scope has more than 12 leaves. Excel: header cells merged across a header's leaves, numbers
  as numbers, row TOTAL QTY / pair QTY / pair AMOUNT / GRAND TOTAL / footers as `=SUM(...)` formulas.

### Customer feedback (replaces Accept / Reject / Apply for every quotation)
- Public `POST /api/v1/public/quotation-sign/{token}/amendment-request` (URL kept; rate limit kept) body
  `{"items": [{"line_id", "cell_key"?, "kind": "note|quantity|unit_price|remove|model_swap", "value"?,
  "model"?, "note"?}], "note"?, "requester_name"?}`. One item = one row. Rules: line on this issue (422
  `quotation_amendment_line_unknown`); `cell_key` must be a leaf of that line's version (422
  `quotation_feedback_cell_unknown`) and only with kind `note` or `quantity`; `quantity` value 0..9,999,999.99
  (2 dp); `unit_price` value > 0; `remove` no value; `model_swap` needs `model` (1..200 chars), optional price in
  `value`; `note` kind needs a note; every item's note <= 1000 chars; at least one item or a top-level note
  (422 `quotation_feedback_empty`); duplicate (line, cell, kind) in one body 422
  `quotation_amendment_line_duplicate`. Refused on an accepted issue (409 `quotation_already_accepted`) or a
  superseded one (existing refusal). NOT refused because earlier feedback exists. Never blocks signing: the
  sign page's `blocked_reason` values `amendment_open` / `amendment_applied` are gone.
- Row stored: `field = kind`, `cell_key`, `value_from` = today's value (cell qty, line qty or price; NULL for
  note/remove/model_swap), `value_to` = value, `hint_text` = model, `note`.
- Staff `GET /api/v1/projects/{project_id}/quotation-documents/{document_id}/feedback` (READ permission):
  `{"open_count": int, "requests": [{"id", "issue_label", "submitted_at", "requester_name", "note", "rows": [{"id",
  "line_id", "scope_label", "line_description", "cell_key", "cell_label" ("<header> / <col>" or header label),
  "kind", "value_from", "value_to", "model", "note", "handled_at", "handled_by_name"}]}]}`, newest request first,
  rows in line order. `open_count` = rows with `handled_at IS NULL`.
- Staff `PATCH /api/v1/projects/{project_id}/quotation-documents/{document_id}/feedback/{row_id}` body
  `{"handled": bool}` (EDIT permission) sets / clears `handled_at` + `handled_by`. Row of another document 404.
- Retired: `decide_row`, `apply_request` and their routes (`.../amendment-requests/{id}/rows/{row_id}`,
  `.../amendment-requests/{id}/apply`), the `amendment-request` staff GET (replaced by `/feedback`), and the
  issue gate that refused Issue / signing while a request was open.
- Sign page payload: each scope carries `matrix_columns`, each line `qty_cells`.
