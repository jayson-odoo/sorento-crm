# UAC: ENTITY-EXTRACT-MATCH (extract then match)

Plan: `documentation/plans/chatbot/PLAN-entity-extract-match-26oct.md`. Owner rulings 26 Oct ~16:15: Q1 (a) two-pass +
union in slices S1-S4; Q2 +~1.0 s per turn OK; Q3 (a) no new alias table; Q4 (a) in-process vector cache.

## Journey

1. A dealer or staff member writes to the WhatsApp assistant naming things in their own words: "hanlim wc cert",
   "srt basin hitam ada?", "马桶 picture", "jhonson suise catelog".
2. The system already knows every list the person may see (brands, categories, spec values and names, file types,
   promotion kinds, warehouses, salespeople, customers) and the alias texts admins keep on those rows.
3. A small span pass (S2) copies out each mention and a rough type, without seeing any list values.
4. The resolver (S1) matches each mention to the row(s) it names across ALL lists: exact, alias text, typo, partial
   name, meaning. Type only breaks ties. Two close rows -> ambiguous (the assistant will ask). Nothing close -> none.
5. The parser sees only the matched rows (S2); mentions it leaves out are added back (S3, if it wins the measure).
6. The person gets the right answer without being asked for what they already wrote, and is asked only when two rows
   are genuinely close.

S1 is step 4 alone: a library plus an offline eval. No turn changes behaviour in S1.

## S1: list resolver (no behaviour change)

Fixtures in tests are invented (public repo): never a real customer, salesperson or person name.

- **AC-S1-1 [BE]** Given rows across lists, when a span equals a row text after case/space folding ("Mocha" vs brand
  "MOCHA"), then status `resolved`, that row first, signal `exact`.
- **AC-S1-2 [BE]** Given a row whose extra texts hold an alias ("SRT" on brand SORENTO; "马桶" on category Water
  Closet), when the span is the alias ("srt", "马桶"), then it resolves to that row; the resolver holds no alias words
  of its own (no hard-coded word lists in the module).
- **AC-S1-3 [BE]** Given a misspelled span ("jhonson suise" vs "JOHNSON SUISSE"), then it resolves by spelling.
- **AC-S1-4 [BE]** Given customer rows with long names ("KIMLAN TRADING SDN BHD", "BUMI CERAMIC SDN BHD"), when the
  span is a partial name ("Kimlan") or a partial name with a one-letter typo in a token ("Bumi ceramics"), then it
  resolves to the right row; when the span shares only common tokens with a row ("trading sdn bhd" vs many "... SDN
  BHD" rows), then it does NOT resolve to one of them. Token weights come from the list's own texts (IDF), not a word
  list.
- **AC-S1-5 [BE]** Type is a tie-break, never a filter: a span typed `file_type` that only matches a promotion_kind
  row resolves to that promotion_kind row; when the typed list and another list match the span equally well, the
  typed list's row wins; an untyped span (type None) resolves over all lists.
- **AC-S1-6 [BE]** Given two different rows whose scores are within the ambiguity margin of each other (or rows that
  share the matching text, e.g. salesperson codes "LEE - I" and "LEE - II" both carrying "LEE"), then status
  `ambiguous` with every close row as a candidate, best first.
- **AC-S1-7 [BE]** Given a span that names nothing ("stock", "please"), then status `unresolved` with no candidate;
  each list applies its own floors (spelling, partial, meaning) from one constant table in the module.
- **AC-S1-8 [BE]** A span typed `product_code` is returned with status `skipped` and no candidates (products resolve
  elsewhere).
- **AC-S1-9 [BE]** Given an embedder (callable returning vectors), a span with no spelling overlap but a close vector
  ("booster pump" -> "Water pump") resolves with signal `meaning`; given no embedder or an embedder that raises, the
  resolver still resolves spelled spans and never raises.
- **AC-S1-10 [BE]** `resolve()` returns exactly one result per input span, in input order; an empty span list returns
  an empty list; a span whose text is blank is `unresolved`.
- **AC-S1-11 [BE]** Spec-name rows: given product spec registry entries, the resolver's spec_key row builder yields one
  row per active key with the label, the key spelled with spaces, synonyms and user synonyms, minus suppressed
  synonyms; "colour" resolves to the finish/colour key when that synonym is present.
- **AC-S1-12 [T]** Offline eval CLI `scripts/chatbot_eval/span_resolve.py` on the committed synthetic fixture (lists +
  gold + spans, under tests fixtures) prints the oracle and right-row numbers and they equal the expected values in
  the test; it makes no network call and needs no DB.
- **AC-S1-13 [T]** Gate (evidence in the PR, data stays outside git): the CLI on the phase-1 gold
  (crew/state/eval/eem) reproduces oracle >= 268/271 and B1-span right row on the test half >= 77%.
  Amended 26 Oct (captain, review round 1): the review fixes removed silent picks on equal scores, the per-list
  cap on ambiguous rows and full weight for one-edit words, and the floors went back to the phase-1 calibration with no
  one-phrase fits. The honest gate is oracle >= 265/271 ALL and >= 130/132 TEST, B1-span right row on the test half
  >= 80%, and resolved-wrong on B1 spans no higher than 13 ALL. Floors are re-calibrated on a larger labelled set
  in S2.
- **AC-S1-14 [T]** No behaviour change: no module on the turn path imports `list_resolver` in S1; the existing head
  lookup tests pass unchanged.

## S2: span pass before the parser, dark behind a new parser prompt version

Owner (26 Oct ~23:58, via crew): S2 ships dark behind a new prompt version; the owner hand-tests the two-pass path in
the Chatbot Console by picking that version; spend cap lifted for the S2 gate (both prompts on TRAIN + R5 + the
200-message set). Model per contact (owner rule 24 Oct) applies to the span call too (crew review 26 Oct).

Journey: the same six steps as above; S2 adds steps 3 and 5 (span pass, parser sees only matched rows) for a parser
version that carries the span marker. Every other version behaves exactly as today.

- **AC-S2-1 [BE]** On a parser version WITHOUT the span marker the turn is unchanged: same lookup lines, no span
  call, no `span_extract` trace event, no `chatbot_span_extract` usage row.
- **AC-S2-2 [BE]** With the marker (`== LOOKUP SPANS ==` on its own line), exactly one span call runs before the
  parser, with no DB session open, and its spans go through `list_resolver.resolve` over the rows the contact may see
  (a dealer: its own customers only; salespeople only when the contact may see them), the same visibility as today.
- **AC-S2-3 [BE]** The lookup blocks then hold the rows the resolver matched (resolved or ambiguous), plus the rows
  the message spells near-exactly (today's lookup spelling score >= 0.95; never a meaning-only or looser spelled hit),
  plus held values and number hits as today. A row the message never names is not offered: "check stock", "any
  promotion?" and "basin price" offer no customer, promotion kind or yes/no spec row unless a span names one or the
  message spells the row near-exactly. Amended 27 Oct (crew ruling (b) V2, inside the owner's 26 Oct "two-pass +
  union"): offline on the 198 recorded span answers, spans-only offered the gold row for 79.0% of mentions with 0.77
  unnamed rows per message; adding near-exact spelled rows gives 85.0% with 1.02 (today's lookup: 4.57).
- **AC-S2-4 [BE]** An ambiguous span renders at most `lookup_lists.TOP_K[list]` rows of a list, best first; the trace
  records how many rows were close.
- **AC-S2-5 [BE]** A span call that fails, times out or returns invalid JSON leaves the turn on today's n-gram lookup
  lines; the trace says `fallback`; the turn still answers.
- **AC-S2-6 [BE]** The span call's tokens and cost are recorded under feature `chatbot_span_extract`; the trace event
  `span_extract` carries the spans, each status, the rows rendered, ms, provider, model and model source.
- **AC-S2-7 [BE]** Model per contact: the span call resolves provider/model through the parser's ladder (contact
  override -> contact tag -> the span prompt's `production` label row -> global AI config) via
  `contact_llm_choice.apply_choice`, fed the same choice the parser gets in that turn. One test per rung, plus a chosen
  provider with no API key -> the default pair with source `fallback_no_key` and no key text in logs.
- **AC-S2-8 [T]** Migration: seeds the span prompt (`chatbot_span_extractor` v1, labelled production; unused unless
  a parser version carries the marker) and publishes one UNLABELLED `chatbot_semantic_parser` version = the
  PROMPT-RULES-DIET text with its `== LOOKUP LISTS ==` line replaced by `== LOOKUP SPANS ==`; idempotent; downgrade
  removes only its own rows; the production label never moves; single alembic head.
- **AC-S2-9 [T]** The S1 import guard narrows on purpose: only `head/span_extract.py` and the engine seam import
  `list_resolver`.
- **AC-S2-10 [T]** Gate (paid; estimate and actual spend in a crew-note): both prompts (A = today's production text,
  B = the S2 version; plus the PROMPT-RULES-DIET lookup version as reference) on parser gold TRAIN + R5 and the
  phase-1 200-message set. Pass: B's right row on the 200 set >= A's and >= the reference, rows offered that the message
  never named <= 0.5 per message, p50 added latency <= 1.2 s, and no TRAIN/R5 row that passes on A fails on B without a
  named cause. The span call also runs on the staff Gemini model for the 186 non-code messages (org-key ledger rules).
- **AC-S2-11 [UX]** Hand test: the owner picks the S2 version in the Chatbot Console and runs the script in
  `laneboard/scripts/<PR>.md`; each step names the exact rows the reply must use.

## S3: semantic bridge (Gemini lookup embedder + span "meaning"), owner 27 Oct ~09:4x

Owner: "can we use gemini key for embedding? ... the AI should know what 10 inch means, and what emas or biru mean".
Rulings: Gemini embedder option configured like the chat models, recalibrated floors per provider, prod stays on its
OpenAI embedder unless switched; keep cross-kind partials (no F2); no unit rules and no alias data (the AI bridges
languages and units). Crew 27 Oct: prompt-registry label `chatbot_lookup_embedder`; new PR; span "meaning" field.

- **AC-S3-1 [BE]** The lookup/resolver embedder follows the production label of prompt key `chatbot_lookup_embedder`
  (provider/model, same control as the chat models): label gemini / gemini-embedding-001 -> list and span vectors come
  from Gemini with the AI config's Gemini key; no label or no model -> today's OpenAI text-embedding-3-small (prod
  unchanged); a missing key for the chosen provider -> spelling only, never an exception.
- **AC-S3-2 [BE]** Vectors are cached per (model, text sha): a model switch re-embeds and never mixes vector spaces;
  Gemini list texts are embedded in batches.
- **AC-S3-3 [BE]** Meaning floors are per embedding model in `list_resolver`: text-embedding-3-small keeps today's
  values; gemini-embedding-001 uses the calibrated table (category 0.70, spec 0.75, file_type 0.65, brand 0.60,
  promotion_kind 0.75, location 0.65, salesperson 0.70, customer 0.75, sales_channel 0.65, spec_key 0.75; calibrated on
  the calib half of the phase-1 gold, test half 108/132 right vs 107 on OpenAI vectors); a model with no table -> no
  meaning matches. The n-gram lookup path keeps its OpenAI floors and runs spelling only on any other model.
- **AC-S3-4 [BE]** The span answer carries an optional per-span `meaning` (the plain English form, sizes in mm, or
  null). A migration publishes `chatbot_span_extractor` v2 with that wording UNLABELLED (the production label stays on
  v1); v1 answers without `meaning` keep working.
- **AC-S3-5 [BE]** When a span has a meaning, the resolver tries the meaning first and keeps it if it resolves
  (resolved or ambiguous); otherwise it resolves the span text. The trace records text, meaning and which one matched.
  Measured offline: meaning-first resolves emas -> gold, 金色 -> gold, hitam -> black, warna -> colour, sinki -> sink.
- **AC-S3-6 [FE]** The drawer's Span pass section shows each phrase's meaning (when present) and which form matched;
  the pass-1 line also names the embedding model.
- **AC-S3-7 [T]** Migration: single head, idempotent, downgrade removes only its own rows, no label moves.
- **AC-S3-8 [T]** On the copy (label `chatbot_lookup_embedder` -> gemini, span label -> v2): the owner's two messages
  plus "emas", "biru", "金色" rerun, per phrase before / after, posted on the PR.

### S3 round 2: startup warm of the lookup vectors (crew 27 Oct ~11:3x, ask a70702435)

Why: today the list vectors are embedded lazily by the first turn (`lookup_lists.warm`, called from
`engine._lookup_lines` and `engine._span_prep`); turns never block on it but run spelling only
(`lookup_lists.usable_embedder`) until ~4.6k texts are cached, which took more than 70 s on Gemini (100-text batches,
`GEMINI_EMBED_CHUNK`). So every process start has a no-meaning window, and it only starts when a message arrives.

- **AC-S3-9 [BE]** API start-up (`startup_event`) starts ONE background daemon thread that embeds every list row text a
  turn can load (the `engine._span_prep` rows at the widest visibility: salespeople and all customers of all companies,
  plus the spec-name rows) with the embedder the turn would use (`lookup_lists.embedder`, label-driven). Start-up
  returns without waiting for it: an embedder that blocks for minutes delays start-up by well under 1 s.
- **AC-S3-10 [BE]** Once that warm finishes, the FIRST turn after start uses meaning matching (its rows are cached, so
  `usable_embedder` gives the embedder and a meaning-only span resolves); no earlier turn is needed to start the warm.
- **AC-S3-11 [BE]** The warm is advisory: no key (embedder None), a database error or a provider error is logged and
  swallowed; start-up completes and turns behave as today (lazy warm, spelling only until cached).
- **AC-S3-12 [BE]** Switch `CHATBOT_LOOKUP_WARM_ENABLED` (default on; "0"/"false"/"off"/"no" turn it off);
  `tests/conftest.py` turns it off like `CHATBOT_INBOX_SWEEPER_ENABLED`. The warm reads row texts only, in its own
  read session with company scope None (all companies; the texts go only to the per-process vector cache and to the
  same embedding provider a turn already sends them to), and closes the session before embedding.
- **AC-S3-13 [BE]** (measured 27 Oct 11:2x-11:3x on ONE process: a 4,652-text warm on gemini-embedding-001 got HTTP
  429 part-way three times, even at ~1.5k texts a minute; a single request right after succeeded; the exact limit is
  UNVERIFIED) The background warm (`fill`) retries a chunk that hits a rate limit (`llm_call.is_rate_limited`, not an
  out-of-credit 429) after 15, 30 and 60 s, each stretched by a random 0-50% so the 4 workers of a container do not
  retry in lockstep; after the last wait the fill stops (texts already stored stay cached, the next turn's lazy warm
  goes on). Other errors are not retried. The turn path never retries and never sleeps. Before the production label
  moves to Gemini, a 4-worker start must be checked (4 warms start at once).
- **AC-S3-14 [BE]** A finished warm logs one INFO line naming the embedder model, the texts cached and the seconds
  taken ("lookup lists warm: N texts cached on <model> in S s"), so the copy's log shows which embedder is live; a
  failed warm logs a WARNING.
- **AC-S3-15 [BE]** `warm` does nothing when every text is already cached: no thread, no log line (every turn
  calls it; the reviewer saw three "texts cached ... in 0.0 s" lines after one request).
