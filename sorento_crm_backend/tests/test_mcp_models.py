"""ORM smoke test for the McpTool catalog row."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import McpTool


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


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
    assert tool.is_active is True
