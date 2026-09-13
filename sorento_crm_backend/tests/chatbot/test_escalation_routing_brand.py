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


def test_ac1127_no_product_named_but_the_previous_team_matches_the_landed_one_carries_it() -> None:
    """AC-1127 (journey step 4/5, no photo this turn): the previous turn's OWN routing
    (`prev_variables.routing`, distinct from THIS turn's derived/inherited `ctx.output.
    routing`) already sat on `marketing_product`, the family word `marketing` lands there
    too (AC-1114's ladder) - so the previously-resolved brand `mocha` carries into the body.
    RED today: nothing threads a persisted brand/product forward at all; the lane has no
    read of `prev_variables.routing_brand` for this purpose. Compound with AC-1114: today
    this fixture also fails at the `arm` assertion (the family branch still clarifies
    instead of narrowing to the previous member) - both land together, on S2 and S5."""
    ctx = _ctx(
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables={
            "routing": {"suggested_team": "marketing_product"},
            "routing_brand": "mocha",
        },
    )
    item = _item(team="marketing_product")
    services = _services(gate={"resolved": [], "did_you_mean": []})

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["brand_code"] == "mocha", (
        f"the previous turn's brand must carry when its team equals the LANDED team: {body!r}"
    )


def test_ac1128_no_product_and_the_previous_team_differs_from_the_landed_one_carries_nothing() -> None:
    """AC-1128 (journey step 6): a stock (warehouse) turn, then "escalate to marketing"
    lands on `marketing_product` (AC-1113's open-offer half, or a direct pick) - the
    previous team (`warehouse`) does not match the LANDED team, so brand stays None (the
    whole tier-1 pool). Not a defect on today's code by itself (nothing carries a brand at
    all yet), but pinned separately from AC-1127 so the two cannot be confused (plan: "make
    the assertion hinge on the LANDED team")."""
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[],
        prev_variables={
            "routing": {"suggested_team": "warehouse"},
            "routing_brand": "sorento",
        },
    )
    item = _item(team="warehouse")
    services = _services(gate={"resolved": [], "did_you_mean": []})

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body.get("brand_code") is None, (
        f"the previous turn's team (warehouse) differs from the LANDED team "
        f"(marketing_product) - nothing must carry: {body!r}"
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
