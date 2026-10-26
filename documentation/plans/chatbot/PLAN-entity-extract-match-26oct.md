# PLAN: ENTITY-EXTRACT-MATCH - parser extracts mentions, resolver matches them

Status: Phase 1 (scout + measurement, report only, no product code). Track: L (chatbot architecture), lead pattern.
Owner OK on the design from the numbers is required before any product code.

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
