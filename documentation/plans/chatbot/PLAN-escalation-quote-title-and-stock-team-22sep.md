# PLAN: escalation quote fallback, SLA comment timestamps, stock question always routes to warehouse

Status: small fix track, review READY, awaiting PR (lane `fix/chatbot-reply-quote-and-team`, worktree `sorento_crm-ticket-reply-team`)
UAC: `escalation-quote-title-and-stock-team-22sep-acceptance-criteria.md`
Owner rulings: R1 (22 Sep 2026) drop the ` reply to:` suffix when the quoted message has neither text nor title; R6 (22 Sep 2026) a stock question is always suggested to the warehouse team, no rung override; R7 (23 Sep 2026) THIS turn's own domain team outranks a PREVIOUS turn's carried team - its own clause "an OPEN offer's own carried team still outranks both" is SUPERSEDED BY R9 for open offers (an open offer wins only on an actual acceptance, never unconditionally); R8 (23 Sep 2026) AC-EQ-15's first-turn default table signed off; R9 (owner ruled 23 Sep 2026) = option (i): an open offer's own carried team wins only when THIS turn is answering the offer (yes / escalation confirmation / a pick landing on it) - a fresh question in another domain gets its own domain team instead.

## Journey

Dealer quotes the bot's "Would you like me to escalate to purchasing team?" message and replies "Yes". Staff opens the ticket in the CRM drawer.

Today: header reads `Yes reply to: undefined`, the internal Respond.io note reads `routed to you at [object Object]`, and the ticket sits with the purchasing team although the dealer asked about stock.

After: header reads `Yes reply to: Would you like me to escalate...`, the note carries Malaysia-time timestamps, and the offer + assignment name the warehouse team.

## Defects (all in `sorento_crm_backend/`)

1. `app/services/chatbot/lanes/escalation.py:1245-1247` `_input_message` reads `replyTo.message.text` only. Respond.io delivers a quoted quick-reply message under `title`. `engine.py:321-323` already falls back to `title`.
2. `app/services/chatbot/lanes/escalation_services.py:105-107` `_sla_create` hands back `datetime` objects; `escalation.py:440-456` `_malaysia` calls `jsc.js_string(datetime)`, which renders `[object Object]`. Tests stub ISO strings so the path was never exercised.
3. `app/services/chatbot/lanes/business/answer.py:1120` `_CROSSDOMAIN_RUNG_TEAM = {"purchase_order": "purchasing"}` and `:1425-1444` `_apply_crossdomain_rung` rewrite `parser["routing"]["suggested_team"]` and `block["team"]` to `purchasing` whenever the PO rung answers a stock-origin ask. Parser prompt and `turn/policy_rows.py:141` already say inventory → warehouse.

## Fix

1. `_input_message`: quoted body = `text` if truthy else `title`; if neither is truthy, append nothing. Update the docstring (it currently documents the n8n parity choice).
2. `_sla_create`: return `initiated_at` / `due_at` / `due_at_resolution` as ISO-8601 strings (`.isoformat()` when the value is a `datetime`, else pass through). `_malaysia` unchanged.
3. Delete `_CROSSDOMAIN_RUNG_TEAM` and the override block in `_apply_crossdomain_rung`. The offer sentence and routing keep the question-origin team from `crossdomain_zeroset` (`answer.py:489`). Incoming-origin asks are unaffected (incoming → purchasing already).

## Tests (write first, red, then green)

Files: `tests/chatbot/test_s5_escalation_seams.py` (or a sibling), `tests/chatbot/test_crossdomain_ladder.py`.

- AC-EQ-1..3 quote fallback; AC-EQ-4 datetime comment; AC-EQ-5..7 team.
- Flip the five assertions that pin "purchasing wins": `test_crossdomain_ladder.py:217-238` (`TestAC921...`), `:390-398` (`test_rung_found`), `:757-769`, `:894-933` (incoming-origin PO-rung tests: check whether they assert the team; incoming-origin stays purchasing so they may need no change), `:1197-1212`.

## Fix round 1 (reviewer, 22 Sep 2026)

Reviewer measured that AC-EQ-6/8's MISS branch was still wrong in production after the
first pass: captured traffic shows the LLM parser names no team on 214/218 inventory
turns, and `lanes/business/answer.py::not_found_error_message`'s own `team =
_pretty_team(suggested_team or "customer_service")` (2863-2864) falls straight to the
generic literal for a null `suggested_team` - deleting `_CROSSDOMAIN_RUNG_TEAM` alone
does not fix that half.

Traced further than the reviewer's own citation: `routing.suggested_team` is very
rarely still null by the time `not_found_error_message` reads it, ON THE
`engine.run_turn` PATH - `turn_runtime.lane_parse_output`'s own chain (accepted_team
-> pending.team -> `_prior_suggested_team` -> `DEFAULT_SUGGESTED_TEAM`) already fills
a null verdict with the flat "customer_service" literal, early, in `engine.py`,
before any composer on THAT path sees the parser dict. That is the actual
interception point for a real turn - `not_found_error_message`'s own fallback (added
anyway, belt-and-braces) still fires for a caller that reaches `complete_answer`
directly, bypassing `run_turn`/`lane_parse_output` entirely, with a bare `parser`
dict carrying no `routing` key at all - `test_s6c_answer_lane.py::
TestErrorArmRendersTheMissLane.test_the_error_arm_reaches_the_miss_renderer` is
exactly that shape and now pins it directly (fix round 2; `test_warehouse_entity.py`
does not reach this branch - it passes `domain_hint = "procurement"` with real access
attributes, not a null-routing miss - the earlier citation there was wrong). Fixed at
the root: `lane_parse_output` takes an optional `policy` (threaded from `engine.py`,
which already holds one) and, when nothing more specific named a team, falls back to
`policy.domain(domain_hint).escalation_team_code` before the hard default - AC-EQ-12
to AC-EQ-14. `stock_parse`/the D7 fixture in `test_foundre_rung_end_to_end.py` are
reverted to the captured null-routing shape so the e2e tests measure production, not
a stub that always names a team.

`tests/chatbot/test_turn_replay.py` (the S6 replay gate, full corpus) passes
unchanged - case-038/case-039 (the two cases with `routing.suggested_team: null` and
a recorded "purchasing" escalate offer) carry no `_pin_text` flag, so their `text`
field is never graded; no `DIVERGENCES.md` entry is needed for them.

## Fix round 3 (owner ruling R7 = option (a), R8 signed off, 23 Sep 2026)

Mechanical only. `turn_runtime.lane_parse_output`'s routing-fallback chain reordered:
accepted team > open-offer team (`pending.team`) > THIS turn's own domain team
(`policy.domain(domain_hint).escalation_team_code`) > a PREVIOUS turn's carried team
(`_prior_suggested_team`) > the hard default (`customer_service`) - the domain fill
now outranks a stale prior-turn carry (was the reverse in fix round 1/2). An explicit
parser team still wins over everything, unchanged - the fallback chain only runs when
`routing.suggested_team` is null. AC-EQ-16..19 pin the four orderings directly against
`lane_parse_output` (verified red against the pre-R7 ordering, green restored).
AC-EQ-15's table is now owner-signed (R8) - dropped the "sign-off pending" flag.
`PENDING-LIVE-RERUN.md`'s case-038/039 note extended to cover
`console/case-025-d7-an-incoming-ask-on-a-zero-stock-code-climbs-to-the-po-rung.json`
turn 0 (a stock ask that recorded "purchasing", now stale under R6/R7 -> "warehouse")
- turn 1 (the D7 incoming climb) claimed unchanged here, still "purchasing" either
way. **Corrected in fix round 4: this was wrong**, see below.

## Fix round 4 (mechanical - an owner ruling on open-offer precedence, R9, is pending)

Reviewer measurement corrects fix round 3's claim about case-025 turn 1: it is
UNCHANGED, still "purchasing" on HEAD - measured directly, it renders "warehouse".
Turn 0's stock offer leaves an OPEN `team_pick` pending with `team=warehouse`;
`lane_parse_output`'s `pending.team` arm supplies that unconditionally for turn 1,
with no read of whether turn 1 is actually accepting that offer or asking something
fresh (D7's own climb IS a fresh question, not an acceptance) - `prior_session` is
`None` throughout this case, so R7's domain-vs-carry reorder never engages on it at
all. AC-EQ-17's UAC line and test docstring wrongly attributed case-025 as its own
recorded shape - corrected to describe AC-EQ-17 as a direct unit shape only;
case-025 turn 1 is AC-EQ-18's shape (an open offer answering unconditionally), and
its own staleness (if any) hangs on the still-open R9 ruling below.
`PENDING-LIVE-RERUN.md`'s case-025 note rewritten to say turn 1 is ALSO stale, via
the open-offer arm - not "unchanged".

`make_tool_runner`'s own `lane_parse_output` call (S6, fix round 2) was described as
parity with `engine.py`'s own call - it is not: it passes `policy` but never
`pending`/`prior_session`, so that per-domain fetch context's own
`routing.suggested_team` can only ever be the domain rung, never an open offer or a
prior-turn carry, and genuinely disagrees with the turn's real `ctx.parse.output` on
a shape like case-025 turn 1 (fetch context "purchasing" vs parse output
"warehouse", measured). Not fixed - reworded the comment there (and this note) to
"domain rung only; the fetch context never sees pending or prior, and nothing reads
its team" instead of claiming parity. `lane_out` feeds tool ARGS only (access
levels, date filters, entities) - no escalate sentence or pending write reads it, so
the disagreement is inert today, not a live bug.

**Open ruling, R9, do not implement yet:** should a FRESH question (not an
acceptance) over a still-open offer re-derive its team from its own domain, rather
than inheriting the open offer's team unconditionally? AC-EQ-20
(`xfail(strict=True)`, reason "awaiting owner ruling R9") pins the CURRENT behaviour
as red-when-fixed: open `team_pick` pending team=warehouse from a stock offer,
current turn `domain_hint = incoming`, routing null, not an acceptance -> expects
`purchasing`, currently renders `warehouse`. The `pending.team` arm in
`lane_parse_output` stays untouched until R9 lands.

## Fix round 5 (owner ruling R9 = option (i), 23 Sep 2026)

`lane_parse_output`'s `OFFER_KINDS` pending arm (`pending.team`) is now gated on a
new `_pending_offer_answered(pending, verdict)` helper - the SAME accept signal
`_accepted_pending_field`'s own `escalate_offered_roster` branch already reads
(SRTSC07 review round 2, `turn_runtime.py:473-487`): a bare "yes"
(`is_affirmative is True`), an escalation confirmation
(`escalation.is_escalation_confirmation is True`), or a numbered pick landing on
one of the pending's own options - vetoed by a decline or a negation. When the
turn is NOT an acceptance, the pending arm is skipped and the chain falls through
to THIS turn's domain team (R7) > prior carry > the hard default. The
`accepted_team` arm and the verdict-named-team arm are untouched. Docstring chain
rewritten: accepted > named > pending-if-answering (R9) > domain (R6/R7) > prior >
literal.

AC-EQ-20 flipped from `xfail(strict=True)` to a normal green test. AC-EQ-18
REWRITTEN (it was written under option (ii) in fix round 3/4, where the open offer
won unconditionally regardless of acceptance) - same setup, but the verdict names
no acceptance signal, so under R9 it now expects `warehouse` (this turn's own
domain), not `purchasing`. AC-EQ-21/22 added: a real acceptance (bare "yes",
escalation confirmation, or a landing pick) still routes to the open offer
regardless of this turn's own domain.

One further test needed the same correction once found by the full battery:
`tests/chatbot/test_escalation_agent_carry.py:1051`
(`TestAC1795TeamChainInLaneParseOutputUnchanged.
test_ac_1795_team_precedence_chain_is_unaffected_by_the_agent_carry`, assertion at
line 1088) - its `verdict_in` carries no acceptance signal either, so its own
`suggested_team` assertion flipped from `"purchasing"` (the open offer, old
unconditional inheritance) to `"warehouse"` (the prior session's own carry, since
`policy` is not passed to this call and the domain rung cannot resolve). The
test's actual purpose - the AGENT field rides independent of the team chain - is
untouched, only the incidental TEAM value the old chain happened to produce.
`test_rearch_r12_handpass12_d.py` and `test_foundre_rung_end_to_end.py` were
re-checked and need no flip: neither seeds an `OFFER_KINDS` pending
(`team_pick`/`company_pick`/`member_offer`) - their own open questions are
`product_pick`/`customer_pick`, both `ROSTER_KINDS`, which the pending-team arm
(gated or not) never reads at all.

`replay_turns/console/case-025-d7-...` re-measured directly (a temporary debug
print in `test_turn_replay.py`, added and reverted, never committed): turn 1 now
renders `escalate to purchasing team?`, exactly the recorded value - no longer
stale. Turn 0 stays stale (R6/R7, unaffected by R9).
`PENDING-LIVE-RERUN.md` updated accordingly.

## Fix round 6 (S10, "simplest thing that works" - lane final round)

Reviewer kill test: deleting the ENTIRE `OFFER_KINDS` pending arm in
`lane_parse_output` (fix round 5's `pending.team` read, gated by
`_pending_offer_answered`) plus the helper itself leaves the full suite green
except AC-EQ-21/22, because whenever a turn genuinely accepts an offer
`turn/apply.py::_answer_pending` (:285, :675) already computes that exact
judgement and stamps it onto `trace.team`, which `engine.py:1461` passes straight
in as `accepted_team` - the chain's own FIRST read, above where the deleted arm
sat. Two copies of one judgement. Deleted the arm and `_pending_offer_answered`
entirely; chain is now accepted > named > this turn's domain (R7) > prior carry >
the hard default. Rewrote the docstring and the inline comment to state the chain
and cite R9 as satisfied by `accepted_team` alone, not a second gate.

AC-EQ-20 kept (it already reaches this outcome via the domain rung - `pending`
alone, with no `accepted_team`, is now simply inert). AC-EQ-21/22 re-pointed to
the PRODUCTION shape: they now pass `accepted_team` directly (what `engine.py`
actually hands this function on a real acceptance) instead of a bare `pending=`
with no acceptance signal, a call shape `engine.run_turn` never produces.
AC-EQ-18 duplicated AC-EQ-20 once the arm was gone (byte-identical) - retired,
folded into AC-EQ-20, noted in the UAC. Ran the kill myself: temporarily
short-circuited the `accepted_team` read (`if False and accepted_team:`), AC-EQ-21
and AC-EQ-22 both went red (AC-EQ-22's first draft accidentally used a
domain/team pair where the domain fallback ALSO produced "warehouse", masking the
kill - fixed by picking a domain whose own team differs from the accepted team
under test); AC-EQ-16/17/19/20 stayed green, as expected since none of them touch
the deleted arm. Restored, all six green again.

`replay_turns/console/case-025-d7-...` turn 1 re-confirmed unaffected by this
round (still `purchasing`, not stale) - the deleted arm and `accepted_team` reach
the identical outcome for a fresh question (neither supplies a team), so nothing
here changes what that case renders.

Nits: renamed `TestAC1795TeamChainInLaneParseOutputUnchanged` (in
`test_escalation_agent_carry.py`) to `TestAC1795TeamChainFallsToThePriorCarryUnaffectedByTheAgentCarry`,
naming the value it actually pins ("warehouse", the prior carry) rather than the
retired "pending wins" behaviour its old name described. Fixed a garbled sentence
fragment at `PENDING-LIVE-RERUN.md`'s case-025 note (a stray concatenation of the
UAC filename into running prose). R7's "open offer still outranks both" clause
marked superseded by R9 in this plan's own rulings line.

## Out of scope

Frontend header rendering (lane `fix/sla-chat-panel-layout`), keep-assignee-on-resolve (lane `fix/sla-keep-assignee-on-resolve`).
