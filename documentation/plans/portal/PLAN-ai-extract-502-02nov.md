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
  **503** with a plain JSON message. 503 because Cloudflare's Error Pages do not apply to 503
  (developers.cloudflare.com/rules/custom-errors), and the repo already answers 503 for an unreachable AI
  dependency (`app/api/v1/system/ai_assistant.py:265`). 424 has no precedent in the repo (0 uses).
- Timeout: one constant, 45 s, passed as `timeout=` to `provider.chat`. Every provider already treats a
  caller-set timeout as "no SDK retries" (`llm_provider.py:528-530`, `:890-892`; Gemini has no retry loop).
  A timeout answers 503 with its own message (`code=ai_extract_provider_timeout`), detected by the shared
  `is_timeout` (`llm_provider.py:1985`).
- Plain messages only (owner ruling, 2 Nov, round 2): the provider's raw error (account details,
  billing text) never reaches a portal contact or a staff screen; it goes to the server log.
  Provider busy/failed or an unusable answer: "Could not read the file just now, please try again."
  Truncated answer: "This file is too long to read in one go; try fewer pages." (`ai_extract_too_long`).
  The project register route's own rewrite (`projects.py:218-224`) goes: the service is safe at source.
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

## Round 2: production cause (owner's prod logs, 2 Nov)

Five portal extracts answered 502 after 13-14 s with "Gemini stopped early: MAX_TOKENS (response
truncated; thinking 0, answer 6138 tokens)". The extract hard-coded `max_tokens=4096`; on gemini-3.x the
call's `maxOutputTokens` is that plus 2049 thinking room (`llm_provider.py` `_gemini_thinking`), 6145.
Fix: raise the answer budget to 16384 (`EXTRACT_MAX_OUTPUT_TOKENS`), not split per page/file: one
constant against a split that would need per-call line merging and dedupe. 16384 is what every provider
takes in one non-streamed call (gpt-4o/4o-mini cap 16,384; Anthropic non-streaming ceiling 21,333) and
about what the 45 s cap holds at production's measured speed. A truncation that still happens
(`ResponseTruncated`) answers 503 with the too-long message.

## Round 3: big files read in parallel page groups (crew browser pass, 2 Nov)

On 9c9fb65f18 a 6-page / 168-row stand-in read in 34 s, but a 12-page / 336-row one (the owner's real
promo size) hit the 45 s cap. A line-item upload of MORE than `SPLIT_ABOVE_PAGES` (6, the size crew read
in one call in 34 s) pages is now read as at most `MAX_PARALLEL_CALLS` (4) page groups at once, group size ceil(pages / 4), so every group runs in ONE wave: the whole read ends inside
one call's 45 s cap plus render, under the proxy's 60 s, with no separate deadline to manage. Each call
keeps its own cap and answer budget. Rows merge in page order (`pool.map`, not finish order); a row
exactly equal to one from an earlier group is dropped (repeats inside one group stay, as a single call
always kept them); a single-value field takes the first page's non-empty value and a list field
gathers every group's entries, each once. Smaller uploads and forms without line items stay one call
(review, round 3: a 2-photo complaint split in two lost its second DO number; a field-only form's
answer is one set of fields, not rows per page, so the project register and master-data extracts,
which never show the note, are never split). Groups that fail are named in a plain
`note` ("Pages 7-9 could not be read, try them again.") beside the rows that did read; every group
failing is the 503 path, first group's error. A video is not split (its frames show the same products).
Pasted text rides with the first group. Usage is logged once with the summed tokens.
Frontend: `AIExtractResult.note` and one muted line at the top of the review stage
(`components/common/ai-extract/AIExtractDialog.tsx`, same style as its "Nothing extractable" line).

## Measured (dev copy, read-only)

`ai_assistant_usage_logs` feature=ai_extract: 840 successful calls, max 10.3 s, 0 over 30 s
(portal.price_tag_request p99 9.8 s). 45 s leaves room over every observed success.

## Tests (red first)

`tests/test_ai_extract_upstream_503.py`:
1. Provider raises: 503 plain message, raw text only in the log; over HTTP on the portal route the raw
   text never appears in the body (provider failure, truncation, non-JSON answer).
2. A storage read failure on the master-data field extract: 503.
3. The provider receives `timeout=45` (the constant), so its SDK retries are off.
4. Slow provider: a call that times out answers 503 `ai_extract_provider_timeout` with the 45 s message,
   ending at the timeout (fake provider honours the passed timeout).
5. Empty / non-JSON / cut-off provider answer: 503 plain message.
7. Round 2: the call asks for 16384 answer tokens; a 9000-token Gemini answer that overran the old cap
   now reads; an answer no cap holds is 503 `ai_extract_too_long`; any provider's `ResponseTruncated`
   is 503 too-long.
6. No config row and no label: 400 `ai_extract_no_provider`, no provider built.
Updated: `tests/test_project_register_v2_ai_extract.py::test_c6_a_provider_failure_*` expects 503 and the
same plain message.

## Follow-up (not changed here)

Other `status_code=502` sites listed in the PR body; changed only where the same mechanical pattern
inside this lane's routes.
