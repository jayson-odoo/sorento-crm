"""S5's two untested edges: the `input_message` chain and the production seam wiring.

Written by the coder alongside the fixes below, deliberately in its OWN file - the tester
owns `test_s5_escalation_lane.py` and it stays untouched.

Three things live here, and none of them is covered there:

1. **`input_message`.** `_sla_body` read `ctx.text.message.message.text` and nothing else,
   so an image, a voice note or a document - which arrive with an empty `text` - wrote a
   BLANK `source_message_text` on the SLA row. Live composes a chain (attachment
   description, then a `[image message]` placeholder naming the type) and appends the
   quoted message on a reply. Ported and pinned here.

2. **`escalation_services`.** Its own docstring used to say "nothing here is exercised by
   a test", which is where a typo waits: the module is only reached once the owner adds
   `out_of_scope` to `chatbot_completed_lanes`, i.e. in production, on a real customer.
   The smoke test drives `production_services()` over a blank-schema session with the two
   CRM services stubbed at THEIR boundary (`post_next_assignee`, the SLA service's
   `create_tracking`), so the wiring - the import paths, the argument names, the
   `asyncio.run`, and above all `ConversationSLATrackingCreate(**body)` accepting the
   lane's own body - runs for real.

3. **The clarify arm end to end.** AC-505 has zero live captures (the arm did not fire once
   in the 33-execution window), so the only way to know `complete_turn` surfaces
   `clarify_text` as the reply and re-persists the prior offer state is to drive `run_turn`
   with a faked clarify fragment.

Postgres only, through `tests/chatbot/conftest.py`'s blank-schema `session_factory`.
Nothing here reaches an LLM, n8n, respond.io or a real MCP server.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot.lanes import escalation as escalation_mod


# --------------------------------------------------------------------------- #
# Builders - deliberately local, so the tester's file and this one cannot
# drift into "the fixture changed and the other suite silently changed with it".
# --------------------------------------------------------------------------- #


# Respond.io's own message ids are NUMBERS on the live captures (millisecond epochs, e.g.
# `1788015893412` in the `sub-human-intervention` capture set), and
# `ConversationSLATrackingCreate.message_id` coerces to int - so a seam test that used a
# ZZT- string would fail validation for a reason production never sees.
MESSAGE_ID = 1788015893412


def _ctx(*, message_body: dict[str, Any], reply_to: Any = None) -> dict[str, Any]:
    """The hub `ctx` with one respond.io webhook body in it."""
    message: dict[str, Any] = {"messageId": MESSAGE_ID, "message": message_body}
    if reply_to is not None:
        message["replyTo"] = reply_to
    return {
        "contact": {"id": "ZZT-esc-seam-1", "phone": "+60123450099"},
        "text": {"message": message},
        "session": {"session_vars": {"variables": {}}},
        "parse": {
            "output": {
                "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries"},
                "escalation": {"is_escalation_confirmation": True, "company_pick": None},
                "query_brands": [],
                "entities": [],
            }
        },
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }


def _item() -> dict[str, Any]:
    return {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": "out_of_scope",
    }


class _Services:
    """A seam that records its bodies. No database, no network."""

    def __init__(self) -> None:
        self.next_assignee_bodies: list[dict[str, Any]] = []
        self.sla_bodies: list[dict[str, Any]] = []

    def resolve_and_gate(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover - never live
        raise AssertionError("resolve_and_gate is not on the live graph")

    def next_assignee(self, body: dict[str, Any]) -> dict[str, Any]:
        self.next_assignee_bodies.append(body)
        return {
            "assignee_id": "usr-pic-1",
            "assignee_respond_user_id": "respond-usr-1",
            "team_set_code": "CS",
            "brand_code": None,
            "company_id": None,
            "is_already_assigned": False,
        }

    def sla_create(self, body: dict[str, Any]) -> dict[str, Any]:
        self.sla_bodies.append(body)
        return {
            "id": "sla-row-1",
            "initiated_at": "2026-09-05T04:00:00+00:00",
            "due_at": "2026-09-05T08:00:00+00:00",
            "due_at_resolution": "2026-09-06T04:00:00+00:00",
        }

    def team_members(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover - never live
        raise AssertionError("team_members is not on the live graph")


def _source_message_text(ctx: dict[str, Any]) -> str:
    """Run the lane and read what the SLA row would have carried."""
    services = _Services()
    escalation_mod.run(ctx, _item(), services=services)
    assert len(services.sla_bodies) == 1
    return services.sla_bodies[0]["source_message_text"]


# --------------------------------------------------------------------------- #
# 1. `input_message` - the live chain, kind by kind
# --------------------------------------------------------------------------- #


class TestInputMessageChain:
    """`Call 'sub-human-intervention'`'s `input_message`, which becomes the SLA row's
    `source_message_text`. The expression, from the live export:

        {{ text || attachment?.description
           || '[' + (type || 'unknown') + ' message]' }}{{ replyTo?.message
           ? ' reply to: ' + replyTo.message.text : '' }}
    """

    def test_a_typed_message_uses_its_text(self) -> None:
        ctx = _ctx(message_body={"type": "text", "text": "I need to speak to a human"})
        assert _source_message_text(ctx) == "I need to speak to a human"

    def test_an_attachment_falls_back_to_its_description(self) -> None:
        """An image with a caption. `text` is empty, so the description carries it - and
        THIS is the case the first version blanked: the person picking the case up saw no
        trace of what the customer sent."""
        ctx = _ctx(
            message_body={
                "type": "image",
                "text": "",
                "attachment": {"description": "photo of a cracked tile"},
            }
        )
        assert _source_message_text(ctx) == "photo of a cracked tile"

    def test_an_attachment_with_no_description_names_the_type(self) -> None:
        ctx = _ctx(message_body={"type": "audio", "text": "", "attachment": {}})
        assert _source_message_text(ctx) == "[audio message]"

    def test_a_missing_type_reads_unknown(self) -> None:
        """`(type || 'unknown')` - an empty type is falsy in JS too, so both spellings of
        "we were not told" land on the same placeholder."""
        assert _source_message_text(_ctx(message_body={"text": ""})) == "[unknown message]"
        assert _source_message_text(_ctx(message_body={"type": "", "text": ""})) == "[unknown message]"

    def test_a_reply_appends_the_quoted_message(self) -> None:
        """`replyTo` hangs off the WEBHOOK body, one level above the message body - and
        the suffix is appended to whichever branch of the chain won, not only to `text`."""
        ctx = _ctx(
            message_body={"type": "text", "text": "this one"},
            reply_to={"message": {"text": "SRTWC8517 is 12 pcs"}},
        )
        assert _source_message_text(ctx) == "this one reply to: SRTWC8517 is 12 pcs"

        ctx = _ctx(
            message_body={"type": "image", "text": "", "attachment": {}},
            reply_to={"message": {"text": "SRTWC8517 is 12 pcs"}},
        )
        assert _source_message_text(ctx) == "[image message] reply to: SRTWC8517 is 12 pcs"

    def test_a_replyto_without_a_message_appends_nothing(self) -> None:
        """`replyTo?.message` is the truth test, so a `replyTo` carrying no message is the
        same as no reply at all."""
        ctx = _ctx(message_body={"type": "text", "text": "hello"}, reply_to={})
        assert _source_message_text(ctx) == "hello"

    def test_the_body_still_carries_the_message_id_beside_the_text(self) -> None:
        """The chain changed; the two id fields beside it did not."""
        ctx = _ctx(message_body={"type": "text", "text": "hello"})
        services = _Services()
        escalation_mod.run(ctx, _item(), services=services)
        body = services.sla_bodies[0]
        assert body["message_id"] == MESSAGE_ID
        assert body["source_message_id"] == str(MESSAGE_ID)


# --------------------------------------------------------------------------- #
# 2. `escalation_services` - the production wiring, and its session's lifecycle
# --------------------------------------------------------------------------- #


class TestProductionSeams:
    def test_production_services_draws_an_assignee_and_writes_an_sla_row(
        self, session_factory, monkeypatch
    ) -> None:
        """The seam bundle over a real session, with the two CRM services stubbed at their
        OWN boundary - so everything between the lane and them is the real thing.

        The load-bearing assertion is the one that is easy to miss:
        `ConversationSLATrackingCreate(**body)` is constructed for real, so a lane body
        whose keys drifted from the schema fails HERE rather than on a live escalation.
        """
        from app.api.v1.external import next_assignee as next_assignee_mod
        from app.schemas.sla import ConversationSLATrackingCreate
        from app.services.sla_service import ConversationSLATrackingService

        seen: dict[str, Any] = {}

        async def fake_post_next_assignee(*, body, current_user, db):
            seen["next_assignee_body"] = body
            seen["next_assignee_user"] = current_user
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
            assert isinstance(payload, ConversationSLATrackingCreate), (
                "the seam must hand the service its own schema, not a raw dict"
            )
            seen["sla_payload"] = payload
            return _Created()

        monkeypatch.setattr(next_assignee_mod, "post_next_assignee", fake_post_next_assignee)
        monkeypatch.setattr(
            ConversationSLATrackingService, "create_tracking", fake_create_tracking
        )

        db = session_factory()
        services = escalation_mod.production_services(db)

        ctx = _ctx(message_body={"type": "text", "text": "I need a human"})
        result = escalation_mod.run(ctx, _item(), services=services)

        assert [a["kind"] for a in result["actions"]] == [
            "send_message",
            "assign_conversation",
            "add_comment",
            "send_message",
        ]
        assert seen["next_assignee_body"]["policy_code"] == "NORMAL"
        assert seen["next_assignee_body"]["team_code"] == "customer_service"
        assert seen["next_assignee_user"] == {"id": None, "email": "chatbot"}
        assert seen["sla_payload"].contact_phone_number == "+60123450099"
        assert seen["sla_payload"].source_message_text == "I need a human"

    def test_the_production_session_is_closed_and_rolled_back_on_a_raise(
        self, monkeypatch
    ) -> None:
        """The first version called `SessionLocal()` and walked away: a leaked connection
        per escalation turn, and a seam that raised left its transaction open - which holds
        the round-robin cursor row's lock until the connection is recycled, so the NEXT
        escalation turn blocks behind a failure nobody is watching."""
        from app.services.chatbot.lanes import escalation_services

        events: list[str] = []

        class _FakeSession:
            def rollback(self) -> None:
                events.append("rollback")

            def close(self) -> None:
                events.append("close")

        # The factory is the TURN's now, not `SessionLocal` (H56): the lane's session has
        # to carry the contact's company scope, so it can no longer reach for a global one.
        factory = lambda: _FakeSession()  # noqa: E731

        with escalation_services.production_session(factory) as db:
            assert isinstance(db, _FakeSession)
        assert events == ["close"], "a clean exit closes and does not roll back"

        events.clear()
        with pytest.raises(RuntimeError):
            with escalation_services.production_session(factory):
                raise RuntimeError("the seam refused")
        assert events == ["rollback", "close"]

        # No factory at all is a LOUD failure, never a silent unscoped `SessionLocal`.
        with pytest.raises(ValueError):
            with escalation_services.production_session(None):
                raise AssertionError("the session must not open without a factory")

    def test_a_seam_failure_leaves_no_partial_assignment(self) -> None:
        """`engine.py` promises "the lane returns its whole action list or raises before
        returning any of it". The SLA seam raising is the case that has to hold it."""

        class _Boom(_Services):
            def sla_create(self, body):
                raise RuntimeError("sla create refused")

        with pytest.raises(RuntimeError):
            escalation_mod.run(
                _ctx(message_body={"type": "text", "text": "help"}),
                _item(),
                services=_Boom(),
            )


# --------------------------------------------------------------------------- #
# 3. AC-505 end to end: the clarify arm through `run_turn` + `complete_turn`
# --------------------------------------------------------------------------- #


CLARIFY_TEXT = (
    "Both *Sorento Sdn Bhd* and *Sorento Trading* teams are listed - reply a number, a "
    "name, or the company (*Sorento Sdn Bhd* / *Sorento Trading*) and I'll assign "
    "automatically."
)
PRIOR_RESULT_SET = [
    {"idx": 1, "name": "Ali", "company_name": "Sorento Sdn Bhd"},
    {"idx": 2, "name": "Siti", "company_name": "Sorento Trading"},
]
PRIOR_ROSTER_PLAN = [
    {"plan_idx": 0, "company_id": "co-1", "company_name": "Sorento Sdn Bhd", "brand_code": None},
    {"plan_idx": 1, "company_id": "co-2", "company_name": "Sorento Trading", "brand_code": None},
]


def test_clarify_arm_surfaces_the_ask_and_re_persists_the_offer_state(
    session_factory, system_settings_row, monkeypatch
) -> None:
    """AC-505 end to end, which no capture can prove: the arm did not fire once in the
    33-execution window, so the lane's clarify fragment has never travelled through
    `complete_turn` outside a test.

    Two things have to be true at once, and they are what the arm exists for:

    * the ASK reaches the customer - `clarify_text` becomes the turn's reply, replacing
      the out-of-scope acknowledgement that the human-intervention arm sends;
    * the prior offer state SURVIVES - `selection_context` and `last_result_set` are
      re-persisted, because the next turn resolves the customer's "2" or "Sorento Trading"
      against exactly that pool. Clearing them here would leave the customer answering a
      question the bot has forgotten it asked.
    """
    from sqlalchemy import text as sql_text

    from app.models.chatbot_turn import ChatbotTurn
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.head import parser as parser_mod

    contact_id = "ZZT-esc-clarify-1"
    prior_variables = {
        "selection_context": "member_offer",
        "last_result_set": PRIOR_RESULT_SET,
        "routing_roster_plan": PRIOR_ROSTER_PLAN,
        "response": "Which company should take this?",
    }

    db = session_factory()
    db.execute(
        sql_text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": contact_id,
            "phone": "+60000000097",
            "sv": json.dumps({"variables": prior_variables}),
        },
    )
    setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    setting.chatbot_completed_lanes = ["out_of_scope"]
    db.commit()

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    parser_output = {
        "message_type": "request_for_help",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": "wants a human",
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
        "routing": {
            "suggested_team": "customer_service",
            "suggested_agent": "general_enquiries",
            "team_source": "inferred",
        },
        "escalation": {"is_escalation_confirmation": True, "company_pick": None},
    }

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: dict(parser_output))
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

    # A hand-built clarify fragment: the R3 marker and `clarify_company_reply`'s composed
    # ask riding on the `clarify` carrier the tail reads it off. `actions: []` here is the
    # TEST's stub, not the lane's shape - the real lane sends every clarify as a
    # `send_message` (prod turn 9dd4cd0f); what this one grades is that the tail turns the
    # carrier into the reply and re-persists the offer, whatever the lane sent.
    def fake_run_escalation_lane(ctx, item, *, dry_run=False, session_factory=None):
        return {
            "arm": "clarify",
            "clarify": {
                "branch_kind": "out_of_scope",
                "team": "customer_service",
                "routing_source": "multi_company_unpicked",
                "clarify_company": True,
                "clarify_text": CLARIFY_TEXT,
            },
            "actions": [],
            "pending": {"kind": "company_clarify"},
        }

    monkeypatch.setattr(engine_mod, "run_escalation_lane", fake_run_escalation_lane)

    envelope = Envelope(
        contact={"id": contact_id, "phone": "+60000000097", "custom_fields": []},
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": "ZZT-esc-clarify-msg-1",
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "I need to speak to a human"},
            },
        },
    )

    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    assert result.status == "done", result.error
    assert result.branch_kind == "out_of_scope"
    assert result.delegate is None
    # The ask REPLACES the acknowledgement: the clarify arm assigns nobody, so there is
    # nothing to tell the customer about a PIC.
    assert (result.reply or {}).get("text") == CLARIFY_TEXT
    assert result.actions == [], "the stub handed the engine none; it must invent none"

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    assert row.status == "done", row.error
    assert row.stage == "remembered"
    assert row.response.get("pending") == {"kind": "company_clarify"}

    stored = session_factory().execute(
        sql_text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": contact_id},
    ).scalar()
    variables = stored["variables"]
    assert variables["selection_context"] == "member_offer"
    assert variables["last_result_set"] == PRIOR_RESULT_SET
    assert variables["routing_roster_plan"] == PRIOR_ROSTER_PLAN
    # `variables.response` deliberately keeps the PREVIOUS turn's text. Faithful, not
    # tidied: `compile_state`'s clarify block only overwrites it when the fragment carries
    # `routing_companies` (the escalation sub's OWN this-turn gate ask, B-HB-2) or
    # `clarify_team`, and this lane's `escalation_context` emits neither. What the customer
    # is SENT is `user_response`, asserted as `result.reply` above; `response` is the
    # "what was last offered" state the migration-window offer-open read still uses, and
    # the offer here is still the one the previous turn made.
    assert variables["response"] == "Which company should take this?"
    # The clarify arm's OWN `company_clarify` marker is a TURN-ROW fact, not a session
    # one, and it is asserted on `row.response` above. What `compile_state` writes into
    # `variables.pending` comes from `pending_marker.derive`, and since S3 an open member
    # offer is one of the two kinds it emits - the roster this turn re-persisted is still
    # on the customer's screen, so the marker says so. The next turn still resolves a
    # number against `selection_context` + `last_result_set`, which the assertions above
    # are what protect.
    # `ttl` 3: the clarify arm RE-PERSISTS the roster, which is the bot asking again, so
    # the offer's clock starts over rather than continuing to run down (AC-816 rule 1).
    assert variables.get("pending") == {
        "kind": "member_offer",
        "team": "customer_service",
        "domain": None,
        "ttl": 3,
    }


def test_a_clarifys_quick_replies_reach_the_persisted_reply(
    session_factory, system_settings_row, monkeypatch
) -> None:
    """Prod turn 9dd4cd0f, the half that outlives the turn.

    The escalation clarifies build their own quick replies - the teams, so the answer is a
    tap - and the tail composes no `quick_reply` on that arm. The persisted reply therefore
    said `quick_replies: null` and the `replied` trace fact said `False` about a turn that
    had just sent two buttons. Chat History and the trace screen read the REPLY, so both
    would have shown a different turn from the one the customer got (reviewer, #705).

    Driven through the REAL lane: the fragment under test is the one `escalation.run`
    builds, with only the staff seam injected.
    """
    from sqlalchemy import text as sql_text

    from app.models.chatbot_turn import ChatbotTurn
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.lanes import escalation as escalation_mod
    from tests.chatbot.test_s5_escalation_lane import _services

    contact_id = "ZZT-esc-clarify-qr"
    db = session_factory()
    db.execute(
        sql_text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_id, "phone": "+60000000096", "sv": json.dumps({"variables": {}})},
    )
    setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    setting.chatbot_completed_lanes = ["out_of_scope"]
    db.commit()

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    parser_output = {
        "message_type": "request_for_help",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": "wants Nurain",
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
        "person_mention": "Nurain",
        "is_active": None,
        "order_status": None,
        "correction": False,
        # The DERIVED routing carries a team (the post-processor's own chain); the RAW
        # snapshot is what says this message named none, which is what makes the mention
        # route rather than read as one made in passing.
        "routing": {
            "suggested_team": "customer_service",
            "suggested_agent": "general_enquiries",
            "team_source": "inferred",
        },
        "escalation": {"is_escalation_confirmation": True, "company_pick": None},
    }

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: dict(parser_output))
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

    def real_lane_with_a_staff_seam(ctx, item, *, dry_run=False, session_factory=None):
        services = _services()
        services.staff_lookup = lambda person: [
            {
                "user_id": "u-1",
                "user_name": "Nurain A",
                "respond_user_id": "r-1",
                "team_code": code,
                "team_name": name,
            }
            for code, name in (
                ("do_customer_service", "DO Customer Service"),
                ("project_customer_service", "Project Customer Service"),
            )
        ]
        ctx = {
            **ctx,
            "parse": {
                **(ctx.get("parse") or {}),
                "_parser_raw": {"routing": {"suggested_team": None, "suggested_agent": None}},
            },
        }
        return escalation_mod.run(ctx, item, services=services, dry_run=dry_run)

    monkeypatch.setattr(engine_mod, "run_escalation_lane", real_lane_with_a_staff_seam)

    envelope = Envelope(
        contact={"id": contact_id, "phone": "+60000000096", "custom_fields": []},
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": "ZZT-esc-clarify-qr-1",
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "I want to escalate to Nurain"},
            },
        },
    )

    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    assert result.status == "done", result.error
    sends = [a for a in result.actions if a["kind"] == "send_message"]
    assert len(sends) == 1, result.actions
    assert "DO Customer Service" in sends[0]["quick_replies"]

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    persisted = row.response["reply"]
    assert persisted["quick_replies"] == sends[0]["quick_replies"], (
        "the reply Chat History shows must carry the buttons the customer was sent: "
        f"{persisted!r} vs {sends[0]!r}"
    )
    assert persisted["text"] == sends[0]["text"]
    replied = next(r for r in row.trace if r["stage"] == "replied")
    assert replied["facts"]["quick_replies"] is True, (
        f"the trace says this turn offered nothing to tap: {replied['facts']!r}"
    )
