"""`tests/chatbot/fixtures/parser_memory_cases.json` shape guard (AC-MEM068, plan 8.2).

No network, no provider call, no LLM anywhere - the live grading of these 30 cases
against a real model is `scripts/chatbot_parser_parity.py --memory-cases`, run by the
orchestrator with an OpenAI key this VM does not have. What IS checked here, on every
PR, with no key at all:

* the fixture holds exactly 30 cases;
* every case's `user_block_with_memory` is byte-identical to what `turn/context.assemble`
  produces TODAY from the case's own structured inputs (`profile_facts`, `summaries`,
  `earlier_messages`, `previous_response`, `current_subject`, `current_message`) at
  level `full` - so an edit to `context.py` that silently changes the rendering is
  caught here, not discovered mid-evaluation-run by the orchestrator;
* every case assembles within the 1,800-token cap (contract section 6.2);
* the "ablated" rendering of every `needs_memory: true` case (the SAME inputs at level
  `off`, `turn/context.py`'s own legacy path) carries none of the three memory
  headers - the whole premise of "this case tests memory" is that removing memory
  changes what the parser sees.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot.turn import context as context_mod

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "parser_memory_cases.json"

#: The three headers `_render_l5` / `_render_l4` / `_render_l3` print - level `off`
#: renders none of them (`_assemble_off`'s own docstring: "level off carries none of
#: the new layers").
_MEMORY_HEADERS = ("About this contact:", "Recent conversations:", "Earlier in this conversation")


def _load_cases() -> list[dict[str, Any]]:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _layers(case: dict[str, Any], *, level: str) -> context_mod.ContextLayers:
    return context_mod.ContextLayers(
        level=level,
        profile_facts=case["profile_facts"],
        summaries=case["summaries"],
        earlier_messages=case["earlier_messages"],
        previous_response=case["previous_response"],
        current_subject=case["current_subject"],
        pending_kind=None,
        pending_options=None,
        settings_profile_line=None,
        current_message=case["current_message"],
        reply_to=None,
        media_line=None,
    )


def test_fixture_has_exactly_30_cases() -> None:
    cases = _load_cases()
    assert len(cases) == 30, f"expected 30 cases (AC-MEM068), got {len(cases)}"


def test_case_ids_are_unique() -> None:
    cases = _load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_stored_user_block_matches_a_fresh_assemble_call(case: dict[str, Any]) -> None:
    """The fixture stores the TEXT `context.assemble` produced when it was generated -
    if `context.py`'s rendering changes, this catches the drift instead of the
    orchestrator silently grading a stale block."""
    user_block, report = context_mod.assemble(_layers(case, level="full"))
    assert user_block == case["user_block_with_memory"], (
        f"{case['id']}: assemble() no longer matches the stored user block - "
        f"regenerate the fixture if this is an intentional context.py change.\n"
        f"--- stored ---\n{case['user_block_with_memory']}\n"
        f"--- fresh ---\n{user_block}"
    )
    assert report["total_est_tokens"] == case["assembled_est_tokens"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_every_case_assembles_within_the_budget_cap(case: dict[str, Any]) -> None:
    _user_block, report = context_mod.assemble(_layers(case, level="full"))
    assert report["total_est_tokens"] <= context_mod.TOTAL_CAP, (
        f"{case['id']}: {report['total_est_tokens']} tokens, over the "
        f"{context_mod.TOTAL_CAP}-token cap (contract 6.2)"
    )


@pytest.mark.parametrize(
    "case", [c for c in _load_cases() if c.get("needs_memory", True)], ids=lambda c: c["id"]
)
def test_needs_memory_cases_lose_the_memory_headers_when_ablated(case: dict[str, Any]) -> None:
    """The meta-test the PRINCIPLES kill test demands of any "this needs memory" claim
    (AC-MEM067's own rule, applied here to the parser-eval corpus): the level `off`
    rendering of the IDENTICAL inputs must carry none of the three memory headers, so
    the live evaluation's ablation run is actually stripping something."""
    ablated, _report = context_mod.assemble(_layers(case, level="off"))
    for header in _MEMORY_HEADERS:
        assert header not in ablated, (
            f"{case['id']} is marked needs_memory but its ablated (level=off) "
            f"rendering still carries {header!r} - it does not test memory:\n{ablated}"
        )


def test_every_case_declares_needs_memory() -> None:
    cases = _load_cases()
    missing = [c["id"] for c in cases if "needs_memory" not in c]
    assert not missing, f"cases missing needs_memory: {missing}"


def test_expected_shape_is_the_four_declared_keys_only() -> None:
    """`expected` is graded by the live runner against exactly these four verdict
    keys (plan 8.2) - an extra key here would silently never be graded."""
    allowed = {"entities", "message_type", "profile_statement", "domain_hint"}
    for case in _load_cases():
        extra = set(case["expected"]) - allowed
        assert not extra, f"{case['id']}: expected has undeclared keys {extra}"
