"""PLAN-chatbot-escalation-routing.md, "Brand and company (lane)". AC-1121 to AC-1130.

RED, written before the coder's slices S3/S4/S5 (Phase 2, test-first). Lane-unit level
(`escalation.run`), `_ctx`/`_item`/`_services` imported from `test_s5_escalation_lane.py`.

**Tester's seam design decision** (same convention `test_s5_escalation_lane.py`'s module
docstring uses for `resolve_and_gate`/`preview_assignee`): `resolve_and_gate` is not wired
today (`escalation_services._not_live`), so this file designs the shape the coder implements
against, explicit here rather than guessed at review time:

    services.resolve_and_gate(ctx, item) -> {"resolved": [<row>, ...], "did_you_mean": [<row>, ...]}

    row = {"uuid", "canonical_code", "company_id", "company_name",
           "display": {"brand": {"brand_code": <str | None>}}}

    - exactly one `resolved` row -> that row's brand/company are what the plan's step 1 names
      (`display.brand.brand_code`, the SAME field `lanes/business/gate.py`'s `_bc()` reads
      off a resolver row - not re-invented here).
    - `resolved` empty, `did_you_mean` non-empty -> the lane arms a `product_pick` open
      question (plan step 2): `result["arm"] == "product_pick"`,
      `result["pending"] == {"kind": "product_pick", "options": [...]}`, ONE `send_message`
      action and nothing else (no assign, no comment, no SLA).
    - the deferred escalation rides the pending payload: `result["pending"]["payload"]["then"]
      == {"escalate": {"team_word": <the parser's raw team word this turn>}}` (plus
      `offer_team` when an offer was open - not exercised by these fixtures).

The resolver is only called when THIS TURN names a product entity
(`hint == "product"`, `current_message is True`) - a turn naming none skips straight to D3's
carry rule (AC-1127/AC-1128), covered separately below.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.lanes.escalation import run
from tests.chatbot.test_s5_escalation_lane import _ctx, _item, _services


def _product_entity(code: str) -> dict:
    return {"raw": code, "hint": "product", "confident": True, "canonical_code": None, "current_message": True}


def _resolved_row(code: str, *, brand: str, company_id: str = "co-sorento", company_name: str = "Sorento") -> dict:
    return {
        "uuid": f"uuid-{code}",
        "canonical_code": code,
        "company_id": company_id,
        "company_name": company_name,
        "display": {"brand": {"brand_code": brand}},
    }


def _next_assignee_body(services) -> dict:
    services.next_assignee.assert_called_once()
    return services.next_assignee.call_args[0][0]


# --------------------------------------------------------------------------- #
# AC-1121 / AC-1122: a product that resolves to one row carries its brand, never
# its company, into the next-assignee body
# --------------------------------------------------------------------------- #


def test_ac1121_a_sorento_brand_product_carries_its_brand_into_the_body() -> None:
    """T3 (the 21 Aug turn): SRTWB8004 resolves to one row, brand SORENTO. RED today: the
    lane never calls the resolver at all (H26), so `context_item["brand_code"]` comes only
    from `escalation_context`'s own axes (none of which fire here) and stays None."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_called_once()
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "sorento", (
        f"the resolved product's own brand must reach the body: {body!r}"
    )


def test_ac1121_a_mocha_brand_product_under_the_sorento_company_carries_mocha() -> None:
    """T4: MWC7625-SH-S10, a Mocha-brand product living under the Sorento company (1,264
    such rows, plan "Why" table / roster facts). Brand is the PRODUCT's, company is the
    CONTACT's (D7) - this is the fixture that tells the two apart."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("MWC7625-SH-S10")],
    )
    item = _item(team="customer_service")
    services = _services(
        gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []}
    )

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["brand_code"] == "mocha", body


def test_ac1122_the_lane_never_sets_company_id_from_the_resolved_product() -> None:
    """AC-1122: the resolved row above carries `company_id: "co-sorento"` (the PRODUCT's own
    company row) - the body must not copy it. `next_assignee` resolves the CONTACT's company
    on its own (existing precedence); the lane's job stops at brand."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    run(ctx, item, services=services)

    body = _next_assignee_body(services)
    assert body.get("company_id") is None, (
        f"the body's company_id must come from the CONTACT, never the resolved product's "
        f"own company row: {body!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1124: an unresolved product arms a did-you-mean product_pick, with the deferred
# escalation on its payload, and takes NO action beyond the one ask
# --------------------------------------------------------------------------- #


def test_ac1124_an_unresolved_product_arms_a_product_pick_with_the_deferred_escalation() -> None:
    """T1 (turn_1, 11 Sep 12:55): SRTWC60630-SH does not resolve; three did-you-mean rows
    come back. No assignment, no SLA row, no comment on THIS turn - only the ask."""
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[_product_entity("SRTWC60630-SH")],
    )
    item = _item(team="warehouse")
    did_you_mean = [
        _resolved_row("SRTWC6030-SH-BL", brand="sorento"),
        _resolved_row("SRTWC6030-SH-UF", brand="sorento"),
        _resolved_row("SRTWC6030-SH-MW", brand="sorento"),
    ]
    services = _services(gate={"resolved": [], "did_you_mean": did_you_mean})

    result = run(ctx, item, services=services)

    assert result["arm"] == "product_pick", (
        f"an unresolved product must arm the did-you-mean pick, never assign: {result!r}"
    )
    assert result["pending"]["kind"] == "product_pick", result["pending"]
    offered_codes = {o.get("code") for o in result["pending"]["options"]}
    assert offered_codes == {"SRTWC6030-SH-BL", "SRTWC6030-SH-UF", "SRTWC6030-SH-MW"}, offered_codes
    assert result["pending"]["payload"]["then"]["escalate"]["team_word"] == "marketing", (
        f"the deferred escalation must ride the pending payload so a later pick can re-enter "
        f"the team ladder: {result['pending']!r}"
    )
    kinds = [a["kind"] for a in result["actions"]]
    assert kinds == ["send_message"], (
        f"an unresolved product takes NO assignment action - only the ask: {kinds!r}"
    )
    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-1125 / AC-1126: the `product_pick` handler resumes the escalation on a pick,
# and clears with nothing on a fresh ask instead
# --------------------------------------------------------------------------- #


def test_ac1125_a_pick_on_the_deferred_escalation_question_resumes_the_team_ladder() -> None:
    """AC-1125: `dialogue/open_question.resolve("product_pick", ...)` is the ONE place a
    pick against a frozen roster is answered (D5). A payload carrying `then.escalate` is
    this file's own contract (see module docstring); a pick against it must say so on the
    `Outcome`, so the caller (the escalation lane, on its next turn) knows to re-enter the
    team ladder instead of just answering the product. RED today: `_product_pick` never
    reads `payload.get("then")` at all - only `payload.get("keep")` (issue #708)."""
    from app.services.chatbot.dialogue.open_question import resolve

    options = [{"uuid": "u1", "code": "SRTWC6030-SH-BL", "label": "SRTWC6030-SH-BL", "entity_type": "product"}]
    payload = {"then": {"escalate": {"team_word": "marketing"}}}

    outcome = resolve("product_pick", {"picks": [1]}, options, payload)

    assert outcome.resolved is True
    assert outcome.escalate is True, (
        "a pick on a DEFERRED-ESCALATION product_pick must resume the escalation this turn, "
        f"not just answer the product question: {outcome!r}"
    )
    assert outcome.routing.get("team_word") == "marketing", (
        f"the deferred team word must ride the outcome back to the caller: {outcome!r}"
    )


def test_ac1126_a_fresh_ask_instead_of_a_pick_resolves_no_escalation() -> None:
    """AC-1126: a new ask (no valid pick against the frozen options) answers nothing and
    escalates nothing - the existing, unresolved-outcome behaviour. Guard, not a defect."""
    from app.services.chatbot.dialogue.open_question import resolve

    options = [{"uuid": "u1", "code": "SRTWC6030-SH-BL", "label": "SRTWC6030-SH-BL", "entity_type": "product"}]
    payload = {"then": {"escalate": {"team_word": "marketing"}}}

    outcome = resolve("product_pick", {"picks": []}, options, payload)

    assert outcome.resolved is False
    assert outcome.escalate is False


# --------------------------------------------------------------------------- #
# AC-1127 / AC-1128: D3's carry rule, judged against the LANDED team
# --------------------------------------------------------------------------- #


def _focus_previous_state(*, product_code: str | None, domain: str | None) -> dict:
    """A REAL five-key previous state's `focus` slot (`dialogue/focus.py::from_session`),
    the shape `contracts.SESSION_VAR_KEYS` / `SessionVars(extra="forbid")` can actually
    hold - never the legacy `routing` / `routing_brand` mirrors the schema forbids.

    Reviewer kill test (security review round 3, B1): the ORIGINAL AC-1127 fixture
    injected `prev_variables={"routing": ..., "routing_brand": ...}`, which passed even
    with the landed-item carry logic reverted, because those keys can never exist on a
    real persisted session - the test was proving nothing. This builder is what a photo
    turn (or a stock turn) actually leaves behind: `focus.products` holding the entity
    the customer was last shown, `focus.domains` holding the domain that turn answered in
    (`derive_routing` maps `product_attachment -> marketing_product`, `inventory ->
    warehouse` - the SAME map `test_output_exchange_rules.py::DOMAIN_ROUTING` pins).
    """
    products = [] if product_code is None else [
        {
            "raw": product_code,
            "hint": "product",
            "canonical_code": product_code,
            "current_message": False,
            "confident": True,
        }
    ]
    focus: dict[str, Any] = {}
    if products:
        focus["products"] = {"value": products, "set_at_turn": 1, "set_at": None, "source": "reuse"}
    if domain is not None:
        focus["domains"] = {"value": [domain], "set_at_turn": 1, "set_at": None, "source": "reuse"}
    return {"focus": focus}


def test_ac1127_no_product_named_but_the_previous_team_matches_the_landed_one_carries_it() -> None:
    """AC-1127 (journey step 4/5, no photo this turn), rewritten against a REAL previous
    state after the reviewer's kill test (see `_focus_previous_state`'s docstring). The
    previous turn's `focus.products` holds `MWC7625-SH-S10` and its `focus.domains` holds
    `product_attachment`, which `derive_routing` maps to `marketing_product` - the SAME
    team the family word `marketing` lands on this turn (AC-1114's ladder). Expected: the
    lane resolves the CARRIED product through the resolver seam (this turn named none of
    its own) and the body carries brand `mocha`, team `marketing_product`, no question.
    RED today: `escalation_context`'s same-team rung reads `prev.routing_brand`, a key a
    real session never carries, so nothing is ever resolved for a carried product at all."""
    ctx = _ctx(
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables=_focus_previous_state(product_code="MWC7625-SH-S10", domain="product_attachment"),
    )
    item = _item(team="marketing_product")
    services = _services(gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_called()
    called_with = str(services.resolve_and_gate.call_args)
    assert "MWC7625-SH-S10" in called_with, (
        f"the seam must be asked to resolve the CARRIED code, not a fresh one: {called_with}"
    )
    assert result["arm"] == "human-intervention", result
    assert result["pending"] is None
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "mocha", (
        f"the previous turn's carried product's brand must reach the body: {body!r}"
    )


def test_ac1127_companion_a_focus_domain_outside_the_family_never_resolves_the_carried_product() -> None:
    """AC-1127 companion (reviewer, security review round 3, B1): the previous turn's
    `focus.domains` was `inventory` (a stock/warehouse turn), OUTSIDE the `marketing`
    family - so the ladder asks which marketing team (AC-1112) rather than assigning, and
    the carried product is NEVER sent to the resolver: an unresolved question has no
    landed team yet to judge the carry against."""
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables=_focus_previous_state(product_code="MWC7625-SH-S10", domain="inventory"),
    )
    item = _item(team="warehouse")
    services = _services(gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called()
    assert result["arm"] == "clarify", result
    assert [p["team"] for p in result["pending"]["options"]] == [
        "marketing_product",
        "marketing_form",
        "marketing_promotion",
    ], result["pending"]


def test_ac1128_no_product_and_the_previous_team_differs_from_the_landed_one_carries_nothing() -> None:
    """AC-1128 (journey step 6), rewritten after the reviewer's S6 kill test (security
    review round 3 re-check): the ORIGINAL fixture used the same legacy
    `prev_variables={"routing": ..., "routing_brand": ...}` shape B1 already retired for
    AC-1127 - a real session can never hold those keys, and worse, it meant
    `_carried_products(ctx)` read `focus.products` off a state with no `focus` key at all
    and returned `[]` immediately, so `_carried_brand`'s landed-team GATE (`escalation.py`
    ~791) was never even reached. The reviewer proved it by removing the gate outright and
    finding nothing went red.

    Rewritten on `_focus_previous_state`: a REAL carried product (`MWC7625-SH-S10`) off a
    warehouse (`inventory`) previous turn, this turn's exact word `marketing_product`
    landing there directly (a stock turn, then "ESCALATE TO MARKETING PRODUCT" - the
    direct-pick half of journey step 6). `_carried_products` is now NON-EMPTY, so the gate
    is what must say no: the previous team (`warehouse`) differs from the LANDED team
    (`marketing_product`), so the resolver is never asked about the carried product and
    the body's brand stays None."""
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables=_focus_previous_state(product_code="MWC7625-SH-S10", domain="inventory"),
    )
    item = _item(team="warehouse")
    services = _services(gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called(), (
        "the carried product must never reach the resolver once the landed team differs "
        "from the team the conversation was carrying it on"
    )
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body.get("brand_code") is None, (
        f"the previous turn's team (warehouse) differs from the LANDED team "
        f"(marketing_product) - nothing must carry: {body!r}"
    )


def test_ac1128_companion_a_different_family_member_landing_also_carries_nothing() -> None:
    """AC-1128 companion (reviewer, security review round 3 re-check, S6): the INSIDE-
    FAMILY-BUT-DIFFERENT-MEMBER case. The previous turn's `focus.domains` was
    `product_attachment` (a photo turn on `marketing_product`), and THIS turn names a
    DIFFERENT exact member of the same family, `marketing_form` - a real catalogue word
    always wins outright (R-c), so the ladder lands there directly, with no clarify. The
    landed team (`marketing_form`) still differs from the carried team
    (`marketing_product`), so the carry gate must say no even though both teams are in
    the same family: the customer is very plausibly asking about a DIFFERENT product line
    (forms, not the product they were just shown), and carrying the old product's brand
    across would misname the pool for a team the customer never carried it on."""
    ctx = _ctx(
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_form", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables=_focus_previous_state(product_code="MWC7625-SH-S10", domain="product_attachment"),
    )
    item = _item(team="marketing_product")
    services = _services(gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called(), (
        "a different member of the SAME family still fails the landed-team carry gate"
    )
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_form", body
    assert body.get("brand_code") is None, (
        f"marketing_form is not the team the conversation carried the product on, even "
        f"though both are marketing teams: {body!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1129: the body's team_code/agent_code are the LANDED pair, never the inherited one
# --------------------------------------------------------------------------- #


def test_ac1129_the_body_carries_the_landed_team_and_its_own_agent_never_the_inherited_pair() -> None:
    """AC-1129: inherited `customer_service`/`order_enquiries` (an order turn), landed
    `marketing_product` (the parser's own exact word this turn). RED today:
    `_next_assignee_body` reads `context_item["team"]` - the INHERITED team - and
    `ctx.parse.output.routing.suggested_agent` - the inherited AGENT - verbatim, never
    recomputed for the team the ladder actually landed on."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="customer_service")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", (
        f"the LANDED team must reach the body, not the inherited customer_service: {body!r}"
    )
    assert body["agent_code"] == "general_enquiries", (
        f"the agent must be marketing_product's OWN agent from the domain table "
        f"(product_attachment -> marketing_product/general_enquiries), never the inherited "
        f"order_enquiries: {body!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1130: the PIC comment names the raw code, and the picked code after a pick
# --------------------------------------------------------------------------- #


def test_ac1130_the_comment_names_the_raw_code_the_customer_typed() -> None:
    """AC-1130, first half: the comment the PIC reads must name the code the customer
    actually typed. RED today: `_comment_text` has no read of the entity at all - the
    comment is `Team: ...` plus the SLA block, with no product code anywhere."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    comment = next(a for a in result["actions"] if a["kind"] == "add_comment")
    assert "SRTWB8004" in comment["text"], (
        f"the comment must name the raw code the customer typed: {comment['text']!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1125, the CROSS-TURN half. Added by the coder (slice S4) on the captain's
# instruction: the tester pinned AC-1125 at the `resolve()` handler level because the
# wiring between the two turns was the coder's to design, and a two-turn assertion is what
# proves the design rather than the handler. Nothing above is weakened or edited - these
# two run the REAL artifacts end to end: turn 1's lane arms the question, the REAL
# `open_question.resolve` answers it, and turn 2's lane reads its own payload back.
# --------------------------------------------------------------------------- #


def _deferred_question(team_word: str) -> dict:
    """Turn 1: an escalation naming a code that does not resolve. Returns the armed question."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": team_word, "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[_product_entity("SRTWC60630-SH")],
    )
    services = _services(
        gate={
            "resolved": [],
            "did_you_mean": [_resolved_row("SRTWC6030-SH-BL", brand="sorento")],
        }
    )
    result = run(ctx, _item(team="purchasing"), services=services)
    assert result["arm"] == "product_pick", result
    return result["pending"]


def _resumed_ctx(question: dict) -> dict:
    """Turn 2: the customer picks row 1, through the real resolver and the real handler."""
    from app.services.chatbot.dialogue.open_question import resolve

    outcome = resolve("product_pick", {"picks": [1]}, question["options"], question["payload"])
    assert outcome.escalate is True, outcome
    ctx = _ctx(
        # The head's routing chain on a bare "1": no team of its own, so the turn carries
        # the same inherited team the deferred turn had.
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        # A pick names no team word of its own - that is the whole reason the deferral has
        # to remember one.
        parser_raw={"routing": {"suggested_team": None, "suggested_agent": None}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=outcome.focus["products"],
        prev_variables={"open_question": question},
    )
    # `engine._run_stages` stamps this in the `answered` stage (`parse_block["_answered"] =
    # answered_entry`), which is how the lane knows THIS message answered the question the
    # deferral was armed on. Set here rather than through `_ctx` so the tester's shared
    # builder is untouched.
    ctx["parse"]["_answered"] = {"handler": outcome.handler, "after": {"escalate": True}}
    return ctx


def test_ac1125_a_pick_resumes_the_deferred_escalation_with_the_resolved_brand() -> None:
    """The deferral remembered an EXACT catalogue word, so the pick assigns straight away,
    with the picked product's brand on the body (plan step 2, journey steps 1 to 3)."""
    question = _deferred_question("marketing_product")
    services = _services(
        gate={"resolved": [_resolved_row("SRTWC6030-SH-BL", brand="sorento")], "did_you_mean": []}
    )

    result = run(_resumed_ctx(question), _item(team="purchasing"), services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "sorento", body


def test_ac1125_a_pick_on_a_family_word_deferral_asks_which_team_next() -> None:
    """The deferral remembered the FAMILY word `marketing` and the previous turn sat on
    `purchasing`, outside it - so the pick resolves the product and then asks which
    marketing team, which is journey step 2."""
    question = _deferred_question("marketing")
    services = _services(
        gate={"resolved": [_resolved_row("SRTWC6030-SH-BL", brand="sorento")], "did_you_mean": []}
    )

    result = run(_resumed_ctx(question), _item(team="purchasing"), services=services)

    assert result["arm"] == "clarify", result
    assert [p["team"] for p in result["pending"]["options"]] == [
        "marketing_product",
        "marketing_form",
        "marketing_promotion",
    ], result["pending"]
    services.next_assignee.assert_not_called()


# --------------------------------------------------------------------------- #
# Security review, S1 and its reply companion, S3. Written on the tester's
# own branch after a merge of the coder's slices (head 9742167a8), so these are
# RED against the shipped implementation, not against a stub. Topic: AC-1130
# hardening (S1, item 1 and its reply companion, item 6) and the did-you-mean
# cap (S3, item 3).
# --------------------------------------------------------------------------- #


def _sanitized(raw: str) -> str:
    """What a code SHOULD look like once bounded: every run of whitespace or control
    character removed outright (never collapsed to a space), capped at
    `PRODUCT_CODE_MAX_CHARS`. The same character class `escalation.py`'s own
    `_CODE_NOISE` names (`[\\s\\x00-\\x1f\\x7f-\\x9f]+`), spelled out here rather than
    imported so this test does not depend on a private name staying put - it is the
    CONTRACT (strip, not collapse) that matters, not the constant."""
    import re

    return re.sub(r"[\s\x00-\x1f\x7f-\x9f]+", "", raw)[:100]


def _malicious_raw() -> str:
    """A 300 char typed code carrying a newline, a carriage return, a tab, and the frozen
    offer open phrase (`output_exchange._OFFERED_ESCALATION_RE`), padded to the full
    length with filler.

    Security re-check finding: the phrase must sit WITHIN the first 100 chars, not past
    it. A collapse-to-one-space sanitiser (today's `_CODE_NOISE.sub(" ", ...)`) leaves the
    phrase's own internal spacing untouched - "would you like me to escalate" has no
    control characters of its own, so collapsing the NOISE around it does nothing to the
    phrase itself. Placing it past the 100 char cap made the earlier version of this
    fixture pass on TRUNCATION alone, never exercising whether the sanitiser actually
    breaks the phrase. Here the phrase (with a code beside it, as a customer would
    plausibly type) is the first 40-odd characters, so only a sanitiser that REMOVES
    whitespace rather than collapsing it can defeat it.

    An attacker typing this as a product code is testing two things at once: whether the
    PIC comment and the clarify reply stay one bounded line (S1), and whether the phrase
    could ever reopen a stale offer on a LATER turn if this text ever reached a state's
    `response` field (the legacy `offer_is_open` regex path, still read "during the
    migration window").
    """
    lead = "would you like me to escalate SRTWB8004"
    noise = "\n" + "A" * 40 + "\r" + "B" * 40 + "\t" + "C" * 40
    raw = lead + noise
    raw = raw + "D" * (300 - len(raw))
    assert len(raw) == 300
    assert "would you like me to escalate" in raw[:100].lower(), (
        "the phrase must sit within the first 100 chars, or a truncating sanitiser would "
        "pass this fixture for the wrong reason"
    )
    return raw


def test_s1_pic_comment_product_line_is_bounded_and_never_reopens_a_stale_offer() -> None:
    """Security review S1 (AC-1130 hardening), item 1, tightened by the security re-check
    (`_malicious_raw` now puts the phrase inside the first 100 chars - see that function's
    docstring). `_product_line` embeds the typed code verbatim with no cap and no
    sanitising (`escalation.py`'s own `_product_line`), so a 300 char raw with control
    characters and the frozen offer phrase reaches the PIC comment whole. RED until the
    coder bounds it to one line, at most 100 chars of the typed text, with whitespace
    REMOVED rather than collapsed to a space - a collapse leaves the phrase's own internal
    spacing untouched and still matches `offer_is_open`'s regex."""
    from app.services.chatbot.head.output_exchange import offer_is_open

    raw = _malicious_raw()
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[{"raw": raw, "hint": "product", "confident": True, "canonical_code": None, "current_message": True}],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    comment = next(a for a in result["actions"] if a["kind"] == "add_comment")
    text = comment["text"]
    assert text.count("Product: ") == 1, text
    start = text.index("Product: ") + len("Product: ")
    # `_product_line` ends its own line with exactly one trailing "\n"; the next real
    # field starts with the SLA alert clock emoji, which is a safe fixed marker the
    # malicious raw cannot contain.
    end = text.index("⏰")
    body = text[start:end]
    if body.endswith("\n"):
        body = body[:-1]
    typed_part = body.split(" (picked ")[0]

    # The tightened expectation: whitespace REMOVED, not collapsed to single spaces, so
    # the assertion is an exact match against the STRIPPED text rather than a mere
    # absence-of-control-characters check (which a collapse-to-space sanitiser would also
    # satisfy without breaking the phrase).
    assert typed_part == _sanitized(raw), (
        f"the typed text must be sanitised by REMOVING whitespace, not collapsing it to "
        f"single spaces: got {typed_part!r}, expected {_sanitized(raw)!r}"
    )
    assert not any(ch.isspace() for ch in typed_part), (
        f"no whitespace of any kind may survive in the comment's Product line: {typed_part!r}"
    )
    assert len(typed_part) <= 100, (
        f"the comment must carry at most 100 chars of the typed text: {len(typed_part)} chars"
    )
    assert "would you like me to escalate" not in text.lower(), (
        f"the injected phrase must not survive a bounded comment: {text!r}"
    )
    assert offer_is_open({"response": text}) is False, (
        "the comment text must never make a later turn's offer_is_open read True"
    )


def test_s1_companion_clarify_reply_is_bounded_and_never_reopens_a_stale_offer() -> None:
    """Security review S1, item 6 (the reply half), tightened by the security re-check
    (see `_malicious_raw`'s docstring): `_product_pick_ask`'s
    `lead = f"I could not find *{typed}*."` embeds the SAME typed code with no cap, on
    the did-you-mean ask the customer receives when their code does not resolve. RED for
    the same reason as the comment test above: a collapse-to-space sanitiser leaves the
    phrase's own spacing untouched."""
    from app.services.chatbot.head.output_exchange import offer_is_open

    raw = _malicious_raw()
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[{"raw": raw, "hint": "product", "confident": True, "canonical_code": None, "current_message": True}],
    )
    item = _item(team="warehouse")
    did_you_mean = [_resolved_row("SRTWC6030-SH-BL", brand="sorento")]
    services = _services(gate={"resolved": [], "did_you_mean": did_you_mean})

    result = run(ctx, item, services=services)

    assert result["arm"] == "product_pick", result
    text = result["clarify"]["clarify_text"]
    start = text.index("I could not find *") + len("I could not find *")
    end = text.index("*.", start)
    typed_in_lead = text[start:end]

    # The tightened expectation: whitespace REMOVED, not collapsed to single spaces - an
    # exact match against the STRIPPED text, not merely an absence-of-control-characters
    # check a collapse-to-space sanitiser would also pass.
    assert typed_in_lead == _sanitized(raw), (
        f"the typed text must be sanitised by REMOVING whitespace, not collapsing it to "
        f"single spaces: got {typed_in_lead!r}, expected {_sanitized(raw)!r}"
    )
    assert not any(ch.isspace() for ch in typed_in_lead), (
        f"no whitespace of any kind may survive in the clarify reply's lead: {typed_in_lead!r}"
    )
    assert len(typed_in_lead) <= 100, (
        f"the clarify reply must bound the typed text: {len(typed_in_lead)} chars"
    )
    assert "would you like me to escalate" not in text.lower(), (
        f"the injected phrase must not survive a bounded clarify reply: {text!r}"
    )
    assert offer_is_open({"response": text}) is False, (
        "the clarify reply must never make a later turn's offer_is_open read True"
    )


def _resolution(token: str, *, matches: list[dict] | None = None, alternatives: list[dict] | None = None) -> dict:
    """One `resolutions[]` entry, the shape `app/api/v1/system/references.py` (~line 218)
    and the main product resolver both emit: `{token, resolved, ambiguous, matches,
    alternatives}`. Built here rather than through `escalation.run`, because the cap this
    test pins (`escalation_services._product_rows`) sits BELOW the lane's own seam
    boundary - a lane-level test that mocks `resolve_and_gate` directly bypasses it
    entirely and would pass whether or not the cap exists."""
    return {
        "token": token,
        "resolved": False,
        "ambiguous": False,
        "matches": matches or [],
        "alternatives": alternatives or [],
    }


def _alt_row(code: str, *, brand: str = "sorento") -> dict:
    row = _resolved_row(code, brand=brand)
    row["entity_type"] = "product"
    row["match_tier"] = "fuzzy"
    return row


def test_s3_five_unresolved_tokens_cap_did_you_mean_rows_per_token_and_overall() -> None:
    """Security review S3 (AC-1124 cap), pinned at `escalation_services._product_rows` -
    the function that turns one resolver payload into the lane's `(resolved,
    did_you_mean)` pair and where the coder's fix (commit `3f0e36879`) actually applies
    the business lane's own two caps. Five product tokens in one message, each resolver
    resolution carrying 15 non-exact alternatives (75 rows total): at most 3 survive per
    token (`lanes/business/miss_suggest._cap3`) and at most 5 token blocks survive at all
    (`MISS_TOKEN_BLOCK_CAP`, `_dym_plan`'s own `d1s = d1s[:5]`), so at most 15 rows reach
    the did-you-mean offer whatever the resolver hands back."""
    from app.services.chatbot.lanes.business.miss_suggest import _cap3
    from app.services.chatbot.lanes.escalation_services import MISS_TOKEN_BLOCK_CAP, _product_rows

    per_token_cap = len(_cap3(list(range(15))))
    assert per_token_cap == 3, "miss_suggest.py's own per-token cap moved; re-read it"
    assert MISS_TOKEN_BLOCK_CAP == 5, "escalation_services' own token-block cap moved; re-read it"

    tokens = [f"ZZTTOKEN{i}" for i in range(1, 6)]
    payload = {
        "resolutions": [
            _resolution(token, alternatives=[_alt_row(f"{token}-C{n:02d}") for n in range(1, 16)])
            for token in tokens
        ]
    }

    resolved, did_you_mean = _product_rows(payload)

    assert resolved == []
    assert len(did_you_mean) <= per_token_cap * MISS_TOKEN_BLOCK_CAP, (
        f"at most {per_token_cap * MISS_TOKEN_BLOCK_CAP} rows total, got {len(did_you_mean)}"
    )

    by_token: dict[str, int] = {}
    for row in did_you_mean:
        code = row.get("canonical_code") or ""
        prefix = code.split("-C")[0]
        by_token[prefix] = by_token.get(prefix, 0) + 1
    assert set(by_token) <= set(tokens)
    for token, count in by_token.items():
        assert count <= per_token_cap, (
            f"at most {per_token_cap} rows per token, {token} offered {count}: {by_token!r}"
        )


def test_s3_the_lane_arms_the_capped_rows_as_the_did_you_mean_pick() -> None:
    """The lane-level half: once the seam hands the (already capped) rows back, the lane
    arms every one of them and nothing else - `_product_pick_ask` itself has no cap of
    its own to test, since S3's cap lives one layer below (see the test above)."""
    from app.services.chatbot.lanes.escalation_services import _product_rows

    tokens = [f"ZZTTOKEN{i}" for i in range(1, 6)]
    payload = {
        "resolutions": [
            _resolution(token, alternatives=[_alt_row(f"{token}-C{n:02d}") for n in range(1, 16)])
            for token in tokens
        ]
    }
    _resolved, did_you_mean = _product_rows(payload)
    assert 0 < len(did_you_mean) <= 15, len(did_you_mean)

    entities = [_product_entity(t) for t in tokens]
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=entities,
    )
    item = _item(team="warehouse")
    services = _services(gate={"resolved": [], "did_you_mean": did_you_mean})

    result = run(ctx, item, services=services)

    assert result["arm"] == "product_pick", result
    options = result["pending"]["options"]
    assert len(options) == len(did_you_mean)
    offered_codes = {o.get("code") for o in options}
    assert offered_codes == {row.get("canonical_code") for row in did_you_mean}

    send = next(a for a in result["actions"] if a["kind"] == "send_message")
    if send.get("quick_replies"):
        assert len(send["quick_replies"].split(", ")) == len(options), (
            f"the quick replies must match the offered options count: {send!r}"
        )
    for opt in options:
        assert opt["code"] in send["text"], (
            f"every offered option must appear in the reply text: {opt['code']!r} missing "
            f"from {send['text']!r}"
        )


# --------------------------------------------------------------------------- #
# Security review round 3, new S1: a carried resolved product must never mask a
# typed unresolved one.
# --------------------------------------------------------------------------- #


def test_s1_round3_a_carried_resolved_product_never_masks_the_typed_unresolved_one() -> None:
    """Security review round 3, item S1. The resolver answers per TOKEN
    (`app/api/v1/system/references.py` ~line 218's `resolutions` shape, reused by
    `_product_rows`). This turn carries `SRTWB8004` (`current_message: False` - the
    previous turn's own product, still on the entity list per #863's focus rules) AND
    types a NEW code, `SRTWC60630-SH`, that does not resolve. `_resolve_product` reads
    `resolved` / `did_you_mean` off the WHOLE seam answer with no read of which token is
    THIS turn's own, so a resolved row for the CARRIED product masks the typed one
    entirely: brand comes back `sorento` (the carried code's brand) and the did-you-mean
    for the typed code is never armed - the exact inversion of AC-1124 (did-you-mean
    first, D6). RED until the lane scopes the resolver's answer to the token(s) THIS turn
    actually typed."""
    from app.services.chatbot.lanes.escalation_services import _product_rows

    payload = {
        "resolutions": [
            _resolution(
                "SRTWB8004",
                matches=[{**_resolved_row("SRTWB8004", brand="sorento"), "entity_type": "product", "match_tier": "exact"}],
            ),
            _resolution(
                "SRTWC60630-SH",
                alternatives=[_alt_row("SRTWC6030-SH-BL"), _alt_row("SRTWC6030-SH-UF")],
            ),
        ]
    }
    resolved, did_you_mean = _product_rows(payload)
    assert resolved and resolved[0]["canonical_code"] == "SRTWB8004"
    assert did_you_mean and {r["canonical_code"] for r in did_you_mean} == {
        "SRTWC6030-SH-BL",
        "SRTWC6030-SH-UF",
    }

    ctx = _ctx(
        # An EXACT catalogue word, not a family word: the team ladder must assign with no
        # question, so the product-masking bug this test targets is not hidden behind an
        # unrelated team clarify (a family word would ask first and never reach the body).
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[
            {
                "raw": "SRTWB8004",
                "hint": "product",
                "canonical_code": "SRTWB8004",
                "current_message": False,
                "confident": True,
            },
            _product_entity("SRTWC60630-SH"),
        ],
    )
    item = _item(team="warehouse")
    services = _services(gate={"resolved": resolved, "did_you_mean": did_you_mean})

    result = run(ctx, item, services=services)

    assert result["arm"] == "product_pick", (
        "the TYPED code did not resolve; the did-you-mean must be armed for IT, not "
        f"skipped because a carried code happened to resolve: {result!r}"
    )
    offered = {o.get("code") for o in result["pending"]["options"]}
    assert offered == {"SRTWC6030-SH-BL", "SRTWC6030-SH-UF"}, (
        f"the offer must be for the TYPED code's own candidates only: {offered!r}"
    )
    for action in result["actions"]:
        assert action["kind"] not in ("assign_conversation", "add_comment"), (
            "the carried product must never be assigned as if it answered the typed, "
            f"still-unresolved code: {result['actions']!r}"
        )


# --------------------------------------------------------------------------- #
# Console pass finding 2, 13 Sep 2026: "SRTWT2643 photo" -> the MISS lane's own
# did-you-mean offer ends "...or would you like me to escalate to marketing
# product team?" (chatbot.turns 1699b69d-bd49-47ca-be67-45cfcb5d5a31, v16
# prompt), but the persisted `product_pick` question's payload never recorded
# WHICH team it offered - so a later "yes" has nothing to resume onto.
# --------------------------------------------------------------------------- #


def test_console_finding2_the_miss_lane_persists_the_team_it_offered_to_escalate_to() -> None:
    """Console pass finding 2, item 1. `miss_suggest._attach_question` freezes the
    did-you-mean rows and `payload.keep` / `domain` / `offer_id` / `picked` - everything
    the pick needs to resume the PRODUCT question - but not the team `build_suggest_offer`
    named in the reply text it composed ("...or would you like me to escalate to
    marketing product team?"). RED until the payload also carries `then.escalate.
    offer_team`, the SAME shape the escalation lane's own did-you-mean payload already
    uses (`escalation._product_pick_ask`), so `dialogue/open_question._product_pick`'s
    existing deferred-escalation read (`payload.then.escalate`) can resume onto it without
    a new field name.

    Built directly against `_attach_question`, the one function that composes this
    payload (`lanes/business/miss_suggest.py`) - `build_suggest_offer`'s own captures are
    graded byte for byte by 76 fixtures and may not grow a key (the module's own
    docstring), so the team has to reach the question from OUTSIDE that node, which is
    exactly what `_attach_question` is for."""
    from app.services.chatbot.lanes.business.miss_suggest import _attach_question

    item = {
        "suggest_offer": True,
        "suggest_selection_context": "suggest_offer",
        "suggest_response": (
            'Couldn\'t find "SRTWT2643" (product). Did you mean:\n'
            "1. SRTWT2632\n2. SRTWT2633\n3. SRTWT2634\n"
            "Reply with a code to continue, or would you like me to escalate to "
            "marketing product team?"
        ),
        "suggest_quick_reply": "SRTWT2632,SRTWT2633,SRTWT2634,Yes escalate,No it's okay",
        "suggest_last_result_set": [
            {
                "idx": 1,
                "label": "SRTWT2632",
                "value": "SRTWT2632",
                "product": "SRTWT2632",
                "uuid": "a3055471-0000-0000-0000-000000000000",
                "entity_type": "product",
            },
            {
                "idx": 2,
                "label": "SRTWT2633",
                "value": "SRTWT2633",
                "product": "SRTWT2633",
                "uuid": None,
                "entity_type": "product",
            },
            {
                "idx": 3,
                "label": "SRTWT2634",
                "value": "SRTWT2634",
                "product": "SRTWT2634",
                "uuid": None,
                "entity_type": "product",
            },
        ],
        "dym_offer": {
            "id": "1699b69d-bd49-47ca-be67-45cfcb5d5a31",
            "candidates": [],
            "picked": [],
        },
    }
    gate = {
        "compatible_entities": [
            {"code": "Product Photos", "entity_type": "attachment_type", "uuid": None},
        ],
    }
    parser = {
        "domain_hint": "product_attachment",
        "routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
    }

    result = _attach_question(item, parser=parser, gate=gate)

    question = result["open_question"]
    assert question["kind"] == "product_pick"
    payload = question["payload"]
    assert payload["offer_id"] == "1699b69d-bd49-47ca-be67-45cfcb5d5a31", payload
    assert payload["keep"] == [
        {
            "raw": "Product Photos",
            "hint": "attachment_type",
            "canonical_code": "Product Photos",
            "uuid": None,
            "current_message": True,
            "confident": True,
        }
    ], payload
    assert payload.get("then", {}).get("escalate", {}).get("offer_team") == "marketing_product", (
        f"the reply offered marketing_product by name - the persisted payload must say so, "
        f"or a later 'yes' has no team to resume onto: {payload!r}"
    )


def test_console_finding2_the_miss_lane_never_persists_a_team_the_offer_did_not_actually_put_on_the_wire() -> None:
    """Console pass finding 2, S10 (reviewer re-check of `b6e108634`): the mirror of the
    payload test above. `miss_suggest._attach_question` guards `then.escalate` on
    `answer.offer_named_escalation(item)` - a read of `item["suggest_quick_reply"]`, the
    field the customer's buttons actually render from - because several arms compose the
    "...or would you like me to escalate to {team} team?" SENTENCE and only some of them
    also put the "Yes, escalate" BUTTON on the wire. `lanes/business/answer.py` ~4052 is
    the real negative shape: a date-axis offer to a `customer_service` / `order_enquiries`
    routing composes the sentence but sets `suggest_quick_reply` to the bare date values,
    with no `_YES` / `_NO` appended at all - so a "yes" there answers nothing, and the
    persisted question must carry no `then` key to resume onto.

    Guard, confirmed by hand (security review round 5): forcing `offer_named_escalation`
    to always return `True` left this test failing (and every OTHER test in this file
    green), proving the gate was previously unexercised by any red test - this is that
    missing negative case, not a defect in the shipped code."""
    from app.services.chatbot.lanes.business.miss_suggest import _attach_question

    item = {
        "suggest_offer": True,
        "suggest_selection_context": "suggest_offer",
        "suggest_response": (
            "No delivery on 2026-08-01. This customer has delivery on 2026-08-15. "
            "Reply with a date to continue, or would you like me to escalate to "
            "customer service team?"
        ),
        # The real negative shape (`answer.py` ~4052): `axis == "date" and is_cs_order`
        # drops `_YES` / `_NO` from the wire entirely - bare date values only.
        "suggest_quick_reply": "2026-08-01,2026-08-15",
        "suggest_last_result_set": [
            {
                "idx": 1,
                "label": "2026-08-01",
                "value": "2026-08-01",
                "product": "2026-08-01",
                "display": "2026-08-01",
                "order_number": "SO-1001",
            },
            {
                "idx": 2,
                "label": "2026-08-15",
                "value": "2026-08-15",
                "product": "2026-08-15",
                "display": "2026-08-15",
                "order_number": "SO-1002",
            },
        ],
        "dym_offer": {"id": "date-offer-1", "candidates": [], "picked": []},
    }
    gate = {"compatible_entities": []}
    parser = {
        "domain_hint": "order",
        "routing": {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
    }

    result = _attach_question(item, parser=parser, gate=gate)

    payload = result["open_question"]["payload"]
    assert "then" not in payload, (
        f"the composed reply never put the escalate button on the wire - the persisted "
        f"payload must carry no `then` key at all, not an offer nobody was actually shown: "
        f"{payload!r}"
    )



# --------------------------------------------------------------------------- #
# D10, owner ruling (console pass, 13 Sep 2026, finding 6), NARROWED by reviewer round 9
# (finding measured on the stack DB, 13 Sep 2026): a `team_pick` THIS TURN ANSWERED
# carries the product the escalation named, even when the previous turn's own team
# (re-derived off `focus.domains`, `_carried_team`) differs from the team the pick just
# landed on - the D3 same-team gate is for a product left over from an UNRELATED earlier
# turn, and a team question the lane itself asked on a turn that named the product is a
# deferral of that SAME escalation, not a fresh one.
#
# Round 9 found the first cut too wide: `_resumed_team_pick` (c500b4398) fires off
# `_answered.handler == "team_pick"` plus the previous `open_question.kind == "team_pick"`
# ALONE, with no read of `expects` or the payload - so a bare "yes" to the ONE-team
# escalate offer (`expects: yes_no`) ALSO skips the D3 gate and reaches back into
# `focus.products`, carrying whatever the conversation happened to be about (measured: a
# stock turn on MWC7625-SH-S10/mocha, `focus.domains: [inventory]`, then a plain "ESCALATE
# TO MARKETING" the customer accepted with "yes" - carried MOCHA onto a team the
# escalation itself never named a product for).
#
# The narrowed contract (this round): the carry is now a RESOLVE OF THE QUESTION'S OWN
# PAYLOAD, not a re-read of `focus.products`. At ask time, `tail/compile_state.
# _ask_for_turn`'s `team_clarify` branch freezes the escalation's OWN resolved product
# code onto the `team_pick` question - `payload.product_code` - from a new clarify item
# field `clarify_product_code` (None/absent when the escalation resolved no product). On
# resume, the carry fires only when ALL of:
#
#     ctx.parse._answered.handler == "team_pick"
#     AND the previous open_question.kind == "team_pick"
#     AND the previous open_question.expects == "pick"    (the multi-team ask, D2's own
#                                                            ladder - never the plain
#                                                            one-team yes/no offer)
#     AND payload.product_code is truthy
#
# and it then resolves THAT code through `resolve_and_gate`, never `focus.products` at
# all. Everything else - a fresh team_pick with no `_answered` record, an `_answered` for
# a DIFFERENT open question, a multi-team pick whose OWN payload named no product - still
# falls through to the unchanged D3 same-team gate.
#
# Turn A (finding 6): "esclate to marketing about water tap of SRTWB8004" - the parser
# resolved SRTWB8004, then the family word "marketing" armed a three-way `team_pick`
# (marketing_product / marketing_form / marketing_promotion), `expects: pick`, payload
# `{"team": "purchasing", "domain": "master_products", "product_code": "SRTWB8004"}`.
# Turn B: "marketing product" resolves that `team_pick`, landing `marketing_product`.
# --------------------------------------------------------------------------- #


def _resolved_row_with_brand_name(
    code: str, *, brand_code: str, brand_name: str, company_id: str = "co-sorento", company_name: str = "Sorento"
) -> dict:
    return {
        "uuid": f"uuid-{code}",
        "canonical_code": code,
        "company_id": company_id,
        "company_name": company_name,
        "display": {"brand": {"brand_code": brand_code, "brand_name": brand_name}},
    }


def _resumed_team_pick_ctx(
    *,
    entities: list | None = None,
    expects: str = "pick",
    payload_product_code: str | None = "SRTWB8004",
    focus_product_code: str | None = "SRTWB8004",
    focus_domain: str | None = "master_products",
    team_options: list | None = None,
    landed_team: str = "marketing_product",
) -> dict:
    """Turn B's ctx: the finding 6 shape (a `team_pick` open, `_answered` recording that
    THIS turn resolved it), parametrised over the axes round 9 narrowed the gate to.
    `focus_product_code`/`focus_domain` are what the CONVERSATION was carrying
    (`focus.products`/`focus.domains`, the D3 axes) - under the narrowed contract these no
    longer decide the carry on their own; `payload_product_code` (the question's OWN
    frozen code) and `expects` (`pick` vs `yes_no`) are what do."""
    options = team_options or [
        {"idx": 1, "team": "marketing_product", "label": "Marketing Product"},
        {"idx": 2, "team": "marketing_form", "label": "Marketing Form"},
        {"idx": 3, "team": "marketing_promotion", "label": "Marketing Promotion"},
    ]
    payload = {"team": "purchasing", "domain": focus_domain}
    if payload_product_code is not None:
        payload["product_code"] = payload_product_code
    prev = _focus_previous_state(product_code=focus_product_code, domain=focus_domain)
    prev["open_question"] = {
        "kind": "team_pick",
        "options": options,
        "expects": expects,
        "asked_at_turn": 3,
        "asked_at": None,
        "payload": payload,
    }
    ctx = _ctx(
        routing={"suggested_team": landed_team, "suggested_agent": "general_enquiries"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=entities or [],
        prev_variables=prev,
    )
    answer = (
        {"resolved": True, "picks": [1]}
        if expects == "pick"
        else {"resolved": True, "yes_no": "yes"}
    )
    ctx["parse"]["_answered"] = {
        "before": {"kind": "team_pick", "expects": expects, "options": len(options), "quoted": False},
        "answer": answer,
        "after": {"escalate": True, "declined": False, "lane": "escalation"},
        "handler": "team_pick",
        "outcome": f"Routed to {landed_team}.",
    }
    return ctx


def test_d10_a_resumed_multi_team_pick_carries_the_products_own_frozen_code_over_the_previous_teams_gate() -> None:
    """D10, narrowed (live). RED on c500b4398: `_carried_brand` still reads
    `_carried_products(ctx)` (`focus.products`) for the resumed-pick carry, never
    `open_question.payload.product_code` - so today's code cannot be told apart from a
    world where the seam is asked about the wrong code. The call-args assertion below is
    what the narrowing has to make true: `resolve_and_gate` is asked about the code the
    QUESTION ITSELF froze. The previous state's OWN `focus.products` deliberately names a
    DIFFERENT code (`ZZTOLDFOCUS01`) than the question's frozen `payload.product_code`
    (`SRTWB8004`) - the two axes the round-9 narrowing tells apart - so a mechanism that
    still reads `focus.products` sends the seam the WRONG code and both assertions below
    catch it, rather than passing by coincidence because the fixture happened to reuse one
    code for both."""
    ctx = _resumed_team_pick_ctx(focus_product_code="ZZTOLDFOCUS01")
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_called_once()
    # The literal string "SRTWB8004" also sits, unrelated, inside the ctx's own
    # `open_question.payload.product_code` (it rides along on every call because
    # `_carry_ctx` shallow-copies `ctx` rather than stripping the session) - so the check
    # has to be the ACTUAL ENTITY the seam was asked to resolve, not a substring match
    # over the whole call repr.
    resolved_ctx = services.resolve_and_gate.call_args[0][0]
    resolved_codes = {
        e.get("canonical_code") or e.get("raw")
        for e in resolved_ctx["parse"]["output"]["entities"]
    }
    assert resolved_codes == {"SRTWB8004"}, (
        f"the seam must be asked to resolve the code the question's OWN payload froze, "
        f"not the stale ZZTOLDFOCUS01 `focus.products` was still carrying: {resolved_codes!r}"
    )
    assert result["arm"] == "human-intervention", result
    assert result["pending"] is None
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "sorento", (
        f"a resumed multi-team pick must carry the code its own payload froze: {body!r}"
    )
    second_send = result["actions"][-1]
    assert second_send["kind"] == "send_message"
    assert "Marketing Product team handling SORENTO" in second_send["text"], second_send["text"]


def test_d10_dry_run_the_resumed_carry_reaches_the_preview_and_the_same_copy() -> None:
    """D10, narrowed, dry run (D9's own rule: every READ in the ladder, including this
    one, runs on a dry run exactly as it does live). Same code-mismatch fixture as the
    live test above, for the same reason."""
    ctx = _resumed_team_pick_ctx(focus_product_code="ZZTOLDFOCUS01")
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services, dry_run=True)

    services.resolve_and_gate.assert_called_once()
    resolved_ctx = services.resolve_and_gate.call_args[0][0]
    resolved_codes = {
        e.get("canonical_code") or e.get("raw")
        for e in resolved_ctx["parse"]["output"]["entities"]
    }
    assert resolved_codes == {"SRTWB8004"}, resolved_codes
    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()

    second_send = result["actions"][-1]
    assert second_send["kind"] == "send_message"
    assert second_send.get("dry_run") is True
    assert "Marketing Product team handling SORENTO" in second_send["text"], second_send["text"]

    services.preview_assignee.assert_called_once()
    preview_body = services.preview_assignee.call_args[0][0]
    assert preview_body.get("brand_code") == "sorento", (
        f"the dry-run preview must carry the same brand the live draw would: {preview_body!r}"
    )
    assert preview_body.get("preview") is True, preview_body


def test_d10_narrow_a_one_team_yes_no_offer_never_carries_even_when_resumed() -> None:
    """Reviewer round 9, measured: the multi-team `team_pick` (`expects: pick`) is the
    lane's own ask about WHICH marketing team - a reply to it defers the SAME escalation
    request (D10). The plain one-team escalate offer (`expects: yes_no`, the bare "shall I
    escalate to X" accept/decline) is a DIFFERENT question, with no product_code on its
    own payload; answering IT with a yes must never smuggle in whatever the conversation
    was carrying (a stock turn on MWC7625-SH-S10/mocha, domain `inventory`) just because
    `_answered.handler` also reads `team_pick`. RED on c500b4398: today's
    `_resumed_team_pick` checks only `handler`+`kind`, ignoring `expects` and the payload
    entirely, so this exact shape still resolves and carries MOCHA - the whole tier-1 pool
    problem D3 exists to prevent, one layer down."""
    ctx = _resumed_team_pick_ctx(
        expects="yes_no",
        payload_product_code=None,
        focus_product_code="MWC7625-SH-S10",
        focus_domain="inventory",
        team_options=[{"idx": 1, "team": "marketing_product", "label": "Marketing Product"}],
    )
    item = _item(team="warehouse")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name(
                    "MWC7625-SH-S10", brand_code="mocha", brand_name="Mocha",
                    company_id="co-mocha", company_name="Mocha",
                )
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called(), (
        "a one-team yes/no offer's payload carries no product_code - the D10 carry must "
        "never fire off it, whatever the conversation happened to be carrying before"
    )
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body.get("brand_code") is None, (
        f"no brand must reach the body off a plain yes/no accept: {body!r}"
    )
    second_send = result["actions"][-1]
    assert "handling" not in second_send["text"], second_send["text"]


def test_d10_narrow_a_multi_team_pick_whose_payload_named_no_product_never_carries() -> None:
    """Reviewer round 9: the multi-team pick's OWN payload carries no `product_code` (the
    escalation this ask was armed for named no product itself) - a resumed pick must not
    then reach back into `focus.products` for a stock-turn leftover either. RED on
    c500b4398: today's carry still reads `_carried_products(ctx)`, never the payload, so a
    stock turn's MOCHA product still carries here too."""
    ctx = _resumed_team_pick_ctx(
        payload_product_code=None,
        focus_product_code="MWC7625-SH-S10",
        focus_domain="inventory",
    )
    item = _item(team="warehouse")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name(
                    "MWC7625-SH-S10", brand_code="mocha", brand_name="Mocha",
                    company_id="co-mocha", company_name="Mocha",
                )
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called()
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body.get("brand_code") is None, body


def test_d10_guard_a_fresh_team_pick_with_no_answered_record_still_drops_the_carry() -> None:
    """GREEN guard, must stay green: the SAME previous state (an open `team_pick`,
    payload carrying the frozen `product_code`) but `ctx.parse._answered` is absent - this
    is an ordinary fresh "escalate to marketing product" turn that happens to arrive while
    an unrelated team_pick is still open, not an answer to it, so D3's gate must still say
    no."""
    ctx = _resumed_team_pick_ctx()
    del ctx["parse"]["_answered"]
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called(), (
        "no `_answered` record means this turn never resumed the open team_pick - the D3 "
        "same-team gate must still apply and drop the carry"
    )
    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body.get("brand_code") is None, (
        f"with no answered record the previous team (purchasing) still differs from the "
        f"landed one (marketing_product) - nothing must carry: {body!r}"
    )


def test_d10_n1_an_answered_product_pick_over_an_open_team_pick_question_never_carries() -> None:
    """N1 pin, guard: `_answered.handler` must be exactly `team_pick` - a turn that
    resumed a DIFFERENT open question (a `product_pick`) while a stale `team_pick` also
    happens to sit in the previous state must not read as the D10 resumption. Not
    reachable in practice (only one question is ever open, D6/AC-1014) but pinned as the
    discriminator's own boundary, the same defence `_deferred_escalation` applies to its
    own handler check. GUARD, already green under both the old and the narrowed gate -
    kept here so the narrowing cannot regress it silently."""
    ctx = _resumed_team_pick_ctx()
    ctx["parse"]["_answered"]["handler"] = "product_pick"
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called()
    body = _next_assignee_body(services)
    assert body.get("brand_code") is None, body


def test_d10_n1_an_answered_team_pick_over_a_previous_product_pick_question_never_carries() -> None:
    """N1 pin, guard: the previous open question's own `kind` must also say `team_pick` -
    a stale `_answered` record naming `team_pick` with the SESSION's open question
    actually a `product_pick` must not carry either. GUARD, already green."""
    ctx = _resumed_team_pick_ctx()
    ctx["session"]["session_vars"]["variables"]["open_question"]["kind"] = "product_pick"
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    services.resolve_and_gate.assert_not_called()
    body = _next_assignee_body(services)
    assert body.get("brand_code") is None, body


def test_d10_the_lane_freezes_the_resolved_products_code_on_the_team_clarify_ask() -> None:
    """New contract (reviewer round 9, item 5): the `team_clarify` question the lane arms
    THIS turn must carry the product this escalation resolved, so a resumed pick can find
    it again without reaching back into `focus.products` at all. D6 already resolves the
    product before the team ladder runs (the product-first order); this only adds the ONE
    field `tail/compile_state._ask_for_turn` needs to freeze it onto the `team_pick`
    payload. RED on c500b4398: `_human_intervention`'s clarify branch builds `clarify`
    with no `clarify_product_code` key at all."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="purchasing")
    services = _services(
        gate={
            "resolved": [
                _resolved_row_with_brand_name("SRTWB8004", brand_code="sorento", brand_name="SORENTO")
            ],
            "did_you_mean": [],
        }
    )

    result = run(ctx, item, services=services)

    assert result["arm"] == "clarify", result
    assert result["clarify"] is not None
    assert result["clarify"].get("clarify_product_code") == "SRTWB8004", (
        f"the team_clarify ask must freeze the code this escalation resolved: {result['clarify']!r}"
    )


def test_n4_a_production_dry_run_whose_ladder_raises_is_never_swallowed(monkeypatch) -> None:
    """N4 (review round 8). D9's dry-run READS are guarded only where a SEAM can fail
    (`_resolve_product`, `_carried_brand`, the `preview_assignee` call itself) - AC-1142's
    own rule is that a RESOLVER failure degrades, never a genuine LANE DEFECT. The
    session-open/bundle-build `try` at `run()`'s dry-run branch (escalation.py ~616) is
    narrower still: it wraps opening the unit of work, not `_human_intervention` itself,
    so a raise from inside the ladder - a real bug, not a seam failure - must surface
    uncaught, and the session it opened must still be rolled back and closed by
    `production_session`'s own `with` (H56's unit-of-work rule, ~escalation.py 626-630)."""
    from app.services.chatbot.lanes import escalation as escalation_mod

    class _StubSession:
        def __init__(self) -> None:
            self.rolled_back = False
            self.closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    sessions: list[_StubSession] = []

    def _factory() -> _StubSession:
        session = _StubSession()
        sessions.append(session)
        return session

    def _boom(_ctx: dict, _landed_item: dict) -> dict:
        raise RuntimeError("a genuine lane defect, not a seam failure")

    monkeypatch.setattr(escalation_mod, "_next_assignee_body", _boom)

    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="warehouse")

    with pytest.raises(RuntimeError, match="a genuine lane defect"):
        escalation_mod.run(ctx, item, dry_run=True, session_factory=_factory)

    assert len(sessions) == 1, sessions
    assert sessions[0].rolled_back is True, (
        "production_session must roll back on the way out of a raise from the ladder"
    )
    assert sessions[0].closed is True, (
        "production_session must close the session whatever happened inside the ladder"
    )
