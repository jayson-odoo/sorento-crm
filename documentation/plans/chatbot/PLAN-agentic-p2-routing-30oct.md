# PLAN: Agentic P2 - auto-route each staff message to the chat bot or the agent (Jev)

Status: building (owner 30 Oct ~17:10: "yeah let's go jev routing, I got api key already"). Slice 1 = key
storage, Jev client, router + state rules, console Auto mode, eval harness; red tests first. Gold-set eval runs
locally on crew's machine. Track: full (new vendor, settings migration). Lane AGENTIC-P2-JEV-ROUTER (PR #2010).

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
- Key: stored exactly like the other AI provider keys: a new `EncryptedText` column
  `ai_assistant_configs.jev_api_key_ciphertext` (pattern `app/models/ai_assistant.py:49-50`
  `gemini_api_key_ciphertext`), written by `AIAssistantConfigService.update` (pattern
  `app/services/ai_assistant_service.py:464-465`), returned only masked (`:481` `_mask_key`), entered on the AI
  assistant settings form (`system-management/ai-assistant/components/AIAssistantSettingsForm.tsx`). Fallback:
  env `JEV_API_KEY` when the column is empty (local runs and the eval). The key never appears in a prompt,
  log, trace, PR, chat or the repo.

### 4. Where it runs (console first)

A new console mode `Auto` beside `Bot` and `Agent`: the message goes to `POST /system/chatbot/console/auto-turn`,
which routes and then calls today's console turn or `run_agent_turn`. The reply shows a small route badge
(`Agent` / `Bot`, and `low confidence` / `daily cap` / `router failed` when that decided it). WhatsApp: a later
slice, behind `chatbot_router_enabled`.

### 5. Settings (one migration)

`system_settings.chatbot_router_enabled` (bool, off), `chatbot_router_min_score` (0.7, 0.5..0.95),
`chatbot_agent_daily_turns` (50, 0 = no cap); `respond_contacts.chatbot_agent_daily_turns` (int, null = the
global value). Edited on the existing Chatbot settings screen and the contact's Chatbot tab.

## Jev wire format (from the official SDK `typesafe-sdk` 0.7.5, read not run)

`POST https://api.typesafe.ai/v1/systemone` (`typesafe_sdk/_core/constants.py` `SYSTEM_ONE_PATH`;
`typesafe_sdk/constants.py` `DEFAULT_BASE_URL`), header `Authorization: Bearer <key>`
(`_core/transport.py:143`), JSON body (`_core/endpoints.py` `prepare_system_one`;
`_schemas/models.py` `SystemOneRequest`):

```json
{"model": "jev-latest", "state": "<message + last 3 exchanges>",
 "questions": {"route": {"type": "choice", "instructions": "<prompt label chatbot_router>",
                         "criteria": {"chat": "<...>", "agent": "<...>"}}}}
```

Response (`SystemOneResponse`): `{"model", "answers": {"route": {"type": "choice", "choice", "confidence",
"probabilities": {"chat", "agent"}}}, "usage": {"input_tokens", "output_tokens"}}`. Called with the backend's
`httpx` (already in `requirements.txt`); the SDK is not added (it pulls `httpx2`). Base URL overridable by env
`JEV_BASE_URL`; model by the prompt label's model field (default `jev-latest`).

## Build contract, slice 1 (tests import these names)

- `app/services/chatbot/router.py`: `RouteDecision(route: "chat"|"agent", score: float|None, reason: str,
  provider: str|None, ms: int, tokens_in: int)`; `decide(db, ctx, text, *, history, has_media, now=None, jev=None)
  -> RouteDecision` (state rules 2.1-2.4 then Jev; reasons `pending_action`, `open_question`, `media`,
  `daily_cap`, `jev`, `low_confidence`, `router_failed`); `jev_key(db) -> str|None` (column, then env).
- `app/services/chatbot/jev_client.py`: `choose(key, *, state, instructions, criteria, model="jev-latest",
  timeout=1.5, base_url=None) -> {"choice", "confidence", "probabilities", "input_tokens", "output_tokens"}`;
  raises `JevError` on any HTTP / shape failure (message never contains the key).
- Settings: `system_settings.chatbot_router_enabled`, `chatbot_router_min_score`, `chatbot_agent_daily_turns`;
  `respond_contacts.chatbot_agent_daily_turns`; `ai_assistant_configs.jev_api_key_ciphertext`. One migration
  `p2r_0001_jev_router` on main's current head.
- Route: `POST /api/v1/system/chatbot/console/auto-turn` `{contact_respond_id, text}` -> `{route: RouteDecision,
  turn: <console turn response> | <agent turn response>}`; same permission as `/agent/turn`.
- Daily cap counts today's (Malaysia day) agent turns of the contact (`chatbot.turns`, `ingress="agent"`).
- Usage row `feature="chatbot_router"` per Jev call.
- Eval harness `scripts/chatbot_eval/router_eval.py`: reads a JSONL gold file (`{id, text, previous_3, label,
  language}`), calls `jev_client.choose` with `JEV_API_KEY` from env (no DB needed), writes per-item results +
  a summary (agreement, missed-agent, wasted-agent, per language, p50 / p95 ms, tokens) to `--out`; `--limit`,
  `--threshold`; spend guard: stops when the summed input tokens would exceed `--max-input-tokens`.

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

## Review round 1 (30 Oct): reviewer NOT READY, security SECURE with should-fixes

J1. **Auto keeps the console conversation** (reviewer B1). `AutoTurnRequest` gains optional `session_vars` and
    `run_id` exactly as `ConsoleTurnRequest`; both pass through to `run_console_turn`. State rule 2 reads the open
    question from the supplied `session_vars` when present (else the stored row), through
    `session_state.five_keys(...)["open_question"]` and `turn/pending.tick(from_wire(...))`, so an expired
    escalation offer does not hold the contact on the bot. Note: business and roster questions never expire
    (R22), so once the bot asks one, messages go to the bot until the bot closes it; that is the rule as written.
J2. **Console Auto mode** (reviewer B2; the plan's slice 1): a third console tab `Auto` beside `Bot` and `Agent`.
    It keeps the bot side's `session_vars` / `run_id` like the Bot tab, calls `auto-turn`, shows the reply of the
    side chosen (agent replies with their steps / actions as in the Agent tab), and a small route badge per reply:
    `Agent` or `Bot`, plus `low confidence`, `daily cap`, `router failed`, `routing off` or `not eligible` when
    that decided it. Service -> hook -> UI, extractApiError, usable at 375 and 1280.
J3. **Off switch** (security should-fix 1; reviewer should-fix 4): `chatbot_router_enabled` gates Jev in the
    console: off -> the bot answers with reason `routing_off` and no Jev call. Default off; the settings switch
    stays, labelled for the console. WhatsApp routing remains a later slice.
J4. **Trim what Jev receives** (security should-fix 2): in `build_state` the new message is cut to 500
    characters, each earlier text and reply to 300, matching the gold-set extraction.
J5. **Eval survives a failed call** (reviewer should-fix 3): a `JevError` per item is recorded as route `chat`,
    reason `router_failed`, counted in the summary (`failures`); `results.jsonl` is written line by line; the
    summary also gives missed-agent and wasted-agent rates per language.
J6. **Key rotation** (reviewer should-fix 2): `scripts/reencrypt_field_secrets.py` `COLUMNS` gains
    `("ai_assistant_configs", "jev_api_key_ciphertext", True)`.
J7. **Reason name** (reviewer should-fix 5): a contact the agent cannot serve -> reason `not_eligible`, with the
    refusal's own reason in `detail`.
J8. **Model on the label** (reviewer should-fix 6): the `chatbot_router` label's model is used only when its
    provider is empty or `jev`; else `jev-latest`.
J9. **Key with a non-ASCII character** (security nit): headers are built inside the client's error handling, so
    any failure is a `JevError` without the key; the AI settings save refuses a non-ASCII Jev key.
J10. **Nits**: low confidence = P(agent) >= P(chat) but < min_score (a 0.5 tie is low confidence, as now, but
    defined against P(chat)); the three new settings columns join `_CHATBOT_COLUMN_DEFAULTS` so an explicit
    null saves the default instead of a 500.
