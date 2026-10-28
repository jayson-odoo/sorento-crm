# PLAN: explicit Gemini context caching for parser calls (GEMINI-EXPLICIT-CACHE)

Status: in progress (small fix track: backend only, no migration, no auth/RBAC, no new ingest surface)

## Why

Production parser runs on `gemini-3.5-flash-lite` for most contacts since 28 Oct 15:09. Every
Gemini call reports 0 cached tokens, so the ~28k-token static system prompt is billed in full on
every turn (OpenAI: ~28.5k cached per turn). Explicit context caching
(`cachedContents`) makes Google bill that prefix at the cached rate.

## Design (simplest thing that works)

All inside `GeminiProvider.chat` (`app/services/llm_provider.py`); callers change only by
passing the `prompt_cache_key` they already pass.

1. A call that carries `prompt_cache_key` AND a system prompt asks for an explicit cache.
   Cache identity = sha256(model, systemInstruction, tools). The system text includes
   `{{current_date}}`, so the key rolls over at Malaysia midnight by itself (cache per day);
   the date stays where it is (no prompt change, no eval needed).
2. Lookup order: in-process dict -> Redis (`gemini_cache:<hash>` -> cache name, shared across
   gunicorn workers) -> create via `POST cachedContents` (systemInstruction + tools, ttl).
3. The request then sends `cachedContent: <name>` and omits `systemInstruction`/`tools`
   (the API refuses both together). `generationConfig` (incl. `responseSchema`) stays on the
   request.
4. Any cache error (create refused, too few tokens, Redis down) falls back to the uncached
   request; a generateContent refusal naming the cached content (404/400/403 on an expired or
   deleted entry) forgets the name and retries the call once uncached, creating fresh next time.
5. Short failure memo: a create that is refused (e.g. prompt under the model's minimum) is not
   retried for a few minutes, so a small prompt does not pay a failed POST every turn.

## UAC

- AC-1 first call with a key creates one cachedContents entry and sends `cachedContent`.
- AC-2 a second call with the same model + system text reuses it (no second create).
- AC-3 a second process (empty in-memory map) reuses the name found in Redis.
- AC-4 a generateContent that fails on the cached entry (expired / 404) retries uncached and
  the next call creates a new entry.
- AC-5 create failing (any error) -> the call still answers, uncached.
- AC-6 `cachedContentTokenCount` lands in `ChatResult.cached_tokens`.
- AC-7 no `prompt_cache_key` or no system prompt -> request unchanged.
