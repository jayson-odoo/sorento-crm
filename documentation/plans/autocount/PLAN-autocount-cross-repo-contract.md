# PLAN: AutoCount cross-repo contract (shared-service plan 22, Appendix A)

**Status:** APPROVED 2026-08-30 (brief from the foundryx-shared-service session, Appendix A of
`foundryx-shared-service/documentation/plans/sprint-4/22-autocount-db-etl.md`, ACs AC-22-25..28).
Slices: A1-A4 DONE, review next (A1 = commit `feat(external): company-anchored ingest/read (A1)`
on this branch; a commit cannot carry its own sha, so the hash is in the handoff).
**Branch:** `feat/autocount-cross-repo-contract` off `origin/main` e1ba232ca.
**Worktree:** `.claude/worktrees/autocount-contract` (backend only; no dev server needed).
**UAC:** `autocount-cross-repo-contract-acceptance-criteria.md` alongside.

The shared service's `SorentoSink` (`service_backend/modules/autocount/sinks_sorento.py`) is coded
against the shapes below verbatim. Anything that deviates from Appendix A is listed in section 7
and is reported back to that session.

## 0. What already exists (measured on `origin/main`)

| Thing | State |
| --- | --- |
| `POST /api/v1/external/ingest/{entity}` + `POST /api/v1/external/read/{entity}` | Live for 6 masters (`product_categories`, `units_of_measure`, `warehouses`, `suppliers`, `customers`, `products`). Per-record SAVEPOINT verdicts, always-200, `?dry_run=true`, `MAX_BATCH=1000`. `app/api/v1/external/ingest.py`, `app/services/master_ingest_service.py`. |
| Company anchor | NONE on ingest/read. `MasterIngestService._apply` raw-INSERTs without `company_id` (all 6 masters are `CompanyScopedMixin`; migration 305 makes the column NOT NULL) and `_lookup_id` adopts by code with no company predicate. GRN already has `pin_scope_to_companies` (`app/api/v1/external/utils.py`) + `tests/test_external_company_anchor_scope.py`. |
| Integration principal | `get_external_api_user` -> `{"id", "integration_id", "integration_name", ...}`. `integrations.config_json` is JSONB (`foundryx-esb` row holds `{"base_url": ...}`). |
| Companies | `companies.code` unique (`SRT`, `MOCHA` on dev); `companies.autocount_ref` nullable, empty today. |
| `sales_agents` | Table exists (`app/models/sales_agent.py`), NOT `CompanyScopedMixin`: `company_id` NULL = shared row; unique index `coalesce(company_id, nil)` + `sales_agent`. Slugs `master_data.sales_agents.{view,add,edit,delete}` registered; `integration_foundryx_esb` holds view+edit, only `admin` holds delete. |
| `public.sales_orders` / `public.purchase_orders` | `app/models/order.py:360` / `app/models/procurement.py:627`, both `CompanyScopedMixin`, headers carry `source_system`/`source_ref`/(SO) `source_doc_no`, lines carry `source_system`/`source_ref`. SO statuses in use: `open`, `partially_delivered`, `fulfilled`; PO: `draft`, `active`, `partial`, `received`, `closed`, `cancelled`. Slugs `scm.sales_orders.*` / `scm.purchase_orders.*` exist; esb holds view+edit, only admin holds delete. |
| `IntegrationReferenceService` | `SUPPORTED_ENTITY_TYPES` allowlist did NOT contain `sales_agents` (measured in A2; section 0's original claim was wrong, and `test_integration_reference` pins the set exactly, so A2 adds it to both). Still does NOT contain `sales_orders` / `purchase_orders` (it has legacy `orders`/`order_lines`). `resolve()` returns `str`. A3 adds `sales_orders` + `purchase_orders` (and the exact-set test). |
| Grant migration pattern | `alembic/versions/414_product_set_grant_sweep.py` (create-if-absent slug, sweep grant from a source slug, `ON CONFLICT DO NOTHING`, mirrored downgrade). Head: `444_notify_email_on_mention`. |
| Stale branch | `sorento_crm-autocount` (PR #46, 300 commits behind main) carries an older SO/PO ingester keyed on `so_number = AC-{DocKey}` with wholesale line replacement and no company anchor. Reference only; nothing is cherry-picked. |

## 1. A1 - Company-anchored external ingest (gates everything)

**Resolution order** (one helper, `resolve_company_anchor(db, payload, principal) -> str`, in
`app/api/v1/external/company_anchor.py`):

1. Explicit `companyCode` at the top level of the request body (`{"companyCode": "SRT", "records": [...]}`,
   `{"companyCode": "SRT", "source_refs": [...]}`). Matched against `companies.code`, then
   `companies.autocount_ref`; case-insensitive on both. Unknown code -> 422 `UNKNOWN_COMPANY`.
2. Integration binding: `integrations.config_json ->> 'company_code'` for the calling
   `integration_id`, resolved the same way. A binding AND an explicit code that disagree -> 422
   `COMPANY_ANCHOR_AMBIGUOUS`.
3. Neither -> 422 `COMPANY_ANCHOR_REQUIRED`.

The helper calls `set_company_scope(db, frozenset({company_id}))` so the ORM filter + auto-stamp
agree with the raw SQL below, and returns the id. Inactive company -> 422 `UNKNOWN_COMPANY`.

**Applied to:** `POST /external/ingest/{entity}`, `POST /external/read/{entity}`,
`POST /external/ingest/{entity}/deletions` (A4). Not applied to the other external routers (GRN et al
keep `pin_scope_to_companies`; out of scope).

**MasterIngestService changes** (`company_id` passed into the constructor):

- INSERT path stamps `company_id` for every `CompanyScopedMixin` table. For `sales_agents`
  (shared master) the insert writes `company_id = NULL`: the table's doctrine is "one row serves
  both companies", and partitioning it would split one agent's demand class (model docstring).
- `_lookup_id` adoption is scoped: `WHERE code = :v AND company_id = :cid` for scoped tables,
  `WHERE code = :v AND (company_id IS NULL OR company_id = :cid)` for `sales_agents`.
  `_product_columns` category/UoM lookups use the same scoped helper.
- Ref resolution keyed within company: after `refs.resolve()` returns an id for a scoped table,
  the row's `company_id` is checked; a mismatch is `FAILED` with
  `errors={"source_ref": "linked to a record in another company"}`, never an update.
- `_diff`, `_update` unchanged (they address by id).

**MasterReadService:** `read` resolves within the anchor the same way; a ref whose row belongs to
another company reports under `not_found`.

**Tests** (`tests/test_external_company_anchor_scope.py` EXTENDED, plus
`tests/test_master_ingest_routes.py` updated to send `companyCode`):

- ingest without an anchor -> 422 `COMPANY_ANCHOR_REQUIRED`; with unknown code -> 422; with
  integration binding and no body code -> 200.
- NULL-company regression: a created warehouse carries the anchor's `company_id`.
- Cross-company adoption blocked: the same code in company B, ingest anchored to A creates a new A
  row and leaves B's untouched. Pinned on `products`, not `warehouses`: `Warehouse.warehouse_code`
  still carries the pre-305 GLOBAL `unique=True` in the model, so a schema built by `create_all`
  cannot hold one code in two companies, while `Product` was brought into step with migration 305's
  composite. That model drift is real and out of scope here - it bites only schemas built from the
  models, never production.
- Cross-company ref: a source_ref linked to a B row, pushed under A -> `failed`, row unchanged.
- read under A for a ref that resolves to a B row -> `not_found`.

## 2. A2 - `sales_agents` EntitySpec

- `CanonicalSalesAgent(_Canonical)`: `code` (1..100), `description` (<=255), `is_active` (default
  true), `person_label` (<=100, optional).
- `EntitySpec("sales_agents", CanonicalSalesAgent, "sales_agent", _sales_agent_columns)`; columns
  written: `sales_agent`, `description`, `is_active`, `person_label`. `internal_note`, `follow_up`,
  `demand_class`, `location_group`, `source` are never in the column set, so a re-sync cannot touch
  them. Code stored upper-cased + trimmed (matches `sales_agent_service`).
- `_READ_COLUMNS["sales_agents"]` = code/description/is_active/person_label.
- `INGEST_PERMISSIONS["sales_agents"] = "master_data.sales_agents.edit"`,
  `READ_PERMISSIONS[...] = ".view"`, `DELETE_PERMISSIONS[...] = ".delete"`.
- Migration `445_autocount_grant_sweep` (shortened from `445_autocount_contract_grant_sweep`:
  alembic's own `alembic_version.version_num` is `varchar(32)` and that id was 34 characters,
  which `test_alembic_revision_ids` catches): sweep `master_data.sales_agents.delete`,
  `scm.sales_orders.delete`, `scm.purchase_orders.delete` onto every role holding the matching
  `.edit` slug (measured: for the six existing masters the `.edit` and `.delete` holder lists are
  identical, so this is the shape the surface already has).

## 3. A3 - Document ingest (SO + PO)

Endpoints: `POST /api/v1/external/ingest/sales_orders`, `POST /api/v1/external/ingest/purchase_orders`,
read-back `POST /api/v1/external/read/sales_orders|purchase_orders`. Same envelope, same verdicts,
same `dry_run`. `DocumentIngestService` in `app/services/document_ingest_service.py`; targets
`public.sales_orders` + `public.sales_order_lines`, `public.purchase_orders` + `public.purchase_order_lines`
(`app.models.order.SalesOrder`, `app.models.procurement.PurchaseOrder`; NEVER the `projects.*`
tables of the same name).

**Record shape (SO):**

```json
{
  "source_ref": "SO:1234",              // AutoCount DocKey, header idempotency key
  "so_number": "SO-000123",            // AutoCount DocNo; the adopt-by-number key on first sync
  "customer_ref": "DEBTOR:300-R009",   // integration ref of the customer (optional)
  "sales_agent_ref": "AGENT:SEAN I",   // integration ref of the sales agent (optional)
  "doc_date": "2026-08-30",
  "requested_delivery_date": "2026-09-15",
  "status": "open",                    // canonical: open | partial | fulfilled | closed | cancelled
  "internal_note": "...",
  "lines": [
    {
      "source_ref": "SO:1234:1",       // AutoCount DtlKey, per-line key
      "product_ref": "ITEM:ABC-1",     // integration ref of the product (REQUIRED to resolve)
      "warehouse_ref": "LOC:BRW",      // integration ref of the warehouse (optional)
      "qty_ordered": 10, "qty_delivered": 4,
      "unit_price": 12.5, "discount": 0, "line_total": 125,
      "uom": "PCS", "required_date": "2026-09-15"
    }
  ]
}
```

PO is the same with `po_number`, `supplier_ref`, `issue_date`, `expected_date`, `currency`, lines with
`qty_ordered`, `qty_received`, `unit_cost`, `discount`, `line_total`, `uom`, `currency`, `expected_date`.
`extra="forbid"` on every model.

**Header ladder:** `refs.resolve("sales_orders", source_ref)` (within company) -> adopt by
`so_number` within company where the row has no integration reference (a number already linked to
another ref is `failed`, `ReferenceConflict`) -> create. On create `source_system='autocount'`,
`source_ref`, `source_doc_no = so_number`, `company_id = anchor`.

**Master refs:** `customer_ref`/`supplier_ref`/`sales_agent_ref`/`product_ref`/`warehouse_ref` are
integration references of the respective master entity types; an unknown one raises
`MissingReference` -> the whole record is `retryable`, nothing written. A missing OPTIONAL ref key
(absent/null) leaves the FK NULL; a present-but-unknown ref is retryable.

**Status mapping** (canonical -> Sorento): SO `open->open`, `partial->partially_delivered`,
`fulfilled->fulfilled`, `closed->closed`, `cancelled->cancelled`. PO `open->active`,
`partial->partial`, `fulfilled->received`, `closed->closed`, `cancelled->cancelled`. Unknown string
-> `failed` (`errors={"status": ...}`). Cancelled is an UPDATE; the row and its lines stay.

**Lines:** upsert by `(header_id, source_ref)` on the line table's `source_ref` column
(`source_system='autocount'`); lines of the header whose `source_ref` is not in the payload are
DELETED (including ref-less lines an earlier extract import created - the push is authoritative).
`line_status` = `cancelled` when the header is cancelled, else `fulfilled` when
`qty_delivered >= qty_ordered > 0`, else `open`. Every line row carries `company_id = anchor`.

**Read-back** returns the header fields in canonical names plus `lines[]` in the same shape, with
`entity_id` per header and per line. A master the header points at that carries no integration
reference reads back as `null` rather than as an invented ref, and a stored status outside the
canonical five (a locally raised PO sits in `draft`) reads back as itself.

**As built.** `DocumentIngestService` is parameterised by two `DocumentSpec` instances and exposes
the SAME constructor and `ingest()` signature as `MasterIngestService`, so the existing
`POST /external/ingest/{entity}` picks one on the entity name and there is no second router;
`DocumentReadService` mirrors `MasterReadService.current_state` on the read side.
`IngestOutcome` / `IngestResult` / `RecordResult` / `MissingReference` / `_field_errors` /
`_value_changed` / `_lookup_id` / `_is_company_scoped` are imported from the master service, not
forked. The writes go through the ORM models rather than raw SQL (the master service's shape):
`sales_orders`, `sales_order_lines`, `purchase_orders` and `purchase_order_lines` all exist a
SECOND time in the `projects` schema, so an unqualified table name in raw SQL is answered by
`search_path` - and `public.`-qualifying it instead would point a scratch-schema test at the real
database. The anchor is still stamped by hand on top of the ORM auto-stamp. Header-level diff only
on a dry run; lines are not diffed (a per-line before/after over a 200-line order buries the one
change that matters).

## 4. A4 - Deletion endpoint

`POST /api/v1/external/ingest/{entity}/deletions`, body `{"source_refs": [...]}` (+ optional
`companyCode`), `?dry_run=true`, batch <= 1000 (413 above). Guard: the router-level ingest guard
(`.edit`) plus a route-level `require_external_permission_for_path(DELETE_PERMISSIONS)` (`.delete`).
Entities: the 7 masters + `sales_orders` + `purchase_orders`.

Per ref, inside its own SAVEPOINT:

1. `refs.resolve()` within company -> none -> `not_found`.
2. Dependent check: every FK in `pg_catalog` that references the target table (cached per table
   per process) is probed with `SELECT EXISTS (... WHERE fk_col = :id)`. For documents the own
   line table is skipped as a referrer and the LINE table's referrers are probed instead. This
   is deliberate: `customers -> sales_orders.customer_id` is `ON DELETE SET NULL`, so a bare
   `DELETE` would "succeed" by orphaning every order. A dependent anywhere = no hard delete.
3. No dependents -> `DELETE` (lines cascade) -> `refs.unlink()` -> verdict `deleted`.
4. Dependents (or an `IntegrityError` on the DELETE) -> fallback update -> verdict `deactivated`:
   `is_active=false` for masters; `products`: `is_discontinued=true` and `is_active` untouched
   (`product.py:177`); `sales_orders`/`purchase_orders`: `status='cancelled'` (the document
   equivalent; they have no `is_active`). The integration reference stays linked.
5. Anything else -> `failed` + `errors`.

Response: `{"dry_run": bool, "summary": {"total","deleted","deactivated","not_found","failed"},
"records": [{"source_ref","outcome","entity_id", "errors"?}]}`.

**As built.** `DeletionService` (`app/services/deletion_service.py`) takes the SAME constructor as
the two ingest services and is mounted on `ingest_router` as `POST /{entity}/deletions`, so the
router's `.edit` guard applies and the route adds its own `.delete` one. `/{entity}` matches a
single path segment, so the two routes cannot shadow each other - pinned by a test that ingests a
warehouse after the deletion route exists. Body guards, batch cap and anchor resolution run in the
same order as the ingest, for the same reason.

Three details the section above did not fix:

* A reference resolving into ANOTHER company reads as `not_found`, not as a failure. It is not this
  caller's row, and distinguishing the two would confirm that a record exists somewhere it may not
  look.
* The document line probe is ONE query per referrer, joining the referrer to the line table on the
  header's FK, rather than loading the line ids and probing each. Same question, no array binding,
  and it does not grow with the line count.
* The referrer list is NOT cached. One catalogue query per record is cheap at this batch size; the
  trigger for caching is a deletion batch appearing in the slow-query log, and it is written down in
  the service rather than built now.

## 5. Order of work

A1 (tests first, then code) -> A2 -> A3 -> A4, all on one branch. Each slice: pytest on the touched
suites + `tests/test_external_permission_coverage.py`; full external suite before the PR. Report to
the shared-service session after A1 and after A4.

## 6. Out of scope

- Re-anchoring the other external routers (GRN/SPO/packing-list keep `pin_scope_to_companies`).
- The stale `sorento_crm-autocount` branch (PR #46) and its 12-entity mirror.
- Frontend. No UI changes; the mirror is read through existing pages.

## 7. Deviations from Appendix A (reported to the shared-service session)

1. `companyCode` is a top-level body field on all three calls, matched against `companies.code`
   then `companies.autocount_ref` (case-insensitive). Integration binding = `config_json.company_code`.
2. Document status vocabulary is fixed here: `open | partial | fulfilled | closed | cancelled`.
3. Document lines carry `product_ref` / `warehouse_ref` (integration refs), not codes.
4. Deletion of a document with dependents = `status='cancelled'` (verdict `deactivated`); there is
   no `is_active` on documents.
5. The dependent check is a FK probe, not "let the DELETE fail": SET NULL FKs would otherwise let a
   customer with orders hard-delete.
7. Document quantities and money read back as JSON NUMBERS, not strings: they are `Decimal` in the
   model and FastAPI's encoder renders a Decimal as a number. Same as the masters' `list_price` /
   `credit_limit` on this surface today, so it is stated rather than changed - but a sink that
   round-trips a float through a 4-dp quantity has to say so, not assume it.
8. A document line is addressed by the line's own `source_ref` (AutoCount's DtlKey). Two lines
   carrying the same one inside a single record is a validation failure, not last-one-wins.
6. `sales_agents` rows are created SHARED (`company_id NULL`). Two companies pushing the same agent
   code under different source_refs: the second push is `failed` (`ReferenceConflict`, the row is
   already linked). ACCEPTED by the shared service 2026-08-30: it mints the agent ref UNQUALIFIED
   as `agent:{CODE}` (upper/trim), never company-qualified, so every company's push hits the same
   ref -> same shared row -> `updated`. Sorento side must therefore: (a) exempt shared tables from
   the A1 cross-company ref check (a NULL `company_id` row is visible to every anchor), (b) let
   `link()` re-link the same (source_system, entity_type, source_ref) from a different
   `integration_id` in place (it already does: it overwrites `integration_id`/`last_synced_at`),
   (c) pin this with a test: same `agent:X` pushed under company A then company B -> `created` then
   `updated`, one row. Master refs on document lines stay `{DatabaseName}:{key}` as pushed.
