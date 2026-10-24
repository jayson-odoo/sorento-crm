# PLAN: chatbot model per contact (MODEL-PER-CONTACT)

Status: Plan - behaviour card filed to the owner 24 Oct 2026, build waits on the answers. Track: L (migration, settings UI, keys).

## Journey

Owner, 24 Oct 2026: "we need to have the model split where I can set per contact, I will set staff use gemini
customer use open AI, need to build this configuration and flexibility".

The owner sets which LLM provider + model answers a contact: a default per contact class, a per-contact
override that beats it, and nothing set means exactly today's behaviour (the `production` label row, then the
global AI assistant config).

## Facts (origin/main e21e2b61bd, verified)

- Parser config: `head/parser.py:872` `resolve_config`; provider/model from `agent_model(db, PROMPT_KEY)` then
  `AIAssistantConfigService(db).get()` (`parser.py:906-913`); called at `engine.py:5073`, after the profile is
  loaded at `engine.py:4853`.
- Clarifier: `lanes/casual.py:263` `resolve_clarifier_config`, model falls back to `DEFAULT_MODEL`
  (`casual.py:287`); called at `engine.py:6946`.
- Code reader: `resolver_code_reader.py:219` `_resolve_provider`: own label, then the parser's label, then global.
- Image lane: `media_extract/service.py:520-527`, `settings.image_provider`, runs on the worker (no profile).
- Key trap: `llm_provider.py:140` `resolve_api_key`; OpenAI has no own column, the generic
  `api_key_ciphertext` counts for OpenAI only while the config row's provider is `openai` (`llm_provider.py:169,184`).
- Classifiers: `contact_asker.classify` (`contact_asker.py:135`, first match salesperson / staff / salesperson
  via sales_agents / dealer / unclassified) vs `turn/state.py:265` `is_staff_profile` (tier == office).
- Dev data (`sorento_cagent_stack`, read-only, 24 Oct): 405 contacts; asker words dealer 216, unclassified 93,
  staff 64, salesperson 32; `chatbot_profile.tier` set on 0; `respond_contact_tags` has 0 rows.
- Parser trace already carries provider + model + usage (#1624, `head/parser.py:1197`).

## Decisions

- Crew 24 Oct 2026: Q3 (a) parser + clarifier + code reader follow the contact, image lane keeps its own setting;
  Q4 (a) no key for the chosen provider -> label/global for that turn + warning log + trace
  `model_source=fallback_no_key`; Q5 (a) provider + model pair, no profile table.
- Crew 24 Oct 2026, R4 addendum accepted: nullable `ai_assistant_configs.openai_api_key_ciphertext` + "OpenAI API
  key" field beside Gemini/Anthropic; OpenAI order = own column > generic while `config.provider == openai` > env.
  Write-only in the API, masked like the other keys; security review covers it.
- Q1 (which classifier) and Q2 (rows per class): with the owner. Only R4 is built until they land.

## Slices

1. R4 key slots (UAC AC-R4-1..8): migration, model, resolver, settings API, reencrypt script, redaction. Red first.
2. PENDING Q1/Q2: resolver + settings card + contact field + trace + AC-R4-9 field.

Test DB: `sorento_mpc_throwaway` (`SORENTO_ENV_FILE=.env.ci-tests`, redis index 13).

## Architecture

To be filled after the answers: one resolver (contact override > class default > label row > global) that every
chatbot LLM config reader calls, so the parser, clarifier and code reader cannot drift apart.
