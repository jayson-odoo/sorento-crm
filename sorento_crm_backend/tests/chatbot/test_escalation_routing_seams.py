"""PLAN-chatbot-escalation-routing.md, "Seams and safety" + S6 replay. AC-1141, AC-1142,
AC-1144.

RED, written before the coder's slices (Phase 2, test-first). AC-1143 (the H26/H27 strict
xfail flips) lives in `test_s5_escalation_lane.py`, edited directly rather than duplicated
here.

**AC-1144 deviation, said up front.** The plan's own wording ("fixtures for the 11 Sep 12:55,
12:55, 12:56 turns and the 21 Aug turn, plus one Mocha-brand turn, in
`tests/fixtures/chatbot/*.json`") points at the vendored n8n-capture corpus
`tests/chatbot/_corpus.py` drives (`test_replay.py`'s `RUNNERS["output_exchange"]`) - JSON
files shaped `{source, input, expected}` with a `When Executed by Another Workflow` node.
None of these five turns has a real n8n capture (the 21 Aug one is even sourced from an old
n8n trace, not this port), so a fixture there would have to be `"reasoned"` (hand-written),
which `test_replay.py`'s own docstring says never gates the suite - exactly the outcome a RED
test-first file must not produce. This file instead pins the same five turns directly as
pytest functions over the real evidence
(`documentation/plans/chatbot/evidence/escalation-routing-real-turns.json`), chaining the
real head (`test_escalation_routing_head.py`'s `_post_process`) into the real lane
(`escalation.run`) exactly as `engine.run_turn` would - substituting the vendored-corpus
mechanism, not extending it. Flagged for the coder/captain: if `test_replay.py`'s corpus
fixtures are wanted in addition, that is new scope beyond this red pass.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.head.output_exchange import post_process, suggest_follow_up
from app.services.chatbot.lanes.escalation import run
from tests.chatbot.test_escalation_routing_brand import _next_assignee_body, _product_entity, _resolved_row
from tests.chatbot.test_escalation_routing_head import (
    TURN_1_PARSER_RAW,
    TURN_1_PREVIOUS_STATE,
    TURN_3_PARSER_RAW,
    TURN_3_PREVIOUS_STATE,
    _decide_ctx,
)
from tests.chatbot.test_s5_escalation_lane import _ctx, _item, _services

# --------------------------------------------------------------------------- #
# AC-1141 / H37: a dry run reaches no side-effecting seam, over every shape above
# --------------------------------------------------------------------------- #


def _plain_assign_shape() -> tuple[dict, dict]:
    return (
        _ctx(
            routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
            parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        ),
        _item(team="warehouse"),
    )


def _team_clarify_shape() -> tuple[dict, dict]:
    return (
        _ctx(
            routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
            parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        ),
        _item(team="purchasing"),
    )


def _product_resolve_shape() -> tuple[dict, dict]:
    return (
        _ctx(
            routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
            parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
            escalation={"is_escalation_confirmation": True, "company_pick": None},
            entities=[_product_entity("SRTWB8004")],
        ),
        _item(team="customer_service"),
    )


def _product_not_found_shape() -> tuple[dict, dict]:
    return (
        _ctx(
            routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
            parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
            entities=[_product_entity("SRTWC60630-SH")],
        ),
        _item(team="warehouse"),
    )


DRY_RUN_SHAPES = {
    "plain_assign": _plain_assign_shape,
    "team_clarify": _team_clarify_shape,
    "product_resolve": _product_resolve_shape,
    "product_not_found": _product_not_found_shape,
}


@pytest.mark.parametrize("shape", DRY_RUN_SHAPES, ids=list(DRY_RUN_SHAPES))
def test_ac1141_a_dry_run_reaches_no_seam_for_every_new_shape(shape: str) -> None:
    """AC-1141 / H37. All four shapes are GREEN today, and for two different reasons:
    `plain_assign` and `team_clarify` because the dry-run gate already exists
    (`test_dry_run_never_reaches_next_assignee` proves the mechanism); `product_resolve`
    and `product_not_found` only because `resolve_and_gate` is not wired AT ALL yet (H26 -
    see `test_escalation_routing_brand.py`), so there is trivially nothing to call under a
    dry run either. Kept as a GUARD: once the coder wires the resolver (S3/S4), it must be
    wired BEHIND this same `dry_run` check, and this parametrisation is what would catch a
    seam added in front of it instead."""
    ctx, item = DRY_RUN_SHAPES[shape]()
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    run(ctx, item, services=services, dry_run=True)

    services.resolve_and_gate.assert_not_called()
    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-1142: a raising resolver degrades, never fails the turn
# --------------------------------------------------------------------------- #


def test_ac1142_a_raising_resolver_degrades_instead_of_raising_out_of_run() -> None:
    """AC-1142: the resolve call uses the production bundle's resolver; a resolver error
    must degrade to "not found" (or brand None) rather than a failed turn. RED today for
    the same reason as `test_escalation_routing_brand.py`'s AC-1121 tests: the seam is
    never even reached, so there is nothing to degrade FROM - the `assert_called_once` below
    is what proves the coder's slice actually attempted the call before catching the raise."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="customer_service")
    services = _services()
    services.resolve_and_gate.side_effect = RuntimeError("resolver seam is down")

    result = run(ctx, item, services=services)  # must not raise

    services.resolve_and_gate.assert_called_once()
    assert result["arm"] in ("human-intervention", "product_pick", "clarify"), result
    if result["arm"] == "human-intervention":
        body = _next_assignee_body(services)
        assert body.get("brand_code") is None, (
            f"a raising resolver must degrade to no brand, never propagate a half-read: {body!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1144: the five real turns, replayed head-to-lane (see the module docstring for
# why this substitutes the vendored n8n-capture corpus rather than extending it)
# --------------------------------------------------------------------------- #


def _replay_turn(parser_raw: dict, previous_state: dict, *, message: str, lane_services) -> dict:
    """`engine.run_turn`'s own order for an escalation turn: the head decides the verb and
    the derived routing, `route.decide` sends a `request_for_help`-with-team turn to the
    lane, and the lane decides team/brand. `_decide_ctx` is the SAME helper
    `test_escalation_routing_head.py` uses, so a head-level regression there shows up here
    too rather than being masked by a second implementation of the wiring.

    `_parser_raw` is stamped by `post_process` onto the BLOCK it returns
    (`output["_parser_raw"] = parser_raw_snapshot` in `output_exchange.py`, where `output`
    is the `{output: o}` wrapper, not `o` itself), and `suggest_follow_up` returns that same
    block, mutated, with the sibling key intact. `test_escalation_routing_head.py`'s own
    `_post_process` helper unwraps to `parse_block["output"]` for its callers' convenience
    and so drops `_parser_raw` on the floor - fine for that file's assertions, which never
    read it, but wrong here: `_replay_turn` needs the WHOLE block, so it calls `post_process`
    and `suggest_follow_up` directly rather than going through that helper.
    """
    parent_input = {
        "latest_user_message": message,
        "contact_id": "ZZT-esc-head-1",
        "previous_conversation_state": previous_state,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]
    ctx = _decide_ctx(qf)
    # `_person_routing` reads `ctx.parse._parser_raw` for the pre-derivation team word
    # (AC-815), the same way `engine.build_ctx(parse=parse_block)` threads the WHOLE block
    # (including its `_parser_raw` sibling key) onto `ctx["parse"]` in production.
    ctx["parse"]["_parser_raw"] = parse_block.get("_parser_raw")
    item = {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": "out_of_scope",
    }
    return run(ctx, item, services=lane_services)


def test_ac1144_turn_1_11sep_1255_resolves_the_did_you_mean_before_any_assignment() -> None:
    """`turn_1_11sep_1255`: SRTWC60630-SH does not resolve - the reply is the did-you-mean
    picker, deferred escalation attached, zero assignment actions this turn."""
    did_you_mean = [
        _resolved_row("SRTWC6030-SH-BL", brand="sorento"),
        _resolved_row("SRTWC6030-SH-UF", brand="sorento"),
        _resolved_row("SRTWC6030-SH-MW", brand="sorento"),
        _resolved_row("SRTWC6030-SH-MK", brand="sorento"),
        _resolved_row("SRTWC6030-SH-MG", brand="sorento"),
    ]
    services = _services(gate={"resolved": [], "did_you_mean": did_you_mean})

    result = _replay_turn(
        TURN_1_PARSER_RAW,
        TURN_1_PREVIOUS_STATE,
        message="ESCALTE TO MARKETING BIDET SEAT COVER FOR SRTWC60630-SH",
        lane_services=services,
    )

    assert result["arm"] == "product_pick", result
    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()


def test_ac1144_turn_3_11sep_1256_asks_which_marketing_team_never_purchasing() -> None:
    """`turn_3_11sep_1256`: the confirmation flag is ignored (no offer open), the family
    word `marketing` with a previous team `purchasing` outside it asks over the three
    marketing teams - never the old defect's silent assignment to `purchasing`."""
    services = _services()

    result = _replay_turn(
        TURN_3_PARSER_RAW,
        TURN_3_PREVIOUS_STATE,
        message="ESCALATE TO MARKETING",
        lane_services=services,
    )

    assert result["arm"] == "clarify", result
    assert result["pending"]["kind"] == "team_clarify", result["pending"]
    services.next_assignee.assert_not_called()


def test_ac1144_turn_4_21aug_resolves_sorento_brand_and_lands_marketing_product() -> None:
    """`turn_4_21aug_n8n`: SRTWB8004 resolves (brand SORENTO), previous team
    `customer_service` (outside the exact-word case, irrelevant here since the word IS a
    catalogue member) - lands `marketing_product` with brand `sorento`, never null."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("SRTWB8004", brand="sorento")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "sorento", body


def test_ac1144_a_mocha_brand_turn_lands_marketing_product_with_brand_mocha() -> None:
    """The fifth, hand-added turn (plan "roster facts"): `MWC7625-SH-S10`, a Mocha-brand
    product under the Sorento company - same shape as the 21 Aug turn, Mocha brand."""
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        entities=[_product_entity("MWC7625-SH-S10")],
    )
    item = _item(team="customer_service")
    services = _services(gate={"resolved": [_resolved_row("MWC7625-SH-S10", brand="mocha")], "did_you_mean": []})

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    body = _next_assignee_body(services)
    assert body["team_code"] == "marketing_product", body
    assert body["brand_code"] == "mocha", body
