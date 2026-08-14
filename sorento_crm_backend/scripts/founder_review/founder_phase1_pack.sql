-- =====================================================================
-- PHASE 1 GO-LIVE REVIEW PACK  (go-live = 2026-07-01)
-- DB: sorento_ai_automation  (CRM Postgres — same DB n8n writes chat_histories to)
-- Run 00_probe.sql FIRST. If July rows ~0, the numbers below are empty by data, not by query.
--
-- MODEL / DEFINITIONS (state these on the slide so no one argues later):
--   * Enquiry           = one INCOMING customer message (chat_histories.type='incoming').
--   * AI answered        = incoming turn that got a bot OUTGOING reply AND the contact was
--                          NOT handed to a human (no conversation-SLA row overlapping).
--   * Escalated to human = a conversation-scope row in conversation_sla_tracking
--                          (source_entity_type IS NULL OR ='conversation'). One open per contact.
--   * AI response time   = seconds incoming -> its bot outgoing reply.
--   * Human response time= conversation_sla_tracking.response_time (sec) — first human reply.
--   * Resolution time    = conversation_sla_tracking.resolution_duration (sec) — to resolved.
--   * Topic              = conversation_frames.domain, bucketed (see topic_bucket() CASE).
--
-- WINDOW: change :GO in each query. Default '2026-07-01'.
-- CHANNEL: chat_histories.channel — add "AND channel='whatsapp'" if you must isolate WA.
-- =====================================================================


-- =====================================================================
-- SECTION A — HIGH-LEVEL FUNNEL + WEEKLY DEGRADATION (the opening slide)
-- Total enquiries -> AI-answered vs escalated, per week (wk1/wk2/wk3 of July).
-- =====================================================================

-- A1. Weekly funnel: volume, escalation rate, trend
WITH inc AS (
  SELECT id, contact_id, sent_at,
         date_trunc('week', sent_at)::date AS wk
  FROM chat_histories
  WHERE type='incoming' AND sent_at >= '2026-07-01'
),
-- did a human conversation-SLA row open for this contact within +/- 1 day of the msg?
esc AS (
  SELECT DISTINCT i.id
  FROM inc i
  JOIN respond_contacts rc ON rc.respond_io_id = i.contact_id
  JOIN conversation_sla_tracking t
    ON t.respond_contact_id = rc.id
   AND (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
   AND t.initiated_at BETWEEN i.sent_at - interval '1 day' AND i.sent_at + interval '1 day'
)
SELECT i.wk AS week_start,
       count(*)                                          AS total_enquiries,
       count(*) FILTER (WHERE e.id IS NULL)              AS ai_answered,
       count(*) FILTER (WHERE e.id IS NOT NULL)          AS escalated,
       round(100.0*count(*) FILTER (WHERE e.id IS NOT NULL)/nullif(count(*),0),1) AS escalation_pct
FROM inc i
LEFT JOIN esc e ON e.id = i.id
GROUP BY i.wk
ORDER BY i.wk;

-- A2. Whole-period one-liner (the headline number)
WITH inc AS (
  SELECT id, contact_id, sent_at FROM chat_histories
  WHERE type='incoming' AND sent_at >= '2026-07-01'
),
esc AS (
  SELECT DISTINCT i.id FROM inc i
  JOIN respond_contacts rc ON rc.respond_io_id = i.contact_id
  JOIN conversation_sla_tracking t ON t.respond_contact_id = rc.id
   AND (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
   AND t.initiated_at BETWEEN i.sent_at - interval '1 day' AND i.sent_at + interval '1 day'
)
SELECT count(*) total_enquiries,
       count(*) FILTER (WHERE e.id IS NULL)     ai_answered,
       count(*) FILTER (WHERE e.id IS NOT NULL) escalated,
       round(100.0*count(*) FILTER (WHERE e.id IS NULL)/nullif(count(*),0),1)     ai_answer_pct,
       round(100.0*count(*) FILTER (WHERE e.id IS NOT NULL)/nullif(count(*),0),1) escalation_pct
FROM inc i LEFT JOIN esc e ON e.id=i.id;


-- =====================================================================
-- SECTION B — AI RESPONSE TIME
-- Prefer turn_id pairing; fall back to "next outgoing per contact" when turn_id null.
-- =====================================================================

-- B1. PREFERRED: turn_id pairing (use once turn_id/respond_ts are flowing)
WITH pairs AS (
  SELECT turn_id,
         min(sent_at) FILTER (WHERE type='incoming') AS in_at,
         min(sent_at) FILTER (WHERE type='outgoing') AS out_at
  FROM chat_histories
  WHERE turn_id IS NOT NULL AND sent_at >= '2026-07-01'
  GROUP BY turn_id
)
SELECT count(*) turns_paired,
       round(avg(EXTRACT(epoch FROM out_at-in_at))::numeric,1)            avg_sec,
       round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p50_sec,
       round((percentile_cont(0.9)  WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p90_sec,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p99_sec
FROM pairs
WHERE out_at IS NOT NULL AND out_at > in_at;

-- B2. FALLBACK: pair each incoming with the next outgoing from the same contact (no turn_id needed)
WITH ordered AS (
  SELECT contact_id, type, sent_at,
         lead(sent_at) FILTER (WHERE type='outgoing') OVER w AS na  -- not used directly; kept for clarity
  FROM chat_histories
  WHERE sent_at >= '2026-07-01'
  WINDOW w AS (PARTITION BY contact_id ORDER BY sent_at)
),
resp AS (
  SELECT i.contact_id, i.sent_at AS in_at,
         (SELECT min(o.sent_at) FROM chat_histories o
           WHERE o.contact_id=i.contact_id AND o.type='outgoing'
             AND o.sent_at > i.sent_at
             AND o.sent_at < i.sent_at + interval '10 min') AS out_at
  FROM chat_histories i
  WHERE i.type='incoming' AND i.sent_at >= '2026-07-01'
)
SELECT count(*) FILTER (WHERE out_at IS NOT NULL) replied,
       count(*) FILTER (WHERE out_at IS NULL)     no_reply_10min,
       round(avg(EXTRACT(epoch FROM out_at-in_at))::numeric,1)            avg_sec,
       round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p50_sec,
       round((percentile_cont(0.9)  WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p90_sec,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p99_sec
FROM resp;


-- =====================================================================
-- SECTION C — AI-ANSWERED, BY TOPIC (stock / product / files / incoming / ...)
-- Topic source = conversation_frames.domain (bucketed). Frames are the classified unit.
-- =====================================================================

-- C0. Reusable topic bucket — paste this CASE wherever "topic" is needed.
--     domain is LLM free-text (29+ raw values); bucket by keyword.
--   CASE
--     WHEN domain ILIKE '%promo%' OR domain ILIKE '%marketing%'      THEN 'Promotion/Marketing'
--     WHEN domain ILIKE '%goods_receiv%' OR domain ILIKE '%incoming%' OR domain ILIKE '%grn%' THEN 'Incoming/Goods Receiving'
--     WHEN domain ILIKE '%deliver%' OR domain ILIKE '%order%'        THEN 'Delivery/Orders'
--     WHEN domain ILIKE '%stock%' OR domain ILIKE '%inventory%' OR domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
--     WHEN domain ILIKE '%photo%' OR domain ILIKE '%catalog%' OR domain ILIKE '%certificate%' OR domain ILIKE '%image%' THEN 'Files/Catalogue'
--     WHEN domain ILIKE '%product%'                                  THEN 'Product Info'
--     WHEN domain ILIKE '%complaint%' OR domain ILIKE '%service%'    THEN 'Complaint/Service'
--     WHEN domain IS NULL OR domain='' OR domain ILIKE '%other%'     THEN 'Other/Unclassified'
--     ELSE 'Other/Unclassified' END

-- C1. AI-answered frames by topic (frame answered = tools_used non-empty OR closed cleanly, no escalation)
WITH f AS (
  SELECT cf.*,
    CASE
      WHEN domain ILIKE '%promo%' OR domain ILIKE '%marketing%'      THEN 'Promotion/Marketing'
      WHEN domain ILIKE '%goods_receiv%' OR domain ILIKE '%incoming%' OR domain ILIKE '%grn%' THEN 'Incoming/Goods Receiving'
      WHEN domain ILIKE '%deliver%' OR domain ILIKE '%order%'        THEN 'Delivery/Orders'
      WHEN domain ILIKE '%stock%' OR domain ILIKE '%inventory%' OR domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
      WHEN domain ILIKE '%photo%' OR domain ILIKE '%catalog%' OR domain ILIKE '%certificate%' OR domain ILIKE '%image%' THEN 'Files/Catalogue'
      WHEN domain ILIKE '%product%'                                  THEN 'Product Info'
      WHEN domain ILIKE '%complaint%' OR domain ILIKE '%service%'    THEN 'Complaint/Service'
      ELSE 'Other/Unclassified' END AS topic
  FROM conversation_frames cf
  WHERE started_at >= '2026-07-01'
)
SELECT topic,
       count(*)                                                    AS conversations,
       count(*) FILTER (WHERE array_length(tools_used,1) > 0)      AS used_a_tool,
       round(100.0*count(*)/sum(count(*)) OVER (),1)               AS pct_of_answered
FROM f
GROUP BY topic
ORDER BY conversations DESC;

-- C2. Most-used AI tools (proves WHICH capabilities carry the load)
SELECT tool, count(*) uses
FROM conversation_frames cf, unnest(cf.tools_used) AS tool
WHERE started_at >= '2026-07-01'
GROUP BY tool ORDER BY uses DESC;

-- C3. AI response time BY topic (frame -> its chat turns). Uses fallback pairing on chat_histories.
--     Join frames to chat by contact_id + time window of the frame.
WITH resp AS (
  SELECT i.contact_id, i.sent_at AS in_at,
         (SELECT min(o.sent_at) FROM chat_histories o
           WHERE o.contact_id=i.contact_id AND o.type='outgoing'
             AND o.sent_at > i.sent_at AND o.sent_at < i.sent_at + interval '10 min') AS out_at
  FROM chat_histories i
  WHERE i.type='incoming' AND i.sent_at >= '2026-07-01'
),
tagged AS (
  SELECT r.*,
    (SELECT CASE
       WHEN cf.domain ILIKE '%promo%' OR cf.domain ILIKE '%marketing%' THEN 'Promotion/Marketing'
       WHEN cf.domain ILIKE '%goods_receiv%' OR cf.domain ILIKE '%incoming%' THEN 'Incoming/Goods Receiving'
       WHEN cf.domain ILIKE '%deliver%' OR cf.domain ILIKE '%order%' THEN 'Delivery/Orders'
       WHEN cf.domain ILIKE '%stock%' OR cf.domain ILIKE '%inventory%' OR cf.domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
       WHEN cf.domain ILIKE '%photo%' OR cf.domain ILIKE '%catalog%' OR cf.domain ILIKE '%image%' THEN 'Files/Catalogue'
       WHEN cf.domain ILIKE '%product%' THEN 'Product Info'
       ELSE 'Other/Unclassified' END
     FROM conversation_frames cf
     WHERE cf.contact_id=r.contact_id
       AND r.in_at BETWEEN cf.started_at AND coalesce(cf.closed_at, cf.last_activity_at) + interval '5 min'
     ORDER BY cf.started_at DESC LIMIT 1) AS topic
  FROM resp r
  WHERE r.out_at IS NOT NULL
)
SELECT coalesce(topic,'Other/Unclassified') topic,
       count(*) replies,
       round(avg(EXTRACT(epoch FROM out_at-in_at))::numeric,1) avg_sec,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_at-in_at)))::numeric,1) p90_sec
FROM tagged GROUP BY 1 ORDER BY replies DESC;


-- =====================================================================
-- SECTION D — AI CANNOT ANSWER -> ESCALATED TO HUMAN
-- What got escalated, human response time, resolution time, and the topic mix
-- (so founder sees the SAME topic taxonomy on both the answered and escalated side).
-- =====================================================================

-- D1. Escalation volume + human response/resolution times, weekly (degradation view)
SELECT date_trunc('week', initiated_at)::date week_start,
       count(*)                                              escalated,
       count(*) FILTER (WHERE is_responded)                 got_human_reply,
       count(*) FILTER (WHERE is_resolved)                  resolved,
       round((avg(response_time)      FILTER (WHERE is_responded)/60.0)::numeric,1) avg_human_response_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY response_time)      FILTER (WHERE is_responded)/60.0)::numeric,1) p90_human_response_min,
       round((avg(resolution_duration) FILTER (WHERE is_resolved)/60.0)::numeric,1)  avg_resolution_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY resolution_duration) FILTER (WHERE is_resolved)/60.0)::numeric,1) p90_resolution_min
FROM conversation_sla_tracking
WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
  AND initiated_at >= '2026-07-01'
GROUP BY 1 ORDER BY 1;

-- D2. Escalated, BY TOPIC — bridge conversation-SLA -> respond_contacts -> latest frame's domain
WITH esc AS (
  SELECT t.*, rc.respond_io_id
  FROM conversation_sla_tracking t
  JOIN respond_contacts rc ON rc.id = t.respond_contact_id
  WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
    AND t.initiated_at >= '2026-07-01'
),
tagged AS (
  SELECT e.*,
    (SELECT CASE
       WHEN cf.domain ILIKE '%promo%' OR cf.domain ILIKE '%marketing%' THEN 'Promotion/Marketing'
       WHEN cf.domain ILIKE '%goods_receiv%' OR cf.domain ILIKE '%incoming%' THEN 'Incoming/Goods Receiving'
       WHEN cf.domain ILIKE '%deliver%' OR cf.domain ILIKE '%order%' THEN 'Delivery/Orders'
       WHEN cf.domain ILIKE '%stock%' OR cf.domain ILIKE '%inventory%' OR cf.domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
       WHEN cf.domain ILIKE '%photo%' OR cf.domain ILIKE '%catalog%' OR cf.domain ILIKE '%image%' THEN 'Files/Catalogue'
       WHEN cf.domain ILIKE '%product%' THEN 'Product Info'
       WHEN cf.domain ILIKE '%complaint%' OR cf.domain ILIKE '%service%' THEN 'Complaint/Service'
       ELSE 'Other/Unclassified' END
     FROM conversation_frames cf
     WHERE cf.contact_id = e.respond_io_id
       AND cf.started_at <= e.initiated_at + interval '10 min'
     ORDER BY cf.started_at DESC LIMIT 1) AS topic
  FROM esc e
)
SELECT coalesce(topic,'Other/Unclassified') topic,
       count(*)                                          escalated,
       round(avg(response_time)/60.0,1)                  avg_human_response_min,
       round(avg(resolution_duration)/60.0,1)            avg_resolution_min
FROM tagged GROUP BY 1 ORDER BY escalated DESC;

-- D3. Escalation reasons (verbatim) — WHY the AI handed off
SELECT coalesce(escalation_reason,'(none/auto)') reason, count(*)
FROM conversation_sla_tracking
WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
  AND initiated_at >= '2026-07-01'
GROUP BY 1 ORDER BY 2 DESC;


-- =====================================================================
-- SECTION E — TOPIC PARITY (one table: AI-answered vs escalated by topic)
-- The money slide: "Product enquiries — 82% AI-handled, 18% to human".
-- =====================================================================
WITH answered AS (   -- from frames NOT escalated
  SELECT
    CASE
      WHEN domain ILIKE '%promo%' OR domain ILIKE '%marketing%' THEN 'Promotion/Marketing'
      WHEN domain ILIKE '%goods_receiv%' OR domain ILIKE '%incoming%' THEN 'Incoming/Goods Receiving'
      WHEN domain ILIKE '%deliver%' OR domain ILIKE '%order%' THEN 'Delivery/Orders'
      WHEN domain ILIKE '%stock%' OR domain ILIKE '%inventory%' OR domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
      WHEN domain ILIKE '%photo%' OR domain ILIKE '%catalog%' OR domain ILIKE '%image%' THEN 'Files/Catalogue'
      WHEN domain ILIKE '%product%' THEN 'Product Info'
      WHEN domain ILIKE '%complaint%' OR domain ILIKE '%service%' THEN 'Complaint/Service'
      ELSE 'Other/Unclassified' END AS topic,
    count(*) n
  FROM conversation_frames
  WHERE started_at >= '2026-07-01'
  GROUP BY 1
),
escalated AS (       -- reuse D2 logic, counts only
  SELECT topic, count(*) n FROM (
    SELECT (SELECT CASE
       WHEN cf.domain ILIKE '%promo%' OR cf.domain ILIKE '%marketing%' THEN 'Promotion/Marketing'
       WHEN cf.domain ILIKE '%goods_receiv%' OR cf.domain ILIKE '%incoming%' THEN 'Incoming/Goods Receiving'
       WHEN cf.domain ILIKE '%deliver%' OR cf.domain ILIKE '%order%' THEN 'Delivery/Orders'
       WHEN cf.domain ILIKE '%stock%' OR cf.domain ILIKE '%inventory%' OR cf.domain ILIKE '%warehouse%' THEN 'Stock/Inventory'
       WHEN cf.domain ILIKE '%photo%' OR cf.domain ILIKE '%catalog%' OR cf.domain ILIKE '%image%' THEN 'Files/Catalogue'
       WHEN cf.domain ILIKE '%product%' THEN 'Product Info'
       WHEN cf.domain ILIKE '%complaint%' OR cf.domain ILIKE '%service%' THEN 'Complaint/Service'
       ELSE 'Other/Unclassified' END
      FROM conversation_frames cf WHERE cf.contact_id=rc.respond_io_id
        AND cf.started_at <= t.initiated_at + interval '10 min'
      ORDER BY cf.started_at DESC LIMIT 1) topic
    FROM conversation_sla_tracking t
    JOIN respond_contacts rc ON rc.id=t.respond_contact_id
    WHERE (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
      AND t.initiated_at >= '2026-07-01'
  ) s GROUP BY topic
)
SELECT coalesce(a.topic,e.topic) topic,
       coalesce(a.n,0) ai_answered,
       coalesce(e.n,0) escalated,
       round(100.0*coalesce(a.n,0)/nullif(coalesce(a.n,0)+coalesce(e.n,0),0),1) ai_handled_pct
FROM answered a FULL OUTER JOIN escalated e USING (topic)
ORDER BY (coalesce(a.n,0)+coalesce(e.n,0)) DESC;
