"""Migration `517_chatbot_session_5key`: every stored session becomes the five keys.

The conversion is a PURE function inside the migration, so it is driven here on literal
legacy blobs rather than through a database - which is what lets the three shapes that
actually matter be stated as data: a contact looking at a picker, a contact looking at an
escalate offer, and a contact whose last turn was a plain answer. The fourth case is the one
that must NOT be touched: a session already in the new shape.

Loaded by path (`importlib`), the same way `tests/chatbot/test_parser_v3.py` reads its
migration: a revision id is not an importable module name.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "517_chatbot_session_five_keys.py"
)

FIVE_KEYS = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("m517", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _legacy(**overrides) -> dict:
    base = {
        "domain_hint": "inventory",
        "entities": [{"raw": "SRTWC8517", "hint": "product", "canonical_code": "SRTWC8517"}],
        "access_levels": ["dealer"],
        "contains_flyer": False,
        "ideation": None,
    }
    base.update(overrides)
    return {"variables": base}


class TestTheThreeShapesThatMatter:
    def test_a_contact_looking_at_a_picker_keeps_the_rows_they_were_shown(self, migration):
        converted = migration.convert(
            _legacy(
                selection_context="disambiguation",
                last_result_set=[
                    {"label": "SRTWC8517-A", "code": "SRTWC8517-A"},
                    {"label": "SRTWC8517-B", "code": "SRTWC8517-B"},
                ],
                requested_attributes=["quantity"],
            )
        )
        variables = converted["variables"]
        assert set(variables) == FIVE_KEYS

        question = variables["open_question"]
        assert question["kind"] == "product_pick"
        assert question["expects"] == "pick"
        assert [row["idx"] for row in question["options"]] == [1, 2]
        assert [row["code"] for row in question["options"]] == ["SRTWC8517-A", "SRTWC8517-B"]

        focus = variables["focus"]
        assert focus["domains"]["value"] == ["inventory"]
        assert [e["raw"] for e in focus["products"]["value"]] == ["SRTWC8517"]
        assert focus["attributes"]["value"] == ["quantity"]
        assert set(focus["domains"]) == {"value", "set_at_turn", "set_at", "source"}

    def test_a_contact_looking_at_an_escalate_offer_gets_the_one_team_yes_no(self, migration):
        converted = migration.convert(
            _legacy(
                domain_hint="order",
                entities=[],
                pending={"kind": "escalation_offer", "team": "customer_service"},
            )
        )
        question = converted["variables"]["open_question"]
        assert question["kind"] == "team_pick"
        assert question["expects"] == "yes_no"
        assert question["options"] == [
            {"idx": 1, "team": "customer_service", "label": "customer_service"}
        ]
        assert question["payload"]["team"] == "customer_service"

    def test_a_plain_answer_carries_its_scope_and_leaves_no_question_open(self, migration):
        converted = migration.convert(
            _legacy(
                domain_hint="promotion",
                query_brands=["sorento"],
                date_filter_start="2026-09-01",
                date_filter_end="2026-09-30",
                date_mode="overlap",
            )
        )
        variables = converted["variables"]
        assert variables["open_question"] is None
        focus = variables["focus"]
        assert focus["brands"]["value"] == ["sorento"]
        assert focus["date_window"]["value"] == {
            "start": "2026-09-01",
            "end": "2026-09-30",
            "mode": "overlap",
        }


class TestItNeverRewritesASessionTwice:
    def test_an_already_converted_session_is_left_alone(self, migration):
        already = {
            "variables": {
                "focus": {"products": {"value": [], "set_at_turn": 3, "set_at": None, "source": "reuse"}},
                "open_question": None,
                "ideation": None,
                "access_levels": ["dealer"],
                "contains_flyer": False,
            }
        }
        assert migration.convert(already) is None

    def test_a_flat_blob_stays_flat(self, migration):
        """A session written through `PUT /external/conversation-variables` has no
        `variables` wrapper, and the reader after this migration reads whichever it finds."""
        converted = migration.convert({"domain_hint": "inventory", "entities": [], "access_levels": []})
        assert set(converted) == FIVE_KEYS

    def test_a_blob_that_is_not_an_object_is_left_alone(self, migration):
        assert migration.convert(None) is None
        assert migration.convert("nonsense") is None
