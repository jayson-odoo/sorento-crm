"""Integration tests for /access-agents/{id}/mcp-tools GET/PUT routes."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.access import AccessAgent, McpTool


API_KEY = os.environ.get("EXTERNAL_API_KEY", "")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup_ids(db):
    tool_ids: list[str] = []
    agent_ids: list[str] = []
    yield {"tools": tool_ids, "agents": agent_ids}
    if tool_ids:
        db.query(McpTool).filter(McpTool.id.in_(tool_ids)).delete(synchronize_session=False)
    if agent_ids:
        db.query(AccessAgent).filter(AccessAgent.id.in_(agent_ids)).delete(synchronize_session=False)
    db.commit()


def _seed_agent(db, name: str = "A") -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()),
        code=f"AG-{uuid.uuid4().hex[:6]}",
        name=name,
        is_active=True,
    )
    db.add(a)
    db.flush()
    return a


def _seed_tool(db, agent_id: str | None = None) -> McpTool:
    t = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"phase2_route_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/x",
        http_method="GET",
        is_active=True,
        last_seen_at=datetime.utcnow(),
        agent_id=agent_id,
    )
    db.add(t)
    db.flush()
    return t


def test_get_returns_tools_owned_by_agent(client, db, cleanup_ids):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    a = _seed_agent(db)
    b = _seed_agent(db)
    cleanup_ids["agents"].extend([a.id, b.id])
    t_a = _seed_tool(db, agent_id=a.id)
    t_b = _seed_tool(db, agent_id=b.id)
    cleanup_ids["tools"].extend([t_a.id, t_b.id])
    db.commit()

    res = client.get(
        f"/api/v1/user-management/access-agents/{a.id}/mcp-tools",
        headers={"X-API-Key": API_KEY},
    )
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()}
    assert t_a.id in ids
    assert t_b.id not in ids


def test_put_reassigns_tool_from_other_agent(client, db, cleanup_ids):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    a = _seed_agent(db, "Alpha")
    b = _seed_agent(db, "Bravo")
    cleanup_ids["agents"].extend([a.id, b.id])
    t = _seed_tool(db, agent_id=b.id)
    cleanup_ids["tools"].append(t.id)
    db.commit()

    res = client.put(
        f"/api/v1/user-management/access-agents/{a.id}/mcp-tools",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"tool_ids": [t.id]},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    db.refresh(t)
    assert t.agent_id == a.id


def test_put_releases_tools_not_in_new_set(client, db, cleanup_ids):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    a = _seed_agent(db)
    cleanup_ids["agents"].append(a.id)
    t1 = _seed_tool(db, agent_id=a.id)
    t2 = _seed_tool(db, agent_id=a.id)
    cleanup_ids["tools"].extend([t1.id, t2.id])
    db.commit()

    res = client.put(
        f"/api/v1/user-management/access-agents/{a.id}/mcp-tools",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"tool_ids": [t1.id]},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    db.refresh(t1)
    db.refresh(t2)
    assert t1.agent_id == a.id
    assert t2.agent_id is None
