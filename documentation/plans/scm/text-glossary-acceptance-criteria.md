# UAC: Text glossary

Plan: `PLAN-text-glossary.md`. Reuses `translation_memory` + `translation_service` (R11).
Nothing is seeded (R6): every test inserts the memory rows it needs through
`translation_service.remember` (or a direct `TranslationMemory` insert) in its own setup,
`source_lang='zh'`, `target_lang='en'`. Tests that must not hit the model patch
`translation_service._ai_fill` to return `{}` (the existing
`tests/scm/test_supplier_document_translations.py` shows the pattern).

## A. Fill and re-bind (pytest, `tests/scm/test_description_translation.py`)

- **A1** `description_translation.fill(db, rows)` over three fresh `ProformaInvoicePackingLine`
  objects (`description` = `盆`, `连体马桶`, `BASIN`) with memory rows for the first two sets
  `description_en` = `Basin`, `One-piece toilet`, `None`. `BASIN` never reaches `_ai_fill`
  (R7). One `translate` call for the batch (spy on `translation_service.translate`).
- **A2** `fill` with the PROVIDER stubbed (`get_provider` / `provider.chat` returning the
  JSON `{"translations": [{"source": "连体马桶", "target": "One-piece toilet"}]}`) so
  `_ai_fill_chunk` runs for real: `description_en` comes from the AI answer AND the memory now
  holds an `ai` row for it. No helper in `description_translation` writes that row.
- **A3** `rebind(db, "盆", "Basin")`: two PIs each with a line `description='盆'` and one
  packing row `description=' 盆 '` (padded), plus one line `description='连体马桶'`. Every
  `盆` line and row has `description_en='Basin'`; the `连体马桶` line is untouched; returns
  `{"lines": 2, "packing_rows": 2}`.
- **A4** `rebind(db, "盆", None)` sets `description_en` NULL on the same rows only.
- **A5** `translation_service.remember(db, [{"source_text": "盆", "target_text": "Basin"}])`
  re-binds (rows from A3's shape carry `Basin` afterwards) and returns
  `{"written": 1, "rebound": {"lines": 2, "packing_rows": 2}}`.
- **A6** `translation_service.update_target_text(db, id, "Wash basin")` re-binds every row
  to `Wash basin`; `delete_memory(db, id)` re-binds them to NULL.
- **A7** A memory row for `盆` with `target_lang='ms'` never touches `description_en` on
  `remember` / `update_target_text` / `delete_memory` (R5).

## B. Fill on write (pytest, same file)

- **B1** `replace_packing_rows` with `PackingLine`s (`product_name` = `盆`, `连体马桶`,
  `Unknown thing`, `BASIN`), memory holding the first two, `_ai_fill` -> `{}`: rows land
  `Basin`, `One-piece toilet`, `NULL`, `NULL`.
- **B2** PI apply through the real service function (Jiexia fixture, or a synthetic parsed
  payload) with a memory row for one line's description writes
  `ProformaInvoiceLine.description_en` for that line and NULL for the rest.
- **B3** Line update (`:2779` path) that changes `description` from `盆` to `连体马桶`
  re-fills and stores `One-piece toilet`; a change to an unknown text stores NULL; a save that
  leaves `description` unchanged does NOT call `translate` for that line (spy).
- **B4** `serialize` output: each line dict and each packing row dict carries
  `description_en` (present even when NULL).
- **B5** A translation added AFTER upload does not create a revision entry: the revision diff
  for a PI whose lines gained `description_en` reports no `changed` lines.
- **B6** Migration 510 backfill: a line and a packing row with `description='盆'` written
  BEFORE the migration, and a memory row for `盆`, carry `description_en='Basin'` after
  `alembic upgrade head`; `downgrade -1` drops both columns and leaves `translation_memory`
  alone.

## C. Downstream (pytest, same file)

- **C1** Convert a PI whose line has `description='盆'`, `description_en='Basin'`: the
  `InboundShipmentLine.description` is `Basin`; a line with `description_en` NULL copies
  `description` unchanged.
- **C2** The converted packing list line (`InboundShipmentLine.description`, the packing list's line model) is `Basin` for the same line via the OTHER copy site (`:1802` grouping), not only C1's.
- **C3** `to_xlsx` container workbook prints `Basin` in the description cell for that line.
- **C4** An unmatched/dismissed packing row with `description='盆'`, `description_en='Basin'`
  and no code lands `Basin` in the shipment's unplaced-rows note, not `盆`.

## D. Routes (pytest, same file)

- **D1** `PUT /scm/proforma-invoices/{id}/translations` needs `scm.proforma_invoice.upload`
  (403 without); unknown or non-uuid invoice id -> 404.
- **D2** Success body `{source_text: "盆", target_text: "Basin"}` -> 200 with
  `{source_text, target_text, source: "manual", rebound: {lines, packing_rows}}`; the
  invoice detail read back afterwards shows `description_en='Basin'` on every affected line
  and packing row of THIS and of another PI with the same text.
- **D3** Blank or whitespace-only `target_text` or `source_text` -> 422 naming the field; nothing
  written. `source_text` over 500 chars or `target_text` over 1000 -> 422.
- **D6** `source_text` that matches no `description` on that invoice's lines or packing rows ->
  422 naming `source_text`; nothing written to the memory.
- **D7** Company scoping: company A's PUT re-binds A's rows and leaves company B's row with the
  identical description untouched (`set_company_scope` to A for the call, read B's row after).
- **D8** `to_xlsx` writes a description cell whose text starts with `=` as a string cell (no
  formula), for both `description` and `description_en`.
- **D9** `POST /scm/supplier-documents/apply` with 201 `translations` pairs -> 422; 200 pairs
  accepted.
- **D4** A second PUT for the same text overwrites (memory row count unchanged, `manual`),
  including over an existing `ai` row.
- **D5** `PUT /system/translations/{id}` (existing route) and the deferred
  `translation_memory.delete` action, when they lapse, re-bind the rows (A6 through the
  routes; the delete test runs through the existing deferred-action harness).

## E. Frontend (vitest + agent-browser, sidebar clicks from `/`)

- **E1** Packing tab shows `Description (EN)` beside `Description`; rows whose word is in
  the memory show the English, others a dash (including an already-English description,
  R7). Vitest: column present, values rendered, dash for null.
- **E2** The editable dash shows a rest-state affordance (dashed underline, `title`). Click the dash on an unmatched row whose description is `连体马桶`, type
  `One-piece toilet`, Enter: cell shows the English, toast names the count, the OTHER row
  with the same description on the same tab updates without reload. Escape cancels with no
  request. Vitest covers Enter/Escape/blur and the `extractApiError` path.
- **E3** Lines tab shows the same column in view mode and in edit mode, in the same position;
  editing it does not dirty the line form.
- **E4** System Management > Translations (existing page) lists the word typed in E2 with
  source `manual`; editing its English there changes the PI's cell on next load; NO
  "Text Glossary" entry exists in the sidebar (R8/R11).
- **E5** Usable and non-clipped at 375 and 1280 on the Packing tab and the Lines tab.
- **E6** No UUID visible anywhere; no on-screen explanation text.
