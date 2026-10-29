# PLAN: LOOKUP-EMBED-CENTRAL - one source per lookup list, one lookup-vector table, one screen to see them

Status: CARD v3 + MOCK v3 filed for the owner (29 Oct 2026): owner answered v1 Q1-Q5 and v2 N1-N5; v3 adds the
embedder setting, the keep set (S1 pending), threshold tuning and performance. No code. Track: L.
Owner answered S1, T1, P1 (b), P2, G1, G2, M1 (a): BUILD (UAC `lookup-embed-central-acceptance-criteria.md`)
(`documentation/mockups/LOOKUP-EMBED-CENTRAL/index.html`).
BUILT (29 Oct 2026): slices 1-6 + review fix rounds 1-5 on PR #1967; reviewer READY, security-reviewer CLEAN, final
browser pass PASS (1280 / 375), owner hand test PASS (~23:35). Merged origin/main c97eda2785, lec_0001 re-parented onto
idea_capture_fields_0001 (single head lec_0003_lookup_words_sync). PR ready for review; crew labels ci and merges on green.

## Owner words (29 Oct 2026, verbatim)

- "it is either we use the lookup set, or we have embedding table, i want to centralize this" ... "I want the
  embedding to be centralized, meaning yes for those data I embed and can visualize maybe, but those lookup words for
  the word like dealer, project, category maybe, attachment type maybe will also be embedded and looked up
  semantically, i want this visibility".
- ~10:2x: "the lookup set, it cannot be always us maintaining it right? for example, attachment type comes from
  attachment type table, spec comes from spec table, category comes from category table, i cannot be configuring the
  lookup set every time a new record is added to these tables, it should be interlinked and I can just optionally add
  the lookup if alias are needed".
- Standing rule: semantic / parser only, no regex or word lists in code.

## Journey

The owner opens one screen, picks a list (Category, File type, Sales channel ...), sees every row the chatbot can
match, where each row comes from (its master table), every word it is matched on (name, code, aliases) and whether
that word has a vector for the live embedder. He types any phrase ("零售", "smart toilet") and sees the rows the span
pass would offer, with score and the list's floor. A new category or attachment type shows up there (and is matched)
without anyone touching a lookup set. When a row needs an extra word, he adds it once, on the alias home of that list.

## Facts (origin/main 98773e5aa9)

Rows already come from master tables, read live every turn:
- `load_rows` is called per turn (`app/services/chatbot/engine.py:1265`, `:1325`) and at start-up warm (`:1365`).
- Loaders: category `head/lookup_lists.py:647-685` (product_categories, searchable + active, plus class labels and
  `product_type` registry values as `type:` rows via `turn_runtime.product_type_names`, `turn_runtime.py:823-835`);
  spec `:503-543` (product_spec_registry); file_type `:546-561` (attachment_types via
  `chatbot_prompt_vars.py:314-334`, `:393`); brand `:564-582`; promotion_kind `:585-592`; location `:595-605`
  (warehouses); salesperson `:608-629` (sales_agents); customer `:632-644` (customers).
- The ONE list with no table: sales_channel, rows from code constant `SALES_CHANNELS = ("dealer", "project")`
  (`app/services/reports/ask.py:386`), loaded at `lookup_lists.py:693`, text = the code value only.

Aliases live in four different places today:
1. Master-table columns: `product_categories.search_synonyms` (`app/models/product.py:57`),
   `sales_agents.aliases` (`app/models/sales_agent.py:67`), `product_spec_registry.synonyms` / `user_synonyms`
   (`app/models/product_spec.py:66`, `:120`), and attachment_types.description split on `, ; /` into words
   (`chatbot_prompt_vars.py:362-375`).
2. Lookup sets keyed by option value = the master record's name or code, wired by set_key in code:
   `attachment_type_alias` (`chatbot_prompt_vars.py:341-359`), `brand_alias` (value = brand code,
   `turn_runtime.py:573-582`).
3. Code dict `PROMPT_SYNONYMS` (`lookup_lists.py:67-83`): 3 category entries (water tap, water closet, kitchen sink;
   they match the class-label `type:` rows, since category_name is code-like, e.g. `SRT-WC`) + 8 file type entries.
4. Code constant rows: SALES_CHANNELS above, no alias home at all.

`lookup_bindings` is NOT an alias link. A binding says "column T.C takes its values FROM set S" (a dropdown;
`app/models/lookup.py:72-90`), checked against an eligibility registry (`lookup_binding_service.py:24`), and
creating one requires every distinct existing column value to be an option already (`lookup_binding_service.py:41`).
Reusing it for aliases would force every attachment type / category into the set, exactly the upkeep the owner
rejects. Dev bindings today: complaints.* (4), purchase_requests.sponsor_subject / sales_type, forms.form_type;
`attachment_type_alias` has no binding (query on sorento_cagent_stack, 29 Oct).

Vectors:
- Per-process cache keyed `(model, sha1(text))` (`lookup_lists.py:898-908`), cap 20,000 (`:92`); a per-model shared
  file + flock per container (#1959, `:924-981`); start-up warm thread (`engine.py:1345-1385`, started at
  `app/main.py:416`); a turn embeds missing texts lazily inside a 3 s budget (`EMBED_TIMEOUT`, `lookup_lists.py:89`).
- Embedder = production label of prompt key `chatbot_lookup_embedder` (`lookup_lists.py:87`, `:1245-1257`); Gemini
  sized down to 1536 dims (`:914`), 100 texts per request (`:912`), 429 retry waits 15/30/60 s (`:919`).
- Two matchers, both comparing a phrase with EVERY text of a row (`LookupRow.texts`, `lookup_lists.py:124-135`):
  label, code, class label, alias column words, alias set words, attachment type description words (built by the
  loaders above); the best text wins.
  - Span path (prompt marker LOOKUP SPANS, `engine.py:1414-1446`): the span model names the phrase, then
    `list_resolver.resolve` (`head/list_resolver.py:344-420`) scores each row on exact (folded text equal, 1.000),
    spelling (trigram similarity, `:286`), partial (IDF-weighted share of the phrase's words a row word matches,
    `:290-305`) and vector (cosine, `:310-330`, any model). A row passes when ANY signal reaches its list floor
    (spelling / partial `FLOORS` `:43-54`; vector per model, gemini-embedding-001 table `:59-63`: category 0.70,
    file_type 0.65, sales_channel 0.65, brand 0.60, customer 0.75 ...); its score is the strongest signal; rows
    within 0.03 make the phrase ambiguous (`:77`). The span model may also hand an English form, tried first (`:350-360`).
  - Fallback / LOOKUP LISTS path (`engine.py:1274`, `lookup_lists.shortlist` `:349-396`): spelling + vector, but
    vector only for text-embedding-3-small (`lookup_lists.py:310`); with gemini it is spelling only. Its floors
    (`:46-50`) are 3-small ones.
  - Chinese words have no ASCII trigrams (`lookup_lists.py:160-163`): 零售 / 马桶 match by exact word or vector only.
  - Which marker prod's parser prompt carries: UNVERIFIED in this lane (SPAN-PASS-PROD lane owns it).
- RAG tables `embedding_documents` / `embedding_chunks` (`app/models/embeddings.py:72-150`): document chunks of
  business records, `document_id` FK NOT NULL, `is_current` / `superseded_at` versioning, `company_id`,
  `Vector(1536)`; fed by `embedding_queue` (`:29-62`). Different lifecycle from lookup words.

Dev sizes (sorento_cagent_stack, 15 Oct dev copy, read-only, 29 Oct): 114 categories (39 carry search_synonyms) plus
11 class labels and 44 `product_type` values as type rows; 22 attachment types, of which the file type loader offers 8
(the `chatbot_prompt_vars.py:322-331` filter: product-carried or unused) plus 1 certificate kind; 12 brands, 71
warehouses, 114 sales agents (23 with aliases), 5,864 customers, 53 spec keys. Category + file type + sales channel
rows = 438 distinct texts (502 with the 55 type rows + the certificate kind).

## Real examples (dev data, cached gemini-embedding-001 vectors, no API call made)

Vectors: `crew/state/eval/eem/s3/vec_store` (gemini-embedding-001, 1536 dims, written by the EEM S3 gate on the org
key, 27 Oct); 422 of the 502 category / type / file type / sales channel texts have one. Rows rebuilt from
sorento_cagent_stack as the loaders build them; scores computed by the LIVE span resolver code (`list_resolver`
`resolve`, `_score_list`, `_meaning_scores`, gemini floors) fed those vectors (mock v2 generator).

| Phrase | Verdict | Spelling (text) / floor | Vector (text) / floor | Notes |
|---|---|---|---|---|
| smart toilet | ambiguous: 5 Water Closet categories + class row Water Closet (+1) | 0.538 (toilet, alias column) / 0.40 | 0.759 (马桶, alias column) / 0.70 | passes by vector |
| toilit (typo) | ambiguous: 5 Water Closet categories, Toilet brush, Toilet seat | 0.400 (toilet) / 0.40 | none cached | passes by partial 0.83 (one edit) |
| mixer tap | resolved: Mixer tap (product_type row) by exact 1.000 | 1.000 / 0.40 | 0.991 / 0.70 | Kitchen tap 0.838, Shower tap 0.825 pass by vector but are 0.16 behind |
| high resolution photo | resolved: Product Photos by vector 0.708 | 0.273 (Photo, description word) / 0.50 | 0.708 (Photo) / 0.65 | Combo Image 0.601 fails |
| project | resolved: sales channel project by exact 1.000 | 1.000 | - | Product Photos 0.620 < 0.65, MISC 0.600 < 0.70: fail |
| 零售 | unresolved | 0 (no trigrams) | none cached | dealer row's only text is "dealer" |

Findings the screen makes visible:
- "零售" / "retail" can only reach dealer by vector today (no alias home for sales channel). With a
  `sales_channel_alias` option (dealer <- retail, 零售) they resolve exact at 1.000, no vector needed.
- CORRECTION of v1: v1 showed the 3-small floors (`lookup_lists.py:46-50`) and claimed gemini noise clears them.
  The span path uses the gemini floors (`list_resolver.py:59-63`): project -> Product Photos 0.620 and MISC 0.600
  FAIL there. No floor re-score lane is needed on this evidence.
- PROMPT_SYNONYMS barely reaches dev rows: entries match a row by exact label (`lookup_lists.py:498-500`). Category
  keys: "water closet" and "kitchen sink" match class rows; "water tap" matches nothing (the class is "Tap"). File type
  keys photo / image / video / drawing / technical drawing / 3d model / certificate match no dev type name
  (types are "Product Photos", "Certification", ...); "installation guide" adds "installation manual", already a
  description word. The words themselves are mostly data already: every Water Closet category carries water closet,
  wc, toilet, toilet bowl, closet, tandas, 马桶, 坐厕; Tap carries paip, kepala paip, water tap, 水龙头. UNVERIFIED on
  prod (no prod reads in crew lanes; owner-run read-only SQL in "Rollout").

## Owner answers to card v1 (29 Oct ~09:3x, relayed by crew)

- Q1 (a): keep the master alias columns; one optional alias set per list without one; delete PROMPT_SYNONYMS.
- Q2 (a): sales channel rows from code + `sales_channel_alias` set. REUSE #1964 (CHAT-CHANNEL-LOOKUPSET), which
  seeds that set (`alembic/versions/chan_alias_0001_sales_channel.py:28`, dealer <- retail, retailer, 经销商, 零售,
  peruncit at `:42`). This lane adds nothing for the set; it only shows it.
- Q3 (a): sync job every 10 min + "Embed missing" button, plus label flip and the lazy turn path.
- Q4 (a): grid + Try a phrase, no plot; Try a phrase shows the vector AND spelling scores (mock v2).
- Q5 NOT separate (owner, verbatim): "we will use gemini for embedding already, so i think embedding cannot stay
  separate, need to come into play here". Business-record chunks move to gemini-embedding-001 and into the same
  store and screen. Card v2 below is reworked for that.
- Card v2 answers (29 Oct): N1 (a) lookup words as documents in the existing family. N2: prod's lookup label is
  already gemini (owner flipped it 29 Oct, lookup words only); records (a) write both, search 3-small until 100%.
  N3 (a) capped resumable batch job. N4 (c) keep the 3-small rows, never delete. N5: the switch is ONE setting with a
  100% guard for records; updated 29 Oct: "better to switch the embedding to a setting instead of a prompt" ->
  System Settings > Embeddings tab (provider + model), prod's label value copied in on deploy, label = fallback only.
- Owner notes on mock v3: threshold tuning in this lane; performance must be covered (both in card v3).
- Card v3 answers (29 Oct): S1 (a) keep set, but product = product_spec (spec sentence), not name + description
  ("description got noise"); T1 (a) keep floors, label 30+ meaning-only phrases in the build; P1 (b) ("anything that
  makes our system faster should be considered"): per-model partial index + per-source partial indexes for attachment
  and product_spec; P2 (a); G1 (a); G2 (a); M1 (a) drop mcp_tool + conversation_frame (owner confirmed 29 Oct).
- F1 (29 Oct): (a) keep the category floor at 0.70 (slice 6 re-check: 0.94 vs 0.97 at 0.71 is one phrase; report
  `sorento_crm_backend/scripts/eval/lookup_floors_report.md`). All gemini floors unchanged.
- Owner Lavish feedback on mock v3 (29 Oct 13:30): "1. ok" = mock v3 approved; screens built per it.
- Per-source index cost (scaled from the measured 25,090-row index: 193 MB, 34 s at 512MB): attachment 8,083 rows
  ~62 MB / ~11 s, product_spec 14,678 rows ~113 MB / ~20 s, per model; the keep-set index ~185 MB / ~33 s. Built
  CONCURRENTLY (slower; factor UNVERIFIED). Measured win: attachment-filtered p95 0.8 ms vs 127 ms (iterative scan).
- Owner question (29 Oct): "why we need to embed orders, products ah cause they are code right" -> answered in
  "Which business records are worth embedding" (S1 pending).

## RAG facts (origin/main, read by code; dev counts from sorento_cagent_stack, read-only)

- Store: `embedding_documents` (unique source_type + source_id, company_id; `app/models/embeddings.py:71-105`),
  `embedding_chunks` (Vector(1536), model_name / model_version / embedding_provider, is_current / superseded_at,
  company_id; `:108-154`), partial unique (source_type, source_id, model_name, model_version, chunk_index) WHERE
  is_current (`:144-153`); ONE HNSW cosine index over all rows, raw SQL only
  (`alembic/versions/142_pgvector_embedding_pipeline.py:117-118`). `embedding_queue` events (`:28-68`).
- Model: plain settings, provider openai / text-embedding-3-small / v1 / 1536 (`app/config.py:314-317`); the
  worker POSTs to OpenAI directly (`app/services/embedding_worker.py:646-676`) and needs OPENAI_API_KEY
  (`:649-650`). `OpenAIProvider.embed` hardcodes text-embedding-3-small (`app/services/llm_provider.py:555-558`).
- Two models can already sit side by side: the skip check (`embedding_worker.py:898-936`) and the supersede
  (`:977-982`, `embedding_service.py:227-239`) are per model, so a rebuild under a new model writes new rows and
  leaves the old model's rows current.
- Readers, NONE filter by model_name and ALL embed the query with the OpenAI model:
  `EmbeddingReadService.search_current` (`embedding_service.py:246-276`) used by `/external/rag/search`
  (`app/api/v1/external/rag.py:57`, own OpenAI POST `:23-43`), `fuzzy_resolver.py:56`,
  `project_registration_service.py:200`; `search_tool_candidates` (`embedding_service.py:325`) used by
  `/external/rag/tool-search` (`rag.py:98`) and the AI assistant (`ai_assistant_service.py:1454`); raw `<=>` SQL in
  `entity_resolver.py:3039-3080` and `:6009-6061`; `frame_service.py:197-222`.
- Throughput: the `embedding_job_processor` task runs every 30 s (`alembic/versions/143_seed_embedding_job_processor_task.py:25-30`),
  10 Redis + 10 DB items per run (`config.py:296`), one document per item: about 2,400 documents per hour.
- Dev volume: 269,914 current chunks (269,431 documents) over 21 sources, all text-embedding-3-small, 50.4M
  characters; biggest: spo_allocation 82,534, order 74,902, order_line 40,289, promotion_product 24,719, product
  15,403. Table sizes: chunks 5,066 MB, documents 225 MB, queue 2,479 MB (888,712 pending + 138,874 dead_letter:
  the dead dev OpenAI key). Other 1536 vectors: `ai_assistant_wishlist_clusters` (0 rows on dev),
  `ai_assistant_unanswered_queries` (4 rows) (`app/models/ai_assistant.py:233`, `:257`).

## ARCHITECTURE (v3)

- One table family for every vector: `embedding_documents` + `embedding_chunks` (owner N1 (a)). Lookup words are
  documents of `source_type = 'lookup_word'`, `source_id = '<list>:<row key>'`, one chunk per word, `company_id` =
  the row's company or NULL. Business records: only the keep set (S1, section "Which business records ...").
- One embedder setting: a new Embeddings tab in System Settings (`user-management/settings/layout.tsx:306-361`), provider + model (owner N5, 29 Oct: "better to switch the
  embedding to a setting instead of a prompt"). Two `system_settings` columns (`embedding_provider`,
  `embedding_model`), added to BOTH manual dict builders (CLAUDE.md lesson). On deploy the migration copies prod's
  current `chatbot_lookup_embedder` production label (gemini / gemini-embedding-001, flipped by the owner 29 Oct) into
  it, so nothing changes for the owner. The label is read only as a fallback while the setting is empty, and removed
  in a later lane. `lookup_lists.py:1243-1259` and the worker read the setting through one function.
- One embed function `embed_texts(texts, provider, model)` (Gemini batchEmbedContents, 100 per request, 1536 dims,
  429 waits `lookup_lists.py:919`; OpenAI kept behind it). Worker, lookup lists, every reader, AI assistant call it;
  the direct OpenAI POSTs (`embedding_worker.py:666-676`, `rag.py:23-43`, `llm_provider.py:555-558`) go.
- Records search model (`embedding_records_search_model`, a third column, written only by code): the model every
  record reader embeds the question with and filters `model_name` on. It moves to the setting's model only when the
  backfill job finds that model at 100% of the keep set (the guard, shown on the screen). Until then new and changed
  records are written with BOTH the setting's model and the search model (owner N2 (a)).
- Lookup words follow the setting at once (as the label does today): a turn embeds its own misses, the 10-min sync
  embeds the rest (owner Q3 (a)).
- Indexes: one partial HNSW index per model over the keep set (`WHERE model_name = '<m>' AND is_current AND
  source_type IN (<keep set>)`); source-filtered readers set `hnsw.iterative_scan = relaxed_order` (P1).
- Fixed classes: rows from master tables, aliases from one home per list, vectors from one family under one setting;
  nothing per-list or per-source special-cased beyond the keep set list.

## Why re-embedding is needed (plain words)

An embedding model turns a text into a list of 1,536 numbers. Each model invents its own number system: "toilet"
from OpenAI and "toilet" from Gemini are two unrelated lists of numbers, like the same word written in two different
secret codes. A search embeds the QUESTION with one model and compares it with the stored numbers; if the stored
numbers came from the other model the scores are noise (a right answer can score below a wrong one). So when the
setting changes model, every stored text has to be embedded again with the new model before searches may use it,
and until that is finished searches keep using the old model's numbers. That is what the guard enforces.

## Card v3

### Per list

| List | Rows from (auto) | Alias home | Embedded as |
|---|---|---|---|
| Category | product_categories (searchable, active) | search_synonyms column | lookup_word docs, sync + lazy |
| Class / type rows | distinct class_label + product_type registry values | union of the class's categories' search_synonyms; registry user_synonyms | same |
| Spec | product_spec_registry | synonyms / user_synonyms columns | same |
| File type | attachment_types (non-certificate + certificate kinds) | description words + attachment_type_alias set | same |
| Brand | brands (active) | brand_alias set | same |
| Promotion kind | promotion types | none until needed | same |
| Location | warehouses (active) | none until needed | same |
| Salesperson | sales_agents (active) | aliases column | same |
| Customer | customers (active, scoped) | none | same |
| Sales channel | code values dealer / project | sales_channel_alias set (#1964) | same |
| Business records (keep set, S1) | the RAG producer (`embedding_change_listener.py:378-401`) | n/a | record docs, queue + backfill job |

### Switch flow (owner N2 (a), N3 (a), N4 (c), N5 as updated)

1. Deploy: the setting holds gemini / gemini-embedding-001 (copied from the label). Lookup words: gemini, as today.
   Records: search model stays text-embedding-3-small; writes go to both models.
2. The capped, resumable backfill job embeds the keep set with the setting's model: 25,090 chunks on dev, ~251
   requests, ~13 min at 20 requests/min (USD ~0.19, price UNVERIFIED). Progress per source on the screen.
3. At 100% the job builds the model's partial HNSW index (CONCURRENTLY) and moves the records search model to the
   setting's model. Writes to the old model stop.
4. 3-small rows are kept, never deleted (owner N4 (c)). Switching back = the owner changes the setting; the same guard
   runs; only documents changed since then are re-embedded (the per-model skip check, `embedding_worker.py:898-907`).
- Dev: the OpenAI key is dead, so 3-small writes fail (shown as failed, not blocking); dev reaches step 3 in minutes.

### Threshold tuning (owner note on mock v3: in this lane)

Done now, zero API spend: `scratchpad/tune/tune_floors.py` (copied into the lane at build) scores the EEM labelled gold
(`crew/state/eval/eem/labels/gold_all.jsonl`, 338 messages) with the cached gemini vectors against the current
gemini floors (`list_resolver.py:59-63`), sweep 0.55-0.85.

| List | Positives | Near-miss negatives | Floor now | P / R now | Meaning-only positives | Verdict |
|---|---|---|---|---|---|---|
| category | 24 | 72 | 0.70 | 0.35 / 1.00 | 1 | keep 0.70 |
| spec | 16 | 48 | 0.75 | 0.59 / 1.00 | 0 | keep 0.75 |
| file_type | 15 | 45 | 0.65 | 0.88 / 0.93 | 1 | keep 0.65 |
| brand | 10 | 30 | 0.60 | 0.83 / 1.00 | 0 | keep (under 15 positives) |
| promotion_kind | 3 | 9 | 0.75 | 1.00 / 0.67 | 0 | keep (under 15) |
| location | 5 | 15 | 0.65 | 0.25 / 1.00 | 0 | keep (under 15) |
| salesperson | 8 | 24 | 0.70 | 1.00 / 1.00 | 0 | keep (under 15) |
| customer | 24 | 72 | 0.75 | 0.69 / 0.75 | 1 | keep 0.75 |
| sales_channel | 3 | 3 | 0.65 | 1.00 / 1.00 | 0 | keep (under 15) |
| spec_key | 10 | 30 | 0.75 | 0.80 / 0.80 | 0 | keep (under 15) |

- End to end (list_resolver.resolve on the gold spans, cached vectors): 239 of 243 correct, 0 wrong, at the current
  floors. Precision above is low by construction (3 near-miss negatives per positive); what matters is that only 3
  positives in the whole gold depend on the vector alone, so there is nothing to tune a floor on.
- Skipped for no cached vector: category 5, customer 9, file_type 3, location 1, promotion_kind 2, salesperson 3,
  spec 6 phrases.
- Build step (T1): label 30+ meaning-only phrases per main list (category, file type, brand, sales channel) from the
  201 dev resolver tokens that found no match (masked) and the screen's Try a phrase, embed only those phrases
  (~USD 0.0001), re-run the script, change a floor only where precision >= 0.95 holds.

### Performance (owner note on mock v3: "need to be careful of the performance")

Measured 29 Oct on the dev Mac (PostgreSQL 17.7, pgvector 0.8.2, maintenance_work_mem 64MB, shared_buffers 128MB);
prod hardware and settings UNVERIFIED (owner-run `SHOW` lines below).

Today, 270k chunks, one HNSW index over all rows (2,206 MB):
| Reader shape | Plan | p50 | p95 |
|---|---|---|---|
| `search_current` (`embedding_service.py:255,272`, ORDER BY similarity DESC) | Seq Scan + Sort of every vector | 7,468 ms | 13,457 ms |
| same + model filter | same | 10,860 ms | 23,948 ms |
| same, rewritten ORDER BY distance + model | HNSW | 61 ms | 117 ms |
| `entity_resolver` tier3, product filter (`:3039-3080`) | HNSW, post-filter | 3.5 ms | 11.3 ms |
- The filtered HNSW search returned 0 of 5 product rows for an order-like question (post-filter loss); pgvector's
  iterative scan returned 1 row after 7.7 s; an exact product-only scan returned 5 rows in 276-588 ms.
- `search_current` serves `/external/rag/search`, `fuzzy_resolver.py:56` (staff order / incoming / GRN list search)
  and the project duplicate check: each such call reads every vector today. The rewrite is part of this lane.

Keep set, 25,090 chunks (throwaway copy of the dev vectors, dropped after):
| Measure | Result |
|---|---|
| Partial HNSW build, maintenance_work_mem 64MB | 131 s ("graph no longer fits after 9,756 tuples") |
| Partial HNSW build, 512MB, 2 parallel workers | 33-34 s |
| Index size | 193 MB |
| Unfiltered search, partial index | p50 1.4 ms, p95 3.7 ms, 0/39 short |
| Product-filtered, partial index | p95 1.5 ms, 2/39 queries returned < 5 rows |
| Attachment-filtered, partial index | p95 1.2 ms, 37/39 short |
| Attachment-filtered + iterative scan | p95 127 ms, 0/39 short |
| Attachment-filtered, per-source partial index | p95 0.8 ms, 0/39 short |
| form (46 rows), exact scan | p95 2.6 ms |

- Target: DB part of a record search p95 <= 150 ms (keep set with iterative scan: 127 ms on dev). The chatbot's
  lookup-word matching stays in process (no DB per turn).
- Every reader's SQL carries the literal predicate of the partial index (`model_name = '<m>' AND is_current AND
  source_type IN (...)`); SQLAlchemy + psycopg2 inline parameters client side, so the planner can match it
  (a server-side prepared generic plan would not; none is used, UNVERIFIED for every call site until the build).
- Per reader after the change: search_current -> ORDER BY distance, partial index; entity_resolver tier3 /
  `_rag_resolve_phrase` -> partial index + iterative scan; frame_service (conversation_frame, 118 rows) and tool
  search (mcp_tool, 186 rows) -> exact scan (planner picks it, ~3-6 ms); fuzzy_resolver -> via search_current plus a
  similarity floor (today none, `fuzzy_resolver.py:55-129`); project duplicate check -> via search_current.
- Backfill IO: ~150 MB of vector writes in ~13 min at 20 requests/min (100-row inserts per request) plus one
  193 MB index build CONCURRENTLY at the end with maintenance_work_mem 512MB for that session only (CONCURRENTLY
  takes longer than the 34 s measured; UNVERIFIED factor). Small enough to run any time; the cap is a setting.
- Disk: +~0.35 GB for the gemini keep set. Replacing the 2.2 GB all-rows index by a 3-small partial index over the
  keep set frees ~2 GB (P2; the DROP INDEX is held for the owner).

Owner-run read-only checks on prod:
```sql
SHOW maintenance_work_mem; SHOW max_parallel_maintenance_workers; SHOW shared_buffers;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT pg_size_pretty(pg_relation_size('ix_embedding_chunks_embedding_hnsw')) AS hnsw_size;
```

### Edge cases

- Setting changed while a backfill runs: the job restarts for the new model; search stays on the last 100% model.
- A chunk that fails 3 times (bad text, 429 storm): counted as failed, listed on the screen (G1).
- Dropped sources: listeners stop queuing them, readers stop asking for them, their rows stay.
- Company-scoped rows: record readers keep `_embedding_company_filter` (`embedding_service.py:54-79`); lookup words
  list under the viewer's scope.
- Other dims (3072): refused by embed_texts.

### Cost (all USD, Gemini price UNVERIFIED)

Lookup words ~0.01 per model; records keep set ~0.19 once; tuning phrases ~0.0001; steady state: only new or edited
text. No lane run spends the org key beyond the tuning phrases (ledger line first).

### Migration, rollback, prod rollout

- Migration: three `system_settings` columns (embedding_provider, embedding_model, embedding_records_search_model)
  with the label copy; the partial HNSW index for 3-small over the keep set (CONCURRENTLY). The gemini index is built
  by the job at 100%. No table created.
- Rollback: revert the PR before the search model moves: clean. After it moved: set the search model column back to
  text-embedding-3-small first (3-small rows were never removed), then revert.
- Prod steps: (1) owner runs the read-only checks; (2) deploy; (3) Embeddings screen: lookup words green; (4) start
  the records backfill (~13 min); (5) watch the guard move search to gemini; (6) later, the held DROP of the old
  all-rows index (P2).

### Questions v3 (S1 is in its own ask)

T1. Floors: (a) keep the current gemini floors now; label 30+ meaning-only phrases per main list in the build and
re-run the tuning before the PR; (b) change floors now on 3 meaning-only cases. Recommend (a).

P1. Source-filtered record search: (a) one partial index per model + iterative scan (p95 127 ms); (b) also a
per-source partial index for attachment and product (p95 < 1 ms, two more indexes per model). Recommend (a).

P2. The old 2.2 GB all-rows HNSW index: (a) replace by a 3-small keep-set partial index, then an owner-run DROP of
the old one; (b) keep it. Recommend (a): frees ~2 GB, and the old index serves only dropped sources.

G1. A chunk that keeps failing: (a) after 3 tries it counts as failed, is listed on the screen, and does not block
the guard; (b) the guard waits for literally every chunk. Recommend (a): one bad text must not hold search on the
old model forever.

G2. Backfill cap: (a) 20 requests/min default, editable beside the setting; (b) fixed in code. Recommend (a).

## Which business records are worth embedding (owner question 29 Oct: "code sucks against embedding, no?")

Evidence (no prod reads; the chat connector's bot_turns carry no resolver tier, so prod frequency is UNVERIFIED):
- What decides a lookup today: dev turn traces (sorento_cagent_stack = prod copy, chatbot.turns, 6-22 Sep, 1,794
  resolver gates, `trace[].raw.resolve_gate.ctx.gate.resolutions[].matches[0].match_tier`): 561 tokens; 0 decided by
  embedding. product: exact 192 / prefix 26 / substring 4; attachment_type: substring 46 / word 34 / exact 4 / prefix 2;
  inbound_shipment exact 27; customer_order exact 20; certificate exact 3; customer exact 2; no match 201. The
  semantic step still ran on 356 gates: p50 1,428 ms, p95 2,993 ms, max 7,641 ms.
- Order of tiers in the chatbot's resolver (`entity_resolver.resolve_references`): exact `:5475` -> prefix /
  substring `:5505` -> head-code retry `:5572` -> LLM code reader `:5615` -> cross-type `:5703` -> embedding `:5766`,
  only for tokens still empty, similarity >= 0.80 and gap >= 0.05 (`:2936-2937`), at most 1 hit.
- Code share = share of value tokens that are codes / numbers / ids (300 random current chunks per source).

| Source | Chunks (dev) | Embedded text (`embedding_worker.py`) | Code share | Read by | Recommend |
|---|---|---|---|---|---|
| spo_allocation | 82,534 | SPO no, shipment / product uuid, qty, status (`:389-398`) | 0.59 | tier3 + entity filters (exact wins) | DROP |
| order | 74,902 | order no, type; debtor, salesman, transporter, remarks (`:471-481`) | 0.67 | tier3, entity filters | DROP (numbers exact; names via customer) |
| order_line | 40,289 | uuids, qty, price (`:605-614`) | 0.71 | generic /external/rag/search only | DROP |
| promotion_product | 24,719 | product code, promo price, %; promo line, product name (`:341-350`) | 0.74 | generic only | DROP (promotion + product cover it) |
| product | 15,403 | code, category, brand; name, description (`:127-137`) | 0.81 | tier3, entity filters, fuzzy_resolver | NAME + DESCRIPTION ONLY |
| product_attachment | 12,318 | uuids, primary, sort, fixed keywords (`:437-447`) | 0.13 (boilerplate) | generic only | DROP |
| attachment | 8,083 | file name, description; path, uuid (`:212-224`) | 0.10 | tier3, entity filters | KEEP (file name + description) |
| inbound_shipment_line | 4,530 | uuids, qty, status, batch (`:373-382`) | 0.43 | generic only | DROP |
| picking_header | 2,595 | picking / SPO no, statuses, notes (`:405-414`) | 0.32 | tier3 | DROP |
| picking_line | 957 | uuids, qty, condition (`:421-430`) | 0.57 | generic only | DROP |
| customer | 796 | code, country, email, phone; name (`:547-556`) | 0.58 | tier3, entity filters, fuzzy_resolver | DROP (names: trigram) |
| promotion_attachment | 791 | uuids, fixed keywords (`:454-464`) | 0.27 (boilerplate) | generic only | DROP |
| promotion | 685 | dates; description (`:191-198`) | 0.62 | tier3, entity filters | KEEP (description) |
| certificate | 569 | scheme, number, covered codes; body, issuer, title (`:256-267`) | 0.64 | tier3 | KEEP (title, issuer, body) |
| inbound_shipment | 365 | shipment no, status, dates; notes (`:357-366`) | 0.38 | tier3, entity filters | DROP |
| mcp_tool | 186 | capability text, aliases, typical questions (`:101-114`) | 0.05 | /external/rag/tool-search, AI assistant | KEEP |
| conversation_frame | 118 | frame summary (`:621-623`) | 0.06 | /external/memory/frames/search (chatbot recall deleted, `chatbot/turn/memory.py:452-457`) | KEEP (n8n use UNVERIFIED) |
| form | 46 | form name, purpose (`:289-298`) | 0.14 | tier3, entity filters | KEEP |
| transporter | 14 | code; name (`:570-576`) | 0.52 | tier3, entity filters | DROP (trigram) |
| order_status | 8 | code; name, description (`:590-598`) | 0.24 | generic only | DROP |
| schema_doc | 6 | field keys, labels (`:316-325`) | 0.01 | generic only | DROP |
| project | 0 on dev | title, developer, state, mukim (`:498-506`) | - | duplicate check `project_registration_service.py:200` | KEEP |

Readers that matter (`entity_resolver.py`, `embedding_service.py`, `fuzzy_resolver.py`):
- Chatbot: `resolve_references` in process (`lanes/business/services.py:142-169`, `resolve_gate.py:408/1579`,
  `head/grounding.py:491`, `engine.py:9503`); embedding is the last tier and decided 0 of 561 tokens on the traces.
- Staff list filters (`resolve_entities_to_filters` `:6182`): substring -> trigram -> embedding (min 0.20, top 15).
- `fuzzy_resolver.py:55-129` (order / incoming / GRN list search): on EVERY call it ORs the top 10 vector hits'
  codes / names into the ILIKE filter with NO similarity floor, so a staff search can pull in unrelated customers or
  products. Dropping customer embeddings and keeping product name + description with a floor fixes it.
- `/external/rag/search` (`rag.py:46-85`, all sources): no in-repo caller; the n8n consumer is UNVERIFIED.

Effect of the recommendation:
- Keep set: product (name + description), attachment, promotion, certificate, form, mcp_tool, conversation_frame,
  project = 25,090 chunks today (9.3% of 269,914), ~5.1M characters (~1.3M tokens): ~USD 0.19 to re-embed on
  gemini-embedding-001 (price UNVERIFIED), ~251 batch requests: minutes with a capped job (vs ~112 h on today's
  queue for all 270k). Gemini vectors + HNSW for 25k chunks: ~0.35 GB instead of ~3.9 GB.
- Dropped sources stop writing (no embed calls, no queue churn: on dev 680,984 of the 888,712 pending queue events
  are order + spo_allocation) and readers stop asking for them; their 3-small rows stay (owner N4 (c)).
- A filtered vector search on a 25k index where products are 60% keeps its results (on the 270k shared index a
  product-only search returned 0 of 5 rows, measured 29 Oct; see Performance).

## Build slices (lead pattern: tester red tests first per slice, one coder kept alive, reviewer + security-reviewer once)

Track L. Migration: one alembic revision (head id <= 32 chars, re-parent with `./scripts/alembic-reparent.sh`), plus
idempotent SQL for crew at `/Users/tehjayson/Documents/foundryx/crew/state/migrations/LOOKUP-EMBED-CENTRAL.sql`
(ADD COLUMN IF NOT EXISTS; index DDL CONCURRENTLY IF NOT EXISTS; the P2 DROP INDEX held for the owner). Tests run on a
throwaway Postgres DB via `SORENTO_ENV_FILE=.env.ci-tests` (never the shared dev DB), pytest `-n 2`, touched files only,
plus `tests/test_schema_uuid_id_principle.py` and `tests/test_list_pagination_limit.py`.

1. **Setting + embed function** (AC-LEC-1..4): system_settings columns (both dict builders), migration copying the
   `chatbot_lookup_embedder` label, `resolve_embedder()`, `embed_texts()`; lookup_lists production embedder
   (`lookup_lists.py:1243-1259`), worker `_embed_text_chunks` (`embedding_worker.py:646-676`), `rag._embed_query`
   (`rag.py:23-43`), `OpenAIProvider.embed` (`llm_provider.py:555-558`) all go through it. Tests: settings GET/PUT
   carry the fields; migration fills from a seeded label and leaves NULL without one; resolver order setting > label >
   default; embed_texts batches 100, refuses non-1536, no other module posts to an embeddings URL (grep test).
2. **Keep set + product_spec + readers** (AC-LEC-5..12): keep-set constant; listeners / worker skip other sources;
   `enqueue_spec_embedding` wired on rendered_text change; readers' source maps `product` -> `product_spec`
   (`entity_resolver.py:2913-2935`, `_rag_resolve_phrase` callers `:6036`, `fuzzy_resolver.py:56` canonical model);
   model filter on every reader; `search_current` ORDER BY distance (`embedding_service.py:255,272`); per-model keep-set
   partial index + per-source indexes (attachment, product_spec) with literal predicates; iterative scan elsewhere;
   fuzzy_resolver floor. Tests: AC-LEC-9 two-model fixture (a 3-small and a gemini chunk, search returns only the
   search model's); EXPLAIN shows the partial / per-source index; k of k on a 30% source; fuzzy floor drops a far hit.
3. **Dual write, backfill job, guard** (AC-LEC-8, 13, 14): RQ task on an existing queue, rpm cap setting, resumable,
   failed after 3 tries, guard flips the search model and builds the model's indexes. Tests: dual write while models
   differ; rerun skips done docs; failed rows do not block; flip only at 100%; switching back re-runs.
4. **Lookup words in the family** (AC-LEC-15..18): lookup_word documents, 10-min scheduled sync + embed-missing task,
   worker start SELECT replaces the shared file (`lookup_lists.py:924-981`, `engine.py:1345-1385`), PROMPT_SYNONYMS
   removal (`lookup_lists.py:67-83`, `_with_synonyms` `:498-500`) + one-off script. Tests: sync creates / updates /
   retires docs by source_hash; start-up load makes no provider call; a turn miss writes a chunk; dict gone and the
   script's dry run lists the 3 words missing on dev.
5. **API + FE** (AC-LEC-19..24): `/api/v1/system/embeddings/*` endpoints (permission master_data.lookup_sets.view /
   .edit), Embeddings page + menu entry (`config/menu.config.tsx:1131` group), System Settings Embeddings tab
   (`user-management/settings/layout.tsx:306-361`), alias option master picker (lookup-sets OptionFormDialog). Mock:
   `documentation/mockups/LOOKUP-EMBED-CENTRAL/index.html`. vitest on touched components; agent-browser 1280 + 375
   via sidebar on the crew test copy (crew runs it; hand test script at laneboard/scripts/<PR>.md).
6. **Floors re-check** (AC-LEC-25): copy `scratchpad/tune/tune_floors.py` into `sorento_crm_backend/scripts/eval/`,
   add 30+ masked meaning-only phrases per main list (category, file type, brand, sales channel) as a fixture, embed
   only the new phrases (ledger line first, ~USD 0.0001), re-run, table in the PR body.

### Slice 1 contract (names the tests and the code share)

- Migration `sorento_crm_backend/alembic/versions/lec_0001_embedding_setting.py`, revision `lec_0001_embedding_setting`,
  down_revision = main's head at build time (`unpaid_0001_chatbot_ar_role` on 98773e5aa9; re-parent before PR). Adds
  nullable `system_settings.embedding_provider` varchar(32), `embedding_model` varchar(128),
  `embedding_records_search_model` varchar(128) and `embedding_backfill_rpm` int default 20. Upgrade copies the
  production label of prompt key `chatbot_lookup_embedder` (provider, model) into provider / model when such a label
  exists, sets `embedding_records_search_model = 'text-embedding-3-small'`; idempotent; downgrade drops the 4 columns.
- `app/services/embedding_settings.py`: `resolve_embedder(db) -> tuple[str, str]` (setting, else the label via
  `ai_prompt_registry.agent_model(db, "chatbot_lookup_embedder")`, else `("openai", "text-embedding-3-small")`);
  `records_search_model(db) -> str`.
- `app/services/embedding_client.py`: `embed_texts(texts, provider, model, *, api_key=None) -> list[list[float]]`,
  unit-normalised, 1536 dims (Gemini `outputDimensionality` 1536, `batchEmbedContents`, <= 100 texts per request;
  OpenAI embeddings endpoint); raises `EmbeddingDimensionError` when a vector is not 1536 long. The only module that
  posts to an embeddings endpoint.
- System settings API GET returns the 4 fields; PUT accepts provider, model, backfill rpm; it never changes
  `embedding_records_search_model` (only the guard does).

### Slice 2 contract (keep set, product_spec, readers, indexes)

- `app/services/embedding_settings.py`: `RECORD_KEEP_SET = frozenset({"attachment", "promotion", "certificate", "form",
  "product_spec", "project"})`, `HOT_FILTERED_SOURCES = ("attachment", "product_spec")`.
- Producers: the change listeners (`embedding_change_listener.py:378-401`) and every explicit enqueue site queue only
  keep-set sources (order / spo / picking / customer / transporter / promotion_product / *_attachment links /
  order_status / schema_doc / mcp_tool / conversation_frame stop); the worker marks a queue item of any other source
  `skipped` without an embed call. Existing rows are never deleted.
- `product_spec` is enqueued when a `product_specifications` row is inserted or its `rendered_text` changes to a
  non-empty value (wire `enqueue_spec_embedding`, `product_spec_change_listener.py:103-131`).
- Readers: `entity_resolver` source maps use `product_spec` where they used `product` and map the hit's `source_id`
  (the product id) back to the product; no reader asks for a source outside `RECORD_KEEP_SET`; every reader filters
  `model_name = records_search_model(db)` and embeds the question with that model through `embed_texts`.
- `EmbeddingReadService.search_current` orders by `embedding <=> :q` (not by similarity DESC) and keeps every filter.
- `app/services/embedding_indexes.py`: `index_names(model) -> dict` and `index_ddl(model) -> list[str]` giving, per
  model, `CREATE INDEX CONCURRENTLY IF NOT EXISTS` for one keep-set partial HNSW index (`vector_cosine_ops`, `WHERE
  model_name = '<m>' AND is_current AND source_type IN (<keep set>)`) and one per hot source (`... AND source_type =
  '<s>'`). Reader SQL repeats the literal predicate so the planner matches the index. Migration
  `lec_0002_embedding_indexes` (down_revision `lec_0001_embedding_setting`) runs `index_ddl('text-embedding-3-small')`
  in an autocommit block.
- Filtered reads to a source not in `HOT_FILTERED_SOURCES` run `SET LOCAL hnsw.iterative_scan = relaxed_order`.
- `fuzzy_resolver`: a vector hit is added only at similarity >= `VECTOR_FLOOR_BY_MODEL[model]`
  (`{"text-embedding-3-small": 0.55, "gemini-embedding-001": 0.70}`, the lookup floors of the same models).

### Slice 3 contract (dual write, backfill job, guard)

- `app/services/embedding_settings.py`: `write_models(db) -> list[str]` = the setting's model (via `resolve_embedder`)
  plus `records_search_model(db)` when it differs, setting's model first.
- Worker: a keep-set queue item is embedded once per model in `write_models(db)`; the per-model skip check and
  supersede stay per model; a model whose embed raises does not block the other model's chunks.
- `app/services/embedding_backfill_service.py`: `backfill_records(db, model, *, rpm=None, batch_size=100, sleep=time.sleep,
  should_stop=None) -> BackfillResult(embedded: int, failed: int, remaining: int, complete: bool)`. Picks active
  keep-set documents with no current chunk of `model` whose failure count for `model` is < 3, embeds their chunk texts
  in requests of <= `batch_size` texts via `embed_texts`, sleeping `60 / rpm` seconds between requests (`rpm` default =
  `system_settings.embedding_backfill_rpm`, 20). A request that raises adds 1 to each of its documents' failure count,
  kept in `embedding_documents.metadata_json["embed_failures"][model]`; at 3 the document counts as failed. A rerun skips
  documents already done. `should_stop()` is checked between requests.
- `apply_search_model_guard(db, model) -> bool`: True and acts only when every active keep-set document has a current
  chunk of `model` or is failed for it; then it runs `embedding_indexes.index_ddl(model)` (autocommit, CONCURRENTLY) and
  sets `system_settings.embedding_records_search_model = model`. Otherwise False and nothing changes.
  `failed_documents(db, model)` lists the failed ones (source_type, source_id, failures).
- `app/tasks/embedding_backfill.py`: RQ task `run_records_backfill(model=None)` on the `imports` queue (worker): model
  defaults to the setting's; runs `backfill_records` then `apply_search_model_guard`.
- Settings PUT that changes provider or model enqueues `run_records_backfill` once (no change, no job).
- Switching back is the same flow: only documents without a current chunk of the target model are embedded.

### Slice 4 contract (lookup words in the store, PROMPT_SYNONYMS gone)

- `app/services/chatbot/head/lookup_word_store.py` (inside the chatbot boundary): `LOOKUP_SOURCE = "lookup_word"`.
  - `sync_lookup_words(db, *, model=None, embed=True) -> SyncResult(created, updated, retired, embedded)`: rows from
    `lookup_lists.load_rows` with the widest visibility (as the start-up warm, `engine.py:1345-1385`: salespeople,
    customers, spec rows); one `embedding_documents` row per lookup row (`source_type = 'lookup_word'`, `source_id =
    '<list>:<row key>'`, `title` = label, `body_text` = the texts one per line, `source_hash` = sha256 of the texts,
    `company_id` NULL: rows are listed under the viewer's scope by `load_rows`, and record readers never read
    `lookup_word`); one chunk per text that has a vector for `model` (default: the setting's model). A text already
    embedded for `model` in any `lookup_word` chunk is copied, not re-embedded; only new texts call `embed_texts`.
    Changed rows (new hash) get their chunks rebuilt; documents of rows that no longer exist get `is_active = false`
    and their chunks `is_current = false`.
  - `load_lookup_vectors(db, model) -> int`: one SELECT of current `lookup_word` chunks of `model` into the
    in-process cache (`lookup_lists._cache`, key `_key(text, model)`, unit vectors); no provider call.
  - `write_back(db, model, vectors: dict[str, list[float]]) -> int`: a turn's freshly embedded row texts become chunks
    of every active `lookup_word` document whose texts contain them.
- `lookup_lists.py`: the per-container shared vector file (`_shared_path`, `_lock_shared`, `_read_shared`,
  `_write_shared`, `CHATBOT_LOOKUP_VECTOR_DIR`) is removed; the warm loads via `load_lookup_vectors`, then embeds only
  what is still missing and writes it back. `PROMPT_SYNONYMS` and `_with_synonyms` are removed; a class-label `type:`
  row's texts = the class label + the union of the `search_synonyms` of its categories.
- Scheduled task `lookup_words_sync` every 600 s (handler registered next to `embedding_job_processor`,
  `app/scheduler/task_scheduler.py:185,793`), seeded idempotently by migration `lec_0003_lookup_words_sync`
  (down_revision `lec_0002_embedding_indexes`) the way `143_seed_embedding_job_processor_task.py` seeds its row.
- RQ task `embed_missing_lookup_words()` (`app/tasks/chat_turns.py`, the chatbot doorway; queue `imports`) = `sync_lookup_words`.
- Script `scripts/move_prompt_synonyms.py` (dry run by default, `--apply` to write): every former PROMPT_SYNONYMS
  word not already on a row of its class / type is listed; `--apply` adds a category word to the `search_synonyms` of
  every active category of that class, a file type word as a keyword of that type's `attachment_type_alias` option
  (creating the option if missing). The 11 entries are a constant inside the script.

### Slice 5 contract (API + screens)

API. The chatbot import boundary (`tests/chatbot/test_import_boundary.py`: core never imports `app.services.chatbot`)
splits it: record endpoints go on the existing core router `app/api/v1/system/embeddings.py` (prefix
`/api/v1/system/embeddings`; `/metrics`, `/dead-letters`, `/rebuild`, `/backfill` stay): `GET /overview`,
`POST /records-backfill`. Lookup-word endpoints, which need `lookup_lists` / `list_resolver`, go on the chatbot doorway
router `app/api/v1/system/chatbot.py` under `/api/v1/system/chatbot/lookup-words` (`GET ""`, `POST /try`,
`POST /embed-missing`). Overview's lookup numbers are counted from `embedding_chunks` (`source_type = 'lookup_word'`)
in core SQL. View = `master_data.lookup_sets.view`, edit = `master_data.lookup_sets.edit`:
- `GET /overview` (view) -> `{setting: {provider, model, backfill_rpm}, records_search_model, lookup: {texts_total,
  texts_with_vector}, records: [{source_type, documents, chunks_by_model: {<model>: n}}], guard: {target_model,
  ready, remaining, failed}}` (records = the keep set only; guard numbers from `embedding_backfill_service`).
- `GET /api/v1/system/chatbot/lookup-words?list=<name>` (view) -> `{list, rows: [{key, label, source, group, words: [{text, home,
  has_vector}]}]}`, rows from `load_rows` under the request's company scope, `home` one of `label`, `code`, `class`,
  `alias_column`, `alias_set`, `description`; `has_vector` for the setting's model. Lists: category, spec, file_type,
  brand, promotion_kind, location, salesperson, customer, sales_channel. Unknown list -> 422.
- `POST /api/v1/system/chatbot/lookup-words/try` (view) `{phrase}` -> `{verdict: resolved|ambiguous|unresolved, candidates: [{list, key, label, spelling:
  {score, text, home}, vector: {score, text, home} | null, partial, floors: {spell, partial, meaning}, passed,
  signal}]}`: the live span resolver (`list_resolver.resolve`, `_score_list`, `_meaning_scores`) over the same rows,
  phrase embedded once with the setting's model; top 8 candidates.
- `POST /api/v1/system/chatbot/lookup-words/embed-missing` (edit) -> 202 `{job_id}` enqueues
  `app.tasks.chat_turns.embed_missing_lookup_words`; `POST /api/v1/system/embeddings/records-backfill` (edit)
  `{action: start|stop}` -> 202: start enqueues `run_records_backfill`, stop sets the stop flag the job's
  `should_stop` reads (Redis key `lec:records_backfill:stop`).
- Word provenance: `LookupRow` gains `homes: tuple[str, ...] | None` parallel to `texts`, filled by every loader.
- Alias targets (AC-LEC-24): `app/services/lookup_alias_targets.py` `ALIAS_SET_TARGETS` maps `attachment_type_alias`
  -> attachment types (value = type name), `brand_alias` -> brands (brand_code), `sales_channel_alias` -> the
  `SALES_CHANNELS` values; `GET /api/v1/master-data/lookup-sets/{set_id}/alias-targets` -> `[{value, label}]` (404 for a
  set that is not an alias set); options of an alias set carry `orphaned: bool` (value not among the targets).

FE (vitest on touched components; layering UI -> hooks -> `services/embeddingsService.ts` -> api-client):
- Page `app/(protected)/system-management/embeddings/page.tsx`, menu entry beside Lookup Sets (`config/menu.config.tsx`
  ~:1131, permission `master_data.lookup_sets.view`), layout per mock v3 sections 1-6.
- System Settings tab `app/(protected)/user-management/settings/embeddings/page.tsx` + tab entry in
  `settings/layout.tsx` (~:306-361): provider / model SearchableSelect, backfill rpm, read-only coverage rows (mock §7).
- Lookup set option dialog: for an alias set the value is a SearchableSelect over `alias-targets`; orphaned options
  show a Badge.

### Slice 5 FE contract (route-local, like `master-data-management/lookup-sets/`)

- `app/(protected)/system-management/embeddings/`: `page.tsx`; `services/embeddingsService.ts` (`getOverview`,
  `getLookupWords(list)`, `tryPhrase(phrase)`, `embedMissing()`, `recordsBackfill(action)`, all through
  `lib/api-client` + `extractApiError`); `hooks/useEmbeddings.ts` (`useEmbeddingsOverview`, `useLookupWords`,
  `useTryPhrase`, `useEmbedMissing`, `useRecordsBackfill`: invalidate + toast); `components/EmbeddingsHeader.tsx`
  (PageHeader, strip, ONE CTA), `components/LookupWordsGrid.tsx` (DataGrid fixed layout, resizable, words grouped by
  home with a vector dot), `components/TryPhraseCard.tsx` (verdict + per row spelling / vector / partial / floors /
  pass), `components/RecordsGrid.tsx`; tests in `__tests__/`.
- `app/(protected)/user-management/settings/embeddings/page.tsx` + its tab in `settings/layout.tsx` (provider and model
  SearchableSelect, backfill rpm, read-only coverage rows from `getOverview`).
- `master-data-management/lookup-sets`: `services/lookupSetService.ts` `getAliasTargets(setId)`, the option dialog
  uses SearchableSelect over it for an alias set; an orphaned option shows a Badge.
- No UUIDs in the UI, no explanation text, usable at 375 and 1280 (browser pass on the crew test copy).

## Review fix round 1 (reviewer NOT READY + security-reviewer NEEDS WORK, 29 Oct)

Each item: red test first (tester), then fix (coder), kill-proof. R = reviewer, S = security-reviewer.
- F-1 (R2, S-H1): `search_current` returns [] for any `source_type` outside `RECORD_KEEP_SET` (incl. `lookup_word`,
  dropped sources); `/external/rag/search` with `source_type=lookup_word` returns no rows for any principal.
- F-2 (R1, M1 (a)): tool search no longer depends on mcp_tool vectors: the AI assistant agent route skips tool RAG
  (keyword ranking only) and `/external/rag/tool-search` returns an empty candidate list (no error) under any search model.
- F-3 (S-M2): `GET /chatbot/lookup-words?list=customer|salesperson|location` also need `order_management.customers.view`
  / `master_data.sales_agents.view` / `inventory.warehouses.view` (403 otherwise); `/try` drops candidates of lists the
  user cannot view.
- F-4 (R3, S-M3): a failed request counts against its documents only for per-document errors (a 4xx other than
  401/403/429); auth, rate-limit, 5xx and missing-key errors stop the run without counting. The guard flips only when
  the target model has current keep-set chunks, failed documents are under 1% of the keep set, and the model is still
  the setting's model. `POST /records-backfill` needs `system.settings.update` (as the existing `/backfill`).
- F-5 (R6): entity_resolver tier3 and `_rag_resolve_phrase` reads narrowed to a non-hot subset of sources run
  `SET LOCAL hnsw.iterative_scan = relaxed_order`.
- F-6 (R8): settings PUT enqueue failure is logged, the save still returns 200.
- F-7 (R9): `move_prompt_synonyms.py` matches an existing attachment type by name or code; an entry with no type is
  listed as unmatched, never created as an option.
- F-8 (R10): alias targets of `attachment_type_alias` offer both code and name values; an option keyed by either is not
  orphaned.
- F-9 (R11): overview counts remaining / failed in SQL (no per-document metadata load); FE shows an error state when
  the overview fails (no endless skeleton); the Settings tab hides coverage rows on a 403.
- F-10 (S-L4): alias targets for brands use the caller's company scope (staff: granted companies; API key: its scope).
- F-11 (S-L5): `/try` phrase `max_length=200` (422 above).
- F-12 (S-L6): settings PUT validates `embedding_model` against `^[A-Za-z0-9._-]{1,128}$` (422 otherwise).
- F-13 (nits): Stop shows only while a backfill runs; the Settings tab prefills from the resolved embedder (setting or
  label fallback), not openai defaults; the guard's index build sets `maintenance_work_mem = '512MB'` for its session and
  REINDEXes an INVALID index of the model; `rag.py` checks the key of the search model's provider and reports the search
  model; `embed_search_texts` reuses the caller's session; the LookupWordsGrid Row cell shows the row label; the lookup
  set API returns `alias_set: bool` and the FE uses it instead of a duplicated key list; tabs change on
  `onValueChange` (keyboard).
- Test-only (tester): R4 `tests/test_resolver_tier3_company_scope.py:392-406` assert `f"debtor:{code}" not in`; R7 mark
  the slice 2 index tests `serial_ddl` (or scratch schema).
- UAC amendment (R5): AC-LEC-17 "written back" is dropped for the turn path: a turn's misses stay in the in-process
  cache (no DB on the turn path, plan Performance) and the 10-minute sync persists them.

## Review fix round 2 (reviewer NOT READY on one regression + security lows, 29 Oct)

- G-1 (R2-1, regression of F-2): the AI assistant's tool pick ranks by word overlap against each tool's capability text
  (`build_capability_documents`: intent, aliases, typical user questions, description), keeping the portal pin and
  intent nudges, no vectors (owner M1 (a) "keyword ranking"). "stock for SRT-123" and "how many units of SRT-123 do we
  have" pick `crm_inventory_stock_balance_list`.
- G-2 (R2-2): alias-set orphan status is computed from ALL brand codes (unscoped); only the picker list is scoped.
- G-3 (S-low 1): `resolve_embedder` applies the model-name pattern to the label fallback too (invalid -> default),
  and the migration copies a label model only when it matches.
- G-4 (S-low 2): brand picker targets come from the ORM query (standard company filter), not a hand-written scope.
- G-5 (S-low 3 + R2 nit): Gemini 400 API_KEY_INVALID / FAILED_PRECONDITION and 404 stop the run uncounted; a per-document
  4xx on a batch is retried one document at a time before any count; `embed_failures[model]` is cleared when the
  setting's model changes and when Start is pressed.
- G-6 (nits): `/external/rag/search` refuses a source outside the keep set before embedding; the guard RESETs
  `maintenance_work_mem` in a finally; the backfill running flag is one shared key constant, owned by a job token
  (a job clears only its own flag) with a short TTL refreshed per batch; `/lookup-words` checks its permission once;
  the Settings tab prefills only from known values and sends provider / model only when the user changed them; the
  LookupWordsGrid Row label is plain text; entity_resolver's search seam and project_registration pass their session to
  `embed_search_texts`.

## Review fix round 3 (reviewer NOT READY on round 2, 29 Oct; backend only)

- H-1 (G-1 on the real call path): the assistant's tool pick ranks `standalone_query` only, never the appended
  "Resolved references: ..." hint (`ai_assistant_service.py:1096-1099`); "stock for SRT-123" and "how many units of
  SRT-123 do we have" pick `crm_inventory_stock_balance_list` WITH the hint present.
- H-2 (G-5 vs owner G1 (a)): `embed_failures[model]` is reset only when the setting's model changes, not on Start; a
  document that always fails reaches 3 across Starts, counts as failed, and no longer blocks the guard.
- H-3 (nits): the settings PUT's failure-count reset runs inside the logged try (a DB error there never turns a saved
  setting into a 500); a backfill job that cannot claim the running flag exits without embedding (no double run).
- H-4 (browser pass 1280): the Settings tab's Record search row reads `records_search_model` from the overview (shown
  while it differs from the setting's model, with progress); the save toast says when a records backfill was started.
- H-5 (browser pass 1280): the header's record-coverage label no longer truncates at 1280 (short label, full model in
  the title).
- H-6 (browser pass: product_spec 0 documents on the copy): `product_spec` documents are created for every active
  product with non-empty `rendered_text` that has none; the records backfill creates them before embedding, so the
  owner's spec rule (S1) holds for existing products, not only for specs edited after deploy.

## Review fix round 4 (final reviewer NOT READY at 83d601b284, 29 Oct)

- J-1 (blocker): `ensure_product_spec_documents` commits the new product_spec documents before the first embed request
  (`embedding_backfill_service.py` ~:560); a first batch that fails with a per-document 400 while documents are pending
  keeps the documents, embeds the good ones, and counts 1 failure on the bad one (no crash).
- J-2: the settings PUT clears the records-backfill stop flag before it enqueues a backfill (as `/records-backfill`
  start does); the comment at `system/embeddings.py` ~:198 is corrected.
- J-3 (FE): the Settings tab updates its resolved embedder after each successful save, so the "records backfill
  started" toast shows exactly when the save changed provider or model (including a first save of a never-saved setting).
- J-4 (nits): docstring at `embedding_backfill_service.py` ~:447 (no "or Start"), the ai_assistant comment and trace span
  name the question the ranking uses, the always-true ternary at `settings/embeddings/page.tsx` ~:118, the duplicate
  `hashlib` import.

## Review fix round 5 (browser pass on 99a7c0fd27, 29 Oct; FE only + one comment)

- K-1: the header's "Record search reads" cell never overlaps: the model text and the "<model> in progress" badge sit
  on separate lines or wrap (flex-wrap / stacked), both widths.
- K-2: at 375 the header stat labels and the embedder name wrap instead of clipping (no truncation without a title);
  each stat keeps its full text visible or in a title.
- K-3: the LookupWordsGrid Vectors column has an explicit size wide enough for "n / m" so it does not clip at 1280.
- K-4: the stale "the job also clears it" comment in `app/api/v1/system/embeddings.py` (~:198) is corrected.

## Review fix round 6 (crew release review of d6c6971e7f, 30 Oct; backend + migrations)

Release #7 does not wait; this lane goes in the next release. Plus the CI fix: gitleaks flagged made-up UUID row
keys in `embeddingsStubs.ts` (27afd5ad2d), fingerprints added to `.gitleaksignore` (b1b94f5ffc).

- R6-1 (online index build): `lec_0002_embedding_indexes` builds its 3 partial HNSW indexes with
  `app/utils/online_index.ensure_indexes_online` (owner rule 27 Oct, `documentation/runbooks/memory-and-deploy-guards.md`
  section 9): CONCURRENTLY outside the transaction, the repo's migration limits, fail-soft (a timeout logs a WARNING and
  the revision succeeds), an INVALID leftover is dropped and rebuilt, all builds under the shared advisory lock and
  one 180 s budget. Measured: the keep-set index took 131 s at the default maintenance_work_mem and 34 s at 512MB on
  the dev copy, so the migration sets `maintenance_work_mem = '512MB'` for the builds (the same value
  `apply_search_model_guard` already uses) and resets it. The (table, name, columns) tuples come from
  `app/services/embedding_indexes.py` (one predicate source, still reused by `search_current` and `index_ddl`), and
  `scripts/ensure_goods_chain_indexes.py` (run by `start.sh` on every backend start) retries them, so a build the
  deploy budget did not reach is finished on the next start.
- R6-2 (synonyms travel with the deploy): the 11 former PROMPT_SYNONYMS entries move into data through a new
  idempotent data migration `lec_0004_prompt_synonyms` (raw SQL, no ORM): category words appended to
  `product_categories.search_synonyms` of every active category of that class (class label or own name, case aside;
  `water tap` also matches class `tap`), file type words added as `lookup_option_keywords` of the type's option in the
  `attachment_type_alias` set (set and option created when missing; a type that does not exist is skipped). A word
  already present (case aside) is skipped, so a rerun adds nothing; append only. Downgrade is a no-op (it cannot tell
  a moved word from one an admin typed). `scripts/move_prompt_synonyms.py` is removed: one copy of the word list. The
  10-minute `lookup_words_sync` task embeds the new words after deploy.
- R6-3 (reviewer S1 / N1 on round 6, READY): the backend-start retry also sets `maintenance_work_mem = '512MB'` before
  it builds (a rebuild at the default memory could run past the 180 s budget and repeat on every start), and lec_0004
  logs at INFO each file type label it skips because no attachment type matches. Red b9e5806e4f, fix 77c96a939d.
  The UAC's AC-LEC-18 now names the migration instead of the script.
