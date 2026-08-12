-- =====================================================================
-- EPISODE-BASED TIMING — the ONLY defensible way to time response/resolution
-- given overwrite-in-place (initiated_at is reset on re-open) + Respond.io
-- open/close churn (one row had 68 resolution events).
--
-- KEY IDEA: never subtract against the tracking row. Measure gaps BETWEEN
-- consecutive events in conversation_sla_event_log, keyed on event_at.
--   response  = escalation event -> next HUMAN event
--   resolution= escalation event -> next resolution event
-- Filter to sane windows (>0, < 7 days) to drop churn/negative artifacts.
--
-- CAVEAT for the slide: this is a reconstruction, not a stamped SLA metric.
-- Present as "estimated, from event reconstruction" — and flag that the SLA
-- timing instrumentation needs a fix (per-episode stamping) as an action item.
-- =====================================================================

WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger,
         coalesce(e.triggered_by_id, e.assigned_to_id) AS actor
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id = e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (   -- every escalation moment
  SELECT sla_tracking_id, event_at AS esc_at
  FROM ev WHERE event_type IN ('escalation','escalate')
),
paired AS (
  SELECT e.sla_tracking_id, e.esc_at,
    (SELECT min(h.event_at) FROM ev h
       WHERE h.sla_tracking_id = e.sla_tracking_id AND h.event_at > e.esc_at
         AND (h.event_type IN ('response','handling_claimed','handling_taken_over')
              OR h.trigger='manual'))                         AS human_at,
    (SELECT min(r.event_at) FROM ev r
       WHERE r.sla_tracking_id = e.sla_tracking_id AND r.event_at > e.esc_at
         AND r.event_type='resolution')                       AS resolved_at
  FROM esc e
)

-- E1. RESPONSE TIME (escalation -> first human event), sane window
SELECT 'response_time' metric,
       count(*)                                              escalation_events,
       count(human_at) FILTER (WHERE human_at > esc_at AND human_at < esc_at + interval '7 days') n,
       round((avg(EXTRACT(epoch FROM human_at-esc_at)) FILTER (WHERE human_at>esc_at AND human_at<esc_at+interval '7 days')/60.0)::numeric,1) avg_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM human_at-esc_at))
              FILTER (WHERE human_at>esc_at AND human_at<esc_at+interval '7 days')/60.0)::numeric,1) p50_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM human_at-esc_at))
              FILTER (WHERE human_at>esc_at AND human_at<esc_at+interval '7 days')/60.0)::numeric,1) p90_min
FROM paired;

-- E2. RESOLUTION TIME (escalation -> next resolution), sane window
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
p AS (
  SELECT e.sla_tracking_id, e.esc_at,
    (SELECT min(r.event_at) FROM ev r WHERE r.sla_tracking_id=e.sla_tracking_id
       AND r.event_at>e.esc_at AND r.event_type='resolution') resolved_at
  FROM esc e
)
SELECT 'resolution_time' metric,
       count(*) escalation_events,
       count(resolved_at) FILTER (WHERE resolved_at>esc_at AND resolved_at<esc_at+interval '7 days') n,
       round((avg(EXTRACT(epoch FROM resolved_at-esc_at)) FILTER (WHERE resolved_at>esc_at AND resolved_at<esc_at+interval '7 days')/60.0)::numeric,1) avg_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM resolved_at-esc_at))
              FILTER (WHERE resolved_at>esc_at AND resolved_at<esc_at+interval '7 days')/60.0)::numeric,1) p50_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM resolved_at-esc_at))
              FILTER (WHERE resolved_at>esc_at AND resolved_at<esc_at+interval '7 days')/60.0)::numeric,1) p90_min
FROM p;

-- E3. DISTRIBUTION SANITY — bucket the response gaps so you SEE the shape
--     (how many < 5 min, < 1 h, < 1 day, > 1 day). Trust E1 only if buckets look sane.
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
g AS (
  SELECT EXTRACT(epoch FROM (
    (SELECT min(h.event_at) FROM ev h WHERE h.sla_tracking_id=e.sla_tracking_id
       AND h.event_at>e.esc_at
       AND (h.event_type IN ('response','handling_claimed','handling_taken_over') OR h.trigger='manual'))
    - e.esc_at))/60.0 AS gap_min
  FROM esc e
)
SELECT count(*) FILTER (WHERE gap_min IS NULL)            no_human,
       count(*) FILTER (WHERE gap_min <= 0)              negative_or_zero,
       count(*) FILTER (WHERE gap_min > 0   AND gap_min <= 5)     within_5min,
       count(*) FILTER (WHERE gap_min > 5   AND gap_min <= 60)    within_1h,
       count(*) FILTER (WHERE gap_min > 60  AND gap_min <= 1440)  within_1day,
       count(*) FILTER (WHERE gap_min > 1440)            over_1day
FROM g;
