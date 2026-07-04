"""Deterministic router unit tests (M0 Semantic Parser revamp).

``AIAssistantChatService._route(parse, *, record_available)`` is a PURE switch on
the ``ParseResult`` params — no LLM, no DB. These tests construct the ParseResult
directly and assert the resulting ``_RouteDecision`` (``.kind`` / ``.is_how_to``
/ ``.skip_rag``). This is deterministic and does NOT overfit an LLM: we never
assert how a literal sentence classifies (that is the parser's job, exercised
offline via a stub) — only that a GIVEN ParseResult routes to the documented
branch (PLAN §12 router-precedence table). See feedback_no_overfit_llm_nlp.
"""
from __future__ import annotations

import pytest

from app.schemas.ai_semantic_parser import ParseEntities, ParseResult, ParseSignals
from app.services.ai_assistant_service import _LOW_CONFIDENCE_FLOOR, AIAssistantChatService


def _svc() -> AIAssistantChatService:
    # _route touches neither the DB nor any collaborator — pure function.
    return AIAssistantChatService(db=None)  # type: ignore[arg-type]


def _parse(
    intent: str,
    *,
    targets_open_record: bool = False,
    confidence: float = 0.9,
    is_write_intent: bool = False,
) -> ParseResult:
    return ParseResult(
        standalone_query="q",
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        entities=ParseEntities(),
        signals=ParseSignals(
            targets_open_record=targets_open_record,
            is_write_intent=is_write_intent,
        ),
    )


# (label, parse, record_available, expected_kind, expected_is_how_to, expected_skip_rag)
_CASES = [
    # --- capability: zero-LLM deterministic catalog, exempt from the floor -----
    ("capability", _parse("capability"), False, "capability", False, False),
    # --- smalltalk: agent loop with NO tools (skip RAG) -----------------------
    ("smalltalk", _parse("smalltalk"), False, "agent", False, True),
    # --- definition: agent loop WITH tools — a term question mislabelled from a
    #     real data lookup ("what is DO-123?") must still reach MCP read tools ---
    ("definition", _parse("definition"), False, "agent", False, False),
    # --- how_to: agent loop with deterministic guide pre-fetch ----------------
    ("how_to", _parse("how_to"), False, "agent", True, False),
    # --- record_question: only routes to record_answer when BOTH the parser
    #     flags targets_open_record AND a record is actually open --------------
    (
        "record_q open+available",
        _parse("record_question", targets_open_record=True),
        True,
        "record_answer",
        False,
        False,
    ),
    (
        "record_q open but no record",
        _parse("record_question", targets_open_record=True),
        False,
        "agent",
        False,
        False,
    ),
    (
        "record_q available but not targeting open",
        _parse("record_question", targets_open_record=False),
        True,
        "agent",
        False,
        False,
    ),
    # --- data_query / record_action / form_submit / unknown → agent + RAG -----
    ("data_query", _parse("data_query"), False, "agent", False, False),
    (
        "record_action",
        _parse("record_action", is_write_intent=True),
        True,
        "agent",
        False,
        False,
    ),
    (
        "form_submit",
        _parse("form_submit", is_write_intent=True),
        False,
        "agent",
        False,
        False,
    ),
    ("unknown", _parse("unknown"), False, "agent", False, False),
    # --- low-confidence DEMOTION: a shaky non-capability intent is treated as
    #     unknown → agent loop, NEVER the record_answer / capability shortcut ---
    (
        "low-conf record_q demoted (no record_answer)",
        _parse("record_question", targets_open_record=True, confidence=0.3),
        True,
        "agent",
        False,
        False,
    ),
    (
        "low-conf how_to demoted (no guide prefetch)",
        _parse("how_to", confidence=0.39),
        False,
        "agent",
        False,
        False,
    ),
    (
        "low-conf smalltalk demoted (unknown keeps RAG on)",
        _parse("smalltalk", confidence=0.1),
        False,
        "agent",
        False,
        False,
    ),
    # --- capability stays capability even below the floor (floor is exempt) ---
    (
        "low-conf capability still capability",
        _parse("capability", confidence=0.05),
        False,
        "capability",
        False,
        False,
    ),
]


@pytest.mark.parametrize(
    "label,parse,record_available,kind,is_how_to,skip_rag",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_route(label, parse, record_available, kind, is_how_to, skip_rag):
    decision = _svc()._route(parse, record_available=record_available)
    assert decision.kind == kind, f"{label}: kind"
    assert decision.is_how_to is is_how_to, f"{label}: is_how_to"
    assert decision.skip_rag is skip_rag, f"{label}: skip_rag"


def test_low_confidence_floor_boundary_is_exclusive():
    """confidence exactly at the floor is NOT demoted (strict < comparison)."""
    at_floor = _parse("record_question", targets_open_record=True, confidence=_LOW_CONFIDENCE_FLOOR)
    assert _svc()._route(at_floor, record_available=True).kind == "record_answer"

    below = _parse("record_question", targets_open_record=True, confidence=_LOW_CONFIDENCE_FLOOR - 0.01)
    assert _svc()._route(below, record_available=True).kind == "agent"
