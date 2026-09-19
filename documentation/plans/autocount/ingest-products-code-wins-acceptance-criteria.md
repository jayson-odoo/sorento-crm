# UAC - products resolve code-wins on ingest (contract 2.4)

Plan: `documentation/plans/autocount/PLAN-ingest-products-code-wins.md`
Slice: SR0 of the AutoCount pull + review work. Backend only, no screen.
Owner ruling R8 (2026-09-19): products are keyed by item code. Cross-repo text: FoundryX plan 10,
Appendix A9 (`foundryx-shared-service`, `documentation/plans/sprint-5/10-autocount-pull-review.md`).

## Journey

Actor: the FoundryX AutoCount integration (X-API-Key, act-as user), and behind it the Sorento
checker who reads the dry-run preview on a pull.

1. FoundryX sends a product keyed `<prefix>:<ItemCode>` to `POST /external/ingest/products`
   (or Sorento's own pull Confirm calls the same service). It arrives from the AutoCount HTTP
   source, which exposes no numeric item key.
2. Sorento already holds that product. 9,067 SRT products carry a reference minted by SO/PO line
   ingest (`AED_SORENTO:<numeric item key>`), so the incoming reference does not resolve.
3. Sorento matches the product by its item code inside the anchored company. Today that match is
   refused as a conflict and the record fails. After this slice the product is UPDATED, the
   reference the documents minted stays exactly as it is, and the record carries the
   `ref_mismatch` warning. The sender makes no decision and the checker sees `updated` plus the
   field diff in the preview instead of 9,067 failures.
4. When AutoCount removes an item, FoundryX sends a deletion by the same item-code reference plus
   the code itself. Sorento finds the product by code when the reference misses and retires it by
   the existing rule (discontinued when anything points at it, removed when nothing does).
5. FoundryX reads `GET /external/contract`, sees version 2.4, and only then allows item-code
   keyed products for that book.

Nobody else is told anything: no email, no notification, no screen changes.

## Acceptance criteria

All `[BE]` ACs are pytest on Postgres through the real route or service, seeding their own chain
(CI's database has no data).

### Ingest - code wins (products only)

- **AC-CW-1 [BE]** Given a product `P` (code `BRA-1`) in company A holding a reference
  `AED_SORENTO:101` under source system `autocount`, when a product record
  `{source_ref: "AED_SORENTO:BRA-1", code: "BRA-1", ...}` is ingested for company A, then the
  record outcome is `updated`, `entity_id` is `P`, `P`'s columns carry the incoming values,
  `warnings` contains `ref_mismatch`, and `integration_references` still holds exactly ONE row
  for `P` with `source_ref = "AED_SORENTO:101"` (no row for `AED_SORENTO:BRA-1` exists).
- **AC-CW-2 [BE]** Same setup with `dry_run=true`: outcome `updated`, a `diff` naming the changed
  columns with `current` and `incoming`, `warnings` contains `ref_mismatch`, and after the call
  `P` and its reference row are unchanged.
- **AC-CW-3 [BE]** Given a product with code `BRA-2` and NO reference, when ingested with
  `source_ref "AED_SORENTO:BRA-2"`, then it is adopted as today: outcome `updated`, the new
  reference IS linked, no `ref_mismatch` warning.
- **AC-CW-4 [BE]** Given a product whose stored reference equals the incoming `source_ref`, the
  record updates as today with no `ref_mismatch` warning.
- **AC-CW-5 [BE]** Repeating the AC-CW-1 push a second time gives the same result (`updated`,
  `ref_mismatch`, still one reference row). Idempotent.
- **AC-CW-6 [BE]** The code match under code-wins uses the same case and edge-whitespace
  insensitive rule adoption already uses: incoming code `bra-1 ` matches stored `BRA-1`.
- **AC-CW-7 [BE]** Given `P`'s existing reference is under a DIFFERENT source system, the record
  still FAILS with the `source_ref` conflict error, and `P` is unchanged.
- **AC-CW-8 [BE]** Parametrized over every other master entity that adopts by code (brands,
  product_categories, units_of_measure, warehouses, suppliers): a reference miss whose code
  matches a row already linked under another reference still FAILS with the conflict error.
  Code-wins is products only.
- **AC-CW-9 [BE]** Company isolation: a product with the same code in company B, linked or not,
  is never touched by a push anchored to company A; the push creates or matches inside A only.

### Deletions - optional `codes` (products only)

- **AC-DL-1 [BE]** Given `P` as in AC-CW-1 and a sales order line pointing at `P`, when
  `POST /external/ingest/products/deletions` is called with
  `{"source_refs": ["AED_SORENTO:BRA-1"], "codes": {"AED_SORENTO:BRA-1": "BRA-1"}}`, then the
  record outcome is `deactivated`, `P.is_discontinued` is true, `P.is_active` is unchanged,
  `P`'s reference row is intact, and the record carries `warnings: ["ref_mismatch"]`.
- **AC-DL-2 [BE]** Same call for a product nothing points at: outcome `deleted`, the product row
  and its reference row are gone, `warnings: ["ref_mismatch"]`.
- **AC-DL-3 [BE]** Reference miss with NO `codes` key (or no entry for that reference):
  `not_found`, exactly as today.
- **AC-DL-4 [BE]** A reference that resolves is handled by reference as today; its `codes` entry
  is ignored and no warning is attached.
- **AC-DL-5 [BE]** `codes` sent for any entity other than `products` is ignored: a reference miss
  is `not_found`.
- **AC-DL-6 [BE]** A code that matches a product linked under a DIFFERENT source system:
  `not_found`, product unchanged.
- **AC-DL-7 [BE]** A code that matches only another company's product: `not_found`, that product
  unchanged.
- **AC-DL-8 [BE]** `dry_run=true` reports the same verdict and warning and leaves every row
  unchanged.
- **AC-DL-9 [BE]** `codes` that is not a JSON object, or holds a non-string value, is rejected
  with the route's existing 422 validation shape and nothing is deleted. A `codes` key that names
  a reference not present in `source_refs` is ignored.

### Contract

- **AC-CT-1 [BE]** `GET /external/contract` reports `version` `"2.4"`; `fields_added` lists the
  `codes` field for product deletions; `field_notes` states (a) products resolve code-wins with
  the `ref_mismatch` warning and the stored reference kept, and (b) `/external/read/products`
  stays reference-only, so a product linked under a document-minted reference is not found by an
  item-code reference.

### Regression

- **AC-T-1 [T]** The whole ingest test family (`tests/test_ingest_*.py`,
  `tests/test_master_ingest.py`, `tests/test_integration_reference*.py`) is green. Any existing
  test that asserted the old products conflict is updated to the new rule in the same commit as
  the red tests, and named in the PR description.

## Out of scope

- The pull client, the Pull button, the review page and Confirm (SR1 to SR4, separate plan).
- Read-back by item code (`/external/read/products` stays reference-only, FoundryX does not rely
  on it).
- Clearing a brand with an explicit null (measured delta of 16 items, recorded, not patched).
- A `stock_balances` ingest entity (contract 2.5, later).
