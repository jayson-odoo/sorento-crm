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
from app.services.chatbot.head.route import decide
from app.services.chatbot.lanes.escalation import run
from tests.chatbot.test_escalation_routing_brand import _next_assignee_body, _product_entity, _resolved_row
from tests.chatbot.test_escalation_routing_head import (
    TURN_1_PARSER_RAW,
    TURN_1_PREVIOUS_STATE,
    TURN_3_PARSER_RAW,
    TURN_3_PREVIOUS_STATE,
    _decide_ctx,
    _full_emission,
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


# --------------------------------------------------------------------------- #
# Security review, S2 (real DB error, AC-1142), N2 (SLA agent), N4 (session
# identity). Written on the tester's own branch after a merge of the coder's
# slices (head 9742167a8), so these are RED against the shipped implementation.
# --------------------------------------------------------------------------- #


def test_s2_a_real_dbapi_error_from_the_resolver_never_poisons_the_lanes_session(
    session_factory,
) -> None:
    """Security review S2 (AC-1142, real DB error). `_resolve_product`'s
    `except Exception:` catches a real `sqlalchemy.exc.DBAPIError` fine, but a failed
    statement on a Postgres session leaves that session's TRANSACTION aborted - every
    later statement on the SAME session raises `PendingRollbackError` until it is rolled
    back. `_resolve_product` never rolls the session back, so the two seams `_assign`
    calls NEXT - `next_assignee` and `sla_create`, on the SAME session
    (`production_session`'s whole point) - are the ones that actually fail, and the turn
    that was supposed to degrade gracefully raises instead.

    Built on the PRODUCTION bundle (`escalation_services.build`), the way
    `test_s5_escalation_seams.py::TestProductionSeams` draws the assignee, so the session
    is the real unit of work under test, not a mock standing in for one. The resolver's
    OWN network call is stubbed at the business lane's `production_services` boundary (so
    no real resolver logic is needed to prove the point) but the failure itself is a REAL
    bad statement executed on the lane's own session - a genuine `ProgrammingError`, not a
    stand-in exception. `next_assignee` and `sla_create` are then required to make a REAL
    round trip on that SAME session, which only succeeds if it was rolled back.
    """
    from sqlalchemy import text as sql_text

    from app.services.chatbot.lanes import escalation_services
    from app.services.chatbot.lanes.business import services as business_services_mod
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    db = session_factory()

    def _boom(_body):
        db.execute(sql_text("SELECT * FROM zzt_table_that_does_not_exist_at_all"))
        return {}

    def fake_production_services(passed_db, *, space_id=None):
        return ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=_boom, probe=lambda **_: {}
        )

    original_production_services = business_services_mod.production_services
    business_services_mod.production_services = fake_production_services
    try:
        real_services = escalation_services.build(db)
        calls = {"next_assignee": 0, "sla_create": 0}

        def counting_next_assignee(body):
            calls["next_assignee"] += 1
            # a REAL round trip on the SAME session `_resolve_product`'s catch left
            # possibly aborted - this raises PendingRollbackError today
            db.execute(sql_text("SELECT 1"))
            return {
                "assignee_id": "usr-pic-1",
                "assignee_respond_user_id": "respond-usr-1",
                "team_set_code": "CS",
                "brand_code": None,
                "company_id": None,
                "is_already_assigned": False,
            }

        def counting_sla_create(body):
            calls["sla_create"] += 1
            db.execute(sql_text("SELECT 1"))
            return {
                "id": "sla-row-1",
                "initiated_at": "2026-09-05T04:00:00+00:00",
                "due_at": "2026-09-05T08:00:00+00:00",
                "due_at_resolution": "2026-09-06T04:00:00+00:00",
            }

        services = escalation_services.EscalationServices(
            resolve_and_gate=real_services.resolve_and_gate,
            next_assignee=counting_next_assignee,
            preview_assignee=real_services.preview_assignee,
            sla_create=counting_sla_create,
            team_members=real_services.team_members,
            staff_lookup=real_services.staff_lookup,
        )

        ctx = _ctx(
            routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
            parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
            entities=[_product_entity("SRTWB8004")],
        )
        item = _item(team="warehouse")

        result = run(ctx, item, services=services)  # must not raise

        assert result["arm"] == "human-intervention", (
            "the turn must still be assigned - a resolver failure degrades, it never "
            f"fails the turn: {result!r}"
        )
        assert calls == {"next_assignee": 1, "sla_create": 1}, (
            f"both downstream seams must still run, on the same session: {calls!r}"
        )
    finally:
        business_services_mod.production_services = original_production_services


def test_n2_sla_body_agent_code_matches_the_landed_teams_own_agent() -> None:
    """Security review N2. `_next_assignee_body` already reads the LANDED team's own
    agent off `context_item["agent_code"]` (AC-1129); `_sla_body` still reads
    `ctx.parse.output.routing.suggested_agent` unconditionally - the INHERITED agent -
    so the SLA row can name an agent the landed team does not have, the same class of
    defect AC-1129 closed for the round-robin body."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_form", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="purchasing")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    services.sla_create.assert_called_once()
    sla_body = services.sla_create.call_args[0][0]
    assert sla_body["agent_code"] == "marketing_form", (
        f"the SLA row's agent must be the LANDED team's own agent, never the inherited "
        f"general_enquiries: {sla_body!r}"
    )


def test_n4_the_resolvers_session_is_the_same_object_production_session_yielded(
    session_factory, monkeypatch
) -> None:
    """Security review N4 (scope pin). The production resolver seam closes over whatever
    `db` `escalation_services.build(db)` was handed; the identity chain from
    `production_session` through `production_services` to the resolver's own closure is
    what H56 depends on for the resolver to carry the contact's company scope. Pinned by
    IDENTITY so a future `SessionLocal()` swap anywhere on that chain fails this test."""
    from app.services.chatbot.lanes import escalation as escalation_mod
    from app.services.chatbot.lanes.business import services as business_services_mod
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    opened: list = []

    def factory():
        s = session_factory()
        opened.append(s)
        return s

    captured: dict = {}

    def spying_production_services(db, *, space_id=None):
        captured["db"] = db
        return ResolveGateServices(
            access_types=lambda **_: [],
            resolve_entity=lambda _body: {"resolutions": []},
            probe=lambda **_: {},
        )

    monkeypatch.setattr(business_services_mod, "production_services", spying_production_services)

    from app.api.v1.external import next_assignee as next_assignee_mod
    from app.services.sla_service import ConversationSLATrackingService

    async def fake_post_next_assignee(*, body, current_user, db):
        return {
            "assignee_id": "usr-pic-1",
            "assignee_respond_user_id": "respond-usr-1",
            "team_set_code": "CS",
            "brand_code": None,
            "company_id": None,
            "is_already_assigned": False,
        }

    class _Created:
        id = "sla-row-1"
        initiated_at = "2026-09-05T04:00:00+00:00"
        due_at = "2026-09-05T08:00:00+00:00"
        due_at_resolution = "2026-09-06T04:00:00+00:00"

    def fake_create_tracking(self, payload):
        return _Created()

    monkeypatch.setattr(next_assignee_mod, "post_next_assignee", fake_post_next_assignee)
    monkeypatch.setattr(ConversationSLATrackingService, "create_tracking", fake_create_tracking)

    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
    )
    # Respond.io's own message ids are NUMBERS (millisecond epochs); `_ctx`'s default is a
    # ZZT- string, and `ConversationSLATrackingCreate.message_id` coerces to int, so the
    # REAL sla_create this test exercises needs a numeric one (same fix
    # `test_s5_escalation_seams.py`'s own `MESSAGE_ID` constant carries).
    ctx["text"]["message"]["messageId"] = 1788015893412
    item = _item(team="warehouse")

    escalation_mod.run(ctx, item, session_factory=factory)

    assert "db" in captured, "the resolver seam was never invoked"
    assert opened, "the lane never opened a session through the factory"
    assert captured["db"] is opened[0], (
        "the resolver must receive the SAME session object production_session yielded, "
        "not a fresh SessionLocal() - a future swap must fail this identity check"
    )


# --------------------------------------------------------------------------- #
# Security review round 3, S5: the resolver body must be a narrow product-token
# lookup, never the business lane's full-message-understanding body verbatim.
# --------------------------------------------------------------------------- #


def test_s5_round3_the_resolver_body_is_a_narrow_product_lookup_not_the_customers_message(
    session_factory, monkeypatch
) -> None:
    """Security review round 3, item S5. `escalation_services._resolve_and_gate` builds
    its request with `lanes/business/resolve_gate.resolve_entity_body(ctx)` UNMODIFIED -
    the BUSINESS lane's own body builder, whose defaults are `spec_fallback: True` and
    `understand_phrase: True` (further AI processing over `query`), and whose `query` is
    `ctx.text.message.message.text` - the customer's FULL raw message. An escalation turn
    only ever wants "does this ONE code exist"; sending the whole message through
    spec-fallback and phrase-understanding is unnecessary AI spend on customer-controlled
    text and a wider processing surface than the lookup needs. RED until the escalation
    seam builds its own narrow body: `spec_fallback: False`, `understand_phrase: False`,
    `query` limited to the product token(s) this turn named."""
    from app.services.chatbot.lanes import escalation_services
    from app.services.chatbot.lanes.business import services as business_services_mod
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    db = session_factory()
    captured: dict = {}

    def fake_production_services(passed_db, *, space_id=None):
        def spying_resolve_entity(body):
            captured["body"] = body
            return {"resolutions": []}

        return ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=spying_resolve_entity, probe=lambda **_: {}
        )

    monkeypatch.setattr(business_services_mod, "production_services", fake_production_services)

    # Calling the seam directly - not the full `run()` - keeps this test about the BODY
    # shape only; `next_assignee` needs real seeded SLAPolicy/Team rows this file's other
    # tests do not carry, and that seeding is not what S5 is pinning.
    services = escalation_services.build(db)
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        entities=[_product_entity("SRTWB8004")],
        text="ESCALATE TO MARKETING FOR SRTWB8004, PLEASE HELP URGENTLY I NEED SOMEONE NOW",
    )
    item = _item(team="warehouse")

    services.resolve_and_gate(ctx, item)

    assert "body" in captured, "the resolver seam was never invoked"
    body = captured["body"]
    assert body.get("spec_fallback") is False, (
        f"an escalation code lookup must not fall back to spec search: {body!r}"
    )
    assert body.get("understand_phrase") is False, (
        f"an escalation code lookup must not run phrase understanding over the message: {body!r}"
    )
    query = body.get("query") or ""
    assert "URGENTLY" not in query.upper() and "PLEASE HELP" not in query.upper(), (
        f"the query must be the product token(s), never the customer's own message: {query!r}"
    )
    assert "SRTWB8004" in query.replace("-", "").upper() or "SRTWB8004" in [
        t.upper() for t in (body.get("tokens") or [])
    ], (
        f"the product token itself must still be searchable: {body!r}"
    )


# --------------------------------------------------------------------------- #
# Security review round 3, S3: the dry-run preview names the LANDED team's own
# pair, never the inherited one, and reaches no seam.
# --------------------------------------------------------------------------- #


def test_s3_round3_dry_run_preview_names_the_landed_team_and_agent_never_the_inherited_pair() -> None:
    """Security review round 3, item S3, strengthened by the re-check. `run(...,
    dry_run=True)`'s preview branch calls `_preview_routing`, which decides the landed
    team through `_person_routing` same as a live turn - but the customer-facing preview
    text (`ROUTED_TO_PIC_REPLY.format(team=...)`) and the comment it would send must
    still reflect the LANDED pair (AC-1129's own rule), not the inherited `purchasing` /
    `general_enquiries` this fixture starts from, and no WRITING seam may be reached at
    all (H37) - `preview_assignee` is the one read this branch is allowed."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_form", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="purchasing")
    services = _services()

    result = run(ctx, item, services=services, dry_run=True)

    services.resolve_and_gate.assert_not_called()
    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()

    second_send = result["actions"][-1]
    assert second_send["kind"] == "send_message"
    assert "marketing form" in second_send["text"].lower(), (
        f"the preview's customer-facing text must name the LANDED team, not the inherited "
        f"purchasing: {second_send['text']!r}"
    )
    comment = next((a for a in result["actions"] if a["kind"] == "add_comment"), None)
    if comment is not None:
        assert comment["text"].startswith("Team: marketing_form\n"), (
            f"the preview comment must name the landed team too: {comment['text']!r}"
        )

    # The body the READ-ONLY draw is asked to preview against must ALSO carry the landed
    # pair, not the inherited one - the whole reason `_preview_routing` re-derives
    # `_landed_item` before building it, rather than handing `preview_assignee` the
    # turn's own inherited `context_item`.
    services.preview_assignee.assert_called_once()
    preview_body = services.preview_assignee.call_args[0][0]
    assert preview_body["team_code"] == "marketing_form", preview_body
    assert preview_body["agent_code"] == "marketing_form", preview_body
    assert preview_body.get("brand_code") is None, preview_body


def test_s7_round3_dry_run_trace_facts_carry_the_preview_note(
    session_factory, system_settings_row, monkeypatch
) -> None:
    """Security review round 3, item S7 (the other half): the coder moved
    `PREVIEW_BRAND_NOTE` off the dry-run actions and onto the `looked_up` trace record's
    `facts` (`engine.py`'s own comment: "the console renders facts, and an action field
    had no reader") - driven through the REAL engine and the REAL escalation lane (only
    the parser is stubbed), because the fact is stamped by `engine.py`, not by
    `escalation.run()` itself, and a lane-unit call has no trace to assert on at all."""
    import json as _json

    from sqlalchemy import text as sql_text

    from app.models.chatbot_turn import ChatbotTurn
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot import trace as trace_mod
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.lanes.escalation import PREVIEW_BRAND_NOTE

    contact_id = "ZZT-esc-s7-dry-1"
    db = session_factory()
    db.execute(
        sql_text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_id, "phone": "+60000000098", "sv": _json.dumps({"variables": {}})},
    )
    db.commit()

    setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    setting.chatbot_completed_lanes = ["out_of_scope"]
    db.commit()

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    escalation_qf = {
        "message_type": "request_for_help",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": "wants marketing form",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": "marketing_form", "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }

    def fake_parse(config, user_block):
        return escalation_qf

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    envelope = Envelope(
        contact={"id": contact_id, "phone": "+60000000098", "custom_fields": []},
        is_test=True,
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": "ZZT-esc-s7-dry-msg-1",
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "escalate to marketing form"},
            },
        },
    )
    assert envelope.dry_run is True

    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    assert result.status == "done", result.error
    assert result.branch_kind == "out_of_scope"

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    looked_up = next(r for r in trace_mod.stage_records(row.trace) if r["stage"] == "looked_up")
    assert looked_up["facts"].get("preview_note") == PREVIEW_BRAND_NOTE, (
        f"a dry run that assigned must stamp the preview note on the looked_up trace "
        f"facts, not on the actions: {looked_up['facts']!r}"
    )


# --------------------------------------------------------------------------- #
# Console pass finding, 13 Sep 2026: "photo for SRTWB8004" -> no photo -> a
# one-team offer -> "yes" -> routed to customer_service on the real stack.
# AC-1104 / T7 / T12's fixtures did not catch it because they built the open
# question directly into a lane-unit ctx, never through the real five-key
# session shape a photo turn actually leaves behind - the same class of gap
# B1's kill test found in the old AC-1127 fixture. Built EXACTLY as persisted
# (`chatbot.turns` 9c6a50ba in `sorento_ai_automation_focus_full`, parser_raw
# from turn b77a6b2f): `focus.domains`, `focus.products`, `open_question` kind
# `team_pick` / `expects: yes_no`, and NOTHING else - no `routing`, `pending`,
# `selection_context` or `routing_brand` anywhere.
# --------------------------------------------------------------------------- #

CONSOLE_PREVIOUS_STATE = {
    "focus": {
        "domains": {
            "value": ["product_attachment"],
            "set_at_turn": 4,
            "set_at": None,
            "source": "reuse",
        },
        "products": {
            "value": [
                {
                    "raw": "SRTWB8004",
                    "hint": "product",
                    "canonical_code": "SRTWB8004",
                    "current_message": False,
                    "confident": True,
                }
            ],
            "set_at_turn": 4,
            "set_at": None,
            "source": "reuse",
        },
    },
    "open_question": {
        "kind": "team_pick",
        "expects": "yes_no",
        "options": [
            {
                "idx": 1,
                "team": "marketing_product",
                "label": "marketing_product",
                "domain": "product_attachment",
            }
        ],
        "payload": {"team": "marketing_product", "domain": "product_attachment"},
        "asked_at_turn": 4,
        "asked_at": None,
    },
    "ideation": None,
    "access_levels": [],
    "contains_flyer": False,
}


def _assert_only_five_keys(previous_state: dict) -> None:
    from app.services.chatbot.contracts import SESSION_VAR_KEYS

    assert set(previous_state) <= set(SESSION_VAR_KEYS), (
        f"the fixture must be a REAL persisted session - only {SESSION_VAR_KEYS}, never a "
        f"legacy routing/pending/selection_context/routing_brand mirror: {sorted(previous_state)!r}"
    )


def _run_console_turn(parser_raw: dict, *, text: str, gate_result: dict) -> tuple[dict, dict, dict]:
    """The real chain, in `engine.run_turn`'s own order: `_resolve_open_question` first
    (so a pick is applied as this turn's scope), then `post_process`, then
    `suggest_follow_up`, then `route.decide`, then the real escalation lane - the same
    shape `test_escalation_routing_seams.py::test_ac1144_*` already chains, extended with
    the question-resolution step those turns did not need."""
    from app.services.chatbot.engine import _resolve_open_question

    _assert_only_five_keys(CONSOLE_PREVIOUS_STATE)

    answered = _resolve_open_question(
        CONSOLE_PREVIOUS_STATE,
        parser_raw=parser_raw,
        emits_v3=False,
        referenced_result_set=None,
        turn_no=5,
    )
    parent_input = {
        "latest_user_message": text,
        "contact_id": "ZZT-esc-console-1",
        "previous_conversation_state": CONSOLE_PREVIOUS_STATE,
        "parser_emits_v3": False,
        "_answered": answered,
        "turn_no": 5,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]

    ctx = {
        "contact": {"id": "ZZT-esc-console-1", "phone": "+60123450099", "custom_fields": []},
        "text": {"message": {"messageId": "ZZT-esc-console-msg-1", "message": {"type": "text", "text": text}}},
        "session": {"session_vars": {"variables": CONSOLE_PREVIOUS_STATE}},
        "parse": {"output": qf, "_parser_raw": parse_block.get("_parser_raw")},
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }
    branch, _tier = decide(ctx)
    item = {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": branch,
    }

    services = _services(gate=gate_result)
    result = run(ctx, item, services=services)
    return qf, {"branch": branch}, {"result": result, "services": services}


def test_console_finding_a_bare_yes_over_a_team_pick_offer_routes_to_the_offered_team() -> None:
    """Console pass, 13 Sep 2026, item 1/2/3. "yes" over a one-team `marketing_product`
    offer, on a REAL five-key previous state, must route there - D3's same-team carry
    re-resolves the focus product through the seam for its brand. RED today: the lane's
    no-team-word acceptance arm (`_person_routing`, `if is_escalation_confirmation is
    True: return None`) trusts the ALREADY-DERIVED `team`, and `output_exchange`'s own
    routing chain has nothing to inherit from in a real session (no legacy `routing` key
    survives migration 517), so it falls to the hard default `customer_service` instead
    of ever reading `_offered_team(ctx)` / re-deriving from `focus.domains` - exactly the
    stack's own observed behaviour."""
    parser_raw = _full_emission(
        message_type="casual",
        is_affirmative=True,
        entities=[],
        entity_op="reuse",
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="yes",
    )
    gate_result = {
        "resolved": [
            {
                "uuid": "u-srtwb8004",
                "canonical_code": "SRTWB8004",
                "company_id": "c-sorento",
                "company_name": "Sorento",
                "display": {"brand": {"brand_code": "sorento"}},
            }
        ],
        "did_you_mean": [],
    }

    qf, branch_info, lane_info = _run_console_turn(parser_raw, text="yes", gate_result=gate_result)

    assert branch_info["branch"] == "out_of_scope", (
        f"a confirmed escalation must reach the escalation lane: {branch_info!r}"
    )
    result = lane_info["result"]
    services = lane_info["services"]
    assert result["pending"] is None, (
        f"the offer is accepted - no team_clarify, ever: {result['pending']!r}"
    )
    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert body["team_code"] == "marketing_product", body
    assert body["agent_code"] == "general_enquiries", body
    assert body["brand_code"] == "sorento", body
    services.resolve_and_gate.assert_called_once()
    called_with = str(services.resolve_and_gate.call_args)
    assert "SRTWB8004" in called_with, (
        f"the focus product must be the one asked about: {called_with}"
    )
    comment = next(a for a in result["actions"] if a["kind"] == "add_comment")
    assert comment["text"].startswith("Team: marketing_product\n"), comment["text"]
    routed_send = result["actions"][-1]
    assert "marketing product" in routed_send["text"].lower(), routed_send["text"]


def test_console_finding_companion_escalate_to_marketing_with_the_word_reaches_the_same_team() -> None:
    """Console pass companion, item 4: the SAME real previous state, but this turn types
    the family word "marketing" itself (`ESCALATE TO MARKETING`) instead of a bare "yes"
    - D2's offer-narrows-the-family rung (`_offered_team(ctx)` reads `open_question.
    payload.team` directly, never the broken derived routing), so this path is UNAFFECTED
    by the same-team carry defect the primary test pins. GREEN today: confirmed as a
    guard the console finding's OTHER half already passes."""
    parser_raw = _full_emission(
        message_type="request_for_help",
        is_affirmative=None,
        entities=[],
        routing={"suggested_team": "marketing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        user_goal="escalate to marketing",
    )
    gate_result = {
        "resolved": [
            {
                "uuid": "u-srtwb8004",
                "canonical_code": "SRTWB8004",
                "company_id": "c-sorento",
                "company_name": "Sorento",
                "display": {"brand": {"brand_code": "sorento"}},
            }
        ],
        "did_you_mean": [],
    }

    qf, branch_info, lane_info = _run_console_turn(parser_raw, text="ESCALATE TO MARKETING", gate_result=gate_result)

    assert branch_info["branch"] == "out_of_scope", branch_info
    result = lane_info["result"]
    services = lane_info["services"]
    assert result["pending"] is None, (
        f"the offer's own team narrows the family with no question: {result['pending']!r}"
    )
    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert body["team_code"] == "marketing_product", body
    assert body["agent_code"] == "general_enquiries", body
    assert body["brand_code"] == "sorento", body
    routed_send = result["actions"][-1]
    assert "marketing product" in routed_send["text"].lower(), routed_send["text"]


# --------------------------------------------------------------------------- #
# Console pass finding 2, 13 Sep 2026: "SRTWT2643 photo" -> the miss lane's
# did-you-mean offer, WITH the persisted `then.escalate.offer_team` test 1
# (`test_escalation_routing_brand.py`) pins - built as it will exist once that
# fix lands, so these four tests exercise the CONSUMPTION side independently.
# --------------------------------------------------------------------------- #

MISS_LANE_PREVIOUS_STATE = {
    "focus": {
        "domains": {
            "value": ["product_attachment"],
            "set_at_turn": 5,
            "set_at": None,
            "source": "reuse",
        },
        "products": {
            "value": [
                {
                    "raw": "SRTWT2643",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": False,
                    "confident": True,
                }
            ],
            "set_at_turn": 5,
            "set_at": None,
            "source": "reuse",
        },
    },
    "open_question": {
        "kind": "product_pick",
        "options": [
            {
                "idx": 1,
                "uuid": "a3055471-0000-0000-0000-000000000000",
                "label": "SRTWT2632",
                "value": "SRTWT2632",
                "product": "SRTWT2632",
                "domain": "product_attachment",
                "entity_type": "product",
            },
            {
                "idx": 2,
                "uuid": None,
                "label": "SRTWT2633",
                "value": "SRTWT2633",
                "product": "SRTWT2633",
                "domain": "product_attachment",
                "entity_type": "product",
            },
            {
                "idx": 3,
                "uuid": None,
                "label": "SRTWT2634",
                "value": "SRTWT2634",
                "product": "SRTWT2634",
                "domain": "product_attachment",
                "entity_type": "product",
            },
        ],
        "expects": "pick",
        "payload": {
            "keep": [
                {
                    "raw": "Product Photos",
                    "hint": "attachment_type",
                    "canonical_code": "Product Photos",
                    "current_message": True,
                }
            ],
            "domain": "product_attachment",
            "picked": [],
            "offer_id": "1699b69d-bd49-47ca-be67-45cfcb5d5a31",
            "then": {"escalate": {"offer_team": "marketing_product"}},
        },
        "asked_at_turn": 5,
        "asked_at": None,
    },
    "ideation": None,
    "access_levels": [],
    "contains_flyer": False,
}


def _run_miss_lane_turn(parser_raw: dict, *, text: str):
    """The same chained shape as the console finding above (real head, real
    `_resolve_open_question`, real `route.decide`), against `MISS_LANE_PREVIOUS_STATE`."""
    from app.services.chatbot.engine import _resolve_open_question

    _assert_only_five_keys(MISS_LANE_PREVIOUS_STATE)

    answered = _resolve_open_question(
        MISS_LANE_PREVIOUS_STATE,
        parser_raw=parser_raw,
        emits_v3=False,
        referenced_result_set=None,
        turn_no=6,
    )
    parent_input = {
        "latest_user_message": text,
        "contact_id": "ZZT-esc-miss-1",
        "previous_conversation_state": MISS_LANE_PREVIOUS_STATE,
        "parser_emits_v3": False,
        "_answered": answered,
        "turn_no": 6,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]

    ctx = {
        "contact": {"id": "ZZT-esc-miss-1", "phone": "+60123450099", "custom_fields": []},
        "text": {"message": {"messageId": "ZZT-esc-miss-msg-1", "message": {"type": "text", "text": text}}},
        "session": {"session_vars": {"variables": MISS_LANE_PREVIOUS_STATE}},
        "parse": {"output": qf, "_parser_raw": parse_block.get("_parser_raw")},
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }
    branch, _tier = decide(ctx)
    return answered, qf, branch, ctx


def test_console_finding2_yes_over_the_miss_lane_offer_routes_to_the_named_team() -> None:
    """Console pass finding 2, item 2. "yes" over the persisted did-you-mean-plus-escalate
    offer must route to `marketing_product` (the team the reply named), agent
    `general_enquiries`, brand None (no product resolved this turn - the customer
    answered the ESCALATE half, not a pick), and the question must be CONSUMED
    (`open_question_answered`), never a fresh `team_pick`. RED today:
    `engine._resolve_open_question`'s v1 synthesis only fires when `question.expects ==
    "yes_no"` (`ec2b3bb7b`); this question's `expects` is `"pick"` (it is a PRODUCT pick
    that also carries an escalate option), so a bare "yes" resolves nothing at all and the
    lane's acceptance path has no `_offered_team` read wired to it for this shape either."""
    parser_raw = _full_emission(
        message_type="casual",
        is_affirmative=True,
        entities=[],
        entity_op="reuse",
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        user_goal="yes",
    )

    answered, qf, branch, ctx = _run_miss_lane_turn(parser_raw, text="yes")

    assert branch == "out_of_scope", (
        f"a confirmed escalation over the offer must reach the escalation lane: {branch!r}"
    )
    assert qf.get("open_question_answered") == "product_pick", (
        f"the question must be CONSUMED, not left open for the next turn to re-answer: {qf!r}"
    )
    item = {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": branch,
    }
    services = _services(gate={"resolved": [], "did_you_mean": []})
    result = run(ctx, item, services=services)

    assert result["pending"] is None, (
        f"the offer is accepted - no team_pick, ever: {result['pending']!r}"
    )
    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert body["team_code"] == "marketing_product", body
    assert body["agent_code"] == "general_enquiries", body
    assert body.get("brand_code") is None, (
        f"no product was resolved on the ACCEPTING turn - brand stays None: {body!r}"
    )


def test_console_finding2_no_over_the_miss_lane_offer_declines_with_no_actions() -> None:
    """Console pass finding 2, item 3 (guard): "no" over the same offer must clear the
    question and decline - the pre-existing `offered_escalation and is_decline` arm in
    `output_exchange.py` already produces the canned "Escalation declined." copy and a
    TAG_ONLY branch with no lane call at all. Confirmed green today.

    N13 (security review round 5): the emission's `escalation_declined` key alone cannot
    tell "the OPEN-QUESTION HANDLER resolved this as a decline" from "the question was
    left unresolved and a SEPARATE, unrelated arm happened to produce the same copy" - the
    two are different mechanisms that could drift apart silently. Asserted directly on
    `answered["outcome"]` (`dialogue.open_question._product_pick`'s own return value)
    as well: `resolved` and `declined` both true, `escalate` false."""
    parser_raw = _full_emission(
        message_type="casual",
        is_affirmative=False,
        entities=[],
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="no",
    )

    answered, qf, branch, ctx = _run_miss_lane_turn(parser_raw, text="no")

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.resolved is True and outcome.declined is True, (
        f"the HANDLER itself must resolve this as a decline, not leave it unresolved: {outcome!r}"
    )
    assert outcome.escalate is False, outcome
    assert qf["escalation"].get("escalation_declined") is True, qf["escalation"]
    assert branch != "out_of_scope", (
        f"a decline must never reach the escalation lane: {branch!r}"
    )


def test_console_finding2_a_numbered_pick_over_the_miss_lane_offer_answers_the_product_not_the_escalation() -> None:
    """Console pass finding 2, item 4. "2" must pick `SRTWT2633` and re-run the photo ask
    as an ordinary product answer - the escalate option sits ALONGSIDE the did-you-mean
    pick, it is not implied by making one.

    MEASURED, not assumed to already hold (worth stating since the plan called this shape
    a green guard): today `dialogue.open_question._product_pick` treats ANY resolved pick
    against a `then.escalate` payload as resuming the escalation (`if truthy(team_word) or
    truthy(offer_team): outcome.escalate = True`), with no read of WHICH answer shape
    resumed it. That rule is right for the escalation lane's OWN did-you-mean (`team_word`
    payloads - the customer already asked for a person, and picking the code they meant is
    the only way to continue that request). It is wrong here: this offer's `offer_team`
    payload rides an ORDINARY product question the miss lane asked on a `business_query`
    turn, and a numbered pick only answers THAT - `apply_open_question_outcome`'s escalate
    branch fires anyway, and `is_escalation_confirmation` survives `suggest_follow_up`'s
    later retype of `message_type` back to `business_query`, so the turn still lands on
    the escalation lane. RED."""
    parser_raw = _full_emission(
        message_type="business_query",
        is_affirmative=None,
        entities=[],
        reference_positions=[2],
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="2",
    )

    answered, qf, branch, ctx = _run_miss_lane_turn(parser_raw, text="2")

    assert branch == "business_query", (
        f"a numbered pick answers the PRODUCT question, not the escalate offer - it must "
        f"never reach the escalation lane: {branch!r}, qf={qf!r}"
    )
    raws = {str(e.get("raw")) for e in (qf.get("entities") or [])}
    assert "SRTWT2633" in raws, (
        f"the pick must scope this turn to the product the customer chose: {raws!r}"
    )


def test_console_finding2_guard_a_plain_did_you_mean_pick_offer_never_manufactures_an_acceptance() -> None:
    """Console pass finding 2, item 5 (guard). A product_pick with NO escalate offer in
    its payload (a plain stock did-you-mean) has nothing for `_product_pick`'s deferred-
    escalation read to find, so `open_question.resolve` must not manufacture one. Scoped
    to the OPEN-QUESTION layer deliberately: a bare "yes" over THIS shape is ALSO caught by
    `suggest_follow_up`'s separate, pre-existing "plain yes on a picker = escalate to the
    carried team" rule (predates this feature and is not what this guard is about), so the
    lane still assigns SOMETHING further downstream - that is the old, documented
    behaviour for a picker with no offer info at all, not a claim this test makes or
    disturbs. What this test pins is narrower and already true today: the DEFERRED-
    ESCALATION mechanism itself (`_product_pick`'s `then.escalate` read) has nothing to
    resume here and must not invent a team."""
    from app.services.chatbot.engine import _resolve_open_question
    from app.services.chatbot.head.output_exchange import post_process, suggest_follow_up

    previous_state = {
        "focus": {
            "products": {
                "value": [],
                "set_at_turn": 2,
                "set_at": None,
                "source": "reuse",
            }
        },
        "open_question": {
            "kind": "product_pick",
            "options": [
                {
                    "idx": 1,
                    "uuid": None,
                    "label": "SRTKS6091",
                    "value": "SRTKS6091",
                    "product": "SRTKS6091",
                    "domain": "inventory",
                    "entity_type": "product",
                }
            ],
            "expects": "pick",
            "payload": {"domain": "inventory", "keep": [], "picked": []},
            "asked_at_turn": 2,
            "asked_at": None,
        },
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
    }
    _assert_only_five_keys(previous_state)
    parser_raw = _full_emission(
        message_type="casual",
        is_affirmative=True,
        entities=[],
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="yes",
    )

    answered = _resolve_open_question(
        previous_state, parser_raw=parser_raw, emits_v3=False, referenced_result_set=None, turn_no=3
    )

    assert answered["outcome"] is None, (
        f"a product_pick with no `then.escalate` payload has no team to resume onto - the "
        f"open-question layer must leave it unresolved, not invent an acceptance: {answered!r}"
    )


# --------------------------------------------------------------------------- #
# Owner regression, found on 532ab8a24: a numbered pick against a product_pick
# whose payload carries BOTH `then.escalate` and issue #708's `keep` (a sibling
# entity of a DIFFERENT type - an attachment_type, not a product) drops the
# kept sibling. `_product_pick`'s own `focus["products"]` fold
# (`entities + [e for e in keep if _is_product(e)]`, `open_question.py` ~287)
# only ever re-admits a kept PRODUCT; `apply_open_question_outcome`
# (`output_exchange.py` ~1171) reads only `outcome.focus["products"]` /
# `["customer"]` and never `outcome.keep` itself, so a non-product sibling
# never reaches `o["entities"]` at all - whether or not `then` is present.
# --------------------------------------------------------------------------- #


def _keep_pick_previous_state(*, with_then: bool) -> dict:
    payload: dict = {
        "keep": [
            {
                "raw": "Product Photos",
                "hint": "attachment_type",
                "uuid": "90e76894-8384-4186-a3f7-ef73667726ff",
                "canonical_code": "Product Photos",
                "current_message": True,
            }
        ],
        "domain": "product_attachment",
        "picked": [],
        "offer_id": "42267ebd-0000-0000-0000-000000000000",
    }
    if with_then:
        payload["then"] = {"escalate": {"offer_team": "marketing_product"}}
    return {
        "focus": {
            "domains": {
                "value": ["product_attachment"],
                "set_at_turn": 4,
                "set_at": None,
                "source": "reuse",
            },
            "products": {
                "value": [
                    {
                        "raw": "srtwc60630-sh",
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": False,
                        "confident": True,
                    }
                ],
                "set_at_turn": 4,
                "set_at": None,
                "source": "reuse",
            },
        },
        "open_question": {
            "kind": "product_pick",
            "options": [
                {
                    "idx": 1,
                    "uuid": "8e076b8e-ad64-495c-8919-4d06b734df60",
                    "label": "SRTWC6030-SH-BL",
                    "value": "SRTWC6030-SH-BL",
                    "product": "SRTWC6030-SH-BL",
                    "domain": "product_attachment",
                    "entity_type": "product",
                },
                {
                    "idx": 2,
                    "uuid": None,
                    "label": "SRTWC6030-SH-MG",
                    "value": "SRTWC6030-SH-MG",
                    "product": "SRTWC6030-SH-MG",
                    "domain": "product_attachment",
                    "entity_type": "product",
                },
                {
                    "idx": 3,
                    "uuid": None,
                    "label": "SRTWC6030-SH-MK",
                    "value": "SRTWC6030-SH-MK",
                    "product": "SRTWC6030-SH-MK",
                    "domain": "product_attachment",
                    "entity_type": "product",
                },
            ],
            "expects": "pick",
            "payload": payload,
            "asked_at_turn": 4,
            "asked_at": None,
        },
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
    }


def _run_keep_pick_turn(previous_state: dict, *, message_type: str):
    from app.services.chatbot.engine import _resolve_open_question

    _assert_only_five_keys(previous_state)

    parser_raw = _full_emission(
        message_type=message_type,
        is_affirmative=None,
        entities=[],
        reference_positions=[1],
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="1",
    )
    answered = _resolve_open_question(
        previous_state, parser_raw=parser_raw, emits_v3=False, referenced_result_set=None, turn_no=5
    )
    parent_input = {
        "latest_user_message": "1",
        "contact_id": "ZZT-esc-keep-1",
        "previous_conversation_state": previous_state,
        "parser_emits_v3": False,
        "_answered": answered,
        "turn_no": 5,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]

    ctx = {
        "contact": {"id": "ZZT-esc-keep-1", "phone": "+60123450099", "custom_fields": []},
        "text": {"message": {"messageId": "ZZT-esc-keep-msg-1", "message": {"type": "text", "text": "1"}}},
        "session": {"session_vars": {"variables": previous_state}},
        "parse": {"output": qf, "_parser_raw": parse_block.get("_parser_raw")},
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }
    branch, _tier = decide(ctx)
    return answered, qf, branch


def test_owner_regression_a_pick_over_a_deferred_escalation_keeps_the_sibling_attachment_type() -> None:
    """Owner regression, found on `532ab8a24`. Previous state exactly as specified: a
    `product_pick` offering three SRTWC6030-SH variants, `payload.keep` holding the
    `Product Photos` attachment_type entity that already resolved on the turn the picker
    was raised (issue #708), and `payload.then.escalate.offer_team` from the miss lane's
    combined offer (console pass finding 2). "1" picks `SRTWC6030-SH-BL`.

    Expected: the picked product AND the kept attachment_type both reach `qf["entities"]`,
    and the turn lands on the BUSINESS lane (a numbered pick answers the product question,
    never resumes the escalation - the same rule the console finding 2 companion pins).
    Asserted at BOTH the open-question outcome level (`answered["outcome"].keep` already
    carries the sibling correctly - `_product_pick` never lost it) and the derived
    entities level (`qf["entities"]` does not - `apply_open_question_outcome` only reads
    `outcome.focus["products"]` / `["customer"]`, and `_product_pick`'s own
    `focus["products"]` fold only re-admits a kept row that IS a product). Not driven
    through the real resolve gate (`lanes/business/gate.py`'s `'{domain}' requires
    [{missing}] but none resolved`, ~line 317) - the dropped entity is conclusive at the
    entities level, since that is the gate's own input; asserting at this level is the
    reviewer's own named alternative to a full resolver-stub drive.

    RED today: the outcome carries only the pick."""
    previous_state = _keep_pick_previous_state(with_then=True)

    answered, qf, branch = _run_keep_pick_turn(previous_state, message_type="business_query")

    outcome = answered["outcome"]
    assert outcome is not None and outcome.resolved is True
    kept_codes = {e.get("canonical_code") or e.get("raw") for e in outcome.keep}
    assert "Product Photos" in kept_codes, (
        f"the open-question layer itself must still carry the kept sibling: {outcome!r}"
    )

    assert branch == "business_query", (
        f"a numbered pick answers the product question, never the deferred escalation: {branch!r}"
    )
    raws = {str(e.get("raw")) for e in (qf.get("entities") or [])}
    assert "SRTWC6030-SH-BL" in raws, (
        f"the picked product must be in scope: {qf.get('entities')!r}"
    )
    assert "Product Photos" in raws, (
        f"issue #708's kept sibling must survive a pick even when the SAME question also "
        f"carries a deferred escalation - it is dropped entirely: {qf.get('entities')!r}"
    )
    picked_entity = next(e for e in qf["entities"] if e.get("raw") == "SRTWC6030-SH-BL")
    assert picked_entity.get("current_message") is True
    assert picked_entity.get("uuid") == "8e076b8e-ad64-495c-8919-4d06b734df60"


def test_owner_regression_companion_the_same_keep_without_a_deferred_escalation() -> None:
    """Owner regression companion: the SAME payload, minus `then` - a plain issue #708
    `keep` with no escalation offer riding alongside it. MEASURED, not assumed to already
    hold: the plan's own framing called this "green today", but the drop is in
    `apply_open_question_outcome` / `_product_pick`'s focus fold, neither of which reads
    `then` at all - the mixed-type keep (an attachment_type sibling beside a product pick)
    is what is untested, not the escalation payload beside it. RED for the same reason as
    the primary test above."""
    previous_state = _keep_pick_previous_state(with_then=False)

    answered, qf, branch = _run_keep_pick_turn(previous_state, message_type="business_query")

    outcome = answered["outcome"]
    assert outcome is not None and outcome.resolved is True
    kept_codes = {e.get("canonical_code") or e.get("raw") for e in outcome.keep}
    assert "Product Photos" in kept_codes, outcome

    raws = {str(e.get("raw")) for e in (qf.get("entities") or [])}
    assert "SRTWC6030-SH-BL" in raws, qf.get("entities")
    assert "Product Photos" in raws, (
        f"a plain #708 keep with a NON-product sibling is dropped too - this is not "
        f"specific to the deferred-escalation payload: {qf.get('entities')!r}"
    )


# --------------------------------------------------------------------------- #
# Console pass finding 3, 13 Sep 2026: a team_pick left open over three
# marketing teams (turn d2dc30f8), and the customer's NEXT turn (b24ea133)
# named the team the PARSER already resolved structurally
# (`routing.suggested_team: "marketing_product"`) - no position, no yes/no.
# `_resolve_open_question`'s two existing answer channels (positions, and
# `is_affirmative` for a `yes_no` question) both miss it: this question's
# `expects` is `"pick"`, and the answer is neither a position nor a yes/no,
# it is the parser's OWN structured team word matched against the offered
# options. D11 clean throughout: no read of the customer's text anywhere,
# only `routing.suggested_team`, the parser's already-normalised field.
# --------------------------------------------------------------------------- #

TEAM_PICK_PREVIOUS_STATE = {
    "focus": {
        "domains": {
            "value": ["product_attachment"],
            "set_at_turn": 6,
            "set_at": None,
            "source": "reuse",
        },
        "products": {
            "value": [
                {
                    "raw": "srtwc60630-sh",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": False,
                    "confident": True,
                }
            ],
            "set_at_turn": 6,
            "set_at": None,
            "source": "reuse",
        },
    },
    "open_question": {
        "kind": "team_pick",
        "options": [
            {"idx": 1, "team": "marketing_product", "label": "marketing product"},
            {"idx": 2, "team": "marketing_form", "label": "marketing form"},
            {"idx": 3, "team": "marketing_promotion", "label": "marketing promotion"},
        ],
        "expects": "pick",
        # The team the ORIGINAL ask was raised against, not one of the three offered
        # members - the same "who narrowed us here" fact `_offered_team` reads for a
        # deferred escalation, kept here verbatim from the persisted capture.
        "payload": {"team": "customer_service"},
        "asked_at_turn": 7,
        "asked_at": None,
    },
    "ideation": None,
    "access_levels": [],
    "contains_flyer": False,
}


def _run_team_pick_turn(
    *,
    suggested_team,
    reference_positions=None,
    text: str,
    entities=None,
    domain_hint=None,
    previous_state=None,
):
    from app.services.chatbot.engine import _resolve_open_question

    previous_state = previous_state if previous_state is not None else TEAM_PICK_PREVIOUS_STATE
    _assert_only_five_keys(previous_state)

    parser_raw = _full_emission(
        message_type="casual",
        is_affirmative=None,
        entities=entities or [],
        domain_hint=domain_hint,
        reference_positions=reference_positions or [],
        routing={"suggested_team": suggested_team, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal=text,
    )
    answered = _resolve_open_question(
        previous_state,
        parser_raw=parser_raw,
        emits_v3=False,
        referenced_result_set=None,
        turn_no=8,
    )
    parent_input = {
        "latest_user_message": text,
        "contact_id": "ZZT-esc-teampick-1",
        "previous_conversation_state": previous_state,
        "parser_emits_v3": False,
        "_answered": answered,
        "turn_no": 8,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]

    ctx = {
        "contact": {"id": "ZZT-esc-teampick-1", "phone": "+60123450099", "custom_fields": []},
        "text": {"message": {"messageId": "ZZT-esc-teampick-msg-1", "message": {"type": "text", "text": text}}},
        "session": {"session_vars": {"variables": previous_state}},
        "parse": {"output": qf, "_parser_raw": parse_block.get("_parser_raw")},
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }
    branch, _tier = decide(ctx)
    return answered, qf, branch, ctx


def _team_pick_state_with_option_label(label: str) -> dict:
    """A copy of `TEAM_PICK_PREVIOUS_STATE` whose option 1 LABEL is `label` instead of its
    usual "marketing product" - N17 needs a label that reads nothing like its own team so a
    label-matching bug and a team-matching fix are distinguishable."""
    import copy as _copy

    state = _copy.deepcopy(TEAM_PICK_PREVIOUS_STATE)
    state["open_question"]["options"][0]["label"] = label
    return state


def test_console_finding3_a_structurally_named_team_resolves_the_open_team_pick() -> None:
    """Console pass finding 3, primary. `routing.suggested_team: "marketing_product"`
    matches option 1 exactly - the answer is the parser's OWN structured team, never a
    position or a yes/no. RED today: `_resolve_open_question` has no third answer channel
    for a `team_pick` whose `expects` is `"pick"`, so the outcome stays unresolved, the
    routing chain falls to the hard default, and the turn lands on `route.decide`'s
    low-signal catch-all instead of the escalation lane."""
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team="marketing_product", text="marketing product"
    )

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.handler == "team_pick" and outcome.resolved is True, (
        f"the structurally-named team must resolve the open team_pick: {answered!r}"
    )
    assert branch == "out_of_scope", (
        f"a resolved team_pick must reach the escalation lane: {branch!r}"
    )

    item = {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": branch,
    }
    services = _services()
    result = run(ctx, item, services=services)

    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert body["team_code"] == "marketing_product", body


def test_console_finding3_companion_a_family_word_that_names_no_single_option_stays_unresolved() -> None:
    """Console pass finding 3, companion (a) - green guard. `marketing` is the FAMILY, not
    one of the three offered members by exact name - it must not resolve the team_pick
    (a tap can only answer what was actually offered), and today's behaviour (unaffected
    by the fix this file's primary test targets) is pinned as measured, not assumed."""
    answered, qf, branch, ctx = _run_team_pick_turn(suggested_team="marketing", text="marketing")

    assert answered.get("outcome") is None, (
        f"a family word matching no SINGLE offered option must not resolve the pick: {answered!r}"
    )
    assert branch == "low_signal", (
        f"measured today's own branch rather than assuming one: {branch!r}"
    )


def test_console_finding3_companion_a_catalogue_team_outside_the_offered_options_stays_unresolved() -> None:
    """Console pass finding 3, companion (b) - green guard. `warehouse` is a REAL
    catalogue team, but it is not one of the three teams THIS question offered - resolving
    to it would answer with a team the customer was never shown. Today's behaviour pinned
    as measured."""
    answered, qf, branch, ctx = _run_team_pick_turn(suggested_team="warehouse", text="warehouse")

    assert answered.get("outcome") is None, (
        f"a catalogue team outside the offered options must not resolve the pick: {answered!r}"
    )
    assert branch == "low_signal", (
        f"measured today's own branch rather than assuming one: {branch!r}"
    )


def test_console_finding3_companion_a_numbered_pick_is_unchanged() -> None:
    """Console pass finding 3, companion (c) - green guard. The EXISTING positional
    channel is untouched by this finding: "2" still picks `marketing_form` exactly as it
    does today."""
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team=None, reference_positions=[2], text="2"
    )

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.resolved is True
    assert outcome.picked and outcome.picked[0].get("team") == "marketing_form", outcome
    assert branch == "out_of_scope", branch
    assert qf["routing"]["suggested_team"] == "marketing_form", qf["routing"]


@pytest.mark.parametrize(
    "suggested_team",
    ["Marketing Product", "marketing-product"],
    ids=["mixed_case_with_spaces", "hyphenated"],
)
def test_console_finding3_n16_the_slug_equality_check_normalises_both_sides(suggested_team) -> None:
    """N16. `open_question.team_slug_pick` normalises both the parser's slug and the
    offered team (lower, spaces and hyphens to underscores) before comparing them, so a slug
    spelled "Marketing Product" or "marketing-product" is the SAME slug as the offered
    "marketing_product" and must still resolve option 1. Verified by hand: replacing
    `open_question._team_slug` with the identity function turns this red (neither variant
    equals "marketing_product" without normalisation); restored before this run."""
    answered, qf, branch, ctx = _run_team_pick_turn(suggested_team=suggested_team, text=suggested_team)

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.handler == "team_pick" and outcome.resolved is True, (
        f"a differently-cased or hyphenated slug must still equal the offered team: {answered!r}"
    )
    assert outcome.picked and outcome.picked[0].get("team") == "marketing_product", outcome
    assert branch == "out_of_scope", (
        f"a resolved team_pick must reach the escalation lane: {branch!r}"
    )


def test_console_finding3_n17_a_slug_matching_the_label_but_not_the_team_stays_unresolved() -> None:
    """N17, red guard. The option's own LABEL is "Product Marketing" (normalises to
    "product_marketing") while its TEAM stays "marketing_product" - a parser slug of
    "product_marketing" equals the label, never the team, and `team_slug_pick` reads only
    `options[].team` (D11: the parser owns language, code owns structure, and a label is
    display text, not a slug the parser could ever emit). Verified by hand: allowing
    `team_slug_pick` to also match `row.get("label")` turns this red; restored before this
    run."""
    state = _team_pick_state_with_option_label("Product Marketing")
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team="product_marketing", text="product marketing", previous_state=state
    )

    assert answered.get("outcome") is None, (
        f"a slug matching only the LABEL, never the team, must not resolve the pick: {answered!r}"
    )
    assert branch == "low_signal", (
        f"measured today's own branch rather than assuming one: {branch!r}"
    )


def test_console_finding3_n17_companion_the_matching_team_still_resolves_despite_the_odd_label() -> None:
    """N17, green companion. Same odd label ("Product Marketing" on the `marketing_product`
    option), but the parser slug is "marketing_product" - the TEAM, not the label - and it
    must resolve exactly as it does with the ordinary label, proving the odd label changed
    nothing about the team-equality check."""
    state = _team_pick_state_with_option_label("Product Marketing")
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team="marketing_product", text="marketing product", previous_state=state
    )

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.resolved is True, (
        f"the slug matching the TEAM must resolve regardless of the option's label: {answered!r}"
    )
    assert outcome.picked and outcome.picked[0].get("team") == "marketing_product", outcome
    assert branch == "out_of_scope", branch


def test_console_finding3_s11_a_team_pick_answer_that_also_names_its_own_product_still_resolves() -> None:
    """S11 shape, plan update 13 Sep 2026. "marketing product srtwb8004" answers the open
    team_pick AND names, in the same breath, the product the whole conversation already
    concerns: `message_type: casual`, `domain_hint: null`, one product entity marked
    `current_message: true`. RED on 152cdc201 - `_resolve_open_question`'s
    `names_business_content` gate treats ANY current-message entity as business content and
    blocks the team-slug rung, the same guard that correctly blocks a stray product mention
    over an unrelated offer. Expected once S11 lands: the pick still resolves to option 1 and
    the turn reaches the escalation lane with team marketing_product."""
    entities = [
        {
            "raw": "SRTWB8004",
            "hint": "product",
            "confident": True,
            "canonical_code": None,
            "current_message": True,
        }
    ]
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team="marketing_product",
        text="marketing product srtwb8004",
        entities=entities,
        domain_hint=None,
    )

    outcome = answered.get("outcome")
    assert outcome is not None and outcome.handler == "team_pick" and outcome.resolved is True, (
        f"an answer that also names its own product must still resolve the open team_pick: {answered!r}"
    )
    assert outcome.picked and outcome.picked[0].get("team") == "marketing_product", outcome
    assert branch == "out_of_scope", (
        f"a resolved team_pick must reach the escalation lane: {branch!r}"
    )


def test_console_finding3_s11_companion_a_domain_named_turn_over_the_open_pick_stays_unresolved() -> None:
    """S11 shape, companion - green guard, pinned both before and after S11. World chain
    900000006's own case: `domain_hint: "inventory"` over the open team_pick is a real
    business turn wearing the same slug by coincidence, and the domain half of
    `names_business_content` must keep blocking it whatever the entity half does - a stock
    question is never an answer to "which team", full stop."""
    answered, qf, branch, ctx = _run_team_pick_turn(
        suggested_team="marketing_product",
        text="marketing product srtwb8004",
        domain_hint="inventory",
    )

    assert answered.get("outcome") is None, (
        f"a turn naming a domain must not resolve the team_pick, S11 or not: {answered!r}"
    )
    assert branch == "low_signal", (
        f"measured today's own branch rather than assuming one: {branch!r}"
    )
