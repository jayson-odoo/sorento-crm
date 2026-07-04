"""Item 4a (PLAN-post-security-batch) — novice capability overview + the
assistant's deterministic "what can you do?" answer.

These are pure-function tests (no LLM, no DB):

  * ``build_novice_capability_overview`` enriches the live catalog and MUST NOT
    leak admin/internal tools, embedding skip-tools, tool slugs, UUIDs, raw
    machine category codes, methods, or API paths (UAC4.2).
  * ``AIAssistantChatService._build_capability_answer`` renders the overview to
    markdown with NO LLM round-trip (UAC4.1 — deterministic catalog part).

NOTE (M0 semantic-parser revamp): the keyword classifier ``_is_capability_question``
was DELETED — capability recognition is now the Semantic Parser's ``intent ==
"capability"`` (tested in ``test_ai_semantic_parser_route.py`` /
``test_ai_semantic_parser_schema.py``). Only the deterministic catalog BUILDER
is unchanged and still tested here.
"""
from __future__ import annotations

import json

from app.services.ai_assistant_service import AIAssistantChatService
from app.services.mcp_tool_capability_service import (
    _EMBEDDING_SKIP_TOOLS,
    build_novice_capability_overview,
)


def _svc() -> AIAssistantChatService:
    # The capability path touches neither the DB nor any LLM collaborator.
    return AIAssistantChatService(db=None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Enriched overview (UAC4.2)
# --------------------------------------------------------------------------
def test_overview_has_modules_with_friendly_names_and_examples():
    ov = build_novice_capability_overview()
    modules = ov["modules"]
    assert modules, "expected at least one capability module"
    names = {m["module"] for m in modules}
    # Friendly, human module names — not machine codes.
    assert "Products & catalogue" in names
    assert "Stock & inventory" in names
    for m in modules:
        assert m["description"].strip()
        assert m["example_questions"], f"{m['module']} has no example questions"


def test_overview_excludes_admin_internal_and_held_categories():
    ov = build_novice_capability_overview()
    blob = json.dumps(ov)
    # No machine category codes at all.
    assert "internal_admin" not in blob
    assert ".form_submission" not in blob
    assert "general_enquiries." not in blob
    assert "order_enquiries" not in blob
    assert "sla_management" not in blob
    # Held module must never surface.
    assert "commercial" not in blob.lower()


def test_overview_has_no_slugs_uuids_or_paths():
    ov = build_novice_capability_overview()
    blob = json.dumps(ov)
    # Tool slugs.
    assert "crm_" not in blob
    # API paths / methods.
    assert "/api/v1" not in blob
    assert "GET" not in blob and "POST" not in blob
    # No UUID-looking tokens.
    import re

    assert not re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        blob,
    )


def test_overview_skip_tools_are_not_referenced():
    ov = build_novice_capability_overview()
    blob = json.dumps(ov)
    for tool in _EMBEDDING_SKIP_TOOLS:
        assert tool not in blob


# --------------------------------------------------------------------------
# Deterministic answer (UAC4.1) — no LLM call
# --------------------------------------------------------------------------
def test_build_capability_answer_is_deterministic_and_grounded():
    svc = _svc()
    answer = svc._build_capability_answer()
    assert "Here's what I can help you with" in answer
    # Module names render as bold headings.
    assert "**Products & catalogue**" in answer
    assert "**Stock & inventory**" in answer
    # Example questions render as "Try:" bullets.
    assert "- Try:" in answer
    # Never leaks machine internals.
    assert "crm_" not in answer
    assert "internal_admin" not in answer
    assert "commercial" not in answer.lower()
