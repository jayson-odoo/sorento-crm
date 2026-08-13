-- =====================================================================
-- CORRECTED LENS — scope by EVENT_AT, not tracking.initiated_at.
-- Overwrite-in-place resets initiated_at, so an initiated_at>=Jul row can
-- carry March events. To see what actually happened IN JULY, filter on the
-- event's own timestamp. This is the honest go-live view.
-- =====================================================================

-- 09A. ALL event types that FIRED in July (by event_at). Does the log even
--      receive human-action events post-go-live?
SELECT event_type,
       count(*)                          events_in_july,
       count(DISTINCT sla_tracking_id)   distinct_rows,
       min(event_at)::date               first_seen,
       max(event_at)::date               last_seen
FROM conversation_sla_event_log
WHERE event_at >= '2026-07-01'
GROUP BY event_type
ORDER BY events_in_july DESC;

-- 09B. THE HEADLINE: July escalation events vs July human-action events.
SELECT
  count(*) FILTER (WHERE event_type IN ('escalation','escalate'))                    AS escalations,
  count(*) FILTER (WHERE event_type IN ('response','handling_claimed','handling_taken_over')) AS human_action_events,
  count(*) FILTER (WHERE trigger='manual')                                           AS manual_trigger_events,
  count(*) FILTER (WHERE event_type='resolution')                                    AS resolution_events,
  count(*) FILTER (WHERE event_type='assign')                                        AS assign_events
FROM conversation_sla_event_log
WHERE event_at >= '2026-07-01';

-- 09C. If ANY human/manual events exist in July — who, when, what.
SELECT ev.event_at, ev.event_type, ev.trigger,
       coalesce(u.name,u.email,'(unknown)') actor
FROM conversation_sla_event_log ev
LEFT JOIN users u ON u.id = coalesce(ev.triggered_by_id, ev.assigned_to_id)
WHERE ev.event_at >= '2026-07-01'
  AND (ev.event_type IN ('response','handling_claimed','handling_taken_over')
       OR ev.trigger='manual')
ORDER BY ev.event_at;

-- 09D. Daily July: escalations vs human actions (by event_at) — the concerning chart.
SELECT event_at::date AS ev_day,
       count(*) FILTER (WHERE event_type IN ('escalation','escalate'))                     escalations,
       count(*) FILTER (WHERE event_type IN ('response','handling_claimed','handling_taken_over') OR trigger='manual') human_actions,
       count(*) FILTER (WHERE event_type='resolution')                                     resolutions
FROM conversation_sla_event_log
WHERE event_at >= '2026-07-01'
GROUP BY event_at::date
ORDER BY ev_day;
