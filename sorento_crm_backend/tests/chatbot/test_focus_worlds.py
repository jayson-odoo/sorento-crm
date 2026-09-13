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
        world_id="focus-v1-explicit-new-domain-drops-the-old-subject",
        # emits_v3 is FALSE, and that is the whole point: this is the PROMOTED prompt.
        acs=("AC-1008",),
        why=(
            "Browser verification, 13 Sep 2026: under the promoted v1 prompt a topic "
            "change cleared nothing, because `topic_reset` is a v3 key and `v3_signals` "
            "returns False for it under v1 by design. Owner ruling K rule 2 is the ONLY "
            "trigger a v1 deployment has - an EXPLICIT new-domain query bringing its own "
            "scope - and it had gone dead reading `prev.domain_hint` off a session that "
            "is five keys. Same world, same clearing, on the prompt that answers "
            "customers today."
        ),
        turns=(
            OwnerTurn(
                message="orders for Hanlim",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "order",
                    "intent_hint": "check_order",
                    "entities": [_customer("Hanlim")],
                },
                expect={"focus_customer": "Hanlim", "focus_domains": ["order"]},
            ),
            OwnerTurn(
                message="promo for MKS9141",
                emission={
                    "message_type": "business_query",
                    "domain_hint": "promotion",
                    "intent_hint": "check_promotion",
                    "entities": [_product("MKS9141")],
                },
                expect={
                    # The new subject stands, and the OLD one's customer is gone rather
                    # than left narrowing a question nobody asked about them (H66).
                    "focus_products": ["MKS9141"],
                    "focus_domains": ["promotion"],
                    "focus_customer": None,
                },
            ),
        ),
    ),
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
        world_id="focus-picker-two-then-three-re-picks-the-third-row",
        lane="business",
        emits_v3=True,
        acs=("AC-1014",),
        why=(
            "A picker of 3 products is offered. '2' resolves to the SECOND FROZEN "
            "option. '3', with the roster still alive, RE-PICKS the THIRD frozen "
            "option (owner 13 Sep 2026, D19, sticky roster) - a pick does not consume "
            "its roster, restoring ruling K rule 1 / 7 Sep deviation 5 and superseding "
            "AC-1014's close-on-answer clause the 12 Sep UAC introduced."
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
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
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
                    "open_question_kind": "product_pick",
                },
            ),
            OwnerTurn(
                message="3",
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(resolved=True, picks=[3]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    # The roster from turn 2 is STILL ALIVE (D19): "3" re-picks the
                    # third frozen option, and the question stays open for a further
                    # pick.
                    "answered": "product_pick",
                    "focus_products": ["SRTKS8091-C"],
                    "open_question_kind": "product_pick",
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
                arm={
                    "open_question": {
                        "kind": "team_pick",
                        "options": [],
                        "expects": "yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {"team": "warehouse"},
                    },
                },
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
                arm={
                    "open_question": {
                        "kind": "team_pick",
                        "options": [],
                        "expects": "yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {"team": "warehouse"},
                    },
                },
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
                arm={
                    "open_question": {
                        "kind": "team_pick",
                        "options": [],
                        "expects": "yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {"team": "warehouse"},
                    },
                },
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
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B"),
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
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
    # ----------------------------------------------------------------- #
    # D19 (owner 13 Sep 2026): sticky roster. A pick does NOT consume its
    # roster. See PLAN-chatbot-focus-multi-domain.md D19 and
    # tests/chatbot/test_sticky_roster_tail.py for the persistence-level pins;
    # these four worlds grade the same rule end to end through a real turn.
    # ----------------------------------------------------------------- #
    OwnerWorld(
        world_id="focus-tier-pick-then-second-number-re-picks",
        lane="business",
        emits_v3=True,
        acs=("AC-1014",),
        why=(
            "A promo tier menu (office / dealer / end_user) is offered for one "
            "product. '1' resolves office. '2', with the roster still alive (D19 "
            "rule 1 applies to every roster kind, not only product_pick), re-picks "
            "dealer rather than answering nothing."
        ),
        turns=(
            OwnerTurn(
                message="1",
                arm={
                    "open_question": {
                        "kind": "tier_pick",
                        "options": [
                            {"idx": 1, "tier": "office", "label": "Office"},
                            {"idx": 2, "tier": "dealer", "label": "Dealer"},
                            {"idx": 3, "tier": "end_user", "label": "End user"},
                        ],
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
                },
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
                    "answered": "tier_pick",
                    "focus_tier": ["office"],
                    "open_question_kind": "tier_pick",
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
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "tier_pick",
                    "focus_tier": ["dealer"],
                    "open_question_kind": "tier_pick",
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-pick-then-offer-yes-escalates",
        lane="escalation",
        emits_v3=True,
        acs=("AC-1014", "AC-1015"),
        why=(
            "D19 rule 3: the one-team escalate offer a pick's own rerun-miss "
            "produces RIDES on the roster question instead of replacing it with a "
            "bare team_pick. Armed directly rather than driving an actual "
            "pick-then-miss through the real resolve+gate seam (the harness has no "
            "deterministic way to force a miss there) - the merge's OWN "
            "construction is pinned at the unit level "
            "(tests/chatbot/test_sticky_roster_tail.py::"
            "TestTheOfferRidesOnTheRosterInsteadOfReplacingIt); this world grades "
            "what happens NEXT: 'yes' runs the escalation lane and consumes the "
            "whole merged question."
        ),
        turns=(
            OwnerTurn(
                message="yes please",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick_or_yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {
                            "team": "purchasing",
                            "domain": "inventory",
                            "offer": {
                                "team": "purchasing",
                                "domain": "inventory",
                                "options": [
                                    {"idx": 1, "team": "purchasing", "label": "purchasing"}
                                ],
                            },
                        },
                    },
                },
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
                expect={
                    "answered": "team_pick",
                    "branch_kind": "out_of_scope",
                    "lane_ran": True,
                    "open_question_gone": True,
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-pick-then-offer-no-keeps-roster",
        lane="business",
        emits_v3=True,
        acs=("AC-1014", "AC-1015"),
        why=(
            "D19 rule 3's other half: 'no' declines the escalate offer riding the "
            "roster WITHOUT closing the roster - the offer comes off "
            "(expects reverts to 'pick', no payload.offer) and a further pick still "
            "resolves against the same frozen rows (rule 1). Armed directly, same "
            "simplification as focus-pick-then-offer-yes-escalates."
        ),
        turns=(
            OwnerTurn(
                message="no",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick_or_yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {
                            "team": "purchasing",
                            "domain": "inventory",
                            "offer": {
                                "team": "purchasing",
                                "domain": "inventory",
                                "options": [
                                    {"idx": 1, "team": "purchasing", "label": "purchasing"}
                                ],
                            },
                        },
                    },
                },
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
                    "open_question_kind": "product_pick",
                    "open_question_expects": "pick",
                    "open_question_offer_team": None,
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
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "product_pick",
                    "focus_products": ["SRTKS8091-B"],
                    "open_question_kind": "product_pick",
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-pick-then-new-subject-clears-roster",
        lane="business",
        emits_v3=True,
        acs=("AC-1014", "AC-1020"),
        why=(
            "D19 rule 2: a sticky roster still clears by the EXISTING rules - naming "
            "its own subject is one of them (AC-1020). 'SRTWC8517 stock?' arriving "
            "over a live roster (offer included) must clear it - roster and offer "
            "both - and answer the NEW product, not read as a further pick."
        ),
        turns=(
            OwnerTurn(
                message="SRTWC8517 stock?",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick_or_yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {
                            "team": "purchasing",
                            "domain": "inventory",
                            "offer": {
                                "team": "purchasing",
                                "domain": "inventory",
                                "options": [
                                    {"idx": 1, "team": "purchasing", "label": "purchasing"}
                                ],
                            },
                        },
                    },
                },
                emission={
                    "message_type": "business_query",
                    "domain_hint": "inventory",
                    "intent_hint": "check_stock",
                    "entities": [_product("SRTWC8517")],
                    "asks": [{"domain": "inventory", "entities": [_product("SRTWC8517")]}],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "focus_products": ["SRTWC8517"],
                    "answered": None,
                    "open_question_gone": True,
                },
            ),
        ),
    ),
    # ----------------------------------------------------------------- #
    # B2 (Opus S6 review, blocker): under the promoted v1 prompt there is no
    # `answers_open_question` at all, so a bare "yes"/"no" over a merged roster is
    # answered entirely through the OLD `is_affirmative` + `offer_is_open` path,
    # never through `dialogue/open_question.resolve`. `open_question_answered` is a
    # v3-only stamp, so `carry_after_answer` is never called for a v1 turn - the
    # merged question survives the escalation with its offer still riding it
    # (finding S2), and a second "yes" would re-escalate. RED on purpose: the coder
    # wires the v1 escalation-confirmation path to consume/strip the question too.
    # ----------------------------------------------------------------- #
    OwnerWorld(
        world_id="focus-pick-then-offer-yes-escalates-under-v1",
        lane="escalation",
        emits_v3=False,
        acs=("AC-1014", "AC-1015"),
        why=(
            "B2 / finding S2: a bare 'yes' over a merged roster under the PROMOTED "
            "v1 prompt reaches escalation only through output_exchange.offer_is_open "
            "(is_affirmative + offered_escalation), never through "
            "dialogue/open_question.resolve - there is no answers_open_question key "
            "at all under v1. The escalation runs, but open_question_answered is a "
            "v3-only stamp, so compile_state's carry_after_answer is never called and "
            "the merged question - offer included - survives the escalation it just "
            "ran, letting a second 'yes' re-escalate."
        ),
        turns=(
            OwnerTurn(
                message="yes",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick_or_yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {
                            "team": "purchasing",
                            "domain": "inventory",
                            "offer": {
                                "team": "purchasing",
                                "domain": "inventory",
                                "options": [
                                    {"idx": 1, "team": "purchasing", "label": "purchasing"}
                                ],
                            },
                        },
                    },
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "is_affirmative": True,
                },
                expect={
                    "lane_ran": True,
                    "open_question_kind": None,
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-pick-then-offer-no-keeps-roster-under-v1",
        emits_v3=False,
        acs=("AC-1014", "AC-1015"),
        why=(
            "B2 / finding S2's decline half under v1: 'no' over a merged roster sets "
            "escalation.is_escalation_confirmation False directly through the "
            "is_affirmative path, never through carry_after_answer - so the offer is "
            "never stripped and the roster comes back with expects still "
            "pick_or_yes_no instead of reverting to pick."
        ),
        turns=(
            OwnerTurn(
                message="no",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick_or_yes_no",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {
                            "team": "purchasing",
                            "domain": "inventory",
                            "offer": {
                                "team": "purchasing",
                                "domain": "inventory",
                                "options": [
                                    {"idx": 1, "team": "purchasing", "label": "purchasing"}
                                ],
                            },
                        },
                    },
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "is_affirmative": False,
                },
                expect={
                    "open_question_kind": "product_pick",
                    "open_question_expects": "pick",
                    "open_question_offer_team": None,
                },
            ),
        ),
    ),
    # ----------------------------------------------------------------- #
    # B3 (owner-found on :3081): a survived roster must never take the CURRENT
    # turn's ANSWER rows as its own options. See
    # tests/chatbot/test_sticky_roster_tail.py::TestASurvivedRosterNeverTakesTheAnswersRows
    # for the unit-level pin; this world grades the same rule end to end.
    # ----------------------------------------------------------------- #
    OwnerWorld(
        world_id="focus-tier-pick-hit-then-second-number-re-picks-dealer",
        lane="business",
        emits_v3=True,
        acs=("AC-1014",),
        why=(
            "'promo for srtwc286' -> tier menu; '1' -> HIT, the promotion lane's reply "
            "lists 3 promotions numbered 1..3; '2' must still resolve against the "
            "TIER menu (dealer), not against the promotion file names the HIT reply "
            "printed. Owner-found on :3081: after the '1' turn the persisted "
            "open_question kept kind: tier_pick but its options became the three "
            "promotion file names, and the next '2' resolved to a file name instead "
            "of a tier."
        ),
        turns=(
            OwnerTurn(
                message="1",
                arm={
                    "open_question": {
                        "kind": "tier_pick",
                        "options": [
                            {"idx": 1, "tier": "office", "label": "Office"},
                            {"idx": 2, "tier": "dealer", "label": "Dealer"},
                            {"idx": 3, "tier": "end_user", "label": "End user"},
                        ],
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
                },
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
                    "answered": "tier_pick",
                    "open_question_kind": "tier_pick",
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
                    "answers_open_question": _answers(resolved=True, picks=[2]),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": "tier_pick",
                    "focus_tier": ["dealer"],
                    "open_question_kind": "tier_pick",
                },
            ),
        ),
    ),
    # ----------------------------------------------------------------- #
    # S5 (Opus S6 review, should-fix): AC-1020 / D19 rule 2 pinned only for "names
    # its own subject" - a SURVIVED roster clears by the same existing rules too.
    # ----------------------------------------------------------------- #
    OwnerWorld(
        world_id="focus-survived-roster-casual-leaves-it",
        lane="business",
        emits_v3=True,
        acs=("AC-1014", "AC-1020"),
        why=(
            "A pick survives per D19 rule 1; a later CASUAL message ('thanks') that "
            "neither answers nor asks anything must leave the survived roster exactly "
            "as it was - the pre-existing AC-1020 rule, now exercised over a roster "
            "that D19 keeps alive rather than one a lane just composed."
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
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
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
                    "open_question_kind": "product_pick",
                },
            ),
            OwnerTurn(
                message="thanks",
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": False,
                },
                expect={
                    "answered": None,
                    "open_question_kind": "product_pick",
                },
            ),
        ),
    ),
    OwnerWorld(
        world_id="focus-survived-roster-topic-reset-clears-it",
        emits_v3=True,
        acs=("AC-1008", "AC-1014", "AC-1020"),
        why=(
            "D19 rule 2: a survived roster still clears by the existing rules - "
            "topic_reset is one of them. Armed directly, with nothing else in focus, "
            "so the engine's `if cleared_question:` truthiness check (`clearing.apply`'s "
            "SECOND return value, the trace lines) is not accidentally satisfied by an "
            "UNRELATED focus-slot decay line - a two-turn version of this world (a real "
            "product+domain focus established first) passes for the WRONG reason, "
            "because topic_reset's own focus-clearing lines make `cleared_question` "
            "truthy and null the question as a side effect. Isolated like this, RED ON "
            "PURPOSE (S5): dialogue/clearing.py's topic_reset arm loops over `focus` "
            "only and never touches `open_question` at all."
        ),
        turns=(
            OwnerTurn(
                message="another one",
                arm={
                    "open_question": {
                        "kind": "product_pick",
                        "options": _roster("SRTKS8091-A", "SRTKS8091-B", "SRTKS8091-C"),
                        "expects": "pick",
                        "asked_at_turn": 1,
                        "asked_at": None,
                        "payload": {},
                    },
                },
                emission={
                    "message_type": "casual",
                    "domain_hint": None,
                    "intent_hint": None,
                    "entities": [],
                    "asks": [],
                    "answers_open_question": _answers(),
                    "anaphora": False,
                    "topic_reset": True,
                },
                expect={
                    "open_question_kind": None,
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
            _patch_owner_session(session_factory, turn.arm)
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
