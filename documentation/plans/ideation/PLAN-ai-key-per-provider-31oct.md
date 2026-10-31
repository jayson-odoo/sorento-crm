# PLAN: LLM callers resolve their key per provider (AI-KEY-PER-PROVIDER)

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Problem

Three LLM callers take their key from `config.api_key_ciphertext or settings.openai_api_key`
while the config's provider can be gemini or anthropic:

- `app/services/ideation_extractor.py:383` (ideation capture extraction)
- `app/services/ideation_turn_service.py:87` (ideate access-denied reply)
- `app/services/ticket_intake_service.py:262` (IT ticket draft)
- `app/services/scm/explainer_service.py:165` (SCM recommendation explainer, same pattern)

With provider gemini and the key only in the gemini slot, extraction runs with no usable key and
returns an empty extraction; `ideation_capture_service._missing_required` reads that as "no idea",
so the user is asked for the idea again and then refused ("I still couldn't find an idea").

## Fix

1. Every caller above resolves its key with `llm_provider.resolve_api_key(cfg, cfg.provider)`
   (the one existing helper; no copy).
2. The extractor marks a failed read (`IdeateExtraction.failed = True`: config read, no key,
   prompt render, provider or parse error). The capture turn answers a failed read with the new
   `read_failed` reply and does NOT ask for the idea (no `ask_idea`, so the ideate lane opens no
   required ask) and does not give up. The failure is logged.
3. Wording (`ideation_capture_read_failed`), honest and plain, no sorry/busy:
   - en: "I couldn't read that just now. Please send it again."
   - ms: "Saya tidak dapat membaca mesej itu sekarang. Sila hantar sekali lagi."
   - zh: "我刚才无法读取这条消息，请再发送一次。"

## Out of scope (listed, not changed)

Embedding callers read the env OpenAI key on purpose (the embedding provider is its own setting):
`app/jobs/ai_wishlist_clustering.py:44`, `app/services/embedding_client.py:130`,
`app/services/embedding_worker.py:649`.

## Tests (red first)

- provider gemini + key only in gemini slot: extractor, ideate reply and ticket intake hand that
  key to `get_provider`.
- extractor raising: capture turn replies `read_failed`, never `ask_idea` / `ask_idea_gave_up`.
