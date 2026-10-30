# PLAN: Agentic P2 - auto-route each staff message to the chat bot or the agent (Jev)

Status: plan filed; waiting on the owner (Jev access: his sign-up and the vendor data agreement) and on the
crew-labelled gold set. No product code until both are in. Track: full (routing on live turns later, a new
vendor, settings migration). Lane AGENTIC-P2-ROUTING.

Card: `CARD-agentic-p2-p3-30oct.md` Part 1 and the owner's answers (30 Oct ~11:10). Data: crew's dev queries
and `RESEARCH-JEV-parser-cost.md` (delivered in the crew report, not committed: public repo).

## Owner rulings this plan carries

- P2-Q1 (a): routing goes live in the console first; WhatsApp only after the gold-set eval passes.
- P2-Q2: Jev (TypeSafe AI) is the router ("fast and cost saving"). Behind one router interface. If Jev access or
  the eval fails: stop and file a crew-ask; no silent switch to another model.
- P2-Q3 (a): low confidence -> today's bot answers.
- P2-Q4 (b): crew labels the gold set, the owner spot-checks 20.
- P2-Q5 (a), configurable: 50 agent turns per contact per day by default, a global setting and a per-contact
  override.
- Semantic routing only: no regex or word-list guards. State decides two cases (below); Jev decides the rest.
- No silent fallback: an agent turn that fails says so; it is not re-run on the bot.

## Design

### 1. Who is routed

Only contacts with AI replies on, the Agent switch on and a linked active user (P1's `build_context` entry
rule). Everyone else never meets the router: no extra cost, today's bot as now.

### 2. State first, then Jev

In order, before any model call:
1. The contact has a pending agent proposal (`actions.pending_action`) -> agent (the reply may confirm it).
2. Today's bot has an open question waiting on this contact (the turn's `open_question`, `head/parser.py:1310`)
   -> bot.
3. The message carries media -> bot (the agent has no media tools).
4. The contact is at its daily agent-turn cap -> bot, `reason = daily_cap`.
5. Otherwise -> Jev.

### 3. The Jev call

One `Choice` question over two options, `chat` and `agent`, with the message plus the last 3 exchanges and
which side answered each (`last answered by: agent | bot`) as the state. The criteria text says what each
option means (card Part 1 rule 2: `chat` = a lookup today's bot's intents answer; `agent` = several reads
combined, a comparison, a why, an analysis over periods / agents / products, or a change to a record). Jev
returns a probability per option.

- `route = agent` when P(agent) >= `chatbot_router_min_score` (default 0.7), else `chat` with
  `reason = low_confidence` when P(agent) was the larger.
- Jev error / timeout (budget 1.5 s) -> `chat`, `reason = router_failed`.
- The criteria text is a prompt label (`chatbot_router`), published by the owner like every prompt.
- Interface: `router.route(db, ctx, text, history) -> RouteDecision(route, score, reason, provider, ms,
  tokens_in)`; Jev is the only implementation. Usage logged as `feature = "chatbot_router"`.
- Key: stored encrypted (`FIELD_ENCRYPTION_KEY`, `app/utils/field_encryption.py`) on the AI assistant
  config, beside the other provider keys; never in env files.

### 4. Where it runs (console first)

A new console mode `Auto` beside `Bot` and `Agent`: the message goes to `POST /system/chatbot/console/auto-turn`,
which routes and then calls today's console turn or `run_agent_turn`. The reply shows a small route badge
(`Agent` / `Bot`, and `low confidence` / `daily cap` / `router failed` when that decided it). WhatsApp: a later
slice, behind `chatbot_router_enabled`.

### 5. Settings (one migration)

`system_settings.chatbot_router_enabled` (bool, off), `chatbot_router_min_score` (0.7, 0.5..0.95),
`chatbot_agent_daily_turns` (50, 0 = no cap); `respond_contacts.chatbot_agent_daily_turns` (int, null = the
global value). Edited on the existing Chatbot settings screen and the contact's Chatbot tab.

## Gold set and eval

1. Crew runs the extraction SQL below on the dev DB (read-only), masks names / phones / customer names, and
   sends the result in a crew report (never committed).
2. Crew labels each message `chat` or `agent`; the owner spot-checks 20. A third for tuning the criteria text,
   the rest held out. Enriched until at least 40 `agent` items.
3. Each held-out message runs through the router (paid, capped USD 5); results recorded as cassettes.
4. Measured, per language (en / ms / zh / mixed, labelled by crew): agreement, missed-agent rate (labelled
   agent, routed chat), wasted-agent rate (labelled chat, routed agent), p95 router latency, cost per 1k from
   the usage log.
5. Pass bar: missed-agent <= 10%, wasted-agent <= 10%, p95 <= 1.5 s, and no language below 80% agreement.
   Fail -> crew-ask with the numbers; no model switch without the owner.

### Gold-set extraction SQL (crew runs it; read-only)

```sql
-- Staff messages (linked active user), last 60 days, with the previous 3 exchanges of the same contact.
-- Enrichment: every staff turn that ended clarify_menu or out_of_scope, plus a random sample of the rest.
WITH staff_turns AS (
  SELECT t.id, t.contact_respond_id, t.created_at, t.branch_kind,
         t.envelope #>> '{message,message,message,text}' AS text,
         t.response ->> 'reply_text' AS reply
  FROM chatbot.turns t
  WHERE NOT t.is_test
    AND t.created_at > now() - interval '60 days'
    AND coalesce(t.envelope #>> '{message,message,message,text}', '') <> ''
    AND EXISTS (
      SELECT 1 FROM respond_contacts c
      JOIN users u ON u.respond_contact_id = c.id AND u.status = 'ACTIVE' AND NOT u.is_trashed
      WHERE c.respond_io_id = t.contact_respond_id
    )
),
picked AS (
  (SELECT * FROM staff_turns WHERE branch_kind IN ('clarify_menu', 'out_of_scope'))
  UNION
  (SELECT * FROM staff_turns ORDER BY random() LIMIT 300)
)
SELECT p.id AS turn_id, p.created_at::date AS day, p.branch_kind, left(p.text, 500) AS text,
       (SELECT json_agg(json_build_object('text', left(h.text, 300), 'reply', left(h.reply, 300))
                        ORDER BY h.created_at)
          FROM (SELECT * FROM staff_turns h
                 WHERE h.contact_respond_id = p.contact_respond_id AND h.created_at < p.created_at
                 ORDER BY h.created_at DESC LIMIT 3) h) AS previous_3
FROM picked p
ORDER BY p.created_at;
```

## Tests (red first, when the slice starts)

State rules (pending proposal, open question, media, daily cap per contact and global) decide without a Jev
call; low confidence and router failure route to the bot with the reason; a non-eligible contact never calls
the router; the console Auto mode shows the route badge; settings bounds; cassette tests only in CI.

## Open

- The owner's Jev sign-up and data agreement (crew-ask on #2009, 30 Oct).
- The gold set (crew).
