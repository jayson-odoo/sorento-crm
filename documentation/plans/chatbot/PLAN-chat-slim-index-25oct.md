# PLAN v2: retrieval (RAG) before the parser, every list (CHAT-SLIM-INDEX-PLAN, 25 Oct 2026)

Status: PLAN v2 APPROVED (owner Lavish 25 Oct 17:34). Phase 0 DONE incl. pull 2 (18:55, result below): GO categories,
spec WORD values, file types, brands, customers; NO-GO spec NUMBER values (sizes); not enough data for sales agents,
promotion kinds, locations, channels. Phase 1 (a) APPROVED by the owner (crew a25272575): categories (~USD 9) then spec word values (~USD 6), OpenAI eval
key ..bG4A only, x3, early stop, spend.log. Owner later approved file types, brands (no-regression bar), customers (shape 2, ~USD 6) and categories at x3
everywhere (~USD 13.5). Slice WC proposed to crew as lane CHAT-WC-CATEGORY-TOTAL (after #1856).
Step 1 (25 Oct 21:40): category set passed (owner, class-closed labels), R5 early stop; placement rule recorded below
("Placement rule"). Re-gate on the placement-rule variant (22:32): "srt a3 flyer" fixed, "dealer only" still drops the
channel (0/2; owner requires majority) -> early stop; the row gets no category block, so the one pointer line is the
only input change on it. Track: L, plan + eval only.
v1 (code-first + subtractive slim) is replaced by this after the owner's note of 25 Oct 17:26 (verbatim in
crew/state/inbox/slim-index-owner-1726.md): past slimming was long, costly and never better; the index should never
have been spelling-only; index matching must cover ALL list data; a retrieval step BEFORE the parser passes
candidates to the parser, which decides. Lavish page: `PLAN-chat-slim-index-25oct.html` beside this file.
Slice WC (the water-closet code bugs) keeps its UAC: `chat-slim-index-25oct-acceptance-criteria.md`.
Customer names are masked (public repo).

## One general design for all entities (owner 25 Oct: "why cant we use the same design as list ah, can keep it for DO";
## "please just move them into the same architecture so we have one unified general design for all the entities")
1. Every list (categories, spec words, file types, brands, salespeople, locations, customers): code looks the message's word
   pieces up BEFORE the parser (meaning + spelling, any language) and shows short candidate lists; customers use a
   stricter cut-off and their lines are for use only when the message names a customer. The parser picks one or none.
2. Product codes and document numbers (DO / SO / PO): exact look-up AFTER the parser (exact, then did-you-mean), never
   in a candidate list.
Owner 19:13: "we can have noise from RAG, it is fine, but is up to parser to decide and filter the noise". The design is
the list style; the customer step (crew a26741842, ~USD 10, last) proves the parser filters the noise: the failure
that counts is a WRONG CUSTOMER PICKED (esp. on category-only messages such as "tiles"), then recall. Phrase-first
(look up only the parser's customer words after the parser) runs only as the comparison arm.

## Shipping rule (crew, 25 Oct): anchored edits on the label-time text
Each phase-1 step ships as an ANCHORED EDIT list (delete / replace / insert at exact anchor text, each anchor found exactly
once, no line numbers), applied to whatever text holds the production label at that time, never a full-text replacement.
Lane SALES-TARGET-CHAT adds one sales_target value to v63's order_status list + one routing bullet as an anchored insert;
no phase-1 anchor sits in the order_status list or the sales sections, and a coexistence test applies all steps on v63 +
a simulated sales_target insert. Gates run on v63 md5 0f3b48e6 as approved; if the label-time text differs, the shipped
step is re-checked on it before the label moves (cost asked then).

## Phase 1 sequence (owner 25 Oct; crew relays a25272575 + follow-up)

| step | list | data status (phase 0) | bar | gate USD | status |
|---|---|---|---|---|---|
| 1 | categories / classes | GO: 0.961, n=180 | B beats v63 on category rows, no regression elsewhere | ~13.5 (x3 everywhere; owner OK) | category set PASSED by the owner on class-closed labels; R5 EARLY STOP (B 16/15 vs A 18/19/20); placement-rule re-gate (25 Oct 22:32, USD 0.70) R5 raw 18/19, end-to-end 19/19 (A 18/19/20) but owner hard row "dealer only" 0/2 (channel dropped) -> EARLY STOP; decision filed |
| 2 | spec word values | GO: 0.980, n=51 | same | ~6 | APPROVED, after 1 |
| 3 | file types (attachment types) | GO: 1.000, n=137 | NO REGRESSION vs v63 (goal: prompt diet, list text out, retrieval in) | ~5 | APPROVED, after 2 |
| 4 | brands | GO: 0.986, n=72 | NO REGRESSION vs v63 (prompt diet) | ~5 | APPROVED, after 3 |
| 5 | salespeople | ~25 real texts in the whole history name one (pull 3: 10): no recall bar, owner accepts | NO REGRESSION vs v63 on TRAIN + R5; the real rows (n<30) and synthetic probes from agents-mapped.json reported apart, labelled synthetic | ~5 | APPROVED, after brands |
| 6 | locations (warehouses) | ~21 real texts name one (pull 3: 15): no recall bar, owner accepts | same as salespeople (synthetic probes from the warehouse list) | ~5 | APPROVED, after salespeople |
| 7 | customer names: one more list, stricter floor (0.5/0.5), head to head with phrase-first after the parser | probe: list style at 0.5 recall 0.872, 0.66 wrong lines on name-nothing msgs, 5.15 on category-only; phrase-first 0 on both | fewest wrong customers PICKED by the parser, then recall; list style unless it picks wrong ones | ~10 (re-estimated, two styles) | APPROVED, last |
| - | spec number values (sizes) | NO-GO: 0.517 | - | - | stays in the prompt; a size is read by code (separate idea) |

Later-step costs assume arm A's v63 baseline runs are reused on the same main; a new main adds ~USD 3.5.

### Placement rule (crew decision a35332697 option (a), 25 Oct; from the categories diagnosis)
Categories step 1 passed TRAIN (B 91/91 vs A 90/89/90) but early-stopped on R5 (B 16/15 vs A 18/19/20, bar 18). The
diagnosis re-ran 12 R5 follow-ups x3 (4 lost + 8 A-passing) per variant (crew-only REPORT.md "CATEGORIES NO-REGRESSION +
DIAGNOSIS", phase1/diag/make_variants.py); all variants drop the engine's per-turn Product types line unless noted:

| variant | hits / 36 |
|---|---|
| A = v63, per-turn line kept | 35 |
| v3 = v63 text unchanged | 31 |
| v6 = v63 Product types policy line REPLACED by a one-line pointer, no section | 30 |
| v1 = both removals, no section | 28 |
| v5 = translation sentence deleted | 28 |
| v4 = Product types policy line deleted | 27 |
| v2 = removals + CANDIDATES section moved up beside the category rules | 24 |
| B = removals + CANDIDATES section at the prompt end | 16 / 24 |

Every later step builds its B text by these rules (and the categories re-gate uses them):
1. **Replace, never delete.** A list line leaving the system prompt is replaced IN PLACE by a one-line pointer
   (v6 30 vs v4 27). The pointer names the entity rule it carries and says the user turn may list candidates.
2. **No system-prompt candidates section.** No instruction section is added anywhere in the system text (v1 28 vs v2 24;
   B at the end 16 of 24). The rules about how to read candidates live in the block header, not in the prompt.
3. **Self-describing user-turn block.** The block header carries its own rule, e.g. `Category candidates (pick one only
   if the message means it):`; each list's step uses the same form with its own noun.
4. **Per-turn list lines stay until their own step.** The engine's per-turn list lines (e.g. the user-turn
   `Product types: ...` line, `turn_runtime.product_type_names`, the category list again) are left in place by every
   other list's step. Dropping that one line alone cost ~4 of 36 (v63 35 vs v3 31) and flips or5-4-01 ("a3 flyer").
   The categories re-gate therefore KEEPS it (harness `keep_types_line=True`); removing it is its own measured edit
   later, never folded into another step (UNVERIFIED that removal can pass at all).

Known limit: every edit of v63 flips some follow-ups ("yang 3 tu sahaja" is lost under every text edit tried). Crew's
decision (a) moves that class to CODE: lane RANK-REFINE-ROUTE makes held-ranking refine follow-ups (position, channel
word, "only X") robust on the #1853 seam with no prompt change. The categories re-gate (R5 x3 + TRAIN x2, ~USD 2.2,
inside crew's USD 17 hard stop) runs only once that lane's branch is available to the harness. The rule rests on 12 rows
x3; it is untested on a full gate until that re-gate.

## Phase 0 result after pull 2 (25 Oct ~18:55, retrieval only, USD 0.021 total, no parser call)

Pull 2: 183 more real messages picked by the bot's reply kind (categories, specs), labelled blind.

| list | spelling only (today) | hybrid + v63 translations as data | real mentions | verdict |
|---|---|---|---|---|
| categories | 0.928 | 0.961 (0.981 without pasted product-list rows) | 180 | GO |
| spec word values (colour, finish, material, bowl count, trap type) | 0.882 | 0.980 (50 of 51) | 51 | GO |
| spec number values (200mm, 1200mm) | 0.724 | 0.517 | 29 | NO-GO: a number is read by code, not retrieved |
| sales agents / locations | - | - | 10 / 5 | not enough data (pull 2 found none / 5) |

## Phase 0 first result (25 Oct ~18:20, pull 1 only)

Set: 1,318 real prod messages (crew pull, masked) + 3 console cases, labelled blind; 874 name no list value.
Recall@10 at each list's best score floor (GO = >= 0.95 on >= 30 real mentions):

| list | spelling only (today) | hybrid | hybrid + v63 translations as data | real mentions | lines / msg | verdict |
|---|---|---|---|---|---|---|
| file types | 0.993 | 1.000 | 1.000 | 137 | 0.8 | GO |
| brands | 0.986 | 0.986 | 0.986 | 72 | 0.1 | GO |
| customers | 0.920 unfloored, 0.573 at a usable floor | 0.960 | 0.960 | 75 | 6.0 | GO, but wrong lines on 73% of messages that name nothing |
| categories | 0.847 | 0.931 | 0.958 | 72 | 1.1 | EDGE GO (0.935 without the sales-word rows; Chinese 10/12) |
| specs | 0.800 | - | 0.933 | 15 | 1.6 | not enough data |
| sales channels | - | 0.960 on unbiased rows | - | 25 unbiased | 0.2 | not enough unbiased data |
| sales agents / promotion kinds / locations | - | 1.000 | - | 10 / 4 / 1 | - | not enough data |

In 800 random messages: file types 64 mentions, customers 41, categories 22, brands 18, specs 6, locations 0.
The two lists the owner named (categories, specs) are the two with the least real data. Details: crew-only
crew/state/eval/slim-index/REPORT.md.

## 0. Cost, time and stop rules (up front)

| step | what | parser calls | USD | time | stop rule |
|---|---|---|---|---|---|
| Phase 0 | retrieval only, every list family, real messages, recall at k=5 / k=10 | NONE | <= 0.10 (embeddings), cap 0.25 | ~1 day | a family below 95% recall@10 is NO-GO: no parser money on it. No family GO: the plan stops and reports |
| Phase 1, first family | that family's list leaves the prompt, its candidates block comes in; x3 vs v63 md5 0f3b48e6 | yes | ~8.5 (incl. arm A x3 baseline, reused later) | ~0.5 day | any bar missed: the family stays in the prompt as today |
| Phase 1, each next GO family | same, one family at a time | yes | ~5 each (+ ~1.3 once for held-out at the end) | ~0.5 day each | same; two families failing in a row stop phase 1 |
| Slice WC (separate) | 4 code bugs behind the water-closet console case; prompt unchanged | targets only | ~2 | ~1 day | normal lane: red tests first, reviewer, owner hand test |

Phase 1 starts only after the owner reads the phase 0 report and says go, with its own budget.

## 1. Phase 0: retrieval only

Goal: prove that, for each list family, a retrieval step on the message finds the right value among the top k
candidates often enough (>= 95%) that the parser can work from the candidates alone.

### Families (dev copy sorento_cagent_stack, read-only counts)

| family | rows | where the rows come from |
|---|---|---|
| categories + product classes + product types | 120 categories (11 class labels), 14 class values, 43 product types | `product_categories` (name, class_label, search_synonyms), spec class / product_type values |
| specs | 53 keys, 909 key=value pairs | `product_spec_registry` words + `product_specifications` values |
| brands | 12 | `brands` + alias rows (SRT -> Sorento) |
| sales channels | 2 | dealer, project (`services/reports/ask.py:340`) |
| promotion kinds | 5 | `promotion_types` |
| file types + certificate kinds / schemes | 21 + 1, 11 schemes | `attachment_types`, `certificates.scheme` |
| locations | 175 warehouses (71 active) | `warehouses` code + name |
| sales agents | 114 | `sales_agents` (code, person_label, aliases) |
| customer names | 6,850 (5,864 active) | `customers` (customer_name, trading_name, registered_name) |

Product CODES are not a family: they stay exact (resolver: exact, then did-you-mean with the parser's pick first,
owner 23 Oct), never enter the index and never appear in a candidates block. The v103 lineage swapped a typed code
for a listed variant on 11 TRAIN items because near codes were listed to the parser (crew/state/eval/v107/SUMMARY.md).

### Method

- Spans: every 1-4 word window of the message. A code-shaped token (letters mixed with digits, v63 L1181) is never a
  meaning or spelling span; it can only equal a list value exactly (warehouse codes such as DC1).
- Per span and family: spelling score (pg_trgm, as `head/candidates.py:41` does today) and meaning score
  (text-embedding-3-large cosine; multilingual; rows embedded once, vectors in memory). Fusion: reciprocal-rank per
  family. Output: the family's top k for the message (k = 5 and k = 10), plus a score floor variant.
- Arms: (a) spelling only = today's index; (b) meaning only; (c) hybrid; (c+) hybrid + alias rows taken from v63's own
  translations (tandas, 马桶, sinki, paip air, gambar, lukisan teknikal, sijil) to show what data adds.
- Harness: extend crew/state/eval/index-hybrid/r2/tools-h (R1 / R2 harness: embeddings + trigram already built) to
  all families, n-gram spans and k = 5 / 10. No parser, no stack, no DB writes.

### Set (real messages only for the bar)

- Real prod chat messages, read-only, masked, extracted by crew the way R2 did (r2/tools/extract_prod.py; owner
  allowed it 25 Oct ~12:10 for R2): every message that names a value from any family, plus 50 that name none
  (negatives). Hidden / held-out eval texts dropped by the same substring check R2 used.
- Plus: the owner's console cases (water closet + "Dealer <customer F> oct total sales"), and the R2 set's 90 real rows.
- Labels: each message gets the list values it names, per family (a labelling subagent from the DB lists; crew
  spot-checks 10%; owner spot-checks 20). Slices reported apart: English, Chinese, Malay, typos.
- A family needs >= 30 real positive mentions to be judged; below that it is reported "not enough real data" and
  stays NO-GO. Known thin spot: R2 found only 5 real Malay list asks in 32,988 prod messages.

### Report, per family and per slice

recall@5, recall@10 (gold value among the family's top k for that message); lines shown per message (block size);
wrong candidates on the 50 negatives; the misses listed by id for review. Bar: recall@10 >= 95% per family on real
rows -> GO for that family. Cost: embeddings only (rows ~90k tokens + spans ~50k tokens, about USD 0.02).

## 2. Phase 1: candidates replace the list, one family at a time (only GO families)

- Base text = prod v63 (md5 0f3b48e6), never the v103 lineage. For the first family, v63 gains one short CANDIDATES
  section (how to read the block; pick from it or say none fits); each family then removes its own list text from v63
  and its candidates block comes in on the user turn, built by the phase-0 retrieval.
- Order (largest prompt text and the owner's complaints first): specs + product types (v63 L1796-1846, 10.2k chars),
  categories + classes (examples + translations), file types + certificates (L330-371), brands ("Known brands" line),
  locations, sales agents, customers (no prompt text today: the block adds candidates only), channels + promotion
  kinds (tiny, last).
- The parser still decides; code only retrieves. The candidates block carries no product codes (the existing
  `_code_candidates` lines, `head/candidates.py:364`, stay off; a test asserts it).

### Gate per family (x3 per arm; arm A = v63 0f3b48e6 on the same main, runs reused across families)

| set | pass bar (majority over 3 runs) |
|---|---|
| TRAIN 118 (engine-built) | B >= A - 1 whole-parse; products: 0 new code swaps, paired product losses <= 1 |
| R5 ranking 62 | B >= A - 1 |
| the family's real rows from phase 0 + console cases | B > A, and B right 3 of 3 on every console case |
| Chinese / Malay rows of the family | B >= A |
| drift | B's run-to-run flips <= A's |
| held-out 113 (crew-only), once after the last family | B >= A - 2 |

Stop rule: a missed bar keeps that family in the prompt as today (recorded, next family); two families failing in a row
stop phase 1. Spend per family is capped at its estimate + 20%.

## 3. Slice WC: the water-closet code bugs (separate, prompt unchanged)

A paid probe (USD 0.05, 9 calls, crew/state/eval/slim-index/LEDGER.md) showed v63 marks "water closet" as a category
6 of 6 and the customer 9 of 9; each wrong reply is code (paths under `sorento_crm_backend/app/`):
1. A category hint is widened to promotion and to customer (`services/entity_resolver.py:122-146`) -> resolve it
   through the existing category resolver (`services/chatbot/lanes/business/services.py:638-842`) on every report ask.
2. The customer picker counts every token, the category token included (`services/chatbot/lanes/business/gate.py:432-436`)
   -> skip category tokens, as warehouse tokens already are (`gate.py:298-338`).
3. The sales total takes no category (`api/v1/order_management/orders.py:1790-1830`, `services/sales_report_delivered.py:317-328`,
   `services/chatbot/lanes/business/fetch.py:1085-1126`) although the dataset filters by it
   (`services/reports/datasets/delivery_order_lines.py:217-218`) -> one `category_ids` parameter through the three layers.
4. A customer pick that merges to one company still asks (`services/chatbot/answer_bridge.py:875`, not re-checked as
   `:917` does) -> one company = no pick.
These are bugs whatever phase 0 shows. Gate: parser input byte-equal A vs B ($0), console + ~20 real target turns x3
per arm, EXPLORE-1023C x1 per arm; red tests first, reviewer, owner hand test (UAC file). Starts after PR #1856
merges (it touches `report_ask.py` / `engine.py`). Whether "Dealer <customer F> oct total sales" still says "can't
break sales down" after #1856 is UNVERIFIED; it is checked on the slice's first run.

## 4. Risks

| risk | guard |
|---|---|
| retrieval misses a value, so the parser cannot pick it | the 95% bar per family; misses listed for review; a family below the bar stays in the prompt |
| a big block (9 families x k=10) adds noise and tokens | block size reported in phase 0; score floor variant; phase 1 adds one family at a time |
| customer names: 6,850 rows, short forms, shared words ("water") | judged as its own family; it has no prompt text to remove, so it is measured last |
| code swaps return | codes never in the index or block; zero-swap bar |
| Malay data thin | reported "not enough real data" rather than a claimed recall |
| prompt drift (+-3 items per v63 edit) | x3 per arm, majority scoring, drift bar |
