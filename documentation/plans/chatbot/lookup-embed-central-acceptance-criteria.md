# LOOKUP-EMBED-CENTRAL acceptance criteria

Plan: `PLAN-lookup-embed-central-29oct.md` (card v3 + owner answers 29 Oct). Every criterion is testable; ids are
referenced by the tests (`AC-LEC-<n>` in the test name or docstring).

## A. Embedder setting (owner N5)

- AC-LEC-1: `system_settings` has `embedding_provider`, `embedding_model`, `embedding_records_search_model`; all three
  appear in GET of system settings (both manual dict builders) and PUT accepts provider + model (search model is
  read-only to the API).
- AC-LEC-2: the migration fills provider + model from the production label of prompt key `chatbot_lookup_embedder`
  when one exists (prod: gemini / gemini-embedding-001), else leaves them NULL; `embedding_records_search_model` is
  set to `text-embedding-3-small`. Idempotent; downgrade drops the columns.
- AC-LEC-3: one function resolves the embedder: setting first, the prompt label only when the setting is empty, then
  today's OpenAI default. The lookup lists (`lookup_lists.py` production embedder) and the record worker both use it.
- AC-LEC-4: `embed_texts(texts, provider, model)` returns unit vectors of 1536 dims for gemini (batchEmbedContents,
  <= 100 texts per request) and openai; a model whose vectors are not 1536 long raises; no other code POSTs to an
  embeddings endpoint (`embedding_worker._embed_text_chunks`, `rag._embed_query`, `OpenAIProvider.embed` call it).

## B. Records keep set (owner S1 + spec rule + M1 (a))

- AC-LEC-5: the record keep set is exactly attachment, promotion, certificate, form, product_spec, project (M1 (a): mcp_tool and conversation_frame dropped)
  (one constant). Listeners and the worker stop queuing / embedding every other record source; their existing
  rows are left in place (never deleted).
- AC-LEC-6: `product_spec` is queued whenever a product's `product_specifications.rendered_text` is created or changes
  (and never when it is empty); its text is `rendered_text` only.
- AC-LEC-7: readers that asked for `product` record vectors ask for `product_spec` and map a hit back to the product
  (same product id); no reader asks for a source outside the keep set.

## C. Two models side by side + guard (owner N2 (a), N4 (c), G1 (a), G2 (a))

- AC-LEC-8: while `embedding_records_search_model` differs from the setting's model, a new or changed keep-set record
  is embedded with BOTH models; when they are equal, with that one model only.
- AC-LEC-9: every record reader embeds the question with `embedding_records_search_model` and filters
  `model_name = <that model>` (search_current, entity_resolver tier3 and `_rag_resolve_phrase`, frame/tool search if
  kept, fuzzy_resolver, project duplicate check). A chunk of another model is never compared.
- AC-LEC-10: `search_current` orders by distance (`embedding <=> q`), so the HNSW partial index serves it (EXPLAIN in
  the test shows an Index Scan on the partial index).
- AC-LEC-11: indexes (owner P1 (b), "anything that makes our system faster"): per embedding model one partial HNSW
  index over the keep set, plus per-source partial HNSW indexes for the hot filtered sources `attachment` and
  `product_spec` (`WHERE model_name = '<m>' AND is_current AND source_type = '<s>'`). A read filtered to attachment or
  product_spec uses its per-source index (EXPLAIN in the test) and returns k rows when k exist; other filtered reads set
  `hnsw.iterative_scan = relaxed_order` and also return k of k (test: a source that is 30% of the rows returns 5 of 5).
- AC-LEC-12: `fuzzy_resolver` adds a vector hit only at similarity >= a floor (constant in code); today's no-floor OR
  of the top 10 is gone.
- AC-LEC-13: the backfill job embeds keep-set documents with no current chunk for the setting's model, 100 texts per
  request, at most `embedding_backfill_rpm` requests per minute (setting, default 20), resumable (a rerun skips what
  is done, per-model skip check). A chunk failing 3 times is marked failed and listed.
- AC-LEC-14: guard: when every keep-set document has a current chunk of the setting's model or is failed, the job
  builds that model's partial HNSW index (if missing) and sets `embedding_records_search_model` to it; before that the
  search model does not change. Changing the setting back starts the same process.

## D. Lookup words in the family (owner N1 (a), Q3 (a))

- AC-LEC-15: each lookup row is an `embedding_documents` row (`source_type = 'lookup_word'`, `source_id =
  '<list>:<row key>'`, company of the row or NULL) with one chunk per row text; `source_hash` = hash of its texts.
- AC-LEC-16: the 10-minute sync (scheduler) and "Embed missing" upsert changed rows, embed only texts with no vector
  for the setting's model, and retire documents of rows that no longer exist.
- AC-LEC-17: a worker loads the setting model's `lookup_word` vectors into the in-process cache at start (one SELECT,
  no provider call); the per-container shared vector file is gone; a turn's miss is still embedded inside the 3 s
  budget (kept in process; the 10-minute sync persists it; review fix round 1).
- AC-LEC-18: `PROMPT_SYNONYMS` is deleted; the idempotent data migration `lec_0004_prompt_synonyms` adds each of
  its words not already on a row of its class / type to that row's alias home, so the deploy carries them (review
  fix round 6; it replaced the one-off script, which prod could not run). A file type with no matching attachment
  type is skipped and logged; a rerun adds nothing.

## E. API + screens

- AC-LEC-19: GET `/api/v1/system/embeddings/overview`: setting, lookup coverage (texts with a vector / total), record
  coverage per keep-set source per model, search model, failed count. Permission `master_data.lookup_sets.view`.
- AC-LEC-20: GET `/api/v1/system/embeddings/lookup-words?list=<name>`: rows of that list under the viewer's company
  scope, each word with its home (label, alias column, alias set, description) and vector status.
- AC-LEC-21: POST `/api/v1/system/embeddings/try` `{phrase}`: the span resolver's verdict and per candidate row the
  spelling score + text, vector score + text, partial, floors, pass/fail, winning signal (as mock v3 section 2).
- AC-LEC-22: POST `/api/v1/system/embeddings/embed-missing` (lookup words) and `/backfill` (records start / stop),
  permission `master_data.lookup_sets.edit`; both return at once and run on the worker.
- AC-LEC-23: Embeddings page (`System > Embeddings`, menu beside Lookup Sets): header strip + one CTA, Lookup words /
  Records switch, list tabs, words grouped by home with a vector dot, Try a phrase table, Records grid; System Settings
  gets an Embeddings tab (provider, model, backfill rpm, read-only coverage rows). Usable at 375 and 1280. No UUIDs, no
  explanation text in the UI.
- AC-LEC-24: an alias-set option of a list's alias set (attachment_type_alias, brand_alias, sales_channel_alias) is
  picked from the master records (SearchableSelect), and an option whose code no longer exists is shown as orphaned.

## F. Floors (owner T1 (a))

- AC-LEC-25: the gemini floors in `list_resolver.py:59-63` are unchanged unless the re-run of the tuning script on
  the enlarged label set (30+ meaning-only phrases per main list) shows precision >= 0.95 at another floor; the
  table goes in the PR body.
