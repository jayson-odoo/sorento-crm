# PLAN: CHATBOT-SET-CODES C, a spec word answering a "Did you mean" picks the option that holds it

Status: in progress (small fix track: expected diff under ~300 lines, no migration, no auth change).
Lane: CHATBOT-SET-CODES, follow-up to #2395. Card C ruled by crew from the owner's 14 Nov ruling.

## Problem

Over an open "Did you mean 1. CWC604-P-RL 2. CWC604-S-RL", the reply "S trap" is read as no pick in
about 2 of 7 live tries (CREW-PASSES-4 on 27dad150). The parser sees each option as a bare code, so
nothing links the spec word to option 2. With no pick the turn becomes a new ask
(`turn/decide.py:637-638`) and the spec word runs as a catalogue search.

## Rule (owner ruling 14 Nov: the model judges, no hard fuzzy rules)

1. The parser's per-turn input lists each open option with the specs the catalogue records for its
   products, only where the offered options differ (a shared part adds nothing), in the option's
   `label` field that template v74 already defines (R-P1-01, R-P1-05). No template change.
2. No code turns a parser "no pick" into a pick.
3. While a "Did you mean" pick is open, a reply whose parse has no pick and only spec entities asks
   the same options again (never a catalogue search, never a guess).
4. Every "Did you mean" pick, generic: spec labels come from the spec registry and product
   specifications, not from words in code.

## Where

- Options to the parser: `engine.py:6260-6266` (`question.of_pending`, `turn/question.py:43-57`).
- Spec notes: a helper beside `held_spec_lines` in `head/closed_lists_index.py`, reusing
  `candidates._registry`, `display_spec_value` and the registry label.
- Re-ask: a sibling of `_stock_pick_requantified` (`turn/apply.py:3511`) sharing its re-ask body.

## Tests (red first)

- The parser input for the did-you-mean turn carries each option's differing spec, not the shared part's.
- A spec-only reply with no pick re-asks the same options, with no stock read.
- Lock: pick 2 answers both S parts (existing t1 / t2h tests).

## Gates

Red-first + kill test, reviewer, crew-tests, frozen set LIVE x3 by crew, owner before/after hand
test before any merge. If the model still misses after live x3, report back (crew then asks the owner
about a prompt rule, Phase 3).
