# PLAN: CHAT-STATE round 2 - the weak follow-up kinds

**Status:** Build, round 4 (refine on REAL conversations): R4-A + #1755 C2/C2b merge + held-family exact read
reviewer READY, L1 gate 0 unintended; paired real x1 next. Track: L, LEAD pattern. Branch `crew/chat-state-r2`.
**Base design:** `PLAN-chat-state-16oct.md`, `chat-state-behaviour-card.md` (R1-R16), `chat-state-seam-design.md`.

## Goal (crew, 17 Oct, owner "run as much parallel as possible")

CP0 held-out per kind (crew-only numbers): narrowing 17% (n10), reply to the bot's question 62.5% (n8), and-X 82,
switch 85, pick 91, hand-over 93; bar 90 overall. Lift the weak kinds, narrowing and reply-to-question first.

## Rules of the round

- TRAIN only: `crew/state/eval/cp0/train_followups` (84 items, round-31 export) + new follow-up items EVAL-SETS adds.
  Never held-out. Grade from a checkout pinned at the EVAL-BENCH sha (now #1758 edfa2c11c), never a live worktree.
- Root-cause every failing TRAIN follow-up by kind: parse / state / answer / grader.
- Card delta only if a rule changes what the owner sees.
- Red-first fixes in the state path; understanding stays in the parser (no keyword lists, no regex); kill-proof;
  reviewer; L1 replay $0 every slice; live TRAIN paired vs main, cap $3 per run.
- Every fix must hold on >= 8 varied real phrasings (TRAIN items + fresh paraphrase tests).
- Live stacks: at most 2 on the Mac; take `crew/state/live-slots/<LANE>` only if fewer than 2 entries; rmdir on stop.
- Overlap: spec/family matching over held products is step 2 (CHAT-CLOSED-LISTS #1755); this round fixes the
  state/parse parts and coordinates the rest there.

## Steps

1. $0: re-grade the r2 main and r3 lane runs on the 84-item set with grader edfa2c11c; per-kind failures; root cause.
2. Classes (>= 2 members) -> red tests (>= 8 phrasings per class) -> fix -> kill-proof -> L1 replay.
3. Reviewer (+ security if scope/auth touched).
4. Live TRAIN paired vs main (cap $3 per run), report per kind.

## Findings (17 Oct, $0 re-grade of r2 main / r3 lane on the 84 items, grader #1758 edfa2c11c)

Lane 71.3/84 (84.9%) vs main 69 (82.1%). Per kind lane/main: pick 20.67/20, answer 10/10 (every TRAIN answer item
passes both arms: no TRAIN signal for the held-out 62.5%), refine 1/1 of 5, switch 23/23, and_x 15.67/14.
- SPEC-OVER-HELD (4, step 2) + HELD-FAMILY (3, step 2): fixed in #1755, which only runs under its CLOSED LISTS prompt
  section; v157 lacks it -> r2-C publishes one unlabelled version with BOTH sections (combined schema exists, r2-INT).
- NAMED-HELD-VALUE (3, parse, this lane): STATE_SECTION "Never restate an item of the State" stops the parser emitting a
  spec the user repeats -> r2-B rewrite: an entity is what this message names, even when the State holds it.
- HELD-QTY (5, state, this lane): the held quantity lives only on the answered stock task, so keep/refine/swap re-ask
  "How many units?" -> r2-A carry the task quantity onto the refined items.
- BARE-CODE-DOMAIN (crew, CHAT-CODE-LOOKUP TRAIN cp0-df53e90ebf in cp0/train_code): a bare code after an ETA reply flips
  stock / ETA / product info -> r2-D the State shows the last answer's domain; prompt business rule: a message naming
  only another item asks the same fact as the last answer (owner rule; ETA ruling 16 Oct). Parser input only: no
  post-parser domain override (crew NO-GO).
- Grader/gold for EVAL-BENCH: targets.py:434/769/791 compare `note == "payload omitted"` while trace.py:99 writes
  "payload omitted: N bytes"; `applied` cannot credit a held spec applied as product ids; gold of 253d58ba8b and
  fcd44fe521 vs the family rule; round-32 gold on aad2aaec55 vs round 11 "pick drops the typed entity".
- Every class is below the >= 8 phrasings bar: fresh paraphrase tests per class + EVAL-SETS Deliverable A (crew relays path).
- Test DB: sorento_chatstate_throwaway2 (fresh, current schema).
- Live runs (crew 17 Oct, ports moved 18 Oct: a hand-test copy owns 8109): own stack CRM 8193 / MCP 8293 with an env
  file in this worktree (never cp0/stack.env); slot crew/state/live-slots/CHAT-STATE (max 2 entries machine-wide),
  rmdir on stop. Main arm = origin/main + production v63: without the state heading `parser_config.state_block` is
  off (engine.py:4540), so main runs the pre-state baseline.

## Proof log (posted on the r2 PR when it opens)

- r2-INT: red 459967eff9 (combined schema) + the read-once test red after the merge 697df41293; fix 7833e7365e.
- r2 round 1: red 18bb534d6c (22 red: r2-A held qty 9, r2-D last-answer domain 8, r2-B/D prompt text 2, r2-C combined publish 3);
  fix 18c6556187; kill-proof: reverted 22 failed / restored 196 passed (chat_state apply/block/parser_input/seam).
- L1 replay gate r2 (faa9d0f11e) vs integration base 697df41293, --split dev: grounding 0/1506, turn 0/585 unintended.
- Reviewer r2 (faa9d0f11e): NOT READY on r2-A (B-A1 clear quantity undone; S-A2 qty onto another product; S-A3 qty onto a
  new subject; nit label wording); merge / #1755 alone / combined schema / publish READY.
- r2 round 2: red 721f462bd1 (33 red); fix ff3ec689d9; kill-proof: reverted 33 failed / restored 191 passed.
- Reviewer re-check (ff3ec689d9): READY.
- L1 replay gate r2-2 (a17f1cf2b1) vs 697df41293, --split dev: grounding 0/1506, turn 0/585 unintended, exit 0.
- Merge origin/main 63f4fe47c (#1747 squash e9ef7b416 + #1762): add/add conflicts resolved 3-way against the r1 commit
  the branch already held (f3b0c5dc2); the merge adds only #1762's eval tooling and the import-boundary allowlist
  lines, no chatbot runtime change, so the r2-2 gate stands.
- Live TRAIN r2 (18 Oct, $1.485, 84 calls/run): lane d6be413990 + v168 (id 20d8165c) 72/84 x3 vs main x3 69/84
  (round-1 main runs, same pin): paired +3 [-1, +8], not significant. and_x 16/14, pick 21/20, switch 24/23,
  answer 10/10, escalation 1/1, refine 0/1 of 5. Worse: cp0-75e516bd40 (refine). Refine root cause next ($0).

## Round 3 (18 Oct): refine root cause on the r2 live rows ($0; scratchpad evalrun2/rootcause-r2r2.md)

No refine failure is a parse failure; r2-B now emits the named spec (fcd44fe521, 253d58ba8b).
- **R3-A HELD-QTY-NOT-FETCHED (this lane; cp0 b5eb30e1b9 + f14dc9c818, train2 ~4 UNVERIFIED):** r2-A carries the held
  quantity onto `focus.products` rows only (chat_state.py:821-825), but the fetch reads only the open task's
  `requested_quantities` or this turn's entity quantities (turn_runtime.py `_spec_quantities`), so a refine / keep still
  asks "How many units?". r2-A's tests stop at `apply_changes`, which is why they went green while the carry was dead.
  Fix: the quantities apply carried become the fetch's last source, by own code, with r2 round 2's limits (clear wins,
  own code only, never onto a new subject). Tests go through the fetch seam, >= 8 phrasings (TRAIN + fresh paraphrases).
- **QTY-ONTO-REFINED-SET (253d58ba8b, 665ba3e897): ruled (a), crew 18 Oct** (owner line "don't re-ask what the user
  gave"): the one held quantity rides onto every code a refine of the SAME held subject lands on; never onto a new
  subject or another named product (S-A2 keeps holding for those). Part of R3-A.
- **SPEC-OVER-HELD-NO-MEMBER (#1755, fcd44fe521; train2 up to 19 incl. 10 size refines):** no family member has the
  value -> `narrow_held_family` returns the verdict unchanged (held_family.py:86-88) and the turn widens to the catalogue;
  a numeric size never narrows (string `spec_value` only, held_family.py:71). Crew 18 Oct: (a) in principle, "held,
  none match" says so plainly (owner CP0: say plainly what is not on record); routed to CHAT-CLOSED-LISTS after
  EVAL-BENCH's gold card on fcd44fe521. Grader items queued for EVAL-BENCH round 35.
- **Grader (EVAL-BENCH):** cp0-75e516bd40 flipped only because r2-C turns CLOSED LISTS on and #1755 card R2
  (grounding.py:795-806) puts "Water Closet" for the typed "toilet"; same lookup (47 ids) and reply as main, the grader
  reads words only (targets.py:807-847). G-HELD-BEFORE targets.py:823-828. train2: 7 refines while the bot's own
  "How many units for each?" is owed, which `spec_refine` (targets.py:521) fails.

### train2 baseline (crew (a), 18 Oct, x1 each, eval-sets grade_sets.py with main's targets.py)
Real 49 lane / 50 main of 58; synthetic 29 / 21 of 53 (refine 10 / 0 of 28, answer 19 / 21 with 3 lane `unknown`).
Main baseline for reuse: scratchpad evalrun3/s_main1.jsonl (crew-note on #1772). Root cause: evalrun3/rootcause-train2.md.
- **R3-B STATE-VIEW-ROSTER-OFFER (this lane, 9 TRAIN items: cp0-12e64c3f37, cp0-b2f537d9b6, cp0-2d60b19a93,
  es-33ba35d807, es-bf24a3e2e3, es-s2bd9aaeea, es-safcbef216, es-s6fd301ccd):** after a roster pick the lookup misses and
  the reply offers a hand-over; the engine keeps the roster as the stored question with the team and `escalate_offered`
  (answer_bridge.py:2091-2139, engine.py:8677-8681) and accepts a later "yes", but the State view adds `offer` /
  `hand_over_to` only for the hand-over kinds (chat_state.py:197-205), so the next parser sees `pick_one, owed [pick]`.
  Card R5 / UAC C3 (the question closes) + C8 (the last list stays pickable). Fix in the view only; the store stays.
- Held, not fixed (class bar >= 2, singletons across 11 runs): HELD-FILTERS-NOT-FETCHED (es-s2bd9aaeea: `promo_filter`
  builds from this turn's entities only, turn_runtime.py:582-646); CANCEL-CLEARS-NAMED (es-3e53ca255a:
  `task_close_clears_products` empties a product the message names, apply.py:3530-3538).
- To #1755: SIZE-AS-CODE (3 refines; candidates.py:263-283 substring match, no numeric spec line), near-code
  es-e1f8fae46c. To EVAL-BENCH: 3 OWED-QTY refines (targets.py:536-543); answered roster read as a fresh question
  (targets.py:1166, :784, `_oq_sig` 272-276).

### Round 3 proof
- R3-A: red 3007a7bf2c (16 failed / 6 guards pass); fix dbc0557644 (22 passed; chat_state suites 274); kill-proof:
  the 3 fix files reverted 16 failed / 6 passed, restored 22 passed. L1 replay vs ba6c344e9e: 0/1506 + 0/585.
  PR gate red on ba6c344e (run 39052575920) was exactly these 16 red tests; ci re-run 39053431961 on dbc0557644.
- R3-B: red 85b1cba598 (37 failed / 10 guards pass).
- R3-A review (reviewer NOT READY on dbc0557644: B1 the `[]` branch carried `shared` onto family codes; S1 a vacuous
  test; S2 card R8; N1, N3): red bcc4319fc3 (B1 3 failed), fix c271f536af, card d20a506e39; kill-proof B1 reverted
  3 failed, restored 74 passed (r3a + r3b). Reviewer re-check: READY.
- R3-B fix 8c38347f1d; kill-proof reverted 37 failed. Reviewer: NOT READY: `escalate_offered` does not mean "the last
  reply offered a hand-over": did-you-mean rosters carry it from the ask (answer_bridge.py:1303,1345; compose.py:499),
  and it survives a later pick that finds stock (pending.py:147-160, apply.py:940), so the view showed an offer the
  reply never made (card R13) and hid a fresh roster's owed pick. **Crew ruling 18 Oct (a):** stamp the turn the
  hand-over offer was made (answer_bridge.py:2133-2139, compose.py:906-916); the State shows the offer only when it was
  made on the last reply and the roster was answered; no change to what "yes" does (crew logs for the owner that a
  "yes" after a later stock hit still hands over on main, turn_runtime.py:1226-1238).
- PR gate red on 8b1d6047 (run 39054912036) = exactly the 37 R3-B red tests; pushed d20a506e39, ci run 39056082640.
- L1 replay gate (d20a506e39 vs 8b1d604705): grounding 0/1506; turn tier first run 2 "grounded" rows in cand-0161,
  not reproducible (10 replays per row match on every field; those 14 Oct parses carry no state_changes, so no r3 code
  runs on them; replay.py:818-828 names a row "grounded" when one arm errored); turn tier re-run 0/585. CI green on
  d20a506e39. R3-B review red 00209278af (7 failed: 4 fresh rosters, 3 stale-flag seam cases; 48 pass).
- R3-B fix 1d30ec6732 (offered_at_turn stamp, answer_bridge.py ~2139 / compose.py ~917; view gate chat_state.py
  ~194-210): 7 red green, kill reverted 7 failed; gate vs d20a506e39 0/1506 + 0/585. Reviewer: code right, NOT READY
  on tests (no positive next-turn test; S1 trace after-view at the offer turn's number; S2 dead fallback).
- Red f907faaae4 (S1 2 failed; positive seam tests both stamp paths; fixtures carry offered_at_turn); fix b59bb0ce02
  (after-view at turn_no + 1; fallback dropped): 386 passed; S1 kill reverted 2 failed. Reviewer re-check: READY
  (drop compose stamp 2 red, drop answer_bridge stamp 4 red, == to <= 3 red, revert S1 2 red); guard a7d38a0aa7 for
  a stamped roster never picked from (the one surviving mutation). Nit kept: the stamp is also stored on main-arm
  rosters (read by nothing; gating it would add code for no behaviour).
- Gate vs d20a506e39: grounding 0/1506; turn tier 1 "grounded" row cand-0102 (a first ask, no state_changes, no r3
  code reachable; 10 replays per arm match); a re-run with the temp output kept: 0/585. The L1 gate's turn tier shows
  intermittent "grounded" rows (3 rows over 2 runs, none reproducible); the patched gate copy now prints each arm's
  row shape on the next one.

### Round 3 live (train2 lane x1 on 3f473f6fb4, $0.614 / 116 calls; CI green on 3f473f6fb4)
Same totals as the r2 lane run: real 49 (main 50), synthetic refine 10/28 (main 0), answer 19 + 3 unknown (main 21 + 1).
R3-A fixed es-s5fbda6317 (and, with a spec the parser emitted this time, es-sdac84c3f5); the 3 refine flips P -> F
(es-s5f0edf7fe, es-s75dca5aa6, es-sa6d8a507a) and the es-s8b3b40f95 gain are parser variance: identical user block,
prompt hash, v168 and model on both lane runs, no r3 code on their path. One run per arm swings +-3 on refine.
- **R3-C CANCEL-CLEARS-NAMED (this lane, 2: es-3e53ca255a real and_x, es-sa6d8a507a synthetic refine):** while a
  question is owed the parser sends only `close_question` but the message names its own product / spec; a lone close
  is a cancel (chat_state.py:782-786), the cancel clears every product incl. the named one (apply.py:3530-3538), the
  empty subject is refused (apply.py:2470) and the reply is generic. Expected: a close that comes with an entity this
  message names is not a cancel; a lone close that names nothing still cancels.
  - R3-C proof: red 39a7014d17 (10 failed / 4 guards), fix 39ca8b84eb, kill reverted 10 failed; gate 0/1506 + 0/585.
    Reviewer NOT READY: B1 a close naming a new product left the old stock_qty task open (the next "5" fetched the
    old products; same on close + set product), S1 a null `current_message` should count as named, S2 guard. Red
    d5ff9cde61 (8 failed); fix 6ed46da68d (an open task whose products this message does not name closes when the
    message names a product; S1 `is not False`); kill reverted 8 failed; gate vs 951f38dc33 0/1506 + 0/585.
    Re-review: code holds; tests missed S1 (masked by B1), B1's `any` and the product filter; should-fix: a list pick
    beside a typed code dropped the picked product's task (named set built before the picked rows).
  - Follow-up (not this slice): a typed form only the resolver maps onto a held code ("srt391gm", "SRT39") does not
    match the task's slot label, so the task closes although the subject is the held product; the stated quantity
    still reaches the fetch. Only bites on a turn whose reply carries no availability block (task.py:1155-1218
    rebuilds the task otherwise). Fix later by comparing slot.key with the resolved product uuid.
  - PR gate red on 951f38dc (run 39105858911) = exactly the 10 R3-C red tests (456 others pass).
  - Re-review round: red c3bf40dc5a (3 failed: a list pick beside a typed code dropped the picked product's task;
    12 guards: S1 on a null-flag spec, one of two owed lines answered keeps the task, named-spec keeps the task);
    fix f2c490b99d (named set + old-task close moved below the picks); kill reverted 3 failed / restored 36 passed.
    Reviewer re-check READY (S1 revert 3 red, `any` -> `all` 1 red, product filter 5 red, block back above picks
    3 red; dropping OPEN / canonical_code-only survive, judged harmless). Gate vs 951f38dc33: grounding 0/1506;
    turn tier first run 2 base-side rows (cand-0243 base errored, cand-0277 base made no tool call; neither row
    carries state_changes, so no r3 code reaches them), re-run 0/585.

### Round 3 final set (crew 18 Oct (a), owner: emphasis on chat lanes)
- origin/main 0f5c6537e merged (main only; #1755 kept at f0f94bc38, its newer head is still moving): 55ea3c0f10,
  conflict-free; main touched no chatbot runtime or prompt file, so lane prompt v168 stays; 314 touched tests pass.
- Envelope: ~$4.2 for x3 lane vs x3 main on train2_followups, interleaved; runner + grade_sets.py from a 0f5c6537e
  checkout (#1775 scope listeners); real and synthetic apart; paired CI. Parser-call cap for 18 Oct raised by crew
  from 700 to 1400 (~600 used before this set). The earlier caps lived only in crew messages; this one is enforced
  as a hard per-run `--max-calls` in the final-set runner (scratchpad evalrun4/run_sets.py) and a cumulative stop
  in evalrun4/final.sh (per-run cap 150 at evalrun4/run_sets.py:9, sets.sh:11).
- L1 gate 55ea3c0f10 vs PURE main 0f5c6537e (first base without #1755): grounding 0/1506; turn 3 rows with the same
  tools / decision / grounding / reply and one extra blocked provider.OpenAIProvider call on head; by the earlier
  gates (r2 vs main+#1755+r1 = 0, each r3 slice = 0) that call is #1755's, not this lane's. CI green on 55ea3c0f10.
- **Result (x3 vs x3 interleaved, scoped harness; $4.042, 693 calls):** all 111 items lane 82.33 vs main 72.00,
  +10.33 [+2.67, +18.33]; real 58: 50.00 vs 50.33, -0.33 [-3.33, +2.67]; synthetic 53: 32.33 vs 21.67,
  +10.67 [+4.00, +17.33]; synthetic refine 28: 13.00 vs 0.33, +12.67 [+7.67, +17.67]; synthetic answer 25: 19.33 vs
  21.33, -2.00 [-5.00, 0.00], all of it 2 items the grader scores unknown on the lane (answered roster read as a
  fresh question, EVAL-BENCH r35). Real switch -1 = es-e1f8fae46c (#1755 near-code candidate, routed).
  Crew-note on #1772 (comment 6249197686); rows scratchpad evalrun4.

## Round 4 (crew 19 Oct, owner agreed): refine the last answer, on REAL conversations

Context: crew's combined held-out run, follow-ups 84.0 vs bar 90, refine the hole (~30%); the x3 TRAIN set showed
synthetic refine +12.7 but real flat. Steps: $0 root cause on real refine failures (main + this branch), behaviour
notes only if a rule is the owner's, red-first fixes, reviewer, paired TRAIN real x1 with the owner's early-stop rule
(checkpoints, stop on regression). Budget: per-PR gate, cap $3 for the round. Synthetic = regression check only.
- Data gap (19 Oct): train2's real split has no refine items (pick 16 / switch 24 / and_x 18; eval-sets README:41-42,
  "0 refine turns were free"). The only real refine on TRAIN: cp0/train_followups, 5 items (cp0-b5eb30e1b9,
  cp0-fcd44fe521, cp0-253d58ba8b, cp0-665ba3e897, cp0-75e516bd40). Asked crew: (a) EVAL-SETS mines more real refine
  turns, (b) measure on the 5 now + fresh real-shaped paraphrase tests, (c) EVAL-BENCH relabel. Crew 19 Oct:
  (a)+(b): (b) now (~$0.10); EVAL-BENCH mines >= 8 new REAL refine follow-ups for TRAIN (never held-out) as a set
  file, then the paired x1 with checkpoints runs on it.
- (b) result (5 real cp0 refine, x1, scoped harness, $0.114): lane d3ea0dd9ce 2/5 vs main 0f5c6537e 1/5; lane gains
  cp0-b5eb30e1b9 (R3-A carried quantity); both fail cp0-665ba3e897, cp0-253d58ba8b, cp0-fcd44fe521.
- Root cause (scratchpad evalrun5/rootcause-r4.md; counts checked by SQL): no parse failure; R3-A carried the quantity
  (`_carried_quantity` shared 10 / 5). The held-family narrowing never fires on real data: held_family.py reads a
  family only from `products.variant_of_id` (2 of 15,439 products), while real families sit in `family_code` (13,983;
  SRTWC286-SH's siblings include -P and -NEW-P). So `carry_onto_family` never runs, the fetch has no
  requested_quantities, and the reply asks "How many units for each?" over the catalogue's P-traps. R3-A's and
  #1755's family tests seed `variant_of_id` links the data does not have, which is why they were green.
  C1 none-match (253d58ba8b, fcd44fe521) exists on #1755 head 0665fa0db6; C2 family by `family_code` (665ba3e897) is
  not built; C1 without C2 gives 665 a false "none on record". Crew 19 Oct (a): CHAT-CLOSED-LISTS-L builds C2
  (family_code) in held_family.py on #1755 (one owner per file). This lane: engine-seam red tests on the 3 real
  items in the family_code shape, kept local until #1755 lands; then merge #1755's head into #1772, rewrite the R3-A
  family fixtures to the real shape, paired real x1 with checkpoints (+ EVAL-BENCH's new real refine set).
  Lesson: seed the shape real data has (here family_code), never a link the data lacks.
- Red 6156c918af (local): 9 seam cases on the real family_code shape (3 real cp0 items x 3 phrasings) + the R3-A
  family group re-seeded to family_code (5 fail, assertions unchanged); waits for #1755's C2.
  Reordered onto the R4-A push as 07a492daa3 (14 red). Crew 19 Oct (a88607088): one head, one ci label.
- Merge 0563d38525 = #1755 head ad78e1e738 (C2 family_code + C2b held-first, CI green). Conflicts: engine.py and
  turn/context.py field / keyword order (took #1755's; every call passes keywords); parser.py took #1755's
  `closed_lists_schema(items, *, state=)` and dropped the lane's `_closed_lists_state_schema` (same JSON for 3 items
  and for none, reviewer-checked; only its lru_cache is lost), so parser.py equals ad78e1e738. After the merge 11 of
  14 reds green; cp0-665ba3e897 x3 still fetched 3 products: the narrowing matched the right 2 (SRTWC286-SH-P,
  SRTWC286-SH-NEW-P), then the entity resolver's prefix probe (`entity_resolver._prefix_probe_product`) also placed
  SRTWC286-SH-PP (an s_trap sibling) because `_exact_codes_only` (engine.py ~5705) runs only on `family: false`.
- Fix 558b3fc56d (engine.py ~4939): a non-empty held-family match sets `family: false`, so the turn reads the
  narrowed members exactly. Scope: closed_lists + held products + a match, on BOTH the state path and the
  closed_lists-on state-off path (#1755's seam; main's production prompt has no CLOSED LISTS section, so main is
  unchanged). Doctrine: the narrowing fires only when the message names no product (held_family.py:146-149), so
  the parser's null `family` said nothing about these rows; an execution detail, not a meaning rewrite (reviewer).
  Kill: fix reverted 3 failed, restored 9 passed. L1 gate vs ad78e1e738: grounding 0/1506, turn 0/585 (585 of
  585 replayed). Reviewer READY; should-fix done: state-off guard 9666d3884c (3 phrasings, no `state_changes`;
  fetch exactly SH-P + SH-NEW-P; fix reverted -> fails on the extra -PP; the state-off path carries no quantity,
  so none is asserted). #1755's own fixtures have no -PP-style sibling; crew-note on #1755 6260819707.
  Pushed d45781dbfb (+ origin/main ada7cfc990, eval scripts only); 687 touched tests pass; one ci label (crew).
- Paired real x1 with checkpoints (lane d45781dbfb + v168 vs main 0f5c6537e0 = main's app code; crew-note
  6260953750): train2_refine lane 2/8 vs main 0/8 (gains es-e9d2507a71 R4-A, es-f173186e97 C2b); cp0 real refine
  lane 5/5 vs main 2/5 (gains 665ba3e897, 253d58ba8b, fcd44fe521); real refine 7/13 vs 2/13, no item regressed,
  0.18 USD (round ~0.55 of 3). Left on TRAIN, all owned elsewhere: EVAL-BENCH (242 gold, 9ed / 5eb offer-pick
  labels), #1755 number key (0db8), owner registry synonyms (02332, d2692).
- EVAL-BENCH real refine set `eval-sets/train2_refine` (8 real TRAIN items, round 36 grader; recorded prod 1/8).
  Baseline x1 (scoped): lane 4cdd3f37fd 0/8, main 0f5c6537e 0/8 ($0.162). `filter` fails 8/8 on both arms
  (rootcause-r4.md section 2):
  - **R4-A BRAND-OFFER-KEY (this lane; es-e9d2507a71, es-242b332bca):** the brand offer is stored as
    `set_page = {"set_key": {..., "other_brands": [...]}}` (turn_runtime.py ~4460) but chat_state.py:232/552/841 read
    `set_page["other_brands"]`, so the parser never sees the offer; engine.py ~4822 also skips the offer pick on
    state-led turns; "Sorento" widened to the catalogue's SORENTO products (on 242 the lane is worse than main).
  - #1755: C2 must filter the held products first and reach family_code siblings only when none matches (reading
    the whole family breaks e9 / 242 / f173); number key `trap_length` vs the parser's `dim_width` (0db8cf0a48).
    Crew-note posted on #1755.
  - Parse / owner data: a code segment said as a filter (02332dd6a1, d2692e6c09; "bl" / "gm" registry synonyms).
  - EVAL-BENCH: 9ed83ea52c and 5ebea068a5 are an offer pick ("Mocha" answers the hand-over offer) labelled refine;
    242 gold vs a product created after the turn; a false none-on-record passes `subject` (targets.py:881).
  Projected ladder: C1 3/8, + held-first C2 + key 4, + synonyms 5, + relabel 7 (UNVERIFIED).
- R4-A proof so far (all local): red f9d3e409d2 (12 failed / 5 guards), fix 413cff7e5b (nested offer read; held set
  narrowed to the parser's offered brand), kill reverted 12 failed. Gate vs 55ea3c0f10: grounding 0/1506; 1 turn row
  (cand-0132) = a caught failed turn (GENERIC_ERROR_REPLY, engine.py:131) during Postgres "out of shared memory"
  from other processes' schema drops; 30 reruns match; R4-A unreachable on it. The gate reports a caught failed
  turn as a diff (for EVAL-BENCH). Reviewer NOT READY: an offered brand not held kept nothing (owner's PR #833 r7
  item 6 shape); regex route still deciding on answer turns; two brands kept the first; unguarded brand query.
  Lead decision (card R1 vs R5): a held brand = refine -> narrow the held set; an offered brand not held = answer to
  the offer -> main's `set_brand_chosen` re-runs the set; on the state path the parser's brand decides.
  Red 9c66b9160a (15 failed), fix 1594d7c32b, kill reverted 15 failed; gate 0/1506 + 0/585. Re-check NOT READY:
  the task.py hunk changed main's state-OFF path (an open stock task no longer resumed on a brand pick; the replay
  corpus has no such turn, so the gate missed it) -> gate it to the state path + a state-off pin test; the "no
  capped-set rule" deviation rested on a fixture holding 7 of 37 (real e9 37/37, 242 182/182) -> a capped set re-runs
  the set; a held + an offered-not-held brand dropped one silently -> lead decision: re-run the set once with every
  named brand (state path only). Lesson again: fixtures must carry the shape real data has.
  Red 5bca9ebb9a (12 failed: state-off pin x2, capped set x4, mixed brands x6; fixtures now hold the real counts),
  fix 0ca2aca38d (state path writes `set_brand` as a list, main a string; task.py skips the resume only for a list;
  capped set / any offered-not-held brand re-run the set once with every named brand; product_predicate
  `_brand_clause` IN, one name = the old `==`); kill reverted 12 failed; gate 0/1506 + 0/585; reviewer READY with
  should-fixes: red 2e365f41c2 (the set's own brand dropped beside an offered one; direct two-brand predicate
  tests), fix 4d36d9f9c3 (own brand pickable on the list path), kill reverted 3 failed / restored 59 passed; gate
  0/1506 + 0/585; reviewer re-check 4 READY (mutations R5 / R6 now killed; held-brand narrowing unchanged; main's
  string path unchanged, both state-off pins pass).

### R4 (crew via CHAT-CODE-LOOKUP, 18 Oct): no slice
On main + v63 the parser never sees `Current subject:` (vocabulary line over the 350 L2 cap, context.py:29; only the
subject shrinks, context.py:437-443; train2 s_main1 108/108, cp0 r2main 86/86). With the state section on, `_render_l2`
returns the vocabulary line + the State block uncut (context.py:394-396; engine.py:4568-4570): all 617 held-focus lane
rows carry the State subject line, which holds every L2 subject field and more. Crew 18 Oct (a): no R4 slice here; the
subject reaches main when the state section's prompt version is labelled after the owner's hand test; crew raises the
main-side L2 budget fix with the owner as its own lane.
