# PLAN: Scheduled Tasks grid + Town job on the registry (SCHEDULED-TASKS-GRID)

Status: Build (full track: seed-only migration town_0002_scheduled_task). Owner answered the behaviour card 9 Nov ~16:45.

## Journey

Owner opens System Management > Scheduled Tasks and expects every cron job, including
"Sorento town snapshot", with name, schedule, last run, last result/error, next run, the
enabled toggle and Run now. Each grid row sits on ONE line.

## Findings (measured)

- The page lists DB rows of `scheduled_tasks`
  (`sorento_crm_backend/app/api/v1/system/scheduled_tasks.py:78` -> `list_tasks`,
  `app/services/scheduled_task_service.py:287`). Rows run through the 10s heartbeat
  (`app/scheduler/task_scheduler.py` `_scheduled_tasks_heartbeat` -> `run_due_tasks`,
  `scheduled_task_service.py:586`) by key via `TASK_HANDLERS`.
- The Town job is a raw APScheduler job (`task_scheduler.py:936-942`, `_town_snapshot_tick`
  at :648), so it has no row and never shows. A failed company build is only
  `logger.error` (`app/services/town/snapshot.py:502-503`).
- The grid (`sorento_crm_frontend/app/(protected)/system-management/scheduled-tasks/components/ScheduledTasksList.tsx`)
  already uses `DataGrid`, but sorts/paginates client-side and renders Name + description
  as two lines.

## Design

1. Town moves onto the registry, same mechanism as every other task: a seed row
   `town_snapshot` (every 3 minutes) in an idempotent migration, `register_handler("town_snapshot", ...)`,
   and the APScheduler `add_job` is removed. `run_town_snapshot_tick` returns a summary
   (companies built / failed / outside hours) and raises after the loop when any company
   failed, so the heartbeat writes `last_status=failed` and `last_error` naming the company.
2. Grid: server-side sort + filter on `GET /system/scheduled-tasks` (`page/limit/sort/dir/query`
   + multi-select filters), one line per row (truncate + title), dates dd/mm/yyyy.

## Owner rulings (9 Nov ~16:45, "okay with recommendation")

- Q1 (a) Columns: Name | Frequency | Enabled | Last status | Last run | Next run | Last error. Description
  only on the detail page; Key hidden by default, shown through the column chooser.
- Q2 (a) Row click opens the existing detail page (Enabled switch, Run now, run log live there).
- Q3 (b) Town keeps its 3-minute schedule, but ticks outside 07:00-22:05 MYT write no run row and leave
  Last run alone. Built as generic task data, not a Town special case: `metadata.active_window`
  (`scheduled_task_service._active_window`); outside it the task is not due, its due time and next run move
  to the window's next opening, so the overdue watchdog does not flag it overnight.
- Q4 (c) (crew, on prod evidence: first tick of the day carries a 1.3-2.2s ranking statement, 30s cap):
  Town runs OFF the heartbeat thread. Registered `background=True`; the heartbeat claims the tick
  (last_run_at, status started) and dispatches on Run now's existing thread path
  (`_dispatch_run_in_thread`, extracted from `run_task_now`), which writes the run row, duration_ms and the
  task's last status/error. Run now takes the same path.

## UAC

See `scheduled-tasks-grid-acceptance-criteria.md` (written after the behaviour card).
