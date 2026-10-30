# PLAN: chatbot failure-reply triage (30 Oct 2026)

**Status:** Phase 1 investigation (no code). Track: decided after the cause table (likely S slices per cause).

## Ask

Owner, 30 Oct 2026: "There are a lot of sorry I couldn't process, I couldn't understand. Can you
identify the root cause for all of them and solve it?"

## Data

- Prod backup `sorento_prod_1028` (28 Oct 2026), read-only (`BEGIN READ ONLY ... ROLLBACK`).
- `chatbot.turns` (status, stage, branch_kind, error, trace[], response.reply.text): one row per CRM turn.
- `chat_histories` (outgoing rows = what the contact actually received, including n8n-only error
  texts the CRM never wrote).
- `analytics_connector.llm_calls` (provider, model, tokens, latency per turn).

## Phase 1 steps

1. Every failure/fallback template: exact string, file:line, emitting condition (EN/MS/ZH).
2. Count in the last 30 days of the backup: by day, by audience (staff vs customer), by template.
3. Join each failing reply to its turn row and classify the root cause.
4. Rank causes with 2-3 masked examples each.
5. Drift: releases #8 (b07e71d5bf) and #9 (257b6967eb) changes that touch these paths.
6. One crew `--ask`: cause table + S/M fix slice per cause + recommended order.

## Phase 2 (after owner answers)

Per slice: red test first from the real failures (gold cases), then the fix, kill test, reviewer.
Standing rules: semantic fixes only (no regex/word-list guards), chatbot eval gates, prompt
changes via md5 pin + owner publishes, staff Gemini / customers OpenAI.
