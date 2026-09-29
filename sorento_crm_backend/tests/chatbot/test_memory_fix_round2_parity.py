"""`scripts/chatbot_parser_parity.py --memory-cases` grading (reviewer pass on PR #1304
at d89110c0, S17): the grader reads `profile_statements`, the list the parser emits and
the fixture carries, and the stated-fact cases are out of the ablation count, since a
statement is read off the current message and stays right with memory ablated.

Pure: loads the script as a module, calls no provider.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "chatbot_parser_parity.py"
CASES = BACKEND_ROOT / "tests" / "chatbot" / "fixtures" / "parser_memory_cases.json"


def _parity():
    spec = importlib.util.spec_from_file_location("zzt_parity_round2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stated_role_case() -> dict:
    return next(c for c in json.loads(CASES.read_text(encoding="utf-8")) if c["id"] == "stated-role")


def test_a_verdict_missing_the_stated_fact_is_wrong() -> None:
    case = _stated_role_case()
    verdict = {"message_type": case["expected"].get("message_type"), "entities": [], "profile_statements": []}
    correct, reasons = _parity().grade_verdict(verdict, case["expected"])
    assert not correct and any("profile_statements" in r for r in reasons), reasons


def test_a_verdict_carrying_the_stated_fact_is_right() -> None:
    case = _stated_role_case()
    expected = case["expected"]
    verdict = {
        "message_type": expected.get("message_type"),
        "domain_hint": expected.get("domain_hint"),
        "entities": [],
        "profile_statements": [{"key": "role", "value": "purchaser"}],
    }
    correct, reasons = _parity().grade_verdict(verdict, expected)
    assert correct, reasons


def test_stated_cases_are_out_of_the_ablation_count() -> None:
    parity = _parity()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    counted = [c["id"] for c in cases if parity.counts_for_ablation(c)]
    assert not any(case_id.startswith("stated-") for case_id in counted), counted
    assert len(counted) == len([c for c in cases if c.get("needs_memory")]) - 6, counted
