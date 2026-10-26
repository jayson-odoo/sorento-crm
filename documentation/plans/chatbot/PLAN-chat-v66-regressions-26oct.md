# PLAN: CHAT-V66-REGRESSIONS (26 Oct 2026)

Status: Build (F1 + F7 green with red/kill proofs; F2 waits on the crew ask; gate next). Track: small fix track per case (S); a prompt change ships as a new unlabelled
version via migration (like `lkp_0001`), owner moves labels.

## Why

Prod parser prompt moved 26 Oct ~11:02 MYT from v63 (md5 0f3b48e6, full lists in the prompt) to the
#1865 slim lookup prompt (prod v65/v66 = dev v185 text, md5 3f1e2d27). The lists (categories, brands,
locations, salespeople, customers, spec words, file types) now reach the parser per turn as
"X candidates" blocks from `head/lookup_lists.py`, built from the CURRENT message only
(`engine.py` `_lookup_lines(db, user_turn.own_text, ...)`). Owner: no rollback, fix forward.

## Cases (crew watch 11:02-12:20, contacts masked)

| # | Case | v63 | v66 |
|---|---|---|---|
| 1 | "please share new mocha promotion" -> clarify dealer/end-user -> "dealer" | 2 Mocha dealer promotions | ~50 promotions, all brands, both audiences |
| 2 | "check stock x30/x40 + share the promotion" | the live Mocha flyer | "No current promotion for PP Promo, MSS6917-BL" |
| 3 | staff 9-line list with "MSS-6910- mocha" | not-found suggests MSS6914-GM/6915-GM/6917-GM | suggests CH80020M/CH80025M/CH80030B |
| 4 | "Drawings of Mab7755 and mab7072", "srtks7051-st / srtkt72ss-st" | both products | one product / merged not-found |
| 5 | "SRT WC8317-1UNIT", then "Ya 1 Only" | quantity 1 read | quantity lost; "Ya 1 Only" read as option 1 |
| 6 | customer PO lookup (check_po) | PO only | pulls a product from 3 days earlier |
| 7 | latency | turn avg 6.2 s | 8.6 s (parser ~3.3 s both) |

## Approach

1. Diagnose each case at parser level: same message + same remembered state, v63 text vs v185 text, through
   the prompt-diet harness lookup path (`crew/state/eval/prompt-diet/harness/inject.py`, real
   `engine._lookup_lines`). One crew-note per case with the cause before fixing.
2. Fix where the cause lives: lookup data / lookup logic / clarify-merge code first; prompt text only where
   the slim text removed words the parser needed (put back the minimal words, measured).
3. Red test first per fix (`test(red):` commit, test files only), then the fix, then kill test.
4. Gate: the cases (masked) + similar real messages (>= 8 per behaviour) join the parser gold set; no
   regression vs v63 on them; R5 / TRAIN / category set no worse than v185 (the #1865 bar).
5. Latency: per-step timing on a dev copy; fix if the lookup adds time synchronously.

## ARCHITECTURE

- Layer: the parser INPUT (lookup blocks + prompt text) and the clarify-merge step that carries the earlier
  turn's filters into the answer turn. No post-parser override of the parser's verdict.
- Shared mechanism: `head/lookup_lists.py` (`shortlist`, `render`) and `engine._lookup_lines`; any fix
  applies to every list, not one word.
- Classes fixed (filled in per case after diagnosis): (a) a filter named in an EARLIER turn of the same ask
  must stay valid on a clarify-answer turn; (b) a lookup block must not invent a filter the message did not
  name; (c) multi-product messages; (d) quantity suffixes on codes; (e) unrelated old focus on a document
  lookup; (f) synchronous embedding latency.

## Diagnosis log (26 Oct; full note on PR #1872)

Parser A/B: same message + same State block; A = v63 text, full lists; B = v185 text with the real `_lookup_lines` and
the live embedder; gpt-5.4-mini; explore1020 read-only. Harness: `crew/state/eval/v66/` (ab.sh, pg_b.py, show.py).

| # | Cause | Evidence |
|---|---|---|
| 1 | PROMPT INPUT: the answer turn ("dealer") names no brand, so B has no Brand candidates row and its BRAND CANDIDATES rule forbids naming the held MOCHA; the access-level rule then maps a bare "dealer" to every brand's dealer level | `access_levels ["Mocha Dealer"]`: A 6/7, B 1/7 (B gives all three dealer levels 6/7) |
| 2 | LOOKUP NOISE: "promotion" meaning-matches `pp (PP Promo)` at 0.588 (promotion_kind floor never calibrated, 0.55) | B `promotion_kind "pp"` 1/3, A 0/3; 1,200 real messages: about 2,270 meaning-only hits, nearly all noise |
| 3 | not the prompt: same parse in both arms; the v63 comparison message had no "mocha"; the not-found suggestions are brand-scoped downstream | A/B 3/3 same |
| 4 | not the prompt: both products parsed in both arms 3/3; drop and merge happen after the parser | A/B 3/3 same |
| 5 | not the prompt: "-1UNIT" is unparsed in both arms; "Ya 1 Only" is pick [1] in both | A 4/4 = B 4/4 |
| 6 | not the prompt: PO number parsed as an order in both arms; the stale product comes from the held focus downstream | A/B 3/3 same |
| 7 | lookup cost before the parser: the piece embedding round trip (0.3-0.9 s), `load_rows` (about 0.1 s), and the shortlist loop (0.13-0.7 s on staff turns) | llm_calls parser time flat; turn medians about 4.3 s -> 6.3 s |

## Fixes

- F1 (case 1, b0c57cfb71): `lookup_lists.held_values` + `shortlist(held=...)`. The rows the State subject holds
  (brand, location, customer, channel, category, salesperson, file type) join the blocks, matched by exact name.
  Engine: `_lookup_lines(..., held=held_values(chat_state._subject(focus)))`. Measured: B 1/7 -> 7/7 Mocha Dealer.
- F7 (case 7, db0c5fcd0d): `lookup_lists.prefetch` starts the pieces' embedding before the contact checks and
  `load_rows`. The engine keeps one provider embedder (and one HTTP client) per key. Mac: median 437 -> 320 ms.
- F2 (case 2): meaning-noise options were filed to crew as one ask. Recommended: meaning only for category and file
  type.

## Budget

USD 8 for diagnosis + gates (dev OpenAI key); report before more.
