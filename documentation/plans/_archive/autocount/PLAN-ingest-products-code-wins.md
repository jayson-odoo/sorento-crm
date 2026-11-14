# PLAN - products resolve code-wins on ingest (contract 2.4)

Status: merged (2026-09-20, PR #1049 deployed; contract 2.4 live, FoundryX keys products by ItemCode on both books)
UAC: `documentation/plans/_archive/autocount/ingest-products-code-wins-acceptance-criteria.md`
Branch: `feat/ingest-products-code-wins` (its own lane and PR, ahead of the pull lane)

## Journey

See the UAC `Journey` section. One sentence: FoundryX keys products by item code, Sorento
already holds those products under references the SO/PO lines minted, so the item code decides
and the stored reference is kept.

## Why (measured, 2026-09-19 prod copy)

- `integration_references` holds 9,067 product rows for SRT, all `AED_SORENTO:<numeric item key>`,
  all minted by document LINE ingest (`master_ref_resolver.py`, the code rung links the line's
  `product_ref`). The product master push has never run. MCH holds no references at all.
- The AutoCount HTTP source exposes no numeric item key, only the item code, so a product record
  arrives as `<prefix>:<ItemCode>`.
- Today `MasterIngestService._apply_scoped`: reference miss, adopt-by-code hit, and the matched
  row already has a reference -> `ReferenceConflict` -> record `FAILED`. A products pull for SRT
  would show about 9,067 failures.
- A second reference per product is impossible by design: `uq_integration_ref_entity` is
  UNIQUE `(entity_type, entity_id)`, and `origin_of()` is `.first()` at six call sites.

## Design (two seams, no migration, no new table, no new permission)

The rule is copied from the document-line resolver, with its justification: that resolver
already treats a product whose stored reference differs from the sent one as "resolve by code,
keep the stored reference, warn `ref_mismatch`" (`master_ref_resolver.py`, `WARN_REF_MISMATCH`).
Products get the same identity rule on the master path, so one product has one rule on both.

### Seam 1 - `MasterIngestService._apply_scoped` (adopt branch)

Where it raises `ReferenceConflict` because `refs.origin_of(...)` is not None, add one branch:
when `entity_type == "products"` AND the existing reference's `source_system` equals the source
system this service links under, then:

- run the same product finalisers as the adopt path (`_finalize_product_derived`),
- capture `_diff`, `_update` the row, run `_post_write_product_hooks`,
- do NOT call `_link` (the stored reference stays, the incoming one is not stored),
- append `WARN_REF_MISMATCH` (import the existing constant, do not redefine it) to the record's
  warnings,
- return `IngestOutcome.UPDATED`.

Every other entity, and a product linked under another source system, still raises
`ReferenceConflict`. The adopt lookup is already company-scoped, so company isolation needs no
new code; the tests pin it.

### Seam 2 - deletions

- Route `delete_records` (`app/api/v1/external/ingest.py`): read an optional `codes` from the
  body. Validate: absent is fine; present must be a JSON object whose values are strings, else
  the route's existing 422 validation error shape. Pass it to the service.
- `DeletionService.delete(entity_type, source_refs, *, codes=None, dry_run=False)` and
  `_delete_one(entity_type, source_ref, code=None)`: when `refs.resolve` misses AND
  `entity_type == "products"` AND a code was supplied, look the product up with the same
  company-scoped, case and whitespace insensitive match ingest adoption uses
  (`resolve_master_by_code`). Proceed only when the matched product is unlinked or its reference
  is under the same source system; otherwise `not_found`. From there the existing path runs
  unchanged (dependents probe, hard delete or `is_discontinued = true`).
- `DeletionRecordResult` gains `warnings: list[str]`, emitted by `as_dict()` only when non-empty
  (same rule as `RecordResult`). The code rung sets `["ref_mismatch"]`.
- `codes` for any other entity is ignored. A `codes` entry for a reference that resolves is
  ignored.

The "same source system" test is needed by both seams: one small predicate, defined once (on
`IntegrationReferenceService` or beside the constant), called from both. Not a registry, not a
config.

### Seam 3 - contract

`CONTRACT_VERSION = "2.4"` in `app/api/v1/external/ingest.py`; `contract.py` `FIELDS_ADDED` gains
the product deletions `codes` field and `FIELD_NOTES` gains the two notes in AC-CT-1. Update
`documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md` with a short "v2.4"
section that points here.

## What does not change

Warnings shape (`"warnings": ["<code>", ...]`, stable string codes). Deletion outcomes
(`deleted` / `deactivated` / `not_found` / `failed`). `/external/read/products` (reference-only).
Document ingest. The unique index. Every other entity's conflict behaviour.

## Accepted consequences (owner ruling R8)

- For already-linked products the item-code reference is never stored; every push resolves on
  the code rung and carries `ref_mismatch`. FoundryX treats `updated` + that warning as success.
- An item code renamed in AutoCount arrives as a new product (reference miss, code miss). Same as
  the manual Excel flow today.
- A retired item's code reused for a different item updates the old Sorento product.
- A casing change of an item code changes FoundryX's reference but not the match, so that
  product stays on the code rung permanently.
- For a code-wins product `_link` never runs, so that reference row's `last_synced_at` and
  `integration_id` stay at the value document ingest wrote. Nothing reads `last_synced_at` today;
  the pull lane must not build a "last synced" display on it.
- "Same source system" compares against the constant source system (`autocount`), not the calling
  integration. Trigger to revisit: a second `source_system` value, or a second integration issued
  a key on `autocount`; at that point compare `integration_id` as well.
- The deletions code rung trusts the body `companyCode` exactly as ingest already does (the
  FoundryX integration serves two books, so it carries no single company binding). A batch sent
  under the wrong `companyCode` would match by item code inside that company. Mitigations:
  FoundryX derives `companyCode` and `codes` from the same book record; `codes` is capped at the
  batch limit; every code-rung delete is logged. Recorded for the owner's ruling before merge.

## Files

- `sorento_crm_backend/app/services/master_ingest_service.py` (seam 1)
- `sorento_crm_backend/app/services/deletion_service.py` (seam 2)
- `sorento_crm_backend/app/api/v1/external/ingest.py` (codes parsing, version)
- `sorento_crm_backend/app/api/v1/external/contract.py` (fields_added, field_notes)
- `sorento_crm_backend/app/services/integration_reference_service.py` (the shared predicate, if
  that is where it reads best)
- tests: new `sorento_crm_backend/tests/test_ingest_products_code_wins.py`; existing
  `test_ingest_ref_collision.py`, `test_ingest_deletions.py`, `test_ingest_contract_v2.py`,
  `test_ingest_parity_s4_contract.py` touched only where they assert the old behaviour or the
  old version string.

## Slices

One slice, SR0. Tester writes the red tests from the UAC, coder makes them green, then reviewer
and security-reviewer in parallel (the change relaxes a guard on an external ingest surface).
No Phase 1: there is no screen. No browser verification: nothing renders. Both are recorded in
the PR description as not applicable.

## Definition of Done

1. Mock to real: not applicable (no FE).
2. Backfill: none (no stored data changes shape).
3. New permission: none.
4. New column: none.
5. User's perspective: the contract endpoint on the lane backend reports 2.4, and a dry-run
   product push against a prod-copy database shows `updated` + `ref_mismatch` for an
   already-linked SRT product (evidence in the PR).

## Risks

- An existing test pins the old conflict for products: update it in the red-test commit and name
  it in the PR.
- Deleting an UNLINKED product by code: allowed by the contract (FoundryX owns the item master),
  guarded by company scope and the dependents probe. Security review to confirm.
