# 11. Project Sales tables live in the `projects` schema, without the `project_` prefix

Date: 2026-08-15
Status: accepted

Supersedes the schema clause of ADR-0009. ADR-0009's other two decisions - Project Sales is
ONE module keyed `projects`, and the two core-to-module foreign keys `complaints.project_id`
and `purchase_requests.project_id` are accepted - stand unchanged.

## Context

ADR-0009 (2026-08-13) settled that the module's 47 tables would stay in `public` under a
`project_*` naming prefix. Its argument was that SCM earned its own schema because SCM stores
recomputable brain state that may legitimately die with the module, whereas project tables are
system of record that must outlive an uninstall - and that a schema would buy symbolic
separation while charging us rewritten migrations and raw SQL on live rows.

On 2026-08-15 the client reversed that clause. The reason is ownership, not storage lifetime:
they want the boundary between core CRM and an installable module to be visible in the
database itself, the same way `scm` is, so that "which tables does this module own?" is
answered by `\dn` rather than by reading two Python files.

Two facts made the reversal cheap enough to take now rather than argue about later:

- **Production still has zero project rows.** The module has not been released. The move is a
  metadata-only `ALTER TABLE ... SET SCHEMA` against empty tables in production; the shared
  development database holds a few hundred rows, and `SET SCHEMA` does not rewrite data files
  there either.
- **The cost ADR-0009 priced is not the cost we pay.** ADR-0009 estimated "28 rewritten
  migrations plus every raw SQL string". The actual sweep found two executable raw-SQL sites
  naming a project table in `app/` (`project_service.py` and `project_document_tasks.py`,
  both convertible to ORM), zero in `scripts/`, zero in the MCP server, and zero dependent
  views, triggers or sequences on any of the 47 tables. The migrations are not rewritten at
  all: one new revision moves the tables, and 309 through 353 stay exactly as they are,
  because they ran when the tables were in `public` and that is still true at the moment they
  execute.

ADR-0009 also said "reopening the schema question later means a data migration on live rows,
and it has to be argued as one". This is that argument, made while the row count in production
is still zero.

## Decision

**The 47 module-owned tables move to a dedicated Postgres schema named `projects`.** The
schema name is the module key, exactly as `scm` is (migration 273). One module, one schema,
one name.

**The `project_` table-name prefix is dropped inside that schema.** The prefix existed to say
"this table belongs to the projects module" in a shared namespace. The schema now says that,
and saying it twice produces `projects.project_quotation_lines`. So
`project_quotation_lines` becomes `projects.quotation_lines`, `project_leads` becomes
`projects.leads`, and so on for the 34 tables that carried the prefix. The 13 that did not -
the 12 named in ADR-0009 (`so_amendments`, `order_change_notices`, `so_draft_findings`,
`so_line_allocations`, `allocation_claims`, `delivery_schedules`,
`delivery_schedule_versions`, `delivery_schedule_cells`, `customer_item_code_map`,
`quotation_templates`, `quotation_signatures`, `price_floor_rules`) plus the registration
table `projects` itself - keep their names and only change schema.

**Ownership is still declared by the model files.** `app/models/projects.py` and
`app/models/project_so.py` remain the answer to "is this a project table", and
`tests/test_projects_module_purge_invariants.py` still derives the purge list from them. The
schema is now a second, mechanically checkable expression of the same fact rather than a
replacement for it.

**Purge stays a row-level `DELETE` through the ORM. `DROP SCHEMA` is never issued on
uninstall.** This is the part of ADR-0009's reasoning that survives intact and is the reason
the schema is safe to adopt: a schema is a namespace here, not a lifetime. Signed quotations,
customer POs, signatures and the sales orders behind them are system of record; uninstall
empties tables that an operator explicitly consented to empty, and leaves the (now empty)
schema in place.

**Cross-schema foreign keys to core are fine and are used.** Postgres foreign keys work
across schemas with no ceremony. The 92 module-to-core foreign keys (project tables
referencing `products`, `customers`, `users`, `attachments`, `statuses`, `warehouses`,
`sales_orders`, `purchase_requests`) become cross-schema references and need no change in the
models, because an unqualified `ForeignKey("products.id")` resolves against the default
schema. The two core-to-module foreign keys named in ADR-0009 become
`ForeignKey("projects.projects.id")` and keep `ON DELETE SET NULL`, so an uninstall still
never blocks on them.

## Consequences

- One new revision, `354_projects_schema_move`, creates the schema and performs 47 guarded
  `SET SCHEMA` plus 34 guarded `RENAME TO` steps, with a symmetric downgrade. Every step is
  guarded on "the source exists and the destination does not", so the revision no-ops on a
  database built from the current models and does the work on one built before the move -
  the same dual-path shape as migration 353, and pinned by the same kind of test.
- **Migrations 309 through 353 are not touched.** They created and altered these tables in
  `public`, which is where the tables are when those revisions run. Rewriting history would
  be the expensive change ADR-0009 warned about; not rewriting it is what makes this cheap.
- **Index and constraint names keep their `project_` prefix.** `ALTER TABLE ... SET SCHEMA`
  carries them along unchanged, and renaming 200-odd of them would add risk for cosmetics. So
  `projects.parties` carries indexes named `ix_project_parties_*`. That is expected, not
  drift.
- **Seven of the stripped names now exist twice in the database**: `brands`,
  `purchase_orders`, `purchase_order_lines`, `sales_orders`, `sales_order_lines`,
  `quotations` and `quotation_lines` each exist as a core `public` table AND as a
  `projects` table. They are different things and always were - ADR-0002 says exactly this
  about the two kinds of PO. The consequence is that raw SQL naming any of them without a
  schema silently resolves to the core table. The module therefore reads and writes its own
  tables through the ORM, and any raw SQL that must name one is schema-qualified.
- **`audit_log.entity_type` is pinned to the old names.** It is derived from `__tablename__`
  (`app/services/audit_service.py`), so a bare rename would orphan existing audit rows and
  make the module write `entity_type='brands'` and `'purchase_orders'` on top of core's. Each
  renamed model carries `__audit_entity_type__` set to its pre-move name. The audit trail is
  a record of what happened, and what happened was recorded against `project_leads`.
- **The schema must be created in two places, not one.** Migration 354 creates it for
  databases that migrate; `scripts/bootstrap_env.py` creates it for databases built from zero
  by `create_all`, because `create_all` emits `CREATE TABLE projects.x` and never creates the
  schema. This mirrors the existing `CREATE SCHEMA IF NOT EXISTS scm` line in the same
  function. Missing the second one fails only on a fresh CI database.
- **The test fixtures gain a third scratch schema.** `tests/_pg_fixture.py` creates
  `<blank>_projects` alongside `<blank>_scm` and adds it to the `schema_translate_map` and to
  the pinned `search_path` - LAST, so the seven colliding bare names keep resolving to core.
- **`alembic/env.py` now sets `include_schemas` with a schema-name filter.** Without it
  autogenerate compares only `public` on the connection side while comparing every schema on
  the metadata side, so it proposes re-creating every non-public table. That was already true
  for `scm`; the move made it worth fixing rather than tolerating.
- **The frontend uninstall manifest lists schema-qualified names.**
  `sorento_crm_frontend/modules/projects/purge_tables.json` reads `projects.parties`, not
  `parties`, so an operator consenting to a purge is not shown seven names that are also core
  tables the purge will not touch.
- ADR-0009's remaining consequences are unaffected: purge still deletes across all companies,
  purge still never removes core rows, and the two core FK columns still go NULL through the
  foreign key rather than through the handler.
