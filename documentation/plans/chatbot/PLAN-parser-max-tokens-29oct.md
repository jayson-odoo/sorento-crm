# PLAN: parser max output tokens (PARSER-MAX-TOKENS, 29 Oct 2026)

Status: in review (PR #1970), small fix track (S); one additive migration + Settings > Chatbot field (owner additions, lane stays S).

## Problem

Prod turn 5ad8f394 (29 Oct 10:33 MYT): a 63-code stock check stopped on
`Gemini stopped early: MAX_TOKENS (answer 4081 tokens)` and the customer got the generic
error reply. Not a loop: the same customer's 33-line resend parsed at 3,090 output tokens
(~90 tokens per item), so 63 items need ~5,700.

Measured on origin/main 6011ba76ff:

- `PARSER_MAX_TOKENS = 2048` (`sorento_crm_backend/app/services/chatbot/head/parser.py:44`),
  sent as `max_tokens` at `parser.py:1371`.
- Gemini 3.x adds its thinking budget (1 for flash-lite with no effort) plus
  `GEMINI_3_ANSWER_HEADROOM = 2048` (`llm_provider.py:1027`, `:1048`, `:1658`): real cap 4,097.
- OpenAI sends the same number as `max_completion_tokens` (`llm_provider.py:339-341`), so
  gpt-5.4-mini gets the same answer budget (reasoning included when an effort is sent).
- `MAX_TOKENS` raises a plain `RuntimeError` inside the provider (`llm_provider.py:1714-1722`);
  `llm_call.is_transient` does not retry it, `parse` wraps it as a `ParserError` with no usage,
  and `engine._record_parser_usage` skips the row when usage is empty (`engine.py:2171`), so
  the failed call never reaches `ai_assistant_usage_logs` / the `llm_calls` view.

## Architecture

- Layer: the parser (`head/parser.py`) owns its answer budget; the provider owns the raise.
- One stored setting, same mechanism as `chatbot_parser_reasoning_effort` (`parser.py:959-966`):
  `system_settings.chatbot_parser_max_output_tokens` INTEGER NOT NULL DEFAULT 8192, read per
  parse in `resolve_config` (no cache, like the sibling), carried as
  `ParserConfig.max_output_tokens`, sent by `parse` as `max_tokens` on every provider.
  Range 1024-32768; a stored value outside it is clamped and logged.
- Default `PARSER_MAX_TOKENS = 8192` (Gemini 3.x real cap 8192 + 1 + 2048 = 10,241). Output is
  billed as used, so a normal turn costs the same.
- Failed-call visibility: the Gemini `MAX_TOKENS` raise becomes `ResponseTruncated(RuntimeError)`
  carrying the billed `ChatResult`; `parse` turns it into the same usage dict a success writes,
  so the engine writes a `was_answered = false` row. Message text unchanged (existing tests
  match on it).
- Not changed: the customer-facing reply wording (owner decision; see report).
- Not changed: `llm_call.ATTEMPT_TIMEOUT_SECONDS` (20 s) / `CALL_DEADLINE_SECONDS` (35 s) (crew
  ruling 29 Oct, option a). Measured on turn 5ad8f394: 11,516 ms for 4,081 answer tokens on
  gemini-3.5-flash-lite (~355 tok/s), so ~5.5k tokens takes ~15.5 s and the 20 s attempt timeout
  makes ~7k output tokens the practical ceiling there; gpt-5.4-mini is slower. A setting above
  ~7k raises nothing on flash-lite: the call times out first (customer reads the "busy" reply).
  Recorded in code comments and the PR, not on screen (CLAUDE.md: no feature explanations in the
  UI); the Outline guide is the place for it when guide-writer next runs.
- UI (owner ruling 29 Oct, option b): a "Parser max output tokens" number field in the Switches
  card of Settings > Chatbot (shared `NumberInput`, `numberFieldError` on save with the API's
  bounds), through the settings API (schema + GET dict + null-reset defaults dict).

## Tests (red first)

1. `tests/chatbot/test_parser_max_tokens.py`: a synthetic 63-line stock check through `parse`
   with a fake Gemini transport that answers with ~5,500 output tokens: the request's
   `maxOutputTokens` is 8192 + 1 + 2048 and the parse succeeds; the same message on OpenAI
   asks `max_completion_tokens = 8192`.
2. Setting: unset row reads 8192, stored value honoured, out-of-range values clamped
   (1, 0, -5, 100000) with a warning, column + migration exist.
3. A Gemini `MAX_TOKENS` answer leaves a `ParserError` carrying usage, and the engine writes a
   `chatbot_parser` row with `was_answered = false`.

## Steps

1. Plan + UAC commit. 2. `test(red):` commit. 3. Fix commit. 4. Kill test. 5. Reviewer.
6. PR, crew SQL file, hand test script after the reviewer, CI via crew label.
