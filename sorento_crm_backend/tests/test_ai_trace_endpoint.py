"""HTTP tests for the M2 trace endpoint (PLAN §9 UAC T1).

``GET /api/v1/system/ai-assistant/usage/queries/{message_id}/trace``:
- happy path returns the root + ordered span tree,
- 404 when the message has no trace,
- 403 for a principal lacking ``system.ai_assistant_settings.view``.

Mirrors the TestClient + controllable-permission fixture used by
``test_ai_prompt_registry.py``. Blank Postgres schema, no network.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.ai_assistant import (
    AIAssistantConversation,
    AIAssistantMessage,
    AIAssistantSpan,
    AIAssistantTrace,
)
from app.models.user import User
from tests._pg_fixture import blank_session


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        yield session


# UUID-typed columns reject slug ids - use valid UUIDs. User.id is a String PK.
_CONV_ID = "118892da-f08f-562f-8553-a8aa6727138b"
_MSG_ID = "c1f2f463-4922-56c3-9239-49e868288ad7"
_TRACE_ID = "b830fd9f-e2d2-5680-98b6-039665eed77d"
_ROOT_SPAN_ID = "fd72df69-a027-5828-9471-44c0f827eae7"
_LLM_SPAN_ID = "9c915f41-6cbe-5da6-bc3b-5309192a3c7e"
_NT_CONV_ID = "adce5cde-aa52-5f95-9636-8f4857d93eca"
_NT_MSG_ID = "390ec245-4b1b-5c97-b44e-e837e291dd56"
@pytest.fixture
def traced_message(db: Session) -> str:
    """Seed a message with a trace + two spans; return the message id."""
    # Parents must land before their FK children -- these models declare no ORM
    # relationships, so nothing orders the inserts within a single flush.
    user = User(id="f84ec219-709b-5290-a890-e907ed4f7740", email="ep@test.com", name="EP", status="ACTIVE")
    db.add(user)
    db.flush()
    conv = AIAssistantConversation(id=_CONV_ID, user_id="f84ec219-709b-5290-a890-e907ed4f7740", title="T")
    db.add(conv)
    db.flush()
    msg = AIAssistantMessage(id=_MSG_ID, conversation_id=_CONV_ID, role="assistant", content="a")
    db.add(msg)
    db.flush()
    trace = AIAssistantTrace(
        id=_TRACE_ID,
        message_id=_MSG_ID,
        conversation_id=_CONV_ID,
        user_id="f84ec219-709b-5290-a890-e907ed4f7740",
        status="ok",
        total_tokens_in=10,
        total_tokens_out=5,
        latency_ms=123,
        span_count=2,
    )
    db.add(trace)
    db.flush()
    db.add(
        AIAssistantSpan(
            id=_ROOT_SPAN_ID, trace_id=_TRACE_ID, parent_id=None,
            dotted_order="000001", span_kind="AGENT", name="assistant turn",
        )
    )
    db.flush()
    db.add(
        AIAssistantSpan(
            id=_LLM_SPAN_ID, trace_id=_TRACE_ID, parent_id=_ROOT_SPAN_ID,
            dotted_order="000002", span_kind="LLM", name="chat gpt-4o",
            request_model="gpt-4o", tokens_in=10, tokens_out=5,
            prompt_name="agent_system", prompt_version=1,
        )
    )
    db.flush()
    msg.trace_id = _TRACE_ID
    db.commit()
    return _MSG_ID


@pytest.fixture
def notrace_message(db: Session) -> str:
    """A message with no trace at all."""
    user = User(id="51af1c08-cd3a-5bbb-aa48-14c0bd8207bf", email="nt@test.com", name="NT", status="ACTIVE")
    db.add(user)
    db.flush()  # parent must land before the FK child (no ORM relationship to order it)
    conv = AIAssistantConversation(id=_NT_CONV_ID, user_id="51af1c08-cd3a-5bbb-aa48-14c0bd8207bf", title="T")
    db.add(conv)
    db.flush()
    db.add(AIAssistantMessage(id=_NT_MSG_ID, conversation_id=_NT_CONV_ID, role="assistant", content="a"))
    db.commit()
    return _NT_MSG_ID


@pytest.fixture
def api(db: Session, monkeypatch):
    """TestClient wired to the blank Postgres session with a controllable permission gate."""
    from fastapi.testclient import TestClient

    import app.dependencies as deps
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[deps.get_db] = _override_db
    app.dependency_overrides[deps.get_current_user] = lambda: {"id": "u-admin"}
    app.dependency_overrides[deps.get_current_user_or_api_key] = lambda: {"id": "u-admin"}
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        app.dependency_overrides.pop(deps.get_current_user, None)
        app.dependency_overrides.pop(deps.get_current_user_or_api_key, None)


_BASE = "/api/v1/system/ai-assistant/usage/queries"


def test_trace_endpoint_returns_span_tree(api, traced_message: str):
    client, allow = api
    allow.add("system.ai_assistant_settings.view")
    res = client.get(f"{_BASE}/{traced_message}/trace")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == _TRACE_ID
    assert body["message_id"] == traced_message
    assert body["span_count"] == 2
    assert body["total_tokens_in"] == 10
    assert body["total_tokens_out"] == 5
    spans = body["spans"]
    assert len(spans) == 2
    # Ordered by dotted_order → root AGENT first.
    assert [s["span_kind"] for s in spans] == ["AGENT", "LLM"]
    assert spans[0]["parent_id"] is None
    assert spans[1]["parent_id"] == spans[0]["id"]
    assert spans[1]["prompt_name"] == "agent_system"
    assert spans[1]["prompt_version"] == 1


def test_trace_endpoint_404_when_no_trace(api, notrace_message: str):
    client, allow = api
    allow.add("system.ai_assistant_settings.view")
    res = client.get(f"{_BASE}/{notrace_message}/trace")
    assert res.status_code == 404, res.text


def test_trace_endpoint_404_when_message_missing(api):
    client, allow = api
    allow.add("system.ai_assistant_settings.view")
    res = client.get(f"{_BASE}/cccccccc-0000-0000-0000-000000000099/trace")
    assert res.status_code == 404, res.text


def test_trace_endpoint_denies_without_permission(api, traced_message: str):
    client, _allow = api  # no grants
    res = client.get(f"{_BASE}/{traced_message}/trace")
    assert res.status_code == 403, res.text
