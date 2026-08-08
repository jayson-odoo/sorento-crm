-- =====================================================================
-- DIAGNOSTIC — why "response" events are few but "resolution" events many.
-- Resolves the two-denominator confusion (tracking row vs event history).
-- Run each; paste results.
-- =====================================================================

-- D1. Event-type histogram over CONVERSATION-scope rows, July.
--     Also: how many DISTINCT tracking rows each event type touches.
--     If distinct_rows << events, conversations are re-resolving (overwrite model).
--     If distinct_rows is huge (~hundreds), the scope filter is leaking form rows.
SELECT e.event_type,
       count(*)                         AS events,
       count(DISTINCT e.sla_tracking_id) AS distinct_rows
FROM conversation_sla_event_log e
JOIN conversation_sla_tracking t ON t.id = e.sla_tracking_id
WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
  AND t.initiated_at >= '2026-07-01'
GROUP BY e.event_type
ORDER BY events DESC;

-- D2. Events per tracking row — is it really ~5 events/row (re-open churn)?
WITH per AS (
  SELECT e.sla_tracking_id, count(*) ev,
         count(*) FILTER (WHERE e.event_type='resolution') resols,
         count(*) FILTER (WHERE e.event_type='response')   resps
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
  GROUP BY e.sla_tracking_id
)
SELECT count(*) rows, sum(ev) total_events,
       round(avg(ev)::numeric,1) avg_events_per_row,
       max(resols) max_resolutions_one_row,
       sum(resols) total_resolutions, sum(resps) total_responses
FROM per;

-- D3. THE HONEST RESPONSE METRIC — don't rely on 'response' event alone.
--     "Human first touch" per row = earliest of ANY human-attributable event
--     (response OR resolution OR handling_claimed/taken_over OR manual trigger).
--     Time from row initiation to that = real response time.
WITH conv AS (
  SELECT id, initiated_at FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
touch AS (
  SELECT sla_tracking_id, min(event_at) first_touch
  FROM conversation_sla_event_log
  WHERE event_type IN ('response','resolution','handling_claimed','handling_taken_over')
     OR trigger='manual'
  GROUP BY sla_tracking_id
)
SELECT count(*) escalations,
       count(tc.first_touch) got_human_touch,
       count(*)-count(tc.first_touch) never_touched,
       round((avg(EXTRACT(epoch FROM tc.first_touch - c.initiated_at))/60.0)::numeric,1) avg_first_touch_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM tc.first_touch-c.initiated_at))/60.0)::numeric,1) p50_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM tc.first_touch-c.initiated_at))/60.0)::numeric,1) p90_min
FROM conv c LEFT JOIN touch tc ON tc.sla_tracking_id=c.id;

-- D4. Current resolved state of the 31 rows (row-level truth, not event history)
SELECT count(*) tracking_rows,
       count(*) FILTER (WHERE is_resolved)     currently_resolved,
       count(*) FILTER (WHERE NOT is_resolved) currently_open,
       count(resolution_duration)              have_resolution_duration,
       round((avg(resolution_duration)/60.0)::numeric,1)  avg_resolution_min_rowlevel
FROM conversation_sla_tracking
WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
  AND initiated_at >= '2026-07-01';

-- D5. HANDLER leaderboard, corrected — credit first-human-touch per row to a
--     person (dedup the re-open churn: one credit per row, not per event).
WITH conv AS (
  SELECT id, initiated_at FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
ranked AS (
  SELECT e.sla_tracking_id,
         coalesce(e.triggered_by_id, e.assigned_to_id) actor_id,
         row_number() OVER (PARTITION BY e.sla_tracking_id ORDER BY e.event_at) rn
  FROM conversation_sla_event_log e
  JOIN conv c ON c.id=e.sla_tracking_id
  WHERE e.event_type IN ('response','resolution','handling_claimed','handling_taken_over')
     OR e.trigger='manual'
)
SELECT coalesce(u.name,u.email,r.actor_id,'(unknown)') handler,
       count(*) conversations_first_handled
FROM ranked r LEFT JOIN users u ON u.id=r.actor_id
WHERE r.rn=1
GROUP BY 1 ORDER BY 2 DESC;
