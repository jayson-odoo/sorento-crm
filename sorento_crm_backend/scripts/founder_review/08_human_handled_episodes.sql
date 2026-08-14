-- =====================================================================
-- HUMAN-HANDLED ESCALATIONS — chart-ready extract.
-- Scope: escalation events that DID get a human touch (within 7 days).
-- Mirrors the chat-histories phase: when it happened -> response time ->
-- resolution time -> handler. Plus pre-bucketed distributions + timeline.
--
-- Timing = event-log episode reconstruction (NOT the tracking row — that
-- clock is corrupted by overwrite-in-place + Respond.io open/close churn).
-- =====================================================================

-- Shared base: every escalation moment, its first human event (time+actor),
-- its next resolution, and contact identity.
-- ---------------------------------------------------------------------
--   Reused by all 4 sections below. If your client can't do a leading CTE
--   across statements, paste this WITH block in front of each SELECT.
-- ---------------------------------------------------------------------

-- =====================================================================
-- 08A. ROW-LEVEL EXTRACT — one row per human-handled escalation episode.
--      Columns are chart-friendly (numeric minutes + labels).
-- =====================================================================
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger, e.reason, e.to_tier,
         coalesce(e.triggered_by_id, e.assigned_to_id) AS actor_id
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id = e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (
  SELECT sla_tracking_id, event_at AS esc_at, reason, to_tier
  FROM ev WHERE event_type IN ('escalation','escalate')
),
episode AS (
  SELECT
    e.sla_tracking_id, e.esc_at, e.reason, e.to_tier,
    h.event_at   AS human_at,   h.actor_id AS handler_id,
    r.event_at   AS resolved_at
  FROM esc e
  LEFT JOIN LATERAL (   -- first human event after this escalation
    SELECT event_at, actor_id FROM ev h
    WHERE h.sla_tracking_id=e.sla_tracking_id AND h.event_at > e.esc_at
      AND (h.event_type IN ('response','handling_claimed','handling_taken_over') OR h.trigger='manual')
    ORDER BY h.event_at LIMIT 1
  ) h ON true
  LEFT JOIN LATERAL (   -- first resolution after this escalation
    SELECT event_at FROM ev r
    WHERE r.sla_tracking_id=e.sla_tracking_id AND r.event_at > e.esc_at
      AND r.event_type='resolution'
    ORDER BY r.event_at LIMIT 1
  ) r ON true
)
SELECT
  ep.esc_at                                              AS escalated_at,
  rc.phone_number,
  ep.to_tier                                            AS tier,
  ep.reason                                             AS escalation_reason,
  coalesce(u.name, u.email, '(unknown)')                AS handler,
  round((EXTRACT(epoch FROM ep.human_at   - ep.esc_at)/60.0)::numeric,1) AS response_min,
  round((EXTRACT(epoch FROM ep.resolved_at- ep.esc_at)/60.0)::numeric,1) AS resolution_min
FROM episode ep
JOIN conversation_sla_tracking t ON t.id = ep.sla_tracking_id
LEFT JOIN respond_contacts rc ON rc.id = t.respond_contact_id
LEFT JOIN users u ON u.id = ep.handler_id
WHERE ep.human_at IS NOT NULL
  AND ep.human_at > ep.esc_at
  AND ep.human_at < ep.esc_at + interval '7 days'
ORDER BY ep.esc_at;


-- =====================================================================
-- 08B. RESPONSE-TIME DISTRIBUTION (histogram buckets — bar chart)
-- =====================================================================
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
gap AS (
  SELECT EXTRACT(epoch FROM (
    (SELECT min(h.event_at) FROM ev h WHERE h.sla_tracking_id=e.sla_tracking_id AND h.event_at>e.esc_at
       AND (h.event_type IN ('response','handling_claimed','handling_taken_over') OR h.trigger='manual'))
    - e.esc_at))/60.0 gap_min
  FROM esc e
)
SELECT bucket, count(*) episodes FROM (
  SELECT CASE
    WHEN gap_min IS NULL              THEN '0 — no human (unhandled)'
    WHEN gap_min <= 5                 THEN '1 — <= 5 min'
    WHEN gap_min <= 15                THEN '2 — 5-15 min'
    WHEN gap_min <= 30                THEN '3 — 15-30 min'
    WHEN gap_min <= 60                THEN '4 — 30-60 min'
    WHEN gap_min <= 180               THEN '5 — 1-3 h'
    WHEN gap_min <= 360               THEN '6 — 3-6 h'
    WHEN gap_min <= 720               THEN '7 — 6-12 h'
    WHEN gap_min <= 1440              THEN '8 — 12-24 h'
    ELSE                                   '9 — > 24 h'
  END bucket FROM gap
) s GROUP BY bucket ORDER BY bucket;


-- =====================================================================
-- 08C. RESOLUTION-TIME DISTRIBUTION (histogram buckets — bar chart)
--      NOTE: resolution events include Respond auto-close churn; treat the
--      fast buckets with suspicion. Response (08B) is the trustworthy metric.
-- =====================================================================
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
gap AS (
  SELECT EXTRACT(epoch FROM (
    (SELECT min(r.event_at) FROM ev r WHERE r.sla_tracking_id=e.sla_tracking_id AND r.event_at>e.esc_at
       AND r.event_type='resolution') - e.esc_at))/60.0 gap_min
  FROM esc e
)
SELECT bucket, count(*) episodes FROM (
  SELECT CASE
    WHEN gap_min IS NULL              THEN '0 — never resolved'
    WHEN gap_min <= 15                THEN '1 — <= 15 min'
    WHEN gap_min <= 60                THEN '2 — 15-60 min'
    WHEN gap_min <= 180               THEN '3 — 1-3 h'
    WHEN gap_min <= 720               THEN '4 — 3-12 h'
    WHEN gap_min <= 1440             THEN '5 — 12-24 h'
    WHEN gap_min <= 4320             THEN '6 — 1-3 days'
    ELSE                                  '7 — > 3 days'
  END bucket FROM gap
) s GROUP BY bucket ORDER BY bucket;


-- =====================================================================
-- 08D. TOP HANDLERS — one credit per human-handled episode (bar chart)
--      + their median response time (who's fast).
-- =====================================================================
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger,
         coalesce(e.triggered_by_id, e.assigned_to_id) actor_id
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
ep AS (
  SELECT e.esc_at, h.actor_id, EXTRACT(epoch FROM h.event_at-e.esc_at)/60.0 gap_min
  FROM esc e
  JOIN LATERAL (
    SELECT event_at, actor_id FROM ev h
    WHERE h.sla_tracking_id=e.sla_tracking_id AND h.event_at>e.esc_at
      AND (h.event_type IN ('response','handling_claimed','handling_taken_over') OR h.trigger='manual')
    ORDER BY h.event_at LIMIT 1
  ) h ON true
  WHERE h.event_at < e.esc_at + interval '7 days'
)
SELECT coalesce(u.name,u.email,ep.actor_id,'(unknown)') handler,
       count(*)                                          episodes_handled,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_min))::numeric,1) median_response_min
FROM ep LEFT JOIN users u ON u.id=ep.actor_id
GROUP BY 1 ORDER BY episodes_handled DESC;


-- =====================================================================
-- 08E. TIMELINE — escalations vs human-handled per day (time-series chart)
-- =====================================================================
WITH ev AS (
  SELECT e.sla_tracking_id, e.event_type, e.event_at, e.trigger
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id=e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
esc AS (SELECT sla_tracking_id, event_at esc_at FROM ev WHERE event_type IN ('escalation','escalate')),
d AS (
  SELECT e.esc_at::date AS esc_day,
    (SELECT min(h.event_at) FROM ev h WHERE h.sla_tracking_id=e.sla_tracking_id AND h.event_at>e.esc_at
       AND (h.event_type IN ('response','handling_claimed','handling_taken_over') OR h.trigger='manual')
       AND h.event_at < e.esc_at + interval '7 days') human_at,
    e.esc_at
  FROM esc e
)
SELECT esc_day,
       count(*)                                  escalations,
       count(human_at)                           human_handled,
       round((avg(EXTRACT(epoch FROM human_at-esc_at))/60.0)::numeric,1) avg_response_min
FROM d GROUP BY esc_day ORDER BY esc_day;
