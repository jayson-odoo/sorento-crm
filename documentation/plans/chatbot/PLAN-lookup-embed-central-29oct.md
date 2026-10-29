# PLAN: LOOKUP-EMBED-CENTRAL - one source per lookup list, one lookup-vector table, one screen to see them

Status: CARD v2 + MOCK v2 filed for the owner (29 Oct 2026; owner answered v1 Q1-Q5, Q5 = records join the central store). No code. Track: L (new table + migration, new screen).
Build starts only after the owner answers N1-N5 and approves the mock
(`documentation/mockups/LOOKUP-EMBED-CENTRAL/index.html`).

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

## ARCHITECTURE

- One table family for every vector: `embedding_documents` + `embedding_chunks`. Lookup words join it as documents
  of `source_type = 'lookup_word'`, `source_id = '<list>:<row key>'`, one chunk per row text (label, code, each
  alias, each description word), `company_id` = the row's company (customers, brands, warehouses) or NULL (shared).
  No new table: the v1 `lookup_vectors` table is dropped from the design.
- One embed function `embed_texts(texts, model) -> vectors` (Gemini batchEmbedContents, 100 per request,
  1536 dims, the 429 waits of `lookup_lists.py:919`; OpenAI kept behind the same function for the switch window).
  The worker, the lookup lists, every RAG reader and the AI assistant call it; the three direct OpenAI POSTs
  (`embedding_worker.py:666-676`, `rag.py:23-43`, `llm_provider.py:555-558`) go.
- One model setting, two values: WRITE model (what new and changed text is embedded with) and SEARCH model (what
  every reader embeds the query with and filters `model_name` on). Both start text-embedding-3-small on prod;
  during the switch WRITE = both, SEARCH = 3-small; at the flip both become gemini-embedding-001. Every reader gains
  `model_name = :search_model` (today none filters, so two models in one HNSW index would compare across spaces).
- One partial HNSW index per model (`WHERE model_name = '...' AND is_current`, CREATE INDEX CONCURRENTLY), so a
  model-filtered search keeps HNSW recall while two models coexist.
- Lookup lists: worker start = one SELECT of `lookup_word` chunks for the search model into today's in-process
  cache (replaces the #1959 shared file, `lookup_lists.py:924-981`); a turn's miss embeds inside the 3 s budget
  and is written as a chunk; the 10-min sync diffs live rows (`load_rows`) against `lookup_word` documents by
  source_hash and embeds the difference.
- Fixed classes: rows from master tables, aliases from one home per list, vectors from one family under one model
  setting. Nothing is per-list or per-source special-cased.

## Card v2

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
| Business records (21 sources) | the RAG producer (`embedding_change_listener.py:378-401`) | n/a | record docs, queue + backfill job |

### Switch of business records to gemini-embedding-001 (Q5)

1. Deploy (search unchanged): WRITE = 3-small + gemini, SEARCH = 3-small. New and changed records get both models,
   so search stays complete. Prod only: OpenAI cost for changed records during the window (small); dev has no
   working OpenAI key, so dev starts at step 3 directly.
2. Backfill job (one RQ job, resumable, stop/start on the screen): documents with no current gemini chunk, 100 chunks
   per Gemini request, capped requests per minute, smallest sources first; never through the per-event queue
   (2,400 documents/hour would take ~112 h for 270k). Screen shows per source: gemini n / total.
3. Flip (owner presses it when every source shows 100%): SEARCH = WRITE = gemini. One setting change, no deploy.
4. Keep 3-small rows 14 days for rollback; then an owner-run DELETE (held for the owner, never automatic).
Rollback: flip SEARCH back to 3-small (rows still there); records changed after the flip have stale 3-small rows
until a 3-small rebuild of those sources (the per-model skip check, `embedding_worker.py:898-907`, re-embeds them).

### Screen (mock v2)

`System > Embeddings` (beside Lookup Sets, permission master_data.lookup_sets.view): header with the model, lookup
word coverage, record coverage and which model search reads; one CTA (Embed missing; it becomes "Switch search to
gemini-embedding-001" once records are 100%). A Lookup words / Records switch. Lookup words: tabs per list, words
grouped by home with a vector dot, Try a phrase (verdict + per row spelling, vector, partial, floors, pass/fail).
Records: grid per source (documents, chunks, 3-small, gemini, last embedded, in queue), Search records card
(nearest chunks for a phrase under the viewer's company scope). Chunk text is not in the committed mock: it carries
customer data and the repo is public.

### Edge cases

- Two models side by side: every read filters `model_name`; the partial HNSW index per model keeps recall.
- Search flip with a source below 100%: the flip is refused, the screen names the sources still short.
- Embed failure (429, bad key): chunk not written, row shows failed with the error; turns fall back to spelling.
- Lookup row text on 5 rows (马桶): 5 chunks with the same text; the embed function sends each distinct text once.
- Company-scoped lookup rows (customers, brands, warehouses): the document carries the company; the screen and Try
  a phrase list rows under the viewer's scope (`load_rows`).
- Other dims (3072): refused by embed_texts (column is 1536).
- Task type: today no Gemini taskType is sent (lookup_lists.py and llm_provider.py); kept so lookup floors stay valid.

### Cost and limits

- Gemini embed price USD 0.15 per 1M input tokens (the S3 guard's price, `crew/state/eval/eem/s3/gem_guard_s3.py:15`;
  UNVERIFIED against Google's page). Dev copy: 50.4M characters = ~12.6M tokens at 4 characters per token =
  ~USD 1.9 for all records once; lookup words ~USD 0.01. Prod volume UNVERIFIED: owner-run SQL below.
- Requests: ~2,700 batch requests of 100. Gemini embed RPM / TPM / daily quota of the org key: UNVERIFIED (owner reads
  them in AI Studio); the job's per-minute cap is set below that.
- Storage: a second set of 1536-dim vectors for 270k chunks ~1.7 GB plus its HNSW index while both models are kept;
  prod disk headroom UNVERIFIED.
- Build lanes stay under the org key ledger (`crew/state/eval/gemini-org-key-ledger.md`); the full backfill is a
  prod step for the owner, not a lane run.

### Migration, rollback, prod rollout

- Migrations: one data-free migration adding the partial HNSW index for gemini-embedding-001 (CONCURRENTLY, outside
  a transaction) and the two model settings (system_settings columns, default 3-small). No table is created; the
  lookup_bindings / lookup_sets schemas are untouched.
- Data: PROMPT_SYNONYMS words not already on a row of their class / type go to that row's alias home (list shown to
  the owner first; on dev 3 of the 8 category words are on no category: mangkuk tandas, paip air, sinki dapur).
- Rollback of the code: revert the PR. The old readers do not filter by model (see RAG facts), so once gemini
  record chunks exist they would be compared with 3-small query vectors: a code rollback after step 2 needs the
  owner-run DELETE of gemini record chunks first (held statement in the rollout doc). Before step 2 a revert is clean.
- Prod steps for the owner: (1) run the read-only SQL below; (2) deploy; (3) check the Gemini quota; (4) Embed
  missing (lookup words, ~USD 0.01); (5) start the record backfill, watch the Records tab; (6) Switch search when
  100%; (7) after 14 days run the held DELETE of 3-small rows.

Owner-run read-only checks (prod):
```sql
SELECT class_label, count(*) AS categories,
       count(*) FILTER (WHERE search_synonyms ?| array['马桶','tandas','水龙头','kepala paip','sinki dapur','厨房水槽']) AS with_dict_words
FROM product_categories WHERE is_active AND is_searchable IS NOT FALSE
  AND class_label ILIKE ANY (array['%closet%','%tap%','%sink%']) GROUP BY class_label;
SELECT source_type, model_name, count(*) AS chunks, sum(length(chunk_text)) AS chars
FROM embedding_chunks WHERE is_current GROUP BY 1, 2 ORDER BY 3 DESC;
SELECT pg_size_pretty(pg_total_relation_size('embedding_chunks')) AS chunks_size;
```

### Questions v2 (options, recommendation)

N1. Where lookup-word vectors live: (a) in the existing family as `lookup_word` documents + chunks; (b) a new
table family shared by both, with records migrated into it. Recommend (a): no new table, the per-model skip and
supersede already work, one worker; (b) moves 270k rows and rewrites every reader for no user gain.

N2. During the switch: (a) write both models, search stays on 3-small until the flip; (b) write gemini only and
flip search at once (records not yet re-embedded drop out of search for the backfill hours); (c) write gemini only,
search stays 3-small (new and changed records are unsearchable until the flip). Recommend (a): search never loses
a record; the extra OpenAI cost is only changed records during the window.

N3. Backfill pacing: (a) a dedicated batch job (100 per request, capped per minute, resumable, off-hours);
(b) through today's queue (~2,400 documents/hour, ~112 h). Recommend (a).

N4. 3-small rows after the flip: (a) keep 14 days, then an owner-run DELETE; (b) delete at the flip; (c) keep.
Recommend (a): a one-setting rollback for two weeks, then ~1.7 GB back.

N5. The flip itself: (a) a button on the screen (enabled at 100%, owner only); (b) a System Settings value the
owner edits. Recommend (a): the screen already shows the coverage that gates it.

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
