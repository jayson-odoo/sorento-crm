"""AC-106 / R3: an open escalation offer is recognised from EITHER form (review S6).

H13 is the frozen string contract: the JS decided "is an escalation offer open?" by
matching the literal phrase "would you like me to escalate" against the previous reply.
D11 says understanding text is the parser's job, so S2 writes a `pending.kind` marker
instead and S8 deletes the regex.

Between those two slices the CRM and n8n both write sessions, and they deploy at different
moments. So the reader has to accept both, and BOTH halves need a test - the corpus can
only ever exercise the legacy half, because no captured fixture has a `pending` key.

The two clauses this drives are `offeredEscalation` (which flips
`escalation.is_escalation_confirmation` on an affirmative) and the open-offer company-pick
arm; both read the same helper.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.head import output_exchange as ox

LEGACY_OFFER = "I can't answer that myself. Would you like me to escalate this to a colleague?"


def _qf(**overrides):
    base = {
        "message_type": "casual",
        "intent_hint": None,
        "domain_hint": None,
        "entities": [],
        "entity_op": "reuse",
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_affirmative": True,
        "escalation": {"is_escalation_confirmation": False},
        "routing": {"suggested_team": None, "suggested_agent": None, "team_source": None},
    }
    base.update(overrides)
    return base


def _run(previous_state: dict, qf: dict | None = None) -> dict:
    parent_input = {
        "latest_user_message": "yes please",
        "previous_conversation_state": previous_state,
    }
    return ox.post_process({"output": qf or _qf()}, {}, parent_input)["output"]


class TestOfferIsOpen:
    """The helper itself, both forms and the closed case."""

    def test_the_legacy_frozen_string_alone_opens_the_offer(self) -> None:
        assert ox._offer_is_open({"response": LEGACY_OFFER}) is True

    def test_the_pending_marker_alone_opens_the_offer(self) -> None:
        """No legacy string anywhere: a session the CRM wrote after S2."""
        assert ox._offer_is_open({"pending": {"kind": "escalation_offer"}}) is True

    def test_both_together_open_it_once(self) -> None:
        assert (
            ox._offer_is_open(
                {"response": LEGACY_OFFER, "pending": {"kind": "escalation_offer"}}
            )
            is True
        )

    def test_neither_leaves_it_closed(self) -> None:
        assert ox._offer_is_open({"response": "Here are 3 promotions."}) is False
        assert ox._offer_is_open({}) is False
        assert ox._offer_is_open(None) is False

    @pytest.mark.parametrize("kind", ["team_clarify", "company_clarify", "tier_ask"])
    def test_a_DIFFERENT_pending_kind_does_not_open_an_escalation_offer(self, kind: str) -> None:
        """The marker is typed for exactly this reason: a pending tier ask is not an
        escalation offer, and treating it as one would escalate on a tier reply."""
        assert ox._offer_is_open({"pending": {"kind": kind}}) is False


class TestThroughPostProcess:
    """The consequence: an affirmative on an open offer confirms the escalation."""

    def test_the_legacy_string_plus_yes_confirms(self) -> None:
        output = _run({"response": LEGACY_OFFER})
        assert output["escalation"] == {"is_escalation_confirmation": True}

    def test_the_marker_plus_yes_confirms_identically(self) -> None:
        output = _run({"pending": {"kind": "escalation_offer"}})
        assert output["escalation"] == {"is_escalation_confirmation": True}

    def test_no_open_offer_plus_yes_does_not_confirm(self) -> None:
        output = _run({"response": "Here are 3 promotions."})
        assert output["escalation"].get("is_escalation_confirmation") is not True

    def test_the_marker_plus_no_is_a_decline_not_silence(self) -> None:
        output = _run({"pending": {"kind": "escalation_offer"}}, _qf(is_affirmative=False))
        assert output["escalation"] == {
            "is_escalation_confirmation": False,
            "escalation_declined": True,
        }
        assert output["message_type"] == "casual"


class TestOpenOfferCompanyPick:
    """The second reader of the same helper: a company pick on an offer with no roster."""

    def _company_state(self, **extra) -> dict:
        state = {
            "routing_companies": [
                {"company_name": "Sorento"},
                {"company_name": "Mocha"},
            ],
            "routing": {"suggested_team": "marketing_product"},
        }
        state.update(extra)
        return state

    def test_the_marker_alone_lets_a_company_pick_engage_the_offer(self) -> None:
        qf = _qf(is_affirmative=None)
        qf["escalation"] = {"is_escalation_confirmation": False, "company_pick": "mocha"}
        output = ox.post_process(
            {"output": qf},
            {},
            {
                "latest_user_message": "mocha",
                "previous_conversation_state": self._company_state(
                    pending={"kind": "escalation_offer"}
                ),
            },
        )["output"]
        assert output["escalation"]["is_escalation_confirmation"] is True
        assert output["escalation"]["company_pick"] == "Mocha"

    def test_with_no_open_offer_the_same_reply_is_left_alone(self) -> None:
        qf = _qf(is_affirmative=None)
        qf["escalation"] = {"is_escalation_confirmation": False, "company_pick": "mocha"}
        output = ox.post_process(
            {"output": qf},
            {},
            {
                "latest_user_message": "mocha",
                "previous_conversation_state": self._company_state(),
            },
        )["output"]
        assert output["escalation"].get("is_escalation_confirmation") is not True
