"""Integration tests for GET /api/v1/system/mcp-tools picker endpoint."""
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


def _seed_tool(db, name: str | None = None, agent_id: str | None = None) -> McpTool:
    t = McpTool(
        id=str(uuid.uuid4()),
        tool_name=name or f"picker_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/x",
        http_method="GET",
        is_active=True,
        last_seen_at=datetime.utcnow(),
        module_key="z_phase2",
        agent_id=agent_id,
    )
    db.add(t)
    db.flush()
    return t


def test_picker_returns_tools_with_owner_info(client, db, cleanup_ids):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")

    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=f"PK-{uuid.uuid4().hex[:6]}",
        name="Picker Agent",
        is_active=True,
    )
    db.add(agent)
    db.flush()
    cleanup_ids["agents"].append(agent.id)

    tool_owned = _seed_tool(db, agent_id=agent.id)
    tool_free = _seed_tool(db, agent_id=None)
    cleanup_ids["tools"].extend([tool_owned.id, tool_free.id])
    db.commit()

    res = client.get(
        "/api/v1/system/mcp-tools",
        headers={"X-API-Key": API_KEY},
        params={"is_active": "true", "limit": 500},
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    by_id = {r["id"]: r for r in rows}
    assert tool_owned.id in by_id
    assert by_id[tool_owned.id]["current_agent_id"] == agent.id
    assert by_id[tool_owned.id]["current_agent_name"] == "Picker Agent"
    assert tool_free.id in by_id
    assert by_id[tool_free.id]["current_agent_id"] is None


def test_picker_requires_api_key(client):
    res = client.get("/api/v1/system/mcp-tools")
    assert res.status_code in (401, 403)
