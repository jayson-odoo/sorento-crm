"""AC-1003, AC-1004: `dialogue/clearing.py`, the ONLY three ways a focus slot dies.

D9 (owner, 12 Sep 2026): no counter, no TTL, anywhere. A focus slot is cleared only by
(a) a current-message entity of the same axis replacing it, (b) `topic_reset`, or (c) the
Respond.io "conversation closed" event. `clearing.apply(session, parse, conversation_closed)`
is the one function that applies all three and returns `(session, trace_lines)`, each trace
line `{slot, reason}`.

RED: `app.services.chatbot.dialogue.clearing` does not exist on this branch yet -
`dialogue/decay.py` still owns turn-count TTL clearing (`is_alive`, `age_turns`), which this
module replaces. The import is local to each test so a missing module reads as one clean
`ModuleNotFoundError` per test, not a whole-file collection error masking which case failed.
"""
from __future__ import annotations

import re
from pathlib import Path

CHATBOT_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"


def _slot(value, *, turn_no=1, source="current_message"):
    return {"value": value, "set_at_turn": turn_no, "set_at": None, "source": source}


def _full_focus():
    return {
        "domains": _slot(["inventory"]),
        "products": _slot([{"code": "ZZT-OLD", "hint": "product"}]),
        "customer": _slot({"code": "ZZT-CUST-1"}),
        "transporter": _slot(None),
        "warehouse": _slot(None),
        "date_window": _slot(None),
        "attributes": _slot(None),
        "tier": _slot("gold"),
        "brands": _slot(["ZZT-BRAND"]),
    }


def _casual_parse(**overrides):
    base = {
        "message_type": "casual",
        "asks": [],
        "answers_open_question": {"resolved": False, "picks": [], "yes_no": None, "free_text": None},
        "anaphora": False,
        "topic_reset": False,
    }
    base.update(overrides)
    return base


class TestTheThreeClearingCauses:
    def test_same_axis_entity_replaces(self):
        """(a): a current-message product entity replaces the alive `products` slot,
        never appended alongside it."""
        from app.services.chatbot.dialogue import clearing

        session = {"focus": _full_focus(), "open_question": None}
        parse = _casual_parse(
            message_type="business_query",
            asks=[
                {
                    "domain": "inventory",
                    "entities": [
                        {
                            "raw": "ZZT-NEW",
                            "hint": "product",
                            "canonical_code": "ZZT-NEW",
                            "current_message": True,
                            "confident": True,
                        }
                    ],
                }
            ],
        )
        new_session, trace_lines = clearing.apply(session, parse, conversation_closed=False)

        products_value = new_session["focus"]["products"]["value"]
        assert products_value != [{"code": "ZZT-OLD", "hint": "product"}], (
            "the old product must not survive a same-axis replace"
        )
        assert all(row.get("code") != "ZZT-OLD" for row in (products_value or [])), (
            "REPLACE, never append: the old code must not still be present"
        )
        assert isinstance(trace_lines, list)

    def test_topic_reset_clears_all_but_tier_and_brands(self):
        """(b): `topic_reset` clears every axis except `tier` and `brands` (AC-1008's
        rule, applied here as one of clearing's three causes)."""
        from app.services.chatbot.dialogue import clearing

        session = {"focus": _full_focus(), "open_question": None}
        parse = _casual_parse(message_type="business_query", topic_reset=True)

        new_session, trace_lines = clearing.apply(session, parse, conversation_closed=False)
        focus = new_session["focus"]

        assert focus.get("domains") in (None, {}), focus.get("domains")
        assert focus.get("products") in (None, {}), focus.get("products")
        assert focus.get("customer") in (None, {}), focus.get("customer")
        assert focus.get("tier", {}).get("value") == "gold", (
            "tier must survive a topic reset"
        )
        assert focus.get("brands", {}).get("value") == ["ZZT-BRAND"], (
            "brands must survive a topic reset"
        )
        assert len(trace_lines) > 0
        for line in trace_lines:
            assert set(line) >= {"slot", "reason"}

    # `test_conversation_closed_marker_clears_everything_and_traces` DELETED (coordinator,
    # review fix round): `clearing.apply`'s `conversation_closed` arm is retired by the
    # coder - the SLA path's own eager clear
    # (`ConversationSLATrackingService._clear_chatbot_dialogue_state_best_effort`, called
    # directly from ticket resolve, under the last-open-sibling gate) is the design, and
    # it is what the AC-1006 world
    # (`test_focus_worlds.py`, the SLA-close turn) already covers end to end - a second,
    # pure-function test of a marker `clearing.apply` no longer reads would just pin the
    # deleted arm back in place.

    def test_no_ttl_anywhere(self):
        """No counter, no TTL, anywhere: not in the dialogue module, not on
        `system_settings`. `dialogue/decay.py`'s `ttl_turns` / `age_turns` machinery is
        retired along with it."""
        clearing_path = CHATBOT_DIR / "dialogue" / "clearing.py"
        assert clearing_path.exists(), f"{clearing_path} does not exist yet"
        clearing_src = clearing_path.read_text()
        assert not re.search(r"ttl", clearing_src, re.IGNORECASE), (
            "dialogue/clearing.py must contain no 'ttl' identifier"
        )

        contracts_src = (CHATBOT_DIR / "contracts.py").read_text()
        assert "ttl_turns" not in contracts_src, (
            "contracts.py must declare no ttl_turns field (FocusSlot or OpenQuestion)"
        )

        from app.models.user import SystemSetting

        assert not hasattr(SystemSetting, "chatbot_focus_ttl_turns"), (
            "system_settings must not carry chatbot_focus_ttl_turns (D9: no settings field)"
        )


class TestFiveCasualMessagesLeaveStateUntouched:
    def test_five_casual_messages_leave_state_untouched(self):
        """AC-1004: after a business turn, five casual messages in a row leave every
        focus slot and the open question exactly as they were - a casual message
        matches none of the three clearing causes."""
        from app.services.chatbot.dialogue import clearing

        original_focus = _full_focus()
        original_open_question = {
            "kind": "product_pick",
            "options": [{"idx": 1, "label": "ZZT product", "code": "ZZT-1", "domain": "inventory"}],
            "expects": "pick",
            "asked_at_turn": 1,
            "asked_at": None,
            "payload": {},
        }
        session = {"focus": original_focus, "open_question": original_open_question}

        for _ in range(5):
            session, trace_lines = clearing.apply(
                session, _casual_parse(), conversation_closed=False
            )
            assert trace_lines == [], (
                "a casual message must not trigger any clearing cause"
            )

        assert session["focus"] == original_focus
        assert session["open_question"] == original_open_question
