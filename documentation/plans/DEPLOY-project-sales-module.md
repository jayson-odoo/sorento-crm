# DEPLOY - project sales module (`feat/project-lead-to-so`)

What has to be RUN on production for this branch, beyond `alembic upgrade head`. Everything
here is idempotent and safe to re-run; each entry says how to tell whether it did anything.

## 0. The schema move is `alembic upgrade head` and nothing else

Migration `354_projects_schema_move` creates the `projects` schema and moves the module's 47
tables into it, dropping the `project_` prefix from the 34 that carried it (ADR-0011).
`ALTER TABLE ... SET SCHEMA` is metadata-only - no data files are rewritten - and production
still holds zero project rows, so it is fast either way. There is no script to run and no
backfill.

Two things to check afterwards, in this order:

```sql
-- 47, and the module tables are gone from public
select count(*) from information_schema.tables where table_schema = 'projects';
select count(*) from information_schema.tables
 where table_schema = 'public' and table_name like 'project\_%';   -- 0

-- the 13 that never carried the prefix have to be checked BY NAME: a partially applied
-- 354 that left one of them behind passes the LIKE above, because there is no prefix in
-- it to match. Expect 0.
select table_name from information_schema.tables
 where table_schema = 'public' and table_name in (
   'projects', 'price_floor_rules', 'quotation_templates', 'quotation_signatures',
   'delivery_schedules', 'delivery_schedule_versions', 'delivery_schedule_cells',
   'customer_item_code_map', 'so_draft_findings', 'order_change_notices',
   'so_amendments', 'so_line_allocations', 'allocation_claims');

-- the two core-to-module foreign keys followed the table across the boundary
select con.conname, n.nspname || '.' || c.relname as on_table
  from pg_constraint con
  join pg_class c on c.oid = con.conrelid
  join pg_namespace n on n.oid = c.relnamespace
  join pg_class f on f.oid = con.confrelid
  join pg_namespace fn on fn.oid = f.relnamespace
 where con.contype = 'f' and fn.nspname = 'projects' and f.relname = 'projects';
-- expect complaints_project_id_fkey and purchase_requests_project_id_fkey
```

The same revision unifies the DERIVED index and constraint names, so a migrated database and
one built from zero carry the same identifiers: `ix_project_leads_company_id` becomes
`ix_projects_leads_company_id` (SQLAlchemy folds the schema into the name it derives) and
`project_brands_pkey` becomes `brands_pkey` (Postgres derives that one from the table name).
Names the models spell out by hand keep their `project_` prefix - `projects.parties` still
carries `ix_project_parties_name` - and that is expected, not drift. A third check:

```sql
-- 0 rows: no derived index name still names a pre-move table
select indexname from pg_indexes
 where schemaname = 'projects' and indexname in (
   'ix_project_leads_company_id', 'ix_projects_company_id', 'ix_project_tasks_company_id');
select conname from pg_constraint con
  join pg_class c on c.oid = con.conrelid
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'projects' and conname like 'project\_%\_pkey';
```

A database built from zero rather than migrated - a fresh CI or disaster-recovery instance -
gets the schema from `scripts/bootstrap_env.py`, because `create_all` emits
`CREATE TABLE projects.x` and never creates the schema itself.

## 1. Retire provisional rows superseded before reconciliation shipped

**Script:** `sorento_crm_backend/scripts/backfill_retire_superseded_order_inquiry_rows.py`
**When:** AFTER the app containers carrying commit "reconcile provisional and AutoCount
numbers on ingest" are live. Order matters only in that running it earlier fixes fewer rows;
it never conflicts.

`project_so_ingest_service._reconcile_core_order` merges the Order Inquiry sheet's provisional
`sales_orders` row with AutoCount's real-numbered one AT INGEST TIME. Documents ingested
before that shipped were never reconciled, so both rows stay open and `scm.committed_v` counts
that demand twice, permanently - nothing re-runs the ingest for them. The script finds those
pairs and merges them exactly as the service would: closes the provisional header and its
lines, stamps `Retired: superseded by <doc no>`, moves the still-unresolved SO<->PO link
claims onto the real number, and repoints `projects.sales_orders.so_id` under the service's own
guard (a link a person made by hand is left alone).

```bash
# in the backend container / checkout, from sorento_crm_backend/
python scripts/backfill_retire_superseded_order_inquiry_rows.py            # DRY RUN (default)
python scripts/backfill_retire_superseded_order_inquiry_rows.py --apply    # write
```

- **Dry run is the default.** Nothing is written without `--apply`.
- **Read the dry run before applying.** It prints one line per pair:
  `<provisional number> -> <real number>  [project]`, and marks any pair whose two rows sit in
  DIFFERENT companies as `SKIPPED` - those are never merged, by design (a double count is a
  reporting error, a cross-company link is a breach).
- **Idempotent.** The match is "the provisional row is still `open` while a real-numbered row
  exists", so a row it already retired stops matching. A second run reports nothing, and a
  partial first run is corrected rather than compounded.
- **Verifying afterwards:** the same dry run should report `pairs examined: 0`.

Local development database at the time of writing: **0 pairs** (3 `projects.sales_orders` rows,
none carrying an `autocount_doc_no`), so both the dry run and the apply were no-ops there. The
production count is expected to be non-zero and must be read from the dry run before applying.
