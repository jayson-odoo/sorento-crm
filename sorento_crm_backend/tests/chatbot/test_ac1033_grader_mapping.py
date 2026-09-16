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
            "access_levels": ["dealer", "office"],
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
        # `dialogue/focus.from_session` reads legacy `access_levels` for BOTH `focus.tier`
        # (the constraint on the asker) and the five-key `access_levels` itself - the one
        # legacy field doing double duty, since a capture never told the two apart.
        assert mapped["focus"]["tier"]["value"] == ["dealer", "office"]
        assert mapped["access_levels"] == ["dealer", "office"]
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

    def test_selection_context_tier_offer_maps_to_tier_pick(self) -> None:
        expected = {
            "message_type": "clarification",
            "selection_context": "tier_offer",
            "tier_menu": ["dealer", "office"],
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"]["kind"] == "tier_pick"
        assert mapped["open_question"]["options"] == []
        assert mapped["open_question"]["expects"] == "yes_no"

    def test_selection_context_member_offer_maps_to_member_offer(self) -> None:
        expected = {
            "message_type": "clarification",
            "selection_context": "member_offer",
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"]["kind"] == "member_offer"

    def test_disambiguation_with_a_customer_roster_maps_to_customer_pick(self) -> None:
        roster = [
            {"idx": 1, "label": "Acme Sdn Bhd", "entity_type": "customer"},
            {"idx": 2, "label": "Beta Trading", "entity_type": "customer"},
        ]
        expected = {
            "message_type": "clarification",
            "selection_context": "disambiguation",
            "last_result_set": roster,
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"]["kind"] == "customer_pick"
        assert mapped["open_question"]["options"] == roster

    def test_pending_team_clarify_maps_to_team_pick(self) -> None:
        expected = {
            "message_type": "casual",
            "pending": {"kind": "team_clarify", "team": "sales"},
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"]["kind"] == "team_pick"
        assert mapped["open_question"]["payload"] == {"team": "sales"}

    def test_pending_company_clarify_maps_to_company_pick(self) -> None:
        expected = {
            "message_type": "casual",
            "pending": {"kind": "company_clarify"},
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"]["kind"] == "company_pick"

    def test_a_last_result_set_with_no_selection_context_is_the_answers_own_rows_not_a_roster(
        self,
    ) -> None:
        # A plain stock/order list rides `last_result_set` too - with no `selection_context`
        # and no `pending`, that is the answer's own rows, never an open picker.
        expected = {
            "message_type": "business_query",
            "last_result_set": [{"idx": 1, "label": "SRTWC8517", "code": "SRTWC8517"}],
        }

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert reason is None
        assert mapped["open_question"] is None

    def test_an_unrecognised_selection_context_is_named_not_silently_dropped(self) -> None:
        expected = {"selection_context": "from_a_future_build"}

        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected)

        assert mapped is None
        assert reason is not None
        assert "from_a_future_build" in reason


class TestProjectVariablesForComparison:
    """AC-1033 (revised 13 Sep 2026): `worlds_mod.project_variables_for_comparison`
    grades VALUES, applied identically to both the mapped expectation and the real
    `session_vars` before the world grader compares them."""

    def test_focus_slot_metadata_is_dropped_down_to_value(self) -> None:
        variables = {
            "focus": {
                "domains": {"value": ["order"], "set_at_turn": 4, "set_at": None, "source": "reuse"},
            },
            "open_question": None,
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["focus"]["domains"] == ["order"]

    def test_entity_slots_project_to_a_code_set_not_the_entity_dicts(self) -> None:
        variables = {
            "focus": {
                "products": {
                    "value": [
                        {
                            "raw": "srtwc286",
                            "hint": "product",
                            "canonical_code": "SRTWC286",
                            "current_message": True,
                            "confident": True,
                        },
                        {"raw": "srtws8091", "hint": "product", "canonical_code": None},
                    ],
                    "set_at_turn": 1,
                    "set_at": None,
                    "source": "current_message",
                },
                "customer": {
                    "value": {"raw": "hanlim", "hint": "customer", "canonical_code": None},
                    "set_at_turn": 1,
                    "set_at": None,
                    "source": "current_message",
                },
            },
            "open_question": None,
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["focus"]["products"] == {"SRTWC286", "SRTWS8091"}
        # `customer` is a single entity dict, not a list - still projects to its own code.
        assert projected["focus"]["customer"] == {"HANLIM"}

    def test_brands_projects_to_a_set_tier_keeps_its_value(self) -> None:
        variables = {
            "focus": {
                "brands": {"value": ["cabana", "cabana"], "set_at_turn": 1, "set_at": None, "source": "reuse"},
                "tier": {"value": ["dealer", "office"], "set_at_turn": 1, "set_at": None, "source": "reuse"},
            },
            "open_question": None,
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["focus"]["brands"] == {"cabana"}
        assert projected["focus"]["tier"] == ["dealer", "office"]

    def test_date_window_projects_to_exactly_start_end_mode(self) -> None:
        variables = {
            "focus": {
                "date_window": {
                    "value": {"start": "2026-08-01", "end": "2026-08-31", "mode": "range", "extra": "junk"},
                    "set_at_turn": 1,
                    "set_at": None,
                    "source": "current_message",
                },
            },
            "open_question": None,
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["focus"]["date_window"] == {
            "start": "2026-08-01",
            "end": "2026-08-31",
            "mode": "range",
        }

    def test_expects_is_re_derived_from_kind_spec_not_compared_as_stored(self) -> None:
        """A `member_offer` grades `yes_no` whether or not a roster rides beside it -
        `expects` is recomputed from `KIND_SPEC`, never read off the stored value."""
        with_rows = {
            "focus": {},
            "open_question": {
                "kind": "member_offer",
                "expects": "pick",  # stored wrong on purpose - must not survive
                "options": [{"code": None, "label": "Alpha Corp", "team": "ignored"}],
                "asked_at_turn": 3,
                "asked_at": None,
                "payload": {"team": "customer_service", "domain": None},
            },
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }
        without_rows = {
            "focus": {},
            "open_question": {
                "kind": "member_offer",
                "expects": "yes_no",
                "options": [],
                "asked_at_turn": 1,
                "asked_at": None,
                "payload": {},
            },
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected_with = worlds_mod.project_variables_for_comparison(with_rows)
        projected_without = worlds_mod.project_variables_for_comparison(without_rows)

        assert projected_with["open_question"]["expects"] == "yes_no"
        assert projected_without["open_question"]["expects"] == "yes_no"

    def test_options_project_to_code_and_label_only(self) -> None:
        variables = {
            "focus": {},
            "open_question": {
                "kind": "team_pick",
                "expects": "pick",
                "options": [
                    {
                        "idx": 1,
                        "code": None,
                        "label": "Warehouse",
                        "team": "warehouse",
                        "domain": "incoming",
                        "uuid": None,
                    },
                    {
                        "idx": 2,
                        "code": None,
                        "label": "Customer Service",
                        "team": "customer_service",
                        "domain": None,
                    },
                ],
                "asked_at_turn": 2,
                "asked_at": None,
                "payload": {"team": None, "domain": "incoming"},
            },
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["open_question"]["options"] == [
            {"code": None, "label": "Warehouse"},
            {"code": None, "label": "Customer Service"},
        ]

    def test_payload_keep_projects_to_a_code_set_payload_otherwise_dropped(self) -> None:
        variables = {
            "focus": {},
            "open_question": {
                "kind": "product_pick",
                "expects": "pick",
                "options": [{"idx": 1, "code": "SRTKS8091-B", "label": "SRTKS8091-B"}],
                "asked_at_turn": 5,
                "asked_at": None,
                "payload": {
                    "keep": [
                        {"raw": "srtks6091", "hint": "product", "canonical_code": "SRTKS6091"}
                    ],
                    "team": "should not survive",
                    "domain": "should not survive",
                },
            },
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["open_question"]["keep"] == {"SRTKS6091"}
        assert "team" not in projected["open_question"]
        assert "domain" not in projected["open_question"]
        assert "payload" not in projected["open_question"]
        assert "asked_at_turn" not in projected["open_question"]
        assert "asked_at" not in projected["open_question"]

    def test_no_open_question_projects_to_none(self) -> None:
        variables = {
            "focus": {},
            "open_question": None,
            "ideation": {"draft_id": "d1"},
            "access_levels": ["dealer"],
            "contains_flyer": True,
        }

        projected = worlds_mod.project_variables_for_comparison(variables)

        assert projected["open_question"] is None
        assert projected["ideation"] == {"draft_id": "d1"}
        assert projected["access_levels"] == ["dealer"]
        assert projected["contains_flyer"] is True

    def test_the_mapped_expectation_and_a_real_session_project_to_the_same_shape(self) -> None:
        """End to end: a legacy capture, mapped then projected, equals a real turn's
        session_vars, projected, when the underlying fact is the same - the whole point
        of the revision."""
        expected_legacy = {
            "message_type": "business_query",
            "domain_hint": "inventory",
            "entities": [
                {"raw": "srtwc8517", "hint": "product", "canonical_code": "SRTWC8517", "current_message": True}
            ],
        }
        mapped, reason = worlds_mod.map_expected_variables_to_five_keys(expected_legacy)
        assert reason is None

        real_session_vars = {
            "focus": {
                "domains": {"value": ["inventory"], "set_at_turn": 7, "set_at": None, "source": "current_message"},
                "products": {
                    "value": [
                        {
                            "raw": "SRTWC8517",
                            "hint": "product",
                            "canonical_code": "SRTWC8517",
                            "current_message": True,
                            "confident": True,
                        }
                    ],
                    "set_at_turn": 7,
                    "set_at": None,
                    "source": "current_message",
                },
            },
            "open_question": None,
            "ideation": None,
            "access_levels": [],
            "contains_flyer": False,
        }

        assert worlds_mod.project_variables_for_comparison(
            mapped
        ) == worlds_mod.project_variables_for_comparison(real_session_vars)
