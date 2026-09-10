# PLAN: Text glossary - English for the supplier's own wording on PI lines and packing rows

Status: aligned, building (2026-09-10; revised same day after Phase 1 found the existing translation memory)
Domain: scm
UAC: `text-glossary-acceptance-criteria.md`
Lane: `feat/text-glossary`, branched off `main` after #793 (PI-first) merged 2026-09-10.
Alembic parent: `509_merge_508_summary_and_excl_wh`.
Tickets: #811 (S1 backend), #812 (S2 frontend).

## Journey

Jayson uploads Jinbaichuan's PI + packing list. The Description column reads `连体马桶`
and `盆`. Rows 1, 2 and 5 carry no code at all, so Match-to-product cannot name them. The
customs broker, the shipment grid and the container workbook all need English.

After this lane: the Packing tab and the Lines tab carry a second column, **Description
(EN)**. A word the translation memory already knows (from the upload preview's AI fill or
an earlier correction) is there the moment the upload lands. A word it does not know shows a
dash. Jayson clicks the cell, types `One-piece toilet`, presses Enter. Every row on file that
says `连体马桶` (this PI, every other PI, every packing row) now reads `One-piece toilet` in
that column, and every later upload lands already translated. The converted shipment line,
the packing list and the container workbook print the English. System > Translations (the
page that already exists) lists every word so an admin can correct or forget one, and a
correction there reaches every row too.

## Rulings

| # | Ruling | Consequence |
|---|--------|-------------|
| R1 | English shows in a SEPARATE column, `Description (EN)`; `Description` stays the supplier's own text | No coalesce on the PI screens; both columns serialised |
| R2 | Learning = inline edit on the row (Packing tab AND Lines tab) + an admin page | One write path (`translation_service.remember`) behind both |
| R3 | Slice 1 = `description` on `proforma_invoice_line` and `proforma_invoice_packing_line` only | `material`, `remark`, and the other readers are named triggers, not built |
| R4 | English flows downstream wherever description is COPIED off a PI row | Shipment line, packing list line, container workbook, shipment notes print `description_en or description`; the PI rows keep both |
| R5 | Glossary is the multilingual seed, not a UI i18n framework | `translation_memory` already carries `source_lang` / `target_lang`; the row cache column is `description_en` until a second language is asked for |
| R6 | NO seed rows (owner, 10 Sep) | Nothing is seeded; the operator types, or the preview's AI fill answers |
| R7 | An already-English description shows a dash, editable, no auto-mirror | Matches `translation_service._has_source_script`: no CJK, no model call, no row |
| R8 | The admin page is System Management > **Translations**, which already exists beside Import Column Mappings | NO new page. Phase 1's `system-management/text-glossary/` is deleted |
| R9 | Locale stays hidden in slice 1 | The existing page already shows `source_lang`/`target_lang`; nothing added |
| R10 | Inline edit gated by `scm.proforma_invoice.upload`, same as Match/Dismiss | The person handling the PI names the word; the admin page stays `system.translations.edit` |
| R11 | **Reuse `translation_memory` + `translation_service`. No `text_glossary` table, no new permissions, no new admin routes** (PRINCIPLES "check whether it already exists"; found by the Phase 1 coder) | The lane adds the missing half only: persist the English on the rows, re-bind on every memory write, show it, carry it downstream |

## What exists (measured, 10 Sep)

| Claim | Evidence |
|-------|----------|
| Translation memory table, tenant-wide, `(source_text, source_lang, target_lang)` unique, `source` = `manual` / `ai`, `hit_count` | `app/models/translation_memory.py`, migration `484_translation_memory.py` (purchasing consolidation lane C, R15/R16) |
| `translate(db, texts)` = memory first, batched AI fill for CJK misses written back as `ai`, `{original: TranslationHit(text, source)}`; never raises; non-CJK text never asks the model | `app/services/translation_service.py:88-140`, `_has_source_script` at `:54` |
| `remember(db, pairs, user_id)` = manual upsert, overwrites `ai`; `update_target_text`, `delete_memory` for the admin page | `translation_service.py:320-365, :464-481` |
| Upload preview shows "Translations - English beside the Chinese" with an editable input per phrase; edits are sent on apply and written FIRST via `remember` | `SupplierDocumentsUploadDialog.tsx:668-680`, `supplier_document_service.py:735-749`; preview translates UNMATCHED descriptions, matched-line remarks, block notes, footer (`_translate_preview_texts`, `:262-291`) |
| **Nothing persists the English at apply**: `description_en` exists only in the preview payload (`supplier_document_service.py:236`); PI lines and packing rows store `description` verbatim (`proforma_invoice_service.py:1040`, `:2779`; `proforma_invoice_packing_service.py:103`) | `grep description_en app/services/scm/proforma_invoice*.py` = 0 hits. This is why PI-2609-008 shows raw Chinese |
| Admin page System Management > Translations: DataGrid, inline `target_text` edit (`PUT /system/translations/{id}`), delete via deferred action `translation_memory.delete` (`record_actions.py:929`), perms `system.translations.view/.edit` | `app/api/v1/system/translations.py`, FE `system-management/translations/`, menu `config/menu.config.tsx:914` and `:2137` |
| Rendered raw | `ProformaInvoicePackingTab.tsx:242-251`; Lines grid in `ProformaInvoiceDetail.tsx:617-632` |
| The "re-bind rows on file after a ruling" mechanism | `supplier_code_alias_service._rebind` (stock rows, PI lines, packing rows via `rebind_packing_rows`) |
| Downstream copies of description | `proforma_invoice_service.py:1729` (unplaced rows into shipment notes), `:1790` and `:1906` (shipment grouping), `:2054` (`InboundShipmentLine.description`), `to_xlsx` (`:2193`), `PackingListLine.description` (`procurement.py:369`) |
| Serialisers | `proforma_invoice_service.serialize` (`:3015`; line dict `:3192`, packing row dict `:3295`) |
| Permission gating row rulings on the PI page | FE `ADJUST_PERMISSION = 'scm.proforma_invoice.upload'` (`ProformaInvoiceDetail.tsx:83`); BE `_UPLOAD` (`proforma_invoices.py:40`) |
| Existing tests | `tests/scm/test_supplier_document_translations.py` |
| Phase 1 (done, commit `4f0358bd7`) | `DescriptionEnCell.tsx`, `proformaInvoiceTranslationService.ts` (mock), `useProformaInvoiceTranslation.ts`, columns on both tabs, types. Plus a duplicate `system-management/text-glossary/` page and menu entry that R11 deletes |

## Design

### Migration `510_pi_description_en`

`ALTER TABLE proforma_invoice_line ADD COLUMN description_en TEXT NULL`, same on
`proforma_invoice_packing_line`. Nothing else: no table, no permissions, no seed. Downgrade
drops the two columns.

Backfill in the same migration, so rows already on file (PI-2609-001..008 on prod) get what
the memory already knows without a re-upload:

```sql
UPDATE proforma_invoice_line l SET description_en = m.target_text
FROM translation_memory m
WHERE m.source_lang = 'zh' AND m.target_lang = 'en'
  AND regexp_replace(btrim(l.description), '\s+', ' ', 'g') = m.source_text;
-- same for proforma_invoice_packing_line
```

### Service `app/services/scm/description_translation.py` (new, small)

The scm-side half. `translation_service` stays generic and knows nothing about PI rows.

- `fill(db, rows, *, attr="description", target="description_en")`: one
  `translation_service.translate` call over every non-empty `description` in `rows`, sets
  `description_en` to the hit text (or None). Called from the two write paths below. AI fill
  for CJK misses is the existing `translate` behaviour (the preview already asked for most
  of them, so apply is mostly memory hits); a non-CJK description never asks and lands None
  (R7).
- `rebind(db, source_text, target_text) -> {"lines": n, "packing_rows": n}`: UPDATE both
  row tables where `regexp_replace(btrim(description), '\s+', ' ', 'g') = :source_text`
  (the memory's own normalised key), setting `description_en = :target_text` (None on a
  forget). Through the ORM `query(...).update(synchronize_session=False)` so the company
  filter applies as it does in `supplier_code_alias_service._rebind`. Only `zh -> en` rows
  re-bind the cache column (R5).

### `translation_service` gains the re-bind on every write

`remember`, `update_target_text` and `delete_memory` call
`description_translation.rebind` (lazy import, same pattern
`supplier_code_alias_service._rebind` uses to reach `rebind_packing_rows`) after their own
write and before commit. One place, so the preview's edits at apply, the inline cell, the
admin page's inline edit and the admin page's delete all reach the rows already on file.
`remember` returns the re-bind counts alongside `written` (`{"written": n, "rebound":
{...}}`), so the inline cell's toast can say how many rows changed. Existing callers that
read the int are updated (`supplier_document_service.py:749` ignores the return).

An `ai` row written by `_ai_fill_chunk` does NOT re-bind: it is written during a
`translate` call whose caller is about to `fill` the rows it cares about, and re-binding
every PI on file off a model guess is not a ruling anyone made.

### Write paths that fill `description_en`

1. `proforma_invoice_packing_service.replace_packing_rows`: `fill(db, new_rows)` after the
   loop, before `db.flush()`.
2. `proforma_invoice_service` PI line create (`:1040` block) and line update (`:2779`):
   `fill` over the lines just written, one call per apply.

### Downstream (R4)

Every site that copies a PI row's description OUT reads `ln.description_en or
ln.description`: `:1729`, `:1790`, `:1906`, `:2054`, `PackingListLine.description` at
convert, and the export payload `to_xlsx` reads. The revision diff (`:596-662`) keeps
comparing the SOURCE description.

### Serialisers

`serialize` line dict (`:3192`) and packing row dict (`:3295`) gain `"description_en"`.
Assert it in a test.

### Route (one new)

| Method | Path | Perm | Body |
|--------|------|------|------|
| PUT | `/scm/proforma-invoices/{invoice_id}/translations` | `_UPLOAD` (`scm.proforma_invoice.upload`) | `{source_text, target_text}` -> `translation_service.remember` (one pair, `user_id` = caller) -> `{source_text, target_text, source, rebound: {lines, packing_rows}}`; `invoice_id` must exist (`get_or_404`); 422 on blank text |

The admin routes already exist (`GET/PUT/DELETE /system/translations`), unchanged in shape;
they now re-bind through the service.

### Frontend

- `DescriptionEnCell` (Phase 1) stays: dash / English / inline `Input`, Enter saves,
  Escape cancels, blur saves if changed; editable only when `canAdjust` and `description`
  non-empty. Phase 2 swaps the mock for `PUT /scm/proforma-invoices/{id}/translations`,
  invalidates `proformaInvoiceDetailQueryKey` + `proformaInvoicePackingQueryKey`, toast
  "Translation saved, N rows updated". The Phase 1 subscribe/version mock plumbing is
  removed with the mock.
- Columns on the Packing tab and the Lines tab (both modes) as built in Phase 1.
- **Delete** `app/(protected)/system-management/text-glossary/**` and its two menu entries
  (R8/R11). System > Translations is untouched.
- Types: `description_en: string | null` (already added, optional; keep).

### Not built (named triggers)

- `material` / `remark` cache columns: build when an operator needs a material in English on
  a customs document. (The preview already translates remarks into memory; only the cache
  is missing.)
- Other readers (outstanding SO, PO listing, supplier inventory): a second document type
  shows CJK free text on a screen someone reads.
- Second-locale display: a user asks for a non-English column; the memory already keys on
  `target_lang`.
- "Untranslated texts seen" report: the inline cell proves too slow when onboarding a
  supplier.

## Slices

| Slice | Scope | Tests (tester writes first) |
|-------|-------|------------------------------|
| S1 BE (#811) | migration 510 + backfill, `description_translation.py`, re-bind hooks in `translation_service`, two fill paths, downstream coalesce, serialisers, the SCM route | `tests/scm/test_description_translation.py`: A1-A7, B1-B5, C1-C4, D1-D5 |
| S2 FE (#812) | Phase 1 done. Phase 2: swap mock for the real call, delete the text-glossary page + menu entries, vitest for the cell + both tabs | vitest: cell Enter/Escape/blur, column renders `description_en`, dash for null; service `extractApiError` path. agent-browser: E1-E5 |

## Files

BE: `alembic/versions/510_pi_description_en.py`, `app/models/scm.py` (two columns),
`app/services/scm/description_translation.py` (new), `app/services/translation_service.py`
(re-bind calls, `remember` return shape), `app/services/scm/proforma_invoice_packing_service.py`,
`app/services/scm/proforma_invoice_service.py`, `app/api/v1/scm/proforma_invoices.py`.

FE: `app/(protected)/scm/proforma-invoices/services/proformaInvoiceTranslationService.ts`
(real call), `app/(protected)/scm/hooks/useProformaInvoiceTranslation.ts`,
`.../components/DescriptionEnCell.tsx`, `config/menu.config.tsx` (remove the two Text
Glossary entries), delete `app/(protected)/system-management/text-glossary/`.

## DoD

- UAC A-E green; pytest + vitest in CI; single alembic head after `alembic-reparent.sh`.
- Browser evidence under `documentation/plans/scm/evidence/text-glossary/`.
- Guide: Outline page "Translating supplier wording" (guide-writer) - covers the preview,
  the tab cell, and System > Translations as one flow.
- Prod after deploy: the migration backfill fills whatever the memory already holds; Jayson
  types the missing Jinbaichuan words once on PI-2609-008; PI-2609-001..007 pick them up.
- Alignment record: `.lavish/text-glossary.html` (10 Sep, all four questions answered with
  the recommended option, "good to go"), revised by R11 in this file.
