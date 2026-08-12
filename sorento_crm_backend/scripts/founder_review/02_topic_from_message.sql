-- =====================================================================
-- TOPIC WITHOUT FRAMES — classify enquiries from chat_histories.message text.
-- conversation_frames is dead (0 July rows), so topic is derived post-hoc by
-- keyword bucket. Deterministic, runnable today. If P3 shows state_trace
-- domain_hint is populated, prefer that (swap the CASE for the ->> path).
--
-- 8 canonical buckets — SAME taxonomy on answered + escalated side for parity.
-- CAVEAT for the slide: this is keyword classification of message text, not a
-- model label. Call it "estimated topic". Tune keywords to your catalogue.
-- =====================================================================

-- ---- reusable macro: topic_bucket(msg) ----
--   CASE
--     WHEN m ~* 'promo|discount|offer|campaign'                              THEN 'Promotion/Marketing'
--     WHEN m ~* 'grn|goods受|goods receiv|incoming|shipment|arriv|eta|container' THEN 'Incoming/Goods Receiving'
--     WHEN m ~* 'deliver|do\b|d/o|dispatch|lorry|transport|order status|when.*arrive' THEN 'Delivery/Orders'
--     WHEN m ~* 'stock|balance|qty|quantity|available|inventory|warehouse|how many' THEN 'Stock/Inventory'
--     WHEN m ~* 'photo|image|catalog|cert|spec sheet|drawing|pdf|brochure|file' THEN 'Files/Catalogue'
--     WHEN m ~* 'complain|defect|damage|wrong|broken|refund|return'          THEN 'Complaint/Service'
--     WHEN m ~* 'srt|price|product|item|model|size|colour|color|dimension'   THEN 'Product Info'
--     ELSE 'Other/Unclassified'
--   END

-- =====================================================================
-- T1. AI-ANSWERED by topic + AI response time per topic (respond_ts pairing)
-- =====================================================================
WITH inc AS (
  SELECT i.id, i.contact_id, i.message, i.sent_at, i.respond_ts,
    CASE
      WHEN i.message ~* 'promo|discount|offer|campaign'                     THEN 'Promotion/Marketing'
      WHEN i.message ~* 'grn|goods receiv|incoming|shipment|arriv|eta|container' THEN 'Incoming/Goods Receiving'
      WHEN i.message ~* 'deliver|dispatch|lorry|transport|order status'     THEN 'Delivery/Orders'
      WHEN i.message ~* 'stock|balance|quantity|available|inventory|warehouse|how many' THEN 'Stock/Inventory'
      WHEN i.message ~* 'photo|image|catalog|cert|spec|drawing|pdf|brochure|file' THEN 'Files/Catalogue'
      WHEN i.message ~* 'complain|defect|damage|wrong|broken|refund|return' THEN 'Complaint/Service'
      WHEN i.message ~* 'srt|price|product|item|model|size|colour|color|dimension' THEN 'Product Info'
      ELSE 'Other/Unclassified' END AS topic
  FROM chat_histories i
  WHERE i.type='incoming' AND i.sent_at >= '2026-07-01'
),
-- escalated contacts (to subtract from AI-answered)
esc_ids AS (
  SELECT DISTINCT i.id
  FROM inc i
  JOIN respond_contacts rc ON rc.respond_io_id = i.contact_id
  JOIN conversation_sla_tracking t ON t.respond_contact_id = rc.id
   AND (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
   AND t.initiated_at BETWEEN i.sent_at - interval '1 day' AND i.sent_at + interval '1 day'
),
paired AS (
  SELECT i.*,
         (SELECT min(o.respond_ts) FROM chat_histories o
           WHERE o.contact_id=i.contact_id AND o.type='outgoing'
             AND o.respond_ts > i.respond_ts AND o.respond_ts < i.respond_ts + interval '10 min') AS out_ts
  FROM inc i
  WHERE i.id NOT IN (SELECT id FROM esc_ids)      -- AI-answered only
)
SELECT topic,
       count(*)                                                              enquiries,
       count(out_ts)                                                        got_ai_reply,
       round(100.0*count(*)/sum(count(*)) OVER (),1)                        pct_of_ai_enquiries,
       round(avg(EXTRACT(epoch FROM out_ts-respond_ts))::numeric,1)        avg_resp_sec,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM out_ts-respond_ts)))::numeric,1) p90_resp_sec
FROM paired
GROUP BY topic
ORDER BY enquiries DESC;

-- =====================================================================
-- T2. ESCALATED by topic + human response/resolution time
-- topic = classify the contact's LAST incoming message before escalation.
-- =====================================================================
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
      WHEN c.message ~* 'promo|discount|offer|campaign'                     THEN 'Promotion/Marketing'
      WHEN c.message ~* 'grn|goods receiv|incoming|shipment|arriv|eta|container' THEN 'Incoming/Goods Receiving'
      WHEN c.message ~* 'deliver|dispatch|lorry|transport|order status'     THEN 'Delivery/Orders'
      WHEN c.message ~* 'stock|balance|quantity|available|inventory|warehouse|how many' THEN 'Stock/Inventory'
      WHEN c.message ~* 'photo|image|catalog|cert|spec|drawing|pdf|brochure|file' THEN 'Files/Catalogue'
      WHEN c.message ~* 'complain|defect|damage|wrong|broken|refund|return' THEN 'Complaint/Service'
      WHEN c.message ~* 'srt|price|product|item|model|size|colour|color|dimension' THEN 'Product Info'
      ELSE 'Other/Unclassified' END
     FROM chat_histories c
     WHERE c.contact_id = e.respond_io_id AND c.type='incoming'
       AND c.sent_at <= e.initiated_at + interval '5 min'
     ORDER BY c.sent_at DESC LIMIT 1) AS topic
  FROM esc e
)
SELECT coalesce(topic,'Other/Unclassified') topic,
       count(*)                                              escalated,
       count(*) FILTER (WHERE is_responded)                 got_human_reply,
       round(avg(response_time)      FILTER (WHERE is_responded)/60.0,1) avg_human_resp_min,
       round(avg(resolution_duration) FILTER (WHERE is_resolved)/60.0,1) avg_resolution_min
FROM tagged
GROUP BY 1 ORDER BY escalated DESC;

-- =====================================================================
-- T3. PARITY TABLE — per topic: AI-answered vs escalated, % AI-handled
-- =====================================================================
WITH inc AS (
  SELECT i.id, i.contact_id, i.sent_at,
    CASE
      WHEN i.message ~* 'promo|discount|offer|campaign'                     THEN 'Promotion/Marketing'
      WHEN i.message ~* 'grn|goods receiv|incoming|shipment|arriv|eta|container' THEN 'Incoming/Goods Receiving'
      WHEN i.message ~* 'deliver|dispatch|lorry|transport|order status'     THEN 'Delivery/Orders'
      WHEN i.message ~* 'stock|balance|quantity|available|inventory|warehouse|how many' THEN 'Stock/Inventory'
      WHEN i.message ~* 'photo|image|catalog|cert|spec|drawing|pdf|brochure|file' THEN 'Files/Catalogue'
      WHEN i.message ~* 'complain|defect|damage|wrong|broken|refund|return' THEN 'Complaint/Service'
      WHEN i.message ~* 'srt|price|product|item|model|size|colour|color|dimension' THEN 'Product Info'
      ELSE 'Other/Unclassified' END AS topic
  FROM chat_histories i
  WHERE i.type='incoming' AND i.sent_at >= '2026-07-01'
),
esc_ids AS (
  SELECT DISTINCT i.id FROM inc i
  JOIN respond_contacts rc ON rc.respond_io_id=i.contact_id
  JOIN conversation_sla_tracking t ON t.respond_contact_id=rc.id
   AND (t.source_entity_type IS NULL OR t.source_entity_type='conversation')
   AND t.initiated_at BETWEEN i.sent_at - interval '1 day' AND i.sent_at + interval '1 day'
)
SELECT topic,
       count(*)                                            total_enquiries,
       count(*) FILTER (WHERE e.id IS NULL)                ai_answered,
       count(*) FILTER (WHERE e.id IS NOT NULL)            escalated,
       round(100.0*count(*) FILTER (WHERE e.id IS NULL)/nullif(count(*),0),1) ai_handled_pct
FROM inc i
LEFT JOIN esc_ids e ON e.id=i.id
GROUP BY topic
ORDER BY total_enquiries DESC;
