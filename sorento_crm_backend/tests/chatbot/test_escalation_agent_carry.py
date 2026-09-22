"""RED tests for AC-1784..AC-1795 (PLAN-chatbot-escalation-agent-carry.md).

Written test-first, Phase 2: `turn_runtime.with_routing_agent_default` does not yet take
`pending=`/`session=` keyword arguments, and nothing yet writes an `"agent"` key onto an
escalation offer's `payload`. Every test below either imports a symbol/keyword that does
not exist yet (an immediate `TypeError`/`ImportError`) or drives the real engine and
asserts the CARRIED agent, which today falls back to `DEFAULT_SUGGESTED_AGENT`
(`"general_enquiries"`) instead of the minting turn's real one.

Postgres only, via `tests/chatbot/conftest.py`'s blank-schema `session_factory`. Every
scenario seeds its own contact/workspace/product chain; nothing is read off a shared row.
Nothing here reaches an LLM, n8n, respond.io or the real MCP server (`conftest.py`'s
autouse guards already forbid the LLM/MCP paths; the `/external/next-assignee` and SLA
seams are captured by monkeypatching the exact in-process functions
`app.services.chatbot.lanes.escalation_services._next_assignee` /
`_sla_create` call - `app.api.v1.external.next_assignee.post_next_assignee` and
`ConversationSLATrackingService.create_tracking` - the same boundary
`test_s5_escalation_seams.py` documents as "the two CRM services stubbed at their own
boundary").

**Design decisions, flagged rather than silently assumed** (per the captain's brief):

* AC-1784/AC-1786/AC-1791/AC-1794 build "turn 1" by writing the session state a real
  minting turn would have LEFT BEHIND (`respond_contacts.session_vars.open_question`,
  the exact `Pending.to_wire()` shape) directly, the same pattern
  `test_rearch_s6_handpass1_findings.py::_seed_top_level_session_vars` already uses to
  represent a prior turn. Turn 2 - the acceptance turn the carry fix actually lives in -
  runs for real through `engine.run_turn`, all the way to the captured `/external/
  next-assignee` body. The offer-MINTING half (does turn 1 itself WRITE `payload["agent"]`
  correctly) is covered separately by AC-1792, which drives two real minting turns
  through the engine (a single-team and a multi-team `team_pick`, both reproducible today
  with a single zero-stock product) plus one direct call into the production
  `answer_bridge.answer_for` entry point for the roster case.
* AC-1786 hand-builds a multi-team pending with two options carrying DIFFERENT
  `payload["team"]`/`payload["agent"]` pairs. Production's own multi-team mint site
  (`turn/compose.py::_team_pick_question`, exercised for real in AC-1792) can only ever
  give every option the SAME agent (one parser verdict, one `routing.suggested_agent`),
  so a genuine "two different agents" fixture has to be built by hand - this tests the
  ACCEPTANCE side's per-option read (the thing the carry fix touches), not any one
  mint site's internal signature, per the captain's own instruction not to overfit here.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT
from app.services.chatbot import turn_runtime
from app.services.chatbot.turn.pending import ask as pending_ask

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _link_contact_company, _seed_workspace

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")


# --------------------------------------------------------------------------- #
# Shared builders
# --------------------------------------------------------------------------- #


def _db(session_factory, *, scope: frozenset[str] = frozenset({SORENTO})):
    """Stamp `company_scope` explicitly, same reasoning as every other S3+ test that
    needs several `session_factory()` calls in one seed chain (the lazily-firing
    `after_begin` default races across them otherwise)."""
    db = session_factory()
    db.info["company_scope"] = scope
    return db


def _seed_contact(session_factory, *, phone: str) -> None:
    workspace_id = _seed_workspace(session_factory)
    db = _db(session_factory)
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :wid)"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({}), "wid": workspace_id},
    )
    db.commit()
    _link_contact_company(session_factory, company_id=SORENTO)


def _seed_product(session_factory, *, code: str) -> None:
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    db = _db(session_factory)
    cat = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"ZZTC-{code}",
        category_name="ZZT",
        class_label="zzt",
        search_synonyms=[],
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"ZZTU-{code}", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    db.add(
        Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=f"ZZT {code}",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=1,
        )
    )
    db.commit()


def _stub_incoming_probe_empty(monkeypatch) -> None:
    """Every MCP probe (incoming stock included) answers "nothing" - a genuine ETA miss,
    no network reached (`conftest.py::_no_real_mcp_calls` would otherwise raise)."""
    from app.services.ai_assistant_service import MCPRuntimeClient

    def fake_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return json.dumps({"answers": []})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)


def _write_open_question(session_factory, *, open_question: dict[str, Any]) -> None:
    """Overwrite `respond_contacts.session_vars` with a top-level five-key shape whose
    `open_question` is exactly this pending's wire form - the same shape
    `turn_runtime.load_state` reads on the NEXT turn (`session_state.five_keys`)."""
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :c"),
        {
            "sv": json.dumps(
                {
                    "focus": None,
                    "open_question": open_question,
                    "ideation": None,
                    "access_levels": [],
                    "contains_flyer": False,
                }
            ),
            "c": str(CONTACT_ID),
        },
    )
    db.commit()


def _capture_next_assignee(monkeypatch, *, response: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Replace the REAL `/external/next-assignee` handler
    (`app.api.v1.external.next_assignee.post_next_assignee`, the exact function
    `escalation_services._next_assignee`'s closure imports and calls) with a fake that
    records every body and returns a canned assignee - no database write, no real
    round-robin draw. Same seam `test_s5_escalation_seams.py`'s module docstring names.
    """
    import app.api.v1.external.next_assignee as next_assignee_mod

    bodies: list[dict[str, Any]] = []
    canned = {
        "assignee_id": "zzt-usr-1",
        "assignee_email": "pic@zzt.example",
        "assignee_name": "ZZT PIC",
        "assignee_respond_user_id": "zzt-respond-usr-1",
        "team_set_code": "ZZT",
        "brand_code": None,
        "company_id": None,
        "is_already_assigned": False,
        **(response or {}),
    }

    async def fake_post_next_assignee(body: dict, current_user: dict = None, db: Any = None):
        bodies.append(dict(body))
        return canned

    monkeypatch.setattr(next_assignee_mod, "post_next_assignee", fake_post_next_assignee)
    return bodies


def _capture_sla(monkeypatch) -> list[Any]:
    """Replace `ConversationSLATrackingService.create_tracking` - the payload it is
    given is a REAL `ConversationSLATrackingCreate`, validated for real, so the SLA
    body's shape is exercised exactly as `_sla_create`'s own closure builds it."""
    from app.services.sla_service import ConversationSLATrackingService

    captured: list[Any] = []

    def fake_create_tracking(self, payload: Any) -> Any:
        captured.append(payload)
        return type(
            "FakeRow",
            (),
            {
                "id": "zzt-sla-1",
                "initiated_at": None,
                "due_at": None,
                "due_at_resolution": None,
            },
        )()

    monkeypatch.setattr(ConversationSLATrackingService, "create_tracking", fake_create_tracking)
    return captured


def _yes_verdict(**overrides: Any) -> dict[str, Any]:
    """The bare "yes" acceptance turn: no domain, no entities, no routing of its own -
    `decide()`'s generic `is_affirmative` arm is the only door this answers through."""
    base = verdict(
        message_type="casual",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        is_affirmative=True,
        routing={"suggested_team": None, "suggested_agent": None},
    )
    base.update(overrides)
    return base


def _second_turn_envelope(message_id: str = "ZZT-msg-2", text: str = "yes") -> Any:
    """A second turn's own envelope - a DIFFERENT `messageId` from `_envelope()`'s
    default (`"ZZT-msg-1"`), or D15's duplicate-message guard replays turn 1's own
    cached reply verbatim instead of processing this message at all (measured: the
    reply text and branch_kind both came back byte-identical to turn 1 until this was
    fixed - the deduplication working exactly as intended, on two calls this test
    itself made look like the same respond.io delivery)."""
    from tests.chatbot.test_engine import CONTACT_ID as _CID

    return _envelope(
        message={
            "event_type": "message.received",
            "contact": {"id": _CID},
            "message": {
                "messageId": message_id,
                "contactId": _CID,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": text},
            },
        }
    )


def _position_verdict(position: int, **overrides: Any) -> dict[str, Any]:
    """A numbered pick over a multi-team roster - the ONE other door
    `decide()`/`picked_positions` opens for an `expects == "pick"` team_pick."""
    base = verdict(
        message_type="casual",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        reference_positions=[position],
        routing={"suggested_team": None, "suggested_agent": None},
    )
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# AC-1784: the headline - two-turn engine replay, roster escalate offer
# --------------------------------------------------------------------------- #


class TestAC1784RosterEscalateOfferCarriesTheMintingTurnsAgent:
    def test_ac_1784_bare_yes_over_a_roster_escalate_offer_carries_the_minting_turns_agent(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001784")
        stub_parser(_yes_verdict())
        stub_access()
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)

        # Turn 1's own state: an incoming ETA miss whose reply carried a roster of
        # candidate products PLUS the escalate offer ("reply 'yes' to escalate to
        # purchasing team" - `payload["escalate_offered"] is True` is what turns a
        # bare "yes" over a still-open roster into an escalation acceptance,
        # `turn/apply.py:668`), parsed on that turn with
        # `routing = {"suggested_team": "purchasing", "suggested_agent":
        # "incoming_stock_enquiries"}`.
        _write_open_question(
            session_factory,
            open_question={
                "kind": "product_pick",
                "expects": None,
                "team": "purchasing",
                "asked_at_turn": 1,
                "payload": {
                    "domain": "incoming",
                    "escalate_offered": True,
                    "agent": "incoming_stock_enquiries",
                },
                "options": [
                    {
                        "position": 1,
                        "label": "SRTSC07-A",
                        "entity_type": "product",
                        "uuid": str(uuid.uuid4()),
                        "payload": {},
                    },
                    {
                        "position": 2,
                        "label": "SRTSC07-B",
                        "entity_type": "product",
                        "uuid": str(uuid.uuid4()),
                        "payload": {},
                    },
                ],
            },
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "out_of_scope", result.branch_kind
        assert len(bodies) == 1, f"expected exactly one next-assignee call: {bodies!r}"
        body = bodies[0]
        assert body["team_code"] == "purchasing", body
        # THE failing assertion today: with no fix, `with_routing_agent_default` never
        # reads the pending's carried agent, so this turn's own null parser routing
        # falls to `DEFAULT_SUGGESTED_AGENT` ("general_enquiries").
        assert body["agent_code"] == "incoming_stock_enquiries", body


# --------------------------------------------------------------------------- #
# AC-1785: single-team `team_pick`, fully real two-turn engine replay - no planting
# --------------------------------------------------------------------------- #


class TestAC1785SingleTeamTeamPickCarriesTheMintingTurnsAgentNotTheDefault:
    def test_ac_1785_single_team_team_pick_carries_the_minting_turns_agent(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001785")
        _seed_product(session_factory, code="ZZTSC07")
        _stub_incoming_probe_empty(monkeypatch)
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)

        # Turn 1: a real ETA miss, no siblings at all - `turn/compose.py::
        # _team_pick_question`'s single-team branch ("Would you like me to escalate to
        # purchasing team?", one "Yes" option), reachable end to end with one seeded
        # zero-stock product and no did-you-mean roster.
        stub_parser(
            verdict(
                domain_hint="incoming",
                intent_hint="check_incoming",
                entities=[entity("ZZTSC07", hint="product", confident=True)],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        stub_access()
        turn1 = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert turn1.branch_kind == "business_query", turn1.branch_kind

        row = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).first()
        open_question = (row.session_vars or {}).get("open_question")
        assert open_question is not None and open_question.get("kind") == "team_pick", open_question
        assert open_question.get("team") == "purchasing", open_question

        # Turn 2: the bare "yes" - the parser names no team and no agent of its own.
        stub_parser(_yes_verdict())
        result = engine_mod.run_turn(_second_turn_envelope(), session_factory=session_factory)

        assert result.branch_kind == "out_of_scope", result.branch_kind
        assert len(bodies) == 1, bodies
        body = bodies[0]
        assert body["team_code"] == "purchasing", body
        assert body["agent_code"] == "incoming_stock_enquiries", body
        assert body["agent_code"] != DEFAULT_SUGGESTED_AGENT, (
            "today's bug: the carried agent falls to the hard default"
        )


# --------------------------------------------------------------------------- #
# AC-1786: multi-team `team_pick`, numbered pick carries THAT option's own agent
# --------------------------------------------------------------------------- #


class TestAC1786MultiTeamPickCarriesThePickedOptionsOwnAgent:
    def _plant_multi_team_pending(self, session_factory) -> None:
        _write_open_question(
            session_factory,
            open_question={
                "kind": "team_pick",
                "expects": "pick",
                "team": None,
                "asked_at_turn": 1,
                "payload": {},
                "options": [
                    {
                        "position": 1,
                        "label": "stock",
                        "entity_type": "team",
                        "payload": {"team": "warehouse", "agent": "general_enquiries"},
                    },
                    {
                        "position": 2,
                        "label": "incoming stock",
                        "entity_type": "team",
                        "payload": {"team": "purchasing", "agent": "incoming_stock_enquiries"},
                    },
                    {
                        "position": 3,
                        "label": "No it's okay",
                        "entity_type": "team",
                        "payload": {"team": None, "agent": None, "hold": True},
                    },
                ],
            },
        )

    def test_ac_1786_picking_option_two_by_number_carries_option_twos_agent(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001786")
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        self._plant_multi_team_pending(session_factory)

        stub_parser(_position_verdict(2))
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "out_of_scope", result.branch_kind
        assert len(bodies) == 1, bodies
        body = bodies[0]
        assert body["team_code"] == "purchasing", body
        assert body["agent_code"] == "incoming_stock_enquiries", (
            f"picking option 2 must carry option 2's OWN agent, not option 1's "
            f"('general_enquiries') and not the default: {body!r}"
        )
        assert body["agent_code"] != "general_enquiries", body


# --------------------------------------------------------------------------- #
# AC-1787..AC-1790: `with_routing_agent_default`'s precedence chain, pure python
# --------------------------------------------------------------------------- #


class TestPrecedenceChain:
    def test_ac_1787_a_parser_named_agent_this_turn_is_never_overridden(self) -> None:
        verdict_in = {"routing": {"suggested_team": "purchasing", "suggested_agent": "order_enquiries"}}
        pending = pending_ask(
            "product_pick",
            [],
            team="purchasing",
            payload={"escalate_offered": True, "agent": "incoming_stock_enquiries", "domain": "incoming"},
        )

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=pending, session=None)

        assert out["routing"]["suggested_agent"] == "order_enquiries", out

    def test_ac_1787_a_named_agent_wins_over_a_carried_prior_session_agent_too(self) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": "marketing_form"}}
        session = {"session_vars": {"variables": {"routing": {"suggested_agent": "it_support"}}}}

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=None, session=session)

        assert out["routing"]["suggested_agent"] == "marketing_form", out

    def test_ac_1788_no_offer_parser_null_reads_the_prior_sessions_nested_shape(self) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}
        session = {
            "session_vars": {"variables": {"routing": {"suggested_agent": "incoming_stock_enquiries"}}}
        }

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=None, session=session)

        assert out["routing"]["suggested_agent"] == "incoming_stock_enquiries", out

    def test_ac_1788_no_offer_parser_null_reads_the_prior_sessions_bare_variables_shape(self) -> None:
        # The SAME second fallback `_prior_suggested_team` already reads: `ctx.session.
        # variables` directly, bypassing `session_vars` (`turn_runtime.py:344-345`).
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}
        session = {"variables": {"routing": {"suggested_agent": "order_enquiries"}}}

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=None, session=session)

        assert out["routing"]["suggested_agent"] == "order_enquiries", out

    def test_ac_1789_no_offer_no_prior_routing_parser_null_falls_to_the_hard_default(self) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=None, session=None)

        assert out["routing"]["suggested_agent"] == DEFAULT_SUGGESTED_AGENT, out

    @pytest.mark.parametrize(
        "session",
        [
            "not-a-dict",
            {"session_vars": "also-not-a-dict"},
            {"session_vars": {"variables": "blank string routing block"}},
            {"session_vars": {"variables": {"routing": "blank string"}}},
            {},
            None,
        ],
        ids=["bare-string", "session_vars-not-dict", "variables-not-dict", "routing-not-dict", "empty-dict", "none"],
    )
    def test_ac_1790_an_unreadable_session_shape_reads_as_nothing_carried_never_raises(
        self, session
    ) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=None, session=session)

        assert out["routing"]["suggested_agent"] == DEFAULT_SUGGESTED_AGENT, out


# --------------------------------------------------------------------------- #
# AC-1791: access is checked against the CARRIED agent, not the default
# --------------------------------------------------------------------------- #


class TestAC1791AccessCheckedAgainstTheCarriedAgent:
    def _plant_roster_offer(self, session_factory) -> None:
        _write_open_question(
            session_factory,
            open_question={
                "kind": "product_pick",
                "expects": None,
                "team": "purchasing",
                "asked_at_turn": 1,
                "payload": {
                    "domain": "incoming",
                    "escalate_offered": True,
                    "agent": "incoming_stock_enquiries",
                },
                "options": [
                    {
                        "position": 1,
                        "label": "SRTSC07-A",
                        "entity_type": "product",
                        "uuid": str(uuid.uuid4()),
                        "payload": {},
                    },
                ],
            },
        )

    def _spy_access(self, monkeypatch, *, allowed_agent: str):
        calls: list[str | None] = []

        def fake_check_access(db, *, agent_code, contact_id, space_id):
            calls.append(agent_code)
            return {
                "allowed": agent_code == allowed_agent,
                "decision": "allow" if agent_code == allowed_agent else "deny_no_access",
                "agent_name": "General Enquiries",
                "attributes": None,
                "all_attributes_allowed": None,
            }

        monkeypatch.setattr(engine_mod, "check_access", fake_check_access)
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
        return calls

    def test_ac_1791_a_contact_granted_only_the_carried_agent_is_allowed_on_the_yes_turn(
        self, session_factory, stub_parser, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001791")
        self._plant_roster_offer(session_factory)
        stub_parser(_yes_verdict())
        calls = self._spy_access(monkeypatch, allowed_agent="incoming_stock_enquiries")
        _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert calls == ["incoming_stock_enquiries"], calls
        assert result.branch_kind != "access_denied", result.branch_kind

    def test_ac_1791_a_contact_granted_only_the_default_agent_is_denied_on_the_yes_turn(
        self, session_factory, stub_parser, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001792")
        self._plant_roster_offer(session_factory)
        stub_parser(_yes_verdict())
        calls = self._spy_access(monkeypatch, allowed_agent=DEFAULT_SUGGESTED_AGENT)
        # Today's bug means this check is made against `DEFAULT_SUGGESTED_AGENT`, which
        # this contact IS granted - so today the turn is wrongly ALLOWED through and
        # reaches the real escalation lane. Mocked so that misbehaviour never reaches a
        # real service call while this test is red for the documented reason.
        _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert calls == ["incoming_stock_enquiries"], (
            "the access check must still be made against the CARRIED agent, not the "
            f"default, even though this contact's grant denies it: {calls!r}"
        )
        assert result.branch_kind == "access_denied", result.branch_kind


# --------------------------------------------------------------------------- #
# AC-1792: the offer WRITE side - the minting turn stores the agent on the payload
# --------------------------------------------------------------------------- #


class TestAC1792OfferPayloadCarriesTheAgent:
    def test_ac_1792_single_team_team_pick_stores_the_agent_on_pending_payload(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001793")
        _seed_product(session_factory, code="ZZTSC08")
        _stub_incoming_probe_empty(monkeypatch)
        stub_parser(
            verdict(
                domain_hint="incoming",
                intent_hint="check_incoming",
                entities=[entity("ZZTSC08", hint="product", confident=True)],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        row = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).first()
        open_question = (row.session_vars or {}).get("open_question") or {}
        assert open_question.get("kind") == "team_pick", open_question
        assert open_question.get("payload", {}).get("agent") == "incoming_stock_enquiries", (
            f"a single-team team_pick must store the minting turn's agent on "
            f"pending.payload['agent']: {open_question!r}"
        )

    def test_ac_1792_multi_team_team_pick_stores_the_agent_on_each_option_and_none_on_the_hold(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001794")
        _seed_product(session_factory, code="ZZTSC09")
        _stub_incoming_probe_empty(monkeypatch)
        stub_parser(
            verdict(
                asks=[{"domain": "inventory"}, {"domain": "incoming"}],
                domain_hint=None,
                intent_hint=None,
                entities=[entity("ZZTSC09", hint="product", confident=True)],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        row = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).first()
        open_question = (row.session_vars or {}).get("open_question") or {}
        assert open_question.get("kind") == "team_pick", open_question
        options = open_question.get("options") or []
        assert len(options) == 3, options
        non_hold = [o for o in options if not (o.get("payload") or {}).get("hold")]
        hold = [o for o in options if (o.get("payload") or {}).get("hold")]
        assert non_hold, options
        for option in non_hold:
            assert option["payload"].get("agent") == "incoming_stock_enquiries", (
                f"each real option must carry the minting turn's agent beside its own "
                f"team: {option!r}"
            )
            assert "team" in option["payload"], option
        assert hold, options
        assert hold[0]["payload"].get("agent") is None, (
            f"the hold option ('No it's okay') must carry agent: None, exactly like "
            f"its team: {hold[0]!r}"
        )

    def test_ac_1792_roster_escalate_offer_stores_the_agent_on_pending_payload(self) -> None:
        """The did-you-mean/sibling roster mint site (`answer_bridge.py::_miss_question`),
        driven through the real, already-proven production entry point
        `answer_bridge.answer_for` - the same seam
        `test_rearch_r4_bridge_miss.py::TestDidYouMeanRosterMintsAProductPick` already
        exercises for the team half (`pending.team == "purchasing"`), extended with a
        real `routing.suggested_agent` on the minting turn."""
        from app.services.chatbot import copy as copy_mod
        from app.services.chatbot.lanes.business.services import AnswerServices

        bridge = pytest.importorskip("app.services.chatbot.answer_bridge")

        raw = "SRTWT165-FT"
        parser = {
            "domain_hint": "incoming",
            "intent_hint": "check_incoming",
            "message_type": "business_query",
            "entities": [{"raw": raw, "hint": "product", "current_message": True, "confident": True}],
            "routing": {"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            "access_levels": [],
        }
        resolved = {
            "resolutions": [
                {
                    "token": raw,
                    "matches": [],
                    "alternatives": [
                        {
                            "canonical_code": "11111111-1111-4111-8111-111111111111",
                            "entity_type": "product",
                            "uuid": "11111111-1111-4111-8111-111111111111",
                            "display": {"product_name": "SRTWT165-FTX"},
                            "match_tier": "fuzzy",
                        },
                        {
                            "canonical_code": "22222222-2222-4222-8222-222222222222",
                            "entity_type": "product",
                            "uuid": "22222222-2222-4222-8222-222222222222",
                            "display": {"product_name": "SRTWT165-FTY"},
                            "match_tier": "fuzzy",
                        },
                    ],
                }
            ],
            "unresolved_tokens": [raw],
            "tokens": [raw],
        }
        gate = {"gate_passed": True, "compatible_entities": [], "gate_debug": {"domain": "incoming"}}
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
        services = AnswerServices(
            mcp_probe=lambda name, args: {"has_result": False, "answers": []},
            family_fetch=lambda query: {"data": []},
        )

        answer = bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx={"parse": {"output": parser}, "contact": {"id": "zzt-1792-contact"}, "session": {}},
            canned=copy_mod.fallback_copy(),
            services=services,
            db=None,
            asked_at_turn=3,
        )

        assert answer is not None
        assert answer.question is not None, "a did-you-mean offer must raise a Pending"
        pending = answer.question
        assert pending.kind == "product_pick", pending.kind
        assert pending.team == "purchasing", pending.team
        assert pending.payload.get("escalate_offered") is True, pending.payload
        assert pending.payload.get("agent") == "incoming_stock_enquiries", (
            f"the roster escalate offer must store the minting turn's agent on "
            f"pending.payload['agent']: {pending.payload!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1793: a pending minted with no agent falls through cleanly, no KeyError
# --------------------------------------------------------------------------- #


class TestAC1793NoAgentOnThePendingFallsThroughCleanly:
    def test_ac_1793_a_pending_with_agent_none_falls_through_to_prior_session(self) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}
        pending = pending_ask(
            "team_pick",
            [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
            team="customer_service",
            payload={"agent": None},
        )
        session = {"session_vars": {"variables": {"routing": {"suggested_agent": "order_enquiries"}}}}

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=pending, session=session)

        assert out["routing"]["suggested_agent"] == "order_enquiries", out

    def test_ac_1793_a_pending_with_agent_none_and_no_prior_session_falls_to_the_hard_default(
        self,
    ) -> None:
        verdict_in = {"routing": {"suggested_team": None, "suggested_agent": None}}
        pending = pending_ask(
            "team_pick",
            [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
            team="customer_service",
            payload={"agent": None},
        )

        out = turn_runtime.with_routing_agent_default(verdict_in, pending=pending, session=None)

        assert out["routing"]["suggested_agent"] == DEFAULT_SUGGESTED_AGENT, out
        # /external/next-assignee 400s on an empty agent_code - the carry must never
        # land there as "".
        assert out["routing"]["suggested_agent"] != "", out


# --------------------------------------------------------------------------- #
# AC-1794: the SLA body carries the same agent_code as the next-assignee body
# --------------------------------------------------------------------------- #


class TestAC1794SlaBodyCarriesTheSameAgentCodeAsNextAssignee:
    def test_ac_1794_sla_body_and_next_assignee_body_agree_on_agent_code(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000001795")
        _seed_product(session_factory, code="ZZTSC10")
        _stub_incoming_probe_empty(monkeypatch)
        stub_parser(
            verdict(
                domain_hint="incoming",
                intent_hint="check_incoming",
                entities=[entity("ZZTSC10", hint="product", confident=True)],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        stub_access()
        turn1 = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert turn1.branch_kind == "business_query", turn1.branch_kind

        next_assignee_bodies = _capture_next_assignee(monkeypatch)
        sla_bodies = _capture_sla(monkeypatch)
        stub_parser(_yes_verdict())

        result = engine_mod.run_turn(_second_turn_envelope(), session_factory=session_factory)

        assert result.branch_kind == "out_of_scope", result.branch_kind
        assert len(next_assignee_bodies) == 1, next_assignee_bodies
        assert len(sla_bodies) == 1, sla_bodies
        assert next_assignee_bodies[0]["agent_code"] == "incoming_stock_enquiries", next_assignee_bodies
        assert sla_bodies[0].agent_code == next_assignee_bodies[0]["agent_code"], (
            sla_bodies[0].agent_code,
            next_assignee_bodies[0]["agent_code"],
        )


# --------------------------------------------------------------------------- #
# AC-1795: the TEAM chain in `lane_parse_output` is byte-for-byte unchanged
# --------------------------------------------------------------------------- #


class TestAC1795TeamChainInLaneParseOutputUnchanged:
    def test_ac_1795_team_precedence_chain_is_unaffected_by_the_agent_carry(self) -> None:
        """A pin, not a new behaviour: `lane_parse_output`'s own team chain (accepted
        team, then the pending's team, then the prior session, then the hard default)
        must read exactly as it does today regardless of what `suggested_agent` the
        SAME call carries - the two axes are independent fields on one dict. The real
        regression gate is `tests/chatbot/test_s5_escalation_lane.py` and
        `tests/chatbot/test_turn_replay.py`, run in full alongside this file (both stay
        green, per the plan)."""
        verdict_in = {
            "routing": {"suggested_team": None, "suggested_agent": "incoming_stock_enquiries"},
            "entities": [],
        }
        offer_pending = pending_ask(
            "team_pick",
            [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
            team="purchasing",
        )
        prior_session = {"session_vars": {"variables": {"routing": {"suggested_team": "warehouse"}}}}

        out = turn_runtime.lane_parse_output(
            verdict_in,
            pending=offer_pending,
            prior_session=prior_session,
        )

        # The pending's own team outranks the prior session's, exactly as documented at
        # `turn_runtime.py::lane_parse_output`'s own docstring - unchanged by this slice.
        assert out["routing"]["suggested_team"] == "purchasing", out["routing"]
        # And the agent this call was given rides straight through, untouched by the
        # team chain above it.
        assert out["routing"]["suggested_agent"] == "incoming_stock_enquiries", out["routing"]
