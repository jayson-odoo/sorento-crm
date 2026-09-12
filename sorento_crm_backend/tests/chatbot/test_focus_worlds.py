"""S3 reds, from the UAC (AC-1006, AC-1007, AC-1009, AC-1014, AC-1015, AC-1018, AC-1025).

New `OwnerWorld` entries, run through the SAME harness `tests/chatbot/test_worlds.py`
already built for growth r1 slice B5 (`test_owner_world`) - imported here rather than
duplicated, since a second copy of `owner_stubs` / `_assert_owner_expectations` is one
more thing to keep in step with the real one. `tests/chatbot/worlds.py` carries the
`OwnerWorld` / `OwnerTurn` dataclasses and the small row builders (`_product`,
`_customer`, `_roster`, `_answers`); this file's own worlds are a local tuple, not an
addition to `worlds.OWNER_WORLDS`, precisely so nothing already committed there needs
editing for this slice's reds to land.

RED, expected: L1-S3 (the engine's `answered` stage - resolving an open question through
`dialogue/open_question.py`, and `compile_current_state` persisting the five keys as the
source of truth rather than a shadow computed alongside the legacy markers) has not
landed. Today `output_exchange.py` still decides "was there a picker" and resolves an
answered question off the LEGACY `selection_context` / `pending` markers (its own
comment: "`selection_context` is that marker today and stays the reader for one release
(AC-951); slice B4 replaces it with `open_question` and this line with it"). `focus`'s
carry rules (`domains`, `products`, `customer`, `date_window`) DO already run for real
via `output_exchange.py::focus_rules.apply`, wired at S1, so those halves may already
read correctly; the open-question half is the S3 red.

**AC-1006's conversation-closed half is NOT simulated by a session key** - there is no
`conversation_closed` key; the five-key wall (AC-1001) rejects one. S0 (58c5993eb)
already wires the real event:
`sla_service.ConversationSLATrackingService._clear_chatbot_dialogue_state_best_effort`,
called from ticket resolve beside the Respond close, under the last-open-sibling gate,
idempotent. This file calls that method directly between turns, the same way a resolved
ticket would trigger it, rather than reaching for an invented marker.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from tests.chatbot import worlds as worlds_mod
from tests.chatbot.worlds import OwnerTurn, OwnerWorld, _answers, _customer, _product, _roster
from tests.chatbot.test_worlds import (  # noqa: F401 - fixtures/helpers reused by name
    OWNER_CONTACT,
    _assert_owner_expectations,
    _owner_emission,
    _owner_envelope,
    _owner_fragments,
    _owner_resolve_gate_bundle,
    _owner_session,
    _patch_owner_session,
    owner_stubs,
)


# A sentinel `arm` key, never written to the session: `test_focus_world` intercepts it
# and calls the REAL SLA close path instead (see AC-1006's world, below).
_SLA_CLOSE_SENTINEL = "__sla_conversation_close__"


NEW_WORLDS: tuple[OwnerWorld, ...] = (
    OwnerWorld(
        world_id="focus-product-carries-past-turn-ten-then-conversation-closes",
        acs=("AC-1006",),
        why=(
            "D9: no counter, no TTL, anywhere. A product asked at turn 1 and never "
            "replaced still carries at turn 11 - nine bare continuation turns in "
            "between prove nothing ages it out. Then the Respond.io conversation is "
            "closed, and the next message with no product must ask which one: the "
            "conversation-closed marker is the ONLY thing (besides a same-axis replace "
            "or a topic reset) that clears a focus slot."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={"focus_products": ["SRTWC8517"], "focus_domains": ["inventory"]},
            ),
            *(
                OwnerTurn(
                    message="and the price?",
                    emission={
                        "message_type": "business_query",
                        "domain_hint": None,
                        "intent_hint": None,
                        "entities": [],
                        "entity_op": "reuse",
                    },
                    expect={"focus_products": ["SRTWC8517"]},
                )
                for _ in range(9)
            ),
            # Turn 11: the conversation-closed event. `arm` carries the sentinel key
            # `_SLA_CLOSE_SENTINEL`, which `test_focus_world` (below) intercepts and
            # turns into a REAL call to
            # `sla_service.ConversationSLATrackingService._clear_chatbot_dialogue_state_
            # best_effort` between turns - exactly what a resolved ticket does - rather
            # than writing anything to the session directly. That method nulls `focus`
            # and `open_question` wholesale, outside this turn's own trace (it is a
            # separate DB write the SLA path made, not something turn 11 itself
            # decided), so there is no `decay` line to grade here - only that the slot
            # is actually gone by the time turn 11 runs.
            OwnerTurn(
                message="hello?",
                arm={_SLA_CLOSE_SENTINEL: True},
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                },
                expect={
                    "focus_products": None,
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-incoming-switches-domain-then-what-about-y-replaces-product",
        acs=("AC-1007",),
        emits_v3=True,
        why=(
            "'incoming?' after a stock answer keeps the product and sets "
            "focus.domains = [incoming]; 'what about Y' after that replaces the "
            "product and KEEPS incoming - the domain switch must not also become "
            "sticky to the OLD product."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                emission={
                    "message_type": "business_query",
                    "asks": [{"domain": "inventory", "entities": [_product("SRTWC8517")]}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={"focus_products": ["SRTWC8517"], "focus_domains": ["inventory"]},
            ),
            OwnerTurn(
                message="incoming?",
                emission={
                    "message_type": "business_query",
                    "asks": [{"domain": "incoming", "entities": []}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={"focus_products": ["SRTWC8517"], "focus_domains": ["incoming"]},
            ),
            OwnerTurn(
                message="what about SRTKS6091",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "entities": [_product("SRTKS6091")],
                    "asks": [{"domain": None, "entities": [_product("SRTKS6091")]}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={"focus_products": ["SRTKS6091"], "focus_domains": ["incoming"]},
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-customer-replace-then-last-month-replaces-only-date",
        lane="business",
        acs=("AC-1009",),
        why=(
            "After a DO result, 'for customer ABC instead' replaces ONLY the customer "
            "slot and reruns the order tool; 'last month' then replaces ONLY the date "
            "window - one axis per turn (`replace_same_axis` and `date_restated_only`)."
        ),
        turns=(
            OwnerTurn(
                message="DO for XYZ",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [_customer("XYZ")],
                },
                expect={"focus_customer": "XYZ", "focus_domains": ["order"]},
            ),
            OwnerTurn(
                message="for customer ABC instead",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [_customer("ABC")],
                },
                expect={"focus_customer": "ABC", "focus_domains": ["order"]},
            ),
            OwnerTurn(
                message="last month",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "date_mode": "range",
                    "date_filter_start": "2026-08-01",
                    "date_filter_end": "2026-08-31",
                },
                expect={
                    "focus_customer": "ABC",
                    "focus_date_window": {
                        "start": "2026-08-01",
                        "end": "2026-08-31",
                        "mode": "range",
                    },
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-picker-two-resolves-then-two-again-is-a-new-message",
        lane="business",
        emits_v3=True,
        acs=("AC-1014",),
        why=(
            "A picker of 3 products is offered. '2' resolves to the SECOND FROZEN "
            "option. '2' again, with the question already answered and nothing open, "
            "is a NEW MESSAGE - never a second answer to a question that closed the "
            "moment it was answered (AC-1020: an open question is never silently "
            "re-answered)."
        ),
        turns=(
            OwnerTurn(
                message="SRTKS8091 got stock?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTKS8091")],
                    "asks": [{"domain": "inventory", "entities": [_product("SRTKS8091")]}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={"focus_products": ["SRTKS8091"]},
            ),
            OwnerTurn(
                message="2",
                arm={
                    "selection_context": "disambiguation",
                    "last_result_set": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "product_pick",
                    "focus_products": ["SRTKS8091-B"],
                    "open_question_gone": True,
                },
            ),
            OwnerTurn(
                message="2",
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(resolved=False),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    # Nothing open: "2" answers nothing, and the alive product from the
                    # last REAL pick is what a bare continuation would still carry.
                    "answered": None,
                    "focus_products": ["SRTKS8091-B"],
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-one-team-offer-yes-runs-escalation",
        emits_v3=True,
        lane="escalation",
        acs=("AC-1015",),
        why="A one-team escalate offer: 'yes' runs the escalation lane (D5's yes/no shape).",
        turns=(
            OwnerTurn(
                message="I need a human",
                arm={"pending": {"kind": "escalation_offer", "team": "warehouse"}},
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "is_affirmative": True,
                    "answers_open_question": _answers(resolved=True, yes_no="yes"),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={"answered": "team_pick", "branch_kind": "out_of_scope", "lane_ran": True},
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-one-team-offer-no-renders-declined",
        emits_v3=True,
        acs=("AC-1015",),
        why="A one-team escalate offer: 'no' renders the declined copy, never the lane.",
        turns=(
            OwnerTurn(
                message="I need a human",
                arm={"pending": {"kind": "escalation_offer", "team": "warehouse"}},
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "is_affirmative": False,
                    "answers_open_question": _answers(resolved=True, yes_no="no"),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "team_pick",
                    "branch_kind": "escalation_declined",
                    "lane_ran": False,
                    "open_question_gone": True,
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-one-team-offer-new-ask-clears-it-and-answers-stock",
        lane="business",
        acs=("AC-1015",),
        why=(
            "'SRTWC8517 stock?' instead of yes/no is a NEW ASK: the offer is cleared "
            "with a trace line at received, never read as an answer, and the stock "
            "question is answered."
        ),
        turns=(
            OwnerTurn(
                message="I need a human",
                arm={"pending": {"kind": "escalation_offer", "team": "warehouse"}},
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                },
                expect={
                    "focus_products": ["SRTWC8517"],
                    "open_question_gone": True,
                    "decayed": ("open_question",),
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-pick-reruns-the-alive-domain",
        lane="business",
        emits_v3=True,
        acs=("AC-1018",),
        why=(
            "A pick resolves the entity and then reruns every alive domain in "
            "focus.domains for it - one domain here, so this is the base case AC-1049 "
            "extends to many."
        ),
        turns=(
            OwnerTurn(
                message="which one has stock",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [],
                    "asks": [{"domain": "inventory", "entities": []}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                arm={
                    "selection_context": "disambiguation",
                    "last_result_set": _roster("SRTKS8091-A", "SRTKS8091-B"),
                },
                expect={"focus_domains": ["inventory"]},
            ),
            OwnerTurn(
                message="1",
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(resolved=True, picks=[1]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "product_pick",
                    "focus_products": ["SRTKS8091-A"],
                    "branch_kind": "business_query",
                    "lane_ran": True,
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-clarifier-asks-which-product-then-answers-without-re-ask",
        acs=("AC-1025",),
        why=(
            "'eta?' with focus.domains set and no product (cleared by an earlier topic "
            "reset) makes the clarifier ask for the missing product; the dealer's "
            "'SRTWT2635' then runs the business lane over the set domains WITHOUT a "
            "re-ask."
        ),
        turns=(
            OwnerTurn(
                message="别的, any incoming?",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "incoming",
                    "intent_hint": "check_incoming",
                    "entities": [],
                    "topic_reset": True,
                },
                expect={"focus_domains": ["incoming"], "focus_products": None},
            ),
            OwnerTurn(
                message="eta?",
                emission={
                    "message_type": "clarification",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                },
                expect={"branch_kind": "clarify_menu", "lane_ran": False},
            ),
            OwnerTurn(
                message="SRTWT2635",
                emission={
                    "message_type": "business_query",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [_product("SRTWT2635")],
                },
                expect={
                    "focus_products": ["SRTWT2635"],
                    "focus_domains": ["incoming"],
                    "branch_kind": "business_query",
                },
            ),
        ),
    ),
)


@pytest.mark.parametrize("world", NEW_WORLDS, ids=lambda w: w.world_id)
def test_focus_world(world, owner_stubs, session_factory, monkeypatch) -> None:
    """One authored conversation, turn by turn, on the CRM's own memory.

    Byte-for-byte the same runner `test_worlds.py::test_owner_world` uses over
    `worlds.OWNER_WORLDS` - see that function's own docstring for what each stub
    stands in for. Duplicated rather than imported as a function because pytest
    parametrizes over THIS file's own `NEW_WORLDS`, not the shared tuple.
    """
    lane_calls: list[str] = []
    db = session_factory()
    db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), {"c": OWNER_CONTACT})
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :c, :p, CAST(:sv AS jsonb))"
        ),
        {"c": OWNER_CONTACT, "p": "+60000000778", "sv": json.dumps({"variables": {}})},
    )
    settings_row = db.query(SystemSetting).first()
    if settings_row is None:
        settings_row = SystemSetting()
        db.add(settings_row)
    if world.lane == "business":
        settings_row.chatbot_business_lane_enabled = True
    if world.lane == "escalation":
        lanes = list(settings_row.chatbot_completed_lanes or [])
        if "out_of_scope" not in lanes:
            settings_row.chatbot_completed_lanes = [*lanes, "out_of_scope"]
    db.commit()

    if world.lane == "business":
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: _owner_resolve_gate_bundle(lane_calls),
        )
    if world.lane == "escalation":
        def _fake_escalation(ctx, item, *, dry_run=False, session_factory=None):
            lane_calls.append("escalation")
            return {"arm": "human-intervention", "clarify": None, "actions": [], "pending": None}

        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation)

    for index, turn in enumerate(world.turns):
        if turn.arm and _SLA_CLOSE_SENTINEL in turn.arm:
            # AC-1006's conversation-closed half: the REAL event, not an invented
            # session key. `_clear_chatbot_dialogue_state_best_effort` only reads
            # `tracking.respond_contact_id`, so a duck-typed stand-in is enough - no
            # real ConversationSLATracking row is needed to exercise it.
            from types import SimpleNamespace

            from app.models.access import RespondContact
            from app.services.sla_service import ConversationSLATrackingService

            db = session_factory()
            contact_id = (
                db.query(RespondContact.id)
                .filter(RespondContact.respond_io_id == OWNER_CONTACT)
                .scalar()
            )
            ConversationSLATrackingService(db)._clear_chatbot_dialogue_state_best_effort(
                SimpleNamespace(respond_contact_id=contact_id, id="ZZT-owner-world-ticket")
            )
        elif turn.arm:
            _patch_owner_session(session_factory, turn.arm, drop=("open_question",))
        owner_stubs(_owner_emission(turn.emission), emits_v3=world.emits_v3)
        envelope = _owner_envelope(turn.message, index)
        lane_calls.clear()
        result = engine_mod.run_turn(Envelope(**envelope), session_factory=session_factory)
        assert result.status != "failed", (
            f"{world.world_id} turn {index + 1} failed at {result.stage}: {result.error}"
        )
        if result.delegate is not None:
            engine_mod.complete_turn(
                result.turn_id, _owner_fragments(world), session_factory=session_factory
            )
        row = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.id == result.turn_id)
            .first()
        )
        _assert_owner_expectations(
            world,
            turn,
            index,
            variables=_owner_session(session_factory),
            qf=((result.ctx or {}).get("parse") or {}).get("output") or {},
            trace=list(row.trace or []),
            result=result,
            lane_calls=list(lane_calls),
        )


def test_every_new_world_names_its_ac_and_a_reason() -> None:
    for world in NEW_WORLDS:
        assert world.acs, f"{world.world_id} grades no stated criterion"
        assert len(world.why) > 40, f"{world.world_id} does not say why it exists"
