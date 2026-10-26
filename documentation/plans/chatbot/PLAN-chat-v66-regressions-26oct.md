# PLAN: CHAT-V66-REGRESSIONS (26 Oct 2026)

Status: Plan (diagnosis). Track: small fix track per case (S); a prompt change ships as a new unlabelled
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

## Diagnosis log

(per case, filled as each is reproduced)

## Budget

USD 8 for diagnosis + gates (dev OpenAI key); report before more.
