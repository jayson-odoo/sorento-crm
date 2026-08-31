# PLAN - Spec registry: every reader is a rule, rules read as sentences, try it on a real product

**Status:** In progress 31 Aug 2026. S1 (#432) FE mock done 145e8a3fa; S2 (#433) engine done 096c81a76, golden parity 0 diffs over 2,000 codes, migration `450_spec_rules_readable`; S3 (#434) next. AC-A.1 amended to the measured order (see UAC). UAC: `spec-rules-readable-acceptance-criteria.md`.
**Issue:** #425 (expanded). **Lane:** worktree `spec-rules-readable`, FE :3110 / BE :8110 (captain 31 Aug), after the
flyer lanes finish; branch `feat/spec-rules-readable` from `origin/main`.
**Queue:** flyer #422 -> family #428 -> value labels #423 -> THIS.

## Why

`SRTWC8354-SH-P` showed "the rules now read 180 mm" while the only rule on the Length screen
was `L\s*(\d+...)`. The 180 came from a reader hard-wired into `derive()` that no screen
lists, and the rule that IS listed is a regex nobody can read. The captain's ruling: "if it
is a rule, surface it and let me remove it; the regex is too hard to read; user should look
at simple and configure simple; try it should pull a real product."

## Captain rulings (31 Aug)

- **R1** Every reader is a rule row; nothing fires that the list does not show.
- **R2** Everything removable, class-from-category and brand-from-field included.
- **R3** Raw regex stays, under Advanced.
- **R4** Try-it pulls a real product by server search (whole master).
- **R5** Default order = today's hidden order (column > L x W x H > lone size > user rows).
- **R6** Plausibility cap becomes a per-key field, seeded 5000 on mm keys.
- **R7** Catalogue preview ships in the first cut.
- **R8** Sentence vocabulary = the list below; anything else through Advanced.

## What exists (measured)

- Rule dicts: `{match, pattern, value, capture, scale, unit, source}`; kinds `contains`,
  `ends_with`, `present`, `regex`, `code_suffix`, `code_contains`, `code_starts_with`.
  Order = priority. Shipped rules come from `_rules_from_shipped_tables()`; a key with
  stored `derivation_rules` ignores shipped ones entirely ("change one and they become yours").
- Hard-wired in `derive()` steps 1-4 (`product_spec_derivation.py:933-1055`): class
  (category + `_class_from_description`), brand (product field), `_DIM_RE` triple with
  thickness (4th number) and the round/square gate to diameter, `_SINGLE_DIM_RE` lone
  size, `MAX_PLAUSIBLE_MM = 5000`, `column_conflict` when the `products.dimensions_*`
  column disagrees with the parsed text.
- `POST /spec-registry/reread-catalogue` already runs derivation on the worker; the
  preview reuses its plumbing with a dry-run flag.
- `SpecRuleEditor.tsx` (267 lines) renders `MATCH_KINDS` with a text box for `pattern`.

## Design

### Rule row = engine form + sentence form

One list, one row shape, two views of it:

```
{ match, pattern, value, capture, scale, unit, source,   # engine form (unchanged)
  builder: { kind, ...blanks },                           # sentence form (new, optional)
  shipped: true|absent, shipped_backfill: true|absent }
```

The engine never reads `builder`. The UI renders `builder` when present and compiles it
to `match/pattern/capture` on save; the server recompiles and refuses a mismatch
(AC-A.7). A row without `builder` is a pattern row: shown as "Pattern `...`, capture the
Nth number". Advanced on a builder row shows the compiled pattern; editing it drops
`builder`.

### Sentence kinds (R8) and what they compile to

| builder.kind | sentence | compiles to |
|---|---|---|
| `number_after` {word} | Number after the word `L` | `regex` `\bL\s*(\d+(?:\.\d+)?)` capture 1 |
| `number_before` {word} | Number before `MM` | `regex` `(?<![A-Z0-9X])(\d+(?:\.\d+)?)\s*MM\b` capture 1 |
| `number_between` {a, b} | Number between `S-TRAP` and `MM` | `regex` `A\s*[:,]?\s*(\d+(?:\.\d+)?)\s*B` capture 1 |
| `text_contains` {phrase, value} | Text contains `RIMLESS` -> yes | `contains` |
| `text_ends_with` {phrase, value} | Text ends with `SQUATTING PAN` -> ... | `ends_with` |
| `word_present` {phrase} | Word `THERMOSTATIC` is present -> yes | `present` |
| `code_contains` / `code_starts_with` / `code_ends_with` {token, value} | Code ends with `-UF` -> UF | the code kinds |
| `from_field` {field} | From the product's category / brand field / `dimensions_length` column | NEW engine kind `from_field` |
| `size_triple` {position} | Size from `L x W x H`, take the 1st number | `regex` `_DIM_RE` capture N |
| `name_head` | Product name head (text before the first bracket or WITH) | `regex` compiled from `_CLASS_*` |

Blanks are escaped before compiling; `number_between` a/b are literal phrases. The
existing shipped tables gain a `builder` for every row they emit, so today's shipped rules
read as sentences too (a table test pins each).

### Engine (`product_spec_derivation.py`)

- New kind `from_field`: `field` in `category`, `brand`, `column:<products column>`.
  Reads the product row, not text. Value for `category` = the class signal the step-1
  code computes today; `brand` = the brand name; `column:` = the numeric column.
- Steps 1-4 collapse into "apply rules for every key in order" (step 5 today). The
  shipped rows in AC-A.1 reproduce steps 1-4 exactly; AC-A.2 golden parity is the proof.
- The round/square gate becomes the existing per-rule scope condition (`applies_when`),
  extended with a negative form (`unless`) so `dim_length` rows apply unless shape is
  round/square and `diameter` rows apply when it is.
- `column_conflict` stays as engine behaviour, generalised one notch: when a text row
  wins and a `from_field column:` row lower in the list reads a different number, flag.
- `MAX_PLAUSIBLE_MM` -> `registry.max_value` (AC-A.5).
- `_DESCRIPTION_FIRST_KEYS` goes: with one ordered list there is no "description phase".
  The flyer ingest's `description_first` flag is computed instead as "a higher-priority
  row already read this key from the product's own text/fields", same meaning.

### Registry (`spec_registry.py`, model)

- `max_value NUMERIC(12,3) NULL` column. Migration seeds 5000 where `unit = 'mm'`.
- Backfill for owned keys (AC-A.6): prepend the affected shipped rows, tagged
  `shipped_backfill: true`.
- PATCH validates/compiles `builder` (AC-A.7, A.8). GET serialises `builder`, `shipped`.
- `POST /{spec_key}/try` and `POST /{spec_key}/preview` + `GET /{spec_key}/preview/{job_id}`
  (AC-B.1, B.2). Preview job = `reread-catalogue` machinery with `dry_run=True` and a
  per-key result summary written to a small `spec_preview_job` row (or the RQ job meta,
  whichever `reread-catalogue` already uses; copy that).

### Frontend

- `SpecRuleEditor.tsx` becomes the sentence editor: kind menu by prose, inline blank
  inputs, Advanced toggle, `shipped` tag, drag/remove unchanged.
- New `SpecTryItPanel.tsx`: product `SearchableSelect` (fetchOptions over the products
  select endpoint, page 50) or paste box; per-row read results rendered INTO the rule rows
  (a `readResult` prop), winner marked.
- New `SpecPreviewPanel.tsx`: button, pending state, counts, sample DataGrid (fixed
  layout, sizes, truncate + title).
- `SpecKeyEditor.tsx`: removes the two explanatory sentences; adds `max_value` input.
- Layering: UI -> `useSpecRegistryMutations` / `useSpecTryIt` / `useSpecPreview` ->
  `specRegistryService` -> api-client. Contract block at the top of the service.

### Slices

- **S1 (Phase 1, FE mock)**: sentence rows, Advanced, try-it panel, preview panel, max
  value field, against a mocked service that compiles sentences client-side and fakes
  reads. Browser-verified at 1280 + 375. Group C.
- **S2 (Phase 2, engine)**: `from_field` kind, shipped rows for the hard-wired readers with
  `builder`, `unless` scope, `max_value`, backfill migration, golden parity. Group A.
- **S3 (Phase 2, endpoints + swap)**: try + preview endpoints, worker job, FE swap,
  vitest, evidence run. Group B.

### Tests (red first)
- `tests/test_product_spec_derivation.py`: AC-A.1 list pin, A.3, A.4, A.5, A.8 table.
- `tests/test_product_spec_derivation_golden.py` (new): AC-A.2 over fixtures + the
  2,000-code sample list checked into `tests/fixtures/`.
- `tests/test_spec_registry_pr2_routes.py`: A.7, B.1, B.2 (job enqueued, result shape,
  permissions).
- `tests/test_migration_45x_spec_rules_backfill.py`: A.6 both directions.
- vitest: `SpecRuleEditor.test.tsx` (sentence render, Advanced switch, shipped tag),
  `SpecTryItPanel.test.tsx` (fetchOptions mode, reads rendered, winner), `SpecPreviewPanel.test.tsx`.

### Migration order
Numbered after whatever is head when the lane starts (`alembic heads` on the lane); one
head, always.

### DoD
Mock swapped; owned keys backfilled (AC-A.6); no new permission (uses
`master_data.spec_registry.view/edit`); `max_value` and `builder` asserted in responses;
sidebar verification at both widths. After deploy: re-derive prod (operations, with a go).

## Backlog
- Sentence kinds beyond R8 when a second real case needs one.
- Value labels (#423) interacts: sentences show values through `readableValue` with labels.
