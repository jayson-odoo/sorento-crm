# PLAN: inline import column mapper, remembered per supplier

Status: GRILLED 24 Sep 2026 (R1-R5 + G1-G5 taken); lane opening via /feature.
UAC: `import-column-mapper-24sep-acceptance-criteria.md`.
Track: full `/feature` (two dialogs, one migration-free schema reuse, resolver change).

## What the owner asked (24 Sep 2026, four sample files + Respond.io mapper screenshot)

Supplier files (proforma invoice, packing list, stock list / loading plan) arrive in too
many layouts. Today every new layout means telling the admin to add rows on System >
Configuration > Import Column Mappings, on a separate page, before the upload works.
Two asks:

1. A header written on two lines in Excel (`件数` over `（件）`) cannot be mapped.
2. Map columns INSIDE the upload flow, like the Respond.io contact importer: sample data |
   header | Map to field. Save remembers the layout; next upload of the same layout is
   auto-mapped and the user only double-checks.

Samples: `sorento装箱单20260922（1）.xlsx` (DAFUYUAN PI), `FSCU8706420.xlsx` and
`OOLU9610547.xlsx` (NEW YANGGANG PI), `吕生2026-09-21更新库存(1).xlsx` (NEW YANGGANG stock
list). Copies under `sorento_crm_backend/tests/fixtures/scm/import_mapper/` (coder copies
them in; they are the test fixtures).

## Measured (24 Sep, main, local prod copy)

- `normalize_header` (`app/services/import_alias_service.py:27-40`) already folds newlines,
  full-width brackets and spaces: `件数\n（件）` -> `件数件`. Ask 1 is NOT a normaliser bug.
  The admin typed `件数` (Excel shows only line 1) -> key `件数` -> never matches. An alias
  typed `件数（件）` matches today. The mapper removes the typing entirely, so this ask is
  closed by ask 2 plus showing the whole header text in the grid.
- The header ROW is recognised only when every required field already resolves
  (`proforma_invoice_reader.py:505`, required `item_code, qty, unit_price`;
  `packing_list_reader.py:311`; `supplier_inventory_reader.py:147-179` needs `item_code`).
  No aliases -> no header row -> `unmapped_headers []` -> the existing "Map to..." chip
  (`SupplierDocumentsUploadDialog.tsx:762-840`) never renders for exactly the files that
  need it. All three PI samples return `missing_columns ['qty']`, `unmapped_headers []`.
- `AliasResolver.for_doc_type` loads every row for the doc type and ignores `supplier_id`
  (`import_alias_service.py:60-78`). `import_field_alias.supplier_id` already exists
  (migration `ifa_supplier_word_col.py`, NULL = shared) and is used only by
  `supplier_inventory_word`. No new table is needed.
- Same header, different meaning per supplier: NEW YANGGANG `件数（件）` = cartons,
  `总数量（个）` = qty. Other suppliers' `件数` = qty. A shared alias table cannot hold both;
  a supplier-scoped row can.
- `canonical_fields()` returns `[]` for `supplier_inventory` (`import_alias_service.py:
  139-171`), so the stock-list doc type cannot be mapped through the API at all (POST 422).
  Also leaks internal dataclass names (`row_number`, `index`, `header_row`, `lines`) into
  the field list for the two doc types it does serve.
- Alias-free header-row heuristic verified on all four samples: first row with >= 5 text
  cells followed within 2 rows by a row with >= 3 numeric cells -> rows 14 / 15 / 15 / 2,
  data row 16 / 16 / 16 / 3.
- Blank-header columns: `外箱/木托尺寸` is a merged header `G15:I15` (NEW YANGGANG) with
  L / W / H values in G, H, I and no text in H, I. DAFUYUAN has a merged `箱子 CTN SIZE
  (CM)` `N14:P14` with a SECOND header row `L (长) / W (宽) / H (高)` at row 15.
  `packing_list_reader._with_carton_dims` (line 283) already splices that second row for
  Kailu; the PI and stock-list readers do not.
- Both dialogs already run Test before Confirm via `useTwoStepUpload`
  (`scm/reorder/hooks/useTwoStepUpload.ts`): Plan a container (`scm/loading-plan/
  components/PlanContainerDialog.tsx`, stock list `POST /scm/supplier-inventory/preview`,
  PI `POST /scm/proforma-invoices/preview`) and Upload supplier documents
  (`scm/proforma-invoices/components/SupplierDocumentsUploadDialog.tsx`,
  `POST /scm/supplier-documents/preview`, multi-file). Every reader takes an injectable
  `resolver` (`read_workbook(file_data, resolver=None, *, db=None)`).

## Rulings (owner, 24 Sep 2026)

- R1 Memory key = supplier + doc type. No header-signature fingerprint. Trigger to build
  one: a supplier sends two templates where the SAME header text means different fields.
- R2 Anyone who can upload saves the layout (supplier-scoped rows). Shared rows stay on
  the admin page under `system.import_field_aliases.edit`.
- R3 The mapping step is collapsed when every column of the file is already known for
  this supplier, expanded when any column is not. "Known" includes columns the user chose
  to Ignore, so `序号` / `图片` do not expand it forever: Ignore is saved as a row with the
  reserved field `ignore`.
- R4 One shared `ImportColumnMapper` component, used by both dialogs, reusable by any
  later upload.
- R5 Two sample values per column (first two non-blank data cells), since the first data
  row often has that cell blank (DAFUYUAN `规格` row 16).

## Grill rulings (owner, 24 Sep 2026)

- G1 Test = save mapping + run preview in one click; a later Cancel keeps the saved rows
  (re-map replaces them).
- G2 Ignore is a saved row (`field = ignore`); admin page lists them under "Ignored".
- G3 Header-row guess may be wrong; that is fine. The grid shows "Header row N" with a
  stepper; when no row satisfies the heuristic the grid says so and the stepper starts at
  row 1. No click-the-row preview.
- G4 Combined PI + packing-list file: ONE mapper section per file; Save writes the same
  rows under BOTH doc types (same sheet, same header, same meaning). Field list shown =
  union of both doc types' fields; a field only one doc type reads is saved for that one.
- G5 The "Map to..." chip in Upload supplier documents is retired.

## Design

Simplest thing: the saved layout IS supplier-scoped `import_field_alias` rows. The
resolver prefers a supplier row over a shared row. The mapping grid is a thin UI over
`{header, samples, field}` triples that the server computes.

### Backend

B1 `AliasResolver.for_supplier(db, doc_type, supplier_id)` - loads shared rows plus this
supplier's rows; a supplier row wins over a shared row on the same normalised key; among
supplier rows first wins as today. `for_doc_type` unchanged (callers with no supplier).
Reserved field `ignore`: resolves to nothing at read time (`field_for_header` returns
None) but counts as known for `unmapped_headers`.

B2 `app/services/scm/header_probe.py` (new, alias-free):
`probe(file_data) -> HeaderProbe{header_row, columns:[{position, header, samples[<=2]}]}`.
Header row = first row with >= 5 text cells followed within 2 rows by a row with >= 3
numeric cells; `header_row` overridable by the caller. Column header text = the cell
text; for a blank cell under a merged header range the text is `<merged parent> [n]`
(`外箱/木托尺寸 [2]`, `[3]`); when the row after the header row has text only under merged
parents (DAFUYUAN), the child is spliced: `箱子 CTN SIZE (CM) L (长)`. Uses `sheet_rows`
plus openpyxl merged ranges. Samples = first two non-blank cells below the header in that
column, as strings.

B3 The three readers accept the probe's synthesised header texts: the header map is built
from the probe's column texts instead of the raw row (`_header_map` takes an optional
`header_texts: list[str]`), so `外箱/木托尺寸 [2]` resolves like any other header. The
`_is_header` required-field gate stays for files with no probe (legacy callers).

B4 `POST /api/v1/scm/import-mapping/probe` (multipart `file`, `supplier_id`, `doc_type`,
optional `header_row`) -> `{header_row, columns:[{position, header, samples, field,
source: supplier|shared|none, required}], required_fields, missing_required, fields:
[{field,label}]}`. `field` is the resolver's answer; `source` says which row answered.
Permission: the doc type's own upload permission (same guard as its preview endpoint).

B5 `POST /api/v1/scm/import-mapping/save` `{supplier_id, doc_type, mappings:[{header,
field}]}` - upserts supplier-scoped rows (`ON CONFLICT (doc_type, field, alias) DO
NOTHING`, then delete this supplier's other rows for the same normalised header so a
re-map replaces, not accumulates). `field = "ignore"` allowed. Validates fields via
`canonical_fields`. Permission as B4.

B6 The three preview / apply endpoints accept optional `header_row` and build the
resolver with `for_supplier`. `supplier-documents/preview` (multi-file) does the same per
file. `unmapped_headers` is filled from the probe's header row even when required fields
are missing (today it is empty in that case).

B7 `canonical_fields`: serve `supplier_inventory` (`InventoryRow` dataclass); exclude
internal names (`row_number`, `index`, `header_row`, `lines`, `problems`) via an explicit
deny set on the dataclass fields. Required fields per doc type exported from the readers
(`REQUIRED_COLUMNS`) so B4 can flag them.

### Frontend

F1 `components/common/ImportColumnMapper.tsx` (shared, R4). Props: `probe` (B4 result),
`fields`, `onChange(mappings)`, `onHeaderRowChange(n)`, `busy`. Renders: header-row
stepper ("Header row 15"), then one row per column: samples (two values, truncated,
`title`) | header text as-is, line breaks kept | `SearchableSelect` of fields, clearable,
plus an "Ignore" entry, required fields marked, unresolved required rows highlighted.
Collapsed summary variant: "18 of 18 columns mapped from saved layout" + "Review" toggle;
auto-expanded per R3. 375px: samples stack under the header; 1280px: three columns.

F2 `PlanContainerDialog`: after a file lands (stock list or PI), call probe; render the
mapper between the file and the footer; Test disabled while any required field is
unresolved; Test / Confirm send `header_row`; Save mappings (B5) fires as part of Test,
so Test = save + preview, one click. No separate Save button.

F3 `SupplierDocumentsUploadDialog`: same, one mapper per file (file name as the section
title); the per-file `kind` (PI / packing list / combined) picks the doc type; `combined`
probes both doc types (two mapper sections). The `UnmappedHeaderChip` is retired (the
mapper replaces it).

F4 Admin page unchanged except: supplier chip already renders for supplier rows; `ignore`
rows render under a synthetic "Ignored" field group so they can be deleted.

### Out of scope (named, not built)

- Header-signature fingerprint (R1 trigger above).
- Promoting a supplier row to shared from the mapper.
- Outstanding SO/PO, customer, reorder-level uploads (not supplier files; row-1 headers).

## Tests (captain's list; tester writes red first)

Backend (`tests/scm/test_import_column_mapper.py`, private clone via `_pg_fixture`):
- T1 probe on each of the four fixtures returns the measured header row and data row.
- T2 probe synthesises `外箱/木托尺寸 [2]` / `[3]` (NEW YANGGANG) and splices `箱子 CTN SIZE
  (CM) L (长)` (DAFUYUAN); samples are the first two non-blank cells.
- T3 `for_supplier`: supplier row beats shared row on the same key; another supplier's row
  is invisible; `ignore` resolves to None and is "known".
- T4 save upserts, replaces a re-mapped header for the same supplier, rejects an unknown
  field, accepts `ignore`, refuses a supplier the caller's company cannot see.
- T5 PI preview of FSCU8706420 with a saved NEW YANGGANG layout reads 3 lines, qty from
  `总数量（个）`, cartons from `件数（件）`, unit price from `单价（元）`; without the layout
  `missing_required` names qty and `unmapped_headers` is NOT empty.
- T6 stock-list preview of 吕生 with a saved layout reads 38 rows; `canonical_fields
  ("supplier_inventory")` is non-empty and contains no internal names.
- T7 probe `header_row` override moves the header.

Frontend (vitest):
- V1 mapper renders samples, header with line break, select per column; required
  unresolved rows flagged; Ignore option present.
- V2 collapsed when every column has a field or ignore; expanded when one does not.
- V3 PlanContainerDialog: Test disabled until required resolved; Test posts save then
  preview with `header_row`.
- V4 SupplierDocumentsUploadDialog: one mapper per file; chip gone.

Browser (agent-browser, sidebar nav, 375 + 1280): upload FSCU8706420 as NEW YANGGANG ->
map -> Test -> Confirm; re-open, upload OOLU9610547 -> mapper collapsed "mapped from saved
layout" -> Test -> Confirm; upload 吕生 via Plan a container stock list -> same.

## Lanes

One lane, one PR. Slices in order: B1+B7 (resolver + fields), B2+B3 (probe + readers),
B4+B5+B6 (endpoints), F1 (mapper, against a mocked probe), F2+F3+F4, guide.
