# PLAN: finance module, billing documents from AutoCount through the shared service (#1309)

Status: **draft, round 2 (27 Sep): the owner's 13 rulings are folded in (section 0). Q5 is
being confirmed by the orchestrator; Q14 to Q16 are new and open (section 9). S0 is ready to
build from `S0-build-brief.md`.** Planning half of the pipeline only (journey, grill questions,
UAC, plan, slices, tickets); nothing is built.
Track: full (new module and schema, migration, new permissions, a new external ingest entity).
Domain: finance. Classification: **MODULE `finance`** (installable per tenant: another AutoCount
customer would turn it on; `app_modules_catalog` row + `require_module_enabled_with_api_key`).
Schema: **`finance`**, tables without a `finance_` prefix (the ADR-0011 precedent the `sales`
module followed, `sorento_crm_backend/alembic/versions/sales_0001_teams.py:5-6,43`).
UAC: `finance-billing-documents-27sep-acceptance-criteria.md` alongside (the contract; the journey
J1 to J9 lives there). Alignment pages with the mockups: `alignment/finance-alignment-r1.html`
(round 1, the questions) and `alignment/finance-alignment-r2.html` (round 2, the rulings).
S0 build brief: `S0-build-brief.md`.
Branch: `claude/finance-billing-documents-plan-jks6fx` (the cloud session is pinned to that name;
the brief named `claude/finance-billing-documents-plan`), off `origin/main` 9751e55d; draft PR
#1310. Since then `origin/main` gained PR #1269 (52b0ac24, the sales reports kernel), so S1's
dependency on it is met.

Paths below are relative to the repo root. Backend paths start `sorento_crm_backend/`, shortened
to `be/` in the tables; frontend `sorento_crm_frontend/` to `fe/`.

## 0. Owner rulings (27 Sep)

Source: the owner's notes on the round 1 alignment page, delivered 21:35 MYT and posted verbatim
on issue #1309 (comment 5855833693, "Owner rulings on the round 1 open questions"). Each note is
quoted as written, against the question it was attached to; "Read as" is the orchestrator's
reading in that comment; "Consequence" is what changed in this plan.

| Q | Owner's note (verbatim) | Read as | Consequence in this plan |
| --- | --- | --- | --- |
| 1 | "this" (on the bold (a)) | (a) IV, CS, CN and DN | The CHECK on `document_type` holds all four (3.1); UAC S0-3 loses its "Q1 may shorten" note. |
| 2 | "i will start the shares servcie transfer from 2023 probably, i can set in shared service" | Backfill from 1 Jan 2023; the start date is set on the shared service side, the CRM accepts whatever history arrives | The start date is shared-service configuration, not CRM configuration: the CRM ingest has **no date floor** and accepts a document of any date (3.3.5, new UAC S0-22). The planned start is 1 Jan 2023. The S4 tally covers **2024 onwards** (the months the Yearly comparison shows); 2023 lands but is not tallied (S4-1, S4-3). |
| 3 | "yes this" (on (a)) | (a) net, tax and total as AutoCount sends them | Unchanged from round 1 (3.2). |
| 4 | "yes" (on (a)) | (a) one invoice on the header | `against_document_id` + `against_doc_no` on the header stand (3.2, 3.3.3); UAC S0-12 loses its Q4 marker. A4 is still for the shared service to confirm; a knock-off-only AutoCount is the trigger in section 7. |
| 5 | "yes" (on the line "No. Staff only for now") | Agreement with the recommendation: staff only; **the orchestrator is confirming with the owner in chat** | Provisionally: dealers see no billing document and no amount on the portal. Nothing portal-side is built; new UAC S2-11 holds the portal to that. Kept in section 9 marked "confirming". |
| 6 | "yes" (on (a)) | (a) headers and lines with customer, agent, product and tax fields | A9 is the owner's ruling now, not an assumption; the record shape of 3.3.2 is the NDA scope. |
| 7 | "yes" | Yes: IV + CS + DN - CN | The invoiced basis includes DN (3.4); UAC S1-1 loses its Q7 marker. |
| 8 | "based on the seals order agent" | Group by the sales agent on the document (the sales order agent), not by debtor type and not by the agent's current class; the agent's team as of the document date gives the DEALER / PROJECT TEAM blocks | S1 groups the invoiced basis by the document's `sales_agent_id` and that agent's dated `sales.team_members` row (#1260) covering `doc_date`, with a **"No team" block** as the fallback (3.4). The single "All sales" placeholder block is gone (UAC S1-4 rewritten). How a team maps to a block, and whose agent wins when the invoice's agent differs from its SO's, are new questions Q14 and Q15. |
| 9 | "crearte permissions for this" | (a) with its own permissions (view, export) granted on the Roles screen; admin and superadmin get them by default | Two user-facing slugs, `finance.billing_documents.view` and `finance.billing_documents.export`, seeded by `fin_0001` and granted to admin and superadmin only, as `sales_0001_teams` does; every other role through the Roles screen (3.5, UAC S0-2 rewritten). The ingest-side slugs and who holds them are new question Q16. |
| 10 | "ok" | No | AR-module documents stay out; trigger unchanged in section 7. |
| 11 | "ok" | No | Receipts and payments stay out; trigger unchanged in section 7. |
| 12 | "yes" | Yes | The basis sums `local_net_total` (AutoCount's own MYR amount); unchanged (3.4). |
| 13 | "yes" | Yes | Cancelled stays visible with a Cancelled badge and out of every total; unchanged (3.3.4, 3.4, 3.5). |

The owner ended the Lavish session after these notes.

**Sections rewritten in round 2:** 0 (new), 1 (the history paragraph), 3.3.5 (backfill), 3.3.6
(A9 settled), 3.4 (channel grouping), 3.5 (permissions, export), 4 (slices S0, S1, S2, S4),
5, 6, 7 (the portal line), 8, 9.

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
batches, from the start date you set on the shared service (1 Jan 2023 planned, ruling Q2). The
CRM takes whatever history arrives; the tally against the PDF covers 2024 onwards.

**What the CRM will show.**
1. On **Sales > Yearly comparison and Sales report** (PR #1269), a third basis, **Invoiced**:
   invoices plus cash sales plus debit notes minus credit notes, excluding tax, by document date,
   grouped by the document's sales agent and the team that agent was in on that date. That is
   what the scout on #1269 found the AutoCount PDF counts, and the only basis that can tally
   with it.
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
of 3.3.3 covers the rest), in batches of 1000. **The start date belongs to the shared service**
(ruling Q2: "i can set in shared service"); the owner plans 1 Jan 2023. The CRM therefore has no
start-date setting and no date floor: a document of any `doc_date` is accepted and stored (UAC
S0-22), so moving the start earlier or later is a shared-service change only, and a second,
earlier backfill later is just more pushes. The tally (S4) covers 2024 onwards, the years the
Yearly comparison shows; 2023 documents are stored, listed and counted by the basis but not
tallied against the PDF. Re-running any batch is safe (UAC S0-5). Each company pushes under its own `companyCode` (Sorento `SRT`; Mocha is already
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
- **A9.** Settled by the owner (ruling Q6): the NDA scope is header, line, customer, agent,
  product and tax fields. Nothing about bank accounts, GL accounts or payment details is needed
  or sent.
- **A10** (new, from ruling Q8). The agent code on an IV transferred from an SO is the SO's agent
  code in the normal case; the shared service reports how often they differ (feeds Q15).

### 3.4 The invoiced basis on the sales reports (S1)

On the #1269 reports kernel, merged to main at 52b0ac24 (its dataset
`be/app/services/reports/datasets/sales_order_lines.py`, the definition
`be/app/services/reports/definitions/sales_yearly.py` and the Basis filter): a second dataset over
`finance.billing_documents` (header level is enough; lines only for a brand or product axis), and
Basis gains **Invoiced**.

`invoiced_value = SUM(CASE document_type WHEN 'credit_note' THEN -1 ELSE 1 END * local_net_total)`
over `status = 'posted'` and `document_type IN ('invoice','cash_sale','credit_note','debit_note')`
(DN included, ruling Q7), dated by `doc_date`, company from the Company filter. Excluding tax by
construction (`local_net_total`, AutoCount's own MYR amount, ruling Q12). A CN counts in its own
month (UAC S1-2).

**Channel grouping (ruling Q8: "based on the seals order agent").** On main the SO basis builds
its two blocks from `sales_orders.demand_class` (`sales_order_lines.py:37-47`: `retail` reads
"Dealer", `project` reads "Project team"). The invoiced basis does not use `demand_class` and does
not use the agent's current class: it groups **by the sales agent on the document**
(`billing_documents.sales_agent_id`) **and the team that agent was in on the document date**, from
#1260's dated membership (`sales.team_members`, `be/alembic/versions/sales_0001_teams.py:66-109`).
The dated rule is the one `be/app/services/sales/team_service.py:6-7` already states for orders:
a document of agent A dated X belongs to team T when A has a row for T with
`coalesce(valid_from, -infinity) <= X <= coalesce(valid_to, infinity)`, within the document's
company. `team_service` is the only writer and refuses overlapping stays, so there is at most one
such row; an agent's first team has `valid_from` NULL and so covers their whole history (V1),
which is what makes a 2023 document land in a team at all.

The query is one LEFT JOIN from `finance.billing_documents` to `sales.team_members` on
`(company_id, sales_agent_id)` and the dated condition, then to `sales.teams` for the name. No
new table, column or mapping in `finance`.

**The fallback.** A document lands in the **"No team"** block when any of these holds: its agent
did not resolve at ingest (`sales_agent_id` NULL, warning `agent_unresolved`), the agent has no
team row covering `doc_date`, or the agent is in no team at all. The block is shown only when it
is non-empty, sorts last, and is counted in the company total, so every ringgit the PDF counts is
in the report and the size of the gap is visible. The fix is on the existing Sales Teams screen
(put the agent in a team, or date a move correctly), never in Finance. Not the agent's
`demand_class` as a fallback: the ruling ruled out the agent's class as the grouping, and a
fallback that silently re-grouped by it would produce a block the owner cannot reconcile.

**How a team becomes a block** is new question Q14: the recommendation is that each team is its
own block, headed by the team's name, so teams named "Dealer" and "Project team" reproduce the
PDF's DEALER and PROJECT TEAM rows with no mapping to build. **Whose agent when they differ** (an
IV's own agent vs the agent on the SO its lines came from) is Q15: the recommendation is the
document's own agent, because a cash sale has no SO and a per-line SO agent would split one
document across blocks. The Channel filter, on Basis = Invoiced, lists the company's teams plus
"No team" (UAC S1-4, S1-9).

### 3.5 Module, permissions, menu, pages

- **Module** `finance`: catalog row (display "Finance", sort `"970"`, deps `["base","order"]`),
  manifest entry, `permission_module_map` prefix `finance`, router `be/app/api/v1/finance/`
  mounted at `/finance` with `require_module_enabled_with_api_key("finance")`, FE
  `route-module-map` `{ prefix: '/finance', moduleKey: 'finance' }`, purge registry entry.
  Dormant until switched on in App Store, as `sales` shipped.
- **Permissions (ruling Q9: "crearte permissions for this").** Finance gets its own slugs,
  following the sales module precedent (`be/alembic/versions/sales_0001_teams.py:35-40,112-135`:
  rows inserted into `user_permissions` when absent, granted through `user_role_permissions` to
  `admin` and `superadmin` only, `ON CONFLICT DO NOTHING`; the same slugs declared in
  `be/app/rbac/permission_registry.py` so `sync_permissions` creates them on a `create_all`
  database, as `:818-821` does for `sales.teams`). Every other role gets them on the Roles screen
  (the role editor), never by a migration sweep. The user-facing pair:
  - `finance.billing_documents.view`: the FINANCE menu, the list, the record page, and the S3
    sections on the SO and customer records.
  - `finance.billing_documents.export`: the list's Export button and `POST /list-query/export`
    for the resource. It plugs into the list registry's existing `export_slug`
    (`be/app/services/list_query_registry.py:85`; checked in `be/app/api/v1/list_query.py:240-242`),
    exactly as `order_management.orders.export` does. Export without view is meaningless, so the
    Export button needs both.

  No `.add`: nothing is created by hand. The ingest door gates every entity by a slug
  (`INGEST_PERMISSIONS`, `READ_PERMISSIONS`, `DELETE_PERMISSIONS`, `ingest.py:83-133`), so the
  feed also needs a write slug and a delete slug that no UI uses: `finance.billing_documents.edit`
  (ingest) and `.delete` (deletions), read-back on `.view`. They are declared, seeded and granted
  to admin and superadmin with the others. Whether the migration also grants `.edit`, `.delete`
  and `.view` to the ESB integration's role (every role holding `scm.sales_orders.edit`, the
  `472_ingest_v2_permissions.py` sweep) or an admin grants them on the Roles screen before the
  first push is new question Q16.
- **Menu:** a FINANCE heading after SALES with one item, Billing Documents (`/finance/billing-documents`,
  `permission: 'finance.billing_documents.view'`, `moduleKey: 'finance'`), in `MENU_SIDEBAR` and
  `MENU_SIDEBAR_COMPACT`.
- **List** (`DataGrid`, fixed layout, resizable): Type (Badge), Number, Date, Customer, Agent,
  Total (right aligned; currency code shown when not MYR), Status (Badge: Posted neutral, Cancelled
  muted). Filters: Type (`SearchableMultiSelect`), Status, Customer, Agent (`SearchableSelect`,
  clearable), Date range. Search: number, customer. Export (xlsx of the filtered list, through
  the list-query export) shown only with `.export`. No Add, no Delete: read-only mirror.
- **Portal (ruling Q5, being confirmed):** nothing. No portal route, component or endpoint reads
  `finance`; a dealer's portal role holds no finance slug, so every `/finance` call answers 403
  (UAC S2-11).
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

Ordered for early value. Each slice's ACs are in the UAC under its id. "Round 2" marks what the
rulings changed.

| Slice | What | UAC | Depends on | Before -> after |
| --- | --- | --- | --- | --- |
| **S0** (round 2: permissions, no date floor) | Model + ingest contract + replayable fixture: migration `fin_0001_billing_documents` (schema, two tables, module row, the four slugs and their admin and superadmin grants), models, `CanonicalBillingDocument`, a sibling `BillingDocumentIngestService` with `DocumentIngestService`'s constructor, read-back, deletions, contract 2.6, `_pg_fixture` schema entries, the fixture JSON, contract section 12 in the cross-repo plan. Backend only. Build brief: `S0-build-brief.md`. | S0-1 to S0-22 | none (NDA not needed: the fixture stands in) | No billing document can be received -> the shared service can push, replay and delete billing documents of any date for either company, proven by a fixture. |
| **S1** (round 2: grouping by agent and dated team) | Invoiced basis on Yearly comparison and Sales report, and the chatbot, grouped by the document's agent and that agent's team on the document date, with a "No team" block. | S1-1 to S1-10 | S0; PR #1269 (merged, 52b0ac24); Q14 and Q15 answered before the grouping is built | Reports can only count orders -> Basis: Invoiced counts IV + CS + DN - CN, excl. tax, by document date, in the owner's teams. |
| **S2** (round 2: export slug, portal) | Finance menu, list (with Export on `.export`) and record pages (Phase 1 mock, then wiring). | S2-1 to S2-12 | S0 | Billing documents are invisible -> FINANCE > Billing Documents list and record, for the roles granted on the Roles screen. |
| **S3** | Billing on the SO record and the customer record. | S3-1 to S3-3 | S2 | You leave the SO to find its invoice -> the SO and customer show theirs. |
| **S4** (round 2: start date on the shared service, tally from 2024) | History backfill runbook and the tally against the PDF. | S4-1 to S4-3 | S0, NDA, shared-service sink | The basis has only new documents -> history from the shared service's start date (1 Jan 2023 planned) in the CRM, 2024 onwards tallied. |

S1 and S2 can run in parallel lanes after S0 (different files: reports kernel vs finance pages).
Per the lane rule (CLAUDE.md "Lane merge discipline"), S0 to S3 land as commits on one feature
lane unless the owner splits S1 out to ride with #1269's follow-ups. S0 is briefed to build now
(`S0-build-brief.md`): none of Q5, Q14, Q15 changes it, and Q16 changes only which roles one
migration statement grants to (the brief carries both variants).

**Tickets** (each linking this PLAN and the UAC): one issue per slice, S0 blocking S1, S2 and S4,
S2 blocking S3. S0's ticket can open now; S1's waits on Q14 and Q15.

## 5. Testing seams (agreed before Phase 2)

- S0: pytest through the route (`TestClient` with an integration key) on `blank_session` with the
  `finance` schema translated; the fixture file is the golden set; replay equality compares a
  canonical dump of both tables.
- S1: the kernel's run function on a seeded fixture, the golden numbers written first; the
  seed includes two teams, an agent who moves team mid-month, an agent with no team and a
  document with no resolved agent, so the dated join and the "No team" block are both pinned.
- S2/S3: vitest on the service and hooks against the mock; agent-browser evidence run.

## 6. Risks

- **The NDA is not signed.** S0 to S3 do not need it (the fixture stands in); S4 does. The real
  risk is A1 to A9 being wrong; the contract is versioned and every new key optional, so a
  correction is a 2.7, not a rewrite.
- **Mocha books in another currency or tax regime.** `currency_code`/`local_net_total` cover it.
- **A CN against an invoice from before the backfill start.** `against_doc_no` is kept, the link
  stays NULL, and the basis is unaffected (a CN counts in its own month).
- **#1269 not merged when S1 starts.** Resolved: merged at 52b0ac24.
- **Teams not set up, or not dated back far enough, when the backfill lands.** The "No team"
  block grows and the DEALER / PROJECT TEAM blocks will not tally. It is visible, not silent,
  and the fix is on the Sales Teams screen; an agent's first team already covers all history
  (V1), so only a mid-history move needs dating.
- **The ESB role lacks the ingest slug on the first push** (if Q16 is answered "Roles screen").
  Every record answers 403 until an admin grants it; the S4 runbook's first step is that grant.

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
- **Dealer-facing invoices on the portal:** the owner asks for them (ruling Q5 is staff only,
  being confirmed); then a portal page reads the dealer's own customer's documents.
- **A start-date setting in the CRM:** never while the shared service owns the start (ruling Q2).
- **A team-to-block mapping table:** Q14 answered with a mapping instead of "one block per team".
- **A queue for the ingest:** a billing batch times out on the synchronous route.

## 8. Glossary and ADR

`CONTEXT.md` has no billing terms. The grill (`/grill-with-docs`) should add **Billing document**,
**Document type**, **Invoiced basis** to `documentation/CONTEXT.md` and one ADR,
"0013: billing documents are one typed table in the `finance` schema". Q1 to Q4 are now
answered (section 0), so both are due; the S0 build lane writes them (`S0-build-brief.md`), since
this lane is plan files only. No conflict with an
existing ADR: ADR-0007 (a dealer is a customer) is why a billing document points at `customers`.

## 9. Open questions for the owner (round 2)

Q1 to Q13 are closed by the rulings in section 0, except Q5, which the orchestrator is
confirming. Q14 to Q16 are new: the rulings raised them. Each is answerable yes, no or with one
pick. The recommendation is in bold.

5. **(Confirming.) Do dealers see amounts (their invoices) on the portal?** The owner's note
   "yes" sat on the line "No. Staff only for now", read as agreement. **No: staff only. The plan
   is built that way (UAC S2-11); a "yes, dealers see them" would add a portal slice and changes
   nothing in S0.**
14. **How does a sales team become a block on the invoiced basis?** (a) each team is its own
    block, headed by the team's name, so naming the teams "Dealer" and "Project team" on the
    Sales Teams screen gives the PDF's DEALER and PROJECT TEAM rows; (b) every team is mapped to
    one of two fixed blocks, DEALER or PROJECT TEAM, by a new setting on the team.
    **(a): nothing new to build or keep in step, and the report shows exactly the teams you
    define. (b) is a new column and screen field, worth it only if you keep more teams than
    blocks.**
15. **When an invoice's own agent differs from the agent on the sales order its lines came
    from, whose team does it count for?** (a) the invoice's own agent; (b) the sales order's
    agent, line by line. **(a): a cash sale has no sales order, one document stays in one
    block, and AutoCount's own sales report groups by the document's agent. The shared service
    reports how often they differ (A10); if it is often, we revisit.**
16. **Who grants the billing ingest permission to the AutoCount feed's role?** (a) the migration,
    to every role that already receives sales orders from the feed (holds
    `scm.sales_orders.edit`), as the ingest v2 permissions were granted; (b) an admin, on the
    Roles screen, before the first push. **(a): the feed works on the day the module ships
    and no one has to remember a grant; people's access to Finance stays on the Roles screen
    either way, since this grants only the feed's write and delete (and the read-back it
    needs).**
