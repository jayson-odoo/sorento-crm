"""ORM smoke tests for McpTool, McpAccessLog, and AccessAgent.mcp_tools."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import AccessAgent, McpAccessLog, McpTool


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _new_agent(db: Session, code: str = "TEST-AGENT") -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()), code=code, name="Test Agent", is_active=True
    )
    db.add(a)
    db.flush()
    return a


def test_mcp_tool_inserts_unowned(db: Session):
    tool = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"test_tool_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/test",
        http_method="GET",
        last_seen_at=datetime.utcnow(),
    )
    db.add(tool)
    db.flush()
    assert tool.id is not None
    assert tool.agents == []
    assert tool.is_active is True


def test_access_agent_mcp_tools_many_to_many(db: Session):
    agent_a = _new_agent(db, code=f"REL-A-{uuid.uuid4().hex[:6]}")
    agent_b = _new_agent(db, code=f"REL-B-{uuid.uuid4().hex[:6]}")
    tool = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"rel_tool_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/rel",
        http_method="GET",
        last_seen_at=datetime.utcnow(),
    )
    tool.agents = [agent_a, agent_b]
    db.add(tool)
    db.flush()
    db.refresh(agent_a)
    db.refresh(agent_b)
    assert tool in agent_a.mcp_tools
    assert tool in agent_b.mcp_tools
    assert {a.id for a in tool.agents} == {agent_a.id, agent_b.id}


def test_mcp_access_log_inserts(db: Session):
    log = McpAccessLog(
        id=str(uuid.uuid4()),
        tool_name="test_tool",
        contact_external_id="ext-1",
        decision="allow",
    )
    db.add(log)
    db.flush()
    assert log.id is not None
    assert log.ts is not None
