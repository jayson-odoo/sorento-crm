# PLAN: integration_log indexes + upload bell polling cap (INTEGRATION-LOG-INDEXES)

Status: in progress (small fix track: one additive index-only migration, no auth/RBAC change, no UI change)

## Problem (measured by crew, 2 Nov 2026, read-only on a 20 Oct prod copy)

- `integration_log` (~1.6 GB, ~1.2M rows) has only its PK and `uq_integration_log_ideation_status_event`.
  The five indexes `app/models/integration.py` declares were never created by any migration
  (`git grep ix_integration_log -- sorento_crm_backend/alembic` finds nothing); `create_all` skips
  existing tables, so no install that predates the model change has them.
- The header upload-activity bell (`components/upload-activity/useUploadActivity.ts`, mounted from
  `header.tsx` on every protected page) calls `GET /api/v1/resources/upload-activity`, whose
  latest-log query (`app/api/v1/resources/upload_activity.py`,
  `WHERE business_table='attachments' AND business_id IN (...) ORDER BY business_id, created_at DESC`)
  seq-scans the whole table: 5-82 s per call, evicting shared buffers and slowing every other page.
- The bell polls every 5 s while any session reads `processing`. An attachment whose last log row
  is stuck `sent`/`pending` reads `processing` forever, so polling never stops.

## Fix

1. Migration `il_0001_integration_log_indexes`: CREATE INDEX CONCURRENTLY IF NOT EXISTS in an
   autocommit block, bounded `lock_timeout` with retry (aud_0001 hot-table pattern), INVALID
   leftover dropped and rebuilt:
   - `ix_integration_log_business_table_business_id (business_table, business_id, created_at DESC)`
     (same name and shape crew already created on the dev DB, so it is a no-op there)
   - `ix_integration_log_status (status)`, `ix_integration_log_integration_channel (integration_channel)`,
     `ix_integration_log_created_at (created_at)`, `ix_integration_log_next_retry_at (next_retry_at)`.
   The model's composite index gains `created_at DESC` so model and DB agree.
2. Bell polling cap, frontend only, N = 30 minutes: a backend session counts as in flight for
   POLLING only when its `started_at` is within the last 30 minutes. Optimistic (still uploading in
   this tab) sessions always poll. Display status is unchanged (no UI change); opening the drawer
   still refetches. 30 min: n8n intake replies in seconds to a few minutes; anything older is stuck,
   and the drawer-open refetch still shows a late reply.

## UAC

See `integration-log-indexes-acceptance-criteria.md`.
