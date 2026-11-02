# UAC: integration_log indexes + bell polling cap

- AC-1 After `alembic upgrade head`, `integration_log` has valid indexes
  `ix_integration_log_business_table_business_id` (business_table, business_id, created_at DESC),
  `ix_integration_log_status`, `ix_integration_log_integration_channel`,
  `ix_integration_log_created_at`, `ix_integration_log_next_retry_at`.
- AC-2 The upgrade is rerun-safe: running it on a DB that already has any of them (e.g. the dev DB
  where crew built the composite by hand) succeeds and changes nothing; an INVALID leftover is rebuilt.
- AC-3 The upload-activity latest-log query uses the composite index (no Seq Scan on integration_log).
- AC-4 Downgrade drops the five indexes (CONCURRENTLY) and leaves the unique partial index alone.
- AC-5 The bell stops polling when the only `processing` sessions started more than 30 minutes ago;
  it still polls for a `processing` session younger than 30 minutes and for any optimistic upload.
- AC-6 No visible UI change: statuses and badge count are computed as before.
