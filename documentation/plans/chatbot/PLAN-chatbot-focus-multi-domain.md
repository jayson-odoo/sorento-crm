# PLAN - Chatbot focus + multi-domain: one dialogue state, then fan-out

Status: APPROVED by owner 12 Sep 2026 on the lavish page ("best quality and the shortest time"); lane 1 `feat/chatbot-focus` S0 to S4 BUILT 13 Sep (backend green on the lane DB, replay 1791, one head 517), S5: reviews CLOSED 13 Sep, pre-PR gate green at 09d5a3af3, DRAFT PR opening 13 Sep; browser verification + owner console pass PENDING (frontend slot); lane 2 `feat/chatbot-multi-domain` stacked after. Two lanes, two PRs. S6 sticky roster (D19) BUILT 13 Sep, review round closed at d72420498 (2 blockers + the owner's B3 promo-menu report + 5 should-fix + 3 nits). S7 multiple-matches picker armed + dash fold at the send boundary BUILT 13 Sep at 3dcb9fb1f. S7c prefix-code pin BUILT 13 Sep at e42eee65b (replay 1791 unmoved, chatbot suite 4224, resolve/intersection files 484, one head 517); owner re-pass on :3081 pending. 15 Sep 2026: merged main twice, then the owner's merge test opened R-A to R-F (the pick seam, the offer, the family), the captain's GENERAL-RULE ROUND replaced the arm-shaped fixes with one rule each (the offer has one writer and one team source, a pick keeps what the same message resolved beside it, no answer-or-refinement decision reads `domain_hint`), and TWO Opus re-review rounds landed B1/B2/S1-S4. The live smoke then added R-I (the offer's answer had no pre-v3 channel), R-J (the answer was spent over a question the same turn asked, and an `order_status` carry keyed on one spelling of `entity_op`), R-K (the roster was never shown to the promoted v1 parser - merge blocker) and R-L (any re-arm of an open question keeps its frozen options and its recorded team, not the roster kinds only), plus the final review's B-1 (an echoed offering clause outranked the bot's own promise). All three closed. The owner's live smoke on 6584eb6e7 then found R-K's FIRST fix unreachable (a riding offer hid the roster from the one prompt line a v1 prompt gets) and opened R-M (a stray position over a head-resolved question minted a menu label into the turn's entities, R-B's mechanism on the other arm), and the light review added S-1 / S-2 (whoever prints the offer sentence records the offer; the text is not a source). All four closed in one commit on top of 494df7346.
UAC: `chatbot-focus-multi-domain-acceptance-criteria.md` (AC-10xx).
Supersedes: Slice B of `PLAN-chatbot-growth-r1.md`. CORRECTION 12 Sep: its lane
`feat/chatbot-growth-dialogue` WAS built, locally, never pushed: 14 commits, 42 files,
+7,253 / -358, in the worktree `.claude/worktrees/chatbot-growth-dialogue`, based on main at
#711 (7 Sep) and 48 main commits behind. Lane 1 starts FROM that branch (see "Lane 1 base").
Growth-r1 section D maps onto this UAC, see its supersession table.
Predecessors: `PLAN-chatbot-turn-engine.md` (LIVE), `PLAN-chatbot-growth-r1.md` lanes 1 and 3
(MERGED), `PLAN-broaden-domain-switch.md` (the last patch on the carry rules this plan
deletes).

## Why

The owner wants one turn to answer stock, incoming and PO for a product, and the next turn
to keep working whether the dealer types a new code, a new domain, both, or a picker number.
The engine cannot do that today because every piece of state that would have to hold two
domains holds one: `domain_hint`, `last_result_set`, `picker_domain`, `pending.team`,
`pending.domain`. Bolting arrays onto the flat 34-key bag means threading them through 75
`domain_hint` reads in `head/output_exchange.py` (3,361 lines) and the 47 key assignments in
`tail/compile_state.py::compile_current_state` (lines 271 to 971). That is the same cost as
the approved Slice B, in a worse shape.

Measured demand is small (3 of 337 distinct real messages name two domains). This is an
owner ask, made on 12 Sep 2026, recorded as such.

## Owner decisions (grill, 12 Sep 2026)

| id | decision |
|---|---|
| D1 | Two lanes. Lane 1 = dialogue state with `domains` a list from day one. Lane 2 = fan-out, stacked. |
| D2 | Fan-out only when the message names 2+ domains. The miss ladder keeps covering the zero case on single-domain asks. A per-contact "always full report" default is deferred; trigger: owner asks after seeing lane 2 in prod. |
| D3 | Parser emits `asks: [{domain, entities[]}]`, dealer order. No `domain_hint`, no `intent_hint`, no top-level `entities`. Engine flattens at intake. |
| D4 | One WhatsApp message, one headed section per domain, one escalate line. |
| D5 | The escalate offer opens only when something was missed (as today: not-found and zero branches). Its teams are the teams of the domains that MISSED, not of every domain rendered. One team: today's yes/no. Two or more: one question with a button per team plus "No it's okay", each option numbered, so "1" picks the first team and a bare "yes" re-asks with the buttons. |
| D6 | One open question at a time. A pick resolves the entity, then every alive domain reruns. Product before tier. |
| D7 | A domain word with no product REPLACES `focus.domains`. Never appends. |
| D8 | No persisted mirrors of the 34 legacy keys. The world grader maps. |
| D9 | No counter, no TTL (owner reversed growth-r1 D11 on 12 Sep: a dealer cannot see a turn count). A focus slot is cleared only by a new entity of the same axis, a topic reset, or the Respond.io "conversation closed" event the SLA path already receives. An open question is cleared only when answered, replaced by a newer question, or when the dealer starts a new ask (a message carrying a domain or an entity); casual and low-signal messages leave it open. `member_offer` loses its TTL 3 and follows the same rule. No settings field. |
| D10 | Parser v3 ships as a new registry version; corpus replay green, then a shadow window on prod the owner watches in the console, then the owner promotes. Extra LLM cost accepted. |
| D11 | Sections in the order the dealer said them. |
| D18 | Estimate given 12 Sep: lane 1 about 3 to 4 working days of build, lane 2 about 2, the shadow window (owner's watch, 3 to 7 days) running alongside lane 2. The wide bars are L1-S3 (reply semantics, 72 test files) and parser v3 replay iterations. |
| D12 | No repeated information, by a GENERAL deduper: a fact key `(entity id, domain)` prints once per message whichever section or rung produced it. Not special-cased to stock / incoming / PO. |
| D13 | A denied domain renders its section as the existing denial copy. |
| D14 | `intent_hint` is dropped from the parser, the state and the trace. Every domain has exactly one intent (measured 13:13). |
| D15 | The low-signal clarifier receives `focus_hints`. `casual` still receives nothing. |
| D16 | No fan-out cap. |
| D17 | Deferred, triggers unchanged: episodes (L2 retrieval), profile, learning from corrections, answer LLM (D1 of growth-r1 stands: no answer LLM). |
| D19 | Owner, 13 Sep 2026, after the console pass on :3081 ("why my dym pick does not stick like before" / "need to restore"): a pick does NOT consume its roster. Restores ruling K rule 1 (6 Sep, AC-816) and the 7 Sep deviation 5, superseding AC-1014's close-on-answer clause the 12 Sep UAC introduced. A ROSTER question (`product_pick`, `customer_pick`, `tier_pick`) stays open after a pick, options frozen, `asked_at_turn` unchanged; a later bare number re-resolves against the same frozen roster. It clears only by the existing rules (a newer question of another kind, `topic_reset`, a message naming its own subject, conversation-closed). The one-team yes/no escalate offer that a pick's rerun-miss produces RIDES on the roster question instead of replacing it: `kind`/`options`/`asked_at_turn` stay the roster's, `expects` becomes `pick_or_yes_no`, `payload.offer` carries `{team, domain, options}`; a number re-picks, `yes` runs escalation and consumes the whole question, `no` declines and the roster stays with the offer stripped. Non-roster kinds (`team_pick` clarify, `company_pick`, `member_offer`) keep today's consume-on-answer behaviour. `OPEN_QUESTION_EXPECTS` gains `pick_or_yes_no` (`contracts.py`). |

## Found during S6 verification (13 Sep 2026)

Three defects the console pass and the browser run surfaced, each fixed in S7. They are
recorded here because two of them are older than this lane and would otherwise read as
S6 regressions.

| what | root cause | where fixed |
|---|---|---|
| The "multiple matches" picker did not survive: `incoming wc286` printed ten numbered products and the next `8` answered nothing (owner, turn 26b15a53-87a8-43be-8e55-5839b3ce3149) | LANE-INTRODUCED at L1-S3d. The five-key session replaced `last_result_set` / `selection_context` with `open_question`, and four of the five roster labels were converted; `disambiguation` was not, so the tail armed nothing and the escalate offer won by default. The did-you-mean roster was unaffected because its own lane freezes it (`miss_suggest._attach_question`). | `_ask_for_turn` gains the `disambiguation` arm, before the offer arm, reading its rows from `last_result_set`, then `specific_options`, then `compatible_entities` |
| A yes/no the customer was never shown was persisted on that same turn | PRE-EXISTING. `is_escalate_offer = not is_clarification` (`tail/outcome.py:148`) and `pickers.annotate_incoming` sets `is_clarification: False` on a numbered PICKER "for parity with the not-found require_specific branch", so the flag asserts an open offer on a turn whose reply ends at row 10. | the offer arm now also requires the reply to carry the frozen "Would you like me to escalate to" phrase; the flag itself is untouched, since other readers depend on it |
| A picked row whose code is a PREFIX of its siblings answered about all of them: picking row 10, `SRTWC286-SH-NEW`, of ten also answered for `-150`, `-P` and `-200` (owner, chain G, turns 00c7c844 -> 7620187b). Everything upstream was right: the roster froze rows 1..10 in render order, the pick resolved to `picks: [10]` and the one correct uuid, and the incoming tool was called with that single `product_ids`. | PRE-EXISTING. `resolve_entity_body` built `entity_pins` only when `match_mode != "and"`, and a bare pick emits `"and"` by default, so the uuid the customer had just chosen was dropped from the request; the resolver re-derived the bare token, and the product fold strips hyphens, so `SRTWC286SHNEW` matched four products. Rows 8 and 9 worked only because their codes are nobody's prefix. Byte-identical on origin/main. | S7c, owner ruling "a pin means this token IS this row": the body always sends its pins, and `references.py` narrows a pinned token on the intersection (`_apply_intersection_pins`) instead of rejecting the pin in AND mode |
| One clarifier turn produced two console bubbles, the second carrying a U+2014 in customer-facing text (tester, chain E) | PRE-EXISTING ON MAIN. The casual lane builds its `send_message` from the clarifier's RAW words before the tail runs, and the tail's fold reaches only the sealed reply - so one turn carried two texts differing by one character, and `console_service._customer_texts` de-duplicates by exact equality. | `sanitize_dashes` (em AND en) at the process boundary: the row `_close_turn` writes, `TurnResult` / `CompleteResult`, and `_attachments_src`. The tail's fold stays em-only, because six graded captures carry a U+2013 in a field it walks |

## Found during owner merge test (15 Sep 2026)

Seven defects the owner's console passes on the MERGED head (`d4ae8203b`, prompts v16 and
v20 on `sorento_ai_automation_focus_full`) surfaced, diagnosed together because five of
them meet at one seam: what survives a roster pick. Four are lane-introduced by the
five-key session (D8) replacing main's wholesale `entities` carry with per-axis focus slots
plus `payload.keep`; two (R-B, R-H) are pre-existing and byte-identical on `origin/main`,
and both are the same shape - a rule keyed on whether the model happened to stamp
`domain_hint` on a turn. Each was reproduced under prompt v20 as well as v16 except where
noted, so the cause is code and not the unpromoted prompt. Three further reports from the
same batch closed with no code change and are recorded below the table, so a later reader
does not re-open them.

| what | root cause | where fixed |
|---|---|---|
| R-A: `check stock srtwt2643` printed the did-you-mean roster AND "would you like me to escalate to warehouse team?", and the next `yes` escalated to CUSTOMER SERVICE (owner, turn 3b528785-5c5b-4b74-a9c2-d177b0f2ad2b). The `answered` stage read "Nothing was waiting on an answer." | LANE-INTRODUCED, twice over. `miss_suggest._attach_question` composes the roster with `expects: "pick"` and no `offer`, and `_offer_rides_on_roster` only merges an offer asked over a roster carried from an EARLIER turn - so a roster and an offer born on the SAME turn never merged and D19 rule 3 covered half its cases. The team then had no fallback either: the routing chain reads `previous_conversation_state.routing`, which is not one of the five keys, so it fell through to `DEFAULT_SUGGESTED_TEAM`. The lane's own `TestTheOfferDoesNotReplaceABornDisambiguationRoster` pinned the gap. | `_offer_born_beside_roster` (`tail/compile_state.py`) merges through the existing `with_offer` when the composed reply carries the frozen escalate phrase and a team is known; no `routing` key restored, because `payload.offer.team` is what `_offered_team` already reads |
| R-B: a detail pick after a customer pick re-ran the report over six unrelated SPECIALIST customers and answered "No outstanding delivery order" (owner, turn 576e1057-045e-4786-820c-2a44663eb231) | PRE-EXISTING, byte-identical on `origin/main` (`output_exchange.py:1304/1322`). `own_question and (kind == "outstanding_detail" or picked is None)` has a vacuous disjunct - whenever the open question IS the detail ask it collapses to `own_question` - so a clean pick was read as a new ask, the stored filters died with the pending, and the row label "Delivery order list" was re-resolved as a token whose substring "list" matched every SPECIALIST customer. Masked under v20, where the same bare "1" comes back `domain_hint: null`. | `picked is None` now gates that disjunct; the `names_entity` half is untouched so D17 point 3's stray-position guard stands |
| R-C: `photo for srtwc286` printed the ten-row picker, and picking a row re-asked "Please provide the attachment type" for the type the same message had already named | LANE-INTRODUCED. The co-resolved `attachment_type` was persisted nowhere: `SLOT_BY_HINT` has no axis for it, and `payload.keep` - the mechanism meant to carry exactly this - is empty by construction on a `require_specific` turn, because the gate narrows `compatible_entities` to the picker's own candidates before `_keep_beside` subtracts them. Main carried it in `session_vars.variables.entities` (capture `ms-14993042`). | the gate's narrowing keeps what ANOTHER TOKEN resolved (scoped by token, not type - capture `rs09-t1` taught the difference), and `apply_open_question_outcome` lets an off-axis `keep` member reach `o["entities"]` |
| R-D: `delivery for chin chun product wc286` then `1` answered with "Product: all products" and four DOs, none of them WC286 (owner) | LANE-INTRODUCED, the same seam. The ambiguous-customer arm also narrows `compatible_entities` to its candidates, and `_customer_pick` read no `payload` at all, so the pick emitted `entity_op: replace` with the customer alone. Main kept both (capture `b56-pick-turn`: the picked customer AND `srtwc286`). | the customer arm keeps the other axes; `_customer_pick` applies `payload.keep` as `_product_pick` already did, and routes a kept product to `focus.products` |
| R-E: the scope header read `Customer: 300-C043` (and `Customer: 300-G013`) while the miss copy two lines below named the company correctly | LANE-INTRODUCED. `_entity_of` built `raw` from the row's CODE, and `raw` is what the header's second fallback prints; a customer row's code is a synthetic debtor id. `gate.py`'s own pin re-seat already documents the rule ("the entity's raw IS the roster label we showed; products keep their canonical code") and main's spine emitted it (`b56-pick-turn`: `raw` the name, `canonical_code` the code). | `_entity_of` puts the label in `raw` and the code in `canonical_code` for customer rows; product rows untouched, where the code IS the name the customer reads |
| R-F: a roster line naming two ledgers - `CHIN CHUN HARDWARE SDN BHD (MCH, SRT)` - fetched ONE ledger when picked (`customer_ids` carried a single uuid) | LANE-INTRODUCED. The candidate-to-family map rode a `picker_families` session key, and `compile_state` writes it immediately before the five-key projection drops it, every turn - so the gate that read it back never found one, and its `_cust_base` re-key was broken anyway (fed a debtor code against a map keyed on family names). Kept on the ENTITY rather than on `open_question.payload` because of the captain's 2026-08-24 ruling that the family OUTLIVES the roster: the pin does, and binding it to the question would lose it the moment the detail ask replaces the roster one turn later. | the roster row and the picked entity carry `family_uuids` (`gate.run_gate`, `open_question._entity_of`), `entity_ids_transformer` expands it under the same uuid guard as any other id, and the map, its two dead writers and the gate's unread `picker_families` output are deleted |
| R-H: `only BRW` over an open outstanding question re-armed the scope question instead of narrowing the report already on screen (owner, turn 94639ef2-cdf7-4540-a78e-93b411ba2e84) | PRE-EXISTING, byte-identical on `origin/main`. `_outstanding_keeps_subject` vetoes a refinement whose emission is `message_type: business_query` with a non-null `domain_hint` (R24, 13 Sep), and its own docstring states the premise: "'only BRW' is `business_query` with NO domain". The live v20 model stamped `domain_hint: "order"`, so the turn fell to the new-ask arm (`outstanding_pending_dropped: true`, `outstanding_refined: null`). Same class as R-B: a rule keyed on whether the model happened to stamp a domain word. The question it was asked over was armed correctly (`outstanding_detail`, `expects: pick`, three frozen options). | the veto goes; a refinement is a turn that PICKED NOTHING and names only entities on axes that can never be this report's SUBJECT (a location, a date), which is what R24 was reaching for - a customer named under a product-subject offer ("delivery status for hanlim") is still a new ask, now because a customer CAN be the subject rather than because the model wrote a domain word |
| R-I: a stock answer with the cross-domain incoming rung ended "Would you like me to escalate to warehouse team?", and the next `yes` was routed to CUSTOMER SERVICE (owner, turns cca6b365 -> 570610f0) | LANE-INTRODUCED, on the READ side. The offer was recorded correctly (`expects: pick_or_yes_no`, `payload.offer.team: "warehouse"`); the `yes` never reached the resolver. `answers_open_question` is a prompt-v3 key and the live prompt is v1-shaped, and `_resolve_open_question` had a pre-v3 bridge for NUMBERS only - so the turn resolved nothing (`answer: {picks: [], yes_no: null}`) and the escalation lane fell back to `DEFAULT_SUGGESTED_TEAM`. R-A had fixed the WRITE half, which is why it read as scenario-shaped: the roster shape happened to need the half that was fixed. | the bridge gains the yes/no beside the numbers, from the parser's own structured flags (`escalation.is_escalation_confirmation`, `is_affirmative`) and never a word list, scoped to questions that ADMIT a yes or no (`_is_escalate_offer_question`) so a roster with no offer and a `member_offer` keep their own rules |
| The escalate offer was arm-shaped: three tail arms and one engine arm, each with its own conditions and its own team | OWNER RULING, 15 Sep 2026: "our fix needs to be general and not targeted to 1 scenario only". One rule now - *an offer exists when the outgoing reply carries the frozen sentence and names a real team; it is recorded on whatever question the turn leaves open, from ONE team source* - and one implementation, `open_question.record_offer`, which no caller passes a shape to. **Called twice on purpose:** the reply is composed in two stages (the tail composes the answer, `crossdomain_compose` may then append the sentence), so it is final at two different moments and a single call at either one is blind to the other; `with_offer` is idempotent by construction, so the second call is a no-op unless the sentence changed. The team comes from `open_question.team_from_reply`, read off the FINAL text, which closes the security review's two-sources gap (the printed sentence took its team from `roster_plan[0].team` / `qf.routing.suggested_team`, the record from `_escalation_team`, so a reply could promise one team while the stored offer routed to another). | `record_offer` + `team_from_reply` in `dialogue/open_question.py`; the tail's arms keep only their CONDITION and delegate the construction, and the engine arm delegates the same way |
| A decline under an open outstanding question re-ran the report instead of closing it | FOUND BY THE CORRECTNESS REVIEWER (B2) as a consequence of R-H. `named_entities` counts the CARRIED subject, and R-H's refinement test ignores carried entities, so a turn that picked nothing and merely echoed the subject read as a refinement: "no" re-ran the report and left the question armed. | arm 1 gates on `names_own_entity` (what THIS message named); arm 2 keeps `names_entity`, because a turn that carries a subject AND names its own entity is the new ask it always was. Verified: the decline now drops the pending and runs no tool |
| The same decline then closed in SILENCE once arm 1 stopped catching it | OWNER RULING, 15 Sep 2026: "R22 stands and arms may not differ". Two arms close an outstanding question - the new-ask arm and R22's way-out - and only the way-out stamped a DECLINE, so B2's fix moved the "no" to the other door and it got no closing line. | `_close_outstanding_pending` is the one close: it sets `outstanding_pending_dropped` and, when the turn is a decline, `outstanding_offer_declined` plus the three routing fields that get it to the lane's closing reply. Neither arm carries copy of its own |
| The single-invocation step for rule 1 | OUT OF THIS ROUND (captain, 15 Sep 2026). Deleting the tail's arms outright moved 9 owner worlds for a cause that was not isolated inside the round's budget, so the arms keep their selection conditions and delegate construction to `record_offer`. One rule, one implementation, one team source; two call sites rather than one. The trigger to revisit is somebody having the time to read those 9 world expectations | `record_offer` in `dialogue/open_question.py`, called by the tail's two arms and by the engine arm |
| A this-turn entity emitted with `current_message: null` read as CARRIED | FOUND BY THE REVIEWER (S1). The schema allows null and `gate.py` calls it corrupted; `clearing.py` asks the same question as `is not False`. Read as carried, "delivery status for hanlim" re-ran with the OLD product code and kept the question - R24's loop, reintroduced. | the refinement test asks `is False`, so only an explicitly carried entity is excluded |
| R-J: after a customer pick the scope question is PRINTED but not ARMED, so the next `1` re-picks the customer and the same question is printed again (owner smoke on c95f811bb, turns b4863e5d -> a509fbb0 -> add34025) | LANE-INTRODUCED, and mine: `_spend_the_answer` (added for R-I) overwrote the question the same turn ASKED. The pick's roster carried a riding offer, so the seam fired and `carry_after_answer` kept the roster (D19 rule 1) over the freshly armed scope question - the customer read the scope ask while the bot waited on the customer list. Located with tester 2's red, not guessed: the probe showed `asked = outstanding_scope` winning in the tail on every shape a test exercised, so the answered/asked precedence was never the cause. Second half, the `v1-replace` channel: a numbered answer arrives `casual` with no status of its own and the model spells it `reuse` or `replace_combine`, and the `order_status` carry was gated on `reuse`, so the other spelling lost the status and the outstanding ask degraded into a plain order answer. | the answer is spent on the question it ANSWERED and stands aside when the turn asked something new; the status carry is keyed on the PICK (broad, per R16, which names exactly that turn) |
| R-K (MERGE BLOCKER): under the PROMOTED v20 prompt a bare "10" over a live ten-row roster came back as chat - `incoming wc286` -> "8" -> two casual turns -> "10" read as `casual` with `reference_positions: []` (owner smoke on 92f0c081b, turns ab73f52b / 8440c1ff / 3fd0d37c). The same chain passes under v15. | LANE-INTRODUCED, in the parser INPUT rather than the state. The roster was perfect - all three casual turns carry `before_kind: product_pick` with ten options, so D9's clearing rule held - but the `Open question options:` line is gated on `_OPTION_PENDING_KINDS`, which D17 scoped to the outstanding report's two questions. A roster's rows were therefore never stated to the model, and the promoted v1 prompt sees no `Focus:` / `Open question:` block (v3-only), so nothing in its input mentioned a list. v15 is green because v3 emits `answers_open_question` off its own state block; prod runs v20. | the tuple states the RULE - a question whose answer is a POSITION states its roster to the parser - and the roster kinds plus `member_offer` join it. Nothing new is stored: the rows come off the question, the same frozen list the head resolves the position against. `test_parser_user_block_parity` and every `construct-user-prompt` capture are unchanged |
| R-L: after ONE casual turn a member offer comes back `kind: member_offer`, `options: []`, `payload.team` re-derived to customer_service, so a "2" picks nobody (tester 2, under the member-offer guard) | LANE-INTRODUCED, and the SAME defect S6 fixed for three kinds only. The `offer_hold` re-prompt re-arms the question from a carried LABEL, so the rows `_ask_for_turn` is handed beside it are this turn's (empty) and the team is re-derived from this turn's routing - and `_is_a_re_arm_of` recognised a re-arm only for `ROSTER_KINDS`, so everything else kept the empty list and the wrong team. OWNER RULING, 15 Sep 2026: ANY re-arm of an open question keeps its frozen options AND its recorded team. Generalised rather than widened by one kind: the kind test is now "the same kind as the live one", the EXPECTATION test that the kind test used to carry stays (a plain `yes_no` escalate offer must never inherit a `pick` team clarify's roster), and `member_offer` is NOT added to `ROSTER_KINDS` - what a PICK does to a question is a different rule. A live question with no rows re-prompts empty exactly as before, which is why `TestOfferHold` does not move. | `_is_a_re_arm_of` / `_same_expectation` / `_re_armed` in `tail/compile_state.py`, one seam; `member_offer` then joins `_OPTION_PENDING_KINDS` because its answer is a position too. KNOWN CONFLICT reported to the captain, not edited: `test_s5_escalation_seams::test_clarify_arm_surfaces_the_ask_and_re_persists_the_offer_state` pins `options == []` for the clarify arm over a prior member offer WITH rows - an indistinguishable state shape - while its own docstring requires the pool to survive ("the next turn resolves the customer's '2' ... against exactly that pool") |
| B-1 (FINAL REVIEW BLOCKER): a customer token that echoes the whole OFFERING CLAUSE was recorded as the promised team - `escalate to purchasing.`, `or 'yes' to escalate to warehouse.` and `would you like me to escalate to purchasing team.` all quoted back above a real customer-service offer | LANE-INTRODUCED, on the READ side of rule 1, and the remaining half of the security review's S1. Anchoring `_ESCALATE_TEAM_RE` on the offering clause was not enough once the token IS that clause: `compile_state`'s miss arms and `answer.py`'s `raw_of_tok` print the token back ABOVE the appended offer, so the FIRST match is the customer's word and the question recorded a team nobody promised. Second half, at the engine's post-compose arm: it read a team off a pure ECHO with no offer appended at all and minted a `team_pick` a later bare "yes" would have accepted. | LAST MATCH WINS in `team_from_reply` (every composer appends its clause at the END, and `_catalogue_team` means only a span that reduces to a `SUGGESTED_TEAMS` member can win, so an echo-only reply returns None); and the engine arm now gates on an OPEN offer - the tail's own `offer_open`, or `crossdomain_compose` having handed it an offer - exactly as the tail arm does |


| R-K, SECOND ROUND (the first fix was unreachable): on the live smoke of 6584eb6e7 the same chain failed again - `incoming wc286` -> `8` -> two casual turns -> `10` came back `low_signal`, turn 34000918. | THE RIDING OFFER HID THE ROSTER. `_pending_kind` (engine.py:448-450) answered `team_pick` for ANY question carrying a `payload.offer`, so `_pending_options` read that word against `_OPTION_PENDING_KINDS` and sent no rows - and the one prompt line a v1 prompt gets named the yes/no instead of the list. The model quoted it straight back: `user_goal: "trying to reply with a bare number while a team pick is pending"`, `reference_positions: []`. Measured across the chain: every turn whose question carried an offer (`expects: pick_or_yes_no`) was shown NO rows, and the single turn whose question had none (7e14db69) was shown all ten. The same suppression hit the customer picker on the R-M chain (f7a37b7e). | the collapse is deleted: the `Pending:` line names the question that is OPEN, whatever rides on it. D19 rule 3 already rules a merged question IS the roster (kind, rows and clock kept, the offer adds a yes and a no), `expects: pick_or_yes_no` is where "a yes is also acceptable" lives, and the v1 bridge reads the parser's own flags rather than this label. A PLAIN offer still names itself. 9 reds over product/customer/tier x 0/1/2 casual turns, plus the negative |
| R-M: `DO outstanding for chin chun` -> `1` -> `2` -> `only BRW` answered with a header naming HOME CARE SPECIALIST, BATH IDEA ... SPECIALIST and four more companies nobody had named, over an escalation member roster (owner smoke on 6584eb6e7, turn 0b610e47) | THREE STEPS, measured on the turn. (1) `_apply_outstanding_pending`'s refinement arm (output_exchange.py:1692) required `picked is None`, and v20 had stamped `reference_positions: [1]` on a message that only narrows (`user_goal: "trying to select the delivery order list and narrow it to BRW"`), so the narrowing was disqualified; (2) the new-ask arm (:1706) then closed the question on `names_entity`; (3) the generic REFERENCE POSITIONS -> ENTITIES block (:2648-2713) mapped position 1 to the row LABEL and overwrote `o["entities"]` wholesale, so BRW was gone and `{raw: "Delivery order list", hint: "order"}` went to the resolver - where "list" matched every SPECIA-LIST customer. That is R-B's mechanism on the arm R-B did not close, and the good scope turn three seconds earlier escaped it only because IT took the answer arm, whose second pass re-asserts its reading and resets `entities` to `[]`. | the mint is gated on the LIVE QUESTION's kind: a position over a kind the HEAD resolves (`open_question.HEAD_RESOLVED_KINDS` - the two outstanding questions, whose rows are menu labels and which have no `resolve` handler by design) is never converted into an entity. And the reading: what the MESSAGE NAMES decides, so a stray position no longer vetoes the refinement arm. A pick that lands on a row still answers, and an off-subject filter the same message named is overlaid - which is not a new rule but the one `TestScopeAnswerRunsReportWithCarriedFilters::test_a_date_in_the_answering_turn_wins_over_the_carried_one` has pinned for "2 in 2026" since reviewer N2, so "2, only BRW" behaves the same way: scope `do`, `warehouse_codes: ["BRW"]`, the stored subject intact. A subject-capable entity (a customer) is still a new ask, D17 point 3 unchanged |
| S-1 / S-2 (final review): an ANSWERED turn that prints the escalate sentence recorded nothing, and where a reply carried BOTH the bot's sentence and the customer's echoed token the text could not say which was the promise | S-1: `answer.py`'s partial-promo and entitlement-miss arms print the sentence on a turn with `offer_open` false and no cross-domain offer, so the engine arm's open-offer gate dropped it and a following "yes" resolved nothing - R-I's class, reintroduced by that gate. S-2: `_partial_dym_block` appends the echo AFTER the lane's own sentence, so "last match wins" reads the echo exactly as "first match" did - the text has no reliable answer. | ONE RULE: *whoever appends the offer sentence records the offer.* `answer._offering` wraps the TEAM EXPRESSION at all 20 print sites in the three composers (the wordings are byte contracts, so nothing else moves), the record rides a fragment rather than any node's output (no capture moves), the two miss arms record their own team in `turn_state`, and `crossdomain_compose` already declared its own. `record_offer` takes the team, `team_from_reply` becomes the parity reader the tests compare printed against recorded with, and there is deliberately NO text fallback - a composer that prints without recording un-arms its own offer, which the six per-composer guards catch |

Closed WITHOUT a code change, same console batch (the owner's outstanding re-run after the
`sales_orders.outstanding` grant landed on the console DB):

| what | verdict |
|---|---|
| Every `pending_kind:` assertion in the console case files graded as a failure | HARNESS ARTIFACT. `scripts/chatbot_console_check.py::_pending_of` reads `variables["pending"]["kind"]`, the marker D8 deleted (AC-1019), so it answers `None` for every turn on this lane. The arming is correct: turn 1bd12a11's `remembered` stage carries `open_question {kind: outstanding_scope, expects: pick, options 1/2/3 frozen, payload.filters.customer_ids = the six HANLIM accounts}`. Ported on the tester's branch to read `open_question.kind` from the same two sources, falling back to `pending.kind` for a non-five-key backend. |
| "the scope offer does not resolve, and the next `1` lands out_of_scope" | REFUTED BY THE ROWS. `dd5839a2` ("3" over an open `outstanding_scope`) carries `reference_positions: [3]` and `outstanding_answer_applied: true`. The later `1` (`05eeac36`) arrived when the open question was a `member_offer`, armed by the escalation on the turn before it, so it picked a CS member and branched `out_of_scope` - coherent. `9a23ec02` ("SRTWT7445 outstanding in 2026") dropped its pending correctly: a turn naming its own product is a new ask by design. |
| R20 turn 3 (`36aaf33a`) answered zero rows where the case expects Outstanding 5 | DATA DRIFT on the clone, confirmed by query: SRTKT39SS has 402 sales order lines and 79 delivery order lines overall, and 0 for customer 060f4eaf (CHIN CHUN HARDWARE [A/C I]) inside 2026. The pick resolved and the stored filters carried faithfully - the reply's own header prints the product, the customer and the 2026 window. No action. |
| Found NOT fixed: "DO outstanding for chin chun" asks which document | PRE-EXISTING PROMPT EMISSION GAP, out of this lane (captain ruling, 15 Sep 2026; issue filed for a `do_outstanding` / `so_outstanding` vocabulary migration). The arming turn's own emission is `order_status: "outstanding"`, plain - not `do_outstanding` - so `_outstanding_scope_ask_candidate`'s test fires and the scope ask is correct FOR THAT EMISSION. #862's pre-scoping keys on the specific words, which the model did not produce here. Pre-grant the chain went straight to the DO summary because without `sales_orders.outstanding` the scope ask is not a candidate at all, so the grant is what exposed this, not this round's changes. Deriving the document type from the customer's words in the head would be the D11 word-list this lane forbids, which is why the prompt is the honest route. | not fixed here; tester 2's guard is written against the EMISSION (`order_status: do_outstanding` pre-scopes) |
| The six-ledger family expansion on `CHIN CHUN HARDWARE SDN BHD (MCH, SRT)` | CORRECT BY DEFINITION, no change (captain ruling, 15 Sep 2026). `_cust_base` (`gate.py:379-386`) strips brackets and parens, the legal form and non-alphanumerics, so `[A/C I]`, `[CERAMIC]`, `[IBORN]`, `[A/C II]` and `[A/C III]` all reduce to one key - the markers are exactly what the grouping deletes - and the roster label's `(MCH, SRT)` is the COMPANY span, a different axis from the account markers. Six accounts across two companies is consistent with the line. OWNER QUESTION recorded rather than answered: whether a CERAMIC or IBORN ledger should count as the same customer for an outstanding report is a business rule, and changing `_cust_base`'s marker rule would move every family in the system, so it needs its own decision and its own evidence. | none |


Noted for a later reader (security review, 15 Sep 2026): for a token that matched several
rows, `keep_entities` carries the customer's own WORD rather than a uuid, so the next turn
re-resolves it as free text under that contact's scope. That is main's own shape for this
case (capture b56-pick-turn) and the alternative - pinning one of ten variants the customer
never named - is worse; the trigger to revisit is a report of a family prefix resolving
differently between the two turns.

Replay: 8 captures move and the tester registers both classes rather than the coder
(captain's ruling (b), 15 Sep) - 3 by the additive `family_uuids` key alone
(`CAPTURE_BODY_ADDITIONS["disallowed-entity-gate"]`, where `specific_options`,
`display_name` and `incompatible_only` already sit for the same reason), and 5 as a
field-scoped divergence on `compatible_entities`' customer family rows, because their
recorded `ctx` still carries the `picker_families` map this replaces.


## What exists (origin/main 62e911e, 12 Sep 2026)

| thing | where |
|---|---|
| session read | `app/services/chatbot/engine.py:417` `_read_session_vars` over `conversation_variables_service.get_for_contact` |
| session write | `engine.py:3066` `overwrite_for_contact` inside `run_tail`, after `compile_current_state` at `engine.py:3001` |
| the stage runner | `engine.py:1099` `_run_stages`; `understood` at 1198 to 1264, `post_process` call at 1225, `suggest_follow_up` at 1226 |
| carry rules | `head/output_exchange.py`: `post_process:970` / `_post_process:997` to 3303; K4 block 395 to 431 and its application at 2128; K2 at 2393; `_switch_word_domain:652`; `_query_brands_carried` at 1705; `_tier_carried` at 1733; AXIS BROADEN at 1400 and 3286; `derive_routing:73` (hard-codes the team per domain, duplicating `DOMAIN_SPEC.escalation_team`); `_team_clarify_pick:789`; dym pick application and reference positions at 1800 to 1870 |
| state compiler | `tail/compile_state.py:271` `compile_current_state`, the `variables` literal at 725, `_partial_dym_block:1380`, `_picker_carry:1723`, `_offer_carry:1858`; `tail/pending.py` writes `pending`; `tail/member_offer.py` |
| business lane | `lanes/business/__init__.py`: `run_until_exit:56` (engine 1452) then `resolve_gate.run:669`; `run_fetch:204` (engine 1526) picks `select_tool(domain)` at 307; `complete_answer:450` (engine 1984) calls `run_crossdomain` at 603 and `build_result` at 623; `miss_suggest.run_miss_lane:1271` builds the dym / sibling / partial-miss roster |
| contracts | `contracts.py`: `DOMAIN_SPEC:88`, `PENDING_KINDS:576`, `SESSION_VAR_KEYS:589`, `Pending:629`, `SessionVars:650`, `Envelope:707` (`shadow_of` at 726), `INGRESS_KINDS:527` |
| parser | `head/parser.py:73` `_build_json_schema`; prompt text `app/services/chatbot_parser_prompt.py` (100,585 bytes); registry key `chatbot_semantic_parser` at `ai_prompt_registry.py:788`; versions are published by data migrations (475, 480, 487, 490), each a new unlabelled version; promote = `AIPromptService.set_label` (`ai_prompt_service.py:281`) via `POST /ai-assistant/prompts/{name}/labels` |
| clarifier | `lanes/casual.py`, key `chatbot_clarifier`, `construct_user_prompt:154` blanks state for `casual` and `unknown` |
| shadow | `chatbot.turns.shadow_of` is written from the envelope at `engine.py:560`; nothing reads it |
| settings | model columns in `app/models/user.py` (567 to 595); schema `SystemSettingUpdate` at `api/v1/user_management/settings.py:20`; GET dict at 379 to 384; `_CHATBOT_COLUMN_DEFAULTS` at 645 to 658; FE `app/(protected)/user-management/settings/chatbot/page.tsx` + `services/chatbotSettingsService.ts`. `chatbot_crossdomain_ladder` is NOT on the FE page yet |
| console | `api/v1/system/chatbot.py`: `list_turns:145` (params `contact_respond_id, from, to, status, limit, cursor, include_test`), `get_turn:295` with `trace_detail.compose_trace_detail:242` (nine keys); FE `app/(protected)/system-management/chat-history/`: `TurnPanel.tsx`, `StateTracePanel.tsx` (Parser drift chip row at 59), `TurnDetailDrawer.tsx`, `hooks/useChatbotTurns.ts`, `services/chatbotTurnService.ts:121` |
| tests | `tests/chatbot/worlds.py` (`World.session_vars` input, `expected_variables` target, `body_difference:536`, `drop_paths:524`), `test_worlds.py` reads `respond_contacts.session_vars` at 252 and strips `pending` at 104; `test_replay.py` grades node captures; `divergences.py`; 72 test files import `output_exchange`, 11 import `compile_state`; CI runs the whole `tests/` sweep |
| migrations | highest prefix 512 (two files, `512_hidden_by_default_col` and `512_integration_ref_company`); this lane numbers from 513 and re-parents with `./scripts/alembic-reparent.sh` at PR time |

## Lane 1 base: the unpushed `feat/chatbot-growth-dialogue` branch

What it already has (worktree `.claude/worktrees/chatbot-growth-dialogue`, HEAD `ba13cabbc`):
`dialogue/decay.py` (per-slot turn TTL, `focus_hints`, `open_question_hint`),
`dialogue/focus.py` (the carry rules as named functions: `replace_same_axis`,
`reset_on_topic`, `reuse_alive`, `reuse_domain_entityless`, ...), `dialogue/open_question.py`
(one typed question, `OPEN_QUESTION_KINDS`, frozen options, one resolver), `Focus` /
`FocusSlot` / `OpenQuestion` contracts, parser v3 keys (`answers_open_question`, `anaphora`,
`topic_reset`) published as an unpromoted registry version by a data migration, engine
wiring, `compile_state` writing `focus` + `open_question`, seven owner worlds, and tests
(`test_focus_decay.py`, `test_focus_rules.py`, `test_open_question.py`, `test_parser_v3.py`).

What it does NOT have, and lane 1 adds or changes (each is a delta on that branch):

| delta | why |
|---|---|
| merge `origin/main` (48 commits; 18 overlapping files, `output_exchange.py`, `compile_state.py`, `engine.py`, `parser.py`, `contracts.py` among them) | the branch predates growth-r1 lanes 1 and 3, the broaden-domain-switch fix and the answer polish |
| renumber its migrations `488_chatbot_focus_ttl`, `489_chatbot_parser_v3`, `490_chatbot_turn_run_id` (main already owns 488 to 491) to `513+`, and DROP `488_chatbot_focus_ttl` + `system_settings.chatbot_focus_ttl_turns` entirely | D9: no TTL |
| `decay.py` becomes `clearing.py`: no `ttl_turns`, no `is_alive` by age; clear on conversation-closed marker and on a new ask; `open_question.ttl_turns` removed | D9 |
| `focus.domain` becomes `focus.domains` (list); parser schema replaces `domain_hint` + `intent_hint` + top-level `entities` with `asks[]`; `intake.flatten` | D3, D14 |
| `SESSION_VAR_KEYS` shrinks to the five keys; every mirror the branch still writes (`picker_domain`, `pending`, ...) goes; grader mapping in `worlds.py` | D8 |
| shadow parse + `ingress = shadow` + console filter, badge, summary, drawer column | D10 |
| clarifier receives `focus_hints` | D15 |

The branch's decay tests retire with the rule; its focus-rule and open-question tests are
kept and extended. Its `test_worlds.py` expectations are re-derived through the mapping.

## Design

### Persisted state (lane 1)

`respond_contacts.session_vars` keeps its JSONB column and its wholesale `FOR UPDATE` write.
The shape becomes:

```
{
  focus: {
    domains:     {value: ["inventory", "incoming"], set_at_turn, set_at, source},
    products:    {value: [entity], ...}, customer, transporter, warehouse,
    date_window: {value: {start, end, mode}, ...}, attributes, tier, brands
  },
  open_question: {
    kind: "product_pick" | "customer_pick" | "tier_pick" | "team_pick" | "company_pick" | "member_offer",
    expects: "pick" | "yes_no" | "free",
    options: [{idx, label, uuid, code, domain, ...frozen row}],
    asked_at_turn, asked_at, payload
  } | null,
  ideation: {...as today},
  access_levels: [...],
  contains_flyer: bool
}
```

`SessionVars` is `extra=forbid` over those five. `Focus`, `FocusSlot`, `OpenQuestion` are
Pydantic models in `contracts.py`. `SESSION_VAR_KEYS`, `PENDING_KINDS`, `Pending` go.
`chatbot_parser_shadow_version` is one new `system_settings` column (migration
`513_chatbot_parser_shadow`), exposed through `SystemSettingUpdate`, both dict builders, and
one field on the chatbot settings page. No new table: one writer,
one reader, one row per contact (PRINCIPLES "one preference does not need a table").

### The dialogue module (lane 1)

New package `app/services/chatbot/dialogue/`, pure functions, no DB, no LLM:

- `clearing.py::apply(session, parse, conversation_closed)` applies D9: clears every slot on
  a conversation-closed marker, clears the open question when the parse carries a new ask
  that is not an answer to it, returns the trace lines (`decay` key in `trace_detail` keeps
  its name; its entries read `{slot, reason}`).
- `hints.py::focus_hints(focus)` and `open_question_hint(oq)` build what the parser and the
  clarifier see. Typed, alive slots only, option labels only.
- `intake.py::flatten(parse)` turns `asks[]` into `domains[]`, `entities[]` and the per-turn
  binding `{domain: [entity index]}`.
- `focus.py::apply(prev_focus, parse, resolved, turn_no)` runs, in order,
  `replace_same_axis`, `reset_on_topic`, `reuse_alive`, `domains_from_asks`,
  `date_restated_only`, `anaphora_reuses`, `confident_guard`. Each is a named function
  returning `(focus, trace_line)`. The outputs keep the axis executor's
  `clear / reuse / modify / replace / replace_combine` vocabulary so `resolve_gate` and the
  lanes read the same shapes they read today.
- `open_question.py::resolve(oq, parse, quoted_options)` dispatches on `kind` to one handler
  each (`product_pick`, `customer_pick`, `tier_pick`, `team_pick`, `company_pick`,
  `member_offer`) and returns an outcome the engine acts on: `focus_patch`, `lane`
  (`business`, `escalation`, `declined`, `none`), `trace`.
- `open_question.py::ask(kind, options, payload, turn_no)` is the ONE constructor every
  lane uses to open a question; `idx` is assigned here, from 1, across the whole roster.

### Turn order (lane 1)

`engine._run_stages` changes in four places:

1. `received`: after `_read_session_vars`, `clearing.apply`, then `hints`. The parser call takes
   `focus_hints` and `open_question_hint` instead of the previous reply text and the raw
   state.
2. `understood`: parser v3 schema; `intake.flatten`; `post_process` shrinks to the emission
   assertions and `derive_routing` (which now reads `DOMAIN_SPEC[d].escalation_team` and
   keeps only the certificate split). Every carry rule listed under "What exists" is
   deleted.
3. NEW `answered` (before `access`): if an open question is alive and
   `answers_open_question.resolved`, `open_question.resolve` runs; its `focus_patch` applies
   and its `lane` overrides routing. An open question that is not answered survives a casual
   or low-signal message; a new ask cleared it at `received` (D9).
4. `focus.apply` runs after `resolve_gate` (it needs the resolver's `entity_type` and
   `confident`); `run_fetch` and `complete_answer` read products, customer, date window and
   domain from `focus`, not from `qf`.

`run_tail`: `compile_current_state` keeps building the reply text and quick replies; its
`variables` output becomes `{focus, open_question, ideation, access_levels, contains_flyer}`
assembled from the dialogue module's outputs. `_partial_dym_block`, `_picker_carry`,
`_offer_carry`, `tail/pending.py` and the `dym_offer` ladder are replaced by
`open_question.ask` calls at the point each lane decides to ask.

`trace_detail` keeps its nine keys; `decay`, `focus[]` and `open_question` are now populated
by the module, so the drawer panels shipped in PR #733 render without change beyond the
`domains` list.

### Parser v3 and the clarifier (lane 1)

Schema (strict, `head/parser.py`): removes `domain_hint`, `intent_hint`, `entities`,
`scope_intent`, `broaden_axis`, `reference_positions`, `reference_target`; adds
`asks: [{domain, entities: [entity]}]`, `answers_open_question: {resolved, picks: [int],
yes_no: bool|null, free_text: str|null}`, `anaphora: bool`, `topic_reset: bool`. Every other
key stays. Prompt v3 text lives beside v1 in `chatbot_parser_prompt.py` and is published as
a new unlabelled version by data migration `514_chatbot_parser_v3`; the `production` label
moves only by the owner's hand (D10). The prompt no longer contains "continue the previous
turn", "keep the previous domain" or "re-emit previous entities"; it receives `focus_hints`
and `open_question_hint` as structured JSON under a fixed heading.

Clarifier prompt v2 (`chatbot_clarifier`, migration `514` too): `construct_user_prompt` sends
`focus_hints` + `open_question: none` for `low_signal` and `unknown`; `casual` sends nothing.
The instruction: ask for the one axis the alive focus lacks for the alive domains.

### Shadow parse (lane 1)

When `chatbot_parser_shadow_version` is set, `run_turn` enqueues (same offload path as the
live turn, fire-and-forget, after the live turn's row is inserted) a shadow job: run the
parser at that version over the same envelope and the same hints, insert a `chatbot.turns`
row with `ingress = "shadow"` (new `INGRESS_KINDS` member), `shadow_of` = the live
`message_id`, `status = done`, the parse in `trace`, no reply, no session write, no send.
A shadow failure is a `failed` shadow row and never touches the live turn.

Console: `list_turns` gains `ingress` as a filter and, when `ingress = shadow`, a `summary`
in the response: `{count, branch_parity, asks_parity}` computed over the filtered rows by
joining each shadow row to its live row on `message_id`. FE: a "Shadow" filter chip on the
chat-history list (`ChatbotTurnFilters` gains `ingress`), a drift `Badge` on a shadow row
when `branch_kind` or `domains` differ from the live row, the summary line in the list
header, and the drawer's Parser drift panel showing live and shadow parse side by side (it
already has the chip row; the side-by-side is one new column).

### Fan-out (lane 2)

`run_fetch` loops `focus.domains` in order; for each domain it runs `select_tool(d)` with the
entity list bound to `d` (or every entity when unbound) and the date window when
`_domain_takes_a_date_filter(d)`. One envelope per domain, one `tool` trace event each.
A domain the contact is not granted yields a `denied` envelope instead of a tool call.

`complete_answer` renders one section per envelope in order. One general deduper:
`printed: set[(entity_id, domain)]`, shared by every section and every ladder rung. Whoever
renders a fact for entity X under domain D first adds `(X, D)`; any later renderer (a section
or a rung, for any domain in `DOMAIN_SPEC`) skips it; a section with every entity already
printed is omitted. After the sections, the ladder climbs only to rungs OUTSIDE the asked
set for codes empty in every asked section, once. A denied envelope renders the existing
denial line and runs no ladder. `tail/compose.crossdomain_compose` writes ONE escalate line.

Escalation: the offer opens only when a section missed (the same `escalate_catalog` /
`offer_open` conditions as today, evaluated per section). Teams =
`{DOMAIN_SPEC[d].escalation_team for d in MISSED domains} - {None}`, deduped, in section
order. Every section found: no offer. One team: today's yes/no (kind `team_pick`, one option,
`expects: yes_no`). Two or more: `team_pick` with `expects: pick`, options numbered from 1,
one quick reply per team plus "No it's okay"; "1" picks the first team, a team label picks by
equality, `yes` re-asks with the same buttons (handler outcome `reask`).

`derive_routing` keeps the certificate split for `product_attachment` and otherwise reads
`DOMAIN_SPEC`; the per-domain `if` chain is deleted.

### Simplest thing that works, checked

- No new table, no memory service, no episode store. Two columns, one package of pure
  functions, one schema change.
- No registry of handlers: `open_question.resolve` is a `match` on six literal kinds.
- No answer LLM; sections are the existing envelope renderer called N times.
- The ladder mechanism is reused, not rebuilt; the only addition is the consumed set.
- `focus` slots carry the four fields the trace needs and nothing else.

## Slices

### Lane 1 - `feat/chatbot-focus` (PR 1, branched from `feat/chatbot-growth-dialogue`)

| slice | scope | ACs |
|---|---|---|
| L1-S0 | Base: branch `feat/chatbot-focus` off `feat/chatbot-growth-dialogue`, merge `origin/main`, resolve conflicts, existing chatbot suite green on the lane DB `sorento_ai_automation_focus`; then contracts + settings: `Focus`, `FocusSlot`, `OpenQuestion`, new `SessionVars`; migration `513_chatbot_parser_shadow` (one column); `SystemSettingUpdate` + both dict builders; FE page field "Parser shadow version" (clearable `SearchableSelect` over `GET /system/chatbot/console/prompt-versions`); `external/conversation_variables` schema; the conversation-closed marker on `respond_contacts.session_vars` written by the existing SLA close path | AC-1001, 1002, 1004, 1013, 1028, 1034 |
| L1-S1 | `dialogue/` package, pure, fully tested: clearing, hints, intake, focus rules, open_question ask/resolve with six handlers | AC-1003, 1005, 1008, 1010, 1011, 1012, 1016, 1017, 1019, 1020, 1021 (flatten half) |
| L1-S2 | Parser v3 schema + prompt text + migration `514` (parser v3, clarifier v2); clarifier hints; replay assertion | AC-1021, 1022, 1023, 1024, 1026 |
| L1-S3 | Engine wiring (`received`, `understood`, `answered`, focus apply), business lane reads focus, `compile_current_state` writes the five keys, delete the carry rules and `tail/pending.py`; world grader mapping; divergences; trace population | AC-1006, 1007, 1009, 1014, 1015, 1018, 1025, 1032, 1033, 1035, 1036 |
| L1-S4 | Shadow: enqueue, `ingress = shadow`, list filter + summary, FE chip + badge + summary line + drawer column | AC-1027, 1029, 1030, 1031 |
| L1-S5 | Owner console pass (`console_cases/2026-09-xx-focus.yaml`), guide, DoD | AC-1037 |
| L1-S6 | Sticky roster (D19): `pick_or_yes_no`, `open_question.ROSTER_KINDS` / `carry_after_answer` / `with_offer`, the tail's carry, the offer merge in `_arm_cross_domain_offer`, `offer_is_open` | AC-1014 (amended), AC-1018, AC-1020 |
| L1-S7 | Found during S6 verification (below): `_ask_for_turn`'s missing `disambiguation` arm, the offer arm gated on the frozen phrase, and the dash fold at the process boundary | AC-1013, AC-1014, AC-1020 |
| L1-S7c | Found during S7 verification: a uuid pin is honoured in AND mode, so a picked prefix code stays one product | AC-1014, AC-1017 |

L1-S3 is the slice that changes reply semantics. Rule for the 72 test files importing
`output_exchange`: the `tester` lists, before the coder starts S3, which tests assert a
deleted rule (they retire with the rule, in the tester's commit, with the rule name in the
commit body) and which assert behaviour that now lives in `dialogue/` (they are ported as
tests of the named rule). The coder deletes no test. `test_replay.py` captures for
`output_exchange` retire with the function; world captures stay through the grader mapping.

### Lane 2 - `feat/chatbot-multi-domain` (PR 2, stacked on lane 1)

| slice | scope | ACs |
|---|---|---|
| L2-S0 | `run_fetch` loop with binding + denial envelopes; `complete_answer` sections + consumed set + closing ladder; `_domain_takes_a_date_filter` per section | AC-1040 to 1048, 1052, 1053 |
| L2-S1 | Team set, `team_pick` multi-option, `yes` re-ask, `derive_routing` on `DOMAIN_SPEC` | AC-1051 |
| L2-S2 | Picker before fan-out, product before tier; worlds; console case yaml; drawer check | AC-1049, 1050, 1054 |

## Testing seams (agreed before Phase 2)

- `dialogue/*`: pure functions, pytest per rule and per handler, no DB.
- Parser and clarifier: fake provider returning a fixed v3 emission; prompt render asserted
  as text.
- Engine: worlds (`tests/chatbot/worlds.py`) with a fake MCP and the Postgres fixture; every
  AC tagged "world" is one `World` entry, multi-turn where stated.
- Console: pytest on `list_turns` with `ingress=shadow`, vitest on the badge, the chip and
  the summary line, agent-browser for the E2E ACs.
- Settings: pytest on both dict builders, vitest on the field.

## Phase 1 (frontend, mocked)

Small: one settings field, one filter chip, one badge, one summary line, one drawer column.
Built first against a mocked `chatbotTurnService` and `chatbotSettingsService`, verified with
agent-browser by sidebar clicks at 375px and 1280px. No motion: the chip, badge and panels
use the existing primitives only (AC-1037).

## Hazards

- **Parser v3 regressions.** The gate is the corpus replay (every capture flattened and
  graded on `asks` and `answers_open_question`), then the shadow window. The `production`
  label does not move in a migration.
- **World grader drift.** The mapping function is the one place legacy expectations are
  translated; a world that cannot be mapped is a registered divergence with a reason, never
  a silent skip.
- **Worker.** Shadow jobs ride the same offload path; a lane that edits `app/tasks/*`
  restarts its worker session (CLAUDE.md).
- **Two 512 migrations on main.** `./scripts/alembic-reparent.sh` at PR time; single head
  asserted before marking ready.
- **`response_model` drops undeclared fields.** The list summary and `ingress` are asserted
  in a route test.
- **Both dict builders.** The new settings column is asserted in the GET and the PUT.

## Deferred (triggers)

| deferred | trigger |
|---|---|
| per-contact "always full report" default | owner asks after seeing lane 2 in prod (D2) |
| `domains_op: add` ("also PO?") | corpus shows "also / and / 还有" asks after a fan-out answer |
| episodes, profile, learning from corrections | growth-r1 triggers unchanged (D17) |
| shadow of the clarifier | parser shadow shows a clarifier-caused drift class |
