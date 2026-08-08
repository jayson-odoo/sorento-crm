-- =====================================================================
-- DEFINITIVE CROSS-CHECK — did humans reply to July escalations OFF-SYSTEM?
-- The SLA event log may show 0 July human actions simply because agents
-- reply in the Respond.io inbox and CRM never logs an SLA event.
-- chat_histories logs the actual WhatsApp traffic. After the bot sends the
-- escalation template it STOPS; any following OUTGOING message = a human
-- agent reply. This measures the TRUE human response, independent of SLA.
--
-- ASSUMPTION to verify (ask ops): does chat_histories capture agent-typed
-- Respond.io messages, or only bot sends? If bot-only, "no outgoing after
-- escalation" = genuinely dropped. If it captures agent messages too, the
-- next outgoing IS the human reply. 10D lets you eyeball which.
-- =====================================================================

-- Known bot templates to EXCLUDE when hunting for the human reply:
--   escalation / after-hours / noted / numbered stock-list etc.
-- We treat "next outgoing that is NOT the escalation/after-hours template" as human.

-- 10A. HEADLINE: of July escalation messages, how many got ANY later outgoing?
WITH esc AS (
  SELECT id, contact_id, sent_at AS esc_at
  FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
    AND (message ILIKE '%out of the scope of my ability%'
      OR message ILIKE '%require human assistance%')
),
nxt AS (
  SELECT e.*,
    (SELECT min(o.sent_at) FROM chat_histories o
       WHERE o.contact_id=e.contact_id AND o.type='outgoing'
         AND o.sent_at > e.esc_at
         AND o.message NOT ILIKE '%out of the scope of my ability%'
         AND o.message NOT ILIKE '%require human assistance%'
         AND o.message NOT ILIKE '%outside of our working hours%'
         AND o.message NOT ILIKE '%operating hours%') AS next_out_at
  FROM esc e
)
SELECT count(*)                                                    escalation_messages,
       count(next_out_at)                                          got_later_outgoing,
       count(*)-count(next_out_at)                                 no_outgoing_after,
       round((avg(EXTRACT(epoch FROM next_out_at-esc_at))/60.0)::numeric,1) avg_gap_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM next_out_at-esc_at))/60.0)::numeric,1) p50_gap_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM next_out_at-esc_at))/60.0)::numeric,1) p90_gap_min
FROM nxt;

-- 10B. Distribution of that gap (histogram — is it minutes or days?)
WITH esc AS (
  SELECT contact_id, sent_at AS esc_at FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
    AND (message ILIKE '%out of the scope of my ability%' OR message ILIKE '%require human assistance%')
),
g AS (
  SELECT EXTRACT(epoch FROM (
    (SELECT min(o.sent_at) FROM chat_histories o
      WHERE o.contact_id=e.contact_id AND o.type='outgoing' AND o.sent_at>e.esc_at
        AND o.message NOT ILIKE '%out of the scope of my ability%'
        AND o.message NOT ILIKE '%require human assistance%'
        AND o.message NOT ILIKE '%outside of our working hours%'
        AND o.message NOT ILIKE '%operating hours%') - e.esc_at))/60.0 gap_min
  FROM esc e
)
SELECT CASE
    WHEN gap_min IS NULL THEN '0 — no outgoing after'
    WHEN gap_min <= 5    THEN '1 — <= 5 min'
    WHEN gap_min <= 30   THEN '2 — 5-30 min'
    WHEN gap_min <= 60   THEN '3 — 30-60 min'
    WHEN gap_min <= 180  THEN '4 — 1-3 h'
    WHEN gap_min <= 720  THEN '5 — 3-12 h'
    WHEN gap_min <= 1440 THEN '6 — 12-24 h'
    ELSE                      '7 — > 24 h'
  END bucket, count(*) episodes
FROM g GROUP BY bucket ORDER BY bucket;

-- 10C. Daily: July escalations vs got-a-later-reply (time series)
WITH esc AS (
  SELECT contact_id, sent_at AS esc_at FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
    AND (message ILIKE '%out of the scope of my ability%' OR message ILIKE '%require human assistance%')
),
n AS (
  SELECT e.esc_at,
    (SELECT min(o.sent_at) FROM chat_histories o
      WHERE o.contact_id=e.contact_id AND o.type='outgoing' AND o.sent_at>e.esc_at
        AND o.message NOT ILIKE '%out of the scope of my ability%'
        AND o.message NOT ILIKE '%require human assistance%'
        AND o.message NOT ILIKE '%outside of our working hours%'
        AND o.message NOT ILIKE '%operating hours%') next_out
  FROM esc e
)
SELECT esc_at::date AS esc_day,
       count(*)          escalations,
       count(next_out)   got_reply
FROM n GROUP BY esc_at::date ORDER BY esc_day;

-- 10D. EYEBALL — for a handful of July escalations, show the escalation msg
--      and the next outgoing, so you can judge if it's a real human reply.
WITH esc AS (
  SELECT id, contact_id, sent_at AS esc_at, left(message,60) esc_msg
  FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
    AND (message ILIKE '%out of the scope of my ability%' OR message ILIKE '%require human assistance%')
  ORDER BY sent_at LIMIT 20
)
SELECT e.esc_at, e.contact_id,
       (SELECT left(o.message,80) FROM chat_histories o
         WHERE o.contact_id=e.contact_id AND o.type='outgoing' AND o.sent_at>e.esc_at
           AND o.message NOT ILIKE '%out of the scope of my ability%'
           AND o.message NOT ILIKE '%require human assistance%'
           AND o.message NOT ILIKE '%outside of our working hours%'
           AND o.message NOT ILIKE '%operating hours%'
         ORDER BY o.sent_at LIMIT 1) AS next_outgoing_after
FROM esc e ORDER BY e.esc_at;
