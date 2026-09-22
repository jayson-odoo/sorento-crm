# PLAN - Escalation acceptance carries the AGENT half of routing, not only the team

Status: implemented, awaiting review (small fix track)
Domain: chatbot
Branch: `fix/chatbot-escalation-agent-carry` (worktree `sorento_crm-escalation-agent-carry`)
Base: `origin/main` 2280975f9
UAC: `chatbot-escalation-agent-carry-acceptance-criteria.md`

## Observed (prod transcript, 22 Sep 2026, contact Jennifer)

1. `incoming container SRTSC07` -> parser routes `domain incoming` -> team `purchasing`,
   agent `incoming_stock_enquiries` (parser prompt line 534). Answer ends with the roster
   offer "Reply with a number to check its incoming, or reply 'yes' to escalate to
   purchasing team." (`lanes/business/answer.py:3930`).
2. `yes` -> escalated. Assigned to Chew Hong, whose only `purchasing` link is
   `(agent general_enquiries, team "Purchasing - Product, Stock Inquiry")`. The correct
   pool is `(agent incoming_stock_enquiries, team purchasing)` = "Purchasing - Packing
   List" / "Purchasing - Incoming" (Lucas, Jereen Tee).

## Cause (read, not guessed)

`/external/next-assignee` resolves a pool by the PAIR `(agent_code, team_code)`
(`app/api/v1/external/next_assignee.py:147-183`). The escalation lane sends
`agent_code = ctx.parse.output.routing.suggested_agent` and `team_code = context_item.team`
(`lanes/escalation.py:1140-1156`).

On the acceptance turn ("yes") the two halves are treated differently:

- **team** is carried: `turn_runtime.lane_parse_output` (`turn_runtime.py:566-572`) takes
  the accepted offer's team, then `pending.team`, then `_prior_suggested_team(session)`,
  then `DEFAULT_SUGGESTED_TEAM`.
- **agent** is NOT carried: a bare "yes" names no domain, so the parser emits
  `suggested_agent: null` (prompt line 544), and `turn_runtime.with_routing_agent_default`
  (`turn_runtime.py:422-441`, called at `engine.py:1399`) stamps
  `DEFAULT_SUGGESTED_AGENT = "general_enquiries"` (`contracts.py:177`). Nothing reads the
  offer or the prior turn.

Result: `(general_enquiries, purchasing)` -> the wrong tier-1 team.

## Fix (one seam)

Carry the agent the way the team is carried, from the same source, and only when the
parser named none THIS turn:

1. **Offer write, NINE mint sites** (the original plan named two; implementation and
   reviewer round 1 found seven more - every place that mints a pending an escalation
   acceptance can answer stores the minting turn's `routing.suggested_agent` on
   `payload["agent"]`, single-team/top-level or per-option beside `payload["team"]`, the
   hold option always `agent: None`):
   - `turn/compose.py::_team_pick_question` (single-team top-level payload; multi-team
     per-option) - reached only by a genuine MULTI-domain miss.
   - `answer_bridge.py::_miss_question`'s did-you-mean/require-specific roster arm
     (combined-member and roster-alone, per-option `escalate_offered` payload).
   - `answer_bridge.py::_miss_question`'s escalate-catalog arm (company-clarify and bare
     "Yes" branches) - the THIRD mint site, found in implementation: this is the one a
     real SINGLE-domain fetch miss actually goes through (`via_fetched_empty` ->
     `answer_bridge.answer_for` -> `_miss_question`), not `_team_pick_question`.
   - `answer_bridge.py::_miss_question`'s member-offer arm (top-level payload) -
     reviewer round 1, SHOULD-2.
   - `engine.py::_question_offered`'s team clarify arm (`_option_payload`'s "team" branch,
     per-option, reads `ctx` directly) - SHOULD-2.
   - `engine.py::_question_offered`'s company clarify arm (top-level payload) - SHOULD-2.
   - `engine.py::_question_offered`'s member-offer arm (top-level payload) - SHOULD-2.
   - `engine.py::_question_offered`'s escalate-catalog arm (top-level payload, the twin of
     `answer_bridge.py`'s own bare-"Yes" branch) - SHOULD-2.
   - `turn/compose.py::compose`'s roster re-arm (a miss over a STILL-OPEN roster that
     already carries an escalate offer keeps its own agent first, else this turn's -
     `carried.payload.get("agent") or ctx.suggested_agent`) - SHOULD-2.
   `Pending` already has `payload: dict`; no dataclass field is added.
2. **Acceptance read.** In `turn_runtime.with_routing_agent_default` (the one seam every
   turn passes before the access read - keep it there so access is checked against the
   carried agent, not the default), fill `routing.suggested_agent` in this order when the
   parser's raw value is empty: `_accepted_pending_agent(pending, verdict)`, then
   `DEFAULT_SUGGESTED_AGENT`. The function needs `pending` (`state_in.pending`, loaded at
   `engine.py:1225`, so it is available at line 1399) as an extra keyword argument; every
   other caller keeps working with it absent. A `session=` keyword and its own
   `_prior_suggested_agent` fallback were part of the first round and REMOVED in review
   round 1 (SHOULD-4): no writer in this codebase ever produces
   `variables.routing.suggested_agent` for a previous turn to carry - unlike the team
   half, which `_prior_suggested_team` reads off a nest a real writer DOES still produce.
3. **Gate** (SHOULD-1). `_accepted_pending_agent` only reads a pending that is actually
   ACCEPTABLE as an escalation, the same condition `turn/apply.py:691` uses: `pending.kind
   in OFFER_KINDS or pending.payload.get("escalate_offered") is True`. Without it a plain
   roster pending with no escalate offer attached could still supply an agent while
   `lane_parse_output`'s own team chain (which gates on `OFFER_KINDS` alone for that same
   read) left the team at its default - the two halves of the pair disagreeing.
4. **Member-option fall-through** (SHOULD-3). A numbered pick that lands on a MEMBER
   option (a combined roster+CS offer's own member half - no `payload["agent"]`, no
   `payload["hold"]`) falls through to the pending's own top-level agent instead of
   returning `None` outright; only the explicit hold option or an option that actually
   names an agent short-circuits the read.
5. A parser that DID name an agent this turn is never overridden - the carried value only
   fills a null.

Nothing else moves: `lane_parse_output`'s team chain, `_next_assignee_body`, `_sla_body`,
the access check and the prompt are untouched.

## Non-goals

- No change to `ESCALATION_TEAMS` / `SUGGESTED_TEAM_OPTIONS` (the dropdown holds
  agent_teams link codes; "Purchasing - Packing List" is reachable under `purchasing` once
  the agent half is right).
- No prompt edit. No new session key. No migration.

## Tests (tester writes first, `tests/chatbot/`)

Pure-python where possible (`with_routing_agent_default` takes dicts); one engine replay
through the stubbed parser to prove the wire body. See the UAC for the list; each AC maps
to one test name.

Run: `SORENTO_ENV_FILE=.env.ci-tests venv/bin/pytest tests/chatbot/<file> -q` from the lane
backend (`sorento_ci` is the private test DB; the primary venv is symlinked in).

## Verification

No screen changes: pytest is the gate. Journey runner / console check not required for a
routing-pair fix that no UI renders; the prod transcript above is the reproduction and the
replay test is its record.
