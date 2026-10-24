# UAC: chatbot model per contact (MODEL-PER-CONTACT)

Plan: `PLAN-model-per-contact-24oct.md`. Sections marked PENDING wait on the owner's Q1/Q2 answers.

## R4: each provider's key from its own slot (crew-approved 24 Oct 2026)

- AC-R4-1: `ai_assistant_configs` gains a nullable `openai_api_key_ciphertext` (EncryptedText, Fernet at rest like
  the Gemini and Anthropic slots). Additive migration, idempotent, single alembic head.
- AC-R4-2: `resolve_api_key(cfg, "openai")` returns, in order: the OpenAI column; else the generic
  `api_key_ciphertext` while `cfg.provider == "openai"`; else env `OPENAI_API_KEY`; else "".
- AC-R4-3: with `cfg.provider` = `gemini` (or `anthropic`) and the OpenAI column set, OpenAI gets the OpenAI column
  and Gemini (Anthropic) still gets its own column. Mixed providers resolve both keys from the DB.
- AC-R4-4: with `cfg.provider` = `gemini` and the OpenAI column empty, OpenAI never receives the generic column
  (it holds another provider's key): it gets env `OPENAI_API_KEY` or "".
- AC-R4-5: today's rows (OpenAI column empty, `cfg.provider == "openai"`, generic key set) resolve exactly as before
  for every provider.
- AC-R4-6: the settings API accepts `openai_api_key` write-only: present and non-blank sets the column, absent or
  blank leaves it alone; responses carry only `openai_api_key_masked` (same masking as the other keys), never the
  plaintext or the ciphertext.
- AC-R4-7: the stored value is ciphertext in the DB (a raw SQL read is not the plaintext), and
  `scripts/reencrypt_field_secrets.py` re-encrypts the new column with the other three.
- AC-R4-8: any log/redaction path that hides the other provider keys hides the OpenAI one too
  (`app/services/api_call_log_service.py`).
- AC-R4-9 (UI, after Q1/Q2): System > AI Assistant shows an "OpenAI API key" field beside the Gemini and Anthropic
  ones, masked, empty = today.

## Model per contact (owner rulings 24 Oct 2026: tags decide; crew Q3 a, Q4 a, Q5 a)

Ladder for every chatbot LLM call of a turn (parser, clarifier, code reader): contact override > tag model >
that call's own `production` label row > global AI assistant config. Image lane unchanged.

Tag setting
- AC-M-1: a tag's `chatbot` section accepts `llm: {"provider": <openai|gemini|anthropic>, "model": <non-empty
  string, max 100>}`; anything else is a 422 naming the field. Absent = the tag sets no model.
- AC-M-2: the tag form's Chatbot section has an "AI model" provider select + model select (models from the
  provider list, typed-in name accepted, like the Prompts screen's agent model card); clearing it removes `llm`.

Contact override
- AC-M-3: `respond_contacts` gains nullable `chatbot_llm_provider` + `chatbot_llm_model` (additive migration).
  `PUT /contacts/{id}/chatbot` with `llm: {"provider", "model"}` sets both, `llm: null` clears both, `llm` absent
  leaves them alone; provider outside the three or a blank model is a 422. Gate unchanged
  (`user_management.contacts.edit`).
- AC-M-4: the contact read returns `chatbot_llm` = `{provider, model, source, tags}`: source `contact` (override),
  `tag` (tags names that set it), `tag_conflict` (provider/model null, `tags` = the disagreeing tag names; their
  values show in the tag panel's `conflict_tags`), `none` (provider/model null, today).

Resolution (one resolver, `contact_llm_choice`)
- AC-M-5: override set -> override, source `contact`, whatever the tags say.
- AC-M-6: no override, one or more tags all setting the SAME model -> that model, source `tag`, `tags` = their names.
- AC-M-7: no override, tags setting DIFFERENT models -> no choice, source `tag_conflict` (the `eq` merge rule).
- AC-M-8: no override, no tag sets a model (or untagged) -> no choice, source `none`; every config reader returns
  exactly what it returns on main (same provider, model, key, effort).
- AC-M-9: a tag edit, a tag added or removed, or an override change applies from the contact's next turn (no cache,
  no Apply needed).

Runtime
- AC-M-10: the parser config (`parser.resolve_config`) uses the choice: provider, model and that provider's key
  (`resolve_api_key`, R4); the label's reasoning effort still applies with the existing per-provider caps.
- AC-M-11: the clarifier (`casual.resolve_clarifier_config`) and the code reader (`resolver_code_reader`) use the
  same choice for the same turn.
- AC-M-12: chosen provider has no key -> that call runs on its label/global config, a warning is logged naming the
  provider (never a key), and the turn completes; trace `model_source = fallback_no_key`.
- AC-M-13: the parser `understood` trace records `provider`, `model` (already, #1624) plus `model_source`
  (`contact | tag | label | global | fallback_no_key`) and, for `tag`, the tag names.

Tag panel and Apply
- AC-M-14: the contact's tag panel lists "AI model" with `decided_by` = the tags; a conflict lists both tags
  (`conflict_tags`); the item never counts as differing, and Apply (contact, tag holders, bulk, on tagging) never
  writes the contact override.

Contact page
- AC-M-15: the contact Chatbot section shows "AI model" with the override select (clearable) and a source line:
  "From tag <names>" / "Tags disagree: <tag>, <tag>" / "Set on this contact" / "Default".
- AC-M-16: 375px and 1280px usable, no clipping; no UUIDs shown.
