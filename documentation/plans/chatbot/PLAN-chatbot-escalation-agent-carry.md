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

Carry the agent the way the team is carried, from the same two sources, and only when the
parser named none THIS turn:

1. **Offer write.** When a pending offer that can be accepted into an escalation is minted
   (the roster escalate offer in `lanes/business/answer.py` around line 3930, and the
   `team_pick` offers in `turn/compose.py:72-115`), store the minting turn's
   `routing.suggested_agent` on the pending's `payload["agent"]` (single-team) or on each
   option's `payload["agent"]` (multi-team, beside the option's own `payload["team"]`).
   `Pending` already has `payload: dict`; no dataclass field is added. Implementation found a
   THIRD mint site this list did not name: `answer_bridge._miss_question`'s own
   "escalate-catalog" arm (its single-team, no-roster branch) is the one a real
   SINGLE-domain fetch miss actually goes through (`via_fetched_empty` ->
   `answer_bridge.answer_for` -> `_miss_question`) - `turn/compose.py::_team_pick_question`
   is only ever reached by a genuine MULTI-domain miss, where `answer_bridge` never runs at
   all. Both needed the same `payload["agent"]` carry.
2. **Acceptance read.** In `turn_runtime.with_routing_agent_default` (the one seam every
   turn passes before the access read - keep it there so access is checked against the
   carried agent, not the default), fill `routing.suggested_agent` in this order when the
   parser's raw value is empty: the accepted option's `payload.agent` / the pending's
   `payload.agent` (the customer picked it THIS turn), then `_prior_suggested_agent(session)`
   (mirror of `_prior_suggested_team`, same nest `variables.routing.suggested_agent`), then
   `DEFAULT_SUGGESTED_AGENT`. The function needs `pending` (`state_in.pending`, loaded at
   `engine.py:1225`, so it is available at line 1399) and `session_block` as extra keyword
   arguments; every other caller keeps working with them absent.
3. A parser that DID name an agent this turn is never overridden - the carried value only
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
