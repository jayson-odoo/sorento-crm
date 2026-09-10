# PLAN: Text glossary - English for the supplier's own wording on PI lines and packing rows

Status: aligned, building (2026-09-10)
Domain: scm (surface) + system (glossary page)
UAC: `text-glossary-acceptance-criteria.md`
Lane: `feat/text-glossary`, branched off `main` after #793 (PI-first) merged 2026-09-10.
Alembic parent: `509_merge_508_summary_and_excl_wh`.

## Journey

Jayson uploads Jinbaichuan's PI + packing list. The Description column reads `连体马桶`
and `盆`. Rows 1, 2 and 5 carry no code at all, so Match-to-product cannot name them. The
customs broker, the shipment grid and the container workbook all need English. Today the
only way is to edit the supplier's file by hand before every upload.

After this lane: the Packing tab and the Lines tab carry a second column, **Description
(EN)**. The first time `连体马桶` arrives it shows a dash. Jayson clicks the cell, types
`One-piece toilet`, presses Enter. Every row on file that says `连体马桶` (this PI, every
other PI, every packing row) now reads `One-piece toilet` in that column, and every later
upload lands already translated. The converted shipment line, the packing list and the
container workbook print the English. A System page lists every word learnt so an admin can
correct or forget one.

## Rulings (grill, 10 Sep)

| # | Ruling | Consequence |
|---|--------|-------------|
| R1 | English shows in a SEPARATE column, `Description (EN)`; `Description` stays the supplier's own text | No coalesce on the PI screens; both columns serialised |
| R2 | Learning = inline edit on the row (Packing tab AND Lines tab) + a System page | One write path (`upsert`) behind both; the page is a copy of Import Column Mappings |
| R3 | Slice 1 = `description` on `proforma_invoice_line` and `proforma_invoice_packing_line` only | `material`, `remark`, and the other readers (outstanding SO, PO listing, supplier inventory) are named triggers, not built |
| R4 | English flows downstream wherever description is COPIED off a PI row | Shipment line, packing list line, container workbook, shipment notes print `description_en or description`; the PI rows keep both |
| R5 | Glossary is the multilingual seed, not a UI i18n framework | The table carries a `locale` column so a second target language is INSERTs; the row cache column is `description_en` until a second locale is actually asked for (trigger below) |
| R6 | NO seed rows (owner, 10 Sep) | The migration creates the table empty; the operator types every word through the feature; tests insert their own rows |
| R7 | Lavish alignment 10 Sep, Q1: an already-English description shows a dash, editable, no auto-mirror | One rule, nothing guessed |
| R8 | Q2: page lives at System Management > Text Glossary beside Import Column Mappings | Same admin family, same copy template |
| R9 | Q3: locale hidden on the page in slice 1 | Every row is `en`; the column and the field appear when a second locale exists |
| R10 | Q4: inline edit gated by `scm.proforma_invoice.upload`, same as Match/Dismiss | The person handling the PI names the word; the System page stays admin-only |

## What exists (measured)

| Claim | Evidence |
|-------|----------|
| Header aliases translate HEADERS only | `app/models/import_alias.py` (`import_field_alias`: doc_type, field, alias, locale); `AliasResolver` in `app/services/import_alias_service.py` |
| Cell values stored verbatim | `proforma_invoice_packing_service.replace_packing_rows` writes `description=ln.product_name` (line 103); `proforma_invoice_service.py:1040` writes `description=ln.description` on PI line create, `:2779` on line update |
| Rendered raw | `ProformaInvoicePackingTab.tsx:242-251` (accessorKey `description`, truncate + title); Lines grid in `ProformaInvoiceDetail.tsx:617-632` (editable input in edit mode) |
| The "remember a person's decision and re-bind rows on file" mechanism | `supplier_code_alias_service.create/_record/_rebind/delete` (`_rebind` reaches stock rows, PI lines, packing rows via `rebind_packing_rows`) - the justification: a ruling only usable on the NEXT upload is one nobody gets to use today |
| Admin CRUD page for an import table | `app/api/v1/system/import_field_aliases.py` (list/create/delete, perms `system.import_field_aliases.view/.edit`, mounted in `system/__init__.py:43`); FE `system-management/import-field-aliases/` (list + `FormDialog` + hooks + service); menu `config/menu.config.tsx:903` and `:2126`; deferred delete key `import_field_alias.forget` in `record_actions.py:1419` |
| Downstream copies of description | `proforma_invoice_service.py:1729` (unplaced row descriptions into shipment notes), `:1790` and `:1906` (shipment grouping), `:2054` (`InboundShipmentLine.description`), `:2235` (`to_xlsx` container workbook), `PackingListLine.description` (`procurement.py:369`, "from proforma_invoice_line.description at convert") |
| Serialisers | `proforma_invoice_service.serialize` (`:3015`; line dict at `:3192`, packing row dict at `:3295`) |
| Permission that gates row rulings on the PI page | FE `ADJUST_PERMISSION = 'scm.proforma_invoice.upload'` (`ProformaInvoiceDetail.tsx:83`); BE `_UPLOAD` on `/packing-lines/{row_id}/match` (`proforma_invoices.py:494`) |
| Fixtures | `tests/scm/fixtures/kailu_packing_list_sample.xls`, `jiexia_proforma_invoice_sample.xls`, `jiexia_packing_list_sample.xls`. No Jinbaichuan fixture is committed; tests use synthetic CJK rows |

## Design

### Table `text_glossary` (migration `510_text_glossary`)

| Column | Type | Note |
|--------|------|------|
| id | uuid pk, `gen_random_uuid()` server default | same shape as `import_field_alias` |
| source_text | Text NOT NULL | stored trimmed, internal whitespace collapsed to one space |
| locale | String(8) NOT NULL, server default `'en'` | TARGET language (R5) |
| translation | Text NOT NULL | trimmed |
| source | String(10) NOT NULL, default `'manual'` | `manual` today (an `ai` value is a later trigger) |
| created_by | String(200) NULL | actor |
| created_at, updated_at | timestamp | |

Unique index `uq_text_glossary_key` on `(lower(source_text), locale)`. NOT company-scoped,
same reasoning as `import_field_alias`: a word means the same thing in every operating
company. No `__company_shared__` needed because the model is not company-scoped at all.

Migration also: `ALTER TABLE proforma_invoice_line ADD COLUMN description_en TEXT NULL`,
same on `proforma_invoice_packing_line`; permissions `system.text_glossary.view` /
`.edit` inserted and granted to `admin` + `superadmin` (copy migration 505's grant block).
NO seed rows (R6): the table is created empty. A downgrade drops both columns, the table
and the two permissions.

### Service `app/services/text_glossary_service.py`

- `normalize(text) -> str`: strip, collapse whitespace. Empty in = empty out.
- `lookup(db, texts: Iterable[str], locale="en") -> dict[str, str]`: one query,
  `lower(source_text) IN (...)`, keyed by the caller's ORIGINAL string so callers do not
  re-normalise. Empty/None texts skipped.
- `upsert(db, *, source_text, translation, locale="en", actor) -> dict`: 422 on blank
  source or blank translation; writes or overwrites the one row for `(lower(source), locale)`
  with `source='manual'`; then `_rebind(db, source_text, translation, locale)`. Does not
  commit (caller commits, same contract as `supplier_code_alias_service.create`).
- `forget(db, glossary_id, *, actor) -> dict`: 404 on a non-uuid or missing id; deletes the
  row; `_rebind(db, source_text, None, locale)` so every row cached off it goes back to
  untranslated (the alias `delete` docstring's reasoning: a value whose reason has been
  deleted is a value nobody can account for).
- `_rebind(db, source_text, translation, locale)`: `UPDATE proforma_invoice_line SET
  description_en = :t WHERE lower(description) = lower(:s)`, same on
  `proforma_invoice_packing_line`; via ORM `query(...).update(synchronize_session=False)` so
  the company filter applies exactly as `_rebind` in the alias service. Returns
  `{"lines": n, "packing_rows": n}`. Only `locale == 'en'` writes the cache column; another
  locale writes the glossary row only (R5).
- `apply_to_lines(db, rows, attr="description", target="description_en")`: fills the cache
  column on a list of freshly built ORM objects from one `lookup`. Called from the two write
  paths below.

### Write paths that fill `description_en`

1. `proforma_invoice_packing_service.replace_packing_rows` - after the loop, before
   `db.flush()`: `apply_to_lines(db, new_rows)`.
2. `proforma_invoice_service` PI line create (`:1040` block) and line update (`:2779`):
   after `line.description` is set, look up and set `line.description_en`. One `lookup` per
   apply, not per line.

### Downstream (R4)

Every site that copies a PI row's description OUT to another table or file reads
`ln.description_en or ln.description`:

- `:1729` unplaced row descriptions (shipment notes)
- `:1790`, `:1906` shipment grouping `description`
- `:2054` `InboundShipmentLine.description`
- `PackingListLine.description` at convert (find the write with `grep -n "description" ` in
  the convert path; the model comment at `procurement.py:366` names it)
- `to_xlsx` (`:2193`) reads `line["description"]` off the export payload; the payload builder
  supplies the coalesced value.

The revision diff (`:596-662`) keeps comparing the SOURCE description: a translation
arriving later is not a revision of the invoice.

### Serialisers

`serialize` line dict (`:3192`) and packing row dict (`:3295`) gain `"description_en"`.
Assert it in a test (LESSONS: `response_model` drops undeclared fields; these are plain
dicts, but the test still guards the FE contract).

### Routes

System (`app/api/v1/system/text_glossary.py`, mounted in `system/__init__.py`, tag
`text-glossary`):

| Method | Path | Perm | Body / returns |
|--------|------|------|----------------|
| GET | `/text-glossary?locale=en&q=` | `.view` | `[{id, source_text, locale, translation, source, created_by, created_at, updated_at}]` ordered by source_text; `q` is `ILIKE` on source_text OR translation |
| PUT | `/text-glossary` | `.edit` | `{source_text, translation, locale?}` -> the row + `{rebound: {lines, packing_rows}}`; 200 whether created or overwritten (upsert) |
| DELETE | `/text-glossary/{id}` | `.edit` | 204; registered as deferred action `text_glossary.forget` (reversible window, same family as `import_field_alias.forget` in `record_actions.py:1419`) |

SCM (`app/api/v1/scm/proforma_invoices.py`):

| Method | Path | Perm | Body |
|--------|------|------|------|
| PUT | `/proforma-invoices/{invoice_id}/translations` | `_UPLOAD` (`scm.proforma_invoice.upload`) | `{source_text, translation}` -> same `upsert`, `locale='en'`; `invoice_id` must exist (`get_or_404`) so the route is reachable only from a PI the caller can already see |

Both routes call `text_glossary_service.upsert`. The SCM route exists because the operator on
the PI page holds `scm.proforma_invoice.upload`, not the admin-only `system.*.edit` (same
split as Match on the Packing tab writing a supplier alias through the PI route).

### Frontend

Shared cell `app/(protected)/scm/proforma-invoices/components/DescriptionEnCell.tsx`:
shows `description_en` (truncate + title) or a muted dash; when `canAdjust` and the row has a
non-empty `description`, click swaps to an inline `Input` (Enter saves, Escape cancels, blur
saves if changed); save calls `proformaInvoiceTranslationService.upsert(invoiceId,
{source_text: description, translation})` via `useProformaInvoiceTranslationMutation`
(invalidates `proformaInvoiceDetailQueryKey` + `proformaInvoicePackingQueryKey`, toast
"Translation saved, N rows updated"). A row whose `description` is empty shows the dash and
is not editable (nothing to key on).

- Packing tab: new column `description_en`, header `Description (EN)`, `size: 200`, placed
  right after `Description`. Column personalisation is keyed by the existing
  `LISTING_KEY`; a new column lands visible (check `project_listing_new_column_exiled_right`
  memory: if a stored config hides it, the coder adds it to the default visible set).
- Lines tab (`ProformaInvoiceDetail.tsx` lines grid): same column after `description`, same
  cell, in BOTH view and edit mode (the cell is not part of the line form; it writes the
  glossary directly, so view and edit stay the same layout).
- Types: `packingLine.types.ts` and the line type in `proformaInvoiceService.ts` gain
  `description_en: string | null`.
- System page `app/(protected)/system-management/text-glossary/` copied from
  `import-field-aliases/`: DataGrid (Source text, Translation, Added by, Added) with search,
  Add dialog (source text, translation; locale NOT shown, sent as `en` - R9),
  row edit (same dialog, PUT), delete = deferred `text_glossary.forget`. Menu entries beside
  Import Column Mappings at `menu.config.tsx:903` and `:2126`, title "Text Glossary", perm
  `system.text_glossary.view`. Service `textGlossaryService.ts` uses `extractApiError` and
  `buildDataGridParams`.

### Not built (named triggers)

- `material` / `remark` columns: build when an operator names a material they need in
  English on a customs document.
- Other readers (outstanding SO, PO listing, supplier inventory): build when a second
  document type shows CJK free text on a screen someone reads.
- Second locale display: `description_en` becomes a per-locale structure when a user asks
  for a non-English column. The glossary already holds the data.
- AI pre-fill (`source='ai'`): build when the glossary's untranslated backlog is measured
  above ~50 distinct texts. Deterministic after first store, human confirms.
- "Untranslated texts seen" report on the System page: build when the inline cell proves too
  slow for onboarding a new supplier.

## Slices

| Slice | Scope | Tests (tester writes first) |
|-------|-------|------------------------------|
| S1 BE | migration 510, model, service, two write paths, downstream coalesce, serialisers, three routes, deferred action key, perms | `tests/scm/test_text_glossary.py`: A1-A9, B1-B5, C1-C4; `tests/system/test_text_glossary_api.py`: D1-D6 |
| S2 FE | `DescriptionEnCell`, Packing + Lines columns, translation service/hook, System page, menu, types | vitest: cell view/edit/save/escape; Packing tab column renders `description_en`; System page list + add + delete window; service `extractApiError` path. agent-browser: E1-E5 by sidebar clicks at 375 and 1280 |

Phase 1 (FE against mocks) builds S2's components with a mocked `description_en` on the
detail payload; Phase 2 lands S1 test-first then wires S2 to it.

## Files

BE: `alembic/versions/510_text_glossary.py`, `app/models/text_glossary.py`,
`app/services/text_glossary_service.py`, `app/api/v1/system/text_glossary.py`,
`app/api/v1/system/__init__.py`, `app/api/v1/scm/proforma_invoices.py`,
`app/services/scm/proforma_invoice_packing_service.py`,
`app/services/scm/proforma_invoice_service.py`, `app/services/record_actions.py`,
`app/rbac/permission_registry.py`, `app/models/scm.py` (two columns).

FE: `app/(protected)/scm/proforma-invoices/components/DescriptionEnCell.tsx`,
`.../services/proformaInvoiceTranslationService.ts`, `.../hooks/useProformaInvoiceTranslation.ts`,
`.../[id]/components/ProformaInvoicePackingTab.tsx`, `.../[id]/components/ProformaInvoiceDetail.tsx`,
`.../types/packingLine.types.ts`, `app/(protected)/system-management/text-glossary/**`,
`config/menu.config.tsx`.

## DoD

- UAC A-E green; pytest + vitest in CI; single alembic head after `alembic-reparent.sh`.
- Browser evidence under `documentation/plans/scm/evidence/text-glossary/`.
- Guide: Outline page "Translating supplier wording" (guide-writer).
- Prod after deploy: Jayson types the Jinbaichuan words once on PI-2609-008; verify
  PI-2609-001..007 pick them up without re-upload.
- Alignment record: `.lavish/text-glossary.html` (Lavish session 10 Sep, all four questions
  answered with the recommended option, "good to go").
