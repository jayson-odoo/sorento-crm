# PLAN: the agent's reasoning, visible in the Chatbot Console

Status: in review (small fix track: no migration, no auth/RBAC change, no new ingest surface). Built, tests green,
security reviewer SECURE, browser pass at 1280 + 375 PASS; waiting on the code reviewer and the owner hand test.
Lane: AGENTIC-REASONING-VIS
Owner, 30 Oct 23:13: "I need our reasoning to be more visible ... I need to see the reasoning in
the console so at least I know agent's thought process."

## Evidence (what main does today)

- Model: `chatbot_agent` runs on the `production` label of `ai_prompt_labels` when one is set
  (`app/services/ai_prompt_registry.py` `agent_model` / `agent_reasoning_effort`), else
  `gemini` / `gemini-3.5-flash` with no effort (`app/services/chatbot/agent/loop.py` DEFAULT_PROVIDER,
  DEFAULT_MODEL). No migration seeds a label row for `chatbot_agent`. The sandbox cannot read the
  dev or prod DB, so whether the owner set a label there is not verified here.
- Reasoning is ON only with an effort on the label: every Gemini 2.5+ call gets a `thinkingConfig`
  (`app/services/llm_provider.py` `_gemini_thinking`), but with no effort a flash 3.x model gets
  `thinkingBudget: 1` (`_gemini_thinking_budget`), so it barely thinks; Claude thinks only when an
  effort is set. To see real Thinking, set Reasoning effort (low or medium) on the `chatbot_agent`
  production label in Prompts (settings, no code; owner call on #2022).
- The thought TEXT is not returned: no request sets `includeThoughts`, so Gemini answers with
  `thoughtSignature` parts only (kept as `ChatResult.continuation` for replay, #1979). Anthropic does
  return `thinking` blocks, but they live only in `continuation` and are dropped after the turn.
- Stored today: only the count, `reasoning_tokens` on each `agent_round` trace event.
- Trap: a Gemini part with `thought: true` carries `text`, and the parser today appends every `text`
  part to `content`. Turning on `includeThoughts` without splitting them would put the thoughts in
  the reply.

## Change

1. `ChatResult.reasoning_text` (provider-neutral). Gemini: parts with `thought: true` go there, never
   into `content`; `include_thoughts=True` adds `thinkingConfig.includeThoughts`. Anthropic: the text
   of the `thinking` blocks. OpenAI chat completions returns no reasoning text (left as None).
2. The agent loop asks for thoughts on its own model calls only, and stores each round's reasoning as
   an `agent_reasoning` trace event on the turn (same column and retention as #2009's steps), clipped.
   Never in the reply, the memory history, the tool digest, or a log line.
3. `steps_from_trace` returns `reasoning: [{round, text}]`, each tool call carries its `round`; the
   live turn response and the conversation read both carry it.
4. Console Agent tab: per round, a collapsible "Thinking" item above that round's tool calls.

## Tests (red first)

- Gemini parser: thought parts land in `reasoning_text`, not `content`; `includeThoughts` sent only
  when asked.
- Anthropic: thinking text lands in `reasoning_text`.
- Loop: reasoning stored on the turn trace per round; never in `reply_text`, history or digest.
- Conversation read and live response return it; console renders it collapsed per round.

## Cost

Google bills Gemini thinking on the full thought tokens whether or not `includeThoughts` is set
(ai.google.dev/gemini-api/docs/thinking), so asking for summaries adds no thinking spend. The one extra
cost: each round's summary sits in the replayed `continuation` parts, so it goes back as input on the later
rounds of the same turn (it is never replayed into a later turn). Not measured live here: the cloud sandbox
has no provider key. The hand test reads the console's `Tokens: X in, Y out` line for one sample turn.

## Accepted risk (security review)

- A round's reasoning can restate what a tool returned, including rows the reply left out. #2009 stored
  only each call's arguments and a one-line outcome, so this widens what is kept on `chatbot.turns`
  (no expiry, like every trace). It is readable only with `system.chat_history.view` (console, Chat
  History), the same staff who can run the agent for that contact and read the same data anyway.
- `GET /agent/conversation` does not filter by the operator who ran the turn (already true for replies
  and steps since #2009); any holder of the console permission sees another operator's reasoning for
  the same contact.

## Round 2 (owner, 31 Oct 00:35: "low effort for agent, how do I set reasoning effort")

- The agent defaults to reasoning effort `low` (`loop.DEFAULT_EFFORT`) when its label sets none; an effort on
  the label still wins.
- Why the owner could not set it: nothing wrote `ai_prompt_labels.reasoning_effort` (the column was read at
  runtime only), and dev has no `chatbot_agent` production label (the prompt seed ran before the key
  existed), so even the model save answered 404. Fix: the Runs on card has a clearable Reasoning effort
  select (POST prompts/{name}/model `reasoning_effort`, left out = unchanged), and a key with no
  production label gets one on a version of its built-in text, the text the agent already reads.
- Token cost low vs none: not measurable in the cloud sandbox (no provider key); measured by the owner hand
  test (laneboard/scripts/2022.md, Tokens line A vs B).
