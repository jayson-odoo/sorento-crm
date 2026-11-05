# PLAN: deploy migrate step (DEPLOY-MIGRATE-STEP, 5 Nov 2026)

Status: in progress (Review round 1 folded in). Track: small fix track by size, but it touches the prod deploy
path, so reviewer + security-reviewer both run and crew merges only on the owner's go.

## Problem (measured)

Release run 41872253783 (42d1a56c) logged "backend_blue not healthy after 240s" and reported
FAILED, yet its 5 alembic revisions (polh_0001 .. oiod_0002) had committed to prod: the next run
41940213711 logged "database already at image head oiod_0002_pending_restore". Old code then ran
on the new schema for ~7 h.

Mechanism: `sorento_crm_backend/start.sh` ran `alembic upgrade head` inside the backend
container (one transaction, `alembic/env.py` `run_migrations_online`). `scripts/blue_green_deploy.sh`
waited 240 s for health, then stopped the new colour with `docker compose stop -t 160`, which gave
a long upgrade 160 s more to finish and commit. The script's "failed" did not say what the schema
was.

## Fix

1. **Migrate step.** After the snapshot and the second memory check, and before the new colour
   starts, a one-off container of the NEW backend image (`docker compose run --rm --no-deps
   --entrypoint alembic backend_<new> upgrade head`, named `sorento_migrate_<new>`) runs the
   upgrade under its own timeout, `MIGRATE_TIMEOUT_SECONDS` (default 1200 = 20 min, `.deploy.env`
   tunable). It logs the start revision, end revision and seconds.
   - Its connection carries `PGAPPNAME=sorento_deploy_migrate`.
   - Failure: the deploy stops, nothing is started or swapped; the script reads
     `alembic_version` and says whether the database is at the OLD head, the NEW head or neither.
   - Timeout: the client is killed, the container removed (`docker rm -f`), every Postgres
     session with that application_name is terminated (so the open transaction rolls back now,
     not when its current statement ends), then the same report.
   - Success: the colour starts with `SKIP_MIGRATIONS=1`; the health wait covers app start only.
2. **start.sh** runs `alembic upgrade head` only when `SKIP_MIGRATIONS` is not 1 (dev, tests, CI,
   a box whose compose does not pass the flag through: then it is a no-op after the step). The
   two background jobs (goods-chain index retry, PO link seen backfill) now run on every start,
   whatever the flag.
3. **Health failure after a successful step** logs "schema at <rev>, old code still serving"
   (old colour named). Same note on the Postgres-went-down abort.
4. **Backfill on every start**: `po_link_history.backfill_seen` skips any line that already has a
   `book_so_seen` or `book_so_change` event, and the 42d1a56c inline migration wrote exactly that
   shape (same entity_type, event). A test pins that rows in the old migration's shape make the
   backfill insert nothing.

Rollback (`rollback.yml`) passes `SKIP_MIGRATIONS=1` to the script: the migrate step is skipped
(the old image's alembic does not know the newer revision), as before.

## Not changed

Blue/green order otherwise: lock, preflight, pull, memory, snapshot, memory, (new) migrate, start,
health, Postgres check, swap, drain, workers, stop old.

## Owner step on the box

The prod compose (hand-edited, gitignored) must pass `SKIP_MIGRATIONS: ${SKIP_MIGRATIONS:-0}`
through to `backend_blue` / `backend_green` (runbook step 5, already needed by rollback). Without
it start.sh runs a no-op `alembic upgrade head` after the step; the deploy logs a WARNING.

## Tests

`sorento_crm_backend/tests/test_blue_green_deploy_guards.py` section DEPLOY-MIGRATE-STEP: success,
failure (no start, no swap, old-head report), timeout (killed, sessions terminated, rolled-back
report), health failure after the step (schema note), rollback skip, ordering.
`tests/test_po_link_history.py`: backfill over rows in the old migration's shape inserts nothing;
start.sh runs the backfill whatever SKIP_MIGRATIONS says.

## Review round 1 (reviewer READY; security-reviewer: no blockers, two should-fix)

- The container is bounded on its own: entrypoint `timeout --signal=TERM --kill-after=30
  <MIGRATE_TIMEOUT_SECONDS> alembic upgrade head`; the script's deadline is a backstop
  `MIGRATE_KILL_GRACE_SECONDS` (60) later. The release SSH action has no pty, so a cut session
  sends no HUP: this is what bounds the step then.
- The step's output goes to a temp file, shown afterwards, so a broken SSH pipe cannot kill the
  compose client mid-step. PIPE joined HUP/INT/TERM in the trap; the handler cleans up first.
- A non-zero client exit removes the container and ends the sessions before reading the schema
  (the client can die while the container runs on).
- Session name per run (`sorento_deploy_migrate_<tag>_<random>`), matched by prefix (pgbouncer's
  `application_name_add_host`) and database; "no session matched" is said plainly.
- "no revision was committed" wording (an autocommit block may have run).
- `MIGRATE_TIMEOUT_SECONDS` at least 1; `--preflight` warns above 3600.
- `SKIP_MIGRATIONS=1` on a schema not at the image head: WARNING.
- EXIT trap prints the schema line on any failed exit after the step and before the swap.
- `alembic/env.py`: `hide_parameters=True`, so a failing data migration prints no row values into
  the release log.
