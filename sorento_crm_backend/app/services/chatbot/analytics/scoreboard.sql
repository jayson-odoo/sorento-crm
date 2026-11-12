-- Chatbot live weekly scoreboard (CHATBOT-STEP-A, A1). Read-only SELECTs. Run on the dev copy or on a read replica.
-- Re-run next week UNCHANGED: the only parameter is p.week_from (first Monday shown, Malaysia time) in the CTE below.
-- Two statements, each ends in ';': (1) overall by week and audience, (2) by week and topic (intent).
-- Each took 2 to 5 seconds on the dev copy of prod 12 Nov (limit 30 s). If it nears the limit, raise week_from.
-- Statement 1: overall.
WITH p AS (
  SELECT DATE '2026-09-07' AS week_from,                       -- the ONLY parameter: first Monday shown (Malaysia time)
         ARRAY['check_stock','check_incoming','check_order','check_product_attachment',
               'check_promotion','check_product','(none)','check_po_cost'] AS top8  -- fixed topic list (top 8 by volume, 8 Sep to 12 Nov 2026)
),
a AS (   -- real WhatsApp asks: the real-traffic filter
  SELECT f.id, f.turn_id, f.contact_respond_id, f.audience, f.outcome, f.reply_ms, f.asked_at,
         date_trunc('week', f.asked_at AT TIME ZONE 'Asia/Kuala_Lumpur')::date AS wk,
         COALESCE(f.intent, '(none)') AS intent,
         t.stage, t.response #>> '{reply,text}' AS txt,
         (f.outcome = 'clarified' OR (t.response #>> '{reply,text}') ~* 'did you mean|how many units|which period|reply with the number|多少件') AS askback   -- the reply asked the customer something back
    FROM chatbot.chat_ask_facts f
    JOIN chatbot.turns t ON t.id = f.turn_id
    CROSS JOIN p
   WHERE t.is_test = false
     AND t.ingress NOT IN ('console','panel','agent')
     AND f.audience IN ('staff','dealer')
     AND f.outcome <> 'noise'
     AND f.asked_at >= (p.week_from::timestamp AT TIME ZONE 'Asia/Kuala_Lumpur') - interval '10 minutes'
),
refs AS (   -- products/brands the ask looked up or named (one row per ask and ref)
  SELECT i.ask_id, i.kind || ':' || i.ref_id AS ref
    FROM chatbot.chat_ask_items i
   WHERE i.role IN ('asked','named')
     AND i.ask_id IN (SELECT id FROM a)
   GROUP BY i.ask_id, i.kind, i.ref_id
),
ref_gap AS (   -- per ask: does the same contact ask the same intent about the same product/brand again within 10 minutes
  SELECT x.id, bool_or(x.nxt IS NOT NULL AND x.nxt - x.asked_at <= interval '10 minutes') AS again_ref_raw,
         bool_or(x.nxt IS NOT NULL AND x.nxt - x.asked_at <= interval '10 minutes' AND NOT x.askback) AS again_ref   -- fixed: the later message is not just the answer to the bot's own question
    FROM (SELECT a.id, a.asked_at, a.askback,
                 lead(a.asked_at) OVER (PARTITION BY a.contact_respond_id, a.intent, r.ref ORDER BY a.asked_at, a.id) AS nxt
            FROM a JOIN refs r ON r.ask_id = a.id) x
   GROUP BY x.id
),
intent_gap AS (   -- per ask: same contact asks the same intent again within 10 minutes (no product/brand needed)
  SELECT y.id, COALESCE(y.gap_ok, false) AS again_intent_raw, COALESCE(y.gap_ok AND NOT y.askback, false) AS again_intent
    FROM (SELECT a.id, a.askback,
                 (lead(a.asked_at) OVER (PARTITION BY a.contact_respond_id, a.intent ORDER BY a.asked_at, a.id)
                    - a.asked_at) <= interval '10 minutes' AS gap_ok
            FROM a) y
),
llm AS (   -- LLM calls and cost per turn (chatbot features only, view filters feature LIKE 'chatbot%')
  SELECT chatbot_turn_id, count(*) AS n, sum(cost_usd) AS c, bool_and(priced) AS ok
    FROM analytics_connector.llm_calls
   WHERE chatbot_turn_id IS NOT NULL
     AND created_at >= (SELECT week_from FROM p) - 1
   GROUP BY chatbot_turn_id
),
b AS (
  SELECT a.wk, a.audience, a.contact_respond_id,
         CASE WHEN a.intent = ANY (p.top8) THEN a.intent ELSE 'other' END AS topic,
         (a.txt ~* '(couldn.t find|could not find|not found|no record|cannot find|can.t find|unable to find|did not find|didn.t find)') AS nf_text,
         (a.outcome IN ('answered_empty','missed'))  AS nf_out,
         (a.outcome = 'missed')                      AS missed,
         (a.outcome = 'clarified')                   AS clar_out,
         (a.outcome = 'clarified'
          OR a.txt ~* 'did you mean|how many units|which period|reply with the number|多少件') AS clar_any,
         (a.outcome = 'technical')                   AS tech,
         (a.outcome = 'technical' AND a.stage = 'send_unconfirmed') AS tech_delivery,
         (rg.id IS NOT NULL)                         AS has_ref,
         COALESCE(rg.again_ref, false)               AS again_ref,
         COALESCE(rg.again_ref_raw, false)           AS again_ref_raw,
         COALESCE(ig.again_intent, false)            AS again_intent,
         COALESCE(ig.again_intent_raw, false)        AS again_intent_raw,
         a.askback,
         a.reply_ms,
         COALESCE(l.n, 0) AS llm_calls,
         (l.chatbot_turn_id IS NOT NULL) AS has_llm,
         CASE WHEN l.chatbot_turn_id IS NULL THEN 0::numeric WHEN l.ok THEN l.c END AS cost_usd   -- NULL = a call has no price
    FROM a CROSS JOIN p
    LEFT JOIN ref_gap rg ON rg.id = a.id
    LEFT JOIN intent_gap ig ON ig.id = a.id
    LEFT JOIN llm l ON l.chatbot_turn_id = a.turn_id::text
   WHERE a.wk >= p.week_from
)
SELECT wk, COALESCE(audience,'all') AS audience,
 count(*) AS asks, count(DISTINCT contact_respond_id) AS contacts,
 round(100.0*count(*) FILTER (WHERE nf_text)/count(*),1)    AS nf_text_pct,
 round(100.0*count(*) FILTER (WHERE nf_out)/count(*),1)     AS nf_outcome_pct,
 round(100.0*count(*) FILTER (WHERE missed)/count(*),1)     AS missed_pct,
 round(100.0*count(*) FILTER (WHERE clar_any)/count(*),1)   AS pickone_pct,
 round(100.0*count(*) FILTER (WHERE clar_out)/count(*),1)   AS clarified_outcome_pct,
 round(100.0*count(*) FILTER (WHERE again_ref)/nullif(count(*) FILTER (WHERE has_ref),0),1) AS again_ref_pct,
 round(100.0*count(*) FILTER (WHERE again_ref_raw)/nullif(count(*) FILTER (WHERE has_ref),0),1) AS again_ref_raw_pct,
 count(*) FILTER (WHERE again_ref_raw) AS raw_pairs, count(*) FILTER (WHERE again_ref_raw AND askback) AS raw_pairs_after_askback,
 count(*) FILTER (WHERE has_ref) AS again_ref_denominator,
 round(100.0*count(*) FILTER (WHERE again_intent)/count(*),1) AS again_intent_pct,
 round(100.0*count(*) FILTER (WHERE again_intent_raw)/count(*),1) AS again_intent_raw_pct,
 round(100.0*count(*) FILTER (WHERE nf_text AND again_intent)/nullif(count(*) FILTER (WHERE nf_text),0),1) AS again_after_nf_pct,
 round(100.0*count(*) FILTER (WHERE tech)/count(*),1)       AS technical_pct,
 round(100.0*count(*) FILTER (WHERE tech_delivery)/count(*),1) AS tech_delivery_pct,
 round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p50_s,
 round((percentile_cont(0.95) WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p95_s,
 round(avg(llm_calls),2) AS llm_calls_per_turn,
 round(avg(cost_usd),5)  AS usd_per_turn,
 round(100.0*count(*) FILTER (WHERE has_llm)/count(*),0) AS llm_rows_pct,
 round(100.0*count(cost_usd) FILTER (WHERE has_llm)/nullif(count(*) FILTER (WHERE has_llm),0),0) AS cost_priced_pct
  FROM b GROUP BY GROUPING SETS ((wk,audience),(wk)) ORDER BY wk, 2;

-- Statement 2: by topic (intent). Same CTEs, different final SELECT.
WITH p AS (
  SELECT DATE '2026-09-07' AS week_from,                       -- the ONLY parameter: first Monday shown (Malaysia time)
         ARRAY['check_stock','check_incoming','check_order','check_product_attachment',
               'check_promotion','check_product','(none)','check_po_cost'] AS top8  -- fixed topic list (top 8 by volume, 8 Sep to 12 Nov 2026)
),
a AS (   -- real WhatsApp asks: the real-traffic filter
  SELECT f.id, f.turn_id, f.contact_respond_id, f.audience, f.outcome, f.reply_ms, f.asked_at,
         date_trunc('week', f.asked_at AT TIME ZONE 'Asia/Kuala_Lumpur')::date AS wk,
         COALESCE(f.intent, '(none)') AS intent,
         t.stage, t.response #>> '{reply,text}' AS txt,
         (f.outcome = 'clarified' OR (t.response #>> '{reply,text}') ~* 'did you mean|how many units|which period|reply with the number|多少件') AS askback   -- the reply asked the customer something back
    FROM chatbot.chat_ask_facts f
    JOIN chatbot.turns t ON t.id = f.turn_id
    CROSS JOIN p
   WHERE t.is_test = false
     AND t.ingress NOT IN ('console','panel','agent')
     AND f.audience IN ('staff','dealer')
     AND f.outcome <> 'noise'
     AND f.asked_at >= (p.week_from::timestamp AT TIME ZONE 'Asia/Kuala_Lumpur') - interval '10 minutes'
),
refs AS (   -- products/brands the ask looked up or named (one row per ask and ref)
  SELECT i.ask_id, i.kind || ':' || i.ref_id AS ref
    FROM chatbot.chat_ask_items i
   WHERE i.role IN ('asked','named')
     AND i.ask_id IN (SELECT id FROM a)
   GROUP BY i.ask_id, i.kind, i.ref_id
),
ref_gap AS (   -- per ask: does the same contact ask the same intent about the same product/brand again within 10 minutes
  SELECT x.id, bool_or(x.nxt IS NOT NULL AND x.nxt - x.asked_at <= interval '10 minutes') AS again_ref_raw,
         bool_or(x.nxt IS NOT NULL AND x.nxt - x.asked_at <= interval '10 minutes' AND NOT x.askback) AS again_ref   -- fixed: the later message is not just the answer to the bot's own question
    FROM (SELECT a.id, a.asked_at, a.askback,
                 lead(a.asked_at) OVER (PARTITION BY a.contact_respond_id, a.intent, r.ref ORDER BY a.asked_at, a.id) AS nxt
            FROM a JOIN refs r ON r.ask_id = a.id) x
   GROUP BY x.id
),
intent_gap AS (   -- per ask: same contact asks the same intent again within 10 minutes (no product/brand needed)
  SELECT y.id, COALESCE(y.gap_ok, false) AS again_intent_raw, COALESCE(y.gap_ok AND NOT y.askback, false) AS again_intent
    FROM (SELECT a.id, a.askback,
                 (lead(a.asked_at) OVER (PARTITION BY a.contact_respond_id, a.intent ORDER BY a.asked_at, a.id)
                    - a.asked_at) <= interval '10 minutes' AS gap_ok
            FROM a) y
),
llm AS (   -- LLM calls and cost per turn (chatbot features only, view filters feature LIKE 'chatbot%')
  SELECT chatbot_turn_id, count(*) AS n, sum(cost_usd) AS c, bool_and(priced) AS ok
    FROM analytics_connector.llm_calls
   WHERE chatbot_turn_id IS NOT NULL
     AND created_at >= (SELECT week_from FROM p) - 1
   GROUP BY chatbot_turn_id
),
b AS (
  SELECT a.wk, a.audience, a.contact_respond_id,
         CASE WHEN a.intent = ANY (p.top8) THEN a.intent ELSE 'other' END AS topic,
         (a.txt ~* '(couldn.t find|could not find|not found|no record|cannot find|can.t find|unable to find|did not find|didn.t find)') AS nf_text,
         (a.outcome IN ('answered_empty','missed'))  AS nf_out,
         (a.outcome = 'missed')                      AS missed,
         (a.outcome = 'clarified')                   AS clar_out,
         (a.outcome = 'clarified'
          OR a.txt ~* 'did you mean|how many units|which period|reply with the number|多少件') AS clar_any,
         (a.outcome = 'technical')                   AS tech,
         (a.outcome = 'technical' AND a.stage = 'send_unconfirmed') AS tech_delivery,
         (rg.id IS NOT NULL)                         AS has_ref,
         COALESCE(rg.again_ref, false)               AS again_ref,
         COALESCE(rg.again_ref_raw, false)           AS again_ref_raw,
         COALESCE(ig.again_intent, false)            AS again_intent,
         COALESCE(ig.again_intent_raw, false)        AS again_intent_raw,
         a.askback,
         a.reply_ms,
         COALESCE(l.n, 0) AS llm_calls,
         (l.chatbot_turn_id IS NOT NULL) AS has_llm,
         CASE WHEN l.chatbot_turn_id IS NULL THEN 0::numeric WHEN l.ok THEN l.c END AS cost_usd   -- NULL = a call has no price
    FROM a CROSS JOIN p
    LEFT JOIN ref_gap rg ON rg.id = a.id
    LEFT JOIN intent_gap ig ON ig.id = a.id
    LEFT JOIN llm l ON l.chatbot_turn_id = a.turn_id::text
   WHERE a.wk >= p.week_from
)
SELECT wk, COALESCE(topic,'ALL') AS topic,
 count(*) AS asks, count(DISTINCT contact_respond_id) AS contacts,
 round(100.0*count(*) FILTER (WHERE nf_text)/count(*),1)    AS nf_text_pct,
 round(100.0*count(*) FILTER (WHERE nf_out)/count(*),1)     AS nf_outcome_pct,
 round(100.0*count(*) FILTER (WHERE missed)/count(*),1)     AS missed_pct,
 round(100.0*count(*) FILTER (WHERE clar_any)/count(*),1)   AS pickone_pct,
 round(100.0*count(*) FILTER (WHERE clar_out)/count(*),1)   AS clarified_outcome_pct,
 round(100.0*count(*) FILTER (WHERE again_ref)/nullif(count(*) FILTER (WHERE has_ref),0),1) AS again_ref_pct,
 round(100.0*count(*) FILTER (WHERE again_ref_raw)/nullif(count(*) FILTER (WHERE has_ref),0),1) AS again_ref_raw_pct,
 count(*) FILTER (WHERE again_ref_raw) AS raw_pairs, count(*) FILTER (WHERE again_ref_raw AND askback) AS raw_pairs_after_askback,
 count(*) FILTER (WHERE has_ref) AS again_ref_denominator,
 round(100.0*count(*) FILTER (WHERE again_intent)/count(*),1) AS again_intent_pct,
 round(100.0*count(*) FILTER (WHERE again_intent_raw)/count(*),1) AS again_intent_raw_pct,
 round(100.0*count(*) FILTER (WHERE nf_text AND again_intent)/nullif(count(*) FILTER (WHERE nf_text),0),1) AS again_after_nf_pct,
 round(100.0*count(*) FILTER (WHERE tech)/count(*),1)       AS technical_pct,
 round(100.0*count(*) FILTER (WHERE tech_delivery)/count(*),1) AS tech_delivery_pct,
 round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p50_s,
 round((percentile_cont(0.95) WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p95_s,
 round(avg(llm_calls),2) AS llm_calls_per_turn,
 round(avg(cost_usd),5)  AS usd_per_turn,
 round(100.0*count(*) FILTER (WHERE has_llm)/count(*),0) AS llm_rows_pct,
 round(100.0*count(cost_usd) FILTER (WHERE has_llm)/nullif(count(*) FILTER (WHERE has_llm),0),0) AS cost_priced_pct
  FROM b GROUP BY GROUPING SETS ((wk,topic),(wk)) ORDER BY wk, 2;
