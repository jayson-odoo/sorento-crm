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

## Resolver, screens, trace: PENDING (Q1 classifier, Q2 rows)

Decided by crew 24 Oct 2026: Q3 (a) parser + clarifier + code reader follow the contact, image lane keeps its own
setting; Q4 (a) chosen provider without a key falls back to label/global for that turn, logs a warning, trace
`model_source=fallback_no_key`; Q5 (a) the override is a provider + model pair.
