# PLAN: CHATBOT-SET-CODES (a typed set code answers the set and its members)

Status: Build (crew answered card v1 Q1-Q5, 13 Nov; UAC final). Track: size M, lead pattern, cloud lane.
Phase 1 slice 3 of chatbot plan v2 (owner approved 12 Nov 17:28). Follows PR #2370 (code matching, merged 13 Nov).

Goal: a registered set code typed in any dash/space/case form resolves to the set and its member products through the
set membership table, instead of a wrong "Did you mean <other code>?". A part's role comes from the membership row,
never from a letter in the code. The "X" letter rule in `product_code_family.py` is replaced by catalogue data.

Out of scope: dealer close-code offers (CHATBOT-CLOSE-CODES), size offers (slice 4), prompt changes, engine stale-typo
path.

## Discovery (13 Nov, sandbox, main 0f80d519)

- The plan v2 case is already fixed on main by #2370 (not deployed): seeded `twc604-rl x 2` offers the set, then its
  members, with a `TWC609-RL` decoy not offered; a dash-folded set code is answered as the set. This lane adds the
  regression test (AC-1) only.
- Reuse: `entity_resolver.py:886` `_probe_product_set`, `:931` `_product_set_entities`, `:2136`
  `_prefix_probe_product_set`, `:3276` `visible_set_clauses`, `:3297` `_trgm_product_sets`;
  `lanes/business/answer.py:5023` `_set_then_its_members`, `:5134` `holds_every_typed_part`;
  `trace.py:479` `code_candidates_events` (extended for S4); `product_code_family.py:71` `_family_rows` (X insert
  removed, family read from `family_code` + `_family_set_members` at `:68`).
- X-insert dependency: removing it fails 20 of 642 tests in the 29 family-related files (round7 x8, own_line x8,
  AC-24 control pairs x4), all because the seeded X variant has no catalogue link. Plan (Q2 a): re-seed with a link,
  assertions untouched.

## Slices (one PR)

1. Red tests (tester): AC-1..AC-11, plus the 20 re-seeds.
2. Code (coder): X insert out of `_family_rows`; S4 trace event for set answers and offers.
3. Reviewer, `crew-tests:`, browser pass (Chatbot Console), hand-test script `laneboard/scripts/2395.md`.
