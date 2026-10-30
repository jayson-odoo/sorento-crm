# PLAN: Agentic P2, automatic per-message routing (chat bot or agent), console first

Status: Review (31 Oct 2026), PR #2025; review fix round in progress. Track: full pipeline, Size L (migration, new
external vendor call, AI key surface). Mockup v1 approved by the owner 30 Oct 23:13.
Lane AGENTIC-P2-ROUTE, branch `crew/agentic-p2-route`. UAC: `agentic-p2-route-acceptance-criteria.md`.
Card (owner rulings, binding): `CARD-agentic-p2-p3-30oct.md` Part 1 and the answers table at its top.

## Rulings this plan builds on (do not re-ask)

- P2-Q1 (a): routing goes live in the **console** only. WhatsApp turns are not routed in this lane.
- P2-Q2: the router is **Jev** (TypeSafe AI, typed `choice` + `confidence`), owner 17:10 "let's go jev routing".
  If Jev fails Malay or Chinese on the gold set: stop and ask; no silent switch to Flash-Lite.
- P2-Q3 (a): low confidence -> today's bot. P2-Q4 (b): crew labels the gold set, owner spot-checks 20.
- P2-Q5 (a): 50 agent turns per contact per day, configurable (global setting + per-contact override).
- P3-Q1 principle (6a): give the model general tools, no hard-coded per-request flows; semantic routing only,
  no word lists or regex on the message.
- No silent fallback between agent and bot once the agent was chosen (card rule 6).

## Architecture

**Layer.** One new backend service module `app/services/chatbot/router.py` (pure decision, no HTTP of its own)
plus a thin vendor client `app/services/chatbot/jev_client.py` (one POST, timeout, usage). The console turn
service calls the router once per text turn and then runs exactly one of the two EXISTING paths:
`engine.run_turn` (today's bot, unchanged) or `agent.loop.run_agent_turn` (P1 agent, unchanged). No parallel
pipeline, no new turn table.

**Where it plugs in.** `run_console_turn` (`sorento_crm_backend/app/services/chatbot/console_service.py:450`),
after the media branch (`:474-484`, media always stays on the bot) and before `_borrow_envelope` (`:486`).
WhatsApp entries (`inbox_queue.py:857`, `api/v1/external/chat.py:226/242`, `tasks/chat_turns.py:33`) are NOT
touched; they all end in `engine.run_turn` (`engine.py:2933`) as today.

**Shared mechanism, not a copy.** The agent entry checks (`agent/access.py:68-84`: contact exists,
`chatbot_allowed`, `chatbot_agent_enabled`, active linked user) move into one pure function
`agent_eligibility(db, contact_respond_id) -> str | None` (refusal reason or None) in `agent/access.py`;
`build_context` calls it and raises `AgentRefused(reason)` exactly as today. The router calls the same function,
so "who may reach the agent" has one definition. `build_context` is not called by the router (it sets scopes,
`access.py:97,108`).

### Router contract

```
decide_route(db, *, contact_respond_id, text, session_vars, has_media) -> RouteDecision
RouteDecision = {side: "chat" | "agent", reason: str, score: float | None,
                 model: str | None, ms: int | None, input_tokens: int | None}
```

Order (first match wins; only step 7 calls Jev):

| # | Condition (stored state, never wording) | side | reason |
|---|---|---|---|
| 1 | `agent_eligibility` returns a reason (switch off, AI off, no linked user, ...) | chat | `not_eligible:<reason>` |
| 2 | message carries media | chat | `media` (already true by position, recorded for the trace) |
| 3 | `agent/actions.py:85 pending_action(db, contact)` returns a proposal | agent | `pending_action` |
| 4 | today's bot has an open question: `session_state.pending_of` (`session_state.py:244`) over the console's `session_vars` when given (`None` = stored row, `{}` = reset; `schemas/chatbot_turn.py:139-144`) | chat | `open_question` |
| 5 | agent turns today for this contact >= cap (per-contact override, else global; 0 = no cap) | chat | `daily_cap` |
| 6 | no Jev key in AI settings, or no `chatbot_router` production prompt | chat | `router_failed:no_key` / `router_failed:no_prompt` |
| 7 | Jev call: timeout / HTTP error / 429 / malformed answer | chat | `router_failed:<kind>` |
| 8 | Jev `confidence` < `chatbot_router_min_score` | chat | `low_confidence` (score kept) |
| 9 | otherwise | Jev's `choice` | `classified` |

**Classifier input (Jev `state`).** `{latest_message, recent_exchanges: last 3 [{user, reply, answered_by:
bot|agent}], last_answered_by}`; every reply (bot and agent) truncated to 300 chars. One `choice` question `route` with criteria `chat` and
`agent`; instructions + criteria are the content of a new prompt key `chatbot_router` (owner publishes prompts;
the `production` label's `model` pins the Jev model, e.g. `jev-1.14.0`). Criteria wording is semantic (what each
side is for: single lookups the bot's intents answer vs several reads combined, comparisons, "why", analysis
over periods/agents/products, or a change to a record). Stickiness is decided by Jev from `last_answered_by`.

**Threshold.** `chatbot_router_min_score`, default 0.7 (range 0.5..0.95); the default is confirmed or moved on
the gold set's tuning third before the held-out run (eval records both `confidence` and `probabilities`).

**Timeout and budget.** Jev call timeout 1.5 s (code constant, the card's p95 bar; a setting only if the eval
shows a need). Jev price: USD 0.042 per 1M input tokens, output free (docs.typesafe.ai/models). State ~600-1,500
tokens -> about USD 0.00006 per routed message, ~USD 0.06 per 1,000. Latency target p95 <= 1.5 s.

**Usage + trace.** Every Jev call logs one `ai_assistant_usage_logs` row, `feature = "chatbot_router"`
(`chatbot/usage.py:67 record_turn_llm_usage`), provider `typesafe`, model, tokens, ms, tied to the turn. Price row
`jev-1.14.0` (0.042 / 0 / 0) seeded like `gemprice_0001_gemini_prices.py`. The decision is added to the turn's
trace (`TurnTrace.add("route", ...)`, `trace.py:186`) and returned on `ConsoleTurnResponse`
(`schemas/chatbot_turn.py:161`) as `route: {side, reason, score, model, ms}`.

**Agent side in the console.** When side = agent, `run_console_turn` calls `run_agent_turn(..., operator_user_id)`
and maps `AgentTurnResult` (`loop.py:543`) into the console response (`agent` block, as `AgentTurnResponse`
`schemas/chatbot_turn.py:262` already shapes it). The operator rate limit (`chatbot.py:721`, 30 per 10 min) applies
to routed agent turns too (shared helper, not a copy). `AgentBusy` -> the reply says the agent is busy (no bot
re-run). An agent failure says the agent could not answer (card rule 6).

### How the switch becomes auto, override and fallback

- `respond_contacts.chatbot_agent_enabled` (`models/access.py:352`) keeps name and default (off); meaning becomes
  "this contact's messages may be routed to the agent". Contact Details label: "Agent mode (auto)".
- Console: the Bot tab sends text through the router (auto); the existing Agent tab stays as the **forced-agent
  override** for testing. Turning the contact switch off is the forced-bot override.
- Fallback to today's bot only BEFORE the agent is chosen (rules 1-8). After it is chosen, never.

### Settings and key (one migration)

- `system_settings`: `chatbot_router_min_score` (float, 0.7), `chatbot_agent_daily_turns` (int, 50, 0 = no cap).
  Added to the manual dict builder (`api/v1/user_management/settings.py:482-485`) and the update schema
  (`:176-179`); edited on the P1 "Agent budgets" card (`user-management/settings/chatbot-media/page.tsx:390`).
- `respond_contacts.chatbot_agent_daily_turns` (nullable int; null = global). Set on the contact screen next to
  the Agent switch.
- `ai_assistant_configs.typesafe_api_key_ciphertext` (`EncryptedText`, `field_encryption.py:158`), copying the
  Gemini key path (`361_ai_config_gemini_key.py`): model, schema in + masked, `update` / `to_response_dict`,
  a resolver with **no env fallback**, re-encrypt list (`scripts/reencrypt_field_secrets.py:68`), FE input on
  `AIAssistantSettingsForm.tsx`. Not added to `get_provider` / `PROVIDER_OPTIONS` (Jev is not a chat model).
- Prompt key `chatbot_router` (`ai_prompt_registry.py` `PromptKeySpec`) + v1 + `production` label seeded if
  missing (pattern `eem_0003_span_meaning.py:35-54`); label provider `typesafe`, model `jev-1.14.0`.
- No `chatbot_router_enabled` flag in this lane: console routing is on for every eligible contact once a key is
  set. Trigger to add it: the WhatsApp go-live lane.

## Eval (before product code)

Gold set (crew-only, never committed; `crew/state/eval/agentic-p2/`): >= 60 real masked messages, EN / MS / ZH,
staff and dealer, each with its previous exchanges, crew-labelled chat | agent; tuning third + held-out rest.
Arms: Jev (direct, local key), today's parser as a router (recorded parser output, zero new spend), Gemini
Flash-Lite with the same criteria as a JSON prompt (org key, ledger before/after, cap USD 0.25). Table: agreement,
missed-agent, wasted-agent, per language, p50/p95 latency, cost per 1,000. Pass bar (card): missed-agent <= 10%,
wasted-agent <= 10%, p95 <= 1.5 s. Jev failing MS or ZH -> stop, one ask with the numbers.

## Tickets (one lane, one PR)

1. EVAL: gold set + 3-arm table -> crew report (gate for 2-5).
2. MOCK: static HTML for the 4 UI touches (console route chip, Agent budgets fields, contact cap + label, Jev key
   input) -> `documentation/mockups/agentic-p2-route/index.html`, crew ask, build after approval.
3. BE red tests (tester): router order table, Jev client failure kinds, settings dict, key masking/no env
   fallback, console response `route`, usage row, daily cap count, eligibility refactor parity.
4. BE (coder): migration, `jev_client.py`, `router.py`, eligibility refactor, console wiring, seeds.
5. FE (coder): the 4 UI touches; vitest for the route chip and settings fields.
6. Review: reviewer + security-reviewer (new vendor key + external call + RBAC-adjacent eligibility), console
   browser pass 1280 + 375, hand test script, `--handtest`.

## Eval result (31 Oct, crew-only gold set; aggregates only)

Frozen criteria v2, held-out staff rows n=120: Jev @0.7 agree 92%, missed-agent 15%, wasted-agent 5%, p95 389 ms,
~USD 0.03 per 1,000; Flash-Lite agree 91%, missed 5%, wasted 11%, p95 1,262 ms, ~USD 0.20 per 1,000; parser as
router misses every agent ask. No language failure (Jev staff EN 91% / MS 90% / ZH 94%). Pass-bar decision filed
with crew (missed-agent above the proposed 10%).

## Not in this lane

WhatsApp routing (after the eval passes, own lane with `chatbot_router_enabled` and a total deadline on the
Jev call: httpx's 1.5 s applies per phase, not to the whole call); agent media tools; parser cost
work with Jev (separate experiment per the research report).
