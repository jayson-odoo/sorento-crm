# DB growth scout (12 Nov 2026)

Status: scout done, waiting on the owner's prod numbers (section 5) and rulings (section 9). No app
code, no migration. Lane DB-GROWTH.

Problem: prod Postgres will outgrow the Hostinger VPS disk. Node A (primary, KVM 4) and node B
(streaming replica, KVM 8) both hold the full database.

Paths are relative to `sorento_crm_backend/` unless they start with a top-level folder. "inferred:"
marks anything not read directly from code or a query result.

## 0. Answer in five lines

1. One table is 39% of the database and 60% of its growth: `scm.plan_exception` (13 GB, 8.4M rows,
   about 5.5 GB a month). Every planning batch is kept forever, but the screen reads only the
   newest batch per run: 13,584 of the 8,410,784 rows (section 2.1).
2. Without it the database grows about 3.5-4 GB a month; the biggest of the rest is the Respond.io
   send/receive log in `integration_log` (about 1.4 GB a month).
3. Files are not the problem: uploads already live in S3/R2; the one bytes column is empty (section 3).
4. Node A safety gaps: no disk alert proven installed, `max_slot_wal_keep_size=-1` (a dead replica
   can fill A), no Docker log size cap, no WAL archive to R2 (sections 4, 6, 7).
5. Cheapest fix first: plan_exception retention + one repack frees about 13 GB and removes about
   5.5 GB a month of growth, before any plan upgrade (section 8).

## 1. Dev database (NOT prod)

Measured 12 Nov on the shared dev DB `sorento_prod_1112`, a restore of prod data up to 12 Nov
03:00 (crew event log). Read-only session (`default_transaction_read_only=on`).

**Dev is not prod.** A fresh restore has no bloat: every table and index is rebuilt compact and
`n_dead_tup` is 0 on all 25 tables below. Row counts and growth per month ARE prod's (same rows);
sizes on prod are larger. Prod was "about 54 GB" on 1 Nov
(`documentation/plans/infra/PLAN-n8n-decom-ha-01nov.md:183`) against 34 GB here, so inferred: about
20 GB on prod is bloat (dead space in tables and indexes) that a restore drops. The owner's query
5.2 (f) gives the per-table prod sizes; prod minus dev per table is that table's bloat.

- Database size: **34 GB**; 453 tables; `public` 18 GB, `scm` 15 GB, `chatbot` 821 MB.

Top 25 relations (total = heap + indexes + TOAST):

| # | table | total | % of DB | heap | indexes | TOAST | rows |
|---|---|---|---|---|---|---|---|
| 1 | scm.plan_exception | 13 GB | 38.8 | 13 GB | 428 MB | 0 | 8,410,784 |
| 2 | embedding_chunks | 7,115 MB | 20.3 | 247 MB | 3,434 MB | 3,434 MB | 434,642 |
| 3 | integration_log | 3,856 MB | 11.0 | 2,955 MB | 833 MB | 67 MB | 2,171,241 |
| 4 | import_job_rows | 2,363 MB | 6.8 | 1,625 MB | 737 MB | 0 | 6,934,847 |
| 5 | scm.reorder_recommendation | 1,280 MB | 3.7 | 508 MB | 33 MB | 738 MB | 512,747 |
| 6 | audit_logs | 932 MB | 2.7 | 633 MB | 198 MB | 101 MB | 590,403 |
| 7 | scheduled_task_runs | 904 MB | 2.6 | 584 MB | 221 MB | 98 MB | 3,018,479 |
| 8 | chatbot.turns | 783 MB | 2.2 | 64 MB | 6 MB | 714 MB | 37,163 |
| 9 | orders | 574 MB | 1.6 | 269 MB | 107 MB | 198 MB | 212,821 |
| 10 | api_call_log | 497 MB | 1.4 | 164 MB | 40 MB | 293 MB | 391,412 |
| 11 | order_lines | 370 MB | 1.1 | 200 MB | 170 MB | 0 | 707,537 |
| 12 | billing_document_lines | 350 MB | 1.0 | 232 MB | 119 MB | 0 | 817,088 |
| 13 | sales_order_lines | 322 MB | 0.9 | 250 MB | 72 MB | 0 | 887,059 |
| 14 | embedding_documents | 296 MB | 0.8 | 182 MB | 114 MB | 0 | 360,981 |
| 15 | order_summary_row | 274 MB | 0.8 | 251 MB | 21 MB | 2 MB | 211,183 |
| 16 | integration_references | 252 MB | 0.7 | 97 MB | 155 MB | 0 | 480,237 |
| 17 | chat_histories | 133 MB | 0.4 | 66 MB | 66 MB | 2 MB | 110,600 |
| 18 | billing_documents | 121 MB | 0.3 | 73 MB | 48 MB | 0 | 245,027 |
| 19 | embedding_queue | 111 MB | 0.3 | 91 MB | 20 MB | 0 | 149,006 |
| 20 | sales_orders | 109 MB | 0.3 | 66 MB | 42 MB | 0 | 212,453 |
| 21 | purchase_order_lines | 69 MB | 0.2 | 36 MB | 33 MB | 0 | 155,012 |
| 22 | spo_allocations | 58 MB | 0.2 | 29 MB | 29 MB | 0 | 88,325 |
| 23 | notifications | 56 MB | 0.2 | 33 MB | 14 MB | 10 MB | 42,602 |
| 24 | stock_ledger | 50 MB | 0.1 | 39 MB | 11 MB | 0 | 161,511 |
| 25 | n8n_chat_histories | 43 MB | 0.1 | 28 MB | 1 MB | 15 MB | 53,945 |

Top 5 = 80.6% of the database.

Growth: rows (thousands) / MB of row data per month, by each table's creation timestamp. MB is
`sum(pg_column_size(row))`, so it excludes indexes. November = 1-11 Nov only (11 days).

| table (timestamp) | Jun | Jul | Aug | Sep | Oct | Nov 1-11 |
|---|---|---|---|---|---|---|
| plan_exception (created_at) | - | - | 0 / 0 | 3,717 / 5,376 | 3,914 / 5,657 | 778 / 1,126 |
| embedding_chunks (embedded_at) | 26 / 172 | 35 / 226 | 47 / 306 | 82 / 534 | 121 / 779 | 2 / 15 |
| integration_log (created_at) | 59 / 71 | 95 / 119 | 142 / 180 | 168 / 201 | 964 / 1,261 | 530 / 736 |
| import_job_rows (created_at) | - | 290 / 65 | 2,176 / 479 | 2,863 / 653 | 1,368 / 312 | 319 / 68 |
| reorder_recommendation (created_at) | - | 55 / 88 | 278 / 534 | 97 / 261 | 63 / 178 | 17 / 49 |
| audit_logs (changed_at) | 0 / 2 | 2 / 5 | 36 / 18 | 47 / 31 | 347 / 415 | 93 / 122 |
| scheduled_task_runs (started_at) | 261 / 57 | 426 / 86 | 575 / 112 | 598 / 116 | 613 / 152 | 215 / 60 |
| chatbot.turns (created_at) | - | - | - | 7 / 137 | 21 / 418 | 8 / 162 |
| orders (created_at) | 13 / 27 | 7 / 15 | 9 / 14 | 8 / 18 | 172 / 342 | 2 / 6 |
| api_call_log (created_at) | - | 15 / 2 | 60 / 8 | 70 / 10 | 168 / 245 | 75 / 149 |

Reading it:
- October, all ten tables: about 9.4 GB of row data (about 10.5 GB with index growth, inferred
  from each table's index share). The orders spike in October is a one-off AutoCount load, not a rate.
- 1-11 Nov pace: about 2.5 GB in 11 days, about 7 GB a month. plan_exception swings with uploads:
  26 Oct (641,141 rows) and 1 Nov (654,120 rows) were each one confirmed Outstanding SO upload
  producing about 800 batches.
- **Planning range: 7-11 GB a month today; about 3.5-4 GB a month without plan_exception.**

## 2. What writes the top 10, and is anything pruned?

| table | written by | holds | retention today |
|---|---|---|---|
| scm.plan_exception | `generate_batch` `app/services/scm/plan_exception_service.py:395` (rows :444); called per external SO push `app/api/v1/external/ingest.py:521` and per confirmed Outstanding SO upload `app/services/scm/outstanding_import_service.py:3024` | planning snapshots: timeline/reading/actions jsonb, about 1.5 KB a row | **none.** New batches only insert; the screen reads the newest batch (`plan_exception_service.py:468-472`, `:481`). Only delete is the FK cascade from the batch (`app/models/scm.py:1157`), which nothing triggers |
| embedding_chunks | `process_embedding_queue_item` `app/services/embedding_worker.py:831` (chunk insert :1019), per edit of a listened record | vector(1536) + chunk text (AI search) | **none scheduled.** A re-embed flips old chunks to `is_current=false` (`app/services/embedding_service.py:231`) and keeps them: 61,003 superseded rows. Manual only: `app/scripts/dedupe_embedding_chunks_current.py:184` |
| integration_log | `create_integration_log` `app/services/integration_service.py:860`; callers incl. `app/tasks/respond_io_tasks.py:139`, `:184`, `:754`, Respond webhook, SLA, notifications | request/response headers + payloads as text | **none.** Code says so: `app/utils/online_index.py:235`, `app/api/v1/external/chat_history.py:157`. Last 30 days: respond_io 1,066,380 rows / 1,416 MB of about 1.6 GB total |
| import_job_rows | `ImportOutcome.flush` `app/services/import_outcome.py:295`, one row per source row | per-row import outcome | **code exists, never runs.** `prune_import_job_rows` (`import_outcome.py:443`, setting `import_job_rows_retention_days` = 90, `app/models/user.py:526`, handler registered `app/scheduler/task_scheduler.py:886`), but no migration seeds an `import_job_rows_prune` row in `scheduled_tasks` (grep of `alembic/versions` finds none) and the restore has none. 928,382 rows are past 90 days |
| scm.reorder_recommendation | `run_reorder` `app/services/scm/reorder_run_service.py:757`; daily `scm_reorder_run` + planner Start Plan + chat low-stock report | per-run recommendations, inputs/allocation jsonb | **none.** A re-plan only stamps `superseded_by_run_id` (`reorder_run_service.py:816-820`). 213 runs kept |
| audit_logs | audit listener `app/services/audit_service.py:989`, `:1307` (per audited change) | audit trail, old/new values jsonb | **none, by design.** Postgres trigger blocks DELETE/UPDATE/TRUNCATE (`app/models/audit.py:108`); R2 archive only planned (`documentation/plans/audit/PLAN-audit-standard-26sep.md` section 7.3) |
| scheduled_task_runs | `create_run` `app/services/scheduled_task_service.py:662`; scheduler heartbeat every 10 s (`app/scheduler/task_scheduler.py:912-918`) | one row per task run | **none.** Last 30 days: Takeover Cooldown Commit 120,559, Form Action Grace Commit 120,519, Embedding job processor 120,388 runs (each 15 s or 10 s) |
| chatbot.turns | `app/services/chatbot/engine.py:2937`, `inbox_queue.py:310`, `agent/loop.py:1675`, one per customer message | AI trace + chat I/O, about 20 KB a turn | **none.** Plan promised 90 days (`documentation/plans/chatbot/PLAN-chatbot-turn-engine.md:280`); not built |
| orders | AutoCount ingest `app/services/autocount_doc_ingest_service.py:1182` (`:796` stores the whole AutoCount document in `source_record`) | business data | none, and none wanted (business record) |
| api_call_log | `write_call_log` `app/services/api_call_log_service.py:268` | MCP / API-key request log | **yes:** `prune_api_call_log` `api_call_log_service.py:214`, daily task (`task_scheduler.py:885`), payloads blanked after 30 days, rows deleted after 180 (`app/models/user.py:521-522`). Last success 10 Nov; yet 13,065 rows past 30 days still hold a payload (inferred: a batch limit or one column not blanked; small) |

## 3. Files in the database

- One bytes column: `cost_price_change_sets.source_file_bytes` (`app/models/cost_price.py:134`,
  deferred `LargeBinary`). 0 rows hold bytes on the restore.
- Attachments are a storage key, not bytes: every upload is an S3 or R2 object routed per row
  (`app/services/storage_router.py`; CLAUDE.md "Storage routing").
- Base64 `data:` URIs are built only while rendering (`app/services/project_quotation_pdf_service.py:428`,
  `app/services/product_image_service.py:412`, `:485`); inferred: not stored.
- The big TOAST is JSON, not files: turns 714 MB, reorder_recommendation 738 MB, api_call_log 293 MB,
  orders 198 MB (`source_record`), embedding vectors 3.4 GB.

So moving files to R2 saves about 0.

## 4. Disk users that are not tables

| item | what the repo says | risk |
|---|---|---|
| WAL kept for the replica slot | Prod 7 Nov: `max_slot_wal_keep_size=-1`, `wal_keep_size=0`, slot `sorento_crm_replica_slot` active (`documentation/plans/infra/PLAN-ha-b-replica-sync-07nov.md:313-314`). Template wants 20GB (`infra/templates/compose.ha.yml:44`), gap G9 (`PLAN-ha-b-replica-sync-07nov.md:325`) | **high**: B down for days = A's disk fills with WAL. Fix is a reload, no restart |
| WAL archive | `archive_mode=off` on prod (`PLAN-ha-b-replica-sync-07nov.md:313`, G8 :319) | none on disk today (nothing archived) |
| `max_wal_size` | template 4GB (`infra/templates/compose.ha.yml:40`); prod value unknown | normal pg_wal size up to about this |
| Pre-migrate dumps | one `pg_dump` per deploy into `backups/pre-migrate`, kept 48 h (`scripts/blue_green_deploy.sh:123-124`, prune `:523`); 27 Oct: 8 dumps, about 39 GB (`documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md:84`) | medium: each dump grows with the DB; several deploys in 48 h stack up |
| Nightly backup | `scripts/ops/backup-db.sh` dumps, uploads with rclone to Google Drive (`:47`, `:122`), deletes the local copy, 30-day retention | low |
| Re-seed copy (HA) | a failed rewind moves the data dir aside and keeps it 7 days (`infra/scripts/ha-pg.sh:185`, `:245`; `infra/scripts/cf_failover.py:125`) | **high once HA failover runs**: node A must hold 2 copies of the DB (section 8.2) |
| Docker container logs | no `logging:` / `max-size` in any compose or deploy script (grep over `sorento_crm/`, `infra/`, `scripts/`, `.github/`) | medium: json-file logs grow without cap (inferred; prod compose is not in git) |
| App log files | only the `backend_logs:/app/logs` volume (`sorento_crm/docker-compose.yml:77`); no file handler in app code | low |
| Docker images | `docker image prune -af --filter "until=48h"` per deploy (`scripts/blue_green_deploy.sh:790`) | low |

## 5. Owner-run prod checks (read-only; crew never runs these)

Run on node A (primary) and node B (replica) as the deploy user, from `/opt/sorento-crm2`. Nothing
below writes: the shell part only lists, the SQL is SELECT-only inside a read-only transaction.
Paste the output back to crew (sizes and table names only; no customer rows are printed).

### 5.1 Shell, both nodes

```bash
# Disk per filesystem. Use% on "/" is what fills; 80% is the ha-checks.sh alert line.
df -h

# Docker's share: images, containers, volumes, build cache. RECLAIMABLE = could be freed.
docker system df

# Which container is Postgres on this node (on node B the replica is not the compose db service,
# PLAN-ha-b-replica-sync-07nov.md:316). Note its NAME for 5.2.
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -iE 'postgres|pgvector'

# The five biggest container stdout logs (no size cap in git, section 4).
sudo sh -c 'ls -S /var/lib/docker/containers/*/*-json.log | head -5 | xargs ls -lh'

# Pre-migrate dumps and other backups on this disk.
du -sh /opt/sorento-crm2/backups/* 2>/dev/null

# Is the disk alert installed? A line = installed; nothing = not installed.
crontab -l 2>/dev/null | grep -n ha-checks; sudo crontab -l 2>/dev/null | grep -n ha-checks
```

### 5.2 SQL, both nodes

Set `PGC` to the container name from `docker ps`, then paste.

```bash
PGC=<postgres container name>
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=120s' "$PGC" \
  sh -c 'psql -X -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}"' <<'SQL'
\pset footer off
-- (a) Primary (f) or replica (t)?
SELECT pg_is_in_recovery() AS is_replica, version();

-- (b) Every database and its size. The CRM database is the big one.
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database ORDER BY pg_database_size(datname) DESC;

-- (c) WAL directory. Normal is up to about max_wal_size; far above it = the slot or a failing
--     archive_command is holding WAL.
SELECT count(*) AS wal_files, pg_size_pretty(sum(size)) AS wal_size FROM pg_ls_waldir();

-- (d) Settings that decide how much WAL can pile up.
SELECT name, setting, unit FROM pg_settings
WHERE name IN ('max_slot_wal_keep_size','wal_keep_size','max_wal_size','archive_mode',
               'archive_command','autovacuum','logging_collector','log_directory')
ORDER BY name;

-- (e) Archiver: failed_count rising = archive_command failing and WAL being kept.
SELECT archived_count, failed_count, last_failed_time FROM pg_stat_archiver;
SQL
```

Then in the CRM database (replace `<crm db>` with the biggest name from (b)):

```bash
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=300s' "$PGC" \
  sh -c 'psql -X -U "${POSTGRES_USER:-postgres}" -d "<crm db>"' <<'SQL'
\pset footer off
-- (f) Top 25 tables. Compare with section 1: prod minus dev for a table = roughly its bloat.
SELECT n.nspname AS schema, c.relname,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
  pg_size_pretty(pg_relation_size(c.oid)) AS heap,
  pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
  pg_size_pretty(coalesce(pg_total_relation_size(c.reltoastrelid),0)) AS toast,
  c.reltuples::bigint AS est_rows
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','m','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 25;

-- (g) Dead rows (node A; a replica keeps no vacuum stats). dead_pct over about 20% on a big
--     table = autovacuum is behind. That space is reused by the table, not given back to the disk.
SELECT schemaname, relname, n_live_tup, n_dead_tup,
  round(100.0*n_dead_tup/nullif(n_live_tup+n_dead_tup,0),1) AS dead_pct,
  last_autovacuum::date, last_vacuum::date
FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 25;

-- (h) Replication slot (node A). retained_wal large and growing with active = f means the
--     replica is down and A's disk is filling (gap G9).
SELECT slot_name, active, wal_status,
  pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal,
  pg_size_pretty(safe_wal_size) AS safe_wal_left
FROM pg_replication_slots WHERE NOT pg_is_in_recovery();

-- (i) Replica lag (node B): received but not yet replayed.
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())) AS replay_lag
WHERE pg_is_in_recovery();

-- (j) Are the prune tasks there and running? (import_job_rows_prune is expected MISSING)
SELECT key, enabled, interval_value, interval_unit, last_run_at, last_status
FROM public.scheduled_tasks
WHERE key IN ('api_call_log_prune','import_job_rows_prune','embedding_queue_prune','user_downloads_purge');
SQL
```

Crew needs back: (b) (c) (d) (f) (g) (h) (j) from A; (a) (b) (c) from B; `df -h` and `docker system df`
from both.

## 6. Prod disk-space alert

- `infra/scripts/ha-checks.sh` alerts at 80% (`:19`, check `:61`) through Healthchecks.io and
  prunes old pre-migrate dumps at 85% (`:20`, `:54-57`).
- Installing it on prod is a runbook step marked "THIS CHANGES PROD"
  (`documentation/runbooks/ha-failover.md:123-126`); nothing in the repo shows it was done.
  5.1's `crontab` line answers it.
- Uptime Kuma checks reachability only (`documentation/runbooks/monitoring.md:10`).
- No 70% or 90% tier, no node_exporter or Prometheus rules (none found).

## 7. R2 WAL / backup archive (HA plan D4)

D4 = "Cloudflare LB + R2" (`documentation/plans/infra/PLAN-n8n-decom-ha-01nov.md:176`).
WAL-G to R2 is templated (`infra/templates/compose.ha.yml:52-56`, `infra/templates/postgres/Dockerfile`,
`infra/templates/walg.env.example`) but **not live on prod**: `archive_mode=off` on 7 Nov, nothing
ever archived (`PLAN-ha-b-replica-sync-07nov.md:313`, `:319`). Turning it on is owner phase F5
(`documentation/plans/infra/PLAN-ha-cf-failover-04nov.md:197`) and needs a Postgres restart.

## 8. Options, cheapest first

### 8.1 Ranked

| # | option | effort | saves now | stops growth of | notes |
|---|---|---|---|---|---|
| 1 | plan_exception: keep the newest batch per run, prune the rest daily | S (one prune task; same shape as `prune_import_job_rows`, `app/services/import_outcome.py:443`) | about 13 GB (8,397,200 of 8,410,784 rows go) | about 5.5 GB/month | 0 rows have a decision today (`decided_at` all null), so nothing reviewed is lost. Disk only comes back after a repack (#7) |
| 2 | Seed the missing `import_job_rows_prune` scheduled task (code + 90-day setting already exist) | XS (one seed row) | about 0.3 GB | caps the table at about 90 days | 928,382 rows already past 90 days |
| 3 | `max_slot_wal_keep_size=20GB` on node A | XS (reload, gap G9) | 0 | stops a dead replica filling A | safety, not space |
| 4 | Docker log cap (`max-size`/`max-file` in `/etc/docker/daemon.json` or the prod compose) | XS | unknown until 5.1 | container logs | prod compose is not in git |
| 5 | integration_log: blank payloads after N days, delete rows after M (copy api_call_log's two-stage rule) | S | inferred 2-3 GB | about 1.4 GB/month | owner Q2. Check the replay tool's needs first (`scripts/inbox_queue_replay.py:588`) |
| 6 | One "working data" age for chat traces, scheduler history, old reorder runs, superseded embeddings | S each | inferred 2-3 GB together | about 1 GB/month | owner Q3. Superseded embeddings can use the existing `--delete-superseded` script logic |
| 7 | `pg_repack` (online) or `VACUUM FULL` (locks the table) on the pruned tables, then on any table where prod is far above dev | M (ops window; pg_repack is not in the pgvector image, inferred) | the space #1/#2/#5/#6 freed, plus inferred up to about 20 GB of bloat | - | needs free space about the size of the table being rewritten; the WAL it writes also goes to node B |
| 8 | Hostinger: node A KVM 4 (200 GB) to KVM 8 (400 GB) | XS-S (in-place plan upgrade, then grow the partition) | +200 GB | - | Hostinger does not sell disk alone; a whole plan upgrade is the only route ([upgrade article](https://www.hostinger.com/support/1583229-how-to-upgrade-a-vps-server/)). Plans: KVM 1 50 GB, KVM 2 100 GB, KVM 4 200 GB, KVM 8 400 GB NVMe ([hostinger.com/vps-hosting](https://www.hostinger.com/vps-hosting)). Node B is already a KVM 8 (387G, 30% used on 7 Nov) |
| 9 | Provider with attachable block storage (e.g. [Hetzner Cloud volumes](https://docs.hetzner.com/cloud/volumes/overview), 10 GB to 10 TB, attach to one server) | L (move both nodes, re-seed, DNS/LB) | any size | - | conflicts with "all in Malaysia for now" (D2, `PLAN-n8n-decom-ha-01nov.md:175`). Last resort |
| - | Move files to R2 | - | about 0 | - | already done (section 3) |

inferred, worth one check by the AI lane: 248,128 of 373,647 current embedding chunks are
`spo_allocation`, `order` and `order_line` records, plus 54,191 superseded `order` chunks. CLAUDE.md
says stock and order numerics are intentionally not embedded. If those chunks are not used by any
search, they are most of the 7.1 GB embedding table.

### 8.2 When does node A fill? (inferred, needs owner numbers)

From the last prod facts in the repo, not today's: node A disk 58% of 193G on 7 Nov
(`PLAN-ha-b-replica-sync-07nov.md:315`), database about 54 GB on 1 Nov (`PLAN-n8n-decom-ha-01nov.md:183`).
At 7-11 GB a month:
- 80% alert line: about 40 GB of headroom left on 12 Nov, so roughly Mar-May 2027.
- Disk full: about 81 GB free, so roughly Jun-Oct 2027.
- Earlier cliff, only if HA re-seeds node A: two copies of the DB must fit (section 4). With about
  58 GB of non-database use, that stops fitting once the DB passes about 67 GB: roughly Dec 2026-Jan 2027.

Option 1 + a repack (#7) moves all three dates out by many months. A firm date needs 5.1 and 5.2.

## 9. Owner questions (retention is a product decision)

1. **Planning exceptions history** (13 GB): keep (a) only the newest batch per planning run,
   (b) newest batch plus 30 days of older batches, (c) everything. Recommend (a): the screen reads
   only the newest batch and no row has a decision; (b) keeps about 4-5 GB a month for no screen.
2. **Respond.io / integration message log payloads** (3.9 GB, about 1.4 GB a month): (a) blank
   payloads after 30 days and delete rows after 180 (the rule api_call_log already uses),
   (b) delete whole rows after 90 days, (c) keep forever. Recommend (a): one rule for both logs, and
   the row (who, when, status) stays for six months.
3. **Working data age** for chat turn traces, scheduler run history, superseded reorder runs and
   superseded AI search chunks: (a) 90 days, (b) 180 days, (c) keep. Recommend (a): import rows
   already use 90 (`app/models/user.py:526`) and the chatbot plan promised 90.
4. **Audit log** (0.9 GB, about 0.4 GB a month): (a) keep all in the database for now,
   (b) move rows older than 12 months to an R2 archive (planned, `PLAN-audit-standard-26sep.md` 7.3),
   (c) 24 months. Recommend (a): it is small; revisit at 5 GB.
5. **Disk**: (a) do 1-4 first, upgrade node A only if growth still reaches 70% within 6 months
   after the repack, (b) upgrade node A to KVM 8 now as well, (c) move provider. Recommend (a),
   plus options 3 and 4 (WAL cap, log cap) and installing the 80% alert now, because they cost
   minutes and close the "fills overnight" risks.

## Appendix: dev queries used

Top 25 (section 1), same as 5.2 (f) plus `pg_stat_user_tables.n_live_tup/n_dead_tup`. Growth per
month: `SELECT to_char(date_trunc('month', <ts>), 'YYYY-MM'), count(*), sum(pg_column_size(x.*))
FROM <table> x GROUP BY 1`. plan_exception keep-set: rows whose batch is the newest
`plan_exception_batch` per `run_id` (19,783 batches, 135 runs, 13,584 rows).
