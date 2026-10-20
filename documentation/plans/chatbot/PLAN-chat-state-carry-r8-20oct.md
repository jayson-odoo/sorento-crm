# PLAN: CHAT-STATE round 8 - one carry rule for every held axis (CARRY)

**Status:** Build complete, reviewer READY, L1 gate clean, pushing to #1772 (crew brief 20 Oct, owner exploratory run on #1802 build 4cd6d4d930; scope approved crew a6279481 (a)). Track: inside the L lane, LEAD
pattern (tester red -> coder -> lead kill-proof -> reviewer -> L1 gate -> ONE push to #1772). No migration, no auth.
**UAC:** `chat-state-carry-r8-acceptance-criteria.md` (alongside). **Evidence (local only, never committed):**
crew/state/eval/cp0/explore1020/owner-run-1020.md sections 1-4 (class (a); the T8 half of (b); the INDEX half of (c)).

## Goal
A held axis never outlives the subject it belonged to. A message that names its own subject (a product or a brand)
starts a new subject whatever op the parser picked (`switch_domain` and `new_subject` give the same State); a bare
follow-up ("got eta?", "What price?") keeps the held subject, because that is what `switch_domain` means.

## Today (head 13d5555967)
- `new_subject` rebuilds Focus keeping customers, tier, brands, tasks, last_list, period (turn/chat_state.py:1336-1344);
  `switch_domain` drops only `_DOMAIN_BOUND` (:63-65: status, document, sort, channel, top_selling, ranking, low_stock,
  set_page), so products, warehouse, extra and tier survive every switch (:1346-1362).
- Owner run INDEX: "frg" misfiled as a warehouse at T4/T5 (parser, Fix 4, not here) rides on focus.warehouse through
  every later switch; turn_runtime.py:3600 re-emits it each turn; from T9 ~20 CB*-FRG-DIY rows ride along
  (refinement_keeps_subject, turn/apply.py:1182). held_family (engine.py:5030; head/held_family.py:147 fires on a brand
  alone) lands the held basins on the brand-only flyer ask at T8 and stamps them current_message (held_family.py:174,182).
- The INDEX / BLOCK fork at T9 is only `switch_domain` (INDEX) vs `new_subject` (BLOCK).
- Op data ($0, my recorded TRAIN runs, 1220 rows / 244 items; scratchpad r8-ops-mining.json): bare `switch_domain`
  (no keep, no set) 28 rows, 25 pass ("got eta?", "got promotion price?", "What price?", "Have stock?");
  `set:specification` + switch 16 rows, 13 pass ("I mean this got chrome colour?", "p trap ada?"); `set:product` +
  switch 52 rows, 44 pass. A literal "drop whatever was not restated on any switch" would strip the held product from
  the bare and spec rows, so the rule keys on whether the message names its own subject.

## ARCHITECTURE
1. Layer: State (turn/chat_state.py apply_changes), the single writer; plus the held_family call gate (engine.py:5030).
   No text rewriter, no domain override: the parser's ops and typed entities decide.
2. Shared mechanism: one predicate `names_own_subject(ops, verdict)` = this turn typed or `set` a product or a brand.
   When it holds on a switch (explicit op or implicit domain change) or on `new_subject`, ONE rebuild runs: products,
   warehouse, extra and tier are kept only if restated this turn (a `set` / `keep` on that axis, a pick, a typed entity
   of that kind); customers, brands, period, tasks and last_list keep their current rules. A bare switch (nothing named)
   keeps the held subject whole; a spec / class / category over held products stays the round 6 membership refine.
   held_family runs only when the product axis is carried (keep / refine), never on a new subject.
3. Also fixes: the T8 kind pick on a held token (no held row reaches reconcile), carried product_ids and tier in the
   promotion fetch (INDEX T9 / T16), the "Location: frg" header leak, and any stale filter after a new subject.
4. Removes on the state path: `_DOMAIN_BOUND`'s role for subject axes (the rebuild decides), `new_ask_drops_tier` /
   `new_ask_drops_<extra>` (turn/apply.py:1144-1180, stand down under the state gate; state-off keeps them), the
   brand-only branch of FILTER-OVER-HELD (held_family.py:147) under the gate, and the switch_domain / new_subject fork.
   State OFF stays byte-identical.

## Slices (tester red -> coder -> lead kill-proof -> reviewer; L1 gate at round end; ONE push)
- R8-1 the rebuild + `names_own_subject`: owner turn shapes T8, T9, T10, T15 (masked codes / ids) as replay-style unit
  tests, each run with `switch_domain` AND with `new_subject`: same State. Guards: bare switch keeps the held product;
  spec over held keeps members (round 6); `set product` with no switch keeps the other axes (card R1).
- R8-2 held_family runs only when the product axis is carried (lead dropped a brand-only stand-down: the rebuild already
  clears held products on a brand-named switch, and a brand refine over carried products keeps narrowing); tier no
  longer rides a new subject (prompt line to CHAT-CODE-LOOKUP, sequenced: the new_subject row of
  head/chat_state_prompt.py:31 drops "the access tier"; until it lands the tier is re-asked after a new subject).

## Measurement
L1 replay gate (base 13d5555967) for first asks / state-off; $0 recorded-ops replay of my TRAIN follow-up rows through
old vs new apply_changes, listing every item whose held axes change, checked against its grade (no regression on the
follow-up bars). No paid E2E without crew's cap.

## Round log
- Build (20 Oct): reds 171f0f906b + 0f8e2661df (apply-level owner shapes T8 / T9 / T10 / T15, stale "frg", chains, engine
  T8 / T9 promotions-fetch product_ids, behavioural state-off pins) -> lead-signed test changes bcd1f019fa (T9 engine
  assert = no promotion call carries a held id whether or not one runs: a brand + flyer ask with nothing held has no
  lookup path, evidence class (c) / Fix 3, another lane; test_chat_state_apply.py:95 tier pin follows R8; brand refine
  guard behavioural) -> fix 8cdeb28542 (names_own_subject + one rebuild); kill-proof 22 fail / restored 173/173.
- $0 follow-up delta: parser-level gold delta 0 by construction (no parser input / prompt change); state-level replay of
  1690 recorded TRAIN turns old vs new: 29 items change, all a previous held product no longer riding next to a newly
  typed product on an implicit domain change; 0 bare-switch, 0 spec-refine and (after review) 0 pick turns change
  held axes.
- Review round 1 NOT READY: B1 implicit switch unguarded (kill K3 green), B2 a pick over an open roster on an implicit
  domain change wiped the pending. Tests 0584616cc1 -> fix fcd9fa3975 (an answer to the open question never rebuilds on
  any switch; the rebuild sets the message's domains); kill-proof 4 fail / restored 182/182. Re-check READY (K3 K6 K7
  caught). L1 gate vs 13d5555967: grounding 0/1506, turn 0/585 (both fixes).
