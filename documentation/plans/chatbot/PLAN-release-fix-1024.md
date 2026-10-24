# PLAN: four canonical-code failures blocking the 24 Oct release (RELEASE-FIX-1024)

Status: PR #1840 open, reviewer READY (small fix track: one guard in `head/grounding.py` plus its tests, well under 300
lines; no migration, no auth/RBAC change, no new ingest surface).

Release run 40053956497 (main 2b052c4ca1, `full_suite=true`) failed shard 1 of the backend suite with
four tests, all in `tests/chatbot/test_canonical_code_resolution.py`:

- `TestRealResolver::test_a_type_word_beside_the_code_reaches_the_tool_as_that_code`
- `TestRealResolver::test_a_miss_on_the_canonical_token_is_named_as_typed`
- `TestRealResolver::test_the_owners_fifteen_line_stock_check_reaches_the_tool_with_fourteen_codes`
- `test_the_entities_only_arm_places_the_canonical_code_on_the_typed_row`

## Reproduction and bisect

On a CI-style throwaway DB (`scripts.bootstrap_env`), the file runs 26 passed on prod b3661280a6 and on
8cd4482105 (#1837), and 4 failed / 22 passed on 21b09e2700 (#1825) and on main 2b052c4ca1.

## Cause (product defect, not a stale test)

#1825's Q1 step (owner ruling (a), 23 Oct: a typed code the parser corrected asks did-you-mean, the
parser's pick first) lives in `grounding.ground` (`head/grounding.py` ~962). It reads "the parser
corrected the code" as `token_key(raw) != token_key(canonical_code)`. That is also true of every entity
AC-RSF-01 (RESOLVE-SEMANTIC-FALLBACK, #1511) defines: a type / colour / brand word beside the code, raw
"TAP ZZTWT5608", canonical_code "ZZTWT5608" exactly as typed. The raw's own token "TAPZZTWT5608" resolves
nothing, the canonical is its trigram neighbour, so Q1 drops the canonical and the turn asks
did-you-mean (or the code reader) for a code the dealer typed correctly. The "Tier-3 query embedding
failed for token=TAPZZTWT5608" log lines are a symptom: that token is only looked up because the
canonical was dropped (CI has no embedding key, so the tier logs and falls back to trigram).

The four tests guard AC-RSF-01 / AC-RSF-13 / AC-RSF-15 (`resolve-semantic-fallback-06oct-acceptance-criteria.md`)
and stay unchanged.

## Architecture

- Layer: the head's grounding step, the one place Q1 decides "corrected typo". No change to the parser,
  the resolver, `resolve_gate.pick_near_code_first` or the did-you-mean composer.
- Shared mechanism: `turn.state.token_key` (the resolver's own fold), the same key Q1 already compares.
- Class fixed: any product entity whose canonical_code appears WHOLE in its raw (one word, or a run of
  adjacent words, folded with `token_key`) is a strip of the words beside an exact code (AC-RSF-01 /
  AC-RSF-03: the model never corrects), so it is never a correction. Not a one-shape fix: covers a type
  word before or after, colour / brand words, a spaced code.
- What still asks did-you-mean (Q1 unchanged): the canonical is NOT among the raw's words
  (`srttw8259gm` -> `SRTWT8259-GM`, `TAP ZZTWT5680` -> `ZZTWT5608`, `ZZTWT56081` -> `ZZTWT5608`).

## Tests

1. `test(red):` a Q1 guard in `tests/chatbot/test_near_code_typo_dym.py`, both paths: a type word
   before the code (also with a spaced code) and colour words after it answer the stock line
   directly, no did-you-mean. Red on main: the 4 type-word cases; `colour_words_after` is green
   before the fix too (its raw resolves by prefix narrowing) and stays as a class guard.
2. The four release tests above go green unchanged.
3. Kill test: drop the guard, the 4 red cases and the four release tests go red again (8 failed).
4. Siblings: the 71 `tests/chatbot/` files that touch grounding / the resolver / the code reader
   (`-n 2`): 1819 passed; 1 local Postgres "out of shared memory" flake, green on rerun.

## Open (not in this fix)

- `raw.split()` keeps punctuation stuck to a word, so "TAP SRTWT5608," still reaches Q1 (reviewer
  nit). Trigger to act: a measured turn where a parser raw carries edge punctuation.
