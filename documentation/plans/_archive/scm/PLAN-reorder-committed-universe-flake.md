# PLAN: the reorder committed-universe tests stop deadlocking against a migration replay

Status: shipped (merged in #1013, 18 Sep 2026)
Domain: scm / reorder run, backend test substrate
Branch: `fix/reorder-committed-universe-flake` (worktree `sorento_crm-scm-flake`, test DB `sorento_xdist_local`)
UAC: none - repair of an existing test, no product behaviour changes.

## Symptom

CI job "Backend test suite - SCM (Postgres)" runs

```
python -m pytest -q -p no:cacheprovider -n auto --dist loadfile --durations=30 $IGNORES tests/scm/
```

`tests/scm/test_reorder_committed_universe.py` failed intermittently on unrelated branches and
on main, with assertion messages that all say the same thing in different words: the reorder run
emitted nothing for the test's own product.

- run 35299065967: four consecutive tests (AC-2.2, AC-2.3 covered, AC-2.3 buy qty, AC-2.4),
  `recs` empty each time.
- run 35293438670: one test, `test_a_second_uncommitted_location_emits_nothing_but_stays_in_the_run`,
  `assert []` on "the committed location's own buy must be unaffected".

The file passes alone (15 passed) and passed on neighbouring heads of the same branches.

## Cause (measured)

The Postgres server log CI prints at the end of the job, run 35293438670, job 105441213017:

```
ERROR:  deadlock detected
DETAIL: Process 1078 waits for AccessShareLock on relation 24614 of database 16384; blocked by process 447.
        Process 447 waits for AccessExclusiveLock on relation 24629 of database 16384; blocked by process 1078.
        Process 1078:  WITH cv_all AS ( ... )        <- reorder_run_service._planning_rows
        Process 447: DROP VIEW IF EXISTS scm.committed_v CASCADE
```

and, on the failing test itself:

```
------------------------------ Captured log call -------------------------------
ERROR app.services.scm.reorder_run_service:reorder_run_service.py:751 run_reorder <id> failed
psycopg2.errors.DeadlockDetected: deadlock detected
```

Three facts compose it.

1. **`tests/scm/test_committed_v_migration_chain.py` replayed migration DDL against the REAL
   `scm` schema.** Four of its tests ran `DROP VIEW IF EXISTS scm.committed_v CASCADE` inside a
   `blank_session()`. `blank_session` pins `search_path` to its scratch schemas, but a migration
   names `scm.committed_v` in full, so the statement lands on the shared database's own view.
   `CASCADE` takes `scm.net_position_v` with it (confirmed: `NOTICE: drop cascades to view
   scm.net_position_v`), and the transaction holds an AccessExclusiveLock on BOTH for the length
   of the test before rolling back.

2. **`reorder_run_service._planning_rows` reads exactly those two views** (`keys` is
   `scm.net_position_v UNION scm.po_ordered_v`, and expanding `net_position_v` reaches
   `scm.committed_v`). The two take the same pair of locks in opposite orders - the plan query
   `net_position_v` then `committed_v`, `DROP ... CASCADE` `committed_v` then `net_position_v` -
   so with four xdist workers on one database the cycle closes and Postgres kills one of them.

3. **`run_reorder` never raises.** It RECORDS a failure on the run (`status='failed'` +
   `error_text`) so the RQ worker survives, which is right for production and is why the victim
   test reads an empty plan and fails on its own assertion, with nothing on screen pointing at
   the migration file four alphabetical positions away.

Why a window of several consecutive tests: the DROP holds `scm.committed_v` for the rest of its
own test, so every plan read that arrives in that window is a candidate.

Two mechanisms were considered and ruled out by measurement rather than argument:

- **Blocking alone.** Holding `BEGIN; DROP VIEW IF EXISTS scm.committed_v CASCADE;` open for 90s
  while the reorder file runs makes it 270s instead of 40s, and all 15 still pass. Waiting is not
  the failure; the lock CYCLE is.
- **Committed rows leaking from another file.** `tests/scm/test_outstanding_import_batch_commit.py`
  does commit real rows behind a marker, but nothing it writes or deletes can remove the test's own
  product from `_planning_rows`, and the CI log names the actual pair.

`tests/scm/test_m0_cp1_schema.py` carries a worse version of the same hazard (its 273 round trip
drops the whole `scm` schema and four core tables). It is in `tests/ci_excluded.txt`, so it is out
of this repair; a full local `tests/scm/` run without the CI ignore list will still hit it.

## Fix

One seam: `tests/scm/test_committed_v_migration_chain.py` replays onto its OWN scratch schema, the
way two tests in that same file already did for their data assertions.

- `_scratch_schemas(db)` / `_rebind(sql, scm_schema, projects_schema)` - the rebinding those two
  tests spelled inline, now named once and used by all six.
- `_ScratchOperations(Operations)` - `alembic.op` for a `blank_session`, rewriting the SQL of every
  `op.execute` onto the scratch schemas. The migration FUNCTION is still what runs
  (`m384.upgrade()`, `m424.upgrade()`, the 340-then-346 replay); only where its DDL lands moves.
  `scm.committed_v` is the only `scm`-qualified object any replayed body executes, and `projects.`
  the only other prefix, so the same two replacements cover it.
- The proxy then ASSERTS that no `scm.` / `projects.` prefix survived the rewrite (`_UNREBOUND`,
  whose lookbehind lets through what a rebind produces and what prose mentions). `_rebind` only
  knows the two prefixes these six bodies use, and 376's `_NET_POSITION_V` (`scm.net_position_v`,
  `scm.on_order_v`) is one statement away from being replayed here, so a migration added later that
  names another real object fails loudly instead of quietly landing on the shared schema.
  `test_the_proxy_refuses_a_statement_still_naming_the_shared_schema` pins it: disable the assert
  and the statement reaches the real view, which Postgres refuses with "cannot drop columns from
  view" - the proof that it was aimed there.
- An autouse fixture restores `alembic.op._proxy` after every test (the attribute does not exist
  until something sets it, so restoring can mean removing it again). Otherwise the next test in that
  worker inherits a proxy bound to a closed connection and a dropped schema.
- `_column_types(db, scm_schema)` and `_view_body(db, scm_schema)` read the catalogue at the scratch
  schema instead of `'scm'`.
- The four `CREATE SCHEMA IF NOT EXISTS scm` / `DROP VIEW IF EXISTS scm.committed_v CASCADE` pairs
  are gone. The scratch `_scm` schema carries no views at all (views are not on `Base.metadata`), so
  "the world as 339 left it" is already what is there.

No application code changed. `run_reorder` still records rather than raises: that is the production
contract, and hiding a deadlock behind a retry would be the wrong repair for a test-substrate bug.

## Evidence the fix works

`documentation/plans/scm/` holds no harness, so both probes live in the PR description only:

1. **Deterministic contention probe.** An ordinary reader holds what a plan read holds - an
   AccessShareLock on `scm.net_position_v` and `scm.committed_v` - for 90s, and the migration-chain
   file runs against it.
   - before: 42.9s -> 140.6s (delta +97.7s): the file waits the holder out, which is the
     precondition for the CI cycle.
   - after: 62.8s -> 56.8s (delta -5.9s): the file never asks for the real views.
2. **Not vacuous.** The rebound round trip installs a real 3,926-character body with 7 columns in
   the scratch schema and leaves the real `scm.committed_v` in place, so the column-type and body
   assertions are still asserting something.
3. `tests/scm/test_committed_v_migration_chain.py` 15 passed; `tests/scm/test_reorder_committed_universe.py`
   15 passed.
4. Three consecutive `-n 4 --dist loadfile tests/scm/` runs with CI's own ignore list, on the
   private database `sorento_xdist_local`: **3729 passed, 13 skipped, 13 xfailed, 0 failed** each
   (42m21s, 12m26s, 13m20s). A fourth after the review round, with the guard and its test:
   **3730 passed, 13 skipped, 13 xfailed, 0 failed** (9m06s).
5. One earlier run of the SAME command with the ignore list accidentally not applied (zsh does not
   word-split an unquoted `$IGNORES`, so all 4,099 tests ran including `test_m0_cp1_schema.py`,
   which drops the whole `scm` schema and four core tables) came back with 155 failures, every one
   of them in a CI-excluded file, plus one concurrency casualty in
   `test_location_stock_as_of.py::test_each_location_carries_is_pool_and_its_open_po_quantity`
   (5 passed alone). Both of this lane's files were clean in that harsher run too.

## Follow-ups (not in this change)

- `tests/scm/test_m0_cp1_schema.py` does the same thing harder and is only safe because CI excludes
  it. The trigger for repairing it the same way is anyone taking it off `ci_excluded.txt`.
- `tests/scm/test_description_translation.py` (and `tests/test_ingest_contract_v2.py`, other job)
  hold an AccessExclusiveLock on a real `scm` TABLE for a test, via `ALTER TABLE ... DROP COLUMN IF
  EXISTS` inside `pg_session()`. Nothing in the plan read touches those tables, so there is no cycle
  to close today and they are left alone; the trigger is a reader of `scm.proforma_invoice_line` /
  `scm.order_link_claim` appearing in a query that also reads a second `scm` relation.
  `tests/test_ingest_documents_v2_hooks.py` already does the rewrite this change adopts, and its
  docstring names the same hazard.
- `tests/scm/conftest.py::ensure_reference_data` inserts four FIXED codes (`ZZSCMREF-*`) under a
  `(company_id, code)` unique index, so every `scm_app` test in every worker serialises behind every
  other one. Measured locally: the reorder file takes 40s alone and 425s under a 3-worker load. That
  is a cost, not a defect, and it is a separate piece of work.
