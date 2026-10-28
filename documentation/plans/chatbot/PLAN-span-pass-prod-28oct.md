# PLAN: SPAN-PASS-PROD - the lookup span pass on production, with Gemini embeddings, verified

Status: 28 Oct ~16:00. Owner answers (~15:4x): Q1 (a) two steps, Q2 (a) shared vector file (UAC
`span-pass-prod-acceptance-criteria.md`), Q3 span extractor v2 NOW (works on OpenAI 3-small: `list_resolver.py:344-357`
has no model check, floors `:68-71`), Q4 (a), Q5 (a) eval <= USD 0.25 today. Building Q2 (tester -> coder -> reviewer).
Track: M (no migration, no auth). Owner does every prod step.

## Owner rulings (28 Oct ~15:4x, via crew)

- Q1 (a): step 1 parser -> v69+spans with the OpenAI 3-small embedder; step 2 Gemini embedder after the Q2 fix ships.
- Q2 (a): container-shared vector file + lock (this lane's code). Owner activates at midnight.
- Q3: span extractor v2 (meaning) at step 1, on OpenAI vectors.
- Q4 (a): accept spelling-only on span-fallback turns; revisit if the prod fallback rate > 5% over a week.
- Q5 (a): eval today, cap USD 0.25, crew runs it.

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

## Verification recipe (DRAFT, assumes the card's recommended answers; read-only)

The connector (`app/services/analytics_connector/datasets.py`) has no trace column: it proves the parser version and
the span CALL, not the embedding. The embedding proof is the turn drawer (owner) or one read-only SQL (owner).

Crew, Sorento Chat connector, after each owner flip (T = flip time, Malaysia time):
1. `chat_query` dataset `turn_costs`, period from T, group_by `prompt_version`: every turn after T+60 s (prompt cache
   `ai_prompt_registry.py:38`) shows the new version number.
2. `chat_query` dataset `llm_calls`, period from T, filter `feature` eq `chatbot_span_extract` (`span_extract.py:28`),
   group_by `model`, `was_answered`: one call per parser turn, model gemini-3.5-flash-lite, was_answered true on almost
   all. Zero rows = spans did not run (wrong text: marker line missing).
3. Same, `feature` eq `chatbot_parser`: count of parser calls ~= span calls (staff Console dry runs aside).

Owner, CRM UI (System Management > Chat History > open a turn after T > the span pass section,
`SpanPassSection.tsx:27-38`): the call line reads `gemini / gemini-3.5-flash-lite | label | <embedding model> | N ms`.
- Step 1 (OpenAI embedder): embedding part reads `text-embedding-3-small`; `spelling only` = that worker's cache not
  warm yet (normal for minutes after a restart, not after).
- Step 2 (Gemini): reads `gemini-embedding-001`. Meaning used = a candidate badge `meaning 0.6x-0.9x` on some span
  (`list_resolver.py:388-394`: only the winning signal is shown, so a spelling win hides the meaning score). Ask a
  message with a Malay or Chinese category word (e.g. "ada stok 马桶?") to force a meaning match.

Owner read-only SQL (prod, optional, one hour after a flip):
```sql
-- span turns since the flip, with the embedder each used and how many spans were placed by meaning
SELECT ev->>'embedding_model' AS embedder, (ev->>'fallback')::bool AS fallback, count(*) AS turns,
       sum((SELECT count(*) FROM jsonb_array_elements(ev->'spans') s
            WHERE s->'candidates'->0->>'signal' = 'meaning' OR s->>'matched_by' = 'meaning')) AS meaning_spans
FROM chatbot.turns t, jsonb_array_elements(t.trace) ev
WHERE t.created_at > now() - interval '1 hour' AND ev->>'kind' = 'span_extract'
GROUP BY 1, 2;
```
Pass: `embedder` = the expected model on most turns, `meaning_spans` > 0, fallback turns a few percent.
(Checked on dev sorento_explore1020, 30 days: gemini-embedding-001 48 turns / 31 meaning spans; unwarmed 41 / 0; fallback 2.)

Backend log (owner or crew with log access): one INFO line per worker
`lookup lists warm: N texts cached on <model> in S s` (`lookup_lists.py:1072-1075`); a WARNING
`lookup lists warm failed` with 429 = the burst problem (card Q2).

## Rollback (labels only, live within 60 s, no deploy)

- Spans off: AI Assistant > Prompts > `chatbot_semantic_parser` > move production label back to v69.
- Gemini embedder off: `chatbot_lookup_embedder` production label > clear provider and model (= OpenAI 3-small).
- Span model: `chatbot_span_extractor` production label > back to v1 / previous model.
Order when rolling back both: embedder first only if the parser stays on spans; otherwise parser first (the n-gram
path reads OpenAI vectors only, `lookup_lists.py:307`).

## Owner steps (DRAFT, assumes the card's recommended answers)

Before: run the read-only check (prod):
```sql
SELECT l.name, v.version, l.provider, l.model, md5(v.template) FROM ai_prompt_labels l
JOIN ai_prompt_versions v ON v.id = l.version_id
WHERE l.label = 'production' AND l.name IN ('chatbot_semantic_parser', 'chatbot_span_extractor', 'chatbot_lookup_embedder');
```
Expect parser v69 md5 8c77b4eb, span extractor v1, embedder row with provider/model empty.

Step 1 (spans on, OpenAI vectors; no deploy):
1. AI Assistant > Prompts > `chatbot_span_extractor` > production label: provider gemini, model gemini-3.5-flash-lite.
2. `chatbot_semantic_parser` > new version: paste `crew/state/eval/span-pass-prod/v69-spans.txt` (md5 57d7d412) > save.
3. Move the production label to that version (keep provider/model as v69's label had them).
4. Tell crew the time; crew runs the verification recipe. Rollback = label back to v69.

Step 2 (Gemini vectors; after the Q2 warm fix is deployed):
1. `chatbot_lookup_embedder` > production label: provider gemini, model `gemini-embedding-001` (exactly).
2. `chatbot_span_extractor` > move production label to v2 (the "meaning" version from eem_0003), same model.
3. Watch the backend log for `lookup lists warm: N texts cached on gemini-embedding-001` (one per worker).
4. Tell crew the time; crew re-runs the verification. Rollback = clear embedder provider/model; span label back to v1.
