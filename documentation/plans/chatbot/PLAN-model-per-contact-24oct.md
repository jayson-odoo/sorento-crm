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

## Open (behaviour card questions)

Q1 classifier, Q2 rows per class, Q3 which calls follow, Q4 missing key, Q5 override shape. Answers recorded
here before any code.

## Architecture

To be filled after the answers: one resolver (contact override > class default > label row > global) that every
chatbot LLM config reader calls, so the parser, clarifier and code reader cannot drift apart.
