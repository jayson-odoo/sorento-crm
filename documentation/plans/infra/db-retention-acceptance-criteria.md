# UAC: DB retention jobs (lane DB-RETENTION)

Plan: `PLAN-db-retention-12nov.md`. "Old" = past the rule's setting; every rule is a scheduled task.

1. Scheduled Tasks lists `plan_exception_prune`, `integration_log_prune`, `chatbot_turn_trace_prune`,
   `scheduled_task_runs_prune`, `reorder_run_prune`, `embedding_superseded_prune`,
   `import_job_rows_prune` (and the existing `api_call_log_prune`), each daily, each with Run now.
2. With dry-run ON, a run's summary shows how many rows it would delete/blank and nothing changes.
3. With dry-run OFF, the same counts are deleted/blanked, in batches of the batch-size setting, and
   the summary shows the counts, `dry_run: false`, `finished: true`.
4. A run that hits the time budget stops between batches with `finished: false`; the next run
   carries on and nothing is lost or half-done.
5. Plan exceptions: for each planning run (and for batches with no run, as one group) the newest
   batch keeps every row; older batches lose their undecided rows; an older batch with no rows left
   is removed. A row with a decision (status other than open, or a decision time) is NEVER deleted,
   and its batch stays.
6. Integration log: payloads and headers blank after 30 days, rows gone after 180; a pending or
   processing row is never touched. API call log keeps its 30/180 behaviour.
7. Chat turns older than 90 days lose their trace; the turn itself stays.
8. Scheduler run history older than 90 days is deleted, except the newest run of each task.
9. A superseded planning run older than 90 days is deleted with its recommendations, unless a person
   overrode or decided anything on it. The current run is never deleted.
10. AI search chunks superseded more than 90 days ago are deleted; current chunks never.
11. Import row detail older than 90 days is deleted (existing code, now actually scheduled).
12. Audit logs: untouched.
13. Every retention day count, batch size, sleep, time budget and dry-run is a system setting.
