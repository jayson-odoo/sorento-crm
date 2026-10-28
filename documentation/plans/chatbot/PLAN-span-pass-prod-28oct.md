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
- Warm-up: per process, no shared store (`lookup_lists.py:856`); `WORKERS` default 4 per colour (`gunicorn.conf.py:44`),
  but prod runs 8 (BACKEND-MEMORY #1950, prod measurement 28 Oct; 8 -> 4 is an open owner decision); startup event per
  worker (`main.py:329,415`), lazy warm per turn too (`engine.py:1270,1335`). ~4,652 texts on dev, ~7,035 on prod (#1950)
  / 100 per Gemini request = 47-71 requests per process. Measured 27 Oct on ONE process: 429 part-way at ~1.5k texts/min
  (AC-S3-13). Eight warms at once (start-up OR the label flip itself) = ~56k texts on prod. After 3 retries the fill gives up
  (`lookup_lists.py:916-928`); turns stay spelling-only until every text is cached (`:1086-1091`).

## Steps

1. Card (crew ask) - answered ~15:4x.
2. Eval on dev (crew runs live): `crew/state/eval/span-pass-prod/run.sh live` + `score_ab.py` (arm A = this morning's
   v68.txt run on the same ids); free stub passed 20/20 (span v2, 3-small vectors, spans ran on every row).
3. Code: red 91af4278bf (tester) -> coder -> reviewer, PR #1959.
4. Verification + rollback recipe below.
5. Activation below (owner).

## Verification recipe (read-only; crew + owner)

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
`lookup lists warm: N texts cached on <model> in S s (F from the shared file)` (`warm` in `lookup_lists.py`; the
shared-file count is new in #1959); a WARNING `lookup lists warm failed` with 429 = the burst problem (card Q2).

## Rollback (labels only, live within 60 s, no deploy)

- Spans off: AI Assistant > Prompts > `chatbot_semantic_parser` > move production label back to v69.
- Gemini embedder off: `chatbot_lookup_embedder` production label > clear provider and model (= OpenAI 3-small).
- Span model: `chatbot_span_extractor` production label > back to v1 / previous model.
Order when rolling back both: embedder first only if the parser stays on spans; otherwise parser first (the n-gram
path reads OpenAI vectors only, `lookup_lists.py:307`).

## Activation (owner; the midnight window is fine)

What ships where:
- Step 1 needs NO release: labels and one pasted prompt version only. It can run any time after crew's eval (Q5) passes.
- Step 2 needs the release that carries PR #1959 (the shared vector file). Merge, then crew dispatches `deploy.yml` and
  the owner approves it in the GitHub `production` environment. Check it is live before step 2: the backend log after the
  deploy shows `lookup lists warm: N texts cached on text-embedding-3-small in S s (F from the shared file)` lines (the
  "(F from the shared file)" part is new in #1959).

00:00, before anything (read-only SQL on prod, copy the output to crew):
```sql
SELECT l.name, v.version, l.provider, l.model, md5(v.template) FROM ai_prompt_labels l
JOIN ai_prompt_versions v ON v.id = l.version_id
WHERE l.label = 'production' AND l.name IN ('chatbot_semantic_parser', 'chatbot_span_extractor', 'chatbot_lookup_embedder');
SELECT version, md5(template), position('meaning' in template) > 0 AS has_meaning, commit_message
FROM ai_prompt_versions WHERE name = 'chatbot_span_extractor' ORDER BY version;
```
Expect: parser v69 md5 8c77b4eb; span extractor on v1; embedder with provider/model empty; one span extractor version
with `has_meaning` true and commit message "ENTITY-EXTRACT-MATCH S3: ..." (that is "v2" below, whatever its number).

Step 1, ~00:05 (spans on, span v2, OpenAI vectors). System Management > AI Assistant > Prompts:
1. `chatbot_span_extractor`: move the production label to the "meaning" version; set its provider gemini, model
   gemini-3.5-flash-lite.
2. `chatbot_semantic_parser`: new version, paste `crew/state/eval/span-pass-prod/v69-spans.txt` (md5 57d7d412, 102,624
   chars; it is v69 with its last line `== LOOKUP LISTS ==` changed to `== LOOKUP SPANS ==`), save.
3. Move the parser production label to that new version, with the same provider/model v69's label has.
4. Wait 60 s (prompt cache), then System Management > Chatbot Console: send "ada stok 马桶?" as a staff contact. Open
   the turn in Chat History: the span pass section shows `gemini / gemini-3.5-flash-lite | label |
   text-embedding-3-small | N ms` and the phrase 马桶 with a meaning ("toilet" or similar).
5. Tell crew the time (T1). Crew runs the verification recipe at T1 + 30 min and next morning.
Rollback: parser label back to v69 (and span extractor label back to v1).

Step 2, any night after the #1959 release is live (Gemini vectors):
1. `chatbot_lookup_embedder`: production label provider gemini, model `gemini-embedding-001` (exactly this name; any
   other name switches meaning off, `list_resolver.py:59-75`).
2. Wait 60 s, then send the same Console turn twice, a minute apart. The first turn may read `spelling only` (that
   worker is warming); the backend log shows ONE worker `... cached on gemini-embedding-001 in ~1-5 min (0 from the
   shared file)` and the other workers, on their first turn, `(N from the shared file)` in under a second. The second
   Console turn's drawer reads `gemini-embedding-001`.
3. A `lookup lists warm failed` WARNING with 429 = the burst is still too big: roll back (below) and tell crew.
4. Tell crew the time (T2). Crew re-runs the verification recipe.
Rollback: clear the embedder label's provider and model (= OpenAI 3-small, already cached in every worker).
