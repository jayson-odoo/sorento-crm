"""AC-1033: `worlds.py::map_expected_variables_to_five_keys`, unit-tested directly.

Three literal dicts, one per shape the corpus actually carries: a picker (a roster with
no `pending` marker), an escalate offer (`pending.kind == escalation_offer`) and a plain
answer (neither). Pure function, no DB, no engine - the integration half (wiring this into
`test_worlds.py`'s grading pipeline, applied before `body_difference`) is covered by the
world-replay suite itself, which goes red against it until the coder's S3 persists the
five keys.
"""
from __future__ import annotations

from tests.chatbot import worlds as worlds_mod


class TestMapExpectedVariablesToFiveKeys:
    def test_a_picker_with_no_pending_marker_maps_to_a_product_pick(self) -> None:
        roster = [
            {"idx": 1, "label": "SRTWC8517", "code": "SRTWC8517"},
            {"idx": 2, "label": "SRTKS6091", "code": "SRTKS6091"},
        ]
        expected = {
            "message_type": "clarification",
            "selection_context": "disambiguation",
            "last_result_set": roster,
            "domain_hint": "inventory",
            "entities": [{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            "access_levels": ["dealer"],
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"] == {
            "kind": "product_pick",
            "options": roster,
            "expects": "pick",
            "asked_at_turn": 0,
            "asked_at": None,
            "payload": {},
        }
        assert mapped["focus"]["domains"]["value"] == ["inventory"]
        assert mapped["focus"]["products"]["value"] == expected["entities"]
        assert mapped["access_levels"] == ["dealer"]
        assert mapped["contains_flyer"] is False

    def test_an_escalate_offer_maps_pending_to_team_pick(self) -> None:
        expected = {
            "message_type": "casual",
            "pending": {"kind": "escalation_offer", "team": "warehouse", "domain": "inventory"},
            "domain_hint": "order",
            "response": "Would you like me to escalate to warehouse team?",
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"] == {
            "kind": "team_pick",
            "options": [],
            "expects": "yes_no",
            "asked_at_turn": 0,
            "asked_at": None,
            "payload": {"team": "warehouse"},
        }
        assert mapped["focus"]["domains"]["value"] == ["order"]
        # `response` is dropped: it is not one of the five keys and never was part of
        # `focus` / `open_question`.
        assert "response" not in mapped

    def test_a_plain_answer_with_no_offer_has_no_open_question(self) -> None:
        expected = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "entities": [{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            "routing": {"suggested_team": "customer_service", "suggested_agent": None},
            "query_brands": ["cabana"],
            "tier_menu": ["dealer", "office"],
            "date_filter_start": "2026-08-01",
            "date_filter_end": "2026-08-31",
            "date_mode": "range",
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"] is None
        assert mapped["focus"]["domains"]["value"] == ["inventory"]
        assert mapped["focus"]["products"]["value"] == expected["entities"]
        assert mapped["focus"]["brands"]["value"] == ["cabana"]
        assert mapped["focus"]["tier"]["value"] == ["dealer", "office"]
        assert mapped["focus"]["date_window"]["value"] == {
            "start": "2026-08-01",
            "end": "2026-08-31",
            "mode": "range",
        }
        # `intent_hint` and `routing` are legacy keys with no focus / open_question home.
        assert "intent_hint" not in mapped
        assert "routing" not in mapped

    def test_an_unrecognised_pending_kind_is_named_not_silently_dropped(self) -> None:
        expected = {"pending": {"kind": "from_a_future_build", "team": "warehouse"}}

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert mapped is None
        assert reason is not None
        assert "from_a_future_build" in reason
