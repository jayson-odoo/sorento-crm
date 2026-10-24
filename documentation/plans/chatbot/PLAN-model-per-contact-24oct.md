# PLAN: chatbot model per contact (MODEL-PER-CONTACT)

Status: PR+CI - PR #1839; reviewer READY and security re-check clean after the fix round; hand test filed. Track: L (migration, settings UI, keys).

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
- Owner 24 Oct 2026, Q1 (c) + Q2: contact TAGS decide. Provider + model is a new leaf in the existing tag `chatbot`
  section; no class rows, no `system_settings.chatbot_contact_models`. Order: contact override > tag model >
  production label > global. Untagged contact = today. The contact page shows which tag the model came from.
- Lead, 24 Oct 2026, multi-tag edge (owner: reuse an existing merge rule if one fits): the existing `eq` rule
  (`contact_tag_settings.py:490`, already used by `chatbot_skip_period_questions` / `chatbot_files_as_links`) fits.
  Tags that set the SAME model agree; tags that set DIFFERENT models are a conflict: no tag model applies, the
  contact runs on the label/global default, the tag panel lists the conflicting tags (existing `conflict_tags`), and
  the contact page says the tags disagree. A contact override settles it. No new precedence rule.

## Architecture

- Layer: one backend resolver, `app/services/contact_llm_choice.py` (core, so core callers never import the chatbot package) `contact_llm_choice(db, contact)`, returns
  `(provider, model, source, tag_names)` with source `contact | tag | tag_conflict | none`. It is the ONLY place the
  ladder's top two rungs are read. The tag rung reuses `contact_tag_settings.tags_by_contact_with_settings` +
  `leaves` + the `eq` merge, so the tag page, the contact panel and the runtime cannot disagree on a conflict.
- Live, not applied: every other tag setting is copied onto the contact by Apply, and the runtime reads the copy.
  The model is read live from the tags each turn, because the owner's ladder ("untagged = today", override beats
  tag) cannot hold with a copy: removing a tag would leave its model behind, and a bulk Apply would overwrite an
  override. So the leaf takes part in `evaluate` (the panel shows it, with `decided_by` and conflicts) but its
  `current` is the effective value and it never differs, so Apply never writes it.
- Runtime: `load_profile` (`turn_runtime.py`) carries the choice on `Profile`; the engine hands it to
  `parser.resolve_config` (`engine.py:5073`), `casual.resolve_clarifier_config` (`engine.py:6946`), only when a choice exists (a turn without one
  makes main's exact call). The code reader runs in its own request: `POST /system/references/resolve`
  (`api/v1/system/references.py`) reads the choice for the request's `contact_id` and hands it to
  `resolver_code_reader._resolve_provider`. Each applies one shared helper: choice (when its
  provider has a key, `resolve_api_key`) > its own label row > global. No key for the chosen provider: warning log,
  label/global used, trace `model_source = fallback_no_key`. Image lane untouched.
- Storage: tag leaf `settings.chatbot.llm = {"provider", "model"}` (JSON, no migration). Contact override: nullable
  `respond_contacts.chatbot_llm_provider` + `chatbot_llm_model`, both or neither (migration additive), written by
  `PUT /contacts/{id}/chatbot` with the absent-vs-null rule (`contacts.py:429`).
- Trace: the parser `understood` trace already records provider + model (#1624); it gains `model_source` and, for a
  tag, the tag names.
- UI (no mock: selects on existing forms, owner 29 Sep exception): tag form chatbot section "AI model" (provider +
  model, reusing `AgentModelCard`'s `SearchableSelect` + `PROVIDER_OPTIONS` + `useProviderModels`); contact Chatbot
  section "AI model" override (clearable) plus the source line ("From tag X" / "Tags disagree: ..." / "Default");
  System > AI Assistant "OpenAI API key" field (AC-R4-9).

## Slices

1. R4 key slots (UAC AC-R4-1..8): DONE, red 4d8c8f539b, green 467e9185b8, kill-proof 3 resolver tests.
2. Tag model + contact override + runtime ladder + trace (UAC AC-M-*): red 46cc9b4430 + 28d7389106, green
   def8c255cd + aa5eb508f9 + 757601fd2d, kill-proof (override / conflict / no-key mutations).
3. Review + security fix round (UAC AC-S-1..4 + reviewer findings): red first, then fix.

Test DB: `sorento_mpc_throwaway` (`SORENTO_ENV_FILE=.env.ci-tests`, redis index 13).

