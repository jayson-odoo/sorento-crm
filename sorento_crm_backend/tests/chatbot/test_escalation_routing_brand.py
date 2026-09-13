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


# --------------------------------------------------------------------------- #
# Security review, S1 and its reply companion, S3. Written on the tester's
# own branch after a merge of the coder's slices (head 9742167a8), so these are
# RED against the shipped implementation, not against a stub. Topic: AC-1130
# hardening (S1, item 1 and its reply companion, item 6) and the did-you-mean
# cap (S3, item 3).
# --------------------------------------------------------------------------- #


def _malicious_raw() -> str:
    """A 300 char typed code carrying a newline, a carriage return, a tab, and the frozen
    offer open phrase (`output_exchange._OFFERED_ESCALATION_RE`) placed well past any
    sane truncation point, padded to the full length with filler.

    An attacker typing this as a product code is testing two things at once: whether the
    PIC comment and the clarify reply stay one bounded line (S1), and whether the phrase
    could ever reopen a stale offer on a LATER turn if this text ever reached a state's
    `response` field (the legacy `offer_is_open` regex path, still read "during the
    migration window").
    """
    prefix = "A" * 40 + "\n" + "B" * 40 + "\r" + "C" * 40 + "\t" + "D" * 40
    phrase = "would you like me to escalate"
    padded = prefix + " " + phrase + " "
    raw = padded + "E" * (300 - len(padded))
    assert len(raw) == 300
    return raw


def test_s1_pic_comment_product_line_is_bounded_and_never_reopens_a_stale_offer() -> None:
    """Security review S1 (AC-1130 hardening), item 1. `_product_line` embeds the typed
    code verbatim with no cap and no whitespace collapse (`escalation.py`'s own
    `_product_line`), so a 300 char raw with control characters and the frozen offer
    phrase reaches the PIC comment whole. RED until the coder bounds it to one line, at
    most 100 chars of the typed text, and the phrase cannot survive to make
    `offer_is_open` read a later turn's stale state as an open offer."""
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

    assert "\n" not in typed_part and "\r" not in typed_part and "\t" not in typed_part, (
        f"the comment's Product line must collapse whitespace to single spaces: {typed_part!r}"
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
    """Security review S1, item 6 (the reply half): `_product_pick_ask`'s
    `lead = f"I could not find *{typed}*."` embeds the SAME raw typed code with no cap,
    on the did-you-mean ask the customer receives when their code does not resolve.
    RED for the same reason as the comment test above."""
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

    assert "\n" not in typed_in_lead and "\r" not in typed_in_lead and "\t" not in typed_in_lead, (
        f"the clarify reply must be single line where it names the typed code: {typed_in_lead!r}"
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
