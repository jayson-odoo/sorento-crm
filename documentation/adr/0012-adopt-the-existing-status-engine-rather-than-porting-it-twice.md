# Adopt the existing status engine rather than porting it twice

**Status:** Accepted 2026-08-01. Amends `0001` (status engine is core) on the question of *who ports it*,
not *whether*. Supersedes the S0 scope in `plans/after-sales/PLAN-after-sales-warranty.md`.

## What we found

S0 was written as "port the status engine from `foundryx-shared-service` as CORE". It was started, and the
port passed its 25 tests. Then two independent checks, run concurrently, converged on the same fact:

**The engine already exists.** Commit `0ec9875d2`, "feat(status-engine): configurable per-entity status
graphs as CORE (S0+S1)", dated 2026-07-26, ships exactly this port:

- migration `308_status_engine` creating `statuses` + `status_transitions`, and dropping the orphan
  `workflow_stages` (the same guarded drop S0 had specified)
- `app/models/status.py`, `app/status_engine/{registry,derived}.py`, `app/lazy_registry.py`
- `app/services/status_service.py` (513 LOC: `resolve_graph`, `fork_graph`, `available_transitions`,
  `assert_transition_allowed`, `migrate_records`)
- `app/api/v1/system/statuses.py` plus schemas and RBAC permissions
- an FE admin UI at `system-management/status-graphs/`
- `tests/test_status_engine.py` (551 LOC) at **the same path** the S0 port used, plus two more test files

It is **not on `main`**. It lives only on `chore/project-sales-hardening` and `feat/project-sales-pipeline`.
But it **is applied to the shared local database**, which is stamped `318_complaint_project`, a revision that
does not exist on `main` at all.

## Why the duplicate was invisible until now

Three things hid it, and each is worth naming because each will hide the next one:

1. **`alembic heads` reads the filesystem, not the database.** This worktree reports a single clean head
   (`308_requestor_uploader_attr`) while the database it talks to is nine revisions further along a
   *different* branch. The head being "clean" is not evidence of anything.
2. **Both branches numbered their migration `308`.** `308_status_engine` and `308_requestor_uploader_attr`
   share the parent `307_admin_listing_company`, so they are siblings, and merging both produces a genuine
   dual head. The numeric prefix looks like a sequence and is not one.
3. **`blank_session()` builds its schema from `Base.metadata`, not from migrations.** So a duplicate port
   goes fully green in tests against a schema that could never be created on the real database. Green did
   not mean compatible; it meant self-consistent.

## Decision

**Adopt `0ec9875d2` as the schema of record. Do not land a second engine.**

Two `statuses` tables cannot coexist, and the existing one is a superset: it has the REST surface, the admin
UI, RBAC, derived auto-edges and the rule-engine aggregate facts that the fresh port deliberately excluded.

S0 therefore shrinks from "port the engine" to **"register `complaint` and `service_job` as engine entities,
with their default graphs"** - which was always the after-sales-specific part. The engine itself is now a
dependency, not a deliverable.

## Consequences

- **After-sales depends on an unmerged commit.** The engine must reach `main` before after-sales can merge.
  `PLAN-after-sales-warranty.md` already called for landing S0 as its own PR before either consumer proceeded;
  it just did not know a consumer had already built it. **Merge order is now a real constraint and belongs to
  whoever sequences project-sales.**
- **Dealer Kit S2.5 has the same dependency** and should adopt the same engine rather than porting a third
  time.
- **The engine is FK-based; complaints are string-based.** `StatusEntity.status_attr` defaults to
  `status_id`, and the engine loads records by that FK. `complaints.status` is
  `VARCHAR(50) NOT NULL DEFAULT 'new'` holding the key itself, with no FK and no CHECK constraint. Moving
  complaints onto a `status_id` FK is a data migration across 51 rows and every branch site, which is
  precisely the change S0 promised would be a behavioural no-op. **Registering `complaint` on a
  key-valued column, or adding `status_id` alongside, is an open question that must be settled before the
  complaint graph is registered.** It is not settled here.
- **Two test files claim `tests/test_status_engine.py`.** Ours is renamed; the engine's own behaviour is the
  adopted file's to assert, and after-sales asserts only its own graph registration.
- The port's genuine additions are kept and rebased onto the adopted engine: the declarative
  `StatusSeed` / `TransitionSeed` shape, and the evidence-derived `complaint` and `service_job` graphs.

## What the duplicate port produced that we keep

The transition graph was derived from the live code rather than invented, and that derivation survives the
change of substrate. It is recorded in `plans/after-sales/status-graph-evidence.md` with a file:line citation
per edge, along with four corrections found while checking it: a twelfth status string (`resolved`), a second
genuine entry point (`new`), two invented edges, and an unguarded write path that makes the graph advisory
rather than enforced.
