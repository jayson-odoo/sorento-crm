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


def test_sync_catalog_updates_existing_tool(db: Session, monkeypatch, cleanup_tool_names):
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)

    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v1", path="/a", module="m1"),),
    )
    svc.sync_catalog(db)
    db.commit()

    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v2", path="/b", module="m2"),),
    )
    report = svc.sync_catalog(db)
    db.commit()

    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    assert row.description == "v2"
    assert row.http_path == "/b"
    assert row.module_key == "m2"
    assert row.is_active is True
    assert report.updated >= 1


def test_sync_catalog_deactivates_removed_tools(db: Session, monkeypatch, cleanup_tool_names):
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)

    # Round 1: tool exists in code catalog
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v1", path="/a"),),
    )
    svc.sync_catalog(db)
    db.commit()
    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    assert row.is_active is True

    # Round 2: tool no longer in code catalog
    monkeypatch.setattr(svc, "_load_specs", lambda: ())
    report = svc.sync_catalog(db)
    db.commit()

    db.refresh(row)
    assert row.is_active is False
    assert report.deactivated >= 1

    # Round 3: tool comes back -> is_active flips back to True
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v1", path="/a"),),
    )
    svc.sync_catalog(db)
    db.commit()
    db.refresh(row)
    assert row.is_active is True


def test_sync_catalog_preserves_agent_id(db: Session, monkeypatch, cleanup_tool_names):
    from app.models.access import AccessAgent
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)

    # Seed via sync
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v1", path="/a"),),
    )
    svc.sync_catalog(db)
    db.commit()

    # Admin sets ownership
    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=f"OWN-{uuid.uuid4().hex[:6]}",
        name="Owner",
        is_active=True,
    )
    db.add(agent)
    db.flush()
    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    row.agent_id = agent.id
    db.commit()

    # Re-run sync with the same spec — agent_id must NOT be cleared.
    svc.sync_catalog(db)
    db.commit()
    db.refresh(row)
    assert row.agent_id == agent.id

    # Re-run sync with the spec removed — tool is deactivated but agent_id
    # is preserved (admin can still see who used to own it).
    monkeypatch.setattr(svc, "_load_specs", lambda: ())
    svc.sync_catalog(db)
    db.commit()
    db.refresh(row)
    assert row.is_active is False
    assert row.agent_id == agent.id

    # Cleanup the agent (cleanup_tool_names handles the McpTool row).
    db.query(AccessAgent).filter(AccessAgent.id == agent.id).delete()
    db.commit()
