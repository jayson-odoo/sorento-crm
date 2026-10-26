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

## Phase 1 steps

1. Labelled set: >= 200 real inbound messages (masked) naming list entities; per-list counts. Sources: v66
   noise_pairs / labels, parser gold, R5/TRAIN rows. Gold = (span text, list, row) per mention.
2. Resolver harness (script, not product code): one vector store over ALL lists incl. spec values, attachment types,
   salespeople, locations, customers (reuse lookup_lists vectors); spelling + meaning + per-list cut-offs measured on
   SPANS, not pieces.
3. Run arms A/B/C on the set; record metrics + cost in a ledger.
4. Report: recommendation, PR slicing with sizes, fate of `head/lookup_lists.py` and of the prompt.

## Owner rules honoured

No hard-coded regex/keyword rules (semantic/data only); typo + language robustness (BM, Chinese); parser extracts, code
picks the tool; clarify, don't assume; truthful replies; parser-level eval is the main gate; generalise (>= 8 real
messages per behaviour). No customer names in the repo.

## Findings

(filled as Phase 1 runs)
