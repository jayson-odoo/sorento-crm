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

- AC-S1-7 (review round 1) Predicate values are typed rows (the value plus its registry key / uuid), never bare
  strings, so the fetch never re-reads the focus. Provenance is per axis value: a value typed in THIS message is
  `said` under any op (set, new_subject, keep, answer), as the R16 period rule already does (chat_state.py ~941).
- AC-S1-8 (review round 1) `unresolved` is decided AFTER the resolver ran, by one settle step that lives in
  turn/chat_state.py (the single writer): a said product token the resolver placed makes `source` ids; only a token it
  could not place makes the Subject unresolved. Any later change to the State (offer narrowing, held-family) rebuilds
  the Subject through the same module, so the Subject never goes stale.

- AC-S1-9 (review round 2, lead decision per card R1 / R4 / R5) The op decides the other held axes: `set` (refine)
  keeps every held axis it does not set; `keep` changes nothing (a restated held value keeps every axis; a value typed
  under keep is not a change); `answer` fills ONLY the asked slot and keeps the others (card R5); `new_subject` drops
  every held axis, the product axis included (card R4); a rejected change set keeps every held axis and lets a value
  typed this message fill only its own axis, exactly the held Subject when nothing was typed (lead decision, review
  round 2: with the ops untrusted, the typed words are the only signal). Under `keep` the applier records exactly the words it saw typed on
  a held axis (a Subject field written only under keep); the fetch drops exactly those and never a word a later step
  added (review round 3: a type-clarify answer with a category held reaches the fetch).
- AC-S1-12 (review round 3) `source` ids means explicit uuids; a token-only Subject is `unresolved` until settle places
  the token.
- AC-S1-10 (review round 2) A held product without a uuid stays in the Subject as a token (key = its code) and the
  fetch hands it over, as the browser-pass-6 promo turn 0bd47e62 needs (never a fetch scoped to no product).
- AC-S1-11 (review round 2) Settle keeps the said tokens it could not place in `unplaced`; a Subject with placed ids
  and a non-empty `unplaced` stays visible to S4, which decides the ask.

## S2 The fetch reads the Subject
- AC-S2-1 On a state-led turn the resolver / tool input is built from the Subject by one function.
- AC-S2-2 Setting one axis keeps every other held axis; `new_subject` or an explicit `clear` drops it (the 10
  xfail(strict) F1 tests pass with their marks removed; the 11 plain tests stay green).
- AC-S2-3 R3-A held quantity, R4-A offer picks (held brand narrows, offered-not-held brand re-runs the set) and
  #1755 held-family narrowing (held matches first, family_code siblings only when none match) behave as their suites
  pin today.
- AC-S2-4 On a state-led turn no legacy carry rule runs under any name: with_carried_entities and
  carried_entities_except (its body) are not called, whatever the op (refine, keep, answer, new_subject) and whether the
  message typed a product code. The fetch reads the Subject (source, product_ids, predicate rows) for every Subject axis; customer, warehouse,
  document type and order rows, which are not Subject axes, still come from the focus per kind.
- AC-S2-5 R4-A answer pick: an `answer` to the bot's brand offer gives the brand provenance `offer`, and the fetch holds
  the offered brand, not the held one beside it.

## S3 Decisions read the ops
- AC-S3-1 held-family narrowing, scheme-index and "names its own class" decide from the State ops, not entity-hint
  heuristics; names_own_class is deleted at task.py:735, scheme_index.py:35, held_family.py:152, engine.py:4986.
- AC-S3-2 A type-only follow-up keeps the held product (TYPE-ONLY-EMPTY-SET; #1755 R6-4 semantics).
- AC-S3-3 A message naming its own class is about that class, at every seam (#1755 R6-3 semantics), via the op.

- AC-S3-4 (moved from S2) carry_onto_family (R3-A held qty onto family members) and narrow_held_to_brands (R4-A) are
  expressed through the Subject (applier module) and not called from the engine on a state-led turn.

## S4 Unresolved asks
- AC-S4-1 An unresolved Subject never reaches a fetch; the turn asks (fetch.py:665-675, gate.py:172 on the state path).
- AC-S4-2 (review round 5 carry) The ask covers Subject.unplaced tokens and a token-only `unresolved` Subject after
  settle; scope and hidden keys are filled through the applier only (single writer), from the contact's company scope.

## S5 Legacy rewriters stand down
- AC-S5-1 Under the state gate none of: with_set_count_from_text, with_brand_from_offer, with_company_pick,
  with_new_set_words, the stock-ask regex, decide.py's refine-of-standing-subject branch, reconcile.py:110-121 runs;
  each is ported to an op semantic or deleted, and each has a test pin. Under the state gate they stand down on reject turns too
  (state_led None), so the fetch never reads a Subject a rewriter changed behind it; one reject turn pins it (lead
  decision, review round 3). Also on state-led ANSWER turns (engine.py ~4937 `if not state_led or answering`:
  with_company_pick, with_clarify_answer, with_set_count_from_text), and _top_selling_verdict / order_list_verdict,
  which can replace state_in (engine.py ~5156, ~5181), stand down under the state gate (review round 5 carry).

## S6 UserTurn at ingress
- AC-S6-1 One UserTurn (own_text, quoted_text, media reads) is built at ingress for the webhook path and #1766's
  direct-ingress path; the seven first-line reads (`split("\n", 1)[0]`) read it instead.
- AC-S6-2 Off the state path every value the old first-line reads produced is identical.
- AC-S6-3 (review round 5 carry) Grounding's `latest_user_message.split("\n", 1)[0]` (engine.py ~4973) reads UserTurn.
