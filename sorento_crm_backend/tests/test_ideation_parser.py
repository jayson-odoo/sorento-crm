"""Slice A — parser ``ideate`` intent + router branch (ideation pipeline).

Keys back to ``documentation/plans/ideation/ideation-ideate-intent-acceptance-criteria.md``:

- **AC-01 [T]** — ``ideate`` exists in the ``Intent`` literal, in
  ``PARSE_RESULT_JSON_SCHEMA`` enum + intent description, and the schema still
  validates under OpenAI strict mode.
- **AC-04 [T]** — a low-confidence ``ideate`` guess (< 0.4) demotes to the agent
  loop, never hijacking a CRM turn.
- **AC-05 [T]** — ``ideate`` at/above the floor routes to a DEDICATED decision
  (``kind="ideate"``) — it does not fall through to record_answer/capability.
- **AC-06 [T]** — the in-app WEB brain (``respond``) recognises ``ideate`` and
  returns a friendly redirect to ``/ideas`` WITHOUT calling create_idea and
  without raising.

AC-02 (paraphrase classification) and AC-03 (no-regression corpus) are
live-LLM evals — they exercise how a real model classifies literal sentences,
which cannot run deterministically in CI. They are DEFERRED to the opt-in
live-LLM harness (see the tester note); the deterministic tests below MUST be
green. This follows the repo's split of "routing tests (offline, deterministic)"
vs "classifier-quality eval (live LLM, opt-in)" — see
``test_ai_assistant_record_context_preroute.py`` + ``feedback_no_overfit_llm_nlp``.
"""
from __future__ import annotations

import typing

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.ai_assistant import AIAssistantAuthContext
from app.schemas.ai_semantic_parser import (
    PARSE_RESULT_JSON_SCHEMA,
    Intent,
    ParseEntities,
    ParseResult,
    ParseSignals,
)
from app.services.ai_assistant_service import (
    _LOW_CONFIDENCE_FLOOR,
    AIAssistantChatService,
)
from app.services.entity_resolver import ResolutionResult
from tests._pg_fixture import blank_session


def _parse(intent: str, *, confidence: float = 0.9) -> ParseResult:
    return ParseResult(
        standalone_query="q",
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        entities=ParseEntities(),
        signals=ParseSignals(),
    )


def _svc() -> AIAssistantChatService:
    # _route is a pure switch — touches neither DB nor collaborator.
    return AIAssistantChatService(db=None)  # type: ignore[arg-type]


# ===========================================================================
# AC-01 — schema exposes ``ideate`` and stays OpenAI strict-compliant
# ===========================================================================
def test_ideate_in_intent_literal():
    assert "ideate" in typing.get_args(Intent), "ideate must be a closed Intent value"


def test_ideate_in_json_schema_enum():
    enum = PARSE_RESULT_JSON_SCHEMA["properties"]["intent"]["enum"]
    assert "ideate" in enum, "ideate must be in the parser JSON-schema intent enum"


def test_ideate_in_intent_description():
    desc = PARSE_RESULT_JSON_SCHEMA["properties"]["intent"]["description"]
    assert "ideate" in desc.lower(), "the intent description must document ideate"


def _assert_strict(schema: dict, path: str = "root"):
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties must be False"
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert props == required, f"{path}: required {required} must equal properties {props}"
        for name, sub in schema.get("properties", {}).items():
            _assert_strict(sub, f"{path}.{name}")


def test_schema_still_openai_strict_after_ideate():
    _assert_strict(PARSE_RESULT_JSON_SCHEMA)


# ===========================================================================
# AC-04 / AC-05 — deterministic router branch
# ===========================================================================
def test_ideate_above_floor_gets_dedicated_decision():
    """AC-05: a confident ideate turn routes to the dedicated ideate branch,
    NOT record_answer / capability / bare agent."""
    decision = _svc()._route(_parse("ideate", confidence=0.9), record_available=False)
    assert decision.kind == "ideate"


def test_ideate_at_floor_is_dedicated():
    """AC-05 boundary: confidence exactly at the floor is NOT demoted (strict <)."""
    at_floor = _parse("ideate", confidence=_LOW_CONFIDENCE_FLOOR)
    assert _svc()._route(at_floor, record_available=False).kind == "ideate"


def test_low_confidence_ideate_demotes_to_agent():
    """AC-04: a shaky ideate guess must never hijack a CRM turn."""
    below = _parse("ideate", confidence=_LOW_CONFIDENCE_FLOOR - 0.01)
    assert _svc()._route(below, record_available=False).kind == "agent"


# ===========================================================================
# AC-06 — in-app WEB brain redirects ideate to /ideas (no create_idea)
# ===========================================================================
@pytest.fixture
def db_session() -> Session:
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a JSONB->TEXT compiler shim. The shim mattered:
    it turned the assistant's JSONB metadata columns into strings, so the
    ``metadata_json`` assertion below was reading a hand-rolled type rather
    than the one production uses.
    """
    with blank_session() as session:
        yield session


# The autouse ``_stub_rate_limit_clause`` fixture that lived here is gone. It
# rewrote ``text`` to ``literal(0)`` inside the chat service so sqlite would not
# choke on the per-minute rate-limit window, ``func.now() - text("interval '1
# minute'")``. That substitution meant the rate-limit query under test was never
# the one production runs. Postgres executes the real interval, so the stub is
# no longer needed -- and the real clause is now exercised.


@pytest.fixture
def seeded_user(db_session: Session) -> str:
    user = User(id="u-1", email="u1@test.com", name="User One", status="ACTIVE")
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture
def chat_service(db_session: Session, monkeypatch) -> AIAssistantChatService:
    svc = AIAssistantChatService(db_session)
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()

    svc.gov.build_auth_context = lambda user_id: AIAssistantAuthContext(  # type: ignore[assignment]
        user_id=user_id,
        role_ids=["r1"],
        permission_slugs=["system.ai_assistant_chat.use"],
        enabled_modules=[],
    )
    svc._rag_select_tools = lambda *, standalone_query, enabled_tools, top_k: ([], [])  # type: ignore[assignment]
    svc._generate_suggestions = lambda **_k: []  # type: ignore[assignment]

    import app.services.ai_assistant_service as svc_module

    # Through `monkeypatch`, NOT a bare rebind: an unrestored rebind of a module symbol leaks
    # into every test that runs later in the session. `**_k` because the stub stands in for a
    # function whose keyword arguments are free to grow.
    monkeypatch.setattr(
        svc_module,
        "resolve_references",
        lambda *_a, **_k: ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0),
    )
    return svc


class _Spy:
    def __init__(self, ret):
        self.called = False
        self._ret = ret

    def __call__(self, *_a, **_k):
        self.called = True
        return self._ret


_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_web_brain_ideate_redirects_to_ideas(
    seeded_user: str, chat_service: AIAssistantChatService
):
    """AC-06: the web assistant classifies ideate → friendly /ideas redirect,
    never the agent loop, never a create_idea call, no exception."""
    chat_service._parse_turn = lambda **_k: _parse("ideate", confidence=0.95)  # type: ignore[assignment]
    agent = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]

    _conv, msg = chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="I wish the app could remind me before a PO expires",
        page_snapshot=None,
    )

    assert agent.called is False, "an ideate web turn must NOT run the agent loop"
    assert "/ideas" in (msg.content or ""), "the reply must point the user to the Ideas board"
    assert "/ideas" in (msg.metadata_json or {}).get("links", []), "the /ideas link must be extracted"


def test_low_confidence_ideate_web_falls_through_to_agent(
    seeded_user: str, chat_service: AIAssistantChatService
):
    """AC-04 (web path): a low-confidence ideate must not hijack the web turn."""
    chat_service._parse_turn = lambda **_k: _parse("ideate", confidence=0.2)  # type: ignore[assignment]
    agent = _Spy(("real answer", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="what can I do to expedite this?",
        page_snapshot=None,
    )

    assert agent.called is True, "low-confidence ideate must fall through to the agent loop"
