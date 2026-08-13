-- =====================================================================
-- PHASE 1 — RAW PER-TURN EXPORT: every incoming enquiry, its bot reply,
-- and the response time. One row per incoming customer message.
-- Eyeball this before trusting any aggregate.
--
-- PAIRING: for each incoming, take the FIRST outgoing from the same contact
--          after it, within 30 min (the reply). turn_id used when both ends
--          carry it (exact); otherwise the time-window pairing.
-- CLOCK:   response time uses respond_ts when BOTH ends have it (authoritative),
--          else falls back to sent_at. `clock` column tells you which.
-- =====================================================================

WITH inc AS (
  SELECT id, contact_id, phone_number,
         coalesce(first_name,'')||' '||coalesce(last_name,'') AS name,
         sent_at, respond_ts, turn_id, message
  FROM chat_histories
  WHERE type='incoming' AND sent_at >= '2026-07-01'
)
SELECT
  i.sent_at                                   AS enquiry_at,
  i.name,
  i.phone_number,
  left(i.message, 120)                        AS enquiry,
  left(o.message, 120)                        AS bot_reply,
  CASE
    WHEN o.message ILIKE '%out of the scope of my ability%'
      OR o.message ILIKE '%require human assistance%'    THEN 'escalated'
    WHEN o.message ILIKE '%outside of our working hours%'
      OR o.message ILIKE '%operating hours%'             THEN 'after_hours'
    WHEN o.message ILIKE '%noted down your enquir%'       THEN 'logged_pic'
    WHEN o.id IS NULL                                     THEN 'no_reply'
    ELSE 'ai_answered'
  END                                         AS outcome,
  -- response time (seconds): prefer respond_ts on both ends, else sent_at
  CASE
    WHEN i.respond_ts IS NOT NULL AND o.respond_ts IS NOT NULL
      THEN round(EXTRACT(epoch FROM o.respond_ts - i.respond_ts)::numeric,1)
    WHEN o.id IS NOT NULL
      THEN round(EXTRACT(epoch FROM o.sent_at - i.sent_at)::numeric,1)
    ELSE NULL
  END                                         AS response_sec,
  CASE
    WHEN i.respond_ts IS NOT NULL AND o.respond_ts IS NOT NULL THEN 'respond_ts'
    WHEN o.id IS NOT NULL THEN 'sent_at'
    ELSE 'none'
  END                                         AS clock,
  i.turn_id
FROM inc i
LEFT JOIN LATERAL (
  SELECT o.id, o.message, o.sent_at, o.respond_ts
  FROM chat_histories o
  WHERE o.contact_id = i.contact_id
    AND o.type='outgoing'
    AND o.sent_at > i.sent_at
    AND o.sent_at < i.sent_at + interval '30 min'
    -- exact match when turn_id present on both:
    AND (i.turn_id IS NULL OR o.turn_id IS NULL OR o.turn_id = i.turn_id)
  ORDER BY o.sent_at ASC
  LIMIT 1
) o ON true
ORDER BY i.sent_at;

-- ---------------------------------------------------------------------
-- Quick summary of the SAME pairing (sanity check the raw export above):
-- ---------------------------------------------------------------------
-- WITH inc AS (SELECT id, contact_id, sent_at, respond_ts, turn_id FROM chat_histories
--              WHERE type='incoming' AND sent_at >= '2026-07-01'),
-- paired AS (
--   SELECT i.*, o.sent_at out_sent, o.respond_ts out_rts,
--     CASE WHEN i.respond_ts IS NOT NULL AND o.respond_ts IS NOT NULL
--          THEN EXTRACT(epoch FROM o.respond_ts-i.respond_ts)
--          WHEN o.sent_at IS NOT NULL THEN EXTRACT(epoch FROM o.sent_at-i.sent_at) END sec
--   FROM inc i LEFT JOIN LATERAL (
--     SELECT o.sent_at, o.respond_ts FROM chat_histories o
--     WHERE o.contact_id=i.contact_id AND o.type='outgoing'
--       AND o.sent_at>i.sent_at AND o.sent_at<i.sent_at+interval '30 min'
--       AND (i.turn_id IS NULL OR o.turn_id IS NULL OR o.turn_id=i.turn_id)
--     ORDER BY o.sent_at LIMIT 1) o ON true)
-- SELECT count(*) enquiries, count(sec) replied, count(*)-count(sec) no_reply,
--        round(avg(sec)::numeric,1) avg_sec,
--        round((percentile_cont(0.5) WITHIN GROUP (ORDER BY sec))::numeric,1) p50_sec,
--        round((percentile_cont(0.9) WITHIN GROUP (ORDER BY sec))::numeric,1) p90_sec,
--        round((percentile_cont(0.99) WITHIN GROUP (ORDER BY sec))::numeric,1) p99_sec
-- FROM paired;
