"""Unit tests for app.services.access_agent_mcp_tool_service."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import AccessAgent, McpTool


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _new_agent(db: Session, name: str = "A", code: str | None = None) -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()),
        code=code or f"AG-{uuid.uuid4().hex[:6]}",
        name=name,
        is_active=True,
    )
    db.add(a)
    db.flush()
    return a


def _new_tool(db: Session, name: str | None = None, agent_id: str | None = None) -> McpTool:
    t = McpTool(
        id=str(uuid.uuid4()),
        tool_name=name or f"phase2_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/x",
        http_method="GET",
        is_active=True,
        last_seen_at=datetime.utcnow(),
        agent_id=agent_id,
    )
    db.add(t)
    db.flush()
    return t


def test_list_tools_for_agent_returns_only_owned(db: Session):
    from app.services.access_agent_mcp_tool_service import list_tools_for_agent

    a = _new_agent(db)
    b = _new_agent(db)
    t1 = _new_tool(db, agent_id=a.id)
    t2 = _new_tool(db, agent_id=b.id)
    t3 = _new_tool(db, agent_id=None)
    db.commit()

    rows = list_tools_for_agent(db, a.id)
    ids = {r.id for r in rows}
    assert t1.id in ids
    assert t2.id not in ids
    assert t3.id not in ids


def test_set_tools_for_agent_claims_and_releases(db: Session):
    from app.services.access_agent_mcp_tool_service import set_tools_for_agent

    a = _new_agent(db)
    b = _new_agent(db)
    owned_by_b = _new_tool(db, agent_id=b.id)
    owned_by_a = _new_tool(db, agent_id=a.id)
    unowned = _new_tool(db, agent_id=None)
    will_release = _new_tool(db, agent_id=a.id)
    db.commit()

    set_tools_for_agent(db, a.id, [owned_by_b.id, owned_by_a.id, unowned.id])
    db.commit()

    db.refresh(owned_by_b)
    db.refresh(owned_by_a)
    db.refresh(unowned)
    db.refresh(will_release)
    assert owned_by_b.agent_id == a.id
    assert owned_by_a.agent_id == a.id
    assert unowned.agent_id == a.id
    assert will_release.agent_id is None


def test_set_tools_for_agent_empty_releases_all(db: Session):
    from app.services.access_agent_mcp_tool_service import set_tools_for_agent

    a = _new_agent(db)
    t1 = _new_tool(db, agent_id=a.id)
    t2 = _new_tool(db, agent_id=a.id)
    db.commit()

    set_tools_for_agent(db, a.id, [])
    db.commit()

    db.refresh(t1)
    db.refresh(t2)
    assert t1.agent_id is None
    assert t2.agent_id is None


def test_list_picker_tools_includes_current_owner(db: Session):
    from app.services.access_agent_mcp_tool_service import list_picker_tools

    a = _new_agent(db, name="Alpha")
    b = _new_agent(db, name="Bravo")
    t_owned = _new_tool(db, agent_id=b.id)
    t_unowned = _new_tool(db, agent_id=None)
    db.commit()

    rows = list_picker_tools(db, only_active=True, limit=500)
    by_id = {r["id"]: r for r in rows}
    assert by_id[t_owned.id]["current_agent_id"] == b.id
    assert by_id[t_owned.id]["current_agent_name"] == "Bravo"
    assert by_id[t_unowned.id]["current_agent_id"] is None
    assert by_id[t_unowned.id]["current_agent_name"] is None
