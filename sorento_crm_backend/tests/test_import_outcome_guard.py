"""Structural guard: an import job's counters may only come from the recorder.

The original bug was a counter that moved without a reason (`skipped += 1;
continue`). Local tallies still exist for legacy result fields, but what reaches
`import_jobs` must be the recorder's numbers - because those are, by
construction, the sum of individually attributed rows.

Covers UAC AC-A2 / AC-G1.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.tasks import import_tasks

SOURCE = Path(inspect.getfile(import_tasks)).read_text()
TREE = ast.parse(SOURCE)

#: Counter kwargs that must never be hand-computed at the complete_job boundary.
HAND_COUNTED = {"successful_rows", "failed_rows", "skipped_rows", "processed_rows"}


def _complete_job_calls() -> list[ast.Call]:
    calls = []
    for node in ast.walk(TREE):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name == "complete_job":
            calls.append(node)
    return calls


def test_there_are_complete_job_calls_to_check():
    """Guard against the guard silently passing because it found nothing."""
    assert len(_complete_job_calls()) >= 8, "expected one completion per importer"


@pytest.mark.parametrize("call", _complete_job_calls(), ids=lambda c: f"line{c.lineno}")
def test_completion_counts_come_from_the_recorder(call: ast.Call):
    """Every complete_job must spread `outcome.completion_counts(...)`."""
    hand_counted = {kw.arg for kw in call.keywords if kw.arg in HAND_COUNTED}
    assert not hand_counted, (
        f"complete_job at line {call.lineno} hand-computes {sorted(hand_counted)}. "
        "Counters must come from ImportOutcome so every counted row is attributed - "
        "pass **outcome.completion_counts(total_rows=...) instead."
    )

    spreads = [kw for kw in call.keywords if kw.arg is None]
    assert spreads, (
        f"complete_job at line {call.lineno} does not spread the recorder's counts; "
        "pass **outcome.completion_counts(total_rows=...)."
    )
    spread_src = {ast.unparse(kw.value) for kw in spreads}
    assert any("completion_counts" in src for src in spread_src), (
        f"complete_job at line {call.lineno} spreads {spread_src}, "
        "which is not outcome.completion_counts(...)."
    )


def test_dedup_skip_is_attributed():
    """The exact branch that lost 4,018 rows must name itself."""
    src = inspect.getsource(import_tasks.process_delivery_order_detail_import)
    dedup_block = src.split("existing_remaining[key] -= 1", 1)
    assert len(dedup_block) == 2, "dedup branch not found - did the import change shape?"
    following = dedup_block[1][:600]
    assert "outcome.skip(" in following and "DUPLICATE_LINE" in following, (
        "the duplicate-line branch must record a reason; a bare `skipped += 1` here "
        "is what made 4,018 rows vanish from a green job."
    )


def test_every_importer_builds_the_result_envelope():
    """`result=` at completion must be the recorder's envelope, not a hand dict."""
    for call in _complete_job_calls():
        result_kw = next((kw for kw in call.keywords if kw.arg == "result"), None)
        assert result_kw is not None, f"complete_job at line {call.lineno} has no result"
        src = ast.unparse(result_kw.value)
        assert "finalize(" in src or "outcome" in src, (
            f"complete_job at line {call.lineno} passes a hand-built result ({src[:60]}...); "
            "use outcome.finalize(...) so the breakdown is always present."
        )
