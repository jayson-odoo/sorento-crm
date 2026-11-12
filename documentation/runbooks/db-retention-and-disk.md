# Runbook: data retention jobs and disk safety (DB-RETENTION)

Owner-run on the servers. Crew never SSHes prod and never runs VACUUM FULL there. Plan:
`documentation/plans/infra/PLAN-db-retention-12nov.md`; background and numbers:
`documentation/plans/infra/db-growth-12nov.md` (owner rulings Q1-Q5, 12 Nov 2026).

Order: 1 (WAL cap), 2 (log cap) and 3 (disk alert) as soon as possible, ideally before the deploy
that ships the retention jobs (4), because the first plan-exception drain writes a lot of WAL. Then 5 (give the space back) once it has drained.

`PGC` below = the Postgres container on node A (`docker ps --format '{{.Names}}' | grep -iE 'postgres|db'`).

## 1. Cap WAL kept for the replica slot (node A, reload, no restart)

A replica that is down for days makes node A keep every WAL file for it until the disk fills.
20 GB is the cap already in `infra/templates/compose.ha.yml:44`.

```bash
docker exec -i "$PGC" psql -U postgres -Atc "ALTER SYSTEM SET max_slot_wal_keep_size = '20GB'"
docker exec -i "$PGC" psql -U postgres -Atc "SELECT pg_reload_conf()"
docker exec -i "$PGC" psql -U postgres -Atc "SHOW max_slot_wal_keep_size"   # expect 20GB
```

If the replica falls more than 20 GB behind, its slot is invalidated and node B needs a re-seed
(`documentation/runbooks/ha-failover.md`). That is the trade: a re-seed instead of a full disk on
the primary. Undo: `ALTER SYSTEM RESET max_slot_wal_keep_size; SELECT pg_reload_conf();`.

## 2. Cap Docker container logs (both nodes)

Container stdout logs have no size cap today. Copy `infra/templates/host/docker-daemon.json`
(50 MB a file, 5 files a container) into place, merging by hand if `/etc/docker/daemon.json`
already exists:

```bash
sudo test -f /etc/docker/daemon.json && sudo cat /etc/docker/daemon.json   # merge if it exists
sudo cp infra/templates/host/docker-daemon.json /etc/docker/daemon.json
sudo systemctl restart docker      # THIS RESTARTS EVERY CONTAINER: quiet window only
```

The cap applies only to containers created after the restart; `docker compose up -d
--force-recreate` (or the next blue/green deploy) picks it up. Check one container:
`docker inspect --format '{{.HostConfig.LogConfig}}' <name>` shows `max-size:50m`.
The repo's compose (`sorento_crm/docker-compose.yml`) carries the same cap per service, so a
host without the daemon file is still capped for those services.

## 3. Disk alert at 80% (both nodes)

`infra/scripts/ha-checks.sh` alerts through Healthchecks.io at 80% (`ALERT_AT_PCT`) and prunes old
pre-migrate dumps at 85%. Check whether it is installed: `crontab -l | grep ha-checks`. If the HA
setup (`ha-failover.md` phase 1 step 5) is not done yet, install only the disk check:

```bash
( crontab -l 2>/dev/null; echo '*/5 * * * * DISK_ONLY=1 HC_URL=<healthchecks ping url> /opt/sorento-crm2/infra/scripts/ha-checks.sh >/dev/null 2>&1' ) | crontab -
```

Make a new Healthchecks.io check (period 5 minutes, grace 15) for it; never write the URL into
the repo. After HA phase 1, drop `DISK_ONLY=1` (the full checks include disk).

## 4. Turn the retention jobs live

The jobs ship live (owner approved the deletions, 12 Nov) and run nightly. Each task's last run
summary on **System management > Scheduled tasks** shows what it deleted or blanked:

| task | what it removes |
|---|---|
| Plan exceptions clean-up | undecided rows of older planning batches (newest batch per run and every decided row stay) |
| Integration log clean-up | message text and headers after 30 days, the whole row after 180 (pending, processing and failed-audit records stay) |
| API call log prune | same rule (already live before this change) |
| Chat turn trace clean-up | the AI trace of chat turns after 90 days (the turn stays) |
| Scheduled task history clean-up | scheduler run history after 90 days (the newest run of each task stays) |
| Old planning runs clean-up | superseded planning runs after 90 days (runs someone overrode or decided stay) |
| Old AI search data clean-up | superseded AI search chunks after 90 days |
| Import row detail clean-up | per-row import detail after 90 days |

To see counts without deleting (a timing or check run), use the command-line runner from the
worker container (prod has no plain `backend` service: backend_blue, backend_green, worker); it only counts unless `--apply` is given:

```bash
docker compose exec -T worker python -m app.scripts.run_data_retention --rule plan_exception_prune
```

To pause everything at once: `UPDATE system_settings SET data_retention_dry_run = true;` (the
nightly runs then only count) or disable single tasks on the Scheduled tasks screen.

Knobs, all on `system_settings` (change with the same kind of UPDATE): `data_retention_batch_size`
(5000 rows a batch), `data_retention_batch_sleep_ms` (200 ms between batches),
`data_retention_max_run_minutes` (30; a run stops between batches and the next run continues),
and one retention-days column per rule (plan section 2).

The first plan-exception run removes about 8.4M rows. It drains over one or more nights within the
30-minute budget, or press Run now on the task to push it along. A run's summary says
`finished: false` while work is left. Watch replica lag while it runs (the deletes stream to node B):

```bash
docker exec -i "$PGC" psql -U postgres -Atc "SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) FROM pg_replication_slots"
```

## 5. Give the space back to the disk (owner, quiet window)

Deleting frees space inside the table (so it stops growing) but the file keeps its size. Once the
plan-exception task reports `finished: true` with `rows_deleted` near 0 on a later run, rewrite
the table. It holds about 13.6k live rows then, so the rewrite is small, but `VACUUM FULL` takes an
exclusive lock while it reads the old file: the planning exceptions screen and Outstanding SO
confirms wait until it ends. Timing on a prod-size dev copy: see the lane's PR (crew timing note).

```bash
docker exec -i "$PGC" psql -U postgres -d <crm db> -c "SELECT pg_size_pretty(pg_total_relation_size('scm.plan_exception'))"
docker exec -i "$PGC" psql -U postgres -d <crm db> -c "SET lock_timeout = '10s'; VACUUM (FULL, ANALYZE, VERBOSE) scm.plan_exception"
docker exec -i "$PGC" psql -U postgres -d <crm db> -c "SELECT pg_size_pretty(pg_total_relation_size('scm.plan_exception'))"
```

`lock_timeout` makes it give up instead of queueing behind a long transaction (and blocking
everyone behind it); just run it again. It needs free disk about the size of the live rows (small
here). The other pruned tables (integration_log, scheduled_task_runs, chatbot.turns,
embedding_chunks) keep a large live share, so plain autovacuum reuse is enough for them; rewrite
one only if the owner decides to, with the same command and its own timing.
