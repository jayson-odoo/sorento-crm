-- AGENTIC-UNIFY card: read-only facts crew runs on the shared dev DB. Results stay in the crew
-- report and are never committed (public repo). Mask person names in any free text before relaying.
-- Run with PGOPTIONS='-c default_transaction_read_only=on'.
\pset pager off

-- 1. Who uses the panel, and how many could enter the contact-keyed pipeline as it stands?
with panel as (
  select c.user_id, count(*) filter (where m.role = 'user') as user_msgs
  from ai_assistant_conversations c
  join ai_assistant_messages m on m.conversation_id = c.id
  group by 1
)
select count(*)                                                     as panel_users,
       sum(p.user_msgs)                                             as panel_user_msgs,
       count(*) filter (where u.respond_contact_id is not null)     as linked_to_contact,
       count(*) filter (where rc.chatbot_allowed)                   as chatbot_allowed,
       count(*) filter (where rc.chatbot_agent_enabled)             as agent_enabled,
       sum(p.user_msgs) filter (where u.respond_contact_id is null) as msgs_from_unlinked
from panel p
join users u on u.id = p.user_id
left join respond_contacts rc on rc.id = u.respond_contact_id;

-- 2. Shape of panel turns.
select count(*) filter (where role = 'user')                                                as user_msgs,
       count(*) filter (where role = 'assistant' and metadata_json ? 'pending_confirmation') as write_confirm_cards,
       count(*) filter (where role = 'assistant' and metadata_json ? 'clarify')              as clarify_cards,
       max(created_at)                                                                       as newest
from ai_assistant_messages;

-- 3. Latency and token cost per turn, panel vs agent vs router.
select feature,
       count(*)                                                            as calls,
       percentile_cont(0.5)  within group (order by response_time_ms)      as p50_ms,
       percentile_cont(0.95) within group (order by response_time_ms)      as p95_ms,
       round(avg(prompt_tokens))                                           as avg_in,
       round(avg(completion_tokens))                                       as avg_out
from ai_assistant_usage_logs
where feature in ('ai_assistant', 'chatbot_agent', 'chatbot_router')
group by 1;

-- 4. Agent turns per contact per busiest day, to size the daily cap per user.
select max(n) as busiest_contact_day, round(avg(n), 1) as avg_contact_day
from (
  select contact_respond_id, date(created_at) as d, count(*) as n
  from chatbot.turns
  where ingress = 'agent'
  group by 1, 2
) t;

-- 5. Real panel example candidates: one stock ask, one sales report ask, one write card.
select 'stock' as kind, left(content, 200) as text, created_at
from ai_assistant_messages
where role = 'user' and content ilike any (array['%stock%', '%balance%', '%available%'])
order by created_at desc limit 5;

select 'report' as kind, left(content, 200) as text, created_at
from ai_assistant_messages
where role = 'user' and content ilike any (array['%sales%', '%report%', '%top %', '%revenue%'])
order by created_at desc limit 5;

select 'write' as kind,
       left(a.content, 200) as assistant_text,
       left(a.metadata_json #>> '{pending_confirmation,tool}', 60) as tool,
       a.created_at
from ai_assistant_messages a
where a.role = 'assistant' and a.metadata_json ? 'pending_confirmation'
order by a.created_at desc limit 5;
