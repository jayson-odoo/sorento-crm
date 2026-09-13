# PLAN - Chatbot escalation routing: verb, team and brand from one source each

Status: READY 13 Sep 2026. Reviewer and security verdicts READY on c329fd477 (S9 comment fix on top); two owner console passes since, each finding one defect, each fixed with the tester's real-shape tests merged: the yes/no answer under the promoted parser (ec2b3bb7b) with the family-narrowing source beside it (36e24e928), and the miss lane's combined did-you-mean plus escalate offer (b6e108634). S1 to S6, three review rounds, the tester's five rounds folded in, guide written. `feat/chatbot-focus` merged in at the pre-PR gate (one hand-resolved conflict, in `head/output_exchange.py`), single alembic head `517_chatbot_session_5key`, this lane adds no migration. See "Found on the console pass" for both root causes, which are #863's. Lane `feat/chatbot-escalation-routing`, stacked on `feat/chatbot-focus` (#863); PR after #863 merges. APPROVED by owner 13 Sep 2026 on the lavish page (`.lavish/chatbot-escalation-routing.html`, revision 4).
UAC: `chatbot-escalation-routing-acceptance-criteria.md` (AC-11xx).
Predecessors: `PLAN-chatbot-focus-multi-domain.md` (lane 1, the dialogue state this lane's open questions live in), `PLAN-chatbot-turn-engine.md` S5 (the escalation lane port, hazards H26 / H27 / H37).
Issue: #865 (13 Sep 2026).

## Why

One contact (a Sorento dealer's purchaser) typed four escalation messages across three weeks
and got four different behaviours: a product list, a product list, an assignment to the wrong
team, and an assignment to the right team with no brand (whole-team round robin). Each miss
has a different line of code behind it, and each line is a guess with a fallback that hides
the miss. The escalation decision is spread over three files that disagree about precedence.

Measured on origin/main and the local prod copy, 13 Sep 2026:

| Turn (real) | Bot did | Cause |
|---|---|---|
| `ESCALTE TO MARKETING BIDET SEAT COVER FOR SRTWC60630-SH` (11 Sep) | 10 bidet taps listed | Parser right (`request_for_help`, team `marketing`). Previous turn left a suggest offer open; `head/output_exchange` read the code as a pick and retyped the turn `business_query` (the suggest-pick arm, one of 12 retype arms in that file). |
| `ESCALATE TO MARKETING` (11 Sep) | routed to purchasing | Parser stamped `is_escalation_confirmation: true` with nothing pending. `lanes/escalation._person_routing` checks that flag BEFORE the team word, returns None, assigns the carried team. `_catalogue_teams("marketing")` + `_clarify_over` exist and never ran. |
| `ESCALATE TO MARKETING FOR SRTWB8004` (21 Aug, n8n) | marketing_product, brand null | Brand carries only when this turn's team equals the previous turn's (`escalation_context` same-team rung; `tail/compile_state` "brand-company routing axes" block). Escalation almost always changes team. The lane never resolves the product it was given: `resolve_and_gate` is a raising stub (`escalation_services._not_live`, hazard H26). Next-assignee body takes `context_item["team"]` (inherited), not the narrowed team. |
| `MARKETING SRTWC6030-SH` (11 Sep) | 5 WC variants | No escalate verb; honest parse. Owner ruling D4: leave as is. |

Roster facts (prod copy): both companies have a `marketing_product` team set. Sorento tier 1 =
Tay Zhi Yang (tagged sorento, cabana, bravat, ... 11 brands), Kia Yee (tagged mocha),
Charissa Wang (untagged). 1,264 Mocha-brand products live under the Sorento company
(e.g. `MWC7625-SH-S10`). Brand is not company: company picks the team set (from the
CONTACT), brand narrows members (tagged with it plus untagged). Both rules already exist in
`next_assignee` / `user_service.get_next_assignee`; the lane just never sends a brand.

## Owner decisions (grill on the lavish page, 13 Sep 2026)

| id | decision |
|---|---|
| D1 | A help request that names a team is an escalation, full stop, whatever list the bot was waiting for. No head retype arm applies to it. The 8 Sep ruling (retypes for a help request with NO team) is untouched. |
| D2 | A family word ("marketing") asks which member team, EXCEPT when an open offer names one of the family's teams or the previous turn was already routed to one of them: then that team, no question. Ask only when nothing in the conversation points at one member. |
| D3 | No product named this turn: the previous turn's product and brand carry only when that turn was already routed to the team the escalation lands on (today's same-team rule, judged against the PICKED team, not the inherited one). Stock turn then "escalate to marketing" carries nothing; photo turn then "escalate to marketing" carries product and brand and asks nothing (D2). |
| D4 | `MARKETING <code>` with no escalate verb stays a product answer. No prompt change. |
| D5 | Lane stacks on `feat/chatbot-focus` (#863); rebased to main once #863 merges. Uses #863's open-question kinds (`product_pick`, `team_pick`, `company_pick`) and payloads; nothing new is invented for the deferred escalation. |
| D6 | Unknown product code AND a family word: did-you-mean first, then which team. |
| D7 | Company is the contact's, never the product's. Brand is the resolved product's. The confirmation flag is read only while an offer is open. |

## Design: three facts, one ladder each, all decided in the escalation lane

### Verb (one guard, head)

Source: parser `message_type == "request_for_help"`. In `head/output_exchange`, at the point
where `req_help` and `llm_team_raw` are hoisted, when both hold (`req_help` AND the raw team
word is non-empty), every later arm that assigns `o["message_type"] = "business_query"` (12
today: menu tap, date widen, tier-pick scope, member-offer filter, domain-present clobber,
suggest pick, switch-word retype, ...) is skipped for this turn. One boolean, checked at each
arm, or the arms gathered behind one `if not named_team_help:` block. The arms themselves do
not change.

`escalation.is_escalation_confirmation` from the parser is honoured only when
`offer_is_open(previous state)` is true. With nothing open it is ignored (set False).

### Team (lane, `_person_routing`)

Source: the parser's verbatim team word this turn, already kept in
`_parser_raw.routing.suggested_team`.

1. Word names exactly one catalogue team (`_catalogue_teams` returns one) -> that team.
2. Word names a family (several members): if the open offer's team is a member -> that team;
   else if the previous turn's `routing.suggested_team` is a member -> that team; else
   `team_pick` over the members (numbered quick replies; the existing `_clarify_over`).
3. No word: open offer + yes -> the offered team (unchanged); else the 8 Sep ruling holds
   (carried team, then default).
4. Ordering fix: the team-word check runs BEFORE the `is_escalation_confirmation` short
   circuit. A named team beats the flag.

### Brand and company (lane)

Source: the product named this turn, resolved through the business lane's gate
(`lanes/business/resolve_gate.run` via the lane's existing `resolve_and_gate` seam, wired
to `services.production_services`). This closes H26; the strict xfail tests
`test_fresh_entity_gate_calls_resolve` and `test_pending_marker_written_for_team_clarify`
flip to real tests, and their "live counterparts" asserting no resolve call are retired.

1. Product named and resolves to one row -> `brand_code` = that row's `display.brand.brand_code`.
2. Product named, not found -> the business lane's did-you-mean, armed as a `product_pick`
   open question whose payload carries `then: {escalate: {team_word, offer_team}}`. The
   `product_pick` handler, on a pick with that payload, resolves the brand and re-enters the
   escalation ladder at the team step (D6). A new ask instead of a pick clears the question
   (focus rule, no TTL) and no escalation happens.
3. No product named -> D3: carry the previous turn's product/brand when the previous turn's
   team equals the team the ladder lands on; else brand none (whole tier-1 pool).
4. Company: not set by the lane. `next_assignee` resolves it from the contact (existing
   precedence: body company_id > body company_code > contact's single company > default).
   Contact in two companies -> the existing `company_pick`.
5. Next-assignee body: `team_code` = the team the ladder landed on (not
   `context_item["team"]`), `agent_code` = that team's agent from the domain table
   (`derive_routing`'s map, inverted by team), `brand_code` from step 1 to 3.

The `same_team` gate in `escalation_context` is kept in spirit (D3) and evaluated against
the landed team: the function takes the landed team as a parameter and `_human_intervention`
re-runs it once the ladder has decided, so there is one ladder rather than two.

**Deviation, S5, corrected after review round 2 (captain's ruling, 13 Sep 2026).** The
five-key session (`contracts.SESSION_VAR_KEYS` = `focus`, `open_question`, `ideation`,
`access_levels`, `contains_flyer`, with `SessionVars(extra="forbid")` rejecting a sixth) means
the keys the D3 rung was written against - `routing`, `routing_brand`, `routing_companies`,
`routing_company`, `routing_roster_plan` - are never in a real turn's session at all. So the
rung could not fire, and the first version of this paragraph named a fallback that does not
exist: `query_brands` comes from `_stated_brands` (brand WORDS in the message, brand-hint
entities, access levels) and a resolved product's brand is never written there. Journey step 4
would have shipped with brand None, passing its test on a fixture shape no session can hold.

**What the carry reads instead, with no new slot and no new key.** When this turn names no
product, the lane takes the conversation's product from `focus.products` and the previous
turn's team from `derive_routing` over `focus.domains` - the team is a function of the domain,
by the same table the head's own chain uses, so a photo turn is `product_attachment` ->
`marketing_product` and a stock turn is `inventory` -> `warehouse`. When that team equals the
LANDED team, the lane resolves that focus product through the seam it already has (one extra
call, on this rung only, inside the same savepoint) and takes its brand; otherwise the brand
is none. `escalation.{_carried_products,_carried_team,_carry_ctx,_carried_brand}`, composed in
`_landed_item` below this turn's own product and above the legacy axes.

`escalation_context`'s rungs 2 and 3 keep their `routing_*` reads rather than being deleted:
`routing_source == "multi_company_unpicked"` is how the company-clarify arm is reached and it
is pinned end to end (`test_escalation_context_ladder`, `test_clarify_company_ask_always_in_
reply`, `test_s5_escalation_seams.py`), and a session written by n8n's own spine still carries
those keys while both halves of the migration are live. They are a documented no-op on a
CRM-written session.

`tail/compile_state`'s brand-company axes block and its `fresh` flag are NOT changed, for the
same measured reason: every key that block writes is dropped before the session is written, so
the change would alter a value no later turn reads inside a block 224 `compile-current-state`
captures grade. The trigger to revisit: any of those keys returning to `SESSION_VAR_KEYS`.

### Found on the console pass (13 Sep 2026, owner, stack at d49a8f929)

Journey step 5 failed end to end: "photo for SRTWB8004" offered the Marketing Product team,
"yes" was answered, and the conversation was assigned to CUSTOMER SERVICE.

**Root cause is #863's, not this lane's, and it is wider than this journey: a YES OR NO ANSWER
WAS NOT BEING RESOLVED AT ALL under the promoted parser.** `engine._resolve_open_question` reads
`answers_open_question`, a prompt-v3 key, and production runs v1; the v1 fallback beside it only
reads `reference_positions`, which a bare yes does not carry; and the legacy reader that used to
catch it (`_team_clarify_pick`, keyed on `pending.kind` / `selection_context`) went with the
five-key session. So `dialogue/open_question._team_pick`'s yes arm - which returns exactly the
offered team - was unreachable, the head's routing chain fell to its hard default, and the lane
assigned what it was handed. Measured on the two persisted turns; neither the D7 clamp (an offer
IS open, so the flag stands) nor the S2 reorder (no team word) reaches it, and the fix needed no
change in the lane.

**Fixed in `engine.py`'s v1 fallback** (this lane, because the two are stacked): a question whose
`expects` is `yes_no` is answered by the parser's own `is_affirmative` boolean, positions still
winning. That also means the question is CONSUMED, where before it stayed open after being
answered. Every yes/no offer is affected, not just this journey step: flag it on #863 if the two
lanes are ever split.

A second, narrower gap fell out of the same audit and is fixed beside it: the family-word
narrowing read the team THIS turn inherited as a stand-in for the previous turn's, which on a
five-key session is the hard default. It reads the carried DOMAIN re-derived
(`escalation._carried_team`, already D3's source) instead.

**Second pass, same day, same class one lane over (b6e108634).** "SRTWT2643 photo" missed, and the
miss lane's combined reply offered three codes AND "would you like me to escalate to marketing
product team?" with a Yes escalate button - but the `product_pick` it armed recorded only the
codes, and `engine._resolve_open_question` would not let a picker resolve on a yes. So the yes
answered nothing and the turn was assigned the chain's hard default: offered Marketing Product,
got Customer Service. Fixed as one mechanism with the deferral S4 already had: the question now
carries `then: {escalate: {offer_team}}` (written only when the escalate button really went out,
by the same `answer.offer_escalation_team` the sentence uses), the engine lets such a question
resolve on `is_affirmative`, and `_product_pick` grows a yes arm (accept, to the offered team)
and a no arm (the existing decline, which clears it).

A PICK still answers the product rather than escalating, and that is the one subtlety: two
deferrals ride `then.escalate`, so the lane's own - which always writes the `team_word` KEY, null
included - is told from the miss lane's offer by MEMBERSHIP of that key, not by its truthiness.
Both halves are #863's: the five-key session dropped the legacy readers that used to catch a
yes, and the miss ladder never recorded what its own copy promised.

### Not built, with the reason

- No brand -> team table: member brand tags already do it (36 rows).
- No new open-question kind: `product_pick` with a payload, `team_pick`, `company_pick` exist.
- No rewrite of the 12 retype arms: one guard in front of them.
- No parser prompt change: v11 already emits the team word verbatim (D4 chosen "leave as is").
- No text matching anywhere (D11): every decision reads parser output, resolver output or
  persisted state.
- Bare "escalate" with no team and no offer keeps the carried team (8 Sep ruling).

## Slices (one lane, one coder, commits on the lane branch)

| slice | content | tests that go green |
|---|---|---|
| S1 | Head guard (D1) + confirmation flag only while an offer is open | T1 (lane reached), T2 |
| S2 | `_person_routing` reorder + family narrowing by offer / previous team (D2) | T2, T6, T7, T9b, T12, T13, T14 |
| S3 | Lane resolves this turn's product (H26 closed); brand in the body; landed team + agent in the body (T8) | T3, T4, T8, T10 |
| S4 | Not found -> `product_pick` with deferred escalation; pick re-enters the ladder (D6) | T1b, T1c, T1d |
| S5 | D3 carry against the landed team (lane; compile_state half not needed, see the deviation above) | T9, T9b |
| S6 | Replay fixtures from the four real turns + the Mocha turn; divergences registered; console check | replay green |

Phase 1 (frontend-first mock) does not apply: no UI changes. The console already shows the
lane's stages; the PR description says so.

## Lane

- Branch `feat/chatbot-escalation-routing` from `feat/chatbot-focus` at 49492ca6c (13 Sep).
  Worktree `.claude/worktrees/chatbot-escalation-routing`.
- Tester branch `test/chatbot-escalation-red`, worktree `chatbot-escalation-red`, merged by
  the coder (the #863 pattern).
- Test DB `sorento_ai_automation_escal` (clone of `sorento_ai_automation_focus`, already at
  migration 517). The lane `.env` points `DATABASE_URL` at it (`.env` beats env vars).
- No migration expected. If one is needed it parents on #863's head (`517_chatbot_session_5key`)
  and `./scripts/alembic-reparent.sh` runs at the pre-PR gate.
- Pre-PR gate: merge `feat/chatbot-focus` (then main after #863 merges), single alembic head,
  replay green, three targets green.
