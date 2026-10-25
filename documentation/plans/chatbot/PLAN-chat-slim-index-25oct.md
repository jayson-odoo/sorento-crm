# PLAN: slim parser prompt + hybrid meaning index (CHAT-SLIM-INDEX-PLAN, 25 Oct 2026)

Status: PLAN, waiting for the owner's yes/no (crew report --ask). No code yet. Size L overall; slice 1 is M
(full pipeline: UAC, red tests first, reviewer). Lavish page: `PLAN-chat-slim-index-25oct.html` beside this file.
UAC for slice 1: `chat-slim-index-25oct-acceptance-criteria.md` beside this file.

Owner ask (25 Oct ~17:00): "the category matching is quite weak in the current prompt, same goes for the spec
matching, that's why I am eager to go to index matching semantically and also have a slimmer prompt version".

Customer names are masked in this repo (public): "customer F" is the dealer in the owner's console case.

## 1. Console failures (prod, prompt v63 md5 0f3b48e6)

1. "Dealer <customer F> oct total sales for water closet" -> a 10-way customer pick on "water" (customers with
   WATER in their name) -> "Which one do you mean? 1. <customer F>" (one option) -> after "1": "Couldn't pin down
   'water closet' (promotion). Closest matches: 5. Water Closet.pdf x2".
2. "Dealer <customer F> oct total sales" -> pick "1" -> "I can't break sales down by customer yet"
   (the pick-resume part is lane CHAT-CUSTOMER-PICK-RESUME, PR #1856, open).

## 2. What is true today (measured or read, 25 Oct)

### 2.1 The parser reads failure 1 right; the code does not

Probe (this lane, USD 0.0496, 9 calls, dev key ..bG4A, prod v63 text = copy id 44e007d0, md5 0f3b48e6 checked on
sorento_explore1020, repo runner `scripts/chatbot_eval/parser_gold live`, x3 per message, crew-only data):

| message | entities (3 of 3 runs) | order_status (3 of 3) |
|---|---|---|
| c1 "Dealer <F> oct total sales for water closet" | `<F> sanitary` customer, `water closet` category | sales_analysis |
| c2 "Dealer <F> oct total sales" | `<F>` customer | sales_analysis |
| c3 "<F> water closet sales october" | `<F>` customer, `water closet` category | sales_report |

So v63 already marks "water closet" as a category 6 of 6. The runner row does not carry sales_channel or the date
filter, so whether v63 keeps "dealer" and "oct" on c1 is UNVERIFIED (the slice-1 gate measures it on the turn).
v63 calls c1/c2 `sales_analysis`, which its own text reserves for company totals with no customer (v63 L1367-1372).

Why the reply went wrong (code, origin/main bb99b21c77, paths under `sorento_crm_backend/app/`):
- A `category` hint has no generic resolver. `_expand_entity_types` widens it to promotion by default
  (`services/entity_resolver.py:122-125`) and to customer / transporter under the order domain
  (`services/entity_resolver.py:80`, `:134-146`). No generic probe reads `product_categories` or `class_label`.
- The only category resolver is the sales-ranking lane: `take_words` (`services/chatbot/lanes/business/report_ask.py:438-462`,
  runs only for order_status sales_ranking) -> `_word_filters` (`report_ask.py:836-864`) -> `resolve_category_token`
  (`services/chatbot/lanes/business/services.py:638-673`) and `resolve_category_class` (class_label + search_synonyms,
  `services.py:802-842`).
- Reply 1: the gate's customer picker counts customer rows from EVERY token, the category token included
  (`services/chatbot/lanes/business/gate.py:432-436`); it skips only tokens hinted warehouse (`gate.py:298-338`) and
  cuts at 10 (`gate.py:1138`).
- Reply 2: the customer arm checks for 2+ options before the options are merged by trading name
  (`services/chatbot/answer_bridge.py:840-853`, `:875`; `turn/narrow.py:156-163`); the other arm re-checks
  (`answer_bridge.py:917`), this one does not, so one company prints as a one-option pick.
- Reply 3: after the pick the turn has no domain (`lanes/business/resolve_gate.py:1026-1028`), so no domain filter
  applies (`lanes/business/answer.py:5142-5143`) and the category token falls back to promotion; the did-you-mean
  shows `Promotion.description` (`lanes/business/miss_suggest.py:83-99`), which n8n fills with the flyer's file name
  (`api/v1/external/promotions.py:220-227`), hence "Water Closet.pdf".
- Even a right resolution has nowhere to go: the sales total route takes customer_ids, brand_ids, channel and
  product_code but no category (`api/v1/order_management/orders.py:1790-1830`; engine params
  `services/sales_report_delivered.py:317-328`; chat wiring `lanes/business/fetch.py:1085-1126`), although the
  dataset filters by category already (`services/reports/datasets/delivery_order_lines.py:217-218`, `:301`).

### 2.2 The prompt

v63 = 140,897 characters, 1,848 lines (section map: crew scratch `v63-section-map.md`, 41 contiguous sections).

| kind | chars | share |
|---|---|---|
| routing rules (ask kind, domain, order status) | 53,486 | 38.0% |
| follow-up / state (picks, open question, carry) | 44,662 | 31.7% |
| vocabulary lists | 24,152 | 17.1% |
| output schema | 11,990 | 8.5% |
| policy block header | 3,706 | 2.6% |
| product-code reading | 2,901 | 2.1% |

- v63 spells out NO category list, brand list, certificate list, promotion kinds or warehouse list. Categories appear
  only as examples (water closet, tap, kitchen sink, basin), and only in the ranking, top-selling and low-stock
  sections (L1018-1047, L1067-1076, L1557-1583, L1624-1652); the sales report section (L1141-1211) has none.
- The biggest vocabulary blocks: spec lines in the machine-made policy block L1796-1845 (9,651 chars, 45 keys;
  L1834 alone lists 28 seat-cover PRODUCT CODES as spec values), incoming date fields L241-301 (5,023), low-stock
  category translations L1006-1062 (3,946, incl. tandas / 马桶 -> water closet), file-type synonyms L330-371 (2,791),
  product types L1846 (596, 47 types; "Water Closet" is not one of them).
- Brands come per turn on a "Known brands:" user-block line (L1485-1500); per turn the engine also adds full
  product-type and product-detail lines (`services/chatbot/engine.py:4535-4536`).
- Prod v63 gets NO candidate lines and no code shortlist: they exist only for a prompt carrying "== CLOSED LISTS =="
  (`services/chatbot/head/parser.py:951`, `engine.py:4548-4561`). The v103 lineage carried CLOSED LISTS + CODE LOOKUP
  (near codes listed to the parser) and lost 11 TRAIN items by swapping a typed code for a listed variant
  (crew/state/eval/v107/SUMMARY.md).
- One parse: 38,870 prompt tokens, 96.5% cached, ~USD 0.0055, parser ~4 s (probe rows). A smaller prompt saves little
  money; v103 (76k chars) cost 0.68 vs v63 0.74 per TRAIN run (v107 LEDGER rows 6-7).

### 2.3 Earlier measurements this plan builds on

- PROMPT-V109 / V107 (crew/state/eval/v109, v107): every 4-30 line edit to v63 moves unrelated parses +-3 items on
  gpt-5.4-mini; x1 gates on n=23 slices fail on one flip. v107 = v103 (lean rewrite, 76k) + 3 rules lost TRAIN 64 vs 93 (paired 38:9; v103 alone loses the same way on the split items):
  code swaps, BM/ZH 100 -> 47.8, typos 100 -> 33.3, follow-ups 67.7 -> 41.5.
- INDEX-HYBRID R1/R2 (crew/state/eval/index-hybrid): spelling + text-embedding-3-large lifts list recall on real rows
  0.63 -> 0.82, real Chinese 3 -> 11 of 23, at 2.6x the false hits (37 -> 98; 14 false hits on 25 negative messages). Showing the hits
  to the parser as hint lines did not move it (+3 / +0 of 20). text-embedding-3-small adds nearly nothing.
  Cost: ~USD 0.0000012 per query, p50 350 ms; rows embed once per list change.
- Data (dev copy sorento_cagent_stack, read-only): 120 categories (11 class labels, `search_synonyms` column exists,
  `models/product.py:34`), 14 class spec values, 43 product types, 53 spec keys / 909 key=value pairs, 12 brands,
  21 file types + 1 certificate kind, 11 schemes, 5 promotion types, 2 sales channels (`services/reports/ask.py:340`).
  1,005 products carry class Water Closet; 110 more WC bodies get it from WC-CLASS-FIX (next release, data).
- Product embeddings already exist (text-embedding-3-small, `entity_resolver.py:3039`, min 0.80) but the chatbot
  grounding call runs with semantic_fallback=False (whether tier 3 is off on that path is UNVERIFIED).

## 3. Target shape

One rule for every closed list: **the parser marks the words and what kind of thing they are; code decides
which list value they mean.**

```
message --> PARSER (slim)                         --> CODE
            - ask kind, period, quantity,             - product codes: exact -> did-you-mean (unchanged)
              follow-up, picks (v63 rules, kept)      - customers: customer resolver (unchanged), never fed
            - spans + role: product code |              by a product-kind span
              customer | product kind | property |    - product kind / property / file type spans:
              file type | brand | person              SPAN INDEX (exact, alias rows, near spelling,
            - raw copied exactly as typed              multilingual meaning) -> decide or ask
                                                       - report engines take the decided filter
```

- **Span index** (code, one module beside `head/closed_lists_index.py`): lists = categories (name, class label,
  search_synonyms), product classes, product types, spec values (registry words + values), file types, certificate
  kinds. Rows are DATA: the translations the prompt carries today (tandas, mangkuk tandas, 马桶, sinki, paip air,
  gambar, lukisan teknikal, sijil) move into `search_synonyms` / alias rows, so nothing the prompt knows is lost.
  Steps per span: exact or alias -> near spelling (today's trigram >= 0.55) -> meaning (text-embedding-3-large,
  vectors in memory per rows hash, one call per span that missed the first two steps).
- **Decision (code)**: one clear value -> filter; two close values, or a meaning-only hit below the high bar -> one
  question with at most 3 options (clarify, not assume); nothing -> say the word back. A product-kind span never
  falls back to promotion, customer or a file name.
- **The index reads only the span the parser marked**, never the message, so the owner's 5 Oct rule (no fuzzy
  matching of the message in code) holds; the 11 Oct clarification already allows similarity inside a resolver.
- **Small lists stay full lines in the prompt** (owner 22 Oct): brands (12, "Known brands:" line + alias rows such as
  SRT -> Sorento), sales channels (2), promotion kinds (5).
- **Product codes stay exact.** Codes never enter the span index. The parser copies the typed code (v63's code-reading
  rules stay word for word: the PRODUCT-CODE sections, 2,901 chars, and the code lines inside other sections); the resolver does exact -> did-you-mean with the parser's pick first when
  raw != canonical (owner 23 Oct). No candidate or near-code lines are ever shown to the parser (no CLOSED LISTS / CODE
  LOOKUP marker in any slim version; a test asserts the gate at `head/parser.py:951` stays off). The 28 seat-cover
  codes leave the prompt with the spec lines. Every prompt gate carries a zero-code-swap bar.
- **Slim prompt = subtraction from v63, never a rewrite** (the v103 rewrite lost 38:9 on TRAIN). Per section:

| v63 sections | chars | in the slim prompt |
|---|---|---|
| 1-7, 9-23, 27-29, 32, 36-38, 41 (routing, follow-up, schema, product codes, escalation, policy header) | ~97,500 | kept word for word |
| 39 policy spec lines L1796-1845 (45 keys, 28 codes) | 9,651 | OUT: span index; one line keeps the spec KEY names |
| 40 product types L1846 | 596 | OUT: span index |
| per-turn product-type / product-detail lines (`engine.py:4535-4536`) | not measured | OUT: span index |
| 8 file-type synonyms (gambar, lukisan, sijil ...) | ~1,500 of 2,791 | OUT to alias rows; flyer flag + access levels kept |
| 24 low-stock category translations L1018-1023 | ~1,000 of 3,946 | OUT to search_synonyms; filter rules kept |
| 31 specification entity examples | ~2,000 of 3,449 | SHRINK to one rule: kind words -> product-kind span, property words -> property span, raw as typed |
| 33 Known brands | 1,212 | kept (small list, 22 Oct ruling) |
| 25, 26, 30, 34, 35 sales ranking / report / analysis / top selling | 21,737 | kept in phase 3; phase 4 candidate (ask kind decided in code) |

  Phase 3 removes ~15k chars (v63 -> ~126k, -10%). The real size win is phase 4 (sales ask kinds into code,
  another ~22k), and only if phase 3's numbers say edits on the smaller prompt drift less.

## 4. Slice 1: failure 1 end to end (code only, prompt stays v63)

Why code first: the probe shows v63 already marks the category; every broken step is code (section 2.1). A code
slice moves no parse, so it carries none of the +-3 drift that sank V107 / V109.

Builds (one lane, red tests first, reviewer, owner hand test):
1. A product-kind span (hint category / product_type) resolves through the existing category resolver
   (`resolve_category_token` / `resolve_category_class`, `services.py:638-842`) on EVERY report ask, not only
   sales_ranking; `_expand_entity_types` stops widening these hints to promotion / customer
   (`entity_resolver.py:122-146`).
2. The gate's customer picker skips tokens hinted category / product_type, as it skips warehouse (`gate.py:298-338`).
3. The sales total takes a category filter: `category_ids` on the sales-report route (`orders.py:1790-1830`) ->
   engine params (`sales_report_delivered.py:317-328`) -> chat wiring (`fetch.py:1085-1126`); the dataset already
   filters (`delivery_order_lines.py:217-218`). One parameter through three layers, no rerouting, so the total keeps
   the answer format the owner knows.
4. A customer pick that merges to one company is no pick: answer with it (the "one clearly meant code = answer"
   rule, 17 Oct, applied to customers), re-checked after the merge as `answer_bridge.py:917` does.
5. A total that names a customer is the customer's total even when the parser says sales_analysis (code reads the
   customer entity; no prompt edit). Exact seam chosen in the UAC round after #1856 merges (it touches
   `report_ask.py` and `engine.py`).

Not in slice 1: the meaning index, BM / ZH words ("tandas"), any prompt text.

### Gate (arm A = main + prod v63 md5 0f3b48e6; arm B = slice-1 branch + the same v63 row; gpt-5.4-mini, reasoning
off, composer off, dev key ..bG4A, copy DB sorento_explore1020)

| # | what | runs | pass bar | USD |
|---|---|---|---|---|
| G1 | parser input byte-equal: system prompt + engine-built user block, A vs B, on TRAIN 118 + R5 62 + console set | dry, no LLM | 100% equal (a code slice must not move any parse) | 0 |
| G2 | target turns: console c1 (+ the "1" follow-up), c2, c3 + ~20 real prod "customer + period + total + product kind" messages (crew extracts and masks; else real-shaped rows on dev customers) | x3 per arm | B right 3 of 3 on every row (customer total, product-kind filter, period, channel when said); 0 promotion / file / customer-pick lines on any row; A's rate recorded (expected low) | ~1.2 |
| G3 | regression: dealer battery 117 conversations + EXPLORE-1023C 23 rows | x1 per arm, x3 on any flipped row | no row worse in 2 of 3 runs | ~3.3 |
| G4 | pytest red-first + kill proof; touched suites only | local | green | 0 |

Slice-1 gate total: ~USD 4.5, cap USD 5.

## 5. Phases after slice 1

| phase | builds | gate | USD |
|---|---|---|---|
| 2 span index (prompt stays v63) | span index module; alias / search_synonyms rows from v63's own translations; the slice-1 resolver asks the index when exact misses; file types + certificate kinds through the same index | I1 index-only on the R2 real set relabelled with categories / classes + new real product-kind rows (incl. every real zh / ms row): recall >= 0.85, 0 silently decided filters on the 25 negatives (a question is allowed), vs today's resolver measured first (embeddings ~USD 0.01). I2 turns x3 per arm on ~60 real product-kind rows (typos, "tandas", 马桶, "WC", "toilet bowl"): B >= A on every slice, B right 3/3 on the console rows. I3 battery x1 regression | ~5 |
| 3 slim prompt step 1 (vocab out) | v63 minus the OUT / SHRINK rows of the section table (~126k); per-turn product lines off; no CLOSED LISTS / CODE LOOKUP marker | x3 per arm: TRAIN 118, R5 62, product-kind set ~100, console; HIDDEN 113 x1 per arm (crew-only); battery x1. Bars: TRAIN whole-parse majority B >= A - 1; products: 0 new code swaps, paired product losses <= 1; BM/ZH slice B >= A; product-kind set B >= A; HIDDEN B >= A - 2; battery no row worse in 2 of 3. Plus drift: B's run-to-run flips <= A's | ~14 |
| 4 slim prompt step 2 (sales ask kinds into code) | only if phase 3 passes and its drift is <= A's: sections 25, 26, 30, 34, 35 collapse to "a sales ask + its axes and filters"; code picks total / ranking / analysis from the fields (fixes the c1/c2 sales_analysis class at the source) | same shape as phase 3 + R5 + dealer battery x3 | ~14 |

Spend so far this lane: USD 0.05 (probe). Each phase is its own lane and its own owner ask for budget.

## 6. Risks

| risk | evidence | guard |
|---|---|---|
| meaning hits pick the wrong value | R2: large model 98 false hits vs 37 on real rows, 14 on 25 negative messages | meaning-only hits never decide silently: below the high bar they ask; negatives bar in I1 |
| prompt edits drift unrelated parses | V109: +-3 items per edit | slice 1 and phase 2 change no prompt; phases 3-4 x3 per arm, majority scoring, drift measured on A twice |
| product-code swaps come back | v103: 11 TRAIN swaps from listed near codes | codes never in the index or the parser input; zero-swap bar; marker-off test |
| BM data is thin | R2: only 5 real Malay list asks in 33k prod messages | Malay words enter as alias rows (data the owner can read), not as a recall claim |
| class data gaps make a filtered total too low | WC-CLASS-FIX: 110 WC bodies had no class | data ships with the next release; the answer header names the filter it applied |
| overlap with open lanes | #1856 touches `report_ask.py`, `engine.py` | slice 1 starts on main after #1856 merges |
| latency | embedding p50 350 ms | only on spans that miss exact / alias / spelling; 0 ms otherwise |

## 7. Owner hand test (slice 1, crew test copy)

1. "Dealer <customer F> oct total sales for water closet": one reply, customer F's October total, water closet
   only, dealer channel; no customer pick, no promotion or file line.
2. "Dealer <customer F> oct total sales": customer F's October total; no "can't break sales down" line.
3. "<customer F> sales this year for basin": this year's total, basins only.
4. "<a customer whose name contains WATER> oct total sales": that customer's total (customer words still work).
5. "SRTWC286 oct total sales": the product's total (codes unchanged).

## 8. Questions for the owner

1. Boundary: the parser marks the words and their kind; code decides the list value (spelling + meaning) and asks
   when unsure. (a) yes, recommended: R2 showed hint lines shown to the parser do not move it (+3 / +0), and the
   code already decides product codes this way (owner 23 Oct). (b) keep the 16 Oct D2 split: code shortlists,
   parser picks.
2. Order: slice 1 (code only, v63 unchanged) first, then the index, then the slim prompt. (a) yes, recommended: v63
   reads the category right 6/6; the misses are code. (b) build the slim prompt first.
3. An unsure product word (two close classes, or a meaning-only hit): (a) one question with at most 3 options,
   recommended (clarify, not assume); (b) take the top hit and name it in the answer header.
4. Slim scope: (a) phase 3 = vocabulary out only (~-10%), phase 4 decided later on its numbers, recommended;
   (b) aim for a v103-size prompt (-45%) now (v103 lost 38:9 on TRAIN).
5. Budget: slice-1 gate USD 5 now; phases 2-4 each asked separately (~5, ~14, ~14). (a) yes; (b) other.
