-- =====================================================================
-- PROD FOLLOW-UP PROBES — run these to size what's usable before the deck.
-- Results decide which response-time method + topic source you present.
-- =====================================================================

-- P1. turn_id coverage: is 940 a big or small slice of July incoming?
SELECT type,
       count(*)                              july_total,
       count(turn_id)                        with_turn_id,
       count(respond_ts)                     with_respond_ts,
       round(100.0*count(turn_id)/nullif(count(*),0),1)   pct_turn_id,
       round(100.0*count(respond_ts)/nullif(count(*),0),1) pct_respond_ts
FROM chat_histories
WHERE sent_at >= '2026-07-01'
GROUP BY type;

-- P2. respond_ts pairing viability: how many incoming get a paired outgoing < 10 min?
WITH resp AS (
  SELECT i.id,
         (SELECT min(o.respond_ts) FROM chat_histories o
           WHERE o.contact_id=i.contact_id AND o.type='outgoing'
             AND o.respond_ts > i.respond_ts
             AND o.respond_ts < i.respond_ts + interval '10 min') AS out_ts
  FROM chat_histories i
  WHERE i.type='incoming' AND i.sent_at >= '2026-07-01' AND i.respond_ts IS NOT NULL
)
SELECT count(*) incoming_with_respond_ts,
       count(out_ts) paired,
       count(*)-count(out_ts) no_reply_10min
FROM resp;

-- P3. state_trace as an ALTERNATE topic source (parser domain_hint per turn).
--     If this is populated, it's a cleaner topic than message-text keywords.
SELECT count(*)                                                          july_incoming,
       count(state_trace)                                               with_state_trace,
       count(state_trace->'parser_applied'->>'domain_hint')             with_domain_hint
FROM chat_histories
WHERE type='incoming' AND sent_at >= '2026-07-01';

-- P3b. If domain_hint exists, see its distribution:
SELECT state_trace->'parser_applied'->>'domain_hint' AS domain_hint, count(*)
FROM chat_histories
WHERE type='incoming' AND sent_at >= '2026-07-01'
  AND state_trace->'parser_applied'->>'domain_hint' IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;

-- P4. Escalation reality check: of ALL conversation SLA rows, how many have
--     the timings the founder wants? (expect low — 6 responded earlier.)
SELECT count(*) total,
       count(*) FILTER (WHERE initiated_at >= '2026-07-01') july,
       count(*) FILTER (WHERE is_responded) responded,
       count(response_time) has_response_time,
       count(*) FILTER (WHERE is_resolved) resolved,
       count(resolution_duration) has_resolution_time
FROM conversation_sla_tracking
WHERE source_entity_type IS NULL OR source_entity_type='conversation';

-- P5. Does n8n_chat_histories carry any intent/domain in its jsonb? (last-ditch topic source)
SELECT jsonb_pretty(message) FROM n8n_chat_histories
ORDER BY id DESC LIMIT 3;
