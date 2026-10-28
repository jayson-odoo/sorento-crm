# PLAN: explicit Gemini context caching for parser calls (GEMINI-EXPLICIT-CACHE)

Status: built, review round 1 folded; awaiting a live check on gemini-3.5-flash-lite (small fix
track: backend only, no migration, no auth/RBAC, no new ingest surface)

## Why

Production parser runs on `gemini-3.5-flash-lite` for most contacts since 28 Oct 15:09. Every
Gemini call reports 0 cached tokens, so the ~28k-token static system prompt (129k chars,
`PLAN-llm-test-cost-4oct.md` "Cache friendliness") is billed in full on every turn (OpenAI:
~28.5k cached per turn). Explicit context caching (`cachedContents`) makes Google bill that
prefix at the cached rate.

## Design (simplest thing that works)

All inside `GeminiProvider` (`app/services/llm_provider.py` `_generate`, `_cached_content`,
`_blame_cache`) plus a name store (`app/services/gemini_context_cache.py`). Callers change only by
passing the `prompt_cache_key` they already pass: the parser (`head/parser.py`), the topic
labeller (`analytics/labeller.py`), and now the clarifier (`lanes/casual.py`).

1. A call that carries `prompt_cache_key` AND a system prompt asks for an explicit cache.
   Cache identity = sha256(API key hash, model, systemInstruction, tools); an entry lives in the
   key's project, so another key is another entry.
2. **The date stays in the system prompt.** Moving CURRENT DATE into the user block was already
   implemented and measured on 4 Oct and NOT shipped because it changed parses
   (`PLAN-llm-test-cost-4oct.md`, "Measured, NOT shipped: moving the date line"). The system
   text carries `{{current_date}}`, so the identity rolls over at Malaysia midnight by itself:
   one entry per (key, model, prompt version, day).
3. Lookup: in-process (60s copy) -> Redis `gemini_cache:<hash>` (shared across gunicorn
   workers, own client with 1s timeouts) -> `POST cachedContents` (systemInstruction + tools,
   `ttl: 3600s`, at most 5s and never more than the caller's budget). The name is stored
   `SET NX` for TTL minus 120s; a worker that loses the race uses the winner's and deletes its
   own entry.
4. The request sends `cachedContent: <name>` and omits `systemInstruction` / `tools` (the API
   refuses both together). `generationConfig` (`responseSchema`, `thinkingConfig`) stays.
5. Failure is always an uncached answer, inside `llm_call`'s per-attempt budget:
   - create refused / slow / Redis down: uncached; a refused create is backed off 15 min
     (Redis marker `-`), so a prompt Google will not cache costs one POST per window.
   - cached call refused 400/403/404: retried uncached. If the uncached call also fails, the
     request was the problem: raised as before, cache kept. If it answers, the cache was the
     problem: an entry created in this same call is backed off (no create + refusal + storage
     every turn); an older one is forgotten, only if Redis still holds that same name.
   - 429 / 5xx on the cached call: raised for `llm_call` to wait out, as before.

## Google facts (docs fetched via search; ai.google.dev itself is outside this sandbox's network)

- Explicit caching: `POST v1beta/cachedContents` with `model`, `systemInstruction`, `tools`,
  `ttl` ("3600s"); `generateContent` takes `cachedContent`, and refuses `systemInstruction`,
  `tools`, `toolConfig` beside it (https://ai.google.dev/gemini-api/docs/caching?lang=rest).
- Minimum cacheable size: the caching page lists 1,024 to 4,096 tokens depending on model
  (3.5 Flash: 4,096 on the current localized pages); Flash-Lite is not listed. The parser
  prompt (~28k tokens) clears every listed minimum. Whether `gemini-3.5-flash-lite` accepts
  `createCachedContent` is NOT verified from here (no Gemini key in the sandbox): the live
  check below settles it, and a refusal degrades to today's uncached behaviour.
- Pricing, 3.5 Flash-Lite, Standard tier (https://ai.google.dev/gemini-api/docs/pricing via
  aggregators): input $0.30/1M, cached input $0.03/1M, cache storage $1.00/1M tokens/hour.

## Expected cost

Per parser turn, ~28.5k static tokens move from $0.30/1M to $0.03/1M: $0.00855 -> $0.00086,
saving ~$0.0077. From ~$0.011/turn today that is **~$0.0033/turn plus storage**.

Storage: one live entry costs 28.5k x $1/1M = ~$0.029 per hour it lives, plus one create per
hour billed as ~28.5k input tokens (~$0.0086). Break-even is ~5 turns/hour per entry
(model x key x prompt version x day). At 30 turns/hour the storage adds ~$0.0012/turn
(**~$0.0045/turn all in**, vs ~$0.005 on OpenAI); at 100/hour ~$0.0004 (~$0.0037). Below
~5 turns/hour (night) an entry costs more than it saves, bounded at ~$0.04 per idle hour per
entry since nothing recreates it until the next turn. The clarifier's ratio is the same per
token; its prompt is small, so if it is under the model's minimum the create is refused and
backed off.

Not counted per turn: storage is a project cost, not on any `ai_assistant_usage_logs` row. The
turn-cost views price a cached token only when `llm_model_prices.cached_input_usd_per_1m` is
set (`analytics_connector/prices.py`); a Gemini row without it now reads NULL cost.

## UAC

- AC-1 first call with a key creates one cachedContents entry and sends `cachedContent`.
- AC-2 a second call with the same model + system text reuses it (no second create).
- AC-3 a second process (empty in-memory map) reuses the name found in Redis.
- AC-4 a cached call refused for an expired entry answers uncached; the next call creates anew.
- AC-5 create failing (any error, or slow) -> the call still answers, uncached.
- AC-6 `cachedContentTokenCount` lands in `ChatResult.cached_tokens`.
- AC-7 no `prompt_cache_key` or no system prompt -> request unchanged.
- AC-8 the cache steps stay inside the caller's timeout.
- AC-9 an entry refused right after its create is not recreated every turn.

Tests: `sorento_crm_backend/tests/test_gemini_context_cache.py`.
