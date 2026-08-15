# PLAN - move the Project Sales tables into a `projects` Postgres schema

Status: implemented on `feat/project-lead-to-so` - awaiting tester gate

## Decision

The client reversed the schema clause of ADR-0009 on 2026-08-15. The projects module's 47
tables move out of `public` into a dedicated Postgres schema named `projects` (the module
key, matching the `scm` precedent from migration 273), and the `project_` table-name prefix
is dropped inside that schema, because the schema is now the ownership marker.

ADR: `documentation/adr/0011-project-sales-tables-live-in-the-projects-schema.md`
(supersedes the schema clause of `documentation/adr/0009-project-sales-is-one-module-tables-stay-public.md`;
0009's one-module and two-core-FK decisions stand).

Purge stays a row-level `DELETE` through the ORM. `DROP SCHEMA` is never issued on uninstall.

### Four points the orchestrator must rule on before S1 starts

1. **`public.projects` becomes `projects.projects`.** There is no `project_registrations`
   table in this codebase - the registration table IS `public.projects`
   (`app/models/projects.py:192`, class `Project`). The mechanical rule (strip a `project_`
   prefix; `projects` has none) therefore yields `projects.projects`. If
   `projects.registrations` was actually intended, that is a table RENAME on top of the
   schema move and needs to be stated, because it also changes `ForeignKey("projects.id")`
   in 15 places to `ForeignKey("projects.registrations.id")`, both core FK columns, and the
   ORM class docstrings. This plan assumes `projects.projects` unless told otherwise.
2. **`audit_log.entity_type` silently changes for the 34 renamed tables.**
   `app/services/audit_service.py:36-37` derives it from `__tablename__` unless the model
   sets `__audit_entity_type__`. Dropping the prefix would (a) orphan every existing audit
   row for those tables, and (b) make the projects module write `entity_type='brands'` and
   `'purchase_orders'`, which core `app/models/product.py:58` and
   `app/models/procurement.py:475` already use. **Recommendation: set
   `__audit_entity_type__ = "<old prefixed name>"` on all 34 renamed models.** That keeps
   audit history intact, keeps the entity types collision-free, and leaves
   `project_lead_service.py:58` (`LEAD_AUDIT_ENTITY_TYPE = "project_leads"`) and
   `project_task_service.py:908` (`AuditLog.entity_type == "project_tasks"`) correct with no
   edit. This plan assumes that recommendation is taken.
3. **FE purge manifest carries schema-qualified names.** Recommended: `projects.parties`,
   not `parties`. Bare names would show the operator `brands`, `purchase_orders`,
   `sales_orders`, `quotation_lines` - all of which are ALSO core tables the purge does not
   touch. See S5 for the mechanical consequence (`Table.fullname`).
4. **`alembic/env.py` has no `include_schemas`.** This is already broken for `scm` and the
   move makes it worse. See Hazard H4; fixing it is in S1.

---

## The 47-row mapping

Old name is `public.<name>` today; new name is `<schema>.<name>` after migration 354.
"*(unchanged)*" marks a table whose bare name does not move, only its schema.

| # | Old | New | Model class | File |
|---|-----|-----|-------------|------|
| 1 | `public.project_parties` | `projects.parties` | `ProjectParty` | `sorento_crm_backend/app/models/projects.py:73` |
| 2 | `public.project_types` | `projects.types` | `ProjectType` | `sorento_crm_backend/app/models/projects.py:112` |
| 3 | `public.project_templates` | `projects.templates` | `ProjectTemplate` | `sorento_crm_backend/app/models/projects.py:141` |
| 4 | `public.project_template_roles` | `projects.template_roles` | `ProjectTemplateRole` | `sorento_crm_backend/app/models/projects.py:168` |
| 5 | `public.projects` | `projects.projects` *(unchanged)* | `Project` | `sorento_crm_backend/app/models/projects.py:192` |
| 6 | `public.project_sales_profile` | `projects.sales_profile` | `ProjectSalesProfile` | `sorento_crm_backend/app/models/projects.py:294` |
| 7 | `public.project_brands` | `projects.brands` | `ProjectBrand` | `sorento_crm_backend/app/models/projects.py:328` |
| 8 | `public.project_stakeholders` | `projects.stakeholders` | `ProjectStakeholder` | `sorento_crm_backend/app/models/projects.py:348` |
| 9 | `public.project_collaborators` | `projects.collaborators` | `ProjectCollaborator` | `sorento_crm_backend/app/models/projects.py:386` |
| 10 | `public.project_takeover_requests` | `projects.takeover_requests` | `ProjectTakeoverRequest` | `sorento_crm_backend/app/models/projects.py:401` |
| 11 | `public.project_template_tasks` | `projects.template_tasks` | `ProjectTemplateTask` | `sorento_crm_backend/app/models/projects.py:456` |
| 12 | `public.project_tasks` | `projects.tasks` | `ProjectTask` | `sorento_crm_backend/app/models/projects.py:494` |
| 13 | `public.project_leads` | `projects.leads` | `ProjectLead` | `sorento_crm_backend/app/models/projects.py:600` |
| 14 | `public.project_series` | `projects.series` | `ProjectSeries` | `sorento_crm_backend/app/models/projects.py:745` |
| 15 | `public.project_series_categories` | `projects.series_categories` | `ProjectSeriesCategory` | `sorento_crm_backend/app/models/projects.py:772` |
| 16 | `public.project_series_products` | `projects.series_products` | `ProjectSeriesProduct` | `sorento_crm_backend/app/models/projects.py:790` |
| 17 | `public.price_floor_rules` | `projects.price_floor_rules` *(unchanged)* | `PriceFloorRule` | `sorento_crm_backend/app/models/projects.py:837` |
| 18 | `public.project_quotation_documents` | `projects.quotation_documents` | `ProjectQuotationDocument` | `sorento_crm_backend/app/models/projects.py:890` |
| 19 | `public.quotation_templates` | `projects.quotation_templates` *(unchanged)* | `QuotationTemplate` | `sorento_crm_backend/app/models/projects.py:978` |
| 20 | `public.project_quotation_issues` | `projects.quotation_issues` | `ProjectQuotationIssue` | `sorento_crm_backend/app/models/projects.py:1028` |
| 21 | `public.quotation_signatures` | `projects.quotation_signatures` *(unchanged)* | `QuotationSignature` | `sorento_crm_backend/app/models/projects.py:1117` |
| 22 | `public.project_quotation_issue_scopes` | `projects.quotation_issue_scopes` | `ProjectQuotationIssueScope` | `sorento_crm_backend/app/models/projects.py:1162` |
| 23 | `public.project_quotations` | `projects.quotations` | `ProjectQuotation` | `sorento_crm_backend/app/models/projects.py:1202` |
| 24 | `public.project_quotation_versions` | `projects.quotation_versions` | `ProjectQuotationVersion` | `sorento_crm_backend/app/models/projects.py:1257` |
| 25 | `public.project_quotation_lines` | `projects.quotation_lines` | `ProjectQuotationLine` | `sorento_crm_backend/app/models/projects.py:1298` |
| 26 | `public.project_samples` | `projects.samples` | `ProjectSample` | `sorento_crm_backend/app/models/projects.py:1383` |
| 27 | `public.project_purchase_orders` | `projects.purchase_orders` | `ProjectPurchaseOrder` | `sorento_crm_backend/app/models/projects.py:1422` |
| 28 | `public.project_purchase_order_lines` | `projects.purchase_order_lines` | `ProjectPurchaseOrderLine` | `sorento_crm_backend/app/models/projects.py:1510` |
| 29 | `public.project_po_versions` | `projects.po_versions` | `ProjectPOVersion` | `sorento_crm_backend/app/models/project_so.py:69` |
| 30 | `public.project_po_lines` | `projects.po_lines` | `ProjectPOLine` | `sorento_crm_backend/app/models/project_so.py:125` |
| 31 | `public.project_po_annotations` | `projects.po_annotations` | `ProjectPOAnnotation` | `sorento_crm_backend/app/models/project_so.py:162` |
| 32 | `public.delivery_schedules` | `projects.delivery_schedules` *(unchanged)* | `DeliverySchedule` | `sorento_crm_backend/app/models/project_so.py:200` |
| 33 | `public.delivery_schedule_versions` | `projects.delivery_schedule_versions` *(unchanged)* | `DeliveryScheduleVersion` | `sorento_crm_backend/app/models/project_so.py:227` |
| 34 | `public.project_delivery_phases` | `projects.delivery_phases` | `ProjectDeliveryPhase` | `sorento_crm_backend/app/models/project_so.py:276` |
| 35 | `public.delivery_schedule_cells` | `projects.delivery_schedule_cells` *(unchanged)* | `DeliveryScheduleCell` | `sorento_crm_backend/app/models/project_so.py:309` |
| 36 | `public.customer_item_code_map` | `projects.customer_item_code_map` *(unchanged)* | `CustomerItemCodeMap` | `sorento_crm_backend/app/models/project_so.py:336` |
| 37 | `public.project_sales_orders` | `projects.sales_orders` | `ProjectSalesOrder` | `sorento_crm_backend/app/models/project_so.py:374` |
| 38 | `public.project_sales_order_lines` | `projects.sales_order_lines` | `ProjectSalesOrderLine` | `sorento_crm_backend/app/models/project_so.py:432` |
| 39 | `public.so_draft_findings` | `projects.so_draft_findings` *(unchanged)* | `SODraftFinding` | `sorento_crm_backend/app/models/project_so.py:478` |
| 40 | `public.order_change_notices` | `projects.order_change_notices` *(unchanged)* | `OrderChangeNotice` | `sorento_crm_backend/app/models/project_so.py:523` |
| 41 | `public.so_amendments` | `projects.so_amendments` *(unchanged)* | `SOAmendment` | `sorento_crm_backend/app/models/project_so.py:560` |
| 42 | `public.project_order_inquiries` | `projects.order_inquiries` | `OrderInquiry` | `sorento_crm_backend/app/models/project_so.py:600` |
| 43 | `public.project_order_inquiry_rows` | `projects.order_inquiry_rows` | `OrderInquiryRow` | `sorento_crm_backend/app/models/project_so.py:640` |
| 44 | `public.so_line_allocations` | `projects.so_line_allocations` *(unchanged)* | `SOLineAllocation` | `sorento_crm_backend/app/models/project_so.py:695` |
| 45 | `public.allocation_claims` | `projects.allocation_claims` *(unchanged)* | `AllocationClaim` | `sorento_crm_backend/app/models/project_so.py:734` |
| 46 | `public.project_so_divergences` | `projects.so_divergences` | `ProjectSODivergence` | `sorento_crm_backend/app/models/project_so.py:790` |
| 47 | `public.project_so_divergence_lines` | `projects.so_divergence_lines` | `ProjectSODivergenceLine` | `sorento_crm_backend/app/models/project_so.py:837` |

34 tables are renamed (prefix stripped); 13 keep their bare name and only change schema
(the 12 unprefixed legacy tables plus `projects` itself).

### Seven of the stripped names collide with an EXISTING `public` table

Verified against the dev database catalog. These are the unqualified-SQL hazards, and the
reason raw SQL must be schema-qualified or converted to ORM everywhere:

| New projects name | Existing core table of the same bare name |
|---|---|
| `projects.brands` | `public.brands` (`app/models/product.py:58`) |
| `projects.purchase_orders` | `public.purchase_orders` (`app/models/procurement.py:475`) |
| `projects.purchase_order_lines` | `public.purchase_order_lines` (`app/models/procurement.py:505`) |
| `projects.sales_orders` | `public.sales_orders` (`app/models/order.py:296`) |
| `projects.sales_order_lines` | `public.sales_order_lines` (`app/models/order.py:346`) |
| `projects.quotations` | `public.quotations` (legacy table, no ORM model) |
| `projects.quotation_lines` | `public.quotation_lines` (legacy table, no ORM model) |

### Dev-database catalog state (read-only check, 2026-08-15)

- All 47 tables present in `public`. Schemas present: `public`, `scm`, `dealer_kit`. **No
  `projects` schema exists yet**, so none of the 47 new names can collide inside it.
- **Zero dependent views or materialized views** on any of the 47 (`information_schema.view_table_usage`
  and `pg_depend`/`pg_rewrite` both empty).
- **Zero triggers** on any of the 47.
- **Zero owned sequences** (`pg_get_serial_sequence` returns NULL for every column; the module
  is uuid-PK throughout).
- **Two core-to-module FKs**, both `ON DELETE SET NULL`, both onto `public.projects`:
  `complaints.project_id` and `purchase_requests.project_id`. These become cross-schema FKs,
  which Postgres handles natively.
- **92 module-to-core FKs** (project tables referencing `public` tables). All become
  cross-schema. Nothing to do: the models name those targets unqualified, and unqualified FK
  targets resolve against the default-schema metadata key, which is still `public`.
- The local dev DB is a production copy and **does hold project rows** (5 `projects`, 304
  `project_quotation_lines`, 263 `delivery_schedule_cells`, etc.). `ALTER TABLE ... SET SCHEMA`
  is metadata-only, so the rows travel; but the migration is not "no data at risk" locally.

---

## Work slices

### S1 - migration 354 + `alembic/env.py`

**New file:** `sorento_crm_backend/alembic/versions/354_projects_schema_move.py`

- `revision = "354_projects_schema_move"`, `down_revision = "353_project_order_inquiry_rename"`
  (verified: `alembic heads` returns exactly that one head).
- Body, in order:
  1. `CREATE SCHEMA IF NOT EXISTS <target>`.
  2. For each of the 47: if `<source>.<old>` exists and `<target>.<new>` does not,
     `ALTER TABLE "<source>"."<old>" SET SCHEMA "<target>"`, then, when the name changes,
     `ALTER TABLE "<target>"."<old>" RENAME TO "<new>"`.
  3. Both steps individually guarded, so the revision is idempotent and no-ops on a database
     already built by `create_all` from the post-move models.
- **Do NOT rename indexes or constraints.** They ride with the table and keep their
  `project_*` names inside the `projects` schema. This is the one place migration 354
  deliberately differs from 353, which had to rename them because a table rename in the same
  schema leaves index names behind. Record the reason in the docstring so a future
  autogenerate diff does not read as drift.
- **Schema names must be module-level constants, not literals**, or the dual-path test in S4
  cannot run in a scratch schema:
  - `TARGET_SCHEMA = "projects"` at module level (the test rebinds it to `f"{blank}_projects"`).
  - Source schema resolved at run time from `current_schema()`, NOT hardcoded `public`. In
    production `current_schema()` is `public`; in the scratch fixture it is the blank schema.
    Hardcoding `public` would make the S4 test move REAL dev-database tables.
- `downgrade()` is the exact inverse: rename back to the prefixed name inside `projects`,
  then `SET SCHEMA <source>`. Do not drop the schema on downgrade (other objects may land
  there later); leaving an empty `projects` schema is correct and keeps downgrade idempotent.

**Edit:** `sorento_crm_backend/alembic/env.py:78-80` (the `context.configure(...)` call in
`run_migrations_online`) - add `include_schemas=True` plus an `include_name` filter that
accepts only `{None, "scm", "projects"}`. Verified from the installed alembic 1.18.1 source
(`alembic/autogenerate/compare/schema.py:43-44` sets `schemas = {None}` when
`include_schemas` is false, while `alembic/autogenerate/compare/tables.py:71-73` builds
`metadata_table_names` from ALL metadata tables regardless of schema): today autogenerate
already wants to `CreateTableOp` every `scm.*` table, and after this move it would want all
47 `projects.*` tables too. The `include_name` filter is required as well, otherwise turning
`include_schemas` on newly surfaces the `dealer_kit` schema (present in the dev DB, absent
from `Base.metadata`) as DROP candidates.

**Dev-DB dry run (before committing anything):**

```bash
cd sorento_crm_backend
# 1. private scratch copy, never the shared dev DB for the first run
createdb sorento_projects_move_dryrun
psql sorento_projects_move_dryrun -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
DATABASE_URL=postgresql://localhost/sorento_projects_move_dryrun venv/bin/python -m scripts.bootstrap_env
# 2. forward, then back, then forward again - idempotence and symmetry in one pass
DATABASE_URL=postgresql://localhost/sorento_projects_move_dryrun venv/bin/alembic upgrade head
DATABASE_URL=postgresql://localhost/sorento_projects_move_dryrun venv/bin/alembic upgrade head   # must be a no-op
DATABASE_URL=postgresql://localhost/sorento_projects_move_dryrun venv/bin/alembic downgrade -1
DATABASE_URL=postgresql://localhost/sorento_projects_move_dryrun venv/bin/alembic upgrade head
# 3. catalog assertion
psql sorento_projects_move_dryrun -c "select table_schema, table_name from information_schema.tables where table_schema in ('projects','public') and table_name in ('projects','leads','project_leads') order by 1,2;"
```

Only after that clean round trip run `alembic upgrade head` against the shared dev database
(see Hazard H1 first).

### S2 - models and foreign-key strings

**82 FK strings inside the module + 2 in core = 84 total.** Counts by file, verified by AST
scan over `sorento_crm_backend/app`:

| File | FK strings targeting a project table |
|---|---|
| `sorento_crm_backend/app/models/projects.py` | 43 |
| `sorento_crm_backend/app/models/project_so.py` | 39 |
| `sorento_crm_backend/app/models/procurement.py` | 1 (line 645, `ForeignKey("projects.id", ondelete="SET NULL")`) |
| `sorento_crm_backend/app/models/complaints.py` | 1 (line 44, `ForeignKey("projects.id", ondelete="SET NULL")`) |

There are **zero** `relationship(secondary=...)`, `primaryjoin=`, `secondaryjoin=` or
string `foreign_keys=` arguments naming a project table anywhere in `app/`. Every
`relationship()` in the module targets a CLASS name, which is unaffected.

Per model class:

1. `__tablename__` -> stripped name (rows 1-47 above).
2. `__table_args__` gains `{"schema": "projects"}`. Where `__table_args__` is already a
   tuple, append the dict as the LAST element (the `scm` models do exactly this, e.g.
   `app/models/scm.py:147`, `:222`, `:332`). Where it is absent, add
   `__table_args__ = {"schema": "projects"}` (pattern: `app/models/scm.py:45`).
   `__table_args__` sites in `projects.py`: lines 106, 138, 163, 187, 275, 383, 426, 489,
   560, 694, 767, 875, 971, 1016, 1112, 1159, 1194, 1250, 1291, 1367, 1416, 1499, 1555.
   In `project_so.py`: lines 120, 156, 192, 224, 271, 303, 330, 352, 425, 473, 500, 555,
   581, 619, 677, 731, 770, 831, 875. Classes with no `__table_args__` today
   (`ProjectSalesProfile` 294, `ProjectBrand` 328, `ProjectCollaborator` 386,
   `ProjectSeriesCategory` 772, `ProjectSeriesProduct` 790) need the dict added.
3. Every `ForeignKey("<project table>.<col>")` becomes `ForeignKey("projects.<new>.<col>")`.
   FKs whose target is a CORE table (`customers.id`, `users.id`, `products.id`,
   `statuses.id`, `attachments.id`, `warehouses.id`, `brands.id`, `product_categories.id`,
   `sales_orders.id`, `purchase_requests.id`) stay unqualified - SQLAlchemy resolves an
   unqualified target against the default-schema metadata key, which is still `public`.
   Note `app/models/projects.py:343` and `:758` are `ForeignKey("brands.id", ...)` pointing
   at CORE `public.brands` while sitting on tables that are themselves becoming
   `projects.brands` / `projects.series`. Leave them unqualified and add a one-line comment,
   or the next reader will "fix" them into a self-reference.
4. Add `__audit_entity_type__ = "<old prefixed name>"` to the 34 renamed classes (point 2 of
   the ruling section above). `app/services/audit_service.py:36-37` is the consumer.
5. `sorento_crm_backend/app/models/complaints.py:44` and
   `sorento_crm_backend/app/models/procurement.py:645`: `ForeignKey("projects.id", ...)` ->
   `ForeignKey("projects.projects.id", ...)`. These two are the ADR-0009 core-to-module FKs
   and must keep `ondelete="SET NULL"`.

Sanity gate for this slice, before running any test:

```bash
cd sorento_crm_backend
venv/bin/python -c "
import app.models
from app.database import Base
proj=[t for t in Base.metadata.tables.values() if t.schema=='projects']
print(len(proj))            # must be 47
print(sorted(t.name for t in proj))
"
```

A missed `ForeignKey` string raises `NoReferencedTableError` at import time, so this one
command catches every case in item 3.

### S3 - raw SQL, scripts, MCP

The sweep over `app/`, `alembic/`, `scripts/`, `tests/`, `sorento_crm_mcp/` and
`sorento_crm_frontend/` found 746 lines across 91 files mentioning one of the 46 named
tables. **All but the following are prose (docstrings, comments, plan/ADR text) or
migrations that run BEFORE 354 and are correct as they stand.**

Actual executable references to fix:

| File:line | What it is | Change |
|---|---|---|
| `sorento_crm_backend/app/services/project_service.py:1042-1053` | `text("select 1 from information_schema.tables where table_name = 'project_purchase_orders' limit 1")` then `text("select count(*) from project_purchase_orders where project_id = :pid")` | **Convert to ORM** (`db.query(ProjectPurchaseOrder).filter_by(project_id=...).count()`). The `information_schema` existence probe was a "the PO table arrives in S4" guard and is now dead; delete it. ORM avoids hardcoding `projects.` in a string, which is what makes the test fixtures safe (Hazard H5). |
| `sorento_crm_backend/app/tasks/project_document_tasks.py:77, 93, 99-108` | `_mark_failed(db, "project_po_versions"/"delivery_schedule_versions", ...)` builds `f"UPDATE {table} SET extraction_state = ..."` | **Convert to ORM** (pass the model class, `db.query(Model).filter(Model.id == row_id).update({...})`). Same reason. If it must stay raw SQL, pass `Model.__table__.fullname` rather than a literal. |
| `sorento_crm_backend/app/services/project_lead_service.py:58` | `LEAD_AUDIT_ENTITY_TYPE = "project_leads"` | **No change**, given `__audit_entity_type__` is pinned to the old name in S2. If the orchestrator rejects that, this becomes `"leads"`. |
| `sorento_crm_backend/app/services/project_task_service.py:908` | `AuditLog.entity_type == "project_tasks"` | Same as above: no change under the `__audit_entity_type__` decision. |

Confirmed clean, no change needed:

- **`sorento_crm_mcp/`**: zero references to any project TABLE. `catalog.py:915-1020` and
  `server.py:1209-1213` name HTTP paths (`/api/v1/project-sales/...`) and JSON field names
  (`project_ids`, `project_code`), never a table.
- **`app/services/list_query_registry.py`**: no projects resource registered.
- **`app/services/scm/coverage_service.py:736`, `coverage_timeline.py:29,59`,
  `summary_order_service.py:460`**: comments only. SCM reads core `sales_orders`, never a
  project table (ADR-0010).
- **`app/services/project_schedule_service.py:93` and `project_clash_service.py:62`**
  (`_TRGM_SCHEMA = "public"`): unaffected. That constant qualifies the pg_trgm
  `similarity()` FUNCTION, which stays in `public`. Do not change it to `"projects"`.
- **`app/services/project_so_draft_service.py:780, 2188-2199`**: raw SQL against CORE tables
  (`item_package_lines`, `item_packages`, `customers`) - unqualified is correct and must
  stay unqualified.
- **`scripts/*.py`**: zero hits on any of the 46 table names.
- **Migrations 309-353** (309, 311, 312, 313, 314, 317, 319, 320, 321, 322, 323, 325, 326,
  327, 328, 329, 330 x2, 331, 332, 333, 353): they create and alter these tables in `public`
  and run BEFORE 354. **Leave every one of them untouched.** Rewriting them is the failure
  mode ADR-0009 warned about; 354 is the whole change.

**Edit:** `sorento_crm_backend/scripts/bootstrap_env.py:58` - add
`conn.execute(text("CREATE SCHEMA IF NOT EXISTS projects"))` beside the existing `scm` line.
This is how a from-zero database (CI, disaster recovery) gets the schema, because
`create_all` emits `CREATE TABLE projects.x` and does not create the schema itself. Update
the `create_schema()` docstring on line 51 (currently "plus the `scm` schema").

### S4 - test infrastructure and updated tests

**`sorento_crm_backend/tests/_pg_fixture.py`:**

- Line 84: add `admin.exec_driver_sql(f'CREATE SCHEMA "{name}_projects"')`.
- Line 88: `schema_translate_map={None: name, "scm": f"{name}_scm", "projects": f"{name}_projects"}`.
- Line 105-107 (`drop_blank_schema`): add `DROP SCHEMA IF EXISTS "{name}_projects" CASCADE`.
- Line 133: `SET LOCAL search_path TO "{name}", "{name}_scm", "{name}_projects"` -
  **`{name}_projects` must be LAST**. The default schema must stay first so `current_schema()`
  is still `{name}` and so unqualified raw SQL for `sales_orders` / `brands` /
  `purchase_orders` / `quotation_lines` keeps resolving to the CORE table (see the collision
  table above). Putting it earlier silently repoints seven core tables.
- Line 163-165 (`_with_dependencies`, used by `pg_empty_schema`): it skips any table with
  `table.schema is not None`, and `pg_empty_schema` (line 213) builds a translate map of
  `{None: name}` only. After the move a project model passed to `pg_empty_schema` would be
  skipped from the FK closure and, if passed explicitly, CREATED IN THE REAL `projects`
  SCHEMA. No current test does this (`pg_empty_schema` callers are
  `test_external_permission_guard.py:52`, `test_integration_admin_routes.py:33`,
  `test_integration_seed.py:52`, `test_integration_auth_dependencies.py:39` - none touch
  projects), so the minimum fix is to make it raise a clear error when handed a
  `schema is not None` table. Preferred: give it a `{name}_projects` schema and the matching
  translate-map entry, mirroring `blank_schema_engine`.
- Update the module docstring (lines 60-65) which currently says "`scm` is translated
  alongside the default schema".

**`sorento_crm_backend/tests/conftest.py`:** the sweeper at lines 55-63 drops every schema
matching `nspname LIKE 'zzt_%'`, and the new scratch schema is named `zzt_blank_<hex>_projects`,
so it is already covered. No change required - verify by name, do not assume.

**`sorento_crm_backend/tests/test_import_outcome_attribution.py:103-106`** builds its own
scratch schema with `{None: name}`. It creates only core tables; no change, but re-read it
if it grows.

**New file:** `sorento_crm_backend/tests/test_migration_354_projects_schema_move.py`,
modelled directly on `tests/test_migration_353_order_inquiry_rename.py` (same
`importlib.util.spec_from_file_location` + `MigrationContext.configure(db.connection())` +
`Operations.context(ctx)` pattern, same `blank_session()` fixture). It must monkeypatch the
migration module's `TARGET_SCHEMA` to `f"{blank}_projects"` before running either direction.
Tests, mirroring 353's four:

1. `test_upgrade_changes_nothing_when_the_tables_are_already_in_the_projects_schema` -
   the scratch schema is built by `create_all` from the post-move models, so 354 must no-op.
2. `test_upgrade_is_repeatable` - run it twice, assert the catalog snapshot is identical.
3. `test_upgrade_moves_and_renames_when_the_tables_are_in_the_default_schema` - run
   `downgrade()` first to build the pre-354 shape, assert all 47 prefixed names are back in
   `current_schema()` and none remain in the projects schema, then `upgrade()` and assert the
   snapshot round-trips exactly.
4. `test_rows_travel_with_the_tables` - seed a `ProjectLead` -> `Project` -> `ProjectSalesOrder`
   -> `OrderInquiry` chain (copy the seeding block from
   `test_migration_353_order_inquiry_rename.py:170-200`), `db.expunge_all()`, downgrade,
   assert the row is readable at the old qualified name, upgrade, assert it is readable at
   the new one.

Snapshot helpers should query `pg_tables` / `pg_indexes` / `pg_constraint` filtered on BOTH
the scratch default schema and the scratch projects schema, not `current_schema()` alone.

**Existing tests to update:**

| File:line | Why | Change |
|---|---|---|
| `tests/test_migration_353_order_inquiry_rename.py:44, 76-79, 85-90, 96-102, 199-213` | Its `_tables()`/`_indexes()`/`_constraints()` helpers filter on `schemaname = current_schema()`, and its final raw SQL reads `FROM project_order_inquiries`. After the move those tables live in the scratch projects schema, so every assertion silently sees an empty set. | Point the helpers at the scratch projects schema; qualify the two raw-SQL reads. Migration 353 itself still runs against `current_schema()` and is still correct: on a fresh DB it no-ops because the tables are not there at all. Keep both paths asserted. |
| `tests/test_project_quotation_images.py:692` | `text("UPDATE project_quotation_lines SET product_id = :pid WHERE id = :lid")`. **`quotation_lines` also exists in core**, so an unqualified rewrite would hit the wrong table. | Convert to ORM (`db.query(ProjectQuotationLine).filter(...).update(...)`) - the safe fix - or qualify with the scratch projects schema. |
| `tests/test_project_lead_acceptance.py:55` | `text("alter table project_leads alter column customer_id drop not null")` | Qualify to the scratch projects schema (the fixture knows its name via `blank_schema_engine().get_execution_options()["schema_translate_map"]["projects"]`). |
| `tests/test_projects_module_purge.py:185` | `assert counts["project_parties"] == 0` | Key changes with the S5 purge-return decision -> `counts["projects.parties"]`. |
| `tests/test_schema_uuid_id_principle.py:48-53, 103-109` | `EXEMPTIONS` is keyed by bare table name and `_non_compliant_tables()` returns `t.name`. After the move `project_brands` reports as `brands`, which is also a core table name, so the allowlist entry becomes ambiguous and `test_allowlist_has_no_stale_entries` fails on the four stale keys. | Switch `_non_compliant_tables()` to `t.key` (schema-qualified for schema'd tables), rekey the four projects entries to `projects.brands`, `projects.collaborators`, `projects.series_categories`, `projects.sales_profile`, and rekey the existing `currency_rate` entry (line 78) to `scm.currency_rate` - it is an `scm` model and would move under the same change. |
| `tests/test_projects_module_purge_invariants.py:127-136` | Asserts `manifest["tables"] == [model.__tablename__ for model in PURGE_ORDER]`. | Change to `model.__table__.fullname` (SQLAlchemy renders `projects.parties`), matching the S5 manifest decision. |
| `tests/test_project_quotations.py:751, 776` | Asserts `entity_type == "project_quotation_lines"` / `"price_floor_rules"`. | **No change** under the `__audit_entity_type__` decision. If that decision is reversed, these two and `tests/test_project_task_checklist.py:643, 653, 694` change too. |
| `tests/test_company_scope.py:339-340` | Comment naming four project tables. | Prose only. |

`sorento_crm_frontend/modules/registry.test.ts` needs **no change**: every assertion compares
the registry against the JSON file itself, and none constrain the table-name shape.

### S5 - purge handler and the FE manifest

- `sorento_crm_backend/app/modules/projects/purge.py`: `PURGE_ORDER` is a list of model
  CLASSES, so the order needs no edit at all - the table names move with the models. Two
  changes:
  - `_count_deleted` (line 167) and `purge` (line 184) key the returned dict on
    `model.__tablename__`. Switch both to `model.__table__.fullname` so an operator sees
    `projects.parties` and cannot confuse the module's `sales_orders` with core's.
  - Docstring (lines 1-45): the "35 of the 47 tables carry the `project_` prefix" sentence is
    now wrong twice over (it is 34, and the prefix is gone). Rewrite it to say ownership is
    the `projects` schema, declared by the two model files, and point at ADR-0011. Keep the
    RESTRICT-edge comments verbatim - they are still load-bearing.
  - Restate explicitly in the docstring that purge never issues `DROP SCHEMA`.
- `sorento_crm_frontend/modules/projects/purge_tables.json`: rewrite all 47 entries as
  `projects.<name>`, same order. Keep `moduleKey: "projects"` and the `description` string
  as they are.
- `sorento_crm_frontend/modules/registry.ts:52-58`: the comment block explaining the mirror
  is still accurate; add one line noting the entries are schema-qualified.

### S6 - documentation

- **New:** `documentation/adr/0011-project-sales-tables-live-in-the-projects-schema.md`
  (written as part of this task).
- **Edit:** `documentation/adr/0009-project-sales-is-one-module-tables-stay-public.md` -
  Status line (line 4) becomes `superseded in part by ADR-0011`, with a pointer paragraph
  after it. The one-module decision and the two-core-FK decision stay. Lines 52-56 (the
  "35 of the 47 carry the prefix" consequence) get a pointer to 0011 rather than deletion,
  because the ownership-is-the-model-files rule survives.
- **Edit:** `sorento_crm_backend/alembic/versions/353_project_order_inquiry_rename.py:1-17`
  docstring - it argues for the `project_` prefix as the convention for new tables. Add two
  lines saying 354 superseded it and why 353 is nonetheless still correct to keep (it is the
  rename that made the dev DB and a fresh DB agree before the move).
- **Edit (table names only, prose):** `documentation/plans/PLAN-project-sales-pipeline.md`
  (45 hits), `documentation/plans/PLAN-project-quotation-document.md` (21),
  `documentation/plans/PLAN-project-lead-to-so.md` (20),
  `documentation/plans/CONTRACT-project-lead-to-so.md` (10),
  `documentation/plans/PLAN-project-pre-order-sponsorship.md` (6),
  `documentation/plans/scm/PLAN-scm-purchasing-fulfilment.md` (6),
  `documentation/plans/PLAN-project-so-divergence.md` (5),
  `documentation/plans/UAC-project-sales-pipeline.md` (5),
  `documentation/adr/0003-generic-project-skeleton-plus-sorento-sales-extension.md` (5),
  `documentation/plans/UAC-project-lead-to-so.md` (4),
  `documentation/plans/AUDIT-project-sales-2026-08-12.md` (3),
  `documentation/plans/PLAN-project-intelligence-reports.md` (3),
  `documentation/plans/PLAN-standard-products-images-and-recompute.md` (3),
  `documentation/plans/DEPLOY-project-sales-module.md` (2, lines 13/19/38),
  `documentation/CONTEXT.md` (2, lines 35/173),
  `documentation/adr/0002-project-po-separate-from-scm-purchase-orders.md` (1, line 6),
  `documentation/plans/PLAN-quotation-approval-and-revision-request.md` (2),
  `documentation/plans/PLAN-series-catalogue-and-pricing-pages.md` (2),
  `documentation/plans/scm/scm-purchasing-fulfilment-acceptance-criteria.md` (1),
  `documentation/plans/quotation-product-images-acceptance-criteria.md` (1),
  `documentation/user-guides/commercial/data-analysis.md` (1).
  **Scope control:** update only the table names inside these; do not rewrite the documents.
  Historical PLAN/UAC files describing what was built at the time may instead take a single
  header note pointing at ADR-0011, which is cheaper and less lossy than a find-and-replace
  through 45 prose hits. The orchestrator should pick one of the two policies before S6.

---

## Regression guards

**Per-file pytest, in this order (fastest failure first):**

```bash
cd sorento_crm_backend
venv/bin/python -c "import app.models; from app.database import Base; \
  print(len([t for t in Base.metadata.tables.values() if t.schema=='projects']))"   # 47
venv/bin/pytest tests/test_migration_354_projects_schema_move.py -q
venv/bin/pytest tests/test_migration_353_order_inquiry_rename.py -q
venv/bin/pytest tests/test_projects_module_purge.py tests/test_projects_module_purge_invariants.py -q
venv/bin/pytest tests/test_schema_uuid_id_principle.py tests/test_company_scope.py -q
venv/bin/pytest tests/test_project_lead_acceptance.py tests/test_project_registration.py \
  tests/test_project_task_checklist.py tests/test_project_quotations.py \
  tests/test_project_quotation_document.py tests/test_project_quotation_images.py \
  tests/test_project_quotation_pdf.py tests/test_project_quotation_template.py \
  tests/test_project_quotation_template_routes.py tests/test_project_quotation_export_downloads.py \
  tests/test_project_series_products.py tests/test_project_po_intake.py \
  tests/test_project_so_draft.py tests/test_project_so_delta.py \
  tests/test_project_extraction_recovery.py -q
venv/bin/pytest tests/scm -q
```

**Full-suite gate on a private bootstrapped database** (never the shared dev DB - see H1,
and the suite takes a session-long advisory lock, see `tests/conftest.py:26-70`):

```bash
createdb sorento_projects_move_ci
psql sorento_projects_move_ci -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
cd sorento_crm_backend
DATABASE_URL=postgresql://localhost/sorento_projects_move_ci venv/bin/python -m scripts.bootstrap_env
DATABASE_URL=postgresql://localhost/sorento_projects_move_ci venv/bin/pytest -q
```

The bootstrap run is itself a guard: it proves `scripts/bootstrap_env.py` creates the
`projects` schema before `create_all`, which is exactly the failure a fresh CI database
would hit and a dev machine would not.

**Autogenerate guard** (proves `env.py` was fixed and the move produced no drift):

```bash
cd sorento_crm_backend
DATABASE_URL=postgresql://localhost/sorento_projects_move_ci venv/bin/alembic upgrade head
DATABASE_URL=postgresql://localhost/sorento_projects_move_ci venv/bin/alembic revision --autogenerate -m "drift check"
# read the generated file: it must contain no CreateTableOp/DropTableOp for projects.* or scm.*
git checkout -- alembic/versions   # or delete the generated file
```

Note: autogenerate currently raises `NoReferencedTableError` on
`complaint_product_lines.kind_id -> warranty_product_kinds` (a pre-existing missing model on
this branch, unrelated to this work). Expect to have to skip or fix that before the drift
check runs clean; do not let it be mistaken for schema-move fallout.

**Frontend:**

```bash
cd sorento_crm_frontend
npx vitest run modules/registry.test.ts
```

**One agent-browser smoke** after the backend restart. The worktree backend on :8010 runs
WITHOUT `--reload`, so it must be restarted by hand for the model changes to take effect;
the :3010 frontend is unaffected by this change. Navigate from the home page through the
sidebar into Project Sales (never a deep URL), open a project detail page and its Quotations
tab, and confirm rows render and the network tab shows a 200 on the `/api/v1/project-sales/*`
calls. That single page exercises `projects.projects`, `projects.leads`, `projects.parties`,
`projects.quotations`, `projects.quotation_versions` and `projects.quotation_lines` through
the real ORM against the moved dev database.

---

## Hazards

**H1 - the shared dev database gets stamped at 354 and sibling worktrees do not know it.**
Other checkouts of this repo share `DATABASE_URL`. None of them reference a project table
(verified: the only cross-module readers are SCM comments), so their code keeps working, but
their `alembic heads` will disagree with `alembic_version` and any `alembic downgrade` run
from a sibling checkout that lacks `354_projects_schema_move.py` will fail with
`Can't locate revision`. Run the dry run on a private database first; announce the dev-DB
upgrade; and do NOT downgrade the shared database from a checkout that does not carry the
file. Related standing gotcha: DDL against the shared dev DB must go through
`Operations.context`, never a bare `alembic stamp`.

**H2 - seven stripped names collide with existing core tables.** `brands`,
`purchase_orders`, `purchase_order_lines`, `sales_orders`, `sales_order_lines`, `quotations`,
`quotation_lines`. Any unqualified raw SQL that MEANT the project table will now silently
read the core one - no error, wrong rows. This is why S3 converts the two remaining
project-table raw-SQL sites to ORM instead of qualifying them, and why the fixture
`search_path` in S4 must put the projects schema LAST.

**H3 - `audit_log.entity_type` is derived from `__tablename__`.**
`app/services/audit_service.py:36-37`. Without `__audit_entity_type__` pins, 34 tables
change their audit entity type in place, orphaning existing audit rows and colliding with
core `brands` / `purchase_orders`. See ruling point 2.

**H4 - autogenerate drift.** `alembic/env.py` never passes `include_schemas`, and alembic
builds `metadata_table_names` from all metadata tables regardless
(`alembic/autogenerate/compare/tables.py:71-73`). Today that means autogenerate already
wants to re-create every `scm.*` table; after the move it would want all 47 `projects.*`
tables. Fixing it needs `include_schemas=True` AND an `include_name` schema filter, or the
`dealer_kit` schema (present in the DB, absent from metadata) becomes a DROP candidate.

**H5 - the scratch-fixture translate-map trap.** `schema_translate_map` rewrites ORM/Core
constructs only. A hardcoded `projects.` in a raw-SQL string reaches PAST a test's scratch
schema into the REAL `projects` tables and WRITES there. `tests/_pg_fixture.py:127-133`
documents the same trap for the default schema. Two consequences: (a) prefer ORM over
qualified raw SQL in `app/` (S3), and (b) migration 354 must not hardcode `public` or
`projects` as literals inside its ALTER statements (S1).

**H6 - `pg_empty_schema` silently drops schema-qualified tables.**
`tests/_pg_fixture.py:163-165` skips `table.schema is not None` in the FK closure and
`tests/_pg_fixture.py:213` builds a `{None: name}` translate map. A future project test
using this fixture would either get an incomplete schema or create tables in the real
`projects` schema. No current caller is affected; S4 makes it fail loudly.

**H7 - the local dev database holds real project rows.** ADR-0011's "metadata-only, zero
rows at risk" argument is about PRODUCTION. Locally there are 5 projects, 304 quotation
lines, 263 delivery-schedule cells and more. `ALTER TABLE ... SET SCHEMA` does not move data
files, so the rows survive, but the migration is not a no-op locally and the dry run is not
optional.

**H8 - `projects.projects` reads badly and `projects.brands` reads worse.** The second is a
link table between `projects.projects` and CORE `public.brands`, so an unqualified
`ForeignKey("brands.id")` sitting on a table named `projects.brands` looks like a
self-reference and is not one (`app/models/projects.py:343`). Comment both, and settle
ruling point 1 before the coder starts.

**H9 - index and constraint names keep the `project_` prefix inside the schema.** Deliberate
(the migration does not rename them), but it means `projects.parties` carries indexes named
`ix_project_parties_*`. A future autogenerate or a reader may read that as drift. Record it
in the 354 docstring and in ADR-0011's consequences.

**H10 - `bootstrap_env.py` is the only path that creates the schema on a from-zero database.**
`create_all` does not create schemas. Miss the one-line edit at `scripts/bootstrap_env.py:58`
and CI fails at table creation with `schema "projects" does not exist` - a failure that never
reproduces on a developer machine where the dev DB already has the schema from migration 354.

---

## Deviations from this plan, as built

Six, all recorded here so the plan and the code agree. Deviations 1, 2 and 5 were found in
review, after the first four; the first two supersede what S1 said about index and constraint
names.

1. **BOTH directions rename the DERIVED index and constraint names; S1 said rename nothing.**
   S1's "they ride with the table, renaming 200-odd live objects is risk spent on cosmetics"
   was wrong on the facts, in two ways.
   - **SQLAlchemy's convention name folds the SCHEMA in.** An index with no name of its own
     is `ix_%(column_0_label)s`, and `column_0_label` for a schema-qualified table is
     `schema_table_column`. So declaring `schema="projects"` renamed
     `ix_project_leads_company_id` to `ix_projects_leads_company_id` IN THE METADATA, and
     `ix_projects_company_id` (on the table `projects`) to `ix_projects_projects_company_id`,
     while every migrated database kept the old name. 46 indexes. Alembic compares indexes BY
     NAME, so this is not cosmetic and it is not a one-off: it is a permanent autogenerate
     diff on every migrated database, and a CI or disaster-recovery database built by
     `scripts/bootstrap_env.py` disagrees with production - which is precisely the
     fresh-versus-migrated divergence migration 353 existed to remove.
   - **Postgres-default names diverge the same way.** `project_brands_pkey` on a migrated
     database, `brands_pkey` on a bootstrapped one.
   `upgrade()` now renames both families to the form `Base.metadata` produces, and
   `downgrade()` renames both back, each step guarded on "the source is there and the
   destination is not" so the revision stays repeatable and no-ops on a `create_all` database.
   The index map is an explicit constant (`DERIVED_INDEXES`), not a pattern, because a
   hand-named index has the SAME shape in the catalog - `ix_project_parties_name` is a
   single-column index called `ix_<pre-move table>_<column>` and must NOT be renamed - and
   only the models can tell the two apart. A test regenerates the map from `Base.metadata`
   and fails when they drift. Postgres-default names ARE read from the catalog, because a
   name Postgres derived necessarily starts with the table name and nothing hand-named does.
   Hazard H9 is therefore closed rather than accepted.
2. **S4 test 3 asserts an EXACT catalog snapshot round trip.** With both directions renaming,
   a `create_all` schema taken down and brought back is the same catalog it started as, so
   the earlier `_with_derived_names_restored` tolerance is gone. Two further tests pin the
   point directly: the rename map against `Base.metadata`, and "after `upgrade()` on a
   migrated database the index names are the ones `create_all` writes".
3. **The 353 test rewinds through 354 rather than having its helpers re-pointed.** The plan
   proposed pointing `_tables()`/`_indexes()`/`_constraints()` at the scratch projects schema.
   Running 354's own `downgrade()` first is truer: 353 operates on `current_schema()` because
   that is where those tables were when it ran, so the test plays the real historical sequence
   with the real migration code, and the helpers and raw SQL stay exactly as they were.
4. **S6 documentation policy: pointer note for historical documents, inline edit for living
   ones.** PLAN / UAC / CONTRACT / AUDIT files and ADRs 0002, 0003, 0009 record what was decided
   or built at the time and take a single header note pointing at ADR-0011. `CONTEXT.md`, the
   DEPLOY runbook, the user guide and the two SCM documents are read for current fact and had
   their table names updated inline. The SCM pair took the inline treatment rather than the note
   because the SCM documents use their own ADR numbering, in which "ADR-0011" already means
   something else.

5. **Lookup bindings are keyed by the SCHEMA-QUALIFIED table name, and 354 rewrites the rows.**
   Not in the plan at all, and found in review. `lookup_bindings.table_name` stores a table
   name AS DATA, and three code paths keyed it on the bare one:
   `lookup_write_listener.py` read `mapper.local_table.name`, `lookup_eligibility.py` emitted
   and deduped `tbl.name`, and `_eligibility_from_metadata` did
   `Base.metadata.tables.get(table_name)` - which misses outright for a schema-qualified
   table, because that dict is keyed `"projects.leads"`. Consequences, none of which raise:
   binding a set to a projects column 422s with "not registered as a lookup-eligible
   column"; a binding on core `purchase_orders.status` also validates writes to
   `projects.purchase_orders.status` and rejects values that are valid there; and the
   eligibility picker drops one table of each colliding pair depending on model import
   order. All three now use `Table.key`, which is the bare name for a default-schema table
   (so every core binding is unchanged) and `schema.name` for the rest. The picker label
   gains the schema (`Projects / Purchase Orders`), because "Purchase Orders" twice is not a
   choice an operator can make. `upgrade()` rewrites any `lookup_bindings` row whose
   `table_name` exactly matches one of the 47 pre-move names, with the inverse in
   `downgrade()`; the dev and production databases hold zero such rows today, so the rewrite
   is a guard rather than a repair. `import_logs.entity_table` was checked and is NOT the
   same kind of column: it holds a logical entity (`orders`, `stock`), never a table name.

Also fixed in passing, unrelated to the move: `projects.series_products` (a branch-only table
from S18) was missing from the `EXEMPTIONS` allowlist in `tests/test_schema_uuid_id_principle.py`,
which was a standing failure on this branch.
