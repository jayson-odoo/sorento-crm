# UAC: Agentic P2 auto-route (console first)

Plan: `PLAN-agentic-p2-route-30oct.md`. Each item is testable; ids are cited by tests.

## Routing decision (console text turns)

- **R1** A contact that is not eligible for the agent (no contact, AI replies off, Agent switch off, no active
  linked user) gets today's bot; the router makes no Jev call; `route.reason` starts `not_eligible:`.
- **R2** A console turn with media goes to today's bot and makes no Jev call.
- **R3** An eligible contact with a pending (unexpired, `proposed`) agent proposal goes to the agent with reason
  `pending_action`, no Jev call.
- **R4** An eligible contact whose bot session holds an open question goes to the bot with reason
  `open_question`, no Jev call. The console's `session_vars` decide when sent (`{}` = reset = no open question);
  `null` reads the stored row.
- **R5** An eligible contact at or over the daily agent-turn cap goes to the bot with reason `daily_cap`, no Jev
  call. Cap = the contact's own value when set, else the global setting; 0 = no cap. The day is the business day
  (MYT); every agent turn of that contact that day counts.
- **R6** No Jev key in AI settings -> bot, reason `router_failed:no_key`, no HTTP call. The key is never read from
  the environment.
- **R7** Jev timeout (> 1.5 s), HTTP error, 429 or an answer without a valid `route` choice -> bot, reason
  `router_failed:<kind>`. The turn still answers.
- **R8** Jev confidence below `chatbot_router_min_score` -> bot, reason `low_confidence`, score recorded.
- **R9** Otherwise the side is Jev's choice, reason `classified`, with score, model and ms recorded.
- **R10** The Jev request carries the message, the last 3 exchanges (bot replies cut to 300 chars) each marked
  `answered_by: bot|agent`, and `last_answered_by`; the question's instructions and criteria come from the
  `chatbot_router` production prompt and the model from that label.

## Running the chosen side

- **S1** Side = chat: `engine.run_turn` runs exactly as before this lane (same envelope, same reply).
- **S2** Side = agent: `run_agent_turn` runs for the contact with the operator id; the console response carries
  the agent reply, status and pending action as the Agent tab shows them today.
- **S3** Agent chosen and it fails or is busy: the reply says so; today's bot is NOT run for that turn.
- **S4** Routed agent turns count toward the operator's agent rate limit (30 per 10 minutes).
- **S5** WhatsApp, n8n `/external/chat/turn` and inbox-queue turns are not routed (no Jev call, no change).

## Visibility and cost

- **V1** Every console text turn's response carries `route: {side, reason, score, model, ms}` and the turn trace
  holds the same record.
- **V2** Each Jev call writes one usage row, feature `chatbot_router`, provider `typesafe`, the model, input and
  output tokens, ms, tied to the turn id. A price row for the Jev model exists (0.042 per 1M input, output 0).
- **V3** The console shows, on each answered message, which side answered (Agent or Chat), and on hover/tap the
  reason and score. Readable at 375 px and 1280 px.

## Settings and key

- **K1** AI assistant settings accept a TypeSafe (Jev) API key; it is stored encrypted, returned masked, a blank
  save keeps the stored key, and it is in the re-encrypt script's list.
- **K2** System settings return and save `chatbot_router_min_score` (0.5..0.95, default 0.7) and
  `chatbot_agent_daily_turns` (>= 0, default 50); out-of-range values are rejected with 422.
- **K3** The contact screen sets a per-contact daily cap (blank = use the global value, clearable) next to the
  Agent switch, which reads "Agent mode (auto)".
- **K4** The P1 agent entry (`build_context`) refuses with exactly the same reasons as before (eligibility refactor
  parity).

## Eval gate (before product code)

- **E1** Gold set >= 60 real masked messages, EN / MS / ZH, staff and dealer, crew-labelled; 20 marked for the
  owner's spot-check.
- **E2** Table for Jev, parser-as-router and Flash-Lite: agreement, missed-agent, wasted-agent, per language,
  p50/p95 latency, cost per 1,000. Pass: missed-agent <= 10%, wasted-agent <= 10%, Jev p95 <= 1.5 s.
- **E3** Jev below the bar on MS or ZH -> lane stops and files one ask with the numbers.
