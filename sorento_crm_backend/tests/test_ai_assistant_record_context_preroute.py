"""Pre-route regression guard for the bubble record-context feature.

Covers UAC §3 (pre-route discipline) + §4.7 (session-var isolation) for
``PLAN-bubble-record-context-and-guides``.

Two kinds of test, deliberately separated (see memory feedback_no_overfit_llm_nlp):

  * **Routing tests** (offline, deterministic) - stub the classifier verdict and
    the assembler so we test the FORK LOGIC only: record-class+entity bypasses
    the agent loop; everything else reaches it. This is the regression firewall
    and must run in CI.
  * **Classifier-quality eval** (live LLM, opt-in) - paraphrase robustness for
    ``intent_is_record_class`` itself. Because the classifier is a GENERAL
    semantic judgment (an LLM call), not a keyword whitelist, its quality can
    only be tested against a real model. Gated behind ``RUN_LLM_EVALS`` so CI
    stays offline/deterministic; run on demand against a real key.

Mirrors the stub wiring in ``test_ai_assistant_usage.py``.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.ai_assistant import (
    AIAssistantConfig,
    AIAssistantConversation,
    AIAssistantGovernanceEvent,
    AIAssistantMessage,
    AIAssistantUnansweredQuery,
    AIAssistantUsageLog,
    AIAssistantWishlistCluster,
)
from app.models.lookup import LookupBinding
from app.models.user import User
from app.schemas.ai_assistant import (
    AIAssistantAuthContext,
    PageEntityRef,
    PageSnapshotPayload,
)
from app.schemas.ai_semantic_parser import (
    ParseEntities,
    ParseResult,
    ParseSignals,
)
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.entity_resolver import ResolutionResult
from tests._pg_fixture import blank_session


def _parse(
    intent: str,
    *,
    targets_open_record: bool = False,
    confidence: float = 0.9,
    is_write_intent: bool = False,
) -> ParseResult:
    """Build a ParseResult driving a deterministic route. Routing tests assert
    on the ParseResult we construct (routing is a pure switch on it), NOT on how
    the LLM would classify a literal sentence - see feedback_no_overfit_llm_nlp.
    """
    return ParseResult(
        standalone_query="standalone",
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        entities=ParseEntities(),
        signals=ParseSignals(
            targets_open_record=targets_open_record,
            is_write_intent=is_write_intent,
        ),
    )


@pytest.fixture
def db_session() -> Session:
    with blank_session() as session:
        yield session


@pytest.fixture
def seeded_user(db_session: Session) -> str:
    user = User(id="u-1", email="u1@test.com", name="User One", status="ACTIVE")
    db_session.add(user)
    db_session.commit()
    return user.id


class _Spy:
    """Records whether it was invoked and with what kwargs."""

    def __init__(self, ret):
        self.called = False
        self.kwargs = None
        self._ret = ret

    def __call__(self, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return self._ret


_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@pytest.fixture
def chat_service(db_session: Session, monkeypatch) -> AIAssistantChatService:
    """Chat service with every external dependency stubbed OFFLINE.

    The Semantic Parser (``_parse_turn``), RBAC check, assembler and prose
    render are stubbed so routing tests are deterministic and make no network
    calls. Individual tests override ``_parse_turn`` to return a ``ParseResult``
    whose intent drives the deterministic router either way.
    """
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
    # Default parse → unknown (agent loop). Each test overrides for its route.
    svc._parse_turn = lambda **_k: _parse("unknown")  # type: ignore[assignment]
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

    # RBAC check inside the pre-route → allow by default (override per test).
    class _AllowPerm:
        def __init__(self, *_a, **_k):
            pass

        def check_user_has_permission(self, *_a, **_k):
            return True

    monkeypatch.setattr(svc_module, "UserPermissionService", _AllowPerm)

    # Assembler → return a synthetic complaint bundle, no DB/network.
    import app.services.record_context_service as rc_module

    class _FakeAssembler:
        def __init__(self, *_a, **_k):
            pass

        def assemble(self, entity_type, entity_id):
            return {
                "entity_type": entity_type,
                "id": entity_id,
                "display_ref": "CMP-2026-0142",
                "current_state": {"status": "rejected", "reason": "Out of warranty"},
            }

    monkeypatch.setattr(rc_module, "RecordContextService", _FakeAssembler)

    return svc


def _complaint_snapshot() -> PageSnapshotPayload:
    return PageSnapshotPayload(
        path="/complaint-management/complaints/c-1",
        search="",
        title="Complaint CMP-2026-0142",
        visible_text="complaint detail",
        entity=PageEntityRef(entity_type="complaint", id="c-1"),
    )


def _no_entity_snapshot() -> PageSnapshotPayload:
    return PageSnapshotPayload(
        path="/dashboard", search="", title="Home", visible_text="home"
    )


# ===========================================================================
# Routing tests (offline, deterministic) - the regression firewall
# ===========================================================================

# --- §3.1 - entity + record-class → assembler, agent loop bypassed ----------
def test_record_class_with_entity_bypasses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _parse(  # type: ignore[assignment]
        "record_question", targets_open_record=True
    )
    agent = _Spy(("should-not-run", [], _USAGE))
    render = _Spy(("grounded answer from facts", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected and who approved it?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is True, "record-class+entity must use the assembler render path"
    assert agent.called is False, (
        "record-class question on an entity page must take the deterministic "
        "assembler pre-route, not the MCP agent loop"
    )


# --- §3.2 - entity present but catalog question → agent loop (no theft) ------
def test_catalog_question_with_entity_uses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _parse("data_query")  # type: ignore[assignment]
    agent = _Spy(("active promos: ...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="What promotions are active right now?",
        page_snapshot=_complaint_snapshot(),
    )

    assert agent.called is True, (
        "a catalog question must reach the MCP agent loop even when an entity "
        "is on screen - the pre-route must not steal §1 operational questions"
    )
    assert render.called is False


# --- §3.4 - record phrasing but NO entity → agent loop, never assembler ------
def test_record_phrasing_without_entity_uses_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService
):
    # Even if the parser says record_question, no entity → no assembler.
    chat_service._parse_turn = lambda **_k: _parse(  # type: ignore[assignment]
        "record_question", targets_open_record=True
    )
    agent = _Spy(("...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was it rejected?",
        page_snapshot=_no_entity_snapshot(),
    )

    assert agent.called is True, (
        "without page_snapshot.entity the assembler has no id; must fall back "
        "to the agent loop / clarify, never call the assembler"
    )
    assert render.called is False


# --- §3.5 - RBAC denial → degrade to agent loop, no record facts leaked ------
def test_rbac_denied_degrades_to_agent_loop(
    seeded_user: str, chat_service: AIAssistantChatService, monkeypatch
):
    import app.services.ai_assistant_service as svc_module

    class _DenyPerm:
        def __init__(self, *_a, **_k):
            pass

        def check_user_has_permission(self, *_a, **_k):
            return False

    monkeypatch.setattr(svc_module, "UserPermissionService", _DenyPerm)
    chat_service._parse_turn = lambda **_k: _parse(  # type: ignore[assignment]
        "record_question", targets_open_record=True
    )
    agent = _Spy(("...", [], _USAGE))
    render = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is False, "no assembler render when the user lacks the view permission"
    assert agent.called is True, "RBAC denial degrades to the agent loop, not a crash"


# --- §4.7 - bubble path must never touch respond_contacts.session_vars ------
def test_bubble_path_never_writes_contact_session_vars(
    seeded_user: str, chat_service: AIAssistantChatService
):
    """The n8n WhatsApp brain owns ``respond_contacts.session_vars`` (keyed by
    respond_io_id). The bubble (keyed by user_id+conversation_id) must keep its
    state in ai_assistant_* tables only - never cross into the contact blob.
    """
    import app.services.ai_assistant_service as svc_module

    assert not hasattr(svc_module, "overwrite_for_contact"), (
        "bubble service imported the n8n session-var writer - isolation breach"
    )

    chat_service._parse_turn = lambda **_k: _parse(  # type: ignore[assignment]
        "record_question", targets_open_record=True
    )
    chat_service._render_record_answer = _Spy(("ans", [], _USAGE))  # type: ignore[assignment]
    chat_service._run_agent_loop = _Spy(("ans", [], _USAGE))  # type: ignore[assignment]

    # No respond_contacts table exists in this fixture; any write would raise.
    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="Why was this complaint rejected?",
        page_snapshot=_complaint_snapshot(),
    )


# --- A6 fusion: "what should I do now" must be state-grounded ----------------
# Routing-only assertion: a next-step question on an entity page must NOT be
# answered by the bare agent loop - it must take the assembler render path
# (which is permitted one user_guides_read call to fuse guide steps with the
# record's current state). Classifier verdict stubbed; the live verdict for
# this phrasing is covered by the opt-in eval below.
def test_what_should_i_do_now_takes_record_path(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _parse(  # type: ignore[assignment]
        "record_question", targets_open_record=True
    )
    agent = _Spy(("generic advice", [], _USAGE))
    render = _Spy(("state-grounded next step", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._render_record_answer = render  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="What should I do now?",
        page_snapshot=_complaint_snapshot(),
    )

    assert render.called is True
    assert agent.called is False, (
        "'what should I do now' must be grounded by the complaint's current "
        "state (assembler render + guide), not the generic agent loop alone"
    )


# --- Capability confidence floor (code-review fix) ---------------------------
# The capability short-circuit serves a static catalog with NO answer-LLM. Unlike
# the old tight keyword allowlist, the parser is probabilistic - so a LOW-confidence
# "capability" guess must NOT hijack a real question. It must fall through to the
# agent loop. A HIGH-confidence capability is served deterministically.
def test_low_confidence_capability_falls_through_to_agent(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _parse("capability", confidence=0.2)  # type: ignore[assignment]
    agent = _Spy(("real answer", [], _USAGE))
    served = {"hit": False}
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._serve_capability_answer = lambda **_k: served.__setitem__("hit", True)  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="what can I do to expedite this?",
        page_snapshot=_no_entity_snapshot(),
    )

    assert served["hit"] is False, "low-confidence capability must NOT serve the static catalog"
    assert agent.called is True, "low-confidence capability must fall through to the agent loop"


def test_high_confidence_capability_is_served_deterministically(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _parse("capability", confidence=0.95)  # type: ignore[assignment]
    agent = _Spy(("should-not-run", [], _USAGE))
    served = {"hit": False}
    chat_service._run_agent_loop = agent  # type: ignore[assignment]
    chat_service._serve_capability_answer = lambda **_k: served.__setitem__("hit", True) or (None, None)  # type: ignore[assignment]

    chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="what can you help me with?",
        page_snapshot=_no_entity_snapshot(),
    )

    assert served["hit"] is True, "high-confidence capability must be served from the catalog"
    assert agent.called is False, "capability short-circuit must bypass the agent loop"


# --- M3a Clarifier: ask-vs-guess -------------------------------------------
# When the parser flags needs_clarification with a question/options, respond()
# must ask (persist a clarify turn with chips) and NOT run the agent loop. After
# one clarify round it must proceed with the best assumption (no infinite loop).
def _clarify_parse(options):
    return ParseResult(
        standalone_query="standalone",
        intent="unknown",
        confidence=0.2,
        entities=ParseEntities(),
        signals=ParseSignals(
            needs_clarification=True,
            clarify_question="Which record do you mean?",
            clarify_options=list(options),
        ),
    )


def test_ambiguous_turn_asks_clarifying_question_with_chips(
    seeded_user: str, chat_service: AIAssistantChatService
):
    chat_service._parse_turn = lambda **_k: _clarify_parse(["Product", "Customer"])  # type: ignore[assignment]
    agent = _Spy(("should-not-run", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]

    _conv, msg = chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="the hanlim one",
        page_snapshot=None,
    )

    meta = msg.metadata_json or {}
    assert meta.get("clarify", {}).get("options") == ["Product", "Customer"], "chips must be surfaced"
    assert "Which record" in (msg.content or ""), "the clarifying question is the answer text"
    assert agent.called is False, "an ambiguous turn must clarify, not run the agent loop"


def test_second_ambiguous_turn_does_not_loop_clarifying(
    seeded_user: str, chat_service: AIAssistantChatService
):
    # Turn 1: clarify. Turn 2 (same conversation, still ambiguous): must proceed
    # to the agent loop with the best assumption - one clarify round max.
    chat_service._parse_turn = lambda **_k: _clarify_parse(["Product", "Customer"])  # type: ignore[assignment]
    agent = _Spy(("best-assumption answer", [], _USAGE))
    chat_service._run_agent_loop = agent  # type: ignore[assignment]

    conv, _msg1 = chat_service.respond(
        user_id=seeded_user, conversation_id=None, message="the hanlim one", page_snapshot=None
    )
    assert agent.called is False  # first turn clarified

    chat_service.respond(
        user_id=seeded_user, conversation_id=str(conv.id), message="still vague", page_snapshot=None
    )
    assert agent.called is True, "after one clarify round, a still-vague turn must answer with best assumption"
