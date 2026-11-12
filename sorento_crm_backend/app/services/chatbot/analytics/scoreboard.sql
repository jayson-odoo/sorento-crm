-- Chatbot live weekly scoreboard (CHATBOT-STEP-A, A1). Read-only SELECTs. Run on the dev copy or on a read replica.
-- Re-run next week UNCHANGED: the only parameter is p.week_from (first Monday shown, Malaysia time) in the CTE below.
-- Two statements, each ends in ';': (1) overall by week and audience, (2) by week and topic (intent).
-- Each took 2 to 5 seconds on the dev copy of prod 12 Nov (limit 30 s). If it nears the limit, raise week_from.
-- Lives in the repo since CHATBOT-SCOREBOARD (documentation/plans/chatbot/PLAN-chatbot-scoreboard-12nov.md);
-- tests/chatbot/test_chatbot_scoreboard_sql.py runs both statements on fake rows.
--
-- Definitions changed by CHATBOT-SCOREBOARD (every other column is as before):
-- * Outcome columns read chat_ask_facts.outcome, stamped by analytics/outcome.py. The quantity question
--   ("How many units of X?") and pick-one menus are `clarified` there, read from the turn's `state` event,
--   so they are not couldn't-find (nf_outcome) or answered. "Couldn't find X. Did you mean Y?" stays a miss.
--   Facts written before that rule need `scripts/chat_facts_sweep.py --since <day> --rebuild` once; and
--   turns before the `state` event existed (before the week of 5 Oct 2026) keep the old outcome.
-- * stock_nf_pct: check_stock asks ending answered_empty or missed / check_stock asks.
--   stock_dead_end_pct: the same asks whose reply offered no code (no product_pick question) / check_stock asks.
-- * technical_pct = tech_engine_pct + tech_delivery_pct. Engine: the turn failed at any stage but
--   send_unconfirmed. Delivery: send_unconfirmed AND no outgoing chat_histories row for the turn shows the
--   reply went (a row whose delivery_status is failed or not_sent does not count as went).
-- * weekly_line (statement 1, 'all' row): the owner's one line, e.g.
--   "wk 09/11/2026: stock not-found 5.0% (dead-end 2.1%), median 7.7 s, dealer asked-again 10.2%, technical 1.5%".
-- Statement 1: overall.
WITH p AS (
  SELECT DATE '2026-09-07' AS week_from,                       -- the ONLY parameter: first Monday shown (Malaysia time)
         ARRAY['check_stock','check_incoming','check_order','check_product_attachment',
               'check_promotion','check_product','(none)','check_po_cost'] AS top8  -- fixed topic list (top 8 by volume, 8 Sep to 12 Nov 2026)
),
went_out AS (   -- turns whose reply went out: an outgoing chat row for the turn that did not fail (chat_histories.chatbot_turn_id, delivery_status)
  SELECT DISTINCT h.chatbot_turn_id
    FROM public.chat_histories h
   WHERE h.chatbot_turn_id IS NOT NULL
     AND h.type = 'outgoing'
     AND COALESCE(h.delivery_status, '') NOT IN ('failed', 'not_sent')
),
a AS (   -- real WhatsApp asks: the real-traffic filter
  SELECT f.id, f.turn_id, f.contact_respond_id, f.audience, f.outcome, f.reply_ms, f.asked_at,
         date_trunc('week', f.asked_at AT TIME ZONE 'Asia/Kuala_Lumpur')::date AS wk,
         COALESCE(f.intent, '(none)') AS intent,
         t.stage, t.response #>> '{reply,text}' AS txt,
         (f.outcome = 'clarified' OR (t.response #>> '{reply,text}') ~* 'did you mean|how many units|which period|reply with the number|多少件') AS askback,   -- the reply asked the customer something back
         (SELECT r #>> '{facts,asking}'
            FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.trace) = 'array' THEN t.trace END) r
           WHERE r ->> 'stage' = 'replied' AND r ->> 'kind' IS NULL LIMIT 1) AS asking,   -- the question the reply ended in (product_pick = a code offered), NULL = none
         (w.chatbot_turn_id IS NOT NULL) AS reply_out
    FROM chatbot.chat_ask_facts f
    JOIN chatbot.turns t ON t.id = f.turn_id
    LEFT JOIN went_out w ON w.chatbot_turn_id = t.id::text
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
         (a.outcome = 'technical' AND (a.stage IS DISTINCT FROM 'send_unconfirmed' OR NOT a.reply_out)) AS tech,   -- engine + delivery
         (a.outcome = 'technical' AND a.stage IS DISTINCT FROM 'send_unconfirmed') AS tech_engine,
         (a.outcome = 'technical' AND a.stage = 'send_unconfirmed' AND NOT a.reply_out) AS tech_delivery,   -- send not confirmed AND no outgoing row shows it went
         (a.intent = 'check_stock')                  AS stock,
         (a.intent = 'check_stock' AND a.outcome IN ('answered_empty','missed')) AS stock_nf,
         (a.intent = 'check_stock' AND a.outcome IN ('answered_empty','missed')
          AND a.asking IS DISTINCT FROM 'product_pick') AS stock_dead_end,   -- couldn't find and no code offered
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
SELECT s.*,
       CASE WHEN s.audience = 'all' THEN format(   -- the owner's one weekly line, on the 'all' row only; "-" = cannot be worked out
         'wk %s: stock not-found %s (dead-end %s), median %s, dealer asked-again %s, technical %s',
         to_char(s.wk, 'DD/MM/YYYY'),
         COALESCE(s.stock_nf_pct || '%', '-'),
         COALESCE(s.stock_dead_end_pct || '%', '-'),
         COALESCE(s.p50_s || ' s', '-'),
         COALESCE(max(s.again_ref_pct) FILTER (WHERE s.audience = 'dealer') OVER (PARTITION BY s.wk) || '%', '-'),
         COALESCE(s.technical_pct || '%', '-')) END AS weekly_line
  FROM (
SELECT wk, COALESCE(audience,'all') AS audience,
 count(*) AS asks, count(DISTINCT contact_respond_id) AS contacts,
 round(100.0*count(*) FILTER (WHERE stock_nf)/nullif(count(*) FILTER (WHERE stock),0),1) AS stock_nf_pct,
 round(100.0*count(*) FILTER (WHERE stock_dead_end)/nullif(count(*) FILTER (WHERE stock),0),1) AS stock_dead_end_pct,
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
 round(100.0*count(*) FILTER (WHERE tech_engine)/count(*),1) AS tech_engine_pct,
 round(100.0*count(*) FILTER (WHERE tech_delivery)/count(*),1) AS tech_delivery_pct,
 round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p50_s,
 round((percentile_cont(0.95) WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p95_s,
 round(avg(llm_calls),2) AS llm_calls_per_turn,
 round(avg(cost_usd),5)  AS usd_per_turn,
 round(100.0*count(*) FILTER (WHERE has_llm)/count(*),0) AS llm_rows_pct,
 round(100.0*count(cost_usd) FILTER (WHERE has_llm)/nullif(count(*) FILTER (WHERE has_llm),0),0) AS cost_priced_pct
  FROM b GROUP BY GROUPING SETS ((wk,audience),(wk))
) s ORDER BY s.wk, s.audience;

-- Statement 2: by topic (intent). Same CTEs, different final SELECT.
WITH p AS (
  SELECT DATE '2026-09-07' AS week_from,                       -- the ONLY parameter: first Monday shown (Malaysia time)
         ARRAY['check_stock','check_incoming','check_order','check_product_attachment',
               'check_promotion','check_product','(none)','check_po_cost'] AS top8  -- fixed topic list (top 8 by volume, 8 Sep to 12 Nov 2026)
),
went_out AS (   -- turns whose reply went out: an outgoing chat row for the turn that did not fail (chat_histories.chatbot_turn_id, delivery_status)
  SELECT DISTINCT h.chatbot_turn_id
    FROM public.chat_histories h
   WHERE h.chatbot_turn_id IS NOT NULL
     AND h.type = 'outgoing'
     AND COALESCE(h.delivery_status, '') NOT IN ('failed', 'not_sent')
),
a AS (   -- real WhatsApp asks: the real-traffic filter
  SELECT f.id, f.turn_id, f.contact_respond_id, f.audience, f.outcome, f.reply_ms, f.asked_at,
         date_trunc('week', f.asked_at AT TIME ZONE 'Asia/Kuala_Lumpur')::date AS wk,
         COALESCE(f.intent, '(none)') AS intent,
         t.stage, t.response #>> '{reply,text}' AS txt,
         (f.outcome = 'clarified' OR (t.response #>> '{reply,text}') ~* 'did you mean|how many units|which period|reply with the number|多少件') AS askback,   -- the reply asked the customer something back
         (SELECT r #>> '{facts,asking}'
            FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.trace) = 'array' THEN t.trace END) r
           WHERE r ->> 'stage' = 'replied' AND r ->> 'kind' IS NULL LIMIT 1) AS asking,   -- the question the reply ended in (product_pick = a code offered), NULL = none
         (w.chatbot_turn_id IS NOT NULL) AS reply_out
    FROM chatbot.chat_ask_facts f
    JOIN chatbot.turns t ON t.id = f.turn_id
    LEFT JOIN went_out w ON w.chatbot_turn_id = t.id::text
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
         (a.outcome = 'technical' AND (a.stage IS DISTINCT FROM 'send_unconfirmed' OR NOT a.reply_out)) AS tech,   -- engine + delivery
         (a.outcome = 'technical' AND a.stage IS DISTINCT FROM 'send_unconfirmed') AS tech_engine,
         (a.outcome = 'technical' AND a.stage = 'send_unconfirmed' AND NOT a.reply_out) AS tech_delivery,   -- send not confirmed AND no outgoing row shows it went
         (a.intent = 'check_stock')                  AS stock,
         (a.intent = 'check_stock' AND a.outcome IN ('answered_empty','missed')) AS stock_nf,
         (a.intent = 'check_stock' AND a.outcome IN ('answered_empty','missed')
          AND a.asking IS DISTINCT FROM 'product_pick') AS stock_dead_end,   -- couldn't find and no code offered
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
 round(100.0*count(*) FILTER (WHERE tech_engine)/count(*),1) AS tech_engine_pct,
 round(100.0*count(*) FILTER (WHERE tech_delivery)/count(*),1) AS tech_delivery_pct,
 round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p50_s,
 round((percentile_cont(0.95) WITHIN GROUP (ORDER BY reply_ms)/1000)::numeric,1) AS p95_s,
 round(avg(llm_calls),2) AS llm_calls_per_turn,
 round(avg(cost_usd),5)  AS usd_per_turn,
 round(100.0*count(*) FILTER (WHERE has_llm)/count(*),0) AS llm_rows_pct,
 round(100.0*count(cost_usd) FILTER (WHERE has_llm)/nullif(count(*) FILTER (WHERE has_llm),0),0) AS cost_priced_pct
  FROM b GROUP BY GROUPING SETS ((wk,topic),(wk)) ORDER BY wk, 2;
