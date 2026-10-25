# INDEX-HYBRID-R2: hybrid index verdict round 2 + CODE-SUBSTRING port (25 Oct 2026)

Status: in progress (crew lane INDEX-HYBRID-R2). Track: research S; port = small fix track (port of reviewed #1755 rounds 8-9, no migration, no auth change).

Brief: crew/state/briefs/INDEX-HYBRID-R2.md. Owner approved the prod-clone read 25 Oct ~12:10.

## A. Research (no repo code; everything under crew/state/eval/index-hybrid/)

Round 1 (23 Oct, REPORT.md there): verdict no build; non-English provisional (real ms 0, real zh 6).

1. Top up the TRAIN set from sorento_prod_1020 READ-ONLY: >= 15 real Malay and >= 15 real Chinese inbound
   customer messages that name a closed-list value (spec / file type / cert). Only the message text is
   extracted; person names, phones, emails masked (fake, stable). Data never enters this repo, a PR or a gist.
   If the permission layer blocks the read: stop and ask crew with the exact blocked command.
2. Rerun the harness (tools/README.md there), TWO runs per arm: (a) spelling index, (b) + text-embedding-3-small,
   (b) + text-embedding-3-large, plus the parser test on 20 messages. LLM spend logged in USD within caps.
3. Report recall per language, wrong matches, parser score per run; gate: build only if hybrid beats spelling by
   >= 3/20 in BOTH parser runs. No hybrid build until crew relays the owner's go.

## B. Port #1755 rounds 8-9 onto main (this branch, its own PR)

Why: the Index on main (head/closed_lists_index.py, candidates.py) came in through the EXPLORE-1021C releases
(#1823/#1825) without #1755's round 8-9 resolver fixes, so a CLOSED LISTS prompt going live would run the older
code-substring behaviour.

Scope (from #1755, branch claude/chat-closed-lists-x6ymb5):
- CODE-SUBSTRING: a registry word (class / type / spec word) never reaches a product through its code, substring
  or whole segment; one early drop `_drop_word_code_fragments` (app/api/v1/system/references.py) is the only gate;
  whole typed codes, digit fragments, non-registry code families keep working. Commits bf462eb739, d52ea77e66,
  fcb6fb589a, 20b385e244 (+ entity_resolver.py, product_predicate_service.py).
- AND-ROW-REGISTRY (round 9): every token of an AND row checked against the registry in the form the probe matched
  it by. Commits 83d697a768, b01b363750, 1dd6270383, d9d9651e53.
- DUP-CODE-LABEL: a code two companies share is named with its company on every domain; picker lines key on
  product id. Commits 6b8986ed7a, c6e038a66f (lanes/business/gate.py, pickers.py).
- Tests (5 files): tests/chatbot/test_closed_lists_code_substring.py, tests/chatbot/test_closed_lists_and_row_registry.py,
  tests/chatbot/test_picker_duplicate_code_company.py, tests/test_resolve_predicate.py, tests/test_resolve_spec_fallback.py
  (+ the sign-off amendments in tests/chatbot/divergences.py and tests/chatbot/test_resolve_gate_unit.py).
- Out of scope: the rest of round 8 (CLASS-NAMED-OFF-UNDER-STATE, owner a35818889 (b) hidden key, KEEP) and the
  spec_bare_size migration.

Order: test(red) commit of the ported tests alone, red proof on main code, then the code port, kill proof,
reviewer, PR. Touched tests only locally (pytest -n 2).

## Open item for the owner (one crew ask, with the research verdict)

289 MWC products reach "wc" only by code (PR #1755 "Owner data list"). Once CODE-SUBSTRING is on main they stop
showing for "wc" until data is filled: (a) give them class Water Closet, or (b) map product_type -> class.
