# PLAN - AutoCount `brands` ingest entity (contract 2.3)

**Status:** BUILT 2026-09-12 (owner go; grilled x2 on Opus). Phase 3 review + security review done; fix round in flight; PR next.

**UAC:** `autocount-brands-ingest-acceptance-criteria.md` (alongside).
**Origin:** cross-session brief from foundryx-shared-service-57, their plan
`foundryx-shared-service/documentation/plans/sprint-5/08-autocount-http-source.md` Appendix A
(owner-approved 2026-09-11, decisions D5 / D10 / D15 there; corrections folded in at their commit
962c9eb4).

## 1. Journey

The ESB reads each AutoCount company's ItemBrand list (db1 = Sorento `SRT`, db2 = Mocha `MOCHA`)
and pushes it to Sorento BEFORE products, so every brand exists as a proper master row with an
integration reference, instead of only as the code = name placeholder the product push auto-creates
today. It can read those rows back for its approval diff, retire them through deletions, and gate on
`GET /external/contract` reporting version >= `2.3` with `brands` in `entities`. On a 2.2 Sorento the
ESB stages brand tasks and logs; nothing 422s, so ordering between the two repos is free.

Wire shape the ESB sends (name = code, because AutoCount's ItemBrand descriptions are blank):

```json
{"companyCode": "SRT", "records": [
  {"source_ref": "AED_SORENTO:SORENTO", "code": "SORENTO", "name": "SORENTO",
   "description": "", "is_active": true}
]}
```

## 2. Measured facts (origin/main 1c35299d0; line numbers +-3, the coder re-verifies on the lane base)

| Fact | Where |
| --- | --- |
| Entity set = `ENTITY_SPECS` + documents + shipping orders | `app/api/v1/external/ingest.py:183` |
| Sibling canonical shape `CanonicalProductCategory` | `app/schemas/canonical_masters.py:56-66` |
| Sibling column builder `_category_columns` | `app/services/master_ingest_service.py:330-333` |
| Sibling EntitySpec; NOT NULL defaults table (still needed: an explicit `is_active: null` on update must not hit NOT NULL) | `master_ingest_service.py:596-599`, `:306-327` |
| Default adoption = `resolve_master_by_code`: `upper(btrim())` on both sides, company-filtered, run inside `company_scope`; `Brand` is already in its code/name column maps | `master_ingest_service.py:784, :812-822`; `app/services/rules/master_rules.py:38, :47, :84-107` |
| `normalized_code=True` routes to `_lookup_id` raw SQL, the SHARED-table path built for sales agents | `master_ingest_service.py:442-479, :817-820` |
| Per-record SAVEPOINT: an IntegrityError fails one record, never the batch | `master_ingest_service.py:714-754` |
| `brands`: `brand_code` String(50), `brand_name` String(150), CompanyScopedMixin; CRM-owned `manufacturer`, `website`, `logo_url`, `access_levels` (JSONB, server default). Widths are from the MODEL (aligned to the prod schema in 2d0ced269); no migration creates `brands`, 222 / 302 / 305 only alter it | `app/models/product.py:79-112` |
| **Two** unique indexes on prod, both on RAW values: `(company_id, brand_code)` and `(company_id, brand_name)`. The model declares only the first, so a create_all test DB lacks the name index | `alembic/versions/305_company_composite_unique.py:60, :130-132`; `product.py:105-111` |
| Product push auto-creates brands, code = name = stripped raw value (not upper-cased), no integration reference; it matches code THEN name | `master_ingest_service.py:528-532`; `rules/product_rules.py:151-198` (`:173`, `:176-178`) |
| Manual `create_brand` checks the code EXACTLY, so case-variant duplicates can already exist in one company | `app/services/product_service.py:2433` |
| Brand routing normalises codes (trim + lower), so rewriting a code's case on adoption is safe for routing | `app/services/user_service.py:108-117` |
| FKs to `brands.id`: `products.brand_id` SET NULL; `projects.brands.brand_id` **CASCADE**; `projects.series.brand_id` SET NULL; `user_product_discontinued_scopes.brand_id` **CASCADE**. `team_member_brands.brand_code` is text, no FK | `product.py:177`; `app/models/projects.py:384, :823` (migrations 309:139, 313:35); `app/models/user.py:151` (migration 375:38) |
| Dependents are read from the Postgres catalogue, so all four FKs are probed | `app/services/dependent_probe.py:45-64`; `deletion_service.py:356` |
| Table name `brands` exists in two schemas (`public`, `projects`); raw-SQL paths use the bare name and rely on `public` resolving first (prod does; the test harness puts `projects` last) | `master_ingest_service.py:1024, :1053`; `deletion_service.py:335`; `master_read_service.py:134`; `integration_reference_service.py:275`; `tests/_pg_fixture.py:205-212` |
| Permission maps INGEST / READ / DELETE; exact-set pin that all three equal the served set | `ingest.py:76-119`; `tests/test_external_permission_coverage.py:94-99` |
| Slugs `master_data.brands.{view,add,edit,delete}` in the registry since 2026-03-05; `sync_permissions` runs at startup | `app/rbac/permission_registry.py:203`; `app/main.py:361-371` |
| Integration roles seeded as a copy of Admin's grants; admin bypasses checks, so whether Admin (and so the ESB) holds brand grants is unknown | `app/services/integration_seed.py:18-22, :167` |
| Grant pattern: permission row `(id, slug, name, description, created_at)`; grant `(id, role_id, permission_id, assigned_at)`, `ON CONFLICT (role_id, permission_id)` | `alembic/versions/445_autocount_grant_sweep.py:116-143` |
| Reference allowlist (exact-set pin) | `app/services/integration_reference_service.py:57-76`; `tests/test_integration_reference.py:124` |
| Read-back columns; deletion models + deactivation map | `app/services/master_read_service.py:39-95`; `deletion_service.py:44, :117, :134-140` |
| Contract version + the three `"2.2"` pins (entity-list and FIELDS_ADDED checks are subset checks) | `ingest.py:185-196`; `contract.py:1-34`; `tests/test_ingest_contract_v2.py:150`, `tests/test_ingest_documents_v5_so_po_links.py:208`, `tests/test_ingest_parity_s4_contract.py:79` |

## 3. Decisions

- **D1 Canonical shape.** `CanonicalBrand(_Canonical)` beside `CanonicalProductCategory`:
  `code` (1..50), `name` (1..150), `description?`, `is_active?`, plus the inherited `source_ref` /
  `source_doc_no`. The caps are the column widths, not the siblings' 100 / 255, so an oversize value
  is a per-record `failed` verdict and never reaches the INSERT.
- **D2 EntitySpec.** `"brands": EntitySpec("brands", CanonicalBrand, "brand_code", _brand_columns, Brand)`,
  placed beside `product_categories` (reference masters sync before products). `_brand_columns`
  writes `brand_code`, `brand_name`, and only the present `description` / `is_active`.
  `manufacturer`, `website`, `logo_url` and `access_levels` are never in the written set.
- **D3 Adoption: default path, no new code, code only.** Brief item 5 is met by the existing
  `resolve_master_by_code` (case- and whitespace-insensitive, company-scoped). `normalized_code=True`
  is the wrong path (shared-table raw SQL). **No name rung**: adopting a row by name would rewrite a
  hand-made `brand_code`, and `team_member_brands.brand_code` is a text tag with no FK, so a changed
  code would silently detach those tags. Consequence (see Risk 1): a push whose code differs from a
  hand-made brand that already carries the same name comes back `failed` on the name index, which is
  loud and fixed once in Sorento.
- **D4 NOT NULL defaults.** `_NOT_NULL_DEFAULTS["brands"] = {"is_active": True}`.
- **D5 Permissions.** INGEST `brands` -> `master_data.brands.edit`, READ -> `.view`, DELETE ->
  `.delete`, as every sibling (ingest takes `.edit`, not `.add`).
- **D6 Grant migration: insurance, idempotent, no-op downgrade.** Grants `master_data.brands.{view,
  edit,delete}` to `integration_foundryx_esb`. Permission rows are created only if absent (for databases
  built by alembic alone); grants are `INSERT ... SELECT ... ON CONFLICT (role_id, permission_id) DO
  NOTHING`; a clean no-op where the role does not exist (CI). **Downgrade is a no-op**: the grants may
  well pre-date it (the Admin copy), and removing them could strip access the ESB already had. Only the
  ESB role gets it (the one caller; admin bypasses). Revision id <= 32 chars;
  `./scripts/alembic-reparent.sh` onto main's head at PR time.
- **D7 Allowlist, read-back, deletions.** `SUPPORTED_ENTITY_TYPES += {"brands"}`;
  `_READ_COLUMNS["brands"] = {code: brand_code, name: brand_name, description, is_active}`;
  `ENTITY_MODELS["brands"] = Brand` (+ the `Brand` import at `deletion_service.py:44`) and deactivation
  `("is_active", False)`. The catalogue probe covers all four FKs, so a brand referenced even only by a
  CASCADE row (`projects.brands`, `user_product_discontinued_scopes`) is deactivated, never
  hard-deleted into a cascade.
- **D8 Contract 2.3.** `CONTRACT_VERSION = "2.3"`, with a 2.3 line in BOTH docstrings (`contract.py`
  and `ingest.py:185-196`). `entities` lists `brands` automatically; `FIELDS_ADDED` is untouched. Test
  edits: the three `"2.2"` pins move to `"2.3"`; `test_external_permission_coverage.py` and
  `test_integration_reference.py` exact sets gain `brands`.
- **D9 Products unchanged.** `brand_code` on a product push resolves or auto-creates exactly as today.
- **D10 Backend only.** No UI or user-guide change (the Brands screen already lists brands). Phase 1
  (frontend mock) and the guide-writer step are N/A; the PR says so.

## 4. Out of scope / backlog

- ItemType / ItemClass / ItemCategory: no Sorento home (their BL-SS-201).
- Orphaned `team_member_brands` tags after a brand hard delete: accepted (no FK, text tag).

## 8. BL-056 folded in: `integration_references.company_id` (owner ruling 2026-09-12)

**Owner chose** to close BL-056 in this lane rather than ship Mocha on the ESB's per-company ref
prefix alone. Slice 2 of the same PR.

Measured (origin/main 1c35299d0):

| Fact | Where |
| --- | --- |
| Table: unique `(source_system, entity_type, source_ref)` GLOBAL + unique `(entity_type, entity_id)`; no company column | `app/models/integration_reference.py:65-71`; `alembic/versions/301_integration_references.py:79-84` |
| `resolve()` / `link()` filter on `(source_system, entity_type, source_ref)` only; `origin_of` / `unlink` are entity-keyed | `app/services/integration_reference_service.py:95-171, :189-249` |
| Every one of the 14 company-scoped entity types is `CompanyScopedMixin` (incl. legacy `stock`, `orders`, `order_lines`, `picking_headers`, `picking_lines`); only `sales_agents` is shared | `SHARED_TABLES`, `master_ingest_service.py:272`; models |
| Six constructors, every one holding `company_id` at construction: `master_ingest_service.py:638`, `deletion_service.py:156`, `master_read_service.py:105`, `DocumentReadService` `document_ingest_service.py:1608` (`DocumentIngestService` itself gets `refs` by subclassing `MasterRefResolver`), `shipping_order_ingest_service.py:1341`, `master_ref_resolver.py:89`. No instance spans two companies; the resolver memo is per instance and per batch (`:90-100`) | as listed |
| Partial unique indexes with `postgresql_where` already ship on this model layer (the same IS NULL / IS NOT NULL pair), so create_all and CI pg16 build them; autogenerate is manual-only and schema-filtered | `app/models/access.py:486-495`; `alembic/env.py:49-58` |
| `entity_id` is varchar; every entity id is `UUID(as_uuid=False)`, so the backfill join is `r.entity_id = t.id::text` | `integration_reference.py:37`; `301_integration_references.py:48` |
| `_is_company_scoped` is imported from `master_ingest_service` by `deletion_service.py:52` and `master_read_service.py:33` | as listed |
| Today a ref linked in company B and pushed under A is refused per record ("already claimed outside this company anchor") by THREE `_require_same_company` sites: master ingest, document header, and the v2 ladder's ref rung | `master_ingest_service.py:796, :1013-1029`; `document_ingest_service.py:833-839`; `master_ref_resolver.py:123-163`; pinned by `tests/test_external_company_anchor_scope.py:529-552` (AC-A1-7), `tests/test_ingest_documents.py:782-800, :883`, `tests/test_ingest_documents_v2_resolution.py:460, :475` (AC-V1-8) |
| Postgres: prod pg17, CI `pgvector/pgvector:pg16` | `.github/workflows/deploy.yml:326` |

Decisions:

- **D11 Column.** `integration_references.company_id` UUID NULL, FK `companies(id) ON DELETE CASCADE`.
  Company-scoped entity types carry the anchor company; shared types (`sales_agents`) carry NULL.
  `SHARED_TABLES` and `_is_company_scoped` move to `integration_reference_service.py` (the refs service
  cannot import the ingest service: circular) and `master_ingest_service` re-exports both, so
  `deletion_service.py:52` and `master_read_service.py:33` keep importing from where they do today.
- **D12 Uniqueness.** Drop `uq_integration_ref_source`. Two partial unique indexes, declared on the
  model too (`postgresql_where`) so create_all matches prod:
  `uq_integration_ref_source_company (source_system, entity_type, source_ref, company_id) WHERE
  company_id IS NOT NULL` and `uq_integration_ref_source_shared (source_system, entity_type, source_ref)
  WHERE company_id IS NULL`. Partial indexes rather than `NULLS NOT DISTINCT` so nothing depends on the
  pg version. `uq_integration_ref_entity` stays (one entity, one origin).
- **D13 Backfill in the migration.** For each company-scoped type: `UPDATE integration_references r SET
  company_id = t.company_id FROM <table> t WHERE r.entity_type = '<table>' AND r.entity_id = t.id::text
  AND r.company_id IS NULL`. Scoped rows still NULL afterwards point at a row that no longer exists;
  they are deleted (they are exactly the orphans `resolve()` clears on touch, `:224-233`) and the count
  per entity type is logged and quoted in the PR body. Table names in the backfill stay UNQUALIFIED:
  `sales_orders` / `purchase_orders` exist in `projects` too, and the bare name resolves through
  `search_path` (`public` first on prod), the same rule `dependent_probe.py:19-23` relies on.
  Downgrade: drop the two indexes, drop the column, recreate the global unique; it fails loudly if two
  companies hold one ref by then, which is the right outcome.
- **D14 Service.** `IntegrationReferenceService(db, *, company_id: Optional[str] = None)`. `resolve()`
  and `link()` add a scope predicate: scoped type -> `company_id = :anchor` (a scoped call with no
  anchor raises `ValueError`, since every caller has one); shared type -> `company_id IS NULL`.
  `link()` writes the column. `origin_of` / `unlink` / `is_externally_sourced` / the `by_entity`
  guard are unchanged (entity-keyed). All six constructors pass their `company_id`.
- **D15 Behaviour flip (AC-A1-7 and AC-V1-8 retired).** A ref linked in company B is INVISIBLE
  under anchor A. Three consequences, each deliberate:
  1. Master push: `resolve()` sees nothing in A, adoption by code runs inside A, the record is
     `created` in A, B untouched. BL-056's fix statement.
  2. Document header: same, adopted by number inside A or created.
  3. Document line / master ref on the v2 ladder (`master_ref_resolver.py:123-127`): an unknown ref
     raises `MissingReference` -> the document is **retryable**, not `failed`. Correct from A's view:
     that master has not been synced INTO A yet, exactly the sequencing verdict an unsynced customer
     already gets; the ESB drains it once it pushes the master under A's own prefix. With per-company
     prefixes the case never arises in practice. Ruling 2026-09-12 (fix round 2): NO cross-company
     peek to tell "linked elsewhere" from "unknown" (the coder's first cut added one as
     `MissingReference.unconditional`; removed). A B-only ref sent WITH a code/name takes the
     code/name rung inside A like any unknown ref; the mapping it writes is A's own, which is the
     point of BL-056.
  All three `_require_same_company` sites become unreachable through refs and are removed. Test
  edits: `test_external_company_anchor_scope.py:529-552` (flip to `created`; on `products`, not
  `warehouses`: create_all cannot hold one warehouse code in two companies, see `:483`),
  `test_ingest_documents.py:782-800, :883` and `test_ingest_documents_v2_resolution.py:460, :475`
  (flip to `retryable`, field named in `errors`). `test_ingest_deletions.py:435` and
  `test_external_company_anchor_scope.py:555-568` keep their verdicts (`not_found`).
  Reads: another company's row still reports `not_found` (scoped resolve returns None).
- **D16 Shared agents unchanged.** `agent:{CODE}` pushed by SRT then MOCHA: `created` then `updated`,
  one row, one NULL-company reference (the peer's design rule, plan section 7 item 6). Both link paths
  reach the same shared branch: master ingest `master_ingest_service.py:1087-1094` and the ladder's
  back-create `master_ref_resolver.py:232`, each keyed by `model.__tablename__`.

Risks: the backfill runs one UPDATE per entity type over the whole table (prod ~ hundreds of
thousands of rows across SO/PO lines); index builds hold a lock for the duration. Runs inside the
deploy's migration step like every other DDL here. Row count is measured on the dev copy by the
tester before the PR.

Test edits the tester owns: `tests/test_integration_reference.py` (constructor + scope predicate +
shared NULL), the five flips in D15, `test_ingest_sales_agents.py` (D16). Phase 2 gate (not a test):
`test_ingest_ref_collision.py`, `test_ingest_deletions.py` and the document-ingest suites stay green.

## 5. Risks

1. **A hand-made brand whose code differs from the AutoCount code but whose name matches** (for
   example code `SRT`, name `SORENTO`, against a `SORENTO` / `SORENTO` push). Not adopted (code only),
   the insert hits `uq_brands_company_brand_name`, and the record is `failed`. The product push would
   link the same row by name, so only the brands push is strict. Mitigation: the first prod brands run
   is `?dry_run=true` (in the ESB's S5 runbook), whose `failed` rows name every mismatch; fix the
   Sorento code on the Brands screen, then push.
2. **Case-variant duplicate brands already in a company** (manual create checks the code exactly):
   adoption picks one arbitrarily (`.first()`, no ORDER BY). Pre-flight query before the first push,
   per company, run by the owner on prod:
   `SELECT company_id, upper(btrim(brand_code)), count(*) FROM brands GROUP BY 1, 2 HAVING count(*) > 1;`
   Any row = merge in Sorento first.
3. **Bare table name `brands`** shared with `projects.brands`: correct only while `public` precedes
   `projects` on the search path (true on prod). No change; noted so nobody "fixes" a test by
   reordering the path.
4. **An adopted row loses its auto-created description**: the ESB sends `description: ""`, an explicit
   clear (D14). Intended.

## 6. Owner rulings (2026-09-12)

1. **Go** to build.
2. **BL-056:** fold `company_id` on `integration_references` into this lane (section 8).
3. **Name-match mismatch (Risk 1):** code only, fail loudly, fix the code in Sorento.

## 7. Lane

- Worktree `.claude/worktrees/autocount-brands`, branch `feat/autocount-brands-ingest` off
  origin/main 1c35299d0. Backend only, no dev server. Private Postgres test DB (never the shared dev
  DB).
- Two slices, one PR: S1 brands entity (sections 3-5), S2 BL-056 (section 8). Phase 2: the `tester`
  writes the red tests from the UAC first, then ONE `coder` makes them green, slice by slice. Phase 3:
  `reviewer` + `security-reviewer` (external ingest surface) in parallel, once.
- Pre-PR gate: merge origin/main, alembic reparent, single head. Never merge; the PR number goes to
  the peer.
