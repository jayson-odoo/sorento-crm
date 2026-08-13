-- PROBE: does go-live AI telemetry even exist? Run FIRST.
SELECT 'chat_histories'      src, count(*) FILTER (WHERE sent_at   >= '2026-07-01') AS july_rows,
       count(*) FILTER (WHERE turn_id   IS NOT NULL) AS have_turn_id,
       count(*) FILTER (WHERE respond_ts IS NOT NULL) AS have_respond_ts
  FROM chat_histories
UNION ALL
SELECT 'conversation_frames', count(*) FILTER (WHERE started_at >= '2026-07-01'), count(*), 0
  FROM conversation_frames
UNION ALL
SELECT 'conv_sla(conversation)', count(*) FILTER (WHERE initiated_at >= '2026-07-01'),
       count(*), count(*) FILTER (WHERE is_responded)
  FROM conversation_sla_tracking
 WHERE source_entity_type IS NULL OR source_entity_type='conversation';
