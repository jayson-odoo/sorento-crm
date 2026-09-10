# UAC: Text glossary

Plan: `PLAN-text-glossary.md`. Locale is `en` throughout slice 1. The migration seeds NOTHING
(R6): every test inserts the glossary rows it needs (`连体马桶 -> One-piece toilet`, `盆 -> Basin`)
through `text_glossary_service.upsert` or a direct model insert in its own setup.

## A. Glossary service (pytest, `tests/scm/test_text_glossary.py`)

- **A1** `normalize("  连体  马桶 ")` returns `"连体 马桶"`; `normalize("")` and `normalize(None)`
  return `""`.
- **A2** `lookup` with `{"连体马桶", "盆", "BASIN"}` after the test inserts the two rows returns
  `{"连体马桶": "One-piece toilet", "盆": "Basin"}`; `"BASIN"` absent (no row). One SQL
  statement (assert with the statement counter fixture or `db.execute` spy).
- **A3** `lookup` is case-insensitive on Latin text: a row `("Basin tap", en, "...")` is
  found by `"BASIN TAP"` and the result is keyed by the caller's spelling `"BASIN TAP"`.
- **A4** `upsert(source_text="盆", translation="Wash basin")` overwrites the existing row (same
  id, `translation='Wash basin'`); no second row for `盆`.
- **A5** `upsert` with blank `source_text` or blank `translation` raises `AppException(422)`
  naming the field; nothing written.
- **A6** `upsert` re-binds: two PIs (same company) each with a line `description='盆'` and
  one packing row `description='盆'`, plus one line `description='连体马桶'`. After
  `upsert("盆", "Basin")` every `盆` line and row has `description_en='Basin'`; the
  `连体马桶` line is untouched; return value is `{"rebound": {"lines": 2, "packing_rows": 2}}`.
- **A7** `forget(id)` deletes the row and sets `description_en` NULL on every line/row whose
  `description` matches, leaving other translations alone. Non-uuid id and unknown id raise
  `AppException(404)`.
- **A8** `upsert` with `locale='ms'` writes the glossary row and re-binds NOTHING
  (`description_en` unchanged); `lookup(..., locale='ms')` finds it.
- **A9** The migration creates `text_glossary` EMPTY (R6); `alembic downgrade -1` then
  `upgrade head` leaves the table, both `description_en` columns and the two permissions in
  place and the table still empty.

## B. Fill on write (pytest, same file)

- **B1** With the two rows inserted, `replace_packing_rows` with three `PackingLine`s
  (`product_name` = `盆`, `连体马桶`, `Unknown thing`) writes rows with `description_en` =
  `Basin`, `One-piece toilet`, `NULL`. A plain-English `product_name` (`BASIN`) with no row
  also lands NULL (R7: no auto-mirror).
- **B2** PI apply (Jiexia fixture with one line's description patched to `盆` in the parsed
  payload, or a synthetic apply through the same service function) writes
  `ProformaInvoiceLine.description_en='Basin'`.
- **B3** Line update (`:2779` path) that changes `description` from `盆` to `连体马桶`
  re-looks-up and stores `One-piece toilet`; a change to an unknown text stores NULL.
- **B4** `serialize` output: each line dict and each packing row dict carries
  `description_en` (present even when NULL).
- **B5** A translation added AFTER upload does not create a revision entry: the revision diff
  for a PI whose lines gained `description_en` reports no `changed` lines.

## C. Downstream (pytest, same file)

- **C1** Convert a PI whose line has `description='盆'`, `description_en='Basin'`: the
  `InboundShipmentLine.description` is `Basin`; a line with `description_en` NULL copies
  `description` unchanged.
- **C2** The converted `PackingListLine.description` is `Basin` for the same line.
- **C3** `to_xlsx` container workbook prints `Basin` in the description cell for that line.
- **C4** An unmatched/dismissed packing row with `description='盆'`, `description_en='Basin'`
  and no code lands `Basin` in the shipment's unplaced-rows note, not `盆`.

## D. Routes (pytest, `tests/system/test_text_glossary_api.py` + scm route in the same file)

- **D1** `GET /system/text-glossary` needs `system.text_glossary.view`: 403 without, list
  with; `?q=basin` matches on translation, `?q=盆` on source text.
- **D2** `PUT /system/text-glossary` needs `.edit`; body `{source_text, translation}` ->
  200 with the row and `rebound`; a second PUT for the same text overwrites (200, same id).
- **D3** `PUT` with blank translation -> 422 naming `translation`; over-long locale (9 chars)
  -> 422.
- **D4** `DELETE /system/text-glossary/{id}` -> 204; non-uuid -> 404; deferred action
  `text_glossary.forget` is registered in `record_actions` and commits the delete when its
  window lapses (test through the existing deferred-action harness the
  `import_field_alias.forget` test uses).
- **D5** `PUT /scm/proforma-invoices/{id}/translations` needs `scm.proforma_invoice.upload`;
  unknown invoice id -> 404; success returns the row + `rebound` and the invoice detail read
  back afterwards shows `description_en` on every affected line and packing row.
- **D6** `system.text_glossary.view/.edit` exist in `permission_registry` and the migration
  grants both to `admin` and `superadmin`.

## E. Frontend (vitest + agent-browser, sidebar clicks from `/`)

- **E1** Packing tab shows `Description (EN)` beside `Description`; rows whose word is in the
  glossary show the English, others a dash (including an already-English description, R7). Vitest: column present, values rendered, dash for null.
- **E2** Click the dash on an unmatched row whose description is `连体马桶`, type
  `One-piece toilet`, Enter: cell shows the English, toast names the count, the OTHER row
  with the same description on the same tab updates without reload. Escape cancels with no
  request. Vitest covers Enter/Escape/blur.
- **E3** Lines tab shows the same column in view mode and in edit mode, in the same position;
  editing it does not dirty the line form.
- **E4** System Management > Text Glossary, beside Import Column Mappings (menu entry
  visible with `.view`): list shows Source text / Translation / Added by / Added, NO locale
  column (R9); Add writes a row (no locale field); editing an existing row's translation overwrites
  it; Delete starts the reversible countdown, Cancel restores, lapse removes the row.
- **E5** Usable and non-clipped at 375 and 1280 on both the Packing tab and the System page.
- **E6** No UUID visible anywhere on either surface; no on-screen explanation text.
