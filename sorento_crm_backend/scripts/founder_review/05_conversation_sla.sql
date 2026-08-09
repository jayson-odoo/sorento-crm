-- =====================================================================
-- PHASE 2 — CONVERSATION SLA TRACKING: escalations, response time,
-- resolution time, and the main human handlers.
--
-- SCOPE: conversation SLA only (source_entity_type IS NULL OR ='conversation').
--        Excludes form SLA (complaint/PR/stock_inquiry) — different system.
-- TIMING: is_responded flipped only ~6x and response_time is null on most rows,
--         so DERIVE from conversation_sla_event_log.event_at (the actual actions).
-- NAMES:  every *_id field is a users.id UUID -> join users.name (email fallback).
--
-- RECONCILE NOTE: ~125 escalation TEMPLATES in messages vs ~31-42 tracking rows.
--   Expected: one-open-conversation-per-contact merges repeat escalations from
--   the same contact into a single tracking row. R0 below quantifies the gap so
--   you can say it on the slide instead of being asked.
-- =====================================================================


-- ---------------------------------------------------------------------
-- R0. RECONCILE: escalation templates vs tracking rows vs distinct contacts
-- ---------------------------------------------------------------------
SELECT
  (SELECT count(*) FROM chat_histories
     WHERE type='outgoing' AND sent_at >= '2026-07-01'
       AND (message ILIKE '%out of the scope of my ability%'
         OR message ILIKE '%require human assistance%'))                AS escalation_messages,
  (SELECT count(DISTINCT contact_id) FROM chat_histories
     WHERE type='outgoing' AND sent_at >= '2026-07-01'
       AND (message ILIKE '%out of the scope of my ability%'
         OR message ILIKE '%require human assistance%'))                AS distinct_contacts_escalated,
  (SELECT count(*) FROM conversation_sla_tracking
     WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
       AND initiated_at >= '2026-07-01')                               AS tracking_rows;


-- ---------------------------------------------------------------------
-- R1. PER-ESCALATION detail: response + resolution time (event-derived), tier,
--     assignee, resolver. One row per tracking row — eyeball before aggregating.
-- ---------------------------------------------------------------------
WITH conv AS (
  SELECT id, initiated_at, current_tier, escalated_at, escalation_reason,
         is_resolved, resolved_at, resolution_duration,
         assigned_to_id, responded_by, resolved_by
  FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
first_human AS (            -- first human action = response time
  SELECT sla_tracking_id, min(event_at) first_human_at
  FROM conversation_sla_event_log
  WHERE event_type IN ('response','handling_claimed','handling_taken_over','reassignment')
     OR trigger='manual'
  GROUP BY sla_tracking_id
),
res_evt AS (               -- resolution event (fallback if resolution_duration null)
  SELECT sla_tracking_id, min(event_at) resolved_evt_at
  FROM conversation_sla_event_log WHERE event_type='resolution' GROUP BY sla_tracking_id
)
SELECT
  c.initiated_at,
  c.current_tier                                                          AS tier,
  c.escalation_reason,
  round((EXTRACT(epoch FROM fh.first_human_at - c.initiated_at)/60.0)::numeric,1)    AS response_min,
  coalesce(round((c.resolution_duration/60.0)::numeric,1),
           round((EXTRACT(epoch FROM re.resolved_evt_at - c.initiated_at)/60.0)::numeric,1)) AS resolution_min,
  c.is_resolved,
  coalesce(ur.name, ur.email, '(unassigned)')                            AS responder,
  coalesce(uz.name, uz.email, '(unresolved)')                            AS resolver
FROM conv c
LEFT JOIN first_human fh ON fh.sla_tracking_id = c.id
LEFT JOIN res_evt   re ON re.sla_tracking_id = c.id
LEFT JOIN users ur ON ur.id = c.responded_by
LEFT JOIN users uz ON uz.id = c.resolved_by
ORDER BY c.initiated_at;


-- ---------------------------------------------------------------------
-- R2. AGGREGATE: response + resolution time distribution (the headline)
-- ---------------------------------------------------------------------
WITH conv AS (
  SELECT id, initiated_at, is_resolved, resolution_duration
  FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
fh AS (
  SELECT sla_tracking_id, min(event_at) at FROM conversation_sla_event_log
  WHERE event_type IN ('response','handling_claimed','handling_taken_over','reassignment') OR trigger='manual'
  GROUP BY 1
),
re AS (
  SELECT sla_tracking_id, min(event_at) at FROM conversation_sla_event_log
  WHERE event_type='resolution' GROUP BY 1
),
m AS (
  SELECT c.*,
         EXTRACT(epoch FROM fh.at - c.initiated_at)/60.0 AS resp_min,
         coalesce(c.resolution_duration/60.0,
                  EXTRACT(epoch FROM re.at - c.initiated_at)/60.0) AS reso_min
  FROM conv c LEFT JOIN fh ON fh.sla_tracking_id=c.id LEFT JOIN re ON re.sla_tracking_id=c.id
)
SELECT count(*)                                            escalations,
       count(resp_min)                                    responded,
       round(avg(resp_min)::numeric,1)                    avg_response_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY resp_min)::numeric,1) p50_response_min,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY resp_min)::numeric,1) p90_response_min,
       count(*) FILTER (WHERE is_resolved)                resolved,
       round(avg(reso_min)::numeric,1)                    avg_resolution_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY reso_min)::numeric,1) p50_resolution_min,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY reso_min)::numeric,1) p90_resolution_min
FROM m;


-- ---------------------------------------------------------------------
-- R3. MAIN HANDLERS — leaderboard from event_log (actual actions), by person.
--     Credits the assignee/actor per event. Names via users.
-- ---------------------------------------------------------------------
WITH ev AS (
  SELECT e.event_type,
         coalesce(e.triggered_by_id, e.assigned_to_id) AS actor_id,
         e.event_at
  FROM conversation_sla_event_log e
  JOIN conversation_sla_tracking t ON t.id = e.sla_tracking_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
    AND e.event_type IN ('response','resolution','handling_claimed','handling_taken_over')
)
SELECT coalesce(u.name, u.email, ev.actor_id, '(unknown)')      AS handler,
       count(*) FILTER (WHERE event_type='response')            AS responded,
       count(*) FILTER (WHERE event_type IN ('handling_claimed','handling_taken_over')) AS claimed_handling,
       count(*) FILTER (WHERE event_type='resolution')          AS resolved,
       count(*)                                                 AS total_actions
FROM ev LEFT JOIN users u ON u.id = ev.actor_id
GROUP BY 1
ORDER BY total_actions DESC;

-- R3-alt. Simpler handler view straight off the tracking row (resolver credit):
SELECT coalesce(u.name, u.email, '(unresolved)') AS resolver,
       count(*) resolved
FROM conversation_sla_tracking t
LEFT JOIN users u ON u.id = t.resolved_by
WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
  AND t.initiated_at >= '2026-07-01' AND t.is_resolved
GROUP BY 1 ORDER BY resolved DESC;
