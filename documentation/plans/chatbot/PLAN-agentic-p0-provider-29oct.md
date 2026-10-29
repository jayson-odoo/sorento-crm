# PLAN: Agentic phase 0 - provider continuation and reasoning effort

Status: in progress (build). Small fix track (expected diff under 300 lines, no migration, no auth/RBAC change, no new ingest surface). Lane AGENTIC-P0-PROVIDER, branch `crew/agentic-p0-provider`, base origin/main 3b3d3e1b91.

Parent: `PLAN-agentic-crm-29oct.md` component 8 ("Model integration") and AC11 in `UAC-agentic-crm-29oct.md`. Only phase 0 lands here; P1 (read-only agent path behind a per-contact switch) waits for owner answers and is out of scope.

## Problem (measured on 3b3d3e1b91)

1. Gemini: `GeminiProvider.chat` normalizes a `functionCall` part into `{id, name, arguments}` and drops the rest of the part (`llm_provider.py:1695-1716`). `_convert_messages_to_gemini` rebuilds the model turn as `{"functionCall": {name, args}}` only (`:1313-1326`), so the `thoughtSignature` Gemini 3 attaches to a function-call part never goes back. Google documents a 400 for a Gemini 3 function call replayed in the current turn without its signature; the default model is `gemini-3.5-flash` (`:113`). Verified from Google's docs, not with a live call (no paid calls in this lane).
2. Anthropic: `AnthropicProvider.chat` takes `reasoning_effort` and drops it (`:822`, pinned by `tests/test_llm_provider.py:1526`); no `thinking` or `output_config` is ever sent (`:893-905`). Only `text` / `tool_use` blocks survive normalization (`:907-920`), so thinking blocks and their signatures cannot be sent back in a tool loop.
3. The assistant's tool loops call the provider without an effort: `_run_agent_loop` (`ai_assistant_service.py:2602`) and `_render_record_answer` (`:3006`, `:3119`). The registry already serves one per prompt label (`ai_prompt_registry.agent_reasoning_effort`, `:1601`).

## Architecture

- Layer: the provider adapter (`app/services/llm_provider.py`) owns every provider-native shape. Callers stay on the OpenAI-style message list.
- Shared mechanism: one new optional `ChatResult.continuation` (provider-native assistant turn, opaque to callers: `{"provider": "gemini", "parts": [...]}` or `{"provider": "anthropic", "content": [...]}`). A tool loop copies it onto the assistant message it echoes (`"continuation"` key). The provider's own converter replays it verbatim when the provider matches, and rebuilds from `tool_calls` exactly as today otherwise. Set only when the response carries something a rebuild would lose (a Gemini `thoughtSignature`, an Anthropic `thinking` / `redacted_thinking` block), so every other request stays byte-identical.
- Anthropic effort: `reasoning_effort` is honoured per model family. Claude 4.6 and later: `thinking: {type: adaptive}` + `output_config.effort` (`none` / `minimal` send only effort `low`, no thinking). Older Claude (Haiku 4.5, Sonnet 4.5, ...): `thinking: {type: enabled, budget_tokens}`, `none` / `minimal` send nothing. With thinking on, `temperature` is not sent (Anthropic refuses a non-default temperature with thinking) and the thinking room is ADDED to `max_tokens`, the same rule as Gemini (the caller's number is its answer budget). An effort on a forced-tool structured call (`json_schema`) or an unknown effort value raises `ValueError` (thinking is refused with a forced `tool_choice`; a silent drop is what this lane removes). No caller sends one today: the parser sends `off` for Anthropic (`chatbot/head/parser.py:994-995`).
- Loops: both assistant tool loops read `agent_reasoning_effort(db, "agent_system")` once and pass it only when set (same `**({...} if effort else {})` shape as `parser.py:1431`). NULL label effort = request unchanged.

Classes fixed, not one shape: every Gemini response part with metadata, every Anthropic thinking block kind, every tool loop in the assistant service.

## Out of scope

Prompt text (md5-pinned), parser/chatbot turn path, OpenAI (Chat Completions has no reasoning continuation), model selection, the P1 agent runtime, task persistence, Anthropic `stop_reason=max_tokens` handling.

## Tests (red first, `tests/test_llm_provider.py` + `tests/test_agentic_p0_loops.py`)

1. Gemini: a response part's `thoughtSignature` comes back on `ChatResult.continuation`; an echoed assistant message carrying it is sent with the signature on its `functionCall` part, in order, with the function response still keyed by name.
2. Gemini: no signature in the response = no continuation; a history without continuation converts as before.
3. Anthropic: effort on `claude-sonnet-4-6` sends `thinking adaptive` + `output_config.effort`, no temperature, max_tokens grown; `none` sends effort `low` only.
4. Anthropic: effort on `claude-haiku-4-5` sends `budget_tokens` below max_tokens, no temperature; `none` sends nothing new.
5. Anthropic: thinking + tool_use blocks come back on `continuation`; echoed, they are replayed verbatim (signature included) before the tool result.
6. Anthropic: effort + `json_schema`, or an unknown effort, raises `ValueError`; no effort = request unchanged (no `thinking`, no `output_config`).
7. Loops: `_run_agent_loop` and `_render_record_answer` echo `continuation` into the next call's assistant message and pass the label's `reasoning_effort`; with no label effort the kwarg is absent.

## Delivery

1. `test(red):` commit with the tests above, red-proof posted.
2. Fix commit (provider + loops), green, kill-proof.
3. Reviewer subagent; PR; crew labels CI.
