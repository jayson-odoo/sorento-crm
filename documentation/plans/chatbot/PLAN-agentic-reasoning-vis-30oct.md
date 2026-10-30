# PLAN: the agent's reasoning, visible in the Chatbot Console

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)
Lane: AGENTIC-REASONING-VIS
Owner, 30 Oct 23:13: "I need our reasoning to be more visible ... I need to see the reasoning in
the console so at least I know agent's thought process."

## Evidence (what main does today)

- Model: `chatbot_agent` runs on the `production` label of `ai_prompt_labels` when one is set
  (`app/services/ai_prompt_registry.py` `agent_model` / `agent_reasoning_effort`), else
  `gemini` / `gemini-3.5-flash` with no effort (`app/services/chatbot/agent/loop.py` DEFAULT_PROVIDER,
  DEFAULT_MODEL). No migration seeds a label row for `chatbot_agent`. The sandbox cannot read the
  dev or prod DB, so whether the owner set a label there is not verified here.
- Reasoning is ON: every Gemini 2.5+ call gets a `thinkingConfig` (`app/services/llm_provider.py`
  `_gemini_thinking`, applied in `GeminiProvider.chat`), so the model thinks and its
  `thoughtsTokenCount` is billed.
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
