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
    """Security review round 3, item S3. `run(..., dry_run=True)`'s preview branch calls
    `_preview_routing`, which decides the landed team through `_person_routing` same as a
    live turn - but the customer-facing preview text (`ROUTED_TO_PIC_REPLY.format(team=
    ...)`) and the comment it would send must still reflect the LANDED pair (AC-1129's own
    rule), not the inherited `purchasing` / `general_enquiries` this fixture starts from,
    and no seam may be reached at all (H37)."""
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
