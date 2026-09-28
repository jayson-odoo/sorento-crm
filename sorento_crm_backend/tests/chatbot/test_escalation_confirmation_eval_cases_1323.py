"""Issue #1323: the parser eval cases for the semantic escalation confirmation.

`console_cases/2026-09-28-escalation-confirmation.yaml` grades the REAL parser by hand
(`live_only`), so pytest never calls the LLM. What it pins here is that the file says
what the issue asks for, and that `scripts/chatbot_console_check.py::_grade_parser`
grades it: the recorded verdict of turn 9d9c417d fails the photo case, a verdict that
keeps the offer open and emits the ten codes passes it.
"""
from __future__ import annotations

import importlib.util
import pathlib
from typing import Any

import yaml

from tests.chatbot.test_escalation_confirmation_semantic_1323 import OFFER_WIRE, PHOTO_CODES

FIXTURE = (
    pathlib.Path(__file__).resolve().parent
    / "console_cases"
    / "2026-09-28-escalation-confirmation.yaml"
)
GRADER_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "chatbot_console_check.py"


def _cases() -> list[dict[str, Any]]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["cases"]


def _grader():
    spec = importlib.util.spec_from_file_location("_console_check_1323", GRADER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_text() -> dict[str, dict[str, Any]]:
    return {case["text"].strip(): case for case in _cases()}


def test_every_case_is_live_only_over_the_open_warehouse_offer() -> None:
    for case in _cases():
        assert case.get("live_only") is True, case["name"]
        state = case["previous_conversation_state"]
        assert state["open_question"] == OFFER_WIRE, case["name"]


def test_the_photo_case_expects_no_confirmation_and_the_ten_codes() -> None:
    case = _by_text()["Check stocks level\n" + "\n".join(PHOTO_CODES)]
    parser = case["expect"]["parser"]
    assert parser["escalation"] == {"is_escalation_confirmation": False}
    assert [e["canonical_code"] for e in parser["entities"]] == PHOTO_CODES
    assert all(e["hint"] == "product" and e["current_message"] is True for e in parser["entities"])


def test_the_three_agreements_expect_a_confirmation() -> None:
    cases = _by_text()
    for text in ("yes", "ok escalate", "boleh, escalate"):
        assert cases[text]["expect"]["parser"] == {
            "escalation": {"is_escalation_confirmation": True}
        }, text


def _emitted(confirmation: bool, codes: list[str]) -> dict[str, Any]:
    return {
        "is_affirmative": True,
        "escalation": {"is_escalation_confirmation": confirmation, "company_pick": None},
        "entities": [
            {
                "raw": code,
                "hint": "product",
                "canonical_code": code,
                "current_message": True,
                "confident": True,
            }
            for code in codes
        ],
    }


def test_the_grader_passes_the_right_reading_and_fails_the_recorded_one() -> None:
    grade = _grader()._grade_parser
    wanted = _by_text()["Check stocks level\n" + "\n".join(PHOTO_CODES)]["expect"]["parser"]
    assert grade(wanted, _emitted(False, PHOTO_CODES)) == []
    # The recorded turn itself carried `false` and the codes, and was handed over
    # anyway: that was the engine's bug. A parser that said `true` fails the case.
    assert grade(wanted, _emitted(True, PHOTO_CODES))
    # A missing code is a failure too: lists stay whole.
    assert grade(wanted, _emitted(False, PHOTO_CODES[:-1]))


def test_the_grader_still_compares_scalars_and_lists_by_equality() -> None:
    grade = _grader()._grade_parser
    assert grade({"document": ["DO"]}, {"document": ["SO", "DO"]})
    assert grade({"status": "outstanding"}, {"status": "delivered"})
    assert grade({"document": ["DO"]}, {"document": ["DO"]}) == []
