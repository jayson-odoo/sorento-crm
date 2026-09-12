# UAC - AutoCount `brands` ingest entity (contract 2.3)

Plan: `PLAN-autocount-brands-ingest.md`. `[T]` = pinned by a pytest (Postgres only).
Every request carries `X-API-Key` for an integration principal and a top-level `companyCode`.
Test fixtures create `uq_brands_company_brand_name` `(company_id, brand_name)` as well, because
create_all does not build it and prod has it (migration 305).

Shared route behaviour (company anchor, record log, sync route) is already pinned by the sibling
entities and is not re-tested here.

## Ingest

- **AC-1 [T]** `POST /api/v1/external/ingest/brands` with a new brand (`source_ref`, `code`, `name`)
  returns 200 with verdict `created`. The `brands` row sits in the anchored company, and
  `integration_references` links (`brands`, `source_ref`) to it.
- **AC-2 [T]** Re-pushing the same `source_ref` returns `updated` on the same id. An omitted optional
  field leaves the stored value untouched; `description: ""` clears it to null.
- **AC-3 [T]** Adoption: the anchored company holds an unlinked, hand-made brand with code
  `" sorento "`. A push with `code: "SORENTO"` returns `updated` on THAT id and no second row appears.
  Its `manufacturer`, `website`, `logo_url` and `access_levels` are unchanged.
- **AC-4 [T]** Company scope: brand `SORENTO` exists only in company A. A push anchored on company B
  returns `created` with a new row in B, and A's row is untouched.
- **AC-5 [T]** Name clash (plan Risk 1): the company holds a brand with code `SRT` and name `SORENTO`. A
  push with code `SORENTO` and name `SORENTO` returns `failed` for that record and creates nothing. The
  batch still answers 200 and the other records land.
- **AC-6 [T]** A 51-character `code`, a 151-character `name`, or an unknown key (for example
  `logo_url`) gives that record `failed` with the field named in `errors`. The other records land.
- **AC-7 [T]** 1001 records -> 413 `BATCH_TOO_LARGE`.
- **AC-8 [T]** `?dry_run=true` reports the verdicts and writes nothing: no brand row, no reference.

## Permissions

- **AC-9 [T]** A principal without `master_data.brands.edit` gets 403 on the brands ingest. (The
  READ and DELETE maps are pinned by the permission-coverage exact-set test.)
- **AC-10 [T]** The migration gives `integration_foundryx_esb` `master_data.brands.view`, `.edit` and
  `.delete`. Running it twice changes nothing, and on a database without that role it is a no-op, not
  an error. Its downgrade is a no-op.

## Read-back and deletions

- **AC-11 [T]** `POST /api/v1/external/read/brands` with the pushed `source_refs` returns
  `code`, `name`, `description`, `is_active` shaped like the ingest.
- **AC-12 [T]** Deletions:
  - a brand no row references -> `deleted`;
  - a brand a product references -> `deactivated` (`is_active` false, reference kept, the product keeps
    its `brand_id`);
  - a brand referenced ONLY by a `projects.brands` row (ON DELETE CASCADE) -> `deactivated`, and the
    `projects.brands` row still exists;
  - an unknown ref -> `not_found`;
  - `?dry_run=true` writes nothing.

## Contract and regressions

- **AC-13 [T]** `GET /api/v1/external/contract` returns `version: "2.3"`, and `entities` includes
  `brands`.
- **AC-14 [T]** A products push with a new `brand_code` still auto-creates the brand with warning
  `brand_created`, and with an existing code still links it. Behaviour is unchanged from 2.2.
- **AC-15 [T]** `IntegrationReferenceService.SUPPORTED_ENTITY_TYPES` equals the old set plus
  `brands`, and the permission-coverage test's three maps equal the served entity set including
  `brands`.

## Slice 2: BL-056, `integration_references.company_id` (plan section 8)

- **AC-16 [T]** Migration: adds `company_id` (nullable, FK companies, CASCADE), replaces the global
  unique with the two partial unique indexes, and backfills every existing scoped row from its entity's
  `company_id`; a `sales_agents` row stays NULL; a scoped row whose entity is gone is removed. Running
  the upgrade twice on an already-migrated database is a no-op.
- **AC-17 [T]** `IntegrationReferenceService(db, company_id=A).link(...)` on a scoped type stores
  `company_id = A`; on `sales_agents` stores NULL. `resolve()` with anchor A does not see a row linked
  under B; with anchor B it does. A scoped `resolve`/`link` with no anchor raises `ValueError`.
- **AC-18 [T]** The same `(source_system, entity_type, source_ref)` can exist once per company: linking
  it under A and under B to two different entities succeeds; linking it twice under A to two entities
  raises `ReferenceConflict`.
- **AC-19 [T]** BL-056 end to end: a products ref linked in company B, pushed under company A ->
  `created`, a new row in A, B's row and reference untouched. `POST /external/read/products` under A
  for a ref linked only in B -> `not_found`. (Replaces AC-A1-7 in `test_external_company_anchor_scope.py`.)
- **AC-19b [T]** Documents: a header `source_ref` linked only in B, pushed under A -> `created` (new
  header row in A, B untouched; `test_ingest_documents.py:782-800`). A ladder ref (`customer_ref`,
  `supplier_ref`, a line's `product_ref`) linked only in B is simply UNKNOWN under A and takes the
  ladder an unknown ref already takes: sent alone -> `retryable`, with that field named in `errors`,
  nothing written; sent WITH a code/name -> the code/name rung applies inside A exactly as for any
  unsynced master (no cross-company peek exists to tell the two apart) (`test_ingest_documents.py:883`, `test_ingest_documents_v2_resolution.py:460,
  :475`). All four replace the old "outside this company anchor" `failed` verdicts. Deletions under A of a ref linked only in B
  stay `not_found` (`test_ingest_deletions.py:435` unchanged).
- **AC-20 [T]** Shared agents: `agent:X` pushed under SRT then under MOCHA -> `created` then `updated`,
  one `sales_agents` row, one reference with NULL `company_id`.
- **AC-21 (gate, not a test)** `tests/test_ingest_ref_collision.py`, `tests/test_ingest_deletions.py`
  and the document-ingest suites stay green with no edits beyond AC-19b (same-company semantics are
  identical).
