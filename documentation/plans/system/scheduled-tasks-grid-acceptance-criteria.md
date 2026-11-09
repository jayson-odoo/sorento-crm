# UAC: SCHEDULED-TASKS-GRID

Plan: `PLAN-scheduled-tasks-grid-09nov.md`.

## Town job on the registry

- AC-1 System Management > Scheduled Tasks lists "Sorento town snapshot" (key `town_snapshot`,
  every 3 minutes, enabled) after `alembic upgrade head`; the seed is idempotent.
- AC-2 The job runs through the scheduled-tasks heartbeat only; no bare APScheduler job
  `town_snapshot` remains (so it never runs twice per tick).
- AC-3 A tick inside 07:00-22:05 MYT that builds every company records status Success with
  summary `{companies, built, failed: 0}`; outside the window, Success with
  `{"skipped": "outside 07:00-22:05 Malaysia time"}`; while another run holds the lock,
  Success with `{"skipped": "an earlier town run is still going"}`.
- AC-4 A company whose build fails does not stop the others; the run then records status
  Failed and the task's Last error reads `Town snapshot failed for N of M companies: <company
  name>: <error>` (company NAME, never its id).
- AC-5 Run now and the Enabled switch on the task's detail page work for Town as for every
  other task (same endpoints, no special case).

## Grid

- AC-6 The grid is the standard `DataGrid` + `DataGridListToolbar` + `buildSelectColumn`
  stack, query built by `buildDataGridParams`; tick-box selection like every list.
- AC-7 Columns: Name, Key (hidden by default, column chooser), Frequency, Enabled, Last
  status, Last run, Next run, Last error. Every column sorts server-side (`sort`/`dir`);
  Frequency sorts by real interval length; empty values sort last.
- AC-8 Filters Enabled, Last status (incl. "Never run") and Frequency are multi-select and
  applied server-side; search matches name, key, description and last error.
- AC-9 One line per row: no cell stacks a second line; long text truncates with the full
  value in its hover title. The description shows on the detail page only.
- AC-10 Dates read dd/mm/yyyy, h:mm am/pm, Malaysia time.
- AC-11 Clicking a row opens `/system-management/scheduled-tasks/{id}`.
