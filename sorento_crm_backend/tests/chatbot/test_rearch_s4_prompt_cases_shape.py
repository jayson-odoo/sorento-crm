"""S4 - the live rearch-prompt console cases (AC-1551, PLAN-chatbot-turn-rearch.md).

Two things under test, neither of which ever calls the parser LLM (these cases run by
hand, paced, per AC-1551's own evidence line - never in CI):

1. The YAML file's SHAPE: every case (including each sub-turn of a multi-turn case)
   carries `text`, `expect.parser`, and the top-level case carries `live_only: true`.
2. `scripts/chatbot_console_check.py`'s grader has a branch for the `expect.parser`
   key - measured today (module docstring of the yaml file) it does not:
   `grep -n "expect.get(.parser.)" scripts/chatbot_console_check.py` finds nothing.
   RED until the coder adds the branch.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

FIXTURE = (
    pathlib.Path(__file__).resolve().parent
    / "console_cases"
    / "2026-09-16-rearch-prompt.yaml"
)
GRADER_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "chatbot_console_check.py"


def _load() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _all_turns(case: dict) -> list[dict]:
    """A single-turn case IS its own one turn; a multi-turn case's `turns` list."""
    if "turns" in case:
        return case["turns"]
    return [case]


class TestYamlShape:
    def test_file_parses_and_has_seven_cases(self) -> None:
        doc = _load()
        assert "contact" in doc
        assert len(doc["cases"]) == 7, [c.get("name") for c in doc["cases"]]

    def test_every_case_carries_live_only_true(self) -> None:
        doc = _load()
        for case in doc["cases"]:
            assert case.get("live_only") is True, (
                f"case {case.get('name')!r} must carry live_only: true"
            )

    def test_every_turn_that_expects_something_carries_text_and_expect_parser(self) -> None:
        doc = _load()
        for case in doc["cases"]:
            turns = _all_turns(case)
            expecting_turns = [t for t in turns if "expect" in t]
            assert expecting_turns, f"case {case.get('name')!r} has no turn with an expect block"
            for turn in expecting_turns:
                assert turn.get("text"), f"case {case.get('name')!r}: a turn with expect must carry text"
                assert "parser" in (turn.get("expect") or {}), (
                    f"case {case.get('name')!r}: expect must carry a 'parser' key"
                )

    def test_document_status_reference_positions_scope_exclusive_asks_named(self) -> None:
        doc = _load()
        parser_expects = []
        for case in doc["cases"]:
            for turn in _all_turns(case):
                if "expect" in turn and "parser" in turn["expect"]:
                    parser_expects.append(turn["expect"]["parser"])

        seen_keys: set[str] = set()
        for p in parser_expects:
            seen_keys.update(p.keys())

        for expected_key in ("document", "status", "reference_positions", "scope_exclusive", "asks", "intent_hint"):
            assert expected_key in seen_keys, (
                f"no case's expect.parser exercises {expected_key!r}: {seen_keys!r}"
            )


class TestGraderHasAParserBranch:
    def test_grade_function_reads_expect_parser(self) -> None:
        source = GRADER_SCRIPT.read_text(encoding="utf-8")
        assert 'expect.get("parser")' in source or "expect['parser']" in source, (
            "scripts/chatbot_console_check.py::_grade has no branch reading "
            "expect.get('parser') yet - add it so a case's parser expectations are "
            "graded against the turn's trace parse stage"
        )
