# 9. Project Sales is one module; its tables stay in public

Date: 2026-08-13
Status: accepted

## Context

The Project Sales work on `feat/project-lead-to-so` (47 tables) ships as an installable
module, not as core: a catalog row `projects` in `module_manifest.py`, every router behind
`require_module_enabled_with_api_key("projects")`, FE nav entries carrying `moduleKey:
'projects'`, permission slugs namespaced under `projects.*`, and the status-engine entities
registered in `app/modules/projects/status_entities.py`. The code itself stays where this
repo already puts module code - `app/api/v1`, `app/services`, `app/models`, `app/schemas` -
per the placeholder-module convention in `app/modules/README.md`.

What was still open, and what the client settled on 2026-08-13: does the module get its own
Postgres schema the way SCM did (the `scm` schema, migration 273)?

## Decision

**One module, key `projects`.** Not split. Quotations without registration is not a product
anyone buys, and splitting would not remove the coupling - it would recreate the same
foreign keys across a module boundary, where they are harder to reason about, not easier.

**The tables stay in the `public` schema under the `project_*` naming prefix. No dedicated
Postgres schema.** SCM earned its schema because what it stores is recomputable brain state:
plans, suggestions, coverage - things that may legitimately die with the module when it is
uninstalled. Project tables are system of record. Signed quotations, customer POs,
signatures and the sales orders behind them must outlive an uninstall, which is precisely
what a drop-the-schema story puts at risk. A schema would buy symbolic separation and charge
us 28 rewritten migrations plus every raw SQL string, later, on live rows.

This is decided now rather than deferred because it is the one modularisation choice that
gets more expensive with every production row. Route gating, permission namespacing and
folder moves stay cheap forever; the physical location of the tables does not.

**Two core-to-module foreign keys are accepted, and named here so nobody discovers them by
surprise:** `complaints.project_id` and `purchase_requests.project_id`. Both are nullable,
both are `ON DELETE SET NULL`, and both were added beside text fields that keep working when
the module is absent. Core therefore carries a column that means nothing without the module.
That is the deliberate price of a reportable link instead of a typed-in project name, and
`SET NULL` is what guarantees an uninstall never blocks on them.

## Consequences

- Module completion owes a purge handler at `app/modules/projects/purge.py`, so
  uninstall-with-purge is a real operation rather than a gap.
- Purge removes rows in module-owned tables only. It never removes core rows the module
  wrote: the `sales_orders` created by the demand feed stay, and the two FK columns above go
  NULL through the foreign key, not through purge.
- "Is this a project table" is answered by the `project_*` prefix, not by a schema name. New
  tables in this module keep the prefix for exactly that reason.
- Reopening the schema question later means a data migration on live rows, and it has to be
  argued as one.
