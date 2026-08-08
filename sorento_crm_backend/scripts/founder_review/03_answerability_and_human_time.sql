-- =====================================================================
-- ANSWERABILITY (AI can / cannot answer) FROM THE BOT'S OWN TEMPLATES
-- + real human response/resolution time DERIVED FROM conversation_sla_event_log.
--
-- WHY templates: the bot emits fixed outgoing messages that ARE the decision:
--   * "...out of the scope of my ability and require human assistance..." -> ESCALATED (AI cannot)
--   * "...outside of our working hours... notify the respective PIC..."    -> AFTER-HOURS deferral
--   * "We have noted down your enquiries..."                               -> logged for PIC
--   * anything else with data content                                     -> AI ANSWERED
-- Deterministic, covers ALL outgoing — no dependency on the 31 conv_sla rows.
--
-- WHY event_log for timing: tracking.is_responded flipped only 6x, but humans
-- DID act (30 resolved). Human actions are logged as events; the row's
-- response_time never got written. Derive first-human-touch from event_at.
-- =====================================================================


-- ---------------------------------------------------------------------
-- P0 (RUN FIRST on prod): confirm the templates live in chat_histories.
-- If escalation_tmpl/afterhours_tmpl are ~0 here but >0 in n8n_chat_histories,
-- the user-facing send is logged only in n8n_chat_histories -> classify there
-- instead (swap FROM chat_histories -> n8n_chat_histories, message->>'content').
-- ---------------------------------------------------------------------
SELECT
  count(*) FILTER (WHERE message ILIKE '%out of the scope of my ability%'
                      OR message ILIKE '%require human assistance%')      AS escalation_tmpl,
  count(*) FILTER (WHERE message ILIKE '%outside of our working hours%'
                      OR message ILIKE '%operating hours%')               AS afterhours_tmpl,
  count(*) FILTER (WHERE message ILIKE '%noted down your enquir%')        AS noted_tmpl,
  count(*)                                                                AS total_outgoing
FROM chat_histories
WHERE type='outgoing' AND sent_at >= '2026-07-01';


-- =====================================================================
-- 03A. HEADLINE: AI answered vs cannot-answer, whole period
-- =====================================================================
WITH out AS (
  SELECT
    CASE
      WHEN message ILIKE '%out of the scope of my ability%'
        OR message ILIKE '%require human assistance%'      THEN 'Escalated to human (AI cannot)'
      WHEN message ILIKE '%outside of our working hours%'
        OR message ILIKE '%operating hours%'               THEN 'After-hours deferral'
      WHEN message ILIKE '%noted down your enquir%'         THEN 'Logged for PIC'
      ELSE 'AI answered'
    END AS outcome
  FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
)
SELECT outcome,
       count(*)                                        replies,
       round(100.0*count(*)/sum(count(*)) OVER (),1)   pct
FROM out GROUP BY outcome ORDER BY replies DESC;


-- =====================================================================
-- 03B. WEEKLY DEGRADATION: answerability by week (wk1/2/3 of July)
-- The "is it getting better or worse" slide.
-- =====================================================================
WITH out AS (
  SELECT date_trunc('week', sent_at)::date wk,
    CASE
      WHEN message ILIKE '%out of the scope of my ability%'
        OR message ILIKE '%require human assistance%'      THEN 'escalated'
      WHEN message ILIKE '%outside of our working hours%'
        OR message ILIKE '%operating hours%'               THEN 'after_hours'
      WHEN message ILIKE '%noted down your enquir%'         THEN 'logged_pic'
      ELSE 'ai_answered'
    END AS outcome
  FROM chat_histories
  WHERE type='outgoing' AND sent_at >= '2026-07-01'
)
SELECT wk AS week_start,
       count(*)                                                     total_replies,
       count(*) FILTER (WHERE outcome='ai_answered')               ai_answered,
       count(*) FILTER (WHERE outcome='escalated')                 escalated,
       count(*) FILTER (WHERE outcome='after_hours')               after_hours,
       count(*) FILTER (WHERE outcome='logged_pic')                logged_pic,
       round(100.0*count(*) FILTER (WHERE outcome='ai_answered')/nullif(count(*),0),1) ai_answer_pct,
       round(100.0*count(*) FILTER (WHERE outcome='escalated')/nullif(count(*),0),1)   escalation_pct
FROM out GROUP BY wk ORDER BY wk;


-- =====================================================================
-- 03C. HUMAN RESPONSE + RESOLUTION TIME — derived from event_log (the fix)
-- tracking.is_responded is unreliable (6). Use first human-action event_at.
-- Human-action events: response, handling_claimed, handling_taken_over,
-- reassignment, OR any manual-trigger event.
-- =====================================================================
WITH conv AS (
  SELECT id, initiated_at, resolved_at, resolution_duration, is_resolved
  FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
first_human AS (
  SELECT sla_tracking_id, min(event_at) AS first_human_at
  FROM conversation_sla_event_log
  WHERE event_type IN ('response','handling_claimed','handling_taken_over','reassignment')
     OR trigger='manual'
  GROUP BY sla_tracking_id
)
SELECT count(*)                                                         escalations,
       count(fh.first_human_at)                                        got_human_action,
       round((avg(EXTRACT(epoch FROM fh.first_human_at - c.initiated_at))/60.0)::numeric,1)  avg_response_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM fh.first_human_at - c.initiated_at))/60.0)::numeric,1) p50_response_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM fh.first_human_at - c.initiated_at))/60.0)::numeric,1) p90_response_min,
       count(*) FILTER (WHERE c.is_resolved)                           resolved,
       round((avg(c.resolution_duration) FILTER (WHERE c.is_resolved)/60.0)::numeric,1)  avg_resolution_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY c.resolution_duration) FILTER (WHERE c.is_resolved)/60.0)::numeric,1) p90_resolution_min
FROM conv c
LEFT JOIN first_human fh ON fh.sla_tracking_id = c.id;

-- 03C-alt. If resolution_duration is also patchy, derive resolution from event_at too:
WITH conv AS (
  SELECT id, initiated_at FROM conversation_sla_tracking
  WHERE (source_entity_type IS NULL OR source_entity_type='conversation')
    AND initiated_at >= '2026-07-01'
),
res AS (
  SELECT sla_tracking_id, min(event_at) resolved_at
  FROM conversation_sla_event_log WHERE event_type='resolution' GROUP BY 1
)
SELECT count(*) escalations, count(r.resolved_at) resolved_via_event,
       round((avg(EXTRACT(epoch FROM r.resolved_at - c.initiated_at))/60.0)::numeric,1) avg_resolution_min
FROM conv c LEFT JOIN res r ON r.sla_tracking_id=c.id;


-- =====================================================================
-- 03D. ANSWERABILITY x TOPIC — pair each outgoing back to its triggering
-- incoming, classify that incoming's topic (keyword), cross-tab with outcome.
-- Gives: "Stock enquiries — 88% AI-answered, 12% escalated".
-- =====================================================================
WITH out AS (
  SELECT o.contact_id, o.sent_at AS out_at,
    CASE
      WHEN o.message ILIKE '%out of the scope of my ability%'
        OR o.message ILIKE '%require human assistance%'    THEN 'escalated'
      WHEN o.message ILIKE '%outside of our working hours%'
        OR o.message ILIKE '%operating hours%'             THEN 'after_hours'
      WHEN o.message ILIKE '%noted down your enquir%'       THEN 'logged_pic'
      ELSE 'ai_answered'
    END AS outcome,
    -- the incoming message that triggered this reply (latest incoming before it)
    (SELECT c.message FROM chat_histories c
      WHERE c.contact_id=o.contact_id AND c.type='incoming' AND c.sent_at < o.sent_at
      ORDER BY c.sent_at DESC LIMIT 1) AS trigger_msg
  FROM chat_histories o
  WHERE o.type='outgoing' AND o.sent_at >= '2026-07-01'
),
tagged AS (
  SELECT outcome,
    CASE
      WHEN trigger_msg ~* 'promo|discount|offer|campaign'                     THEN 'Promotion/Marketing'
      WHEN trigger_msg ~* 'grn|goods receiv|incoming|shipment|arriv|eta|container' THEN 'Incoming/Goods Receiving'
      WHEN trigger_msg ~* 'deliver|dispatch|lorry|transport|order status'     THEN 'Delivery/Orders'
      WHEN trigger_msg ~* 'stock|balance|quantity|available|inventory|warehouse|how many' THEN 'Stock/Inventory'
      WHEN trigger_msg ~* 'photo|image|catalog|cert|spec|drawing|pdf|brochure|file' THEN 'Files/Catalogue'
      WHEN trigger_msg ~* 'complain|defect|damage|wrong|broken|refund|return' THEN 'Complaint/Service'
      WHEN trigger_msg ~* 'srt|price|product|item|model|size|colour|color|dimension' THEN 'Product Info'
      ELSE 'Other/Unclassified' END AS topic
  FROM out
)
SELECT topic,
       count(*)                                            replies,
       count(*) FILTER (WHERE outcome='ai_answered')       ai_answered,
       count(*) FILTER (WHERE outcome='escalated')         escalated,
       count(*) FILTER (WHERE outcome='after_hours')       after_hours,
       round(100.0*count(*) FILTER (WHERE outcome='ai_answered')
             /nullif(count(*) FILTER (WHERE outcome IN ('ai_answered','escalated')),0),1) ai_handled_pct
FROM tagged
GROUP BY topic ORDER BY replies DESC;
