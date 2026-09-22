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
- **AC-1797** The SAME roster pending WITH `escalate_offered: True` DOES carry its agent,
  given an ACCEPTING verdict (the gate's other side - `pending.kind in OFFER_KINDS or
  payload.get("escalate_offered") is True`). Reworded in review round 2 (see AC-1802):
  this AC's own point - `escalate_offered` matters, where AC-1796's otherwise-identical
  roster without the flag never carries - is unchanged, but its test now also grants an
  accepting verdict, since AC-1802 pins the accept axis on its own and an AC-1797 verdict
  with neither would be red for a DIFFERENT reason than the one this AC is about.
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
  assertion that the minted pending's payload carries the agent. The roster re-arm's OWN
  two tests are corrected in review round 2 (AC-1801 below supersedes the "falls to ctx
  when the roster carries no agent" framing, which was pinning the bug AC-1801 fixes).

## Review round 2

- **AC-1801** (SHOULD-A, BLOCKING) The roster re-arm's `team` and `agent` come from the
  SAME source, not two independent ones: a carried roster with a TEAM but no agent
  (`answer_bridge.py`'s D4 narrower roster, `turn/apply.py`'s narrow ask both produce
  this shape), re-armed under a LATER, different-domain miss, carries `agent: None` -
  never that later turn's own agent paired with the earlier, stale team. A carried
  roster with NO team of its own takes BOTH halves from the turn doing the re-arming.
  A carried roster that already has both keeps its own, over either.
- **AC-1802** (SHOULD-1 residual) The acceptable-offer gate is "ACCEPTABLE", not
  "ACCEPTED": an `escalate_offered` roster (not an `OFFER_KINDS` pending) only carries
  its agent when THIS turn actually accepts - `is_affirmative`, `escalation.
  is_escalation_confirmation`, or a numbered pick landing on one of the roster's own
  options (the same signal `decide()` itself reads at `turn/decide.py:571-573`). A
  non-accepting verdict over the same still-open roster falls to `DEFAULT_SUGGESTED_
  AGENT`. An `OFFER_KINDS` pending (`team_pick`/`company_pick`/`member_offer`) is
  unaffected - its team is read unconditionally at the same `lane_parse_output` line,
  so its agent stays unconditional too.
- **AC-1803** The two `team_pick` mint sites round 1 missed: `answer_bridge.py::
  apply_silent_company_offer`'s pending stamps THIS turn's agent (its team is already
  this turn's own `routing.suggested_team`, read off `raw_team`); `answer_bridge.py::
  _crossdomain_offer_pending`'s pending carries NO agent at all, deliberately - its team
  comes off the cross-domain rung's own render block, not off this turn's routing (the
  function takes no `parser` argument to read one from).

## Round 4 (owner-approved scope extension, 22 Sep 2026): the brand half

"A MOCHA product's escalation goes to Lucas, a SORENTO product's to Jereen" (Packing
List tags in prod: Jereen = every brand except mocha, Lucas = mocha). Engine replays
seed `team_member_brands` rows themselves (never read existing data) and run the REAL
`/external/next-assignee` handler (not the file's usual canned stub), because "the
drawn assignee is the brand-tagged member" is the actual claim - a mock cannot prove it.

- **AC-1804** Turn 1 is an `incoming` ETA miss for a SORENTO-branded product, turn 2 is
  `yes`: the wire body has `brand_code == "sorento"` AND the REAL round-robin draw over
  a seeded Packing List team (Lucas tagged `mocha`, Jereen tagged `sorento`+`cabana`)
  returns Jereen, not a rotation.
- **AC-1805** Same two turns, a MOCHA-branded product: `brand_code == "mocha"` and the
  draw returns Lucas.
- **AC-1806** Four sub-cases:
  - (a)/(b) are AC-1804/AC-1805 themselves.
  - (c) A product with NO brand (`lanes/business/gate.py`'s `routing_brand` stays
    `None`): `brand_code` is `None` on the wire body, and the draw is not narrowed - both
    Lucas and Jereen stay eligible, exactly as before this fix ever carried a brand.
  - (d) Pure test on `escalation_context`: a PICKED-MEMBER row's own `brand_code` still
    outranks a `carried_brand` that says something else - the picked-member and
    company-pick arms are untouched by round 4, on purpose.

## Round 5 (evidence, 22 Sep 2026): does the brand carry hold for a PHOTO escalation too?

Owner asked whether round 4's carry also holds for a `product_attachment` (photo/
drawing request) escalation, not just `incoming`. Journey: a photo request for a
product with NO attachment on file -> the rich miss (`test_rearch_r5_production_
decides.py::TestFetchedEmptyIsAMiss::test_attachment_fetch_with_zero_rows_is_the_rich_
miss` shows the shape) -> its escalate offer (team `marketing_product` off the domain
row, agent `general_enquiries` off the parser's own domain map) -> "yes". Confirmed
green on the FIRST run - the attachment miss takes the SAME mint site round 1 already
found and stamped for the incoming miss (`answer_bridge.py::_miss_question`'s
escalate-catalog bare-"Yes" arm, single team/company) - no code fix needed, evidence
only. Confirmed load-bearing by temporarily reverting that ONE site's `brand_code`
stamp and re-running: both went red with `brand_code: None` on the wire, then green
again once restored.

- **AC-1807** A MOCHA-branded product's photo miss, then "yes": the wire body has
  `brand_code == "mocha"`, `agent_code == "general_enquiries"`,
  `team_code == "marketing_product"`, and the REAL round-robin draw over a seeded
  Marketing - Product team (Kia Yee tagged `mocha`, Tay Zhi Yang tagged
  `sorento`+`cabana`) returns Kia Yee.
- **AC-1808** Same journey, a SORENTO-branded product: the draw returns Tay Zhi Yang.

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
