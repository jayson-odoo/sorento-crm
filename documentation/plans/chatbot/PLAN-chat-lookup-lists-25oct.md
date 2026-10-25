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

## Behaviour card answers (crew a43817015, 25 Oct): defaults
Q1 text-embedding-3-small (OpenAIProvider.embed, llm_provider.py:555), row vectors cached per process, ONE batch per
turn, failure -> spelling only; a ~USD 0.01 retrieval-only recall re-check vs the measured 3-large is approved.
Q2 rule text naming a removed per-turn line is renamed to its block. Q3 customers top 5 + one-span-one-list.
Q4 promotion kinds move to a block ("srt a3 flyer" stays a hard row in the final check). Q5 template marker gate.

## S1 code contract (tests are written against this; names are binding)
Module `app/services/chatbot/head/lookup_lists.py` (no session held across the parse; pure functions + one db loader):
- `MARKER = "== LOOKUP LISTS =="`; `gate_on(template: str) -> bool` (marker present as its own line).
- `HEADER_NOUN = {"category": "Category", "sales_channel": "Sales channel"}` (later slices add "spec", "file_type",
  "brand", "salesperson", "location", "promotion_kind", "customer"); `header(list_name) ->
  f"{HEADER_NOUN[list_name]} candidates (pick one only if the message means it):"`.
- `FLOOR_SPELLING = 0.5`, `FLOOR_MEANING = 0.5`, `TOP_K = {"category": 10, "sales_channel": 2}`.
- `@dataclass(frozen=True) LookupRow(list_name: str, key: str, label: str, texts: tuple[str, ...])`: `texts` are
  the strings matched (name, code, synonyms, class label); `label` is what the block prints.
- `@dataclass(frozen=True) Hit(row: LookupRow, piece: str, spelling: float, meaning: float)`.
- `pieces(message: str, max_words: int = 4) -> list[str]`: every 1..4 consecutive-word piece of the folded message
  (folding as candidates.py `_phrase`), in message order, de-duplicated.
- `Embedder = Callable[[list[str]], list[list[float]]]`; `None` or an exception -> meaning 0.0 for every row.
- `shortlist(message, rows: list[LookupRow], embed: Embedder | None, *, brand_words: frozenset[str] = frozenset())
  -> dict[str, list[Hit]]`: spelling = best `candidates.similarity(trigrams(piece), trigrams(text))` (exact folded
  equality = 1.0); meaning = best cosine(piece vector, text vector); keep a row when spelling >= FLOOR_SPELLING or
  meaning >= FLOOR_MEANING; best hit per row; sorted by max(spelling, meaning) desc then label; cut to TOP_K[list].
  One-span-one-list: a piece in `brand_words` (folded) produces no "category" hit.
- `render(hits: dict[str, list[Hit]], order=("category", "sales_channel")) -> list[str]`: per list with hits, the
  header line then `- <label>` per hit (label de-duplicated); nothing for an empty list.
- `load_rows(db) -> list[LookupRow]`: categories = searchable + active product_categories (label category_name; texts
  name, code, class_label, search_synonyms) + class labels + product types (spec registry product_type values); sales
  channels from `SALES_CHANNELS` (reports/ask.py:340). `brand_words(db) -> frozenset[str]` from active_brands + the
  brand_alias lookup set.
Wiring:
- `ParserConfig.lookup_lists: bool = gate_on(raw_template)` (parser.resolve_config, beside closed_lists :951).
- `ContextLayers.lookup_lines: list[str] | None = None`, printed right after candidate_lines in both assemble paths
  (context.py :505 and :574). When the config has lookup_lists, the engine passes None for product_types,
  product_details, known brands, promotion kinds and sales_channels lines.
- engine: `_lookup_lines(db, message, config)` in a savepoint like `_candidate_lines` (engine.py:1131-1182); any
  error -> [] and the turn continues; trace key "lookup_lists" with pieces + hits (label, piece, spelling, meaning).

## S1 as built (8c906e32c1, kill-proof on PR #1865)
`EMBED` sentinel `USE_PROVIDER` (None = spelling only), `embedder(db)` resolves the key in the engine session; own
Unicode fold (`_fold`, keeps CJK); a category piece CONTAINING a brand word is skipped; code-like pieces (3+ digit run
or a 5+ char letter-digit word) never feed the meaning / spelling lists (AC-12).

## S2 code contract (spec words, spec numbers, file types, prompt translations as data)
- Lists "spec" (header noun "Spec", TOP_K 10) and "file_type" (header noun "File type", TOP_K 5).
- Spec WORD rows: every spec registry value of a WORD key (colour, finish, material, bowl count, trap type, ...; the
  keys the 33 removed v63 "Specification ..." word lines describe), label `<spec label> <value label>`, texts = value,
  label, synonyms.
- Spec NUMBER values: `number_hits(message, db_or_rows) -> list[Hit]` (list "spec"): exact match of a normalised
  number+unit against stored spec values: `normalise_number("200 mm") == normalise_number("200mm") ==
  normalise_number("20 cm") == "200mm"`; units mm, cm, m (and inch if stored); "600x400" / "600 x 400 mm" sizes and
  ranges compared as stored after the same normalisation; every spec key holding the value is offered, label
  `<spec label> <stored value>` ("trap length 200mm"); a number no spec holds offers nothing. No meaning score.
- File type rows: attachment types + certificate kinds (the sources closed_lists_index `_file_matches` reads,
  closed_lists_index.py:248-276), label as the attachment type / certificate kind name.
- Prompt translations become row texts (data), moved verbatim from the v63 spans this lane removes, as one constant
  `PROMPT_SYNONYMS: dict[str, dict[str, tuple[str, ...]]]` (list -> row label -> extra texts), e.g. category "water
  closet": ("tandas", "mangkuk tandas", "马桶"), "water tap": ("paip air", "kepala paip", "水龙头"), "kitchen sink":
  ("sinki dapur", "厨房水槽"), file type "photo": ("gambar", "foto"), "drawing": ("lukisan",), certificate: ("sijil",).
  It applies to S1's category rows too (the measured config was "+ v63 translations as data").
- Block order: category, spec, file_type, sales_channel (later: brand, salesperson, location, promotion_kind,
  customer).
- Meaning floors per list for text-embedding-3-small (crew-only phase1/small/floors.small.md, 26 Oct, free re-score:
  lowest floor keeping the 3-large block size at its recall): `FLOOR_MEANING_BY_LIST = {"category": 0.55,
  "sales_channel": 0.55, "brand": 0.58, "spec": 0.55, "file_type": 0.59, "customer": 0.53}`, any other list 0.55;
  `FLOOR_MEANING = 0.5` stays as the documented base only if a test needs it. Spelling floor 0.5 everywhere. Cost:
  spec words 49 of 51 and file types 136 of 137 mentions at top 10 (one each lost vs 0.5); customers 63 of 75.

## S3 code contract (brands, salespeople, locations, promotion kinds)
- Lists + header nouns + TOP_K: "brand" "Brand" 3; "salesperson" "Salesperson" 5; "location" "Location" 5;
  "promotion_kind" "Promotion kind" 3. Render order: category, spec, file_type, brand, promotion_kind, salesperson,
  location, sales_channel (customer last, S4).
- Rows: brands = active_brands (turn_runtime.py:543-581) texts name + code + brand_alias words (chatbot_prompt_vars.py
  :341), label exactly as the Known brands line spells it ("SORENTO (SRT)", context.py:100); salespeople = the same
  source the sales report uses for agent names (find it; cite file:line), label the name; locations = active
  warehouses, texts name + code, label "<name> (<code>)"; promotion kinds = promotion_kind_rows (turn_runtime.py:814),
  label "<name> (<type_code>)" so the parser can still answer promotion_kind with the code.
- The marked version already drops the Known brands / Promotion kinds / Sales channels lines (S1); these blocks replace
  them.

## S4 code contract (customers)
- List "customer", header noun "Customer", TOP_K 5, meaning floor 0.53, spelling floor 0.5; rows = active customers of
  the company scope (the customer picker's source; cite it), label as the picker shows the name.
- One-span-one-list: a piece whose folded text EQUALS a row text of category, brand, sales_channel or location (or a
  brand word) feeds no customer rows.
- 6,850 rows: vectors warmed in a background thread on the first marked turn (never blocks a turn); until warm,
  customer rows are spelling only. No customer vector is persisted.

## S5 contract (unlabelled list-free version)
- `app/services/chatbot/prompt_lookup_edits.py` (pure): `EDITS: tuple[Edit, ...]` with Edit(op "replace" | "delete",
  anchor: exact text, payload: str); `apply(text) -> str | None` (None when any anchor is missing or found more than
  once; the reason in a returned/logged message); appends the marker line `== LOOKUP LISTS ==` at the end.
- Spans (v63 line numbers for orientation only; anchors are exact text): Product types line (L1846, delete); category
  examples + translations inside the low_stock categories rule (L1018-1023: keep the rule clauses, drop the lists);
  every "Specification ..." line (L1796-1845, word AND number, delete); the attachment-type word maps (L335-341, L391);
  example brand / kind / channel name lists. Rule text naming a removed per-turn line is RENAMED to its block
  ("Known brands:" line -> "Brand candidates" block, "Promotion kinds:" line -> "Promotion kind candidates", the
  "Sales channels" line -> "Sales channel candidates"), never left pointing at a line the turn no longer has.
- Per-version switches read from the template (parser.py:976-978: "compare_to", "by_words", "Sales channels"; :993
  code_lookup) must keep their current value on the new version unless the switch is about a removed list (then say
  which and why). No anchor inside the order_status list or the SALES sections; the SALES TARGET section is inserted
  before `== SALES REPORT: order_status "sales_report", domain_hint "order" ==` (fc2943a9b7 prompt_inserts.py:9) and
  must survive.
- Migration `lkp_0001` (revision id <= 32 chars, down_revision = main's head at push time; `./scripts/alembic-reparent.sh`):
  maskp_0001 pattern (production-labelled text read in SQL), publishes one UNLABELLED version when apply() succeeds,
  skips when an identical template exists, logs and publishes nothing otherwise; downgrade deletes only unlabelled
  versions carrying the marker.
- Tests: synthetic fixture text holding every anchor once + the SALES REPORT header + a simulated SALES TARGET insert:
  apply() removes every span, renames, appends the marker, keeps the insert byte for byte; a missing / doubled anchor
  -> None; the migration on Postgres publishes once, unlabelled, idempotent. Lead proves the edits on the real v63 text
  (crew-only) and records chars before / after.
