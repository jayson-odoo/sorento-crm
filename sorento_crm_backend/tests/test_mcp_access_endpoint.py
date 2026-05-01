"""Integration tests for /api/v1/system/mcp-access endpoints."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
)
from app.models.respond_workspace import RespondWorkspace


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


def test_check_endpoint_allow(client, db, cleanup):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        api_key_ciphertext="test-cipher",
    )
    db.add(ws); db.flush(); cleanup["workspaces"].append(ws.id)
    agent = AccessAgent(id=str(uuid.uuid4()), code=f"AG-{uuid.uuid4().hex[:6]}", name="A", is_active=True)
    db.add(agent); db.flush(); cleanup["agents"].append(agent.id)
    tool = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"chk_{uuid.uuid4().hex[:8]}",
        http_path="/x", http_method="GET",
        is_active=True, last_seen_at=datetime.utcnow(),
        agent_id=agent.id,
    )
    db.add(tool); db.flush(); cleanup["tools"].append(tool.id)
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=ws.id,
    )
    db.add(contact); db.flush(); cleanup["contacts"].append(contact.id)
    link = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=contact.id,
        respond_contact_phone=f"+60{uuid.uuid4().hex[:9]}",
        agent_id=agent.id, is_allowed=True,
    )
    db.add(link); db.flush(); cleanup["links"].append(link.id)
    db.commit()

    res = client.post(
        "/api/v1/system/mcp-access/check",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "tool_name": tool.tool_name,
            "contact_id": contact.respond_io_id,
            "space_id": ws.space_id,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["allowed"] is True
    assert body["decision"] == "allow"
    assert body["agent_name"] == "A"


def test_check_endpoint_deny_unknown_tool(client, db, cleanup):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    res = client.post(
        "/api/v1/system/mcp-access/check",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"tool_name": f"missing_{uuid.uuid4().hex[:6]}", "contact_id": "x", "space_id": str(uuid.uuid4())},
    )
    assert res.status_code == 200, res.text
    assert res.json()["decision"] == "deny_unknown_tool"


def test_log_endpoint_returns_recent(client, db, cleanup):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
    log = McpAccessLog(
        id=str(uuid.uuid4()),
        tool_name=f"log_{uuid.uuid4().hex[:8]}",
        decision="deny_unknown_tool",
    )
    db.add(log); db.flush(); cleanup["logs"].append(log.id); db.commit()

    res = client.get(
        "/api/v1/system/mcp-access/log",
        headers={"X-API-Key": API_KEY},
        params={"limit": 50},
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert any(r["id"] == log.id for r in rows)


def test_check_requires_api_key(client):
    res = client.post(
        "/api/v1/system/mcp-access/check",
        json={"tool_name": "x", "contact_id": "x", "space_id": str(uuid.uuid4())},
    )
    assert res.status_code in (401, 403)
