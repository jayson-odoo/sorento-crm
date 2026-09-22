# UAC - Escalation acceptance carries the agent half of routing

Plan: `PLAN-chatbot-escalation-agent-carry.md`. Numbering continues from AC-1783.

All ACs are backend, pytest, `tests/chatbot/`. "Wire body" = the dict
`lanes/escalation._next_assignee_body` builds for `/external/next-assignee`.

## Acceptance (the bug)

- **AC-1784** Turn 1 is an `incoming` ETA miss whose answer carries the roster escalate
  offer ("reply 'yes' to escalate to purchasing team"), parsed with
  `routing = {suggested_team: "purchasing", suggested_agent: "incoming_stock_enquiries"}`.
  Turn 2 is `yes`, parsed with `routing = {suggested_team: null, suggested_agent: null}`.
  The wire body of turn 2 has `agent_code == "incoming_stock_enquiries"` and
  `team_code == "purchasing"`. (Engine replay through the stubbed parser; today
  `agent_code` is `"general_enquiries"` - the failing assertion.)
- **AC-1785** Same two turns, but turn 1's offer is a single-team `team_pick`
  (`turn/compose._team_pick_question` with one missed domain): turn 2's
  `routing.suggested_agent` is the minting turn's agent, not the default.
- **AC-1786** Multi-team `team_pick` (two missed domains with different teams and
  different agents): picking option 2 by number carries option 2's agent, not option 1's
  and not the default.

## Precedence

- **AC-1787** The parser's own non-null `suggested_agent` on the acceptance turn is never
  overridden by the carried one (a customer who says "yes, packing list please" and the
  parser names `incoming_stock_enquiries` keeps it; a parser naming `order_enquiries`
  keeps that too).
- **AC-1788** No offer pending, parser null: `suggested_agent` comes from the prior
  session's `variables.routing.suggested_agent` (same nest `_prior_suggested_team` reads,
  both session shapes: `session_vars.variables` and bare `variables`).
- **AC-1789** No offer, no prior routing, parser null: `DEFAULT_SUGGESTED_AGENT`
  (`general_enquiries`) - today's behaviour, unchanged. Existing
  `test_rearch_s6_handpass1_findings.py` tests 2b stay green.
- **AC-1790** A session whose routing nest is unreadable (not a dict, blank string,
  missing) reads as "nothing carried", never raises.

## Access

- **AC-1791** The access check on the acceptance turn is made against the CARRIED agent
  (`incoming_stock_enquiries`), not the default: a contact granted only
  `incoming_stock_enquiries` is allowed on the "yes" turn; a contact granted only
  `general_enquiries` is denied on it. (The carry lands in `with_routing_agent_default`,
  before the access read - this AC pins the ordering.)

## Offer payload

- **AC-1792** The roster escalate offer and the single-team `team_pick` store the agent on
  `pending.payload["agent"]`; a multi-team `team_pick` stores it on each option's
  `payload["agent"]` beside `payload["team"]`; the hold option ("No it's okay") carries
  `agent: None`.
- **AC-1793** A pending minted on a turn whose verdict had no agent stores `agent: None`
  and the acceptance falls through to the prior-session / default chain (no KeyError, no
  empty-string agent on the wire - `/external/next-assignee` 400s on an empty
  `agent_code`).

## Regression

- **AC-1794** `SLA` body (`_sla_body`) on the acceptance turn carries the same
  `agent_code` as the next-assignee body (one source, `routing.suggested_agent`).
- **AC-1795** The team chain in `lane_parse_output` is byte-for-byte unchanged: existing
  `test_s5_escalation_lane.py` and `test_turn_replay.py` suites stay green; replay
  fixtures under `tests/chatbot/replay_turns/console/` that pin a `suggested_agent` still
  match.
