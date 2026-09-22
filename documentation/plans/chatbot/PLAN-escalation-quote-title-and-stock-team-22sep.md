# PLAN: escalation quote fallback, SLA comment timestamps, stock question always routes to warehouse

Status: small fix track, fix round 3 (R7) done, awaiting review (lane `fix/chatbot-reply-quote-and-team`, worktree `sorento_crm-ticket-reply-team`)
UAC: `escalation-quote-title-and-stock-team-22sep-acceptance-criteria.md`
Owner rulings: R1 (22 Sep 2026) drop the ` reply to:` suffix when the quoted message has neither text nor title; R6 (22 Sep 2026) a stock question is always suggested to the warehouse team, no rung override; R7 (23 Sep 2026) THIS turn's own domain team outranks a PREVIOUS turn's carried team, but an OPEN offer's own carried team still outranks both; R8 (23 Sep 2026) AC-EQ-15's first-turn default table signed off.

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
- turn 1 (the D7 incoming climb) is unchanged, still "purchasing" either way.

## Out of scope

Frontend header rendering (lane `fix/sla-chat-panel-layout`), keep-assignee-on-resolve (lane `fix/sla-keep-assignee-on-resolve`).
