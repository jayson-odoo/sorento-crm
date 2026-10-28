# PLAN: SPAN-PASS-PROD - the lookup span pass on production, with Gemini embeddings, verified

Status: 28 Oct. Plan + behaviour card filed (crew ask); no code yet. Track: M (prompt text + label config +
verification; code only if the card's answers need it: warm-up sharing, n-gram Gemini floors). Owner does every prod step.

Owner (28 Oct ~15:2x): "I want ... the span pass to be working on prod (which I haven't enabled yet cause idk how to turn
on the google embedding and how to make sure embedding works in prod)". Chat lane rule: understanding is parser-only, no
regex or word lists. Eval gate before any prod prompt publish.

## What must be true on prod for spans to run (origin/main f533248e74, paths under sorento_crm_backend/)

1. Parser text carries `== LOOKUP SPANS ==` as its own line: `parser.py:1052-1053` sets `lookup_spans` from
   `lookup_lists.spans_gate_on` (`lookup_lists.py:148`); `engine.py:5207` then runs `_span_prep` instead of
   `_lookup_lines`. Every live turn reads the production label of `chatbot_semantic_parser` (`parser.py:1003`, no per
   contact text; `llm_choice` changes only provider/model/key, `contact_llm_choice.py:48-66`). Label cache 60 s
   (`ai_prompt_registry.py:38`).
   - Text = prod v69 (`crew/state/eval/prompt-diet/texts/v68.txt`, md5 8c77b4eb) with line 1005 `== LOOKUP LISTS ==`
     swapped for `== LOOKUP SPANS ==`: md5 57d7d412, 102,624 chars. The span block IS that one line (dev v186 -> v187
     differ only there). Dev `sorento_prod_1020` already holds it as v189 (production label, gemini flash-lite).
2. Span extractor `chatbot_span_extractor` (`span_extract.py:27`, `:97-115`): v1 production label seeded by
   `eem_0001_span_pass.py:87-101`; v2 (+ per-span "meaning") published unlabelled by `eem_0003_span_meaning.py`.
   Model from its label, else the AI config provider/model.
3. Embedder `chatbot_lookup_embedder` production label (`lookup_lists.py:1094-1110`, `agent_model` uncached,
   `ai_prompt_registry.py:1576-1598`): provider `gemini` + model -> Gemini embedder; else OpenAI text-embedding-3-small.
   eem_0003 seeded the label with provider/model NULL (= OpenAI). Span meaning floors exist ONLY for
   `text-embedding-3-small` and `gemini-embedding-001` (`list_resolver.py:43-75`); any other model name = meaning off.
4. Gemini key: `ai_assistant_configs.gemini_api_key_ciphertext`, else generic key when provider is gemini, else env
   `GEMINI_API_KEY` (`llm_provider.py:162-184`). Prod parser already runs Gemini, so a key resolves (UNVERIFIED which).

## Known gaps

- n-gram path: `_meaning` drops any non-3-small embedder (`lookup_lists.py:307`). With spans on it runs only as the span
  FALLBACK (`engine.py:1428,1484-1491`: span call failed / unreadable / resolver error). Dev traces: 2 of 21 span turns
  (`sorento_prod_1020`), 2 of 91 (`sorento_explore1020`, call_error).
- Warm-up: per process, no shared store (`lookup_lists.py:856`); 4 gunicorn workers per colour (`gunicorn.conf.py:44`),
  startup event per worker (`main.py:329,415`), lazy warm per turn too (`engine.py:1270,1335`). ~4,652 texts / 100 per
  Gemini request = 47 requests per process. Measured 27 Oct on ONE process: 429 part-way at ~1.5k texts/min
  (AC-S3-13). Four warms at once (start-up OR the label flip itself) = ~18.6k texts. After 3 retries the fill gives up
  (`lookup_lists.py:916-928`); turns stay spelling-only until every text is cached (`:1086-1091`).

## Steps (filled after the card's answers)

1. Card (crew ask) - owner answers.
2. Eval gate on dev: v68.txt (lists) vs v68+spans, Gemini flash-lite, smallest row set inside the ledger cap.
3. Code (only if chosen): red tests first (tester), coder, reviewer.
4. Verification + rollback recipe for crew (Sorento Chat connector, read-only).
5. Owner step list.
