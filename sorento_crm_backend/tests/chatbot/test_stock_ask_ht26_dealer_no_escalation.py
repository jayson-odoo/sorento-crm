"""Owner hand test 26 Sep 2026 (PR #1247), F1: the dealer's did-you-mean, and no
escalation anywhere in a dealer's stock ask.

Owner ruling 26 Sep (verbatim): "we should offer the ELP3756 and yes, yes should still go
to warehouse, oh wait, btw dealer ask cannot have escalation, cannot have direct
escalation to warehouse, their contact point is sales person".

Orchestrator reading, implemented here: a one-candidate did-you-mean is offered as a pick
carrying the typed quantity ("Couldn't find ELP3753. Did you mean ELP3754?"); "yes" or
the code answers that product with the carried quantity; "no" refers the dealer to their
salesman. A dealer (an availability-only stock ask contact) is never offered or given an
escalation to the warehouse team anywhere in the stock ask: every such offer or stored
team pick becomes "Please refer to your salesman." with no pending question. Staff
contacts (detailed / compact) keep today's behaviour.

T15 "ELP3753 10" (a miss, one candidate) stored a `team_pick`; its "yes" would have
escalated. Every test below is T15's state or its answer.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.services.chatbot import dealer_stock as dealer
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

T15_ESCALATE = (
    'Couldn\'t find "ELP3753". Did you mean ELP3754? Reply with a code to continue, or '
    "would you like me to escalate to warehouse team?"
)


def _t15_pick(quantity=10, codes=("ELP3754",)):
    text, pick = dealer.did_you_mean(
        "ELP3753",
        [
            {"idx": i + 1, "label": c, "product": c, "uuid": ht.uuid_of(c), "entity_type": "product"}
            for i, c in enumerate(codes)
        ],
        quantity=quantity,
        asked_at_turn=15,
    )
    return text, pick


def _t15_focus():
    return Focus(
        domains=["inventory"],
        products=[
            {
                "raw": "ELP3753",
                "hint": "product",
                "canonical_code": "ELP3753",
                "quantity": 10,
                "current_message": False,
                "confident": True,
            }
        ],
    )


# --------------------------------------------------------------------------- #
# The did-you-mean pick
# --------------------------------------------------------------------------- #


def test_t15_one_candidate_is_a_pick_carrying_the_quantity():
    text, pick = _t15_pick()
    assert text == "Couldn't find ELP3753. Did you mean ELP3754?"
    assert "escalate" not in text.lower()
    assert pick.kind == "product_pick"
    assert [o["label"] for o in pick.options] == ["ELP3754"]
    assert pick.payload["stock_pick"] is True
    assert pick.payload["stock_qty"] == 10


def test_several_candidates_list_one_numbered_code_per_line():
    text, pick = _t15_pick(codes=("ELP3754", "ELP3756"))
    assert text == "Couldn't find ELP3753. Did you mean:\n1. ELP3754\n2. ELP3756"
    assert [o["label"] for o in pick.options] == ["ELP3754", "ELP3756"]


def test_the_miss_arm_builds_the_dealer_pick_from_the_offer():
    from app.services.chatbot.answer_bridge import _dealer_did_you_mean

    offer = {
        "suggest_last_result_set": [
            {"idx": 1, "label": "ELP3754", "value": "ELP3754", "product": "ELP3754",
             "uuid": ht.uuid_of("ELP3754"), "entity_type": "product"}
        ],
        "dym_candidates": [{"code": "ELP3754", "for_raw": "elp3753"}],
    }
    parser = {"entities": [{"raw": "elp3753", "hint": "product", "quantity": 10}]}
    text, pick = _dealer_did_you_mean(offer, parser, 15)
    assert text == "Couldn't find ELP3753. Did you mean ELP3754?"
    assert pick.payload["stock_qty"] == 10


def test_t15_yes_answers_elp3754_with_the_carried_ten():
    _text, pick = _t15_pick()
    state2, plan = apply(
        ht.state(_t15_focus(), pending=pick, turn_no=16, availability_only=True),
        verdict(is_affirmative=True, entities=[]),
        build_policy(),
    )
    specs = ht.inventory_specs(plan)
    assert len(specs) == 1
    assert [e.get("uuid") for e in specs[0].entities] == [ht.uuid_of("ELP3754")]
    assert specs[0].filters.get("requested_quantities") == {ht.uuid_of("ELP3754"): 10}
    assert state2.pending is None
    assert plan.trace.lane != "escalation"


def test_t16_typing_the_code_answers_it_with_the_carried_ten():
    from app.services.chatbot import turn_runtime

    _text, pick = _t15_pick()
    v = verdict(entities=[ht.asked("ELP3754")])
    state2, plan = apply(
        ht.state(_t15_focus(), pending=pick, turn_no=16, availability_only=True),
        v,
        build_policy(),
    )
    spec = ht.inventory_specs(plan)[0]
    out = turn_runtime._spec_quantities({"entities": v["entities"]}, spec, spec.entities)
    assert out["requested_quantities"] == {ht.uuid_of("ELP3754"): 10}
    assert state2.pending is None


def test_t15_no_refers_the_dealer_to_their_salesman_and_leaves_nothing_open():
    _text, pick = _t15_pick()
    state2, plan = apply(
        ht.state(_t15_focus(), pending=pick, turn_no=16, availability_only=True),
        verdict(is_affirmative=False, entities=[]),
        build_policy(),
    )
    assert plan.fetch == []
    assert plan.trace.task_question == "Please refer to your salesman."
    assert state2.pending is None
    assert plan.trace.lane not in ("escalation", "escalation_declined")


# --------------------------------------------------------------------------- #
# No escalation anywhere in a dealer's stock reply
# --------------------------------------------------------------------------- #


def _team_pick():
    return turn_pending.ask(
        "team_pick",
        [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="warehouse",
        expects="yes_no",
    )


def test_an_escalation_offer_becomes_refer_to_your_salesman():
    text, question = dealer.without_escalation(T15_ESCALATE, _team_pick())
    assert question is None
    assert "escalate" not in text.lower()
    assert text.endswith("Please refer to your salesman.")
    assert text.startswith('Couldn\'t find "ELP3753". Did you mean ELP3754?')


def test_a_bare_escalate_offer_on_a_miss_becomes_refer_to_your_salesman():
    text, question = dealer.without_escalation(
        "I couldn't find ELP3753.\n\nWould you like me to escalate to warehouse team?",
        _team_pick(),
    )
    assert text == "I couldn't find ELP3753.\n\nPlease refer to your salesman."
    assert question is None


def test_a_roster_keeps_its_pick_but_loses_its_attached_offer():
    roster = turn_pending.ask(
        "product_pick",
        [{"position": 1, "label": "A"}, {"position": 2, "label": "B"}],
        team="warehouse",
        payload={"escalate_offered": True},
    )
    text, question = dealer.without_escalation(
        "Did you mean:\n1. A\n2. B\nReply with a code to continue, or would you like me "
        "to escalate to warehouse team?",
        roster,
    )
    assert question is not None and question.kind == "product_pick"
    assert question.payload["escalate_offered"] is False
    assert "escalate" not in text.lower()


def test_a_reply_with_no_offer_is_untouched():
    text, question = dealer.without_escalation("ELP3754 x 10: yes, we have stock.", None)
    assert text == "ELP3754 x 10: yes, we have stock." and question is None


class _Plan:
    def __init__(self, *domains):
        self.domains = list(domains)


def test_engine_guard_applies_to_a_dealer_stock_ask_only():
    from app.services.chatbot.engine import _dealer_refers_to_salesman, _dealer_stock_ask
    from app.services.chatbot.turn import compose as turn_compose

    dealer_state = ht.state(Focus(domains=["inventory"]), availability_only=True)
    staff_state = ht.state(Focus(domains=["inventory"]))
    assert _dealer_stock_ask(dealer_state, _Plan("inventory")) is True
    assert _dealer_stock_ask(staff_state, _Plan("inventory")) is False
    assert _dealer_stock_ask(dealer_state, _Plan("promotion")) is False

    out = _dealer_refers_to_salesman(turn_compose.Answer(text=T15_ESCALATE, question=_team_pick()))
    assert out.question is None
    assert out.text.endswith("Please refer to your salesman.")


def test_engine_guard_keeps_the_dealer_pick():
    from app.services.chatbot.engine import _dealer_refers_to_salesman
    from app.services.chatbot.turn import compose as turn_compose

    text, pick = _t15_pick()
    answer = turn_compose.Answer(text=text, question=pick)
    assert _dealer_refers_to_salesman(answer) is answer


# --------------------------------------------------------------------------- #
# Who is a dealer: the contact's stock visibility policy, read with the profile
# --------------------------------------------------------------------------- #


def _seed_contact_with_policy(session_factory, mode: str | None) -> tuple[str, str]:
    db = session_factory()
    space_id = f"ZZT-SPACE-{uuid.uuid4().hex[:6]}"
    workspace_id = str(uuid.uuid4())
    contact_respond_id = f"ZZT-{uuid.uuid4().hex[:8]}"
    contact_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, api_key_ciphertext) "
            "VALUES (:id, :space_id, 'x')"
        ),
        {"id": workspace_id, "space_id": space_id},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, workspace_id, session_vars) "
            "VALUES (:id, :cid, :phone, :wid, CAST(:sv AS jsonb))"
        ),
        {
            "id": contact_id,
            "cid": contact_respond_id,
            "phone": f"+6004{uuid.uuid4().hex[:7]}",
            "wid": workspace_id,
            "sv": json.dumps({}),
        },
    )
    if mode is not None:
        db.execute(
            text(
                "INSERT INTO stock_visibility_policies (id, contact_id, mode) "
                "VALUES (:id, :contact_id, :mode)"
            ),
            {"id": str(uuid.uuid4()), "contact_id": contact_id, "mode": mode},
        )
    db.commit()
    return contact_respond_id, space_id


def test_load_profile_marks_an_availability_only_contact(session_factory):
    from app.services.chatbot import turn_runtime

    contact_respond_id, space_id = _seed_contact_with_policy(session_factory, "availability")
    profile, _recall = turn_runtime.load_profile(
        session_factory(), contact_respond_id, space_id=space_id
    )
    assert profile.stock_availability_only is True


def test_load_profile_leaves_a_detailed_contact_as_staff(session_factory):
    from app.services.chatbot import turn_runtime

    contact_respond_id, space_id = _seed_contact_with_policy(session_factory, "detailed")
    profile, _recall = turn_runtime.load_profile(
        session_factory(), contact_respond_id, space_id=space_id
    )
    assert profile.stock_availability_only is False


def test_load_profile_unknown_contact_is_not_a_dealer(session_factory):
    from app.services.chatbot import turn_runtime

    profile, _recall = turn_runtime.load_profile(
        session_factory(), f"ZZT-unknown-{uuid.uuid4().hex[:8]}", space_id="ZZT-NONE"
    )
    assert profile.stock_availability_only is False
