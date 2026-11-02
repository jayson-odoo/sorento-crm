# PLAN: AI extract shows the proxy's 502 page instead of the real AI error (AI-EXTRACT-502)

Status: in progress (small fix track: under 300 lines, no migration, no auth/RBAC change, no new ingest surface)

## Problem

Owner, 2 Nov on production: Price Tag Request form, a file's Extract button. The AI Extract dialog shows
"Bad gateway (502). The API server is not responding - check that the backend is running and nginx proxy
settings." That text is `sorento_crm_frontend/lib/api-client.ts:36-38`, reached only when the body is HTML.

- The extract answers HTTP 502 with a JSON message on every AI provider failure
  (`sorento_crm_backend/app/services/ai_extract/extract_service.py:360-366`, plus `_parse_json` 823-856 and the
  attachment download at 266-270). Cloudflare answers an origin 502/504 with its own branded HTML page
  (developers.cloudflare.com "Error 502 or 504"), so the dialog never sees the JSON.
- The provider call has no timeout of its own (`extract_service.py:352-359`): OpenAI SDK default 600 s with
  2 retries (`llm_provider.py:530`), Gemini 120 s (`llm_provider.py:1095`). A hung call outlives the proxy.

## Architecture

- Layer: the extract service (`app/services/ai_extract/extract_service.py`), the one place every AI extract
  route goes through (portal and my-requests via `app/api/v1/public/ai_extract.py:86`, master-data
  `app/api/v1/master_data/ai_extract_field.py:81`, project register `app/api/v1/projects/projects.py:215`).
- One rule: an upstream failure inside the extract (AI provider, its answer, the storage read) answers
  **503** with the JSON message. 503 because Cloudflare's Error Pages do not apply to 503
  (developers.cloudflare.com/rules/custom-errors), and the repo already answers 503 for an unreachable AI
  dependency (`app/api/v1/system/ai_assistant.py:265`). 424 has no precedent in the repo (0 uses).
- Timeout: one constant, 45 s, passed as `timeout=` to `provider.chat`. Every provider already treats a
  caller-set timeout as "no SDK retries" (`llm_provider.py:528-530`, `:890-892`; Gemini has no retry loop).
  A timeout answers 503 with its own message (`code=ai_extract_provider_timeout`), detected by the shared
  `is_timeout` (`llm_provider.py:1985`).
- Project register keeps its plain message (never echoes provider text), now keyed to 503
  (`projects.py:218-224`).
- Frontend: no change. `extractApiError` already shows a JSON body's `message`
  (`lib/api-client.ts`), so a 503 JSON reaches the dialog as the app's own text.

## The "openai" last fallback (`extract_service.py:429`)

`provider_name = label_provider or (cfg.provider if cfg else "openai") or "openai"`.
`ai_assistant_configs.provider` is NOT NULL with default "openai" (`app/models/ai_assistant.py:33`), so
the literal is reached only when the install has NO `ai_assistant_configs` row. Dev copy
(sorento_dev_1028, prod-derived 28 Oct; DEV data, not prod): one row, provider gemini, model
gemini-3.5-flash; every `ai_extract_*` production label has provider NULL. So on an install with a row the
literal changes nothing. Ruling (owner: no OpenAI): the literal goes; with no row and no label the extract
fails fast with a clear 400 (`code=ai_extract_no_provider`) rather than silently posting to OpenAI. Not a
Gemini fallback: with no row there is no configured Gemini key either, only an env key, and a guessed
vendor is the bug this removes.

An install whose configured provider IS openai still calls OpenAI; that is operator config, not the
fallback. With this fix its failure (dead key, quota) now reaches the dialog as the provider's message.

## Measured (dev copy, read-only)

`ai_assistant_usage_logs` feature=ai_extract: 840 successful calls, max 10.3 s, 0 over 30 s
(portal.price_tag_request p99 9.8 s). 45 s leaves room over every observed success.

## Tests (red first)

`tests/test_ai_extract_upstream_503.py`:
1. Provider raises: portal route answers 503, JSON `message` carries the provider's text, code
   `ai_extract_provider_failed`.
2. Provider raises on the master-data ai-extract-field route: 503 JSON.
3. The provider receives `timeout=45` (the constant), so its SDK retries are off.
4. Slow provider: a call that times out answers 503 `ai_extract_provider_timeout` with the 45 s message,
   ending at the timeout (fake provider honours the passed timeout).
5. Empty / non-JSON provider answer: 503.
6. No config row and no label: 400 `ai_extract_no_provider`, no provider built.
Updated: `tests/test_project_register_v2_ai_extract.py::test_c6_a_provider_failure_*` expects 503.

## Follow-up (not changed here)

Other `status_code=502` sites listed in the PR body; changed only where the same mechanical pattern
inside this lane's routes.
