# PLAN: finance module, billing documents from AutoCount through the shared service (#1309)

Status: **draft, round 1, awaiting the owner's answers to section 9 (Q1 to Q13).** Planning half
of the pipeline only (journey, grill questions, UAC, plan, slices, tickets); nothing is built.
Track: full (new module and schema, migration, new permissions, a new external ingest entity).
Domain: finance. Classification: **MODULE `finance`** (installable per tenant: another AutoCount
customer would turn it on; `app_modules_catalog` row + `require_module_enabled_with_api_key`).
Schema: **`finance`**, tables without a `finance_` prefix (the ADR-0011 precedent the `sales`
module followed, `sorento_crm_backend/alembic/versions/sales_0001_teams.py:5-6,43`).
UAC: `finance-billing-documents-27sep-acceptance-criteria.md` alongside (the contract; the journey
J1 to J9 lives there). Alignment page with the mockups:
`alignment/finance-alignment-r1.html`.
Branch: `claude/finance-billing-documents-plan-jks6fx` (the cloud session is pinned to that name;
the brief named `claude/finance-billing-documents-plan`), off `origin/main` 9751e55d.

Paths below are relative to the repo root. Backend paths start `sorento_crm_backend/`, shortened
to `be/` in the tables; frontend `sorento_crm_frontend/` to `fe/`.

## 1. In plain words (for the owner)

**What a billing document is here.** Any document AutoCount raises that bills or un-bills a
customer: an **invoice** (IV), a **cash sale** (CS, an invoice paid on the spot, often with no
sales order), a **credit note** (CN, money given back: a return, a price correction) and a
**debit note** (DN, an extra charge after the invoice). They all have the same shape: a header
(number, date, customer, agent, currency, subtotal, tax, total) and lines (item, quantity, price,
discount, tax code, line total).

**Why one table of typed documents, not one table per type.** Because they are the same shape
and every question you will ask crosses them: "sales this month" is IV plus CS plus DN minus CN;
"what did this customer get billed" is all four; "which credit notes hit this invoice" joins two
types. With one table, each of those is one query with a type filter. With four tables, every
report, list, search and permission is written four times and the four drift apart. This is also
how ERPs do it (Odoo keeps invoices, credit notes and refunds as one "move" with a type). A
**type** column, limited to the four known values, says which document it is, and the sign
(a CN subtracts) is decided in one place, the sales query.

**What AutoCount will send.** After the NDA, AutoCount opens its billing tables to the shared
service. The shared service pushes each document, whole, to the same CRM endpoint that already
receives your sales orders and purchase orders every day, naming Sorento or Mocha. Pushing the
same document twice changes nothing; a document edited in AutoCount is pushed again and replaced;
a cancelled one stays visible and stops counting; history comes in through the same door, in
batches, from a start date you choose (Q2).

**What the CRM will show.**
1. On **Sales > Yearly comparison and Sales report** (PR #1269), a third basis, **Invoiced**:
   invoices plus cash sales minus credit notes, excluding tax, by document date. That is what the
   scout on #1269 found the AutoCount PDF counts, and the only basis that can tally with it.
2. A new **FINANCE > Billing Documents** list and a record page per document, read only
   (AutoCount is the book of record; nobody types an invoice in the CRM).
3. On a **sales order** and a **customer**, the billing documents that belong to them.

Nothing about ledgers, ageing, statements or payments is built (section 7 names what would start
each).

## 2. Measured facts (read only, at 9751e55d unless marked)

### 2.1 Why this module: the scout on #1269

- The scout comment "Scout: why Yearly comparison and the AutoCount PDF do not tally" (PR #1269,
  comment 5852162391, 27 Sep 03:04Z) ranks the causes: order month instead of invoice month
  (largest), tax included (up to x1.10), credit notes not netted, cash sales with no SO, project
  billing lag. Its recommendation (section 5 there): "to tally with AutoCount, the report needs an
  **invoiced** basis: IV plus CS minus CN, excluding tax, filed by invoice date ... No choice of
  Ordered or Delivered, or of date, on SO data can reproduce causes #1, #3 and #6."
- It also found the PDF's PROJECT TEAM row is "a named group of people whose membership is stated
  per month" (the "Nov'24 Whole project team sales 16pax" footnote), i.e. an agent grouping, not
  `demand_class`. That is Q8.
- The owner's ruling that followed (PR #1269 comment 5853731536, 27 Sep 15:20 MYT): #1269 ships on
  the sales-order basis as built; the invoiced basis becomes this module.
- The retail sales reports plan (on the #1269 branch at 0932c995,
  `documentation/plans/sales/PLAN-retail-sales-reports-26sep.md`) section 4, "Basis: sales orders,
  not invoices" (:1254-1278), names the trigger: "if S0 shows a monthly gap above the tolerance
  ... an AutoCount IV (invoice) ingest lane is planned (cross-repo ESB work plus one
  `sales_invoices` table), and the reports gain an `invoiced` basis on the same query layer"
  (:1271-1274); round 3 turned the trigger into "the owner asks" (:1276-1278, repeated in section
  7 :1571-1572). The owner has now asked. This plan widens "one `sales_invoices` table" to one
  typed billing document table, because the basis needs CS and CN as well as IV (section 3.1).
- Same plan, 2.2 (:1150-1154): "No customer invoice. The only invoice tables are supplier
  proformas ... No AutoCount IV (invoice) document is ingested anywhere." Still true on main (2.3).

### 2.2 The AutoCount feed that exists (reused, not copied)

| Thing | Where | What it does |
| --- | --- | --- |
| Ingest route | `be/app/api/v1/external/ingest.py:706-720` | `POST /api/v1/external/ingest/{entity}`, sync `def`, `Depends(get_external_api_user)` (:720); dispatches documents to `DocumentIngestService` (:769-770), one commit per batch (:797), post-write hooks (:802). |
| Deletions, read-back | `ingest.py:833-841`, `:981`, `:1029-1033` | `/{entity}/deletions` (extra `.delete` guard :839); `/read/{entity}` via `DocumentReadService`. |
| Permission maps | `ingest.py:82-103`, `:104`, `:122` | `INGEST_PERMISSIONS` etc. reuse UI slugs; `"sales_orders": "scm.sales_orders.edit"` (:96). |
| Contract version | `ingest.py:235`, `be/app/api/v1/external/contract.py:205` | `CONTRACT_VERSION = "2.5"`, served by `GET /external/contract`. |
| Batch cap | `ingest.py` `MAX_BATCH = 1000` | 413 above. |
| Mounting | `be/app/api/v1/__init__.py:227`, `be/app/api/v1/external/__init__.py:62-77` | `/external/ingest` guarded per entity by `require_external_permission_for_path`. |
| Auth | `be/app/dependencies.py:491` | `X-API-Key` -> `integration_api_keys` -> the integration's `act_as_user_id`. |
| Company anchor | `be/app/api/v1/external/company_anchor.py:135` | `resolve_company_anchor`: body `companyCode`, else `integrations.config_json.company_code`; matched on `companies.code` then `companies.autocount_ref`; 422 `COMPANY_ANCHOR_REQUIRED` / `UNKNOWN_COMPANY` / `COMPANY_ANCHOR_AMBIGUOUS` / `COMPANY_BINDING_INVALID`; then `set_company_scope`. |
| Document service | `be/app/services/document_ingest_service.py:322`, `:414`, `:445`, `:558` | `DocumentIngestService(company_id=...)`, `ingest()`, per-document SAVEPOINT (:492), dry run rolls back (:439-442). `DOCUMENT_SPECS` :209, entity set :292. |
| Idempotency | `document_ingest_service.py:884-929` | `_header`: `refs.resolve(entity, source_ref)` -> adopt by number within company -> create. No `ON CONFLICT`: ORM on purpose, because `projects.sales_orders` shadows `public.sales_orders` (:43-51). |
| Lines | `document_ingest_service.py:1377`, `:1543-1561`, `:1590` | Upsert by the line's `source_ref` (DtlKey); a line absent from the push is deleted, or cancelled in place when referenced; xlsx-era lines adopted. |
| Versioning | none | No modified-at or sequence on the schemas; each push is the whole truth, last write wins (:8-13). |
| Provenance | `document_ingest_service.py:121`, `:1028-1031`, `:999-1001` | `SOURCE_SYSTEM = "autocount"`; header `source_system`/`source_ref`/`source_doc_no`; `debtor_code` from `customer_code`. Ref format `{database}:{DocKey}:{DtlKey}` (`be/app/schemas/canonical_documents.py:130`). |
| Payload base | `be/app/schemas/canonical_masters.py:25`, `canonical_documents.py:162`, `:185-192`, `:196` | `_Canonical` `extra="forbid"`, `source_ref` required; documents cap lines at 2000 and reject duplicate line refs; `CanonicalSalesOrder` has **no tax, tax code or currency**. |
| Deletion | `be/app/services/deletion_service.py`, `be/app/services/dependent_probe.py` | Hard delete when nothing references the row, else `cancelled` (verdict `deactivated`). |
| Ref table | `be/app/models/integration_reference.py:30-103` | `entity_type`, `entity_id`, `company_id` :44, `source_system` :50, `source_ref` :55, `source_doc_no` :57; unique on `(source_system, entity_type, source_ref, company_id)` (:76-92); allowlist `SUPPORTED_ENTITY_TYPES` (`be/app/services/integration_reference_service.py:57`), `link()` :142. |
| Weekly xlsx upload | `be/app/services/scm/outstanding_import_service.py:2203-2233` | SO/PO only, `source_system="scm_upload"`, adopts other feeds' headers; no tax (the SO money is `total_inc`). Not a billing path. |
| Demand class | `be/app/services/scm/demand_class.py:73-133` | `classify_document`: stored order type -> stated -> agent's class -> customer segment. Classifies SO demand only; no invoice link. |

(The brief named `app/services/outstanding_import_service.py` and `app/scm/demand_class.py`; both
live under `app/services/scm/`.)

### 2.3 What is missing

- No billing document of any type: zero hits for credit note, debit note, cash sale (as a
  document), ARInvoice, receipts or payments in `be/app`. `cash_sales` exists only as a purchase
  request `sales_type` value (`be/app/models/procurement.py:1009`).
- No tax master: `be/app/schemas/autocount_mirror.py:4` names `tax_codes` as a future mirror table;
  no model. The archived integration plan said the same (`documentation/plans/_archive/autocount/PLAN-autocount-integration.md:349`).
- `sales_orders` carries no currency, tax or totals (`be/app/models/order.py:410-500`);
  `sales_order_lines.line_total` is AutoCount "Total (Inc)", tax inclusive (`order.py:523-526`).
- The DO table `orders` (`order.py:286-357`) has money columns (`subtotal_amount`, `tax_amount`,
  `total_amount` :326-329) but is not fed by the ESB and its money is documented as unusable
  (retail plan 2.2 :1150-1153). So "link to the delivery order" can only be the DO number as sent.
- `customers.ar_outstanding` / `ar_ageing_json` / `ar_as_of` (`order.py:134-139`) are declared
  "ingested from AutoCount (D23)" but nothing writes them. Section 7.
- The portal (`fe/app/(auth)/portal/`) shows no orders or invoices today; its only document form
  is the price tag request.

### 2.4 Module, permission and UI patterns (the precedent)

| Pattern | Where |
| --- | --- |
| Catalog + enablement | `be/app/models/app_modules.py:10-43` (`app_modules_catalog`, `tenant_modules`); manifest `be/app/modules/runtime/module_manifest.py:127-132` (the `sales` entry), `:146`. |
| Module migration | `be/alembic/versions/sales_0001_teams.py`: `CREATE SCHEMA IF NOT EXISTS sales` :43; tables `schema="sales"` :45-109; permissions into `user_permissions` :112-122; grants via `user_role_permissions` to admin/superadmin :123-135; catalog row `ON CONFLICT DO NOTHING`, sort `"960"` :137-152; no `tenant_modules` row, so dormant (:12-13); downgrade keeps schema and permission rows (:15-17). |
| Slugs | `be/app/rbac/permission_registry.py:11-18` (`_crud`), `:821` (sales); `sync_permissions` :824, run at boot `be/app/main.py:399-402`. Prefix map `be/app/modules/runtime/permission_module_map.py:35`. |
| Route guards | `be/app/dependencies.py:313` `require_permission`; `be/app/modules/runtime/guards.py:62` `require_module_enabled_with_api_key`; mount `be/app/api/v1/__init__.py:105-110` (sales). |
| Model schema pin | `be/app/models/sales.py:35` `SCHEMA = "sales"`, `__table_args__ = (..., {"schema": SCHEMA})` :71-79. |
| Test fixture schemas | `be/tests/_pg_fixture.py:127,137,176,227,316,325` hand-list `sales`; `finance` must be added at each. `be/scripts/bootstrap_env.py:78-81` derives schemas from metadata. |
| List registry | `be/app/services/list_query_registry.py:81-103` (`ListQueryResourceAdapter`, the `orders` example), `get_adapter` :178. |
| Menu | `fe/config/menu.config.tsx:78-100` (SALES heading, per-child `moduleKey`, comment :80-83); duplicated in `MENU_SIDEBAR_COMPACT` (~:1848-1865); types `fe/config/types.ts:18-25`; route guard `fe/lib/route-module-map.ts:31`; purge registry `fe/modules/registry.ts:68`. |
| Record with line tabs | `fe/app/(protected)/user-management/users/[id]/layout.tsx:45-63` (route tabs), `:151-157` (`PageHeader`, hero), `:158-174` (`TabsList variant="line"`). |
| DataGrid list | `fe/app/(protected)/sales/teams/components/SalesTeamsView.tsx:169` (`tableLayout` fixed, resizable). |
| Primitives | `fe/components/common/SearchableSelect.tsx`, `SearchableMultiSelect.tsx`, `PageHeader.tsx`, `RecordNavigation.tsx`, `fe/components/ui/badge.tsx` (`status` prop :158), `fe/lib/status-badge.ts:84`. Design language `documentation/reference/DESIGN-LANGUAGE.md` sections 4 (:150, DataGrid rule :155) and 7 (:204). |
| Company model | `be/app/models/company.py:18-35` (`code`, `autocount_ref`); `CompanyScopedMixin` `be/app/models/base.py:92-127`. |

**Precedents named in the brief, and what they are.** Neither PR #1299 (audit standard S0) nor PR
#1305 (supplier cost price lists) creates a Postgres schema; both are open, both work in `public`.
What they contribute:
- #1299 makes auditing **default-on** for every mapped table unless it declares
  `__audit_skip__ = "<reason>"`, adds `__audit_parent__` and `@audit_event("domain.entity.verb")`,
  and writes nothing on a touch-only or no-change update (PR body). Section 3.6 applies it.
- #1305 is the latest shape of a new domain with its own migration prefix (`cpc1_`, `cpc2_`), a
  `module.resource.action` slug trio seeded to the roles that need it, and a list plus `[id]` record
  page (`procurement-management/cost-price-uploads/`). The migration prefix `fin_` follows it and
  `sales_0001`.
- The actual own-schema precedents are `sales` (above), `scm` (`be/alembic/versions/273_scm_module_schema.py:42`),
  `dealer_kit` (`309_dealer_kit_module.py:93`) and `projects` (`354_projects_schema_move.py:362`,
  ADR-0011).

### 2.5 The shared service's AutoCount plans

**Unreachable from this lane.** This session's GitHub access is scoped to
`jayson-odoo/sorento-crm` only, so `jayson-odoo/foundryx-shared-service`
(`documentation/plans/sprint-4/22-autocount-db-etl-acceptance-criteria.md`,
`16-autocount-mapping-formulas.md`, `13-autocount-esb-acceptance-criteria.md`) could not be read,
and no local copy exists. What this repo quotes of them: plan 22's Appendix A is the SO/PO
contract (`documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md:1-14`, sink
`service_backend/modules/autocount/sinks_sorento.py`); plan 13 is the original ESB plan
(`documentation/plans/_archive/autocount/PLAN-autocount-integration.md:4`); plan 16 is referenced
nowhere in this repo. **So the contract in 3.3 is planned from the CRM side, and every AutoCount
field it names is an assumption (A1 to A9, section 3.3.6) for the shared-service session to confirm
or correct**, the same way that session corrected Appendix A (cross-repo contract section 7).

## 3. Design

### 3.1 One table of typed documents

- **`finance.billing_documents`** (header) and **`finance.billing_document_lines`**. Not
  `sales_invoices` (the retail plan's name): the invoiced basis needs CS and CN too, and a DN is
  the same shape. The uninstall test (PRINCIPLES "Modular architecture") would put durable records
  in `public`; the owner asked for a `finance` schema, and ADR-0011 plus the `sales` module already
  moved durable records into their module's schema, with row-level purge and `DROP SCHEMA` never
  issued. Normal cross-schema FKs to `public` (PRINCIPLES :197-203).
- **`document_type`**: `varchar(20)` with a CHECK constraint over `invoice`, `cash_sale`,
  `credit_note`, `debit_note`. Why these four: they are AutoCount's Sales-module billing documents
  (the ones that carry item lines and feed its sales analysis), and they are exactly the four the
  owner and the scout name. Why a CHECK and not a Postgres ENUM or a lookup table: the list is
  closed and fixed by AutoCount, the repo's precedent for a closed vocabulary is a CHECK built in
  code (`be/app/services/scm/demand_class.py:62` `check_constraint_sql`), and adding a type later
  is one migration replacing the constraint, where an ENUM cannot drop a value and a lookup table
  is a table for four strings. Not in the list, each with its trigger in section 7: AutoCount's
  AR-module documents (AR Invoice, AR Credit Note, AR Debit Note: non-stock, no item lines),
  receipts / payments, refunds, deposits, delivery returns (a stock movement, not a bill).
- **Sign lives in one place.** Amounts are stored as AutoCount prints them (positive on a CN). The
  sign is applied only in the invoiced-basis expression (3.4). A stored negative would make every
  list and record page flip it back.

### 3.2 Columns

`finance.billing_documents` (`CompanyScopedMixin`, `company_id` NOT NULL):

| Column | Type | From / why |
| --- | --- | --- |
| `id` | uuid pk | |
| `company_id` | uuid FK `companies` NOT NULL | the anchor (2.2) |
| `document_type` | varchar(20) CHECK | 3.1 |
| `doc_no` | varchar(50) | AutoCount DocNo; display and search; indexed `(company_id, document_type, doc_no)`, **not unique** (AutoCount can renumber, `PLAN-autocount-integration.md:259`) |
| `doc_date` | date NOT NULL | the basis date; indexed `(company_id, doc_date)` |
| `customer_id` | uuid FK `customers` SET NULL | resolved from `customer_ref` / `customer_code` |
| `debtor_code` | varchar(64) | as sent, kept when unresolved (the `sales_orders.debtor_code` rule, `order.py:423-428`) |
| `sales_agent_id` | uuid FK `sales_agents` SET NULL | resolved from `agent_code`; needed for the people grouping (Q8) |
| `currency_code` | varchar(3) NOT NULL default `MYR` | A5 |
| `currency_rate` | numeric(18,8) NOT NULL default 1 | A5 |
| `net_total` | numeric(15,2) | after discount, excluding tax, document currency |
| `tax_total` | numeric(15,2) | |
| `total` | numeric(15,2) | `net_total + tax_total` (checked within 0.01 at ingest) |
| `local_net_total` | numeric(15,2) | net in MYR as AutoCount computed it (A5); the basis sums this, so the CRM never re-rounds a conversion |
| `status` | varchar(20) CHECK `posted`, `cancelled` | AutoCount's Cancelled flag; not a payment status |
| `against_document_id` | uuid FK self SET NULL | a CN or DN's invoice (Q4) |
| `against_doc_no` | varchar(50) | as sent, kept when the invoice is not in the CRM |
| `ref`, `description` | varchar(100), text | AutoCount Ref / Description, shown on the record |
| `source_system` | varchar default `autocount` | provenance, as `sales_orders` (`order.py:451-457`) |
| `source_ref` | varchar NOT NULL | `{database}:{type}:{DocKey}` (A2) |
| `source_modified_at` | timestamp (naive UTC) | AutoCount LastModified (A3); the stale guard |
| `last_synced_at`, `created_at`, `updated_at` | timestamps | |

Unique: `(company_id, document_type, source_ref)`. The idempotency key proper is the
`integration_references` row (entity type `billing_documents`); the unique index is the database
backstop that a second writer cannot get past.

`finance.billing_document_lines` (`company_id` NOT NULL, FK header ON DELETE CASCADE):
`line_no` int; `product_id` FK `products` SET NULL; `item_code` varchar(100) as sent;
`description` text; `uom` varchar(20); `quantity` numeric(15,4); `unit_price` numeric(15,4);
`discount_amount` numeric(15,2); `net_amount` numeric(15,2) (excl. tax, after discount);
`tax_code` varchar(20); `tax_rate` numeric(7,4); `tax_amount` numeric(15,2); `line_total`
numeric(15,2) (incl. tax); `sales_order_line_id` FK `sales_order_lines` SET NULL;
`from_doc_type`, `from_doc_no`, `from_line_ref` (as sent: the SO or DO the line was transferred
from); `source_ref` (DtlKey) NOT NULL, unique `(document_id, source_ref)`.

No `sales_order_id` on the header: AutoCount links per line (one invoice can bill several orders),
and the header's orders are the distinct orders of its lines. No DO FK: the DO table is not fed by
the ESB (2.3); the DO number is kept as sent in `from_doc_no`, trigger in section 7. No tax master:
`tax_code` is the code as sent, trigger in section 7.

### 3.3 The ingest contract (shared service -> CRM), contract 2.6

**3.3.1 Endpoint.** The existing surface, one new entity: `POST /api/v1/external/ingest/billing_documents`,
`POST /api/v1/external/ingest/billing_documents/deletions`, `POST /api/v1/external/read/billing_documents`.
Same envelope (`{"companyCode": "SRT", "records": [...]}`), same always-200 per-record verdicts,
same `?dry_run=true`, same `MAX_BATCH = 1000`, same anchor. No queue: the SO feed already pushes
synchronously at this batch size, and billing volume is of the same order. Slugs:
`INGEST_PERMISSIONS["billing_documents"] = "finance.billing_documents.edit"`, read `.view`,
delete `.delete`. `GET /external/contract` -> `"2.6"`, `fields_added.billing_documents`.

**3.3.2 Record shape** (`CanonicalBillingDocument(_Canonical)`, `extra="forbid"`):

```json
{
  "source_ref": "SRT_DB:IV:88213",
  "document_type": "invoice",
  "doc_no": "IV-2609/0142",
  "doc_date": "2026-09-26",
  "status": "posted",
  "source_modified_at": "2026-09-26T09:14:02",
  "customer_ref": "SRT_DB:300-R009", "customer_code": "300-R009", "customer_name": "...",
  "agent_code": "SEAN I",
  "currency_code": "MYR", "currency_rate": 1,
  "net_total": 1000.00, "tax_total": 100.00, "total": 1100.00, "local_net_total": 1000.00,
  "against_doc_no": null, "against_source_ref": null,
  "ref": "THE MET KL", "description": "...",
  "lines": [
    {
      "source_ref": "SRT_DB:IV:88213:1",
      "line_number": 1,
      "product_ref": "SRT_DB:ABC-1", "product_code": "ABC-1", "description": "...",
      "uom": "PCS", "quantity": 10, "unit_price": 100.00, "discount_amount": 0,
      "net_amount": 1000.00, "tax_code": "SV-10", "tax_rate": 10, "tax_amount": 100.00,
      "line_total": 1100.00,
      "from_doc_type": "DO", "from_doc_no": "DO-2609/0077", "from_line_ref": "SRT_DB:SO:1234:1"
    }
  ]
}
```

**3.3.3 Resolution.** Header ladder: `refs.resolve("billing_documents", source_ref)` within the
anchor -> create. **No adopt-by-number step**: there are no billing rows in the CRM to adopt, which
removes the ladder's most delicate branch (2.2 idempotency). Masters resolve through the existing
`MasterRefResolver` ref -> code ladder (customers, sales agents, products), but **never create a
master and never make the record retryable**: an unresolved customer, agent or product lands NULL
with the code kept and a warning (`customer_unresolved`, `agent_unresolved`,
`product_unresolved`). A billing document is money; holding it back or dropping a line changes a
total, where an SO line without a product only lost a planning row.
`against_source_ref` (else `against_doc_no` within the company) resolves the CN/DN's invoice; when
an invoice lands, any CN/DN in the company whose `against_doc_no` equals its number and whose
`against_document_id` is NULL is filled (UAC S0-12). `from_line_ref` resolves through
`refs.resolve("sales_orders", ...)` line refs to `sales_order_line_id`.

**3.3.4 Updates, versions, cancels, deletes.**
- A push names the **whole document**; lines not in it are deleted (nothing references a billing
  line, so there is no cancel-in-place branch).
- **Stale guard:** when both the stored and the incoming `source_modified_at` exist and incoming is
  older, nothing is written, verdict `unchanged` + `stale_ignored`. The SO feed has no such guard;
  it earns one here because the backfill (J3) and the live feed are two writers of the same
  documents that can overlap in time, which the SO feed never had.
- **Cancel:** `status: "cancelled"` is an update; the row stays and the basis skips it.
- **Delete:** `/deletions` hard-deletes through the existing `DeletionService` and dependent probe;
  a document still referenced (a CN's `against_document_id`) is set `cancelled`, verdict
  `deactivated`, exactly as SOs do.
- **Reversal documents** (a CN that reverses an IV) are just CNs; nothing in the CRM nets them
  except the basis.

**3.3.5 Backfill and company scoping.** History arrives through the same endpoint, oldest first,
IV and CS before CN and DN of the same day (so `against` links resolve on first write; the late-fill
of 3.3.3 covers the rest), in batches of 1000, from the date Q2 picks. Re-running any batch is safe
(UAC S0-5). Each company pushes under its own `companyCode` (Sorento `SRT`; Mocha is already
connected in production per the owner, PR #1269 comment 5844532989); every row carries the anchor's
`company_id`; a master found only in the other company is not linked (UAC S0-14);
`integration_references` is global, so refs carry the AutoCount database name (cross-repo contract
9.14).

**3.3.6 Assumptions for the shared service to confirm** (the plans in 2.5 were unreachable):
- **A1.** AutoCount exposes IV, CS, CN and DN headers with item detail (Sales-module tables, not
  the AR-module ones) under the NDA.
- **A2.** DocKey is unique per document table, not across them, so the ref carries the type
  (`{database}:{IV|CS|CN|DN}:{DocKey}`); the line ref appends DtlKey.
- **A3.** Each header has a last-modified timestamp the ETL already watermarks on.
- **A4.** A CN (and DN) names the invoice it is against at header level (a knock-off or an
  original-invoice field). If AutoCount only has per-line or knock-off allocations, Q4 changes.
- **A5.** Headers carry `CurrencyCode`, `CurrencyRate` and a local (MYR) net amount; lines carry a
  tax code, rate and amount, net and gross.
- **A6.** A line transferred from a DO or SO names its source line (FromDocType, FromDocNo,
  FromDtlKey), and the shared service can map a DO line back to its SO line ref when the IV was
  transferred from a DO.
- **A7.** Cancelled documents stay in AutoCount with a Cancelled flag; deleted ones vanish and can
  be detected by the ETL as deletions.
- **A8.** Agent and customer codes on billing documents are the same codes the SO feed sends.
- **A9.** The NDA allows header, line, customer, agent, product and tax fields. Nothing about bank
  accounts, GL accounts or payment details is needed (Q6).

### 3.4 The invoiced basis on the sales reports (S1)

On the #1269 reports kernel (its dataset `app/services/reports/datasets/sales_order_lines.py`
and the Basis filter, retail plan 5.1-5.2): a second dataset over `finance.billing_documents`
(header level is enough; lines only for a brand or product axis), and Basis gains **Invoiced**.

`invoiced_value = SUM(CASE document_type WHEN 'credit_note' THEN -1 ELSE 1 END * local_net_total)`
over `status = 'posted'` and `document_type IN ('invoice','cash_sale','credit_note','debit_note')`
(DN included per Q7), dated by `doc_date`, company from the Company filter. Excluding tax by
construction (`local_net_total`). A CN counts in its own month (UAC S1-2).

**Channel grouping, left open (Q8).** The SO basis groups by `sales_orders.demand_class`. A cash
sale has no SO and an invoice's SO link is per line, so the invoiced basis cannot use
`demand_class` directly. Options: (a) the document's agent's current `demand_class`
(`sales_agents`), (b) **the PDF's people grouping**: the document's agent, grouped through
#1260's dated `sales.teams` membership as of `doc_date`, (c) debtor type (#1269 S3). Until the owner
answers, Invoiced shows one "All sales" block (UAC S1-4).

### 3.5 Module, permissions, menu, pages

- **Module** `finance`: catalog row (display "Finance", sort `"970"`, deps `["base","order"]`),
  manifest entry, `permission_module_map` prefix `finance`, router `be/app/api/v1/finance/`
  mounted at `/finance` with `require_module_enabled_with_api_key("finance")`, FE
  `route-module-map` `{ prefix: '/finance', moduleKey: 'finance' }`, purge registry entry.
  Dormant until switched on in App Store, as `sales` shipped.
- **Permissions:** `finance.billing_documents.view` (staff read; granted to admin, superadmin),
  `.edit` and `.delete` (ingest and deletions only: no UI writes; granted to admin, superadmin and
  every role holding `scm.sales_orders.edit`, which is how the ESB integration's role gets it, the
  sweep shape of `414_product_set_grant_sweep.py`). No `.add`: nothing is created by hand. Export
  uses `.view` (trigger for a separate slug: someone must see but not export).
- **Menu:** a FINANCE heading after SALES with one item, Billing Documents (`/finance/billing-documents`,
  `permission: 'finance.billing_documents.view'`, `moduleKey: 'finance'`), in `MENU_SIDEBAR` and
  `MENU_SIDEBAR_COMPACT`.
- **List** (`DataGrid`, fixed layout, resizable): Type (Badge), Number, Date, Customer, Agent,
  Total (right aligned; currency code shown when not MYR), Status (Badge: Posted neutral, Cancelled
  muted). Filters: Type (`SearchableMultiSelect`), Status, Customer, Agent (`SearchableSelect`,
  clearable), Date range. Search: number, customer. No Add, no Delete: read-only mirror.
- **Record** `/finance/billing-documents/[id]`: `PageHeader` (number, type Badge, status Badge),
  meta strip (AutoCount, last synced, document date), `RecordNavigation`, line tabs as on the Users
  record: **Details** (customer, agent, currency and rate, ref, description, totals: net, tax,
  total), **Lines** (DataGrid: item, description, qty, UoM, price, discount, net, tax code, tax,
  total), **Related** (the invoice a CN/DN is against or its raw number; the CNs/DNs against an
  IV; the SOs its lines came from, linking to their records; DO numbers as text). Every tab has an
  empty state. View only, so the View = Edit rule holds trivially.
- **S3 sections:** SO record, "Invoices"; customer record, "Billing documents" tab (the list
  component, pre-filtered).
- Mockups: the alignment page, sections "S2" and "S3", at 1280 and 375.

### 3.6 Audit (if #1299 has merged by S0)

The header table stays audited (default-on); ingest runs as the integration principal, so its rows
read `source = integration`. The lines table declares `__audit_skip__ = "mirror of AutoCount lines,
replaced whole on every push; the header row and integration_references are the trail"`. An unchanged re-push writes no audit row (#1299's no-change rule),
so the idempotency test (S0-5) also bounds audit volume. If #1299 has not merged, nothing is needed.

## 4. Slices

Ordered for early value. Each slice's ACs are in the UAC under its id.

| Slice | What | UAC | Depends on | Before -> after |
| --- | --- | --- | --- | --- |
| **S0** | Model + ingest contract + replayable fixture: migration `fin_0001_billing_documents` (schema, two tables, module row, permissions, grants), models, `CanonicalBillingDocument`, the entity in `DOCUMENT_SPECS` style or a sibling `BillingDocumentIngestService` with the same constructor, read-back, deletions, contract 2.6, `_pg_fixture` schema entries, the fixture JSON, contract section 12 in the cross-repo plan. Backend only. | S0-1 to S0-21 | none (NDA not needed: the fixture stands in) | No billing document can be received -> the shared service can push, replay and delete billing documents for either company, proven by a fixture. |
| **S1** | Invoiced basis on Yearly comparison and Sales report, and the chatbot. | S1-1 to S1-8 | S0, PR #1269 merged | Reports can only count orders -> Basis: Invoiced counts IV + CS (+ DN) - CN, excl. tax, by document date. |
| **S2** | Finance menu, list and record pages (Phase 1 mock, then wiring). | S2-1 to S2-10 | S0 | Billing documents are invisible -> FINANCE > Billing Documents list and record. |
| **S3** | Billing on the SO record and the customer record. | S3-1 to S3-3 | S2 | You leave the SO to find its invoice -> the SO and customer show theirs. |
| **S4** | History backfill runbook and the tally against the PDF. | S4-1 to S4-3 | S0, NDA, shared-service sink | The basis has only new documents -> history from Q2's date, tallied. |

S1 and S2 can run in parallel lanes after S0 (different files: reports kernel vs finance pages).
Per the lane rule (CLAUDE.md "Lane merge discipline"), S0 to S3 land as commits on one feature
lane unless the owner splits S1 out to ride with #1269's follow-ups.

**Tickets** (to be opened on answer of section 9, each linking this PLAN and the UAC): one issue
per slice, S0 blocking S1, S2 and S4, S2 blocking S3. Not opened yet, so the grill can still
reshape them.

## 5. Testing seams (agreed before Phase 2)

- S0: pytest through the route (`TestClient` with an integration key) on `blank_session` with the
  `finance` schema translated; the fixture file is the golden set; replay equality compares a
  canonical dump of both tables.
- S1: the kernel's run function on a seeded fixture, the golden numbers written first.
- S2/S3: vitest on the service and hooks against the mock; agent-browser evidence run.

## 6. Risks

- **The NDA is not signed.** S0 to S3 do not need it (the fixture stands in); S4 does. The real
  risk is A1 to A9 being wrong; the contract is versioned and every new key optional, so a
  correction is a 2.7, not a rewrite.
- **Mocha books in another currency or tax regime.** `currency_code`/`local_net_total` cover it.
- **A CN against an invoice from before the backfill start.** `against_doc_no` is kept, the link
  stays NULL, and the basis is unaffected (a CN counts in its own month).
- **#1269 not merged when S1 starts.** S1 waits; S2 does not.

## 7. Not built, and the trigger for each

- **Receipts and payments (AutoCount AR Payment / Official Receipt), outstanding per invoice, paid
  status:** the owner asks for collections or a customer's balance in the CRM. Then a
  `finance.receipts` table and a knock-off table.
- **Accounting ledgers (GL, journal entries, chart of accounts):** never from AutoCount into the
  CRM without an owner ruling; AutoCount is the ledger.
- **Ageing and statements:** follows receipts; `customers.ar_*` (`order.py:134-139`) is the
  existing seam, still unwritten.
- **AR-module documents (AR Invoice, AR CN, AR DN):** the owner's AutoCount report counts them, or
  a figure fails to tally because of them. Adding them is a CHECK change plus a type.
- **A tax master (`tax_codes`):** a screen or rule needs the tax code's name or rate beyond what the
  line carries.
- **A DO link as a FK:** the DO table is fed by the ESB with trustworthy money.
- **Credit note allocations across several invoices:** A4 is wrong (AutoCount allocates per line or
  by knock-off) and the owner needs to see the split.
- **Dealer-facing invoices on the portal:** Q5 answered yes.
- **A queue for the ingest:** a billing batch times out on the synchronous route.

## 8. Glossary and ADR

`CONTEXT.md` has no billing terms. The grill (`/grill-with-docs`) should add **Billing document**,
**Document type**, **Invoiced basis** to `documentation/CONTEXT.md` and one ADR,
"0013: billing documents are one typed table in the `finance` schema", once Q1 to Q4 are answered.
Not written in this docs-only lane, so the grill can still change them. No conflict with an
existing ADR: ADR-0007 (a dealer is a customer) is why a billing document points at `customers`.

## 9. Open questions for the owner (the grill)

Each is answerable yes, no or with one pick. The recommendation is in bold.

1. **Which document types on day one?** (a) IV, CS, CN, DN; (b) IV, CS, CN only; (c) IV only.
   **(a) all four: they are one shape, and a DN left out would make the invoiced figure short by
   every extra charge.**
2. **Is history backfilled, and from when?** (a) from 1 Jan 2024; (b) from 1 Jan 2025; (c) no, new
   documents only. **(a) 1 Jan 2024: the Yearly comparison shows 2024, 2025 and 2026.**
3. **Tax: how is it stored?** (a) net (excl. tax), tax and total, all three, as AutoCount sends;
   (b) tax-inclusive total only; (c) net only. **(a): the report sums net, the record page shows
   all three, and nothing is recomputed.**
4. **How does a credit note reference its invoice?** (a) one invoice on the CN header, with the
   invoice number kept even when that invoice is not in the CRM; (b) per line; (c) not at all.
   **(a), unless the shared service reports that AutoCount only allocates by knock-off (A4).**
5. **Do dealers see amounts (their invoices) on the portal?** Yes or no. **No: staff only for
   now; the portal shows no orders today.**
6. **What does the NDA allow the shared service to send?** (a) document headers and lines with
   customer, agent, product and tax fields; (b) headers only; (c) something narrower you will name.
   **(a): it is everything this plan uses, and nothing about bank, GL or payment details.**
7. **Does the invoiced basis add debit notes?** Yes or no. **Yes: IV + CS + DN - CN, matching how
   AutoCount's sales analysis treats a DN as extra billing; confirm against the report's options.**
8. **Channel grouping on the invoiced basis** (left open): (a) the agent's current dealer/project
   class; (b) the PDF's people grouping, the agent's sales team as of the document date (#1260's
   dated teams); (c) debtor type. **Provisionally (b), because the PDF's "16pax" footnote says it
   groups people; please confirm from the AutoCount report's options before S1 builds it.**
9. **Who sees Finance > Billing Documents?** (a) admin and superadmin now, others granted on the
   Roles screen; (b) also every sales role. **(a).**
10. **AutoCount AR-module documents (AR Invoice, AR CN, AR DN, no item lines): include now?** Yes
    or no. **No: add them only if the tally shows they are part of the PDF.**
11. **Receipts and payments: plan them now?** Yes or no. **No: named trigger in section 7.**
12. **Foreign-currency documents: report in ringgit using AutoCount's own converted amount?** Yes
    or no. **Yes (`local_net_total`).**
13. **A cancelled document: keep it visible with a Cancelled badge and leave it out of every
    total?** Yes or no. **Yes.**
