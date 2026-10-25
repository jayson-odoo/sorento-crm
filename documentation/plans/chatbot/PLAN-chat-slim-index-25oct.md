# PLAN v2: retrieval (RAG) before the parser, every list (CHAT-SLIM-INDEX-PLAN, 25 Oct 2026)

Status: PLAN v2 APPROVED (owner Lavish 25 Oct 17:34: phase 0 go incl. crew's read-only masked prod pull; slice WC go
after #1856, proposed to crew as lane CHAT-WC-CATEGORY-TOTAL). Phase 0 IN PROGRESS: pull spec filed with crew,
retrieval harness being built (crew/state/eval/slim-index/, crew-only). Phase 1 not started.
v1 (code-first + subtractive slim) is replaced by this after the owner's note of 25 Oct 17:26 (verbatim in
crew/state/inbox/slim-index-owner-1726.md): past slimming was long, costly and never better; the index should never
have been spelling-only; index matching must cover ALL list data; a retrieval step BEFORE the parser passes
candidates to the parser, which decides. Lavish page: `PLAN-chat-slim-index-25oct.html` beside this file.
Slice WC (the water-closet code bugs) keeps its UAC: `chat-slim-index-25oct-acceptance-criteria.md`.
Customer names are masked (public repo).

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
