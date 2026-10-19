# UAC: CHAT-STATE round 6 - one typed Subject (plan: PLAN-chat-state-subject-r6-20oct.md)

Every criterion holds on the state path (prompt carries the State section). Off the state path every reply, fetch and
trace is byte-identical to today unless a line says otherwise.

## S1 Subject written by the applier
- AC-S1-1 A state-led turn's applied State carries a `Subject` with: `source` in {ids, predicate, unresolved};
  explicit product ids (source ids) or a predicate over brand / class / spec / family (source predicate); company
  scope + hidden keys; provenance per axis in {held, said, offer}.
- AC-S1-2 Only turn/chat_state.apply_changes builds or replaces the Subject (no other module writes it).
- AC-S1-3 Provenance: an axis the parser's op set this turn is `said`; a held axis no op touched is `held`; an axis
  taken from the bot's offer (offer pick) is `offer`; a cleared axis is absent.
- AC-S1-4 A class is one axis (category and product_type together), as the round 5 G4 fix holds in the State.
- AC-S1-5 Empty subject (no ids, no predicate axis) or a said product token nothing resolved -> `unresolved`.
- AC-S1-6 The turn trace logs the Subject beside today's fetch input; no reply, fetch or ask changes (L1 gate 0).

## S2 The fetch reads the Subject
- AC-S2-1 On a state-led turn the resolver / tool input is built from the Subject by one function.
- AC-S2-2 Setting one axis keeps every other held axis; `new_subject` or an explicit `clear` drops it (the 10
  xfail(strict) F1 tests pass with their marks removed; the 11 plain tests stay green).
- AC-S2-3 R3-A held quantity, R4-A offer picks (held brand narrows, offered-not-held brand re-runs the set) and
  #1755 held-family narrowing (held matches first, family_code siblings only when none match) behave as their suites
  pin today.
- AC-S2-4 with_carried_entities' "names nothing" rule, carry_onto_family and narrow_held_to_brands are not called on
  a state-led turn.

## S3 Decisions read the ops
- AC-S3-1 held-family narrowing, scheme-index and "names its own class" decide from the State ops, not entity-hint
  heuristics; names_own_class is deleted at task.py:735, scheme_index.py:35, held_family.py:152, engine.py:4986.
- AC-S3-2 A type-only follow-up keeps the held product (TYPE-ONLY-EMPTY-SET; #1755 R6-4 semantics).
- AC-S3-3 A message naming its own class is about that class, at every seam (#1755 R6-3 semantics), via the op.

## S4 Unresolved asks
- AC-S4-1 An unresolved Subject never reaches a fetch; the turn asks (fetch.py:665-675, gate.py:172 on the state path).

## S5 Legacy rewriters stand down
- AC-S5-1 Under the state gate none of: with_set_count_from_text, with_brand_from_offer, with_company_pick,
  with_new_set_words, the stock-ask regex, decide.py's refine-of-standing-subject branch, reconcile.py:110-121 runs;
  each is ported to an op semantic or deleted, and each has a test pin.

## S6 UserTurn at ingress
- AC-S6-1 One UserTurn (own_text, quoted_text, media reads) is built at ingress for the webhook path and #1766's
  direct-ingress path; the seven first-line reads (`split("\n", 1)[0]`) read it instead.
- AC-S6-2 Off the state path every value the old first-line reads produced is identical.
