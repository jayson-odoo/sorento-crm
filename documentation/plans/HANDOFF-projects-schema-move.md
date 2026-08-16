# Handoff - Project Sales schema move (PR #155)

Written 2026-08-16 when a weekly usage limit (resets Aug 18, 5pm Asia/Kuala_Lumpur) stopped the
last gate run. Read this instead of reconstructing the session.

## State

- Worktree `.claude/worktrees/project-sales`, branch `feat/project-lead-to-so`, HEAD `9b6b32697`,
  clean, PUSHED. **PR #155 is open and must NOT be merged** - merge to main triggers deploy, and
  the captain merges personally.
- No servers running in this lane. The machine allows two stacks; neither is ours.
- Shared dev DB `sorento_ai_automation` is migrated to `354_projects_schema_move` with the
  unified identifier names. Rows intact (5 projects, 304 quotation_lines, 263 schedule cells).

## What this branch does

Two client decisions, both recorded as ADRs:

- **ADR 0009 + 0010** (2026-08-13/14): Project Sales ships as ONE installable module `projects`;
  the Order Inquiry loop (derive, export, Joey edits, Excel import, core `sales_orders`) is owned
  end to end by the module, with Excel still the only writer.
- **ADR 0011** (2026-08-15): reverses ADR 0009's schema clause. The 47 tables move out of
  `public` into a dedicated `projects` schema and the `project_` prefix is dropped from 34 of
  them. Decided while production still had zero project rows, so it is a metadata-only move.

Migration `354_projects_schema_move` does the move, and also unifies derived index and constraint
names so a database built by `scripts/bootstrap_env.py` and one built by `alembic upgrade head`
agree identifier for identifier.

## Decisions taken, so they are not relitigated

1. Schema name is `projects` (the module key), not `project`. Matches the `scm` precedent.
2. The prefix is dropped because the schema is now the ownership marker.
3. `public.projects` becomes `projects.projects`. It was NOT renamed to `registrations`.
4. `__audit_entity_type__` is pinned to the OLD names on all 34 renamed models, so audit history
   is not orphaned and the module cannot write `entity_type='brands'` on top of core's.
5. Purge stays a row-level DELETE through the ORM. `DROP SCHEMA` is never issued on uninstall.
6. The FE purge manifest carries schema-qualified names, pinned by pytest against
   `Table.fullname`.
7. Lookup bindings are keyed by the schema-qualified name (`Table.key`), because seven bare names
   now exist twice.
8. `demand_origin` stays the literal `'scm_order_inquiry'` (baked into raw SQL and a CHECK).

## Next steps, in order

1. **Finish the gate.** Full suite on a private bootstrapped HEAD DB versus a baseline DB built
   from `df102ce4b`, and diff the FAILED names. The baseline side is done; the HEAD side was cut
   off. Re-runnable shard scripts are in the session scratchpad under `shards/`
   (`run-{head,base}-{1,2,3}.sh`); the HEAD-only test files must stay out of the baseline lists.
   Expect 0 new failures. Two known pre-existing ones are listed in the PR body.
2. **Then report to the captain for the merge decision.** Do not merge.
4. At deploy time: `alembic upgrade head`, then the catalog checks in DEPLOY runbook section 0,
   then the prod backfill dry-run before `--apply`.

## Reviews done

Two independent passes, and they found different things, which is the argument for running both.

- A Claude reviewer compared `Base.metadata` against a live catalog and found that declaring
  `schema="projects"` renamed 46 convention-derived indexes in the metadata only, so a migrated
  database and a bootstrapped one disagreed on 81 index and 159 constraint names and autogenerate
  churned 92 index ops forever. Also found the lookup bindings keyed on a bare table name. Both
  fixed in `5101d0a86` and `4dd1553bb`.
- A codex pass over `354_projects_schema_move.py` found a silent no-op inside `_rename_index`
  (fixed in `84b947e3d`) and proposed three pieces of defensive machinery, all measured and
  rejected: the 63-byte assertion (longest real name is 53), and two allowlists to replace the
  catalog scan (no name in the catalog matches a table stem without being Postgres-derived, and a
  test already pins that). Rejections are recorded in that commit message with the measurement.

## Known, out of scope, worth a ticket

- `test_no_request_path_ever_calls_the_reader` fails at and before this branch: its allow-list
  went stale when `2be03d4ff` split the service, so `run_extraction(` now also appears in
  `services/project_po_intake_lifecycle.py`.
- `tests/scm/test_m2_demand.py` goldens fail on a data condition (the golden SKU has no rows in
  `scm.consumption_v`), identically at the pre-change commit.
- The shared dev DB carries 37 identifier divergences that predate the move: 30 indexes the
  models declare that no migration ever created, and 7 hand-named in migrations that the models
  never declare. Either add the missing ones in a new revision or declare the hand-named ones on
  the models. On a from-zero database the divergence is 0.

## Pointers

- `documentation/adr/0009-project-sales-is-one-module-tables-stay-public.md` (status: superseded
  in part by 0011), `0010-order-inquiry-loop-owned-by-project-sales.md`,
  `0011-project-sales-tables-live-in-the-projects-schema.md`
- `documentation/plans/PLAN-projects-schema-move.md` (contract, with six recorded deviations)
- `documentation/plans/DEPLOY-project-sales-module.md` (section 0 catalog checks, backfill)
- `sorento_crm_backend/alembic/versions/354_projects_schema_move.py`
- `sorento_crm_backend/app/modules/projects/purge.py`,
  `sorento_crm_frontend/modules/projects/purge_tables.json`
- `sorento_crm_backend/tests/`: `test_migration_354_projects_schema_move.py`,
  `test_lookup_bindings_schema_qualified.py`, `test_projects_audit_entity_types.py`,
  `test_project_document_task_failure_marking.py`
