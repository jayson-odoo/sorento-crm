# S0 build brief: finance billing documents, model and ingest contract (#1309)

For the orchestrator to hand to one build lane. Plan:
`documentation/plans/finance/PLAN-finance-billing-documents-27sep.md` (round 2, sections 0, 3.1
to 3.3, 3.5, 3.6). UAC: `finance-billing-documents-27sep-acceptance-criteria.md`, slice S0.
Alignment: `alignment/finance-alignment-r2.html`. Written 27 Sep 2026 from the plan branch at
61825309, with `origin/main` at 52b0ac24; line numbers below were read at those commits and must
be re-checked at lane start.

**S0 needs no NDA.** It is backend only, and the replayable fixture stands in for AutoCount.
Nothing in it depends on Q5, Q14 or Q15. Q16 changes one statement in the migration; see
"Permissions".

**Track:** full (new schema, migration, new permissions, new external ingest entity). So:
tester-first (the `tester` writes the red tests below from this brief and the UAC before the
`coder` starts), then `reviewer` **and** `security-reviewer` (the diff adds an external ingest
surface and RBAC slugs), then the DoD gate. A private CI database, as usual for a migration lane.

## 1. Scope, exactly

### 1.1 Schema and migration

One migration, `sorento_crm_backend/alembic/versions/fin_0001_billing_documents.py`, revision
id `fin_0001_billing_documents` (26 chars, under the 32 limit). Its `down_revision` is main's
single head at lane start: measure with `alembic heads`, then run `./scripts/alembic-reparent.sh`
before the PR. Shape copied from `alembic/versions/sales_0001_teams.py`:

1. `CREATE SCHEMA IF NOT EXISTS finance` (as `sales_0001_teams.py:43`).
2. `finance.billing_documents`, columns exactly as plan 3.2, including: `company_id` uuid FK
   `companies.id` NOT NULL; `document_type` varchar(20) NOT NULL with
   `CHECK (document_type IN ('invoice','cash_sale','credit_note','debit_note'))`; `status`
   varchar(20) NOT NULL default `posted` with `CHECK (status IN ('posted','cancelled'))`;
   `doc_date` date NOT NULL; money numeric(15,2); `currency_code` varchar(3) NOT NULL default
   `MYR`; `currency_rate` numeric(18,8) NOT NULL default 1; `customer_id` FK `customers` SET
   NULL; `sales_agent_id` FK `sales_agents` SET NULL; `against_document_id` FK
   `finance.billing_documents.id` SET NULL; `source_system` default `autocount`; `source_ref`
   NOT NULL; `source_modified_at` timestamp (naive UTC); `last_synced_at`, `created_at`,
   `updated_at`. Indexes: unique `(company_id, document_type, source_ref)`;
   `(company_id, document_type, doc_no)` (not unique); `(company_id, doc_date)`;
   `(company_id, sales_agent_id, doc_date)` (the S1 team join); `(company_id, customer_id)`.
   **No CHECK or default on `doc_date` beyond NOT NULL**: no date floor (ruling Q2, UAC S0-22).
3. `finance.billing_document_lines`, columns as plan 3.2: `company_id` NOT NULL; `document_id`
   FK `finance.billing_documents.id` ON DELETE CASCADE NOT NULL; `sales_order_line_id` FK
   `sales_order_lines` SET NULL; `product_id` FK `products` SET NULL; `source_ref` NOT NULL,
   unique `(document_id, source_ref)`.
4. The four permission rows and their grants (1.4).
5. The `finance` row in `app_modules_catalog`: display "Finance", description "Billing
   documents from AutoCount: invoices, cash sales, credit notes and debit notes.", sort `"970"`,
   `is_core = false`, deps `["base", "order"]`, `ON CONFLICT (module_key) DO NOTHING`. **No
   `tenant_modules` row** (dormant until switched on in System > App Store, as `sales` shipped).
6. Downgrade: delete the `tenant_modules` and catalog rows, drop both tables. Keep the schema
   and the permission rows, with the same docstring reasoning as `sales_0001_teams.py:15-17`.

FKs between the two finance tables are schema-qualified (`finance.billing_documents.id`), the
rule `app/models/sales.py:5-7` states for `sales`.

### 1.2 Models

New `sorento_crm_backend/app/models/finance.py`: `SCHEMA = "finance"`; `BillingDocument` and
`BillingDocumentLine` with `__table_args__ = (..., {"schema": SCHEMA})` (the
`app/models/sales.py:35,71-79` pattern), `CompanyScopedMixin` (`app/models/base.py:92-127`), the
header-to-lines relationship with `cascade="all, delete-orphan"`, and the CHECKs declared on the
model so a `create_all` database (CI) rejects what the migrated one rejects. Registered in
`app/models/__init__.py` next to the sales import (`:16`, `:371`).

Audit (plan 3.6): if PR #1299 has merged by lane start, the header stays audited (default-on)
and the lines class declares `__audit_skip__ = "mirror of AutoCount lines, replaced whole on
every push; the header row and integration_references are the trail"`. If #1299 has not merged,
add nothing. Set `__audit_entity_type__ = "finance_billing_documents"` on the header either way
(the `sales.py:52-53` reason: bare table names can collide across schemas).

### 1.3 Ingest contract (plan 3.3, contract 2.6)

- **Schema:** `CanonicalBillingDocument` and `CanonicalBillingDocumentLine` in
  `app/schemas/canonical_documents.py`, subclassing `_Canonical` (`extra="forbid"`,
  `canonical_masters.py:25`), with exactly the keys of plan 3.3.2. Validation (UAC S0-19):
  `document_type` in the four values; `status` in `posted`, `cancelled`; lines at most 2000 and
  no duplicate line `source_ref` (as `canonical_documents.py:185-192`); `total` equals
  `net_total + tax_total` within 0.01; quantity not negative on `invoice` and `cash_sale`;
  money fields accept JSON numbers. No date bound on `doc_date`.
- **Service:** new `app/services/finance/billing_document_ingest_service.py` with
  `BillingDocumentIngestService(MasterRefResolver)` and `BillingDocumentReadService`, taking the
  same constructor and returning the same `ingest()` result shape as `DocumentIngestService`
  (`document_ingest_service.py:322-330`, `:414`). The sibling-service precedent is
  `app/services/shipping_order_ingest_service.py` (`SHIPPING_ORDER_ENTITIES` `:94`, the class
  `:165`, its reader `:1416`); follow it, not `DOCUMENT_SPECS`, because billing documents have no
  adopt-by-number step, no demand class and no cancel-in-place for lines. Export
  `BILLING_DOCUMENT_ENTITIES = frozenset({"billing_documents"})`.
  - Header ladder: `refs.resolve("billing_documents", source_ref)` within the anchor company,
    else create. Per-document SAVEPOINT; dry run rolls back (as `:439-442`, `:492`).
  - Masters through `MasterRefResolver` ref then code: customer, sales agent, product. **Never
    create a master, never retryable**: an unresolved one lands NULL with the code kept and a
    warning `customer_unresolved`, `agent_unresolved` or `product_unresolved` (UAC S0-11). Only
    masters of the anchor company link (UAC S0-14).
  - `against_source_ref`, else `against_doc_no` within the company, fills
    `against_document_id`; an IV or DN landing fills any CN or DN in the company whose
    `against_doc_no` equals its `doc_no` and whose link is NULL (UAC S0-12).
  - `from_line_ref` resolves through the `sales_orders` line refs to `sales_order_line_id`,
    else NULL with `from_doc_type`, `from_doc_no`, `from_line_ref` kept (UAC S0-13).
  - Whole-document replace: lines absent from the push are deleted; a line present keeps its id
    (UAC S0-6). An identical re-push writes nothing and moves no `updated_at` (UAC S0-5).
  - Stale guard: stored and incoming `source_modified_at` both present and incoming older, then
    nothing is written, verdict `unchanged` with warning `stale_ignored` (UAC S0-9).
  - `status: "cancelled"` is an update (UAC S0-8).
  - One `integration_references` row per document (and per line if the SO feed links lines the
    same way), entity type `billing_documents`, carrying `company_id`.
- **Route wiring** in `app/api/v1/external/ingest.py`: add `BILLING_DOCUMENT_ENTITIES` to
  `SUPPORTED_ENTITIES` (`:202-207`); dispatch to `BillingDocumentIngestService` beside the
  shipping-order branch (`:760-770`) and to `BillingDocumentReadService` in read-back
  (`:1025-1033`); the three permission maps (`:83`, `:105`, `:124`):
  `"billing_documents": "finance.billing_documents.edit"` / `.view` / `.delete`. Batch cap, the
  always-200 envelope, `?dry_run=true` and the company anchor (`company_anchor.py:135`) are
  reused unchanged; the anchor's 422s hold (UAC S0-15).
- **Deletions:** `app/services/deletion_service.py` handles `billing_documents` beside the
  shipping-order branch (`:59-61`, `:201-215`): hard delete with lines through the ORM cascade
  when nothing references the document, else set `status = 'cancelled'`, verdict
  `deactivated`, when a CN or DN still points at it (UAC S0-10).
- **Reference allowlist:** add `"billing_documents"` to `SUPPORTED_ENTITY_TYPES`
  (`app/services/integration_reference_service.py:57`).
- **Contract:** `CONTRACT_VERSION = "2.6"` (`ingest.py:235`, with a comment line in the
  version history block above it); `FIELDS_ADDED["billing_documents"]` listing every key of the
  record and line (`contract.py:69`); the three warnings added to `WARNINGS` (`contract.py:172`)
  (UAC S0-18).
- **Contract of record:** append section 12, "billing_documents (contract 2.6)", to
  `documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md`: endpoint, record shape
  (plan 3.3.2), resolution, versions, cancels and deletes (3.3.3, 3.3.4), backfill order and
  "the CRM has no start-date floor; the start date is shared-service configuration" (3.3.5), and
  assumptions A1 to A8 and A10 for the shared service to confirm (A9 is settled by ruling Q6)
  (UAC S0-21).

### 1.4 Permissions (ruling Q9, the sales_0001 precedent)

Four slugs, each inserted into `user_permissions` when absent and granted through
`user_role_permissions` to `admin` and `superadmin` with `ON CONFLICT (role_id, permission_id)
DO NOTHING`, copying `sales_0001_teams.py:35-40,112-135` statement for statement:

| Slug | Name | Used by |
| --- | --- | --- |
| `finance.billing_documents.view` | View Billing Documents | read-back now; menu, list, record, S3 sections later |
| `finance.billing_documents.export` | Export Billing Documents | the list's Export (S2), through the list registry's `export_slug` |
| `finance.billing_documents.edit` | Ingest Billing Documents | `POST /external/ingest/billing_documents` only; no UI |
| `finance.billing_documents.delete` | Delete Billing Documents | `/external/ingest/billing_documents/deletions` only; no UI |

The same four declared in `app/rbac/permission_registry.py` after the sales block (`:818-821`),
with the same comment shape ("Migration `fin_0001_billing_documents` creates these and grants
them to admin and superadmin; declared here as well so a database built with create_all +
sync_permissions has them"). Every other role gets them on the Roles screen.

**Q16 (open).** Build to the recommendation (a): one further, separate statement grants
`.view`, `.edit` and `.delete` to every role holding `scm.sales_orders.edit` (the
`472_ingest_v2_permissions.py` sweep shape), so the feed can push on deploy. Keep it a separate
`bind.execute` with its own comment naming Q16, so answer (b) is a deletion of that one
statement and its test assertion. `.export` is never swept.

### 1.5 Module registration

- Catalog row (1.1 step 5).
- `app/modules/finance/__init__.py` and `app/modules/finance/bootstrap.py` with
  `MODULE_KEY = "finance"` and a docstring in the shape of `app/modules/sales/bootstrap.py`
  (it owns schema `finance`; the invoiced basis in the sales reports reads it, S1).
- `app/modules/runtime/module_manifest.py`: a `"finance"` entry after `"sales"` (`:127`),
  display "Finance", the catalog description, deps `["base", "order"]`.
- `app/modules/runtime/permission_module_map.py`: `"finance": "finance"` (after `"sales"`,
  `:35`).
- `tests/_pg_fixture.py`: translate `finance` everywhere `sales` is hand-listed (`:97`, `:127`,
  `:137`, `:176`, `:227`, `:303`, `:316`, `:325` at 52b0ac24; grep `_sales` to find them all).
  `scripts/bootstrap_env.py` derives schemas from metadata and needs nothing.

### 1.6 Replayable fixture

`sorento_crm_backend/tests/fixtures/finance/billing_documents_v1.json`: one `{"companyCode":
..., "records": [...]}` envelope with six documents (UAC S0-4): one IV with two lines, one line
naming an SO line's integration ref in `from_line_ref`; one CS with no SO; one CN with
`against_doc_no` naming that IV; one DN; one cancelled IV; one USD IV (`currency_rate` not 1,
`local_net_total` in MYR). Refs in `{database}:{IV|CS|CN|DN}:{DocKey}` form, and the CN's DocKey
number equal to the IV's (UAC S0-7). The test seeds its own company, customer, agent, product
and SO line (CI's database has no data); the fixture names them by code and ref only. A second
file `billing_documents_v1_pre2023.json` holds the three dated documents of UAC S0-22.

### 1.7 Glossary and ADR (plan section 8)

Add **Billing document**, **Document type**, **Invoiced basis** to `documentation/CONTEXT.md`
and write `documentation/adr/0013-billing-documents-one-typed-table.md` (one typed table in the
`finance` schema; why a CHECK, not an ENUM or a lookup; sign applied only in the basis). Check
the next free ADR number at lane start.

## 2. UAC ids S0 must satisfy

S0-1 to S0-22, all of them: S0-1 (schema, tables, dormant catalog row), S0-2 (four slugs,
admin and superadmin grants, registry, module map, Q16 sweep), S0-3 (type CHECK), S0-4
(fixture lands, six `created`), S0-5 (replay unchanged), S0-6 (update, line kept or removed),
S0-7 (key includes type), S0-8 (cancel), S0-9 (stale guard), S0-10 (delete or deactivate),
S0-11 (unresolved masters kept, never retryable), S0-12 (CN late link), S0-13 (SO line link),
S0-14 (company isolation), S0-15 (anchor 422), S0-16 (403 per slug), S0-17 (read-back), S0-18
(contract 2.6), S0-19 (per-record validation), S0-20 (1000 x 5 batch), S0-21 (contract section
12), S0-22 (no date floor).

## 3. Files it will touch

New:
- `sorento_crm_backend/alembic/versions/fin_0001_billing_documents.py`
- `sorento_crm_backend/app/models/finance.py`
- `sorento_crm_backend/app/modules/finance/__init__.py`, `bootstrap.py`
- `sorento_crm_backend/app/services/finance/__init__.py`,
  `billing_document_ingest_service.py`
- `sorento_crm_backend/tests/fixtures/finance/billing_documents_v1.json`,
  `billing_documents_v1_pre2023.json`
- the tests in section 4
- `documentation/adr/0013-billing-documents-one-typed-table.md`

Changed:
- `sorento_crm_backend/app/models/__init__.py`
- `sorento_crm_backend/app/schemas/canonical_documents.py`
- `sorento_crm_backend/app/api/v1/external/ingest.py`
- `sorento_crm_backend/app/api/v1/external/contract.py`
- `sorento_crm_backend/app/services/deletion_service.py`
- `sorento_crm_backend/app/services/integration_reference_service.py`
- `sorento_crm_backend/app/rbac/permission_registry.py`
- `sorento_crm_backend/app/modules/runtime/module_manifest.py`
- `sorento_crm_backend/app/modules/runtime/permission_module_map.py`
- `sorento_crm_backend/tests/_pg_fixture.py`
- `documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md` (section 12)
- `documentation/CONTEXT.md`
- `documentation/plans/finance/PLAN-finance-billing-documents-27sep.md` (Status line only)

Not touched: anything under `sorento_crm_frontend/`, `sorento_crm_mcp/`, the reports kernel
(`app/services/reports/`), `app/api/v1/__init__.py` (no `/finance` router yet),
`list_query_registry.py`, `document_ingest_service.py` beyond an import if the resolver needs
one.

## 4. Tests it must add (Postgres only, `tests/_pg_fixture.py`)

Written red by the `tester` first, from this section and the UAC:

| File | Covers |
| --- | --- |
| `tests/test_finance_billing_documents_migration.py` | S0-1, S0-2 (on the migrated database: schema, both tables, NOT NULL `company_id`, catalog row with `is_core = false` and no `tenant_modules` row; the four slugs; admin and superadmin hold all four; a plain role holds none; the Q16 sweep role holds view, edit, delete but not export; re-running the grant statements adds no row), S0-3 (each of the four types inserts, a fifth is rejected by Postgres), plus a registry test that `sync_permissions` on a `create_all` database creates the four and `permission_module_map` maps `finance`. |
| `tests/test_ingest_billing_documents.py` | S0-4 to S0-15, S0-17, S0-19, S0-22 through the route (`TestClient`, an integration API key whose act-as user holds the slugs), on `blank_session` with `finance` translated. S0-5 compares a canonical dump of both tables before and after the replay, and `updated_at`. S0-14 uses two seeded companies. |
| `tests/test_ingest_billing_documents_permissions.py` | S0-16: a caller with `scm.sales_orders.edit` only gets 403 on ingest; `.view` only gets 403 on ingest and deletions but 200 on read; `.export` only gets 403 on all three. |
| `tests/test_ingest_billing_documents_contract.py` | S0-18 (`GET /external/contract` answers `"2.6"`, `fields_added.billing_documents` lists every record and line key, the three warnings present), S0-21 (a text check that section 12 exists in the cross-repo contract and names `billing_documents`). |
| `tests/test_ingest_billing_documents_batch.py` | S0-20: 1000 documents x 5 lines in one push complete inside the route's existing timeout and write 1000 `integration_references` rows. Mark it the way the repo marks its other slow ingest tests, if it does. |

Existing suites that must stay green: `test_ingest_documents*.py`, `test_ingest_deletions.py`,
`test_ingest_contract_v2.py` (its version assertion moves to `"2.6"`),
`test_ingest_parity_s4_contract.py`, `test_external_company_anchor_scope.py`, the RBAC and
module-guard suites. Before push: the pre-push hook's gates (single alembic head, py3.12
compile), then `pytest tests/test_*billing_documents*.py tests/test_ingest_*.py -q`.

## 5. What stays out

- Everything in S1 to S4: the invoiced basis and team grouping (S1, waits on Q14 and Q15), the
  `/finance` router, list-query adapter, menu, list and record pages (S2), SO and customer
  sections (S3), the backfill runbook and tally (S4).
- Any frontend change, including `route-module-map.ts` and the purge registry (S2).
- Any portal change (Q5, staff only, being confirmed).
- A start-date setting or floor in the CRM (ruling Q2).
- Receipts, payments, AR-module documents, tax master, DO FK, ledgers (plan section 7).
- A queue for the ingest (plan section 7 trigger).
- Real AutoCount data, the shared service's sink and anything under the NDA.

## 6. Done means

All S0 tests green on the lane's CI database; one alembic head after the reparent; reviewer and
security-reviewer clean; the PR body names the track (full), the UAC ids S0-1 to S0-22, that
Q16 was built as (a) with the one statement to delete for (b), and that the frontend is
untouched so no browser pass applies. The plan's Status line moves to "S0 in review" and, once
merged, "S0 merged".
