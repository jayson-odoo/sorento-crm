# UAC: stock list bare model codes

Plan: PLAN-stock-list-bare-model-codes.md (r2, 17 Sep 2026)

## Reader + composer (S1)

- AC-R1: A 型号 cell merged over rows N..N+k fills `item_code` on every covered row (same
  header-anchored guard as 品名). A merge anchored on or above the header never fills.
- AC-R2: A covered row with stock and a merged 型号 no longer raises "no model number on a
  row with stock"; it parses with the anchor's model.
- AC-R3: Letter-led 型号: `item_code` = 型号 exactly as today, whatever 规格 / 商标 / 品名
  hold and whatever the word list holds. `SRTWC8357-RL-250` with 规格 `250` stays
  `SRTWC8357-RL-250`. Every existing reader test passes unchanged with a word list supplied.
- AC-R4: Bare 型号, every word known: `item_code` = composed code; `model_no` = raw 型号.
  `8613` / `250mm` / `SORENTO` / `连体马桶` -> `SRTWC8613-250`; `8613` / `横排180mm` ->
  `SRTWC8613-P-180`; `8066-PP` / `150mm` -> `SRTWC8066-PP-150`; `-7055` / blank / `SORENTO` /
  `盆` -> `SRTWB7055`; `8605-RL` / blank / `SORENTO` / `水箱` -> `SRTWCY8605-RL`;
  `1009` / `250mm` / `CABANA` / `分体马桶` -> `CWC1009-250`; `888` / `600*450*200mm` /
  `SORENTO` / `盆` -> `SRTWB888`.
- AC-R5: Bare 型号, a word unknown (商标 blank, 品名 unknown, or a CJK run in 型号 / 规格 with
  no row): `item_code` = raw join 型号 + 规格 + 商标 + 品名 (present parts, space-joined):
  `7609对冲 150mm 连体马桶`, `7604-RL高压 横排180mm CABANA 座头`. `model_no` = raw 型号.
- AC-R6: `parse_spec` (parametrized over every distinct 规格 value stored on the 0915 copy
  plus this file's): `250` -> (250, None, []); `180横排` and `横排180mm` -> (180, P, []);
  `250UF` -> (250, None, [UF]); `250-PP` -> (250, None, [PP]); `180A横排` -> (180, P, [A]);
  `250对冲` -> abort without a `对冲` row, (250, None, [<token>]) with one;
  `600*450*200mm` -> (None, None, []); `背部没有孔` -> abort; blank -> (None, None, []).
- AC-R7: After `apply`, the four `8613` rows are four `supplier_inventory` rows with their
  own quantities and codes; the SORENTO and CABANA `7604-RL高压` pedestal rows are two rows.
- AC-R8: `test_stock_list_xlsm_upload.py` and every merged-cells test stay green.

## Word list storage (S2)

- AC-W1: `canonical_fields("supplier_inventory_word")` returns `WORD_TOKENS`; the admin
  API accepts `POST {doc_type: supplier_inventory_word, field: SRT, alias: SORENTO}` (shared)
  and the same with `supplier_id`; rejects `field: XYZ` with the existing 422 and an unknown
  `supplier_id` with 422.
- AC-W2: Migration adds nullable `import_field_alias.supplier_id` (FK suppliers, cascade),
  replaces the unique triple with (doc_type, field, alias, supplier_id); inserts exactly the
  D7 rows with `supplier_id NULL`; downgrade removes rows and column; id <= 32 chars; single
  head. Existing `proforma_invoice` / `packing_list` rows untouched.
- AC-W3: `WordList.for_supplier(db, supplier_id)`: a supplier row for a word wins over the
  shared row; a word with only a shared row resolves; a word with neither is unknown.
  Lookup is case- and whitespace-insensitive on the alias (`S` and `s`, `SORENTO ` and
  `SORENTO`).
- AC-W4: The list endpoint returns `supplier_id` and `supplier_name` per row (no UUID shown
  in the UI, name only).

## Service (S3)

- AC-S1: `preview`, `validate`, `apply` build the word list for the chosen supplier and pass
  it to `read_workbook`; a bare-code file with the D7 seed binds `SRTWB7055` via rung 1 and
  writes no alias (exact match is not remembered, as today).
- AC-S2: A letter-led fixture (the existing service tests' rows) produces identical rows,
  summary and bindings with and without a word list in the database.
- AC-S3: `supplier_code_matcher.py` has no diff in the PR.
- AC-S4: On the 0915 copy (hand-measured, not CI): re-running `apply` for the JINBAICHUAN
  plan keeps 363 bound rows with identical product ids; ROYAL keeps 36.

## Frontend (S4)

- AC-F1: Import field aliases page lists a `Stock list words` doc type; its field select
  offers `WORD_TOKENS` labels; the form shows a clearable `Supplier` select for this doc type
  only; adding `对冲 -> SH` for DAFUYUAN succeeds and the list shows the row with the
  supplier name; a shared row shows a blank Supplier cell.
- AC-F2: `AttachmentPreviewModal` Open, item with `url: ''` and a `downloadUrl`: clicking
  calls `fetchBytes(item)` and `window.open(<blob url>, '_blank')`; no `<a href=/download>`
  is rendered for that item.
- AC-F3: Item with an `http` CDN url: Open stays a plain anchor to that url (unchanged).
- AC-F4: Fetch failure on Open: one non-sticky error toast, no navigation.
- AC-F5: Supplier codes tab renders a `Stock list words` link to
  `/system-management/import-field-aliases?doc_type=supplier_inventory_word`; the page opens
  on that doc type when the query param is present and on its default otherwise.

## Browser (S5)

- AC-B1: From the sidebar, Loading plan for DAFUYUAN, upload `SORENTO库存表20260914.xlsx`:
  the upload summary counts every stock row (no "no model number on a row with stock" for
  row 25); Supplier codes tab lists `SRTWC8613-P-180`, `SRTWC8613-150`, `SRTWC8613-200` as
  separate rows with 品名 · 商标 beside them.
- AC-B2: Lines tab shows the composed binds (at least `SRTWB7055`, `SRTWB888`, `SRTWCY8605`)
  with their quantities.
- AC-B3: Pick a product for `SRTWC8613-P-180` in the Supplier codes tab, re-upload the same
  file: the row is bound on the second upload without a pick.
- AC-B4: Re-upload the JINBAICHUAN 14/09 stock list on its plan: Lines and Supplier codes
  counts identical to before the change (AC-S4 in the UI).
- AC-B5: Open on the stock list attachment opens the sheet in a new tab, no JSON error page.
- AC-B6: System management > Import field aliases > Stock list words at 375px and 1280px:
  the seed rows list with a blank Supplier cell; add one DAFUYUAN row; it shows the supplier
  name.
