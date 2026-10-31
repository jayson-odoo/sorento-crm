# PLAN: no-openai (clarifier model fallback + what still needs an OpenAI key)

Status: Built, in review. Track: small fix (one file of code, no migration, no auth change).

Lane: NO-OPENAI. Owner, 31 Oct: "I am not using OpenAI anymore". He switched System > AI
Assistant > Settings to Google Gemini. He sets the prompt labels and settings on prod himself, so
the click-list card was dropped (owner, 31 Oct ~13:15). Scope:

1. Fix: the chatbot clarifier must not fall back to a hard-coded OpenAI model.
2. No build for voice notes or embeddings. The PR body says what still needs an OpenAI key and
   what breaks without it.

## 1. Clarifier fix

`sorento_crm_backend/app/services/chatbot/lanes/casual.py` `resolve_clarifier_config` used
`model_override or DEFAULT_MODEL` (`DEFAULT_MODEL = "gpt-4.1-mini"`). With a blank
`chatbot_clarifier` label and the assistant on Gemini, provider = gemini and model =
`gpt-4.1-mini`, so Google got an OpenAI model id. Now the model comes from
`llm_provider.resolve_model(config, provider, label_model)`: the label's model, else the config
model when the config runs on the same provider, else that provider's default
(`llm_provider.DEFAULT_MODELS`). The contact / tag choice (`contact_llm_choice.apply_choice`)
still sits on top. `DEFAULT_MODEL` is removed.

Behaviour change on an OpenAI install with a blank label: the clarifier now runs on the
assistant's configured model instead of `gpt-4.1-mini`.

Tests: `sorento_crm_backend/tests/chatbot/test_clarifier_model_fallback.py` (red first, 4 of 6
red before the fix), `tests/chatbot/test_s4_casual_lane.py` pin replaced.

## 2. Still needs an OpenAI key today (file:line, main at 938a7fac)

"The OpenAI key" is either the OpenAI slot in AI Assistant settings or env `OPENAI_API_KEY`
(`llm_provider.resolve_api_key`); the embedding worker and the clustering job read env only.


- Voice notes: always OpenAI whisper. `media_extract/transcribe.py:44` posts to
  `api.openai.com`, `media_extract/service.py:695` reads the OpenAI key. No key: every voice note
  fails.
- Records search + lookup-list embeddings: OpenAI `text-embedding-3-small` until switched
  (`embedding_settings.py:11`, `config.py:318-319`). The worker refuses without env
  `OPENAI_API_KEY` while that is the model (`embedding_worker.py:649-650`); search 503s
  (`api/v1/external/rag.py:36-37`). Switching needs no code: Settings > Embeddings to
  `gemini-embedding-001` queues the backfill (`api/v1/user_management/settings.py:1233-1247`),
  the worker dual-writes (`embedding_settings.py:68-73`), and search flips only once every
  record has a Gemini vector (`embedding_backfill_service.py:667-731`). Remove the key after the
  flip, not before. Quality cost: lookup-list meaning matches are calibrated on OpenAI vectors, so
  on any other model they read spelling only (`chatbot/head/lookup_lists.py:290-291`).
- Unanswered-question clustering job: env `OPENAI_API_KEY` only
  (`jobs/ai_wishlist_clustering.py:44-47`). No key: the job logs a warning and skips.
- Photo reading: provider is the `media_image_provider` setting, seeded `openai` / `gpt-4o`
  (`alembic/versions/358_media_image_model_tiers_seed.py:55-57`). No key and not switched: photo
  reads fail. Settings > Chatbot media switches it, no code.
- Not a dependency: `AIAssistantChatService._embed_query` (`ai_assistant_service.py:3211`) is
  OpenAI-only but has no caller in `app/`; contact / tag choices set to OpenAI fall back to the
  default model when no OpenAI key exists (`contact_llm_choice.py:59-66`).
