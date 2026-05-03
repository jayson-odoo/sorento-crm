-- pg_stat_statements snapshot for stress-test analysis.
--
-- Pre-stress (in psql, once):
--   CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
--   -- restart postgres after adding 'pg_stat_statements' to shared_preload_libraries
--   SELECT pg_stat_statements_reset();   -- run RIGHT BEFORE the stress run
--
-- Post-stress: run this script. Top-20 worst by total time, then by mean time.
--
-- Usage:
--   docker exec -i sorento_crm_db psql -U postgres -d sorento_crm < ci/pg-slow-queries.sql

\echo === Top 20 by TOTAL time (cumulative pain) ===
SELECT
  round(total_exec_time::numeric, 0)            AS total_ms,
  calls,
  round(mean_exec_time::numeric, 1)             AS mean_ms,
  round(stddev_exec_time::numeric, 1)           AS stddev_ms,
  round((100 * total_exec_time / SUM(total_exec_time) OVER ())::numeric, 2) AS pct,
  rows,
  substring(query, 1, 160)                      AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

\echo === Top 20 by MEAN time (single-call slowness) ===
SELECT
  round(mean_exec_time::numeric, 1)             AS mean_ms,
  calls,
  round(total_exec_time::numeric, 0)            AS total_ms,
  rows,
  substring(query, 1, 160)                      AS query
FROM pg_stat_statements
WHERE calls > 5
ORDER BY mean_exec_time DESC
LIMIT 20;

\echo === Active queries right now (catch in flight) ===
SELECT
  pid,
  now() - query_start                           AS duration,
  state,
  wait_event_type,
  wait_event,
  substring(query, 1, 200)                      AS query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start
LIMIT 50;

\echo === Connection pool occupancy ===
SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY 2 DESC;
