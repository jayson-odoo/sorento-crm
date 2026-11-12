# PLAN: DB retention jobs (lane DB-RETENTION)

Status: Build, track L (migration + prod data). Behaviour card answered by crew 12 Nov: Q1 (a), Q2 (a), Q3 (b) ship live.

Source: owner rulings 12 Nov 2026 on `documentation/plans/infra/db-growth-12nov.md` section 9
(PR #2373, branch `crew/db-growth-scout`): Q1-Q5 all option (a). UAC:
`documentation/plans/infra/db-retention-acceptance-criteria.md`.

Paths below are relative to `sorento_crm_backend/` unless they start with a top-level folder.

## 1. What exists (reuse first)

| piece | where | decision |
|---|---|---|
| keyset-batched delete by age | `prune_import_job_rows` `app/services/import_outcome.py:443` | **turn into one shared function** `batched_delete` in a new `app/services/data_retention_service.py`; `prune_import_job_rows` calls it |
| two-stage blank-then-delete | `prune_api_call_log` `app/services/api_call_log_service.py:214` (one unbounded UPDATE + DELETE) | **turn into one shared function** `two_stage_prune`; api_call_log AND integration_log call it (api_call_log also gains batching) |
| daily task + settings lookup | `_handler_api_call_log_prune` / `_handler_import_job_rows_prune` `app/scheduler/task_scheduler.py:380`, `:406`; registration `:885-886` | reuse pattern; new handlers registered with `background=True` (`app/services/scheduled_task_service.py:89`) so a long prune never blocks the 10 s heartbeat |
| retention settings | `system_settings` columns `app/models/user.py:519-526`; API `app/api/v1/user_management/settings.py:57`, `:446` | add columns next to them (one column per value; no new table) |
| task seed | `alembic/versions/293_api_call_log.py:80-95` (`INSERT ... ON CONFLICT (key) DO NOTHING`) | same shape in one new migration |
| superseded embedding chunk delete | `app/scripts/dedupe_embedding_chunks_current.py:182-187` (`is_current=false` delete, manual) | rule uses the same predicate plus an age on `superseded_at`; script left as is |
| newest batch the screen reads | `latest_batch` `app/services/scm/plan_exception_service.py:468-472` (per `run_id`, or newest overall when no run) | the keep-set is defined by the same ordering (`generated_at desc`) |
| run log + counts | `scheduled_task_runs.summary` (`app/models/scheduled_task.py:47`) shown on Scheduled Tasks | every handler returns its counts dict; that IS the log; plus one `logger.info` line per rule |

## 2. Rules

All rules: keyset batches of `data_retention_batch_size` rows (default 5000), one commit per
batch, `data_retention_batch_sleep_ms` (default 200) between batches, stop after
`data_retention_max_run_minutes` (default 30) and report `finished: false` (the next run
continues). `data_retention_dry_run` (default false: the owner approved the deletions; crew ruling) makes every rule count only. The CLI is dry-run unless `--apply`.

| # | rule | task key | selects | does |
|---|---|---|---|---|
| R1 | plan exceptions (Q1) | `plan_exception_prune` | `scm.plan_exception` rows whose batch is NOT the newest batch of its `run_id` (NULL run = one group), batch older than `plan_exception_superseded_grace_days` (default 1), and row `status = 'open' AND decided_at IS NULL` | delete rows; then delete batch rows left with zero exceptions. A decided row and its batch stay forever |
| R2 | integration log (Q2) | `integration_log_prune` | `created_at` past 30 d (payload) / 180 d (row); never `status IN ('pending','processing')` | blank `request_payload`, `response_payload`, `request_headers`, `response_headers`; delete rows past 180 d |
| R2b | api call log (existing) | `api_call_log_prune` | unchanged windows | same shared two-stage function, now batched |
| R3a | chat turn traces (Q3) | `chatbot_turn_trace_prune` | `chatbot.turns.created_at` past 90 d, `trace IS NOT NULL` | blank `trace`, keep the row (crew ruling) |
| R3b | scheduler run history (Q3) | `scheduled_task_runs_prune` | `started_at` past 90 d, not the newest run of its task | delete |
| R3c | superseded reorder runs (Q3) | `reorder_run_prune` | `scm.reorder_run.superseded_by_run_id IS NOT NULL`, created past 90 d, no `recommendation_override` / `plan_row_decision` on it (crew ruling: keep any run someone decided on) | no long transaction: delete the run's children (recommendations and their children, order summary rows) in keyset batches, one commit per batch, then the run row; same sleep and time budget |
| R3d | superseded AI search chunks (Q3) | `embedding_superseded_prune` | `embedding_chunks.is_current = false AND superseded_at` past 90 d | delete |
| R3e | import rows (Q3, existing code) | `import_job_rows_prune` | unchanged (90 d) | **seed the missing `scheduled_tasks` row** so it runs |
| Q4 | audit_logs | - | - | no change |

Retention days are `system_settings` columns: `integration_log_payload_retention_days` 30,
`integration_log_row_retention_days` 180, `chatbot_turn_trace_retention_days` 90,
`scheduled_task_run_retention_days` 90, `reorder_run_retention_days` 90,
`embedding_superseded_retention_days` 90, `plan_exception_superseded_grace_days` 1, plus the
three shared knobs above. Exposed through the existing settings API (`settings.py`) like
`import_job_rows_retention_days`; no new screen.

Schedule: every task `days/1`, `start_at` 02:00 MYT, all `background=True`. All 8 tasks show on
Scheduled Tasks with last run, last error and Run now (standing rule).

Ops entry point for timing: `python -m app.scripts.run_data_retention --rule <key> [--apply]`
(dry-run unless `--apply`) calls the same service functions, prints counts and seconds.

## 3. First prod run and space

- R1 removes about 8,397,200 rows (13 GB). At 5000 rows a batch that is about 1,680 batches;
  real seconds per batch come from the dev-copy timing (crew-ask with exact commands, section 6).
  With the 30-minute budget the first run continues across nights until done; Run now speeds it.
- Deleting does not shrink the file: autovacuum marks the space reusable inside the table, so new
  batches stop growing it, but the disk only gets the 13 GB back after a rewrite. With 13.6k live
  rows left, `VACUUM (FULL, ANALYZE) scm.plan_exception` rewrites only those rows but holds an
  exclusive lock while it reads the 13 GB file (minutes; timed on the dev copy). **Owner runs it in
  a quiet window; crew never runs VACUUM FULL on prod.** Runbook:
  `documentation/runbooks/db-retention-and-disk.md`.
- WAL: the deletes write WAL (full-page images on first touch after a checkpoint, up to roughly the
  table size over the whole drain), streamed to node B. Batches + sleep spread it; the WAL slot cap
  (Q5) goes in first so a down replica cannot pile it up on node A.

## 4. Q5 server config (owner applies; crew never SSHes prod)

- `max_slot_wal_keep_size=20GB`: already in `infra/templates/compose.ha.yml:44`; runbook gives the
  `ALTER SYSTEM` + `pg_reload_conf()` lines (reload, no restart).
- Docker log cap: new `infra/templates/host/docker-daemon.json` (`max-size` 50m, `max-file` 5) and
  `logging:` defaults in `sorento_crm/docker-compose.yml`.
- 80% disk alert: `infra/scripts/ha-checks.sh` (`:19`, `:61`) already does it; runbook gives the
  cron install line.

## 5. Tests (tester writes red first)

`tests/test_data_retention.py` on Postgres (`tests/_pg_fixture.py`), seeding its own chain:
per rule: old rows go, new rows stay, dry-run counts equal the live counts and change nothing,
batch size smaller than the set still finishes, time budget stops early with `finished: false`.
R1: newest batch per run kept, NULL-run group kept, a decided row (status not open, or
`decided_at` set) in an old batch is never deleted and keeps its batch. R2: pending/processing
rows untouched. R3b: newest run per task kept. R3c: run with an override or plan row decision
kept. Migration: 8 task keys present; settings defaults. Global guards
`tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.

## 6. Standing rules that apply

"Every background or scheduled job is listed on Scheduled Tasks with last run, last error and Run
now"; "Reuse functions" (section 1); "Plain business words" for task names/descriptions;
"One bad line never fails a whole batch" (a rule's failure is logged and the next rule still
runs: each rule is its own task). The rest are UI/chat rules with no surface here.

## 7. Contract (tester and coder both build against this)

New module `app/services/data_retention_service.py`. Every rule function takes the session plus
keyword knobs `dry_run: bool = False, batch_size: int = 5000, sleep_ms: int = 0,
max_seconds: float | None = None` and returns a dict that always holds `dry_run` (bool) and
`finished` (bool: false only when the time budget stopped it with work left), plus its counts. In
dry-run the count keys hold what a live run would do and nothing is written. `max_seconds` is
checked between batches, so a run always completes at least one batch.

| function | extra kwargs | count keys |
|---|---|---|
| `prune_plan_exceptions(db, *, grace_days=1, ...)` | | `rows_deleted`, `batches_deleted` |
| `prune_integration_log(db, *, payload_retention_days, row_retention_days, ...)` | | `payloads_cleared`, `rows_deleted` |
| `prune_chatbot_turn_traces(db, *, retention_days, ...)` | | `traces_cleared` |
| `prune_scheduled_task_runs(db, *, retention_days, ...)` | | `rows_deleted` |
| `prune_reorder_runs(db, *, retention_days, ...)` | | `runs_deleted` |
| `prune_superseded_embeddings(db, *, retention_days, ...)` | | `rows_deleted` |
| existing `prune_api_call_log` (`api_call_log_service.py`) | same knobs added, old kwargs kept | `payloads_cleared`, `rows_deleted` |
| existing `prune_import_job_rows` (`import_outcome.py`) | same knobs added, old kwargs kept | `rows_deleted`, `retention_days` |

Scheduler handlers `_handler_<task key>` in `app/scheduler/task_scheduler.py` read the
`system_settings` row (section 2 names and defaults; `data_retention_dry_run` bool default false,
`data_retention_batch_size` 5000, `data_retention_batch_sleep_ms` 200,
`data_retention_max_run_minutes` 30) and return the rule's dict. New task keys are registered with
`background=True`. One migration adds the columns and seeds the 7 task rows (`ON CONFLICT (key)
DO NOTHING`). CLI: `python -m app.scripts.run_data_retention --rule <task key> [--apply]
[--batch-size N] [--sleep-ms N]` prints the dict and elapsed seconds; dry-run unless `--apply`.

No VACUUM FULL anywhere in code or jobs (crew ruling); the runbook leaves it to the owner.
