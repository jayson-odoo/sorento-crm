"""CHAT-PICK-QTY-STATE bug 4: a numbered did-you-mean inside a multi-product stock answer keeps
its roster when the cross-domain zero-stock rung adds its escalate offer.

Live shape: a twelve-code stock ask listed items 1..11, then "Couldn't find SRTWT 5827-2580. Did
you mean: 12. SRTWT5827 13. SRTWT5800 14. SRTWT5801" (a product_pick at 12-14), then the
zero-stock rung. `answer_bridge.apply_crossdomain_hit` replaced the roster with a bare Yes
team_pick (or with None when the contact is offered nothing), so the next `13` found no question
and the eleven items were listed again. Owner ruling: the numbered question wins; the rung renders
WITHOUT the offer sentence. Only the ladder call is stubbed.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot import answer_bridge
from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import compose as turn_compose
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus, Profile

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

OFFER = "escalate to warehouse team"
RUNG = "No incoming for SRTWT5827."
SUGGESTED = {12: "SRTWT5827", 13: "SRTWT5800", 14: "SRTWT5801"}
ANSWER_TEXT = (
    "SRTWT105 x 5: 40 in stock.\n\nCouldn't find SRTWT 5827-2580. Did you mean:\n"
    + "\n".join(f"{n}. {c}" for n, c in SUGGESTED.items())
    + "\nReply with a code to continue."
)
DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]


def _roster():
    return turn_pending.ask(
        "product_pick",
        [
            {
                "position": n, "label": c, "code": c, "entity_type": "product",
                "uuid": ht.uuid_of(c), "uuids": [ht.uuid_of(c)], "payload": {},
            }
            for n, c in SUGGESTED.items()
        ],
        asked_at_turn=3,
        payload={"domain": "inventory", "escalate_offered": False},
    )


@pytest.fixture
def rung(monkeypatch):
    result = {"render": {"_xdBlock": {"any": True, "block": RUNG, "team": "warehouse"}}}
    monkeypatch.setattr(answer_bridge, "_run_crossdomain_ladder", lambda **kw: result)


def _hit(question, tier):
    answer = turn_compose.Answer(text=ANSWER_TEXT, question=question)
    return answer_bridge.apply_crossdomain_hit(
        answer,
        envelope={"figures": []},
        parser={},
        resolved=None,
        entities_names=[],
        crossdomain_ladder={},
        ctx=SimpleNamespace(),
        services=None,
        contact_id="900000001",
        space_id=None,
        asked_at_turn=3,
        profile=Profile(tier=tier),
    )


def _positions(question):
    return [o["position"] for o in question.options]


@pytest.mark.parametrize("tier", ["dealer", "office"], ids=["offers_escalation", "no_offer"])
def test_the_roster_stays_the_question_and_the_rung_has_no_offer_sentence(rung, tier):
    out = _hit(_roster(), tier)
    assert out.question is not None, "the roster was dropped"
    assert out.question.kind == "product_pick"
    assert _positions(out.question) == [12, 13, 14]
    assert RUNG in out.text, "the rung's own block is still rendered"
    assert OFFER not in out.text.lower()


def test_guard_with_no_question_of_its_own_a_dealer_gets_the_offer_and_the_bare_yes(rung):
    out = _hit(None, "dealer")
    assert OFFER in out.text
    assert out.question is not None and out.question.kind == "team_pick"
    assert [o["label"] for o in out.question.options] == ["Yes"]


def test_guard_with_no_question_of_its_own_staff_get_no_offer_and_no_question(rung):
    out = _hit(None, "office")
    assert RUNG in out.text and OFFER not in out.text.lower()
    assert out.question is None


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("tier", ["dealer", "office"])
def test_thirteen_on_the_next_turn_resolves_the_suggested_code(rung, gate, tier):
    stored = _hit(_roster(), tier).question
    focus = Focus(products=ht.product_rows("SRTWT105"), domains=["inventory"])
    state = replace(ht.state(focus, pending=stored, turn_no=4), state_path=gate, state_gate=gate)
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], reference_positions=[13],
        open_question_answer={"mode": "pick", "picked": [13], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": 13}]
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        state, v = applied.state, applied.verdict
    _new_state, plan = apply(state, v, build_policy())
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert codes == ["SRTWT5800"], codes
