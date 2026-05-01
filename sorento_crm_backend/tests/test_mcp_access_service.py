"""Unit tests for app.services.mcp_access_service.evaluate (Phase 3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
)
from app.models.respond_workspace import RespondWorkspace


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup(db):
    state = {"agents": [], "tools": [], "contacts": [], "links": [], "logs": [], "workspaces": []}
    yield state
    if state["logs"]:
        db.query(McpAccessLog).filter(McpAccessLog.id.in_(state["logs"])).delete(synchronize_session=False)
    if state["links"]:
        db.query(ContactAgentAccess).filter(ContactAgentAccess.id.in_(state["links"])).delete(synchronize_session=False)
    if state["tools"]:
        db.query(McpTool).filter(McpTool.id.in_(state["tools"])).delete(synchronize_session=False)
    if state["contacts"]:
        db.query(RespondContact).filter(RespondContact.id.in_(state["contacts"])).delete(synchronize_session=False)
    if state["agents"]:
        db.query(AccessAgent).filter(AccessAgent.id.in_(state["agents"])).delete(synchronize_session=False)
    if state["workspaces"]:
        db.query(RespondWorkspace).filter(RespondWorkspace.id.in_(state["workspaces"])).delete(synchronize_session=False)
    db.commit()


def _workspace(db, cleanup) -> RespondWorkspace:
    w = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        api_key_ciphertext="test-cipher",
    )
    db.add(w); db.flush()
    cleanup["workspaces"].append(w.id)
    return w


def _agent(db, cleanup, name="Owner") -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()),
        code=f"AG-{uuid.uuid4().hex[:6]}",
        name=name,
        is_active=True,
    )
    db.add(a); db.flush()
    cleanup["agents"].append(a.id)
    return a


def _tool(db, cleanup, agent_id=None, is_active=True) -> McpTool:
    t = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"phase3_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/x",
        http_method="GET",
        is_active=is_active,
        last_seen_at=datetime.utcnow(),
        agent_id=agent_id,
    )
    db.add(t); db.flush()
    cleanup["tools"].append(t.id)
    return t


def _contact(db, cleanup, *, respond_io_id=None, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        respond_io_id=respond_io_id or f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=workspace_id,  # may be None; set explicitly when needed
    )
    db.add(c); db.flush()
    cleanup["contacts"].append(c.id)
    return c


def _grant(db, cleanup, contact, agent, *, is_allowed=True) -> ContactAgentAccess:
    g = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=contact.id,
        respond_contact_phone=f"+60{uuid.uuid4().hex[:9]}",
        agent_id=agent.id,
        is_allowed=is_allowed,
    )
    db.add(g); db.flush()
    cleanup["links"].append(g.id)
    return g


def test_evaluate_allow(db, cleanup):
    from app.services.mcp_access_service import evaluate

    ws = _workspace(db, cleanup)
    agent = _agent(db, cleanup, "Sales")
    tool = _tool(db, cleanup, agent_id=agent.id)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    _grant(db, cleanup, contact, agent)
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id=contact.respond_io_id, space_id=ws.id)
    assert out.allowed is True
    assert out.decision == "allow"
    assert out.agent_name == "Sales"

    # Audit row written
    log = db.query(McpAccessLog).filter(McpAccessLog.tool_name == tool.tool_name).order_by(McpAccessLog.ts.desc()).first()
    assert log is not None
    cleanup["logs"].append(log.id)
    assert log.decision == "allow"
    assert log.matched_agent_id == agent.id


def test_evaluate_deny_unknown_tool(db, cleanup):
    from app.services.mcp_access_service import evaluate
    out = evaluate(db, tool_name=f"missing_{uuid.uuid4().hex[:6]}", contact_id="x", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_unknown_tool"
    assert out.agent_name is None


def test_evaluate_deny_tool_unlinked(db, cleanup):
    from app.services.mcp_access_service import evaluate
    tool = _tool(db, cleanup, agent_id=None)
    db.commit()
    out = evaluate(db, tool_name=tool.tool_name, contact_id="x", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_tool_unlinked"
    assert out.agent_name is None


def test_evaluate_deny_unknown_contact(db, cleanup):
    from app.services.mcp_access_service import evaluate
    agent = _agent(db, cleanup)
    tool = _tool(db, cleanup, agent_id=agent.id)
    db.commit()
    out = evaluate(db, tool_name=tool.tool_name, contact_id=f"missing_{uuid.uuid4().hex[:6]}", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_unknown_contact"
    assert out.agent_name == agent.name  # owner returned for UI message


def test_evaluate_deny_no_access(db, cleanup):
    from app.services.mcp_access_service import evaluate

    ws = _workspace(db, cleanup)
    owner = _agent(db, cleanup, "Sales")
    other = _agent(db, cleanup, "Support")
    tool = _tool(db, cleanup, agent_id=owner.id)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    _grant(db, cleanup, contact, other)  # contact under Support, not Sales
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id=contact.respond_io_id, space_id=ws.id)
    assert out.allowed is False
    assert out.decision == "deny_no_access"
    assert out.agent_name == "Sales"


def test_evaluate_deny_when_owner_agent_inactive(db, cleanup):
    from app.services.mcp_access_service import evaluate

    owner = _agent(db, cleanup)
    owner.is_active = False
    db.flush()
    tool = _tool(db, cleanup, agent_id=owner.id)
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id="anything", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_tool_unlinked"
