# PLAN: ENTITY-EXTRACT-MATCH - parser extracts mentions, resolver matches them

Status: S1 in progress (Phase 2, tester red tests first). Phase 1 done; owner design OK 26 Oct ~16:15.
Track: L overall (chatbot architecture), lead pattern; S1 itself is M (library + eval, no migration, no behaviour change).
UAC: `documentation/plans/chatbot/entity-extract-match-acceptance-criteria.md`.

Owner rulings (26 Oct ~16:15, via crew): Q1 (a) two-pass + union, slices S1 -> S2 -> S3 -> S4, S1 its own PR
(red-first, reviewer), then S2; Q2 +~1.0 s per turn OK; Q3 (a) no new alias table: PROMPT_SYNONYMS into lookup_sets,
drop prompt alias lines, mining + approval queue only when >= 8 real mentions need it; Q4 (a) keep the in-process
vector cache. Spend: report before going past the USD 6 already approved.

Lane resources to drop after the last slice merges: DB `sorento_eem_throwaway` (copy of sorento_cgos_throwaway, owner
sorento_crm) + `sorento_crm_backend/.env.ci-tests` (redis index 11); eval kit + real data stay in
`crew/state/eval/eem/` (outside git).

## Owner ask (26 Oct ~14:40)

"go for extract then match ... apply those matching on attachment type, spec, spec values, salesperson all those ...
how can parser label consistently ... if we pass the input, the prompt is too long, if we RAG, it gives noises, if we
don't pass input, it doesn't know what to extract, very chicken and egg"

## Problem (facts at plan time)

- `head/lookup_lists.py` (#1865) matches every 1-4 word piece of the message (up to 154 per message) against ~6.8k
  list rows BEFORE the parser. On 1,200 real messages: ~855 spelled hits vs ~2,270 meaning-only hits, mostly noise
  (crew/state/eval/v66/noise.out).
- Lists out of the prompt saved ~11k chars only (v63 140,897 -> v185 129,651); the prompt is mostly rules.
- A post-parser resolver exists (`entity_resolver.py`, exact -> partial -> vector over embedding_chunks); brands,
  categories, spec values, salespeople have no chunks there.

## Question Phase 1 answers with data

Can the parser find and roughly type mentions WITHOUT the value lists?

| Arm | Shape | Prompt carries |
| --- | --- | --- |
| A | untyped spans + the slot each fills from context; resolver searches all lists; code decides | list TYPES + 2-3 examples each |
| B | typed spans, schema-only prompt; resolver confirms or re-types | types + few examples |
| C | two-pass: tiny span pass -> resolver -> parse with only the resolved rows | pass 1 tiny; pass 2 resolved rows |

Metrics per arm (at most 2 prompt variants each): span recall vs gold, type accuracy, resolution accuracy (right row),
noise (rows offered the message never named), tokens + latency per turn. Model gpt-5.4-mini on the dev key; USD 6 cap.

Budget (owner OK via crew a97110507, 26 Oct ~15:00): 1,500 live calls today, USD 6 hard total, runner stops at
USD 5.5; ledger line per run; report before anything beyond. Labelling uses Claude subagents (no USD).

## Phase 1 steps

1. Labelled set: >= 200 real inbound messages (masked) naming list entities; per-list counts. Sources: v66
   noise_pairs / labels, parser gold, R5/TRAIN rows. Gold = (span text, list, row) per mention.
2. Resolver harness (script, not product code): one vector store over ALL lists incl. spec values, attachment types,
   salespeople, locations, customers (reuse lookup_lists vectors); spelling + meaning + per-list cut-offs measured on
   SPANS, not pieces.
3. Run arms A/B/C on the set; record metrics + cost in a ledger.
4. Report: recommendation, PR slicing with sizes, fate of `head/lookup_lists.py` and of the prompt.

## Owner question 2 (26 Oct ~14:50): industry aliases without hard-coding

"how do we nudge the parser for things like srt is actually sorento brand, wc is actually water closet, all these
industry-specific aliases, how can we nudge it without hard coding in the prompt?"

Phase 1 adds:

1. ALIAS STORE as data: rows attached to list rows (brand SRT -> Sorento, category/product type WC -> water closet,
   马桶/马桶盖 -> toilet/seat cover, BM/ZH names), admin-editable, used by the resolver for spelling + meaning match on
   spans. The parser extracts the span ("srt", "wc") and never needs the alias.
2. Aliases MINED from data, approved by owner/admin, not typed by hand: product-code segments vs master data (SRT*
   codes -> brand Sorento; WC/WB/KS segments vs category), did-you-mean picks users accepted, AutoCount item
   descriptions.
3. Inventory of every place aliases live today (code constants such as `head/lookup_lists.py` PROMPT_SYNONYMS, brand
   aliases in `turn_runtime.active_brands`, `lookup_sets`, `sales_agents.aliases`, prompt text) and a move plan.
4. Measure how many labelled messages need an alias to resolve (gold flag per mention).

## Facts from the scout (26 Oct)

- Lookup vectors are in-process dicts only (`head/lookup_lists.py:588-598`): row cache keyed (model, sha1(text)),
  cap 20000; warm-up thread; spelling-only until warm. No shared/persisted store today.
- Lookup is gated by the "== LOOKUP LISTS ==" line in the template (`head/parser.py:1028`); blocks go into the user
  block after the message (`turn/context.py:266-268`).
- Parser already emits `entities[]` with `raw` + free-string `hint` (`head/parser.py:194-249`); hints seen: brand,
  customer, category/product_type, warehouse, sales_agent, specification (+ spec_key/spec_value), attachment_type.
- `entity_resolver.resolve_references` (`entity_resolver.py:5292`): Tier 1 exact (:5463), Tier 2 ILIKE (:5525),
  Tier 3 vector over embedding_chunks, min sim 0.80 (:5755-5775, :3073-3078). Brand, category, spec registry values,
  sales agents have no probe at all; warehouse + attachment_type have exact/prefix but no vectors.
- Corpus: 7,048 distinct live inbound texts in `chatbot.turns` on `sorento_explore1020` (read-only harness
  `prompt-diet/harness/inject.py`); no existing file has span gold for all lists.

## Owner rules honoured

No hard-coded regex/keyword rules (semantic/data only); typo + language robustness (BM, Chinese); parser extracts, code
picks the tool; clarify, don't assume; truthful replies; parser-level eval is the main gate; generalise (>= 8 real
messages per behaviour). No customer names in the repo.

## Findings

### Labelled set (gold)

338 real inbound messages from `chatbot.turns` on explore1020 (288 stratified by list + nonlatin + Malay + 60 random,
then 50 added for thin types; parser-gold HIDDEN texts excluded). Two independent Claude labellers: identical mention
sets on 275/288 messages, same row on 431/435 shared mentions; 21 messages adjudicated by the lead. 312 messages name
something; 186 name a non-code entity. Mentions (messages): brand 54, category 57 (50), customer 40 (38), file_type 34
(33), spec_value 40 (31), spec_key 21 (20), sales_channel 18 (17), salesperson 17, promotion_kind 11, location 8 (7),
product_code 244 (200). Real messages almost never name a warehouse (8 in 7,048) or a salesperson (17).
Data stays in crew/state/eval/eem/ (unmasked, outside git).

### Run 1: small span extractor, no value lists (gpt-5.4-mini, 338 msgs per arm)

| Arm | Span recall | Span precision | Type acc | Right row | Noise rows / msg | Tokens in/out | p50 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Today's lookup (#1865) | n/a | n/a | n/a | 88.9% offered | 5.72 offered | - | - |
| A1 untyped + slot | 87.7% | 77.2% | 77.9% | 74.5% | 0.39 | ~350 / 33 | ~1,000 |
| B1 typed, schema only | 88.3% | 81.7% | 81.5% | 74.9% | 0.36 | 434 / 33 | 984 |

Product codes: B1 recall 97.1%, precision 95.6%. "Right row" uses the resolver v1 (spelling + meaning, lookup floors).
Oracle (gold span + gold type through the same resolver): 250/271 = 92.3%; failures are partial customer names
(trigram Jaccard punishes long labels) and missing alias texts (drawing, picture, 高清图, color). B1 weak spots:
promotion_kind over-labelled (generic "promotion"), spec_value typed as other types, customer row 51%.
Cost: A1+B1 on 338 = 676 calls, USD 0.30.

### Run 2: resolver v2 (no LLM)

Added an IDF-weighted token partial score (each span token matches a row token exactly, by trigram >= 0.6, or by one
edit; weights = per-list IDF over that list's row texts, so SDN/BHD/TRADING weigh little); per-list floors calibrated
on half the gold, reported on the other half.

| Resolver | Oracle (gold span + type) | B1 spans, test half |
| --- | --- | --- |
| v1 (spelling + meaning, calibrated) | 242/271 = 89.3% | 72.0% |
| v2 (+ IDF token partial) | 269/271 = 99.3% | 77.3% (noise 0.21 rows/msg) |
| v2 + customer_aliases table | 268/271 | no gain |
| v2 + mined code-segment aliases (23 brand prefixes, 9 class segments) | 266/271 | no gain (slightly worse) |

Alias ablation (rows reduced to their label only): 23 of 271 gold mentions (8.5%) need a non-label text, and every one
is rescued by alias text that ALREADY exists: attachment-type words 10, `PROMPT_SYNONYMS` code constant 7 (cert, image,
马桶), category search_synonyms 5 (basin, hose), sales_agents.aliases 1. Mined aliases and customer_aliases rescue none.

### Run 3: full parser (v185 text, gpt-5.4-mini, 200 messages: 186 with a non-code mention + 14 others)

| Arm | Span recall | Type acc | Right row | vs L (95% CI, paired bootstrap) | Rows offered / msg (noise) | Parser ms p50 | USD / turn |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L today (lookup on) | 78.7% | 92.4% | 74.5% | - | 6.50 (4.64) | 2,806 | 0.0050 |
| N no lists at all | 73.3% | 84.5% | 67.2% | -7.4 [-12.0, -3.4] | 0 | 3,100 | 0.0049 |
| C2 two-pass: B1 -> resolver -> parser sees resolved rows only | 77.7% | 93.1% | 75.6% | +1.1 [-2.0, +4.4] | 1.94 (0.28) | 3,052 + B1 984 | 0.0054 |
| B1 + resolver v2 alone (no parser) | 88.3% | 81.5% | 80.1% | +5.5 [-0.4, +11.3] | - | 984 | 0.0005 |
| U: C2 parser entities + B1 mentions the parser left out | 90.0% | 92.2% | 85.6% | +11.1 [+6.4, +15.7] | 1.94 (0.28) | as C2 | 0.0054 |

B2 (B1 + 6 invented examples) vs B1 on the 186: recall 90.3 vs 88.3, type 82.7 vs 81.5, right row 83.0 vs 80.1.
All three parser arms are weakest on spec_key, spec_value and promotion_kind; the span extractor is not
(spec_key 71 / spec_value 87 / promotion_kind 100 recall). Some L/N/C2 misses are field-mapping gaps in the scorer
(parser files "dealer" under access_levels, "dimension" under requested_attributes); Part D re-scores with those mapped.

### Run 4 (Part D): scorer field map fixed, meaning ablation (no LLM)

The scorer now also reads where the parser files mentions outside `entities[]` (access_levels dealer/project,
requested_attributes, routing certification, escalation.company_pick). Re-scored, 200 messages ("x" = fixed map):

| Arm | Span recall | Type acc | Right row | vs Lx (95% CI) |
| --- | --- | --- | --- | --- |
| Lx today | 86.3% | 88.4% | 78.2% | - |
| Nx no lists | 79.3% | 84.9% | 72.0% | -6.3 [-10.5, -2.2] |
| C2x two-pass | 84.3% | 89.7% | 79.0% | +0.7 [-2.2, +3.8] |
| B1 + resolver v2 alone | 88.3% | 81.5% | 80.1% | +1.8 [-4.2, +7.7] |
| Ux = C2x + span mentions the parser left out | 92.3% | 89.5% | 84.5% | +6.3 [+2.5, +10.4] |
| U2 = C2x + B2 spans (186 non-code msgs) | - | - | 84.9% | +6.6 [+2.8, +10.6] |

Only the union clears zero. All parser arms are weakest on spec_value (right row 33-38%) and spec_key (36-43%); the
span pass lifts spec_key to 79%.

Meaning (cosine) ablation, resolver v2: spelling + partial alone reaches 263/271 oracle (97.0%) vs 269/271 with
meaning; on B1 spans 76.5% vs 77.3% (test half). Meaning only rescues vocabulary gaps (handbidet -> Bidet, booster pump ->
Water pump, A3 -> A3 Flyer, over flow -> Without overflow). Cold start: embedding all 4,530 list texts takes ~12 s, so
a fresh worker is spelling-only for ~10 s with today's in-process cache.

Spend: 1,462 live calls, ~USD 3.38 LLM + ~USD 0.002 embeddings (cap 1,500 / USD 6).

## Answers

**Chicken and egg.** The model does not need the values to find mentions; it needs the TYPES. A 434-token typed span
prompt with no value lists finds 88-90% of the named spans (product codes 97%). Matching to rows is code: resolver v2
reaches 99.3% given the right span. What the parser cannot do without lists is type and fill everything inside the big
parse (no-lists arm -6.3 points, significant). Precise rows from a span pass fix that without n-gram noise: rows
offered per message drop from 6.50 (4.64 noise) to 1.94 (0.28 noise).

**Aliases (owner question 2).** 23 of 271 real mentions (8.5%) need a non-label text; all 23 resolve from alias data
that already exists, and no mention in the set needs a NEW alias. 7 of the 23 depend on the code constant
`PROMPT_SYNONYMS` (`head/lookup_lists.py:57-76`), which no admin can edit. "srt" already resolves from the lookup_sets
brand_alias row and "wc" spells the WC category row, so the prompt line "Sorento = SRT, Mocha = MCH, Cabana = CBN" is
redundant (MCH/CBN do not exist in data at all). Mined aliases (23 brand prefixes, 9 class segments at >= 90-95%
purity) rescue 0 mentions: people write segments inside full codes, which resolve as products. Did-you-mean picks (47
pairs) are product codes, not list rows. AutoCount descriptions are on all 14,935 products but no mention needed them.

## Recommendation

Extract then match, two-pass, built in slices; the n-gram lookup retires once the span path proves itself in prod.

1. Span pass: one small LLM call before the parser, typed spans, schema-only prompt (B2 shape), stored as its own
   versioned prompt row. ~430 tokens in / ~35 out, p50 ~1.0 s, ~USD 0.0005.
2. Resolver (code) for every span against every list: exact, alias texts (existing tables), IDF token partial,
   trigram, meaning (today's lookup vector cache); per-list floors calibrated on spans; type is a tie-break, never a
   filter; two close rows -> ambiguous -> clarify.
3. Parser gets ONLY the resolved rows in the existing lookup blocks (same render).
4. List mentions the span pass resolved but the parser left out are added to the parse as entities (union, +6.3
   points). Never overrides a parser verdict (domain, intent, tool). Slice 3 first measures this against a parser-input
   alternative (stronger lookup-block header) and keeps the one that wins.

Cost: +~1.0 s per turn (sequential call) and +~9% LLM USD per turn.

What happens to `head/lookup_lists.py`: `load_rows` (row source, visibility rules), the vector cache and the block render
stay; `pieces()` + `shortlist()` (n-gram matching) retire after slice 2 runs a week in prod; `PROMPT_SYNONYMS` moves to
data. The prompt: lists are already out (#1865); the blocks shrink to resolved rows; alias lines are dropped in the next
version. Prompt size is rules, not lists (PROMPT-RULES-DIET is the lane for that).

Not now, with named triggers:
- Persisted shared list-vector table (text sha -> vector): build when traces show spelling-only turns after deploys
  matter; today meaning is worth ~2 oracle points and the cold window is ~10 s per worker.
- Alias mining + approval queue: build when a label-only ablation on a fresh month of messages shows >= 8 real
  mentions a mined alias would fix.
- A new unified alias table: build when an alias kind appears that none of lookup_sets, spec registry user_synonyms,
  sales_agents.aliases or customer_aliases can hold.

## Slices (one lane PR each; sizes are estimates)

| # | Slice | Size | Gate |
| --- | --- | --- | --- |
| 1 | `head/list_resolver.py`: span -> rows over all lists (exact, alias texts, IDF partial, trigram, meaning), per-list floors, ambiguity; eval script in scripts/chatbot_eval; no behaviour change | M, ~500 lines, no migration | unit tests on fixture lists; span eval >= this report |
| 2 | Span pass prompt row (migration, unlabelled) + `head/span_extract.py` + engine wiring behind a parser_config flag replacing pieces/shortlist; blocks from resolved rows; ships dark | L, ~700 lines + migration | parser-level eval: C2 >= L on this set, parser gold TRAIN + R5 no regression, p50 +<= 1.2 s |
| 3 | Union merge vs stronger header, measured (~400 calls, ~USD 2), then build the winner | M, ~300 lines | eval CI clears zero; owner hand test |
| 4 | `PROMPT_SYNONYMS` -> lookup_sets rows (migration seed); drop prompt alias lines in next version | S, ~150 lines + migration | label-only ablation unchanged; eval no loss |

Tickets: this table is the queue (crew lane; one PR per slice per owner ruling); no GitHub issues are opened.

## S1 design: `app/services/chatbot/head/list_resolver.py` (UAC AC-S1-1..14)

Reuses, does not fork: `lookup_lists.LookupRow` (list_name, key, label, texts) as the row type, `lookup_lists.Embedder`
and the provider embedder's cached `matrix()` / `pieces()` the same way `lookup_lists._meaning` does (`:197-215`), and
`candidates.similarity` (`head/candidates.py:104`) for trigram spelling. Rows come from the caller (S2 passes
`lookup_lists.load_rows(...)`, which already applies visibility); S1 loads nothing on the turn path.

Contract:

```python
SPAN_TYPES = ("brand", "customer", "salesperson", "location", "category", "spec_key", "spec_value",
              "file_type", "promotion_kind", "sales_channel", "product_code")
# span type -> the LookupRow.list_name it prefers on a tie (spec_value -> "spec")

@dataclass(frozen=True)
class Span:
    text: str
    type: str | None = None          # one of SPAN_TYPES, or None (untyped)

@dataclass(frozen=True)
class Candidate:
    row: LookupRow
    score: float                      # 0..1, best signal for this row
    signal: str                       # "exact" | "spell" | "partial" | "meaning"

@dataclass(frozen=True)
class Resolution:
    span: Span
    status: str                       # "resolved" | "ambiguous" | "unresolved" | "skipped"
    candidates: tuple[Candidate, ...] # best first; resolved -> the row; ambiguous -> every close row

def spec_key_rows(registry: Iterable[...]) -> list[LookupRow]   # from product_spec_registry.active_registry entries
def resolve(spans: Sequence[Span], rows: Sequence[LookupRow], *, embed: Embedder | None = None) -> list[Resolution]
```

Scoring per (span, row), the best over the row's texts: exact folded match = 1.0; spelling = trigram similarity;
partial = IDF-weighted share of span tokens matched by a row token (exact, trigram >= 0.6, or one edit for tokens
>= 4 chars), IDF per list over that list's texts; meaning = cosine when an embedder is given and works. A row passes
a list's floors when spell >= spell floor, or partial >= partial floor, or meaning >= meaning floor. The best passing
row over ALL lists wins; the span type only breaks ties (within the margin, prefer the typed list). Rows within
`AMBIGUITY_MARGIN = 0.03` of the best (different rows) -> ambiguous. `product_code` -> skipped.

Floors: one module constant table, values from the phase-1 calibration on the calib half
(`crew/state/eval/eem/floors_partial.json`, reported on the test half): spell 0.4-0.55, partial 0.5-0.8 (1.01 = partial off,
e.g. promotion_kind), meaning 0.55-0.65 per list. The module carries no word lists.

Eval CLI `scripts/chatbot_eval/span_resolve.py`: `--lists` (jsonl {list,row_id,label,texts}), `--gold` (LABEL-GUIDE
format), optional `--spans` (extractor run jsonl), optional `--vectors` (eem vec store dir: vecs.npy + index.json
keyed sha1(model + "\x00" + text); offline embedder, no network), `--half calib|test|all`. Prints oracle (gold span +
gold type) and right-row tables per type. Committed fixture: synthetic lists/gold/spans under
`tests/chatbot/fixtures/span_resolve/`.

Tests (tester writes first, red): `tests/chatbot/test_list_resolver.py` (AC-S1-1..11, pure, no DB),
`tests/chatbot_eval/test_span_resolve_cli.py` (AC-S1-12), plus an import guard for AC-S1-14. Existing
`tests/chatbot/test_lookup_lists_*.py` must stay green.

### Where aliases live today (scout 26 Oct, explore1020 counts; paths under sorento_crm_backend/)

| Place | What | Editable by |
| --- | --- | --- |
| `head/lookup_lists.py:57-76` PROMPT_SYNONYMS | category 3 rows / 8 words (tandas, 马桶 ...), file_type 8 rows / 20 words; merged at :295 | code only |
| `lanes/escalation.py:75-79` CO_ALIASES | sorento->srt, mocha->mch, cabana->cbn (escalation routing) | code only |
| `product_spec_registry.synonyms` / `user_synonyms` (seed `product_spec_registry.py:472`) | 527 words on 50 of 53 keys; 54 user words on 5 keys | user_synonyms: Product Specifications page (`api/v1/master_data/spec_registry.py:144`) |
| `product_categories.search_synonyms` (`models/product.py:57`) | 39 of 120 rows; copied from class synonyms by a job (`product_class_signal.py:181`) | no editor found |
| `lookup_sets` brand_alias / attachment_type_alias (`chatbot_prompt_vars.py:341-359`) | SORENTO -> SRT (1 row); Product Photos -> 6 phrases | System > Lookup Sets page |
| `sales_agents.aliases` (`models/sales_agent.py:67`) | 23 of 114 agents | Sales Agents page |
| `customer_aliases` (`models/order.py:327-341`) | 1,076 rows / 383 customers, from customer merge; read by resolver trigram tier only (`entity_resolver.py:3389`), not by head lookup | UNVERIFIED |
| `import_field_alias` supplier_inventory_word | 15 rows incl. SRT=SORENTO, WC=连体马桶 (SCM import only) | admin page |
| parser prompt text (explore1020 production row) | "Sorento = SRT, Mocha = MCH, Cabana = CBN"; tandas/马桶 -> water closet; sinki dapur -> kitchen sink | prompt edit only |

Brands have no alias column (`models/product.py:99-130`); "SRT" works only through lookup_sets brand_alias.

### Alias mining signals (read-only SQL, explore1020)

- Code prefix -> brand: 214 of 280 three-letter prefixes map to one brand; 97.1% purity over branded products (SRT 5,026
  products 92.9% SORENTO; IDC 100% INFINITY; BRW 99.7% BRAVAT).
- SRT code letters 4-5 -> class: 88.9% weighted purity (WC 545 -> Water Closet 92.1%; WB 437 -> Wash Basin 98.2%; KS 251
  -> Kitchen Sink 89.6%). Mocha codes mostly have NULL class: not minable yet.
- Did-you-mean: offer at `trace[stage=received].raw.session_vars.session_vars.open_question` (kind product_pick,
  payload.did_you_mean); pick at `trace[kind=apply].verdict.reference_positions[0]`; 161 accepted picks, 47 distinct
  typed->picked pairs (product codes, not list rows).
- AutoCount text: `products.description` filled on all 14,935 active products (of 545 SRTWC products 224 say "WC");
  Desc2 (`products.remark`) empty.
