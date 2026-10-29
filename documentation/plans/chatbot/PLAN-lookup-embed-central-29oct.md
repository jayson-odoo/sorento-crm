# PLAN: LOOKUP-EMBED-CENTRAL - one source per lookup list, one lookup-vector table, one screen to see them

Status: CARD + MOCK v2 filed for the owner (29 Oct 2026; v2 answers the owner's Lavish note on v1). No code. Track: L (new table + migration, new screen).
Build starts only after the owner answers Q1-Q5 and approves the mock
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

## ARCHITECTURE

- Layer: `head/lookup_lists.py` stays the one place that builds lookup rows (one loader per list). New: one
  `LookupVector` model + `lookup_vector_service.py` (read / write vectors by `(model, sha1)`), one RQ task
  `lookup_vectors.sync`, one read-only API `GET /api/v1/master-data/lookup-words` (+ `POST .../try`), one FE page.
- Shared mechanism: the vector store behind `_vector_embedder` (`lookup_lists.py:990`) swaps the shared file
  for the table; the in-process cache stays as the hot layer. Every list goes through the same store; no list gets
  its own path.
- Fixed classes: every list's rows from its master table (or code constant), every alias from that list's ONE alias
  home, every vector from the one table. Nothing is per-phrase or per-list special-cased.

## Card

### Per list (proposal = recommended answers below)

| List | Rows from (auto, no set upkeep) | Alias home today | Alias home proposed | Embed trigger |
|---|---|---|---|---|
| Category | product_categories (searchable, active) | search_synonyms column + PROMPT_SYNONYMS dict | search_synonyms column (unchanged) | sync job + lazy |
| Class / type rows | distinct class_label + product_type registry values | PROMPT_SYNONYMS dict | union of its categories' search_synonyms; product_type values: registry user_synonyms | sync job + lazy |
| Spec | product_spec_registry | synonyms / user_synonyms columns | unchanged | sync job + lazy |
| File type | attachment_types (non-certificate) | description words + attachment_type_alias set + dict | description words + attachment_type_alias set, option picked from attachment types | sync job + lazy |
| Brand | brands (active, session companies) | brand_alias set (not on dev) | brand_alias set, option picked from brands | sync job + lazy |
| Promotion kind | promotion types | none | none (add a set only when a word is needed) | sync job + lazy |
| Location | warehouses (active) | none | none (same) | sync job + lazy |
| Salesperson | sales_agents (active) | aliases column | unchanged | sync job + lazy |
| Customer | customers (active, scoped) | none | none | sync job + lazy |
| Sales channel | code constant dealer / project | none | `sales_channel_alias` set, option = dealer / project | sync job + lazy |

Rule: rows NEVER come from a lookup set. An alias set is optional, one per list, keyed by the master record's code
(today's attachment_type_alias / brand_alias convention); its option picker lists the master records, and an option
whose code no longer exists is shown as orphaned on the screen (not silently dropped).

### Lookup-vector table (proposal)

`lookup_vectors`: `id` uuid pk, `model` varchar(128), `text_sha1` char(40), `text` text, `dims` int,
`embedding` vector(1536) null, `status` (`ok` / `failed`), `error` text null, `embedded_at`, `last_seen_at`
(last sync that found a live row carrying the text; texts unseen for 30 days are pruned by the sync). Unique
`(model, text_sha1)`. No source / list columns: one text serves many rows (马桶 sits on 5 categories); the screen
joins LIVE rows to vectors by hash, so a renamed or deleted record can never leave a stale "source" behind.
No company_id: the table holds words, not records; every read that lists rows goes through `load_rows` under the
viewer's company scope.

Flow: worker start = one SELECT of the label model's vectors into the in-process cache (no provider call);
a turn that meets a text with no vector embeds it inside today's 3 s budget and INSERTs it (ON CONFLICT DO
NOTHING); the sync job diffs live texts vs the table every 10 min (scheduler), on an embedder label flip, and on the
screen's "Embed missing" button, embedding in 100-text chunks with today's 429 waits. A model flip therefore
re-embeds in the background; until it completes, turns embed their own misses as they do today.

### Screen (mock: `documentation/mockups/LOOKUP-EMBED-CENTRAL/index.html`)

`System > Lookup Words` (`/master-data-management/lookup-words`, beside Lookup Sets, permission
`master_data.lookup_sets.view`). Header: embedder model + coverage ("422 / 502 texts with a vector"), one CTA
"Embed missing". Line tabs per list. DataGrid per list: row label, source table, words grouped by home
(Label, Alias column, Alias set, Description words), each with a vector dot, vector status. Card "Try a phrase"
(v2): the resolver's verdict (resolved / ambiguous / unresolved), then per candidate row the spelling score + the
text it was spelt like, the vector (cosine) score + the nearest text, each text's home, partial, the list's floors
and pass/fail with the winning signal. It runs the span resolver on the phrase as typed (no span model call; one
embed call for a phrase with no vector). No 2-D plot (Q4).

### Edge cases

- Same word on two lists (photo -> file type and a category synonym): both rows shown with their list's floor.
- Alias option whose master code was renamed or deleted: orphaned badge on the screen; never matched.
- Customer / brand / location rows are company-scoped: the screen and Try card read rows under the viewer's scope.
- Embed failure (429, bad key): row status `failed` + error on screen; the turn path falls back to spelling as today.
- Model with other dims (3072): refused by the sync with a clear error (column is 1536).
- Dev OpenAI key is dead: text-embedding-3-small rows can no longer be embedded on dev; the screen shows `failed`.

### Cost and limits

- Gemini embed: USD 0.15 per 1M input tokens (price used by the S3 guard, `crew/state/eval/eem/s3/gem_guard_s3.py:15`;
  UNVERIFIED against the current price page). Full backfill ~7-8k texts x ~8 tokens = ~60k tokens = ~USD 0.01 per
  model. Steady state: only new or edited words. Try-a-phrase: 1 embed call per search (~USD 0.000001).
- Rate: 100 texts per request -> ~80 requests per full backfill, sent serially with the 15/30/60 s 429 waits.
  Gemini embed RPM / daily quota for the org key: UNVERIFIED (not read; owner to confirm from AI Studio).
- Org key ledger applies to every build-lane call (`crew/state/eval/gemini-org-key-ledger.md`).

### Migration, rollback, prod rollout

- One additive alembic migration: `lookup_vectors` + unique index. No data migration; no change to lookup_sets /
  lookup_bindings schema.
- Data moves (owner-visible, done on the screen or by a one-off script the owner runs): each PROMPT_SYNONYMS word
  not already on a row of its class / type goes to that row's alias home (list shown to the owner first; on dev 3 of the 8 category
  words are missing from every category: mangkuk tandas, paip air, sinki dapur; 马桶 / tandas sit on 5, 水龙头 /
  kepala paip / 厨房水槽 on 4, query 29 Oct); sales_channel_alias set created with
  dealer / project options.
- Rollback: revert the PR (cache code returns to the shared file); the table is left unused, drop later.
- Prod steps for the owner: (1) run the read-only SQL below to confirm the dict's category words are on prod's
  categories; (2) deploy; (3) open Lookup Words, press Embed missing (~USD 0.01); (4) try 零售 / retail / 马桶.

Owner-run read-only check (prod):
```sql
SELECT class_label, count(*) AS categories,
       count(*) FILTER (WHERE search_synonyms ?| array['马桶','tandas','水龙头','kepala paip','sinki dapur','厨房水槽']) AS with_dict_words
FROM product_categories WHERE is_active AND is_searchable IS NOT FALSE
  AND class_label ILIKE ANY (array['%closet%','%tap%','%sink%']) GROUP BY class_label;
```

### Questions (options, recommendation)

Q1. Where does a list's alias live?
(a) Keep the master-table alias columns that exist (category, spec, salesperson); lists without one get ONE optional
alias set keyed by master code (file type, brand, sales channel; others only when needed); delete PROMPT_SYNONYMS.
(b) Move every alias into lookup sets, drop the columns (39 categories + 23 sales agents re-entered as options).
(c) Add an alias column to every master table, retire the alias sets.
Recommend (a): zero upkeep for new records, words stay where the record is edited, no re-entry.

Q2. Sales channel (dealer / project), the only list with no table: rows stay the code constant, aliases in a
`sales_channel_alias` set (a) or a new `sales_channels` master table (b)?
Recommend (a): the report engine filters on those two values (`reports/ask.py:386`); a table adds a screen for two rows.

Q3. What embeds a new or edited word?
(a) Sync job every 10 min + on label flip + "Embed missing" button, plus today's lazy turn path.
(b) A save listener on every source table (8 tables) enqueueing an embed per change.
(c) Lazy turn path + button only.
Recommend (a): one mechanism covers create, edit, model flip and backfill; (b) is 8 hooks to keep in step.

Q4. The screen: (a) per-list DataGrid + "Try a phrase" card, no plot; (b) add a 2-D plot of the vectors.
Recommend (a): a 2-D projection of 1536-dim cosine space misplaces neighbours; Try-a-phrase answers "what matches".

Q5. RAG chunks (`embedding_chunks`, OpenAI, dev key dead): (a) stay in their own table, the screen shows lookup
words only; (b) the screen gets a read-only "Records" tab with RAG counts per source and model; (c) merge into one table.
Recommend (a): different shape (document FK, versioning, company); (c) would rewrite the RAG pipeline for no user gain.
