# PLAN - Flyer reading: adopt an unmatched printed code as an existing product

**Status:** S1 built (adopt + undo, Groups A and B); S2 pending (`#422`). Undo revised to a
deferred action in the S1 review pass, 31 Aug 2026 - see "Frontend" below and UAC AC-B.3.
Approved 31 Aug 2026 (lavish markup: R5 added). Lane: `.claude/worktrees/flyer-code-adopt`.
UAC: `flyer-code-adopt-acceptance-criteria.md`.
**Branch:** `feat/flyer-code-adopt` (worktree lane). **Domain:** dealer-kit.

## Why

The unmatched list on a flyer reading is read-only by design (`PLAN-flyer-seeding.md` D8:
suggestions are shown, never applied). That protects the brochure from a silent
`SRTKS7850` -> `SRTKS7851` swap, but it also leaves 34 printed cards on the real flyer with
no way to say "this printed code IS that product", so their specs never reach
`product_specifications`. The only path today is Propose then Add row, typing each value by
hand as `manual` evidence. D8 stays: nothing is applied without a click. This adds the click.

## Captain rulings (31 Aug)

- **R1 - one product, one card.** Adopting onto a product that another printed code on the
  same reading already resolves to (by itself or by adoption) is refused with 409 naming
  the other code. Two cards feeding one product would write two spec sets for it.
- **R2 - adopt never touches the proposal batch.** A hint line asks for Propose again.
  Auto re-propose would wipe the reviewer's edits and dismissals (flyer-spec AC-A.5).
- **R3 - per reading, not master alias.** Half the rows are real variants (`-S`, `-BI`,
  `-RL`/`-SC`); a global alias would merge products. Trigger for the alias: the same printed
  code adopted on a second flyer.
- **R4 - any product, nearest prefilled.** The suggestion is a default in the dialog. The
  server has no opinion.
- **R5 - the picker reaches the WHOLE master (10k+ products), never a capped list.**
  Server-side search with paging and load-more (`SearchableSelect` `fetchOptions` mode over
  `GET /master-data/products/select`), the same mechanism that already serves the Dealer
  Kit product picker. A dropdown that fetches "the first N" and filters client-side is a
  defect (memory: this bit us twice).

## Design

### Storage

Two columns on the flyer reading row (`dealer_kit.flyer_reading`; coder confirms the
`__tablename__`):

- `code_overrides JSONB NOT NULL DEFAULT '{}'` : `{ "<printed code>": "<product id>" }`
- `code_overrides_changed_at TIMESTAMP NULL` : bumped on adopt and undo; the batch hint
  compares it with `batch.created_at` (AC-C.4). Undo removes the key, so the timestamp
  cannot live inside the map.

No table. One reading, one map. Migration `449_flyer_reading_code_overrides`,
`down_revision = "448_merge_s6b_ptag"` (the single head on `main` after PR #427
joins the price-tag chain with the S6b reference-data chain), revision id
<= 32 chars.

Model: `code_overrides = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"),
default=dict)`. Writes REASSIGN the dict (`record.code_overrides = {**old, code: pid}`);
SQLAlchemy does not see in-place mutation of a plain JSONB column.

### Matching (`app/services/dealer_kit/flyer_matching.py`)

- `MatchedCode` gains `adopted: bool = False`.
- `match_reading(db, reading, promotion_id=None, overrides: Mapping[str, str] | None = None)`.
  After `_products_by_code`, for every printed code that did not resolve and has an
  override, load the override products in ONE company-scoped ORM query
  (`Product.id.in_(...)`). Found -> insert into the `products` dict under the PRINTED code
  and append `MatchedCode(code=printed, product_id=P.id, product_code=P.product_code,
  adopted=True, pages=...)`. Not found -> the code stays unmatched (AC-A.6); nothing is
  written on a read.
- Because the adopted product sits in `products[printed_code]`, `_dimension_candidates`,
  `_not_promoted` and the seed's `product_by_code` need no change (AC-A.2).
- `_suggestions` still runs for the codes that remain unmatched only.

### Service (`flyer_reading_service.py`)

- `report_for` passes `record.code_overrides`.
- `adopt_code(db, record, printed_code, product_id, user_id) -> record`:
  1. status must be `done` (reuse the existing 409 words).
  2. `printed_code` must be in `_printed_codes(to_reading(record))` else 404
     `flyer_code_not_printed`.
  3. Compute the report WITHOUT this code's override. If `printed_code` is matched by
     itself -> 409 `flyer_code_already_matched`.
  4. Product by id, company-scoped ORM -> else 404 `flyer_adopt_product_not_found`.
  5. If any OTHER matched entry (self-matched or adopted) has `product_id == product_id`
     -> 409 `flyer_adopt_target_taken`, message "`<code>` on p. 11 is already this product".
  6. Reassign the map, set `code_overrides_changed_at = now`, commit.
- `unadopt_code(db, record, printed_code)`: key must exist else 404 `flyer_code_not_adopted`;
  status rule; remove key, bump timestamp, commit.
- Neither touches `product_spec_flyer_batch` rows (AC-C.3).

### Routes (`app/api/v1/dealer_kit/flyer_readings.py`)

```
PUT    /dealer-kit/flyer-readings/{reading_id}/code-overrides/{printed_code}
       body {"productId": "<uuid>"}            -> 200 FlyerReadingOut
DELETE /dealer-kit/flyer-readings/{reading_id}/code-overrides/{printed_code}
                                              -> 200 FlyerReadingOut
```

Dependencies: `require_permission("dealer_kit.page.view")` and
`require_permission("master_data.products.edit")` (the pair the spec-proposal routes use).
Both return the full detail (`_detail`) because the report changed; the FE replaces its
cache with it. `printed_code` is a path segment; the FE `encodeURIComponent`s it.

Schemas: `MatchedCodeOut.adopted: bool = False`; `FlyerReadingOut.code_overrides_changed_at`
(alias `codeOverridesChangedAt`); `CodeOverrideIn { product_id: UUID alias productId }`.
`_detail` copies the timestamp (lesson: both manual dict builders; here there is one).

### Propose pass (`product_spec_flyer_ingest.py`)

No change to `_propose`: it already keys card text by `entry.code` (the PRINTED code) and
writes rows to `entry.product_id` / `entry.product_code`. An adopted entry therefore yields
rows for the adopted product from the printed card, with the same origin/evidence as any
matched card. AC-C.1 pins this with a test so a later refactor cannot break it silently.

### Frontend

Files (all under `app/(protected)/dealer-kit/`):

- `services/flyerReadingService.ts`: `MatchedCode.adopted: boolean`,
  `FlyerReading.codeOverridesChangedAt: string | null`, `adoptCode(readingId, printedCode,
  productId, promotionId): Promise<FlyerReading>`, `undoAdoptCode(readingId, printedCode,
  promotionId)` (both carry `promotionId` the same way the GET does, so the response the
  caller gets back is computed against the promotion on screen). Contract block at the
  top of the file. Errors through `extractApiError`.
- `flyer-readings/hooks/useFlyerReadings.ts`: `useAdoptCode(readingId, promotionId)`. On
  success `queryClient.setQueryData([KEY, readingId, promotionId ?? ''], data)` (the
  response IS the new detail for THAT promotion; no refetch flash) + `invalidateQueries`
  the reading's other promotion-keyed entries, + toast. On error extracted message + toast.
- `flyer-readings/components/MatchReportSections.tsx`: the unmatched grid's rows become
  `unmatched ∪ matched.filter(adopted)` sorted by first page then code. Column
  "Nearest existing code" renders the adopted state for adopted rows. New trailing column
  "Action": **This is...** / **Undo**, gated by `useHasPermission(MASTER_DATA_EDIT)` the way
  `DimensionReviewSection` does. Header count and subtitle per AC-A.9.
- `flyer-readings/components/AdoptCodeDialog.tsx` (new): `Dialog`, `SearchableSelect` in
  server mode (`fetchOptions` -> `listPickerProducts` from `services/productPickerService.ts`,
  `pageSize` 50), initial option injected from the suggestion, `clearable`, one Confirm.
- **Undo (revised in the S1 review pass, 31 Aug 2026 - see UAC AC-B.3):** NOT an
  `AlertDialog`. PRINCIPLES.md "Design mandates" / ADR-PRODUCT-STANDARDS govern: a detach
  action is a server-deferred pending action, never a confirmation dialog. Undo parks
  `flyer_reading.undo_code_adopt` (`app/services/record_actions.py`, `entity_types =
  ("flyer_code_adoption",)`, a synthetic `<reading id>:<printed code>` entity id since the
  thing being detached is a key inside `code_overrides`, not a row of its own) through
  `useDeferredRowAction` / `DeferredActionButton` - the button becomes a countdown toast,
  and the server calls the SAME `unadopt_code` the DELETE route always did when the window
  lapses. Registered permission is `master_data.products.edit` only (the generic
  `/pending-actions` route checks one slug; the direct DELETE route still requires BOTH
  that and `dealer_kit.page.view` for a caller that reaches it directly).
- `flyer-readings/components/SpecProposalSection.tsx`: the hint line (AC-C.4).

Layering: UI -> hook -> service -> `lib/api-client`. No `URLSearchParams` by hand, no
hand-rolled error parsing. DataGrid rules already hold on this grid (fixed layout,
explicit sizes, `truncate` + `title`).

### Slices

- **S1 - adopt and undo, report follows.** Migration, model, matching, service, routes,
  FE row/dialog/undo. Groups A and B. Phase 1 mock first (mock `adoptCode` mutates a local
  copy of the reading), Phase 2 test-first.
- **S2 - proposals follow.** AC-C.1..C.3 tests on the ingest service (expected green
  without code change; the tests are the deliverable), AC-C.4 hint line, AC-C.5 evidence run.

### Tests (Phase 2, red first)

Backend, Postgres via `tests/_pg_fixture.py`, own seeded chain, `ZZT-` prefixed codes:
- `tests/test_dealer_kit_flyer_matching.py`: overrides param (adopted in matched, stale
  override ignored, dimension candidate for adopted, not_promoted for adopted).
- `tests/test_dealer_kit_flyer_readings.py`: PUT/DELETE happy paths, every AC-A.5 refusal,
  AC-A.4 replace, AC-A.8 field presence, seed `product_by_code` includes the adopted code.
- `tests/test_product_spec_flyer_ingest_service.py`: AC-C.1, C.2, C.3.
- `tests/test_migration_445_flyer_code_overrides.py` only if the existing migration tests
  for this table (367, 370) establish the pattern; otherwise the column is covered by the
  route tests running on a migrated scratch schema.

Frontend, vitest: `MatchReportSections.test.tsx` (adopted row, permission gating, dialog
opens preselected), `useFlyerReadings.test.tsx` (adopt sets query data), 
`SpecProposalSection.test.tsx` (hint line on/off by timestamps).

E2E: agent-browser evidence run for AC-A.12, B.4, C.5 (sidebar navigation, 375 and 1280).

### DoD

Mock swapped; no backfill needed (`{}` default); no new permission; new columns reach the
FE through `_detail` (asserted); verified from the sidebar at both widths.

## Backlog

- Master-level alias, trigger in R3.
- `SRTWC200-S-RL-UF` vs `SRTWC200-S-UF-RL` reads 100% alike: suffix order differs, one of
  the two records is wrong. Data question for master-data, not this feature.
