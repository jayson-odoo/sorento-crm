"""Unit tests for app.services.mcp_tool_registry_service.sync_catalog."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import McpTool


@dataclass(frozen=True)
class _FakeSpec:
    name: str
    description: str
    path: str
    method: str = "GET"
    module: str = ""


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup_tool_names(db: Session):
    names: list[str] = []
    yield names
    if names:
        db.query(McpTool).filter(McpTool.tool_name.in_(names)).delete(synchronize_session=False)
        db.commit()


def test_sync_catalog_inserts_new_tools(db: Session, monkeypatch, cleanup_tool_names):
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)
    fake_specs = (
        _FakeSpec(
            name=name,
            description="A phase 1 test tool.",
            path="/api/v1/phase1/test",
            method="GET",
            module="phase1",
        ),
    )
    monkeypatch.setattr(svc, "_load_specs", lambda: fake_specs)

    report = svc.sync_catalog(db)

    db.commit()
    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    assert row.module_key == "phase1"
    assert row.http_path == "/api/v1/phase1/test"
    assert row.http_method == "GET"
    assert row.is_active is True
    assert row.last_seen_at is not None
    assert report.added >= 1
