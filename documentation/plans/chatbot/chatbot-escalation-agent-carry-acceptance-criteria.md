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
- **AC-1788** retired: the tail never writes `variables.routing` for the agent half (no
  writer in this codebase produces that nest - `turn/tail.py`'s five session keys hold no
  such block, and `overwrite_for_contact` replaces rather than merges), so the
  prior-session rung `_prior_suggested_team` keeps for the team half has no agent-half
  counterpart and was removed rather than read a nest nothing ever writes (reviewer round
  1, SHOULD-4). The two tests this AC covered were deleted.
- **AC-1789** No offer pending, parser null: `DEFAULT_SUGGESTED_AGENT`
  (`general_enquiries`) - today's behaviour, unchanged. Existing
  `test_rearch_s6_handpass1_findings.py` tests 2b stay green.
- **AC-1790** retired alongside AC-1788 (reviewer round 1, SHOULD-4): it pinned the
  never-raise contract of the SAME retired session-shape reader (`_prior_suggested_agent`,
  six parametrized session shapes). `_accepted_pending_agent`'s own never-raise contract
  (a malformed pending/verdict shape, `try/except` around `picked_positions`) is exercised
  incidentally by AC-1790's sibling tests already in this file (AC-1793's hand-built
  pending, AC-1798's fall-through) rather than by a dedicated parametrized case, since a
  `Pending` only ever reaches this function through `turn_runtime.load_state`'s own
  `from_wire`, which already guarantees the shape.

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
- **AC-1793** A HAND-BUILT pending (a unit test's own fixture, `payload={"agent": None}`)
  falls through to the default chain cleanly (no KeyError, no empty-string agent on the
  wire - `/external/next-assignee` 400s on an empty `agent_code`). Note (NIT-5, reviewer
  round 1): an ENGINE-minted pending never actually stores `agent: None` in practice - by
  the time any mint site reads `routing.suggested_agent`, `with_routing_agent_default` has
  already run for that turn and filled the hard default in, so a real mint's own top-level
  payload always carries a real agent code. `agent: None` is reachable only by hand-building
  a pending directly, which is exactly what this AC's test does.

## Gate and fall-through (reviewer round 1)

- **AC-1796** A roster pending (`product_pick`, not in `OFFER_KINDS`) with NO
  `escalate_offered` flag carries no agent at all, even when its payload happens to hold
  one: `with_routing_agent_default` falls straight to `DEFAULT_SUGGESTED_AGENT`, matching
  `lane_parse_output`'s own team chain, which also does not read that pending (SHOULD-1).
- **AC-1797** The SAME roster pending WITH `escalate_offered: True` DOES carry its agent
  (the gate's other side - `pending.kind in OFFER_KINDS or payload.get("escalate_offered")
  is True`).
- **AC-1798** A numbered pick over a combined roster+CS-member offer that lands on a
  MEMBER option (no `payload["agent"]`, no `payload["hold"]`) carries the pending's own
  top-level agent, not `None` (SHOULD-3); a pick that lands on the explicit hold option
  (`payload["hold"] is True`) carries `None`.
- **AC-1799** The six mint sites named in reviewer round 1 (`engine.py::_question_offered`'s
  team clarify, company clarify, member offer and escalate-catalog arms;
  `answer_bridge.py::_miss_question`'s member-offer arm; `turn/compose.py::compose`'s
  roster re-arm) each stamp the minting turn's `routing.suggested_agent` the same way the
  two already-fixed sites do. At minimum: the company clarify's answering "1" turn carries
  the right `agent_code` on the wire body end to end; every other site gets a pure
  assertion that the minted pending's payload carries the agent.

## Regression

- **AC-1794** `SLA` body (`_sla_body`) on the acceptance turn carries the same
  `agent_code` as the next-assignee body (one source, `routing.suggested_agent`).
- **AC-1795** The team chain in `lane_parse_output` is byte-for-byte unchanged: existing
  `test_s5_escalation_lane.py` and `test_turn_replay.py` suites stay green; replay
  fixtures under `tests/chatbot/replay_turns/console/` that pin a `suggested_agent` still
  match.
- **AC-1800** (NIT-7) A direct unit test on `turn/compose.py::_team_pick_question` itself
  (not just through a full engine replay): the single-team branch's own `Pending` carries
  `payload["agent"] == "x"` when called with `agent="x"`.
