"""Tests for AI assistant usage logging, suggestions, and wishlist tagging.

The full ``respond()`` flow is exercised against an in-memory SQLite database;
the LLM provider, MCP catalog, RAG selector, entity resolver, and auth context
are all monkey-patched so the test is fully synthetic.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.ai_assistant import AIAssistantAuthContext, PageSnapshotPayload
from app.models.ai_assistant import (
    AIAssistantMessage,
    AIAssistantUnansweredQuery,
    AIAssistantUsageLog,
)
from app.services.ai_assistant_service import AIAssistantChatService, MCPToolCallResult
from app.services.entity_resolver import ResolutionResult
from tests._pg_fixture import blank_session


@pytest.fixture
def db_session() -> Session:
    """A blank Postgres schema, rolled back after the test."""
    with blank_session() as session:
        yield session


@pytest.fixture
def seeded_user(db_session: Session) -> str:
    user = User(id="u-1", email="u1@test.com", name="User One", status="ACTIVE")
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture
def chat_service(db_session: Session) -> AIAssistantChatService:
    """Wire a chat service with all external dependencies stubbed.

    The provider call inside ``_run_agent_loop`` is replaced with a stub so
    no network traffic happens; the same goes for RAG, reformulation, the
    entity resolver, and the auth-context builder.
    """
    svc = AIAssistantChatService(db_session)

    # Ensure config row exists (api_key required for suggestion generation
    # branch to be exercised).
    cfg = svc.cfg.get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()

    # Stub out auth context (otherwise needs full RBAC).
    svc.gov.build_auth_context = lambda user_id: AIAssistantAuthContext(  # type: ignore[assignment]
        user_id=user_id,
        role_ids=["r1"],
        permission_slugs=["system.ai_assistant_chat.use"],
        enabled_modules=[],
    )
    # Stub the Semantic Parser so it never hits the network. intent=data_query
    # routes to the agent loop (which the tests stub), NOT the deterministic
    # capability short-circuit.
    from app.schemas.ai_semantic_parser import ParseResult

    svc._parse_turn = lambda **_k: ParseResult(  # type: ignore[assignment]
        standalone_query="standalone", intent="data_query", confidence=0.9
    )
    # Stub RAG selector to a no-op.
    svc._rag_select_tools = lambda *, standalone_query, enabled_tools, top_k: ([], [])  # type: ignore[assignment]
    # Stub the entity resolver helper used inside respond().
    import app.services.ai_assistant_service as svc_module

    svc_module.resolve_references = lambda _db, _q: ResolutionResult(  # type: ignore[assignment]
        tokens=[], resolutions=[], elapsed_ms=0.0
    )
    return svc


def _stub_agent(answer: str, tool_calls: list[MCPToolCallResult] | None = None,
                tokens: tuple[int, int, int] = (12, 7, 19)):
    def runner(**_kwargs):
        usage = {
            "prompt_tokens": tokens[0],
            "completion_tokens": tokens[1],
            "total_tokens": tokens[2],
        }
        return answer, list(tool_calls or []), usage

    return runner


def _stub_suggestions(values: list[str] | None):
    def runner(**_kwargs):
        return list(values or [])

    return runner


def test_respond_writes_usage_log_with_token_counts(
    db_session: Session,
    seeded_user: str,
    chat_service: AIAssistantChatService,
):
    chat_service._run_agent_loop = _stub_agent("Here is your answer.")  # type: ignore[assignment]
    chat_service._generate_suggestions = _stub_suggestions(["q1", "q2", "q3", "q4", "q5"])  # type: ignore[assignment]

    conv, msg = chat_service.respond(
        user_id=seeded_user, conversation_id=None, message="hello"
    )

    log = db_session.query(AIAssistantUsageLog).filter_by(message_id=str(msg.id)).one()
    assert log.user_id == seeded_user
    assert log.conversation_id == str(conv.id)
    assert log.prompt_tokens == 12
    assert log.completion_tokens == 7
    assert log.total_tokens == 19
    assert log.provider == "openai"
    assert log.model == "gpt-4o-mini"
    assert log.was_answered is True


def test_respond_stores_suggestions_in_metadata(
    db_session: Session,
    seeded_user: str,
    chat_service: AIAssistantChatService,
):
    chat_service._run_agent_loop = _stub_agent("Reply with content.")  # type: ignore[assignment]
    chat_service._generate_suggestions = _stub_suggestions(["a", "b", "c"])  # type: ignore[assignment]

    _conv, msg = chat_service.respond(
        user_id=seeded_user, conversation_id=None, message="anything"
    )

    refreshed = db_session.query(AIAssistantMessage).filter_by(id=msg.id).one()
    suggestions = (refreshed.metadata_json or {}).get("suggestions")
    assert suggestions == ["a", "b", "c"]


def test_respond_stores_page_snapshot_when_provided(
    db_session: Session,
    seeded_user: str,
    chat_service: AIAssistantChatService,
):
    chat_service._run_agent_loop = _stub_agent("Reply.")  # type: ignore[assignment]
    chat_service._generate_suggestions = _stub_suggestions([])  # type: ignore[assignment]

    snapshot = PageSnapshotPayload(
        path="/orders/abc",
        search="?tab=lines",
        title="Order ABC",
        visible_text="lots of order detail text" * 80,
    )
    conv, _msg = chat_service.respond(
        user_id=seeded_user,
        conversation_id=None,
        message="summarise this page",
        page_snapshot=snapshot,
    )

    user_msg = (
        db_session.query(AIAssistantMessage)
        .filter_by(conversation_id=conv.id, role="user")
        .order_by(AIAssistantMessage.created_at.asc())
        .first()
    )
    assert user_msg is not None
    user_meta = user_msg.metadata_json or {}
    assert "page_snapshot" in user_meta
    assert user_meta["page_snapshot"]["path"] == "/orders/abc"
    # Truncated to 1000 chars per spec.
    assert len(user_meta["page_snapshot"]["visible_text"]) <= 1000


def test_respond_marks_was_answered_false_for_fallback(
    db_session: Session,
    seeded_user: str,
    chat_service: AIAssistantChatService,
):
    # This is the exact deterministic-fallback string used when there are no
    # tool calls and no model output.
    fallback_text = chat_service._deterministic_fallback([])
    chat_service._run_agent_loop = _stub_agent(fallback_text, tokens=(0, 0, 0))  # type: ignore[assignment]
    chat_service._generate_suggestions = _stub_suggestions([])  # type: ignore[assignment]

    _conv, msg = chat_service.respond(
        user_id=seeded_user, conversation_id=None, message="who are you?"
    )

    log = db_session.query(AIAssistantUsageLog).filter_by(message_id=str(msg.id)).one()
    assert log.was_answered is False


def test_respond_inserts_unanswered_query_on_fallback(
    db_session: Session,
    seeded_user: str,
    chat_service: AIAssistantChatService,
):
    fallback_text = chat_service._deterministic_fallback([])
    chat_service._run_agent_loop = _stub_agent(fallback_text, tokens=(0, 0, 0))  # type: ignore[assignment]
    chat_service._generate_suggestions = _stub_suggestions([])  # type: ignore[assignment]

    _conv, msg = chat_service.respond(
        user_id=seeded_user, conversation_id=None, message="completely unknown question"
    )

    rows = (
        db_session.query(AIAssistantUnansweredQuery)
        .filter_by(message_id=str(msg.id))
        .all()
    )
    assert len(rows) == 1
    assert rows[0].cluster_id is None  # cluster gets assigned later by the job
