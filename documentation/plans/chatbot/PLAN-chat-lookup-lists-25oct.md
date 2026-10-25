# PLAN: chatbot lookup lists before the parser + list-free prompt version (CHAT-SLIM-INDEX build, 25 Oct 2026)

Status: PLAN (build), track L (prompt-version migration). Lane CHAT-SLIM-INDEX-PLAN, branch crew/chat-slim-index-plan.
UAC: `chat-lookup-lists-25oct-acceptance-criteria.md`. Eval history and gates: `PLAN-chat-slim-index-25oct.md`.

## Owner rulings this plan executes (25 Oct, verbatim via crew)
- a42372027: "b for a3 flyer, i still want category in lookip list, dont spend anymore, just do it and remove any
  category related prompt". No code rule for "srt a3 flyer" (left to the prompt); gate overridden, risk accepted.
- 23:4x: "I expect when I hand test, the prompt is already very slim and without all the listing" -> ALL entity lists
  move to lookup in one design: categories (+ classes, product types), sales channels, spec WORD values, spec NUMBER
  values (owner challenge 23:5x), file types (attachment + certificate kinds), brands, salespeople, locations,
  customers (stricter), promotion kinds. Product codes and DO / SO / PO numbers stay exact AFTER the parser.
- No paid runs during the build. One final paid check (USD <= 5) after the full build, reported beside the hand-test
  handover, not a gate. The owner hand test is the gate; crew moves the copy label for the window only.

## What exists (origin/main 3d59b5e716; file:line)
- Per-version switches are literal markers in the template: `parser.resolve_config` (head/parser.py:924-1004),
  `gate_on("== CLOSED LISTS ==")` :951. v63 (md5 0f3b48e6) carries no CLOSED LISTS marker (checked on the text).
- Per-turn user block: `turn/context.py` lines known_brands :100, promotion_kinds :131, sales_channels :150,
  product_types :158, product_details :165; `ContextLayers` :221-269 (candidate_lines :265); `assemble` :540
  (`_assemble_off` :497-537). context.py stays pure (tests/chatbot/test_context_assemble.py:70-76).
- Engine: engine.py:4517-4614 builds the layers in one session; `_candidate_lines` :1131-1182 runs in a savepoint and
  a failure skips the block (pattern to copy). Parse at :4627 with no session open.
- Spelling shortlist today: head/candidates.py (trigrams/similarity :94-107, MAX_PHRASE_WORDS 3 :39, product types +
  classes :128-179) and head/closed_lists_index.py (file types, certificates, code-suffix spec values). Spelling only.
- Embeddings: `OpenAIProvider.embed` (llm_provider.py:555-572, text-embedding-3-small) + `resolve_api_key` :140-190.
  No vectors exist for these lists (embedding_worker sources :95-587). No embedding call before the parser today.
- Data: product_categories (models/product.py:33-96: class_label :53, search_synonyms :57, is_searchable :60),
  product types = spec registry 'product_type' values (models/product_spec.py:41-66), SALES_CHANNELS
  (reports/ask.py:340), brands `active_brands` (turn_runtime.py:543-581) + `brand_alias` lookup set
  (chatbot_prompt_vars.py:341), promotion kinds `promotion_kind_rows` (turn_runtime.py:814).
- Publishing an unlabelled version from the label-time text: alembic/versions/maskp_0001_parser_sub_asks.py
  (publish_on_production :105-162: reads the production-labelled text in SQL, anchored insert, idempotent, unlabelled).

## ARCHITECTURE
- Layer: pre-parser SHORTLIST only (head/). Code lists candidates; the parser picks one or none; nothing in code
  decides meaning. Codes / document numbers keep today's exact path after the parser.
- One shared mechanism, `head/lookup_lists.py`:
  1. pieces(message): every 1-4 word piece of the current message (folded; reuse candidates.py folding/trigrams).
  2. per list: spelling score (trigram similarity, as candidates.py) and meaning score (cosine of the piece vector vs
     the list-row vectors); keep a row when spelling >= floor OR meaning >= floor (0.5 / 0.5, as gated), top-k per list.
  3. one-span-one-list: a piece that is exactly a brand name / code / alias feeds no category or customer candidates;
     a piece that is exactly a category, channel or location word feeds no customer candidates.
  4. render one self-describing block per list: "<Noun> candidates (pick one only if the message means it):" + one
     line per row as the list spells it. Empty list -> nothing.
- Lists are small adapters {name, header noun, rows(db), label(row), top_k}. Spec NUMBER values use a second matcher
  (exact normalised number+unit: "200 mm" = "200mm" = "20 cm"; ranges and "x" sizes as stored) offering every spec that
  holds the value ("Spec candidates: trap length 200mm, width 200mm"). No meaning score for numbers.
- Vectors: list-row vectors embedded once per row text (batch), cached in process keyed by list + row-text hash,
  refreshed when the row set changes; the message pieces are embedded in ONE batch call per turn. Embedding failure or
  timeout -> spelling-only blocks, turn continues (savepoint pattern of `_candidate_lines`).
- Gate: a one-line marker "== LOOKUP LISTS ==" in the template (`gate_on`). Only a version carrying it gets the blocks
  AND loses the per-turn list lines (Product types, Product details, Known brands, Promotion kinds, Sales channels).
  Every other version (prod v63) keeps today's input byte for byte (test).
- Prompt version: alembic `lkp_0001` publishes ONE unlabelled version from the production-labelled text at migration
  time (maskp pattern): anchored REMOVALS of every list span (category vocabulary + translations, Product types line,
  all 50 Specification lines, file-type word maps, brand list wording), rule text that names a removed per-turn line is
  renamed to its block ("Known brands:" -> "Brand candidates"), plus the marker line. Each anchor found exactly once or
  the migration publishes nothing and logs why. No instruction section (placement rule 2). Label untouched.
- Coexistence: no anchor sits in the order_status list or the SALES sections; a unit test applies the edits on a
  fixture carrying SALES-TARGET-CHAT's sales_target / opportunity inserts and asserts both survive.
- Classes fixed, not shapes: any list word in any language reaches the parser as a candidate (meaning + spelling);
  numbers by value. No per-word rules.

## Slices (one PR; each slice = tester red tests -> coder green -> kill proof; one reviewer at the end)
- S1 core + categories (categories, classes, product types; is_searchable only) + sales channels + marker gate +
  context/engine wiring + traces.
- S2 spec WORD values + spec NUMBER values (normaliser + matcher) + file types / certificate kinds.
- S3 brands (+ aliases) + salespeople + locations + promotion kinds.
- S4 customers (top 5, one-span-one-list priority).
- S5 `lkp_0001` migration (anchored removals + marker) + coexistence test; alembic single head.
- Parallel coders only after S1 lands, max 2 at once, separate worktrees folded onto this branch by the lead.

## Hand test + final check
- Crew test copy, label moved to the new version for the window only. Script: laneboard/scripts/<PR>.md (owner's
  console cases: "Dealer fullshun oct total sales for water closet", "dealer only", "srt a3 flyer", a spec size, a
  brand, a salesperson, a location, a customer name).
- Final paid check (owner OK, USD <= 5): TRAIN 118 + R5 62 + category set, x1 per arm (x3 if it fits), eval key.

## Known risks (shipped by owner override; go in the PR body)
- Categories gate: TRAIN 88 vs 90 (G005 "wc" + product code -> attachment; G046 "ka" floor hit adds a customer).
- "srt a3 flyer" depends on the prompt (any block moved it 1-2 of 3 in gates).
- Spec words / numbers, file types, brands, salespeople, locations, customers, promotion kinds never measured in the
  parser. Customers probe: 0.66 wrong lines per name-nothing message, 5.15 on category-only messages.
- Dropping the per-turn Product types line cost ~4 of 36 follow-ups in the diagnosis.
- Recall was measured with text-embedding-3-large; the app default is 3-small (behaviour card Q1).
- Prompt after removals ~130k of 141k chars: list text is 7.5% of v63; the rest is rules.
