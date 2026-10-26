"""CHAT-SLIM-INDEX S1, red tests of `ContextLayers.lookup_lines` (pure, no database). AC-1, AC-2 (context half).

The lines print right after `candidate_lines` in BOTH assemble paths (the off level and the others);
None (or empty) leaves today's output byte for byte.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.turn import context

LOOKUP = ["Category candidates (pick one only if the message means it):", "- Water Closet"]


def _layers(**extra) -> context.ContextLayers:
    return context.ContextLayers(
        level=extra.pop("level", "off"),
        profile_facts=[{"key": "segment", "value": "dealer"}],
        summaries=["Thu 25 Sep: stock asked."],
        earlier_messages=[{"created_at": "Thu 10:02", "text": "hello"}],
        previous_response="Here is the stock.",
        current_subject="domain inventory",
        pending_kind=None,
        pending_options=None,
        settings_profile_line=None,
        current_message="dealer only",
        reply_to=None,
        media_line=None,
        **extra,
    )


@pytest.mark.parametrize("level", ["off", "recent", "episodes", "full"])
def test_lookup_lines_print_right_after_the_candidate_lines(level):
    text, _ = context.assemble(_layers(level=level, candidate_lines=["CAND-HEADER", "- cand one"], lookup_lines=LOOKUP))
    lines = text.splitlines()
    at = lines.index("- cand one")
    assert lines[at + 1 : at + 3] == LOOKUP, lines


@pytest.mark.parametrize("level", ["off", "recent", "episodes", "full"])
def test_lookup_lines_without_candidate_lines_follow_the_current_message(level):
    text, _ = context.assemble(_layers(level=level, lookup_lines=LOOKUP))
    lines = text.splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("Current user message:"))
    assert lines[at + 1 : at + 3] == LOOKUP, lines


@pytest.mark.parametrize("level", ["off", "recent", "episodes", "full"])
@pytest.mark.parametrize("empty", [None, []])
def test_no_lookup_lines_leaves_the_output_byte_identical(level, empty):
    base = _layers(level=level, candidate_lines=["CAND-HEADER", "- cand one"], brands=[{"brand_name": "ZZ Brand", "brand_code": "ZZB"}])
    same = _layers(level=level, candidate_lines=["CAND-HEADER", "- cand one"], brands=[{"brand_name": "ZZ Brand", "brand_code": "ZZB"}], lookup_lines=empty)
    assert context.assemble(base)[0] == context.assemble(same)[0]


def test_lookup_lines_default_is_none():
    assert _layers().lookup_lines is None
