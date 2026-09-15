"""Unit tests for app.services.mcp_tool_registry_service.sync_catalog.

`sync_catalog`'s deactivation step is a blanket UPDATE over every active row in
the real `mcp_tools` table (`last_seen_at < sync_started_at`), not scoped to the
tool names a given test creates - that is the service's actual contract (a tool
absent from ANY sync's catalog gets deactivated). Any other test file that spins
up `with TestClient(app) as client:` fires FastAPI's startup event, which runs a
REAL `sync_catalog(db)` + `db.commit()` against the SAME shared database
(`app/main.py::startup_event`). Under CI's `-n auto` that runs on another xdist
worker at any moment, so a real sync from an unrelated file can commit a
deactivation of THIS file's fake `phase1_test_*` row (which is never in the real
catalog) between this file's own commit and its own assert - see run 34931786068,
`test_sync_catalog_deactivates_removed_tools` failing on
`assert row.is_active is True` immediately after round 1. `--dist loadfile`
already serializes this file's own tests onto one worker, so the race is
cross-file, not within this file; the fix is to stop sharing the table at all,
the same way `tests/test_mcp_catalog_ideation.py` already does for this same
service: `blank_session()` gives each test a private scratch Postgres schema
that no other worker's real sync can ever touch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.models.access import McpTool
from tests._pg_fixture import blank_session


@dataclass(frozen=True)
class _FakeSpec:
    name: str
    description: str
    path: str
    method: str = "GET"
    module: str = ""
    restricted_fields: tuple = ()




@pytest.fixture
def db() -> Session:
    with blank_session() as s:
        yield s


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


def test_sync_catalog_writes_restricted_fields(db: Session, monkeypatch, cleanup_tool_names):
    """AC-964: a `restricted=` field on a presenter's tool reaches `mcp_tools.restricted_fields`
    from a sync alone, with no FE change - this is the sync half of that contract, on a
    FAKE tool declaring one (the real tools that will carry `inventory.sellable` /
    `purchase_orders.supplier` are added by a sibling lane)."""
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)
    fake_specs = (
        _FakeSpec(
            name=name,
            description="A tool with one restricted field.",
            path="/api/v1/phase1/test",
            restricted_fields=(("inventory.sellable", "Sellable stock"),),
        ),
    )
    monkeypatch.setattr(svc, "_load_specs", lambda: fake_specs)

    svc.sync_catalog(db)
    db.commit()

    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    assert row.restricted_fields == [{"key": "inventory.sellable", "label": "Sellable stock"}]

    # Re-sync with the field dropped: the row must follow the catalog, not keep a stale key.
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v2", path="/api/v1/phase1/test"),),
    )
    svc.sync_catalog(db)
    db.commit()
    db.refresh(row)
    assert row.restricted_fields == []


def test_sync_catalog_tool_with_nothing_restricted_syncs_empty_list(
    db: Session, monkeypatch, cleanup_tool_names
):
    from app.services import mcp_tool_registry_service as svc

    name = f"phase1_test_{uuid.uuid4().hex[:8]}"
    cleanup_tool_names.append(name)
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (_FakeSpec(name=name, description="v1", path="/a"),),
    )

    svc.sync_catalog(db)
    db.commit()

    row = db.query(McpTool).filter(McpTool.tool_name == name).one()
    assert row.restricted_fields == []


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

    # Re-run sync with the same spec - agent_id must NOT be cleared.
    svc.sync_catalog(db)
    db.commit()
    db.refresh(row)
    assert row.agent_id == agent.id

    # Re-run sync with the spec removed - tool is deactivated but agent_id
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


def test_sync_catalog_stamps_chatbot_domain_from_the_tool_domain_map(
    db: Session, monkeypatch, cleanup_tool_names
):
    """D17 (8 Sep 2026): `chatbot_domain` comes from
    `app.services.mcp_tool_domains.CHATBOT_TOOL_DOMAINS`, NOT from
    `app.services.chatbot.contracts.DOMAIN_SPEC` - `sync_catalog` is core and must
    never import the chatbot package (AC-002). A tool in the map gets its domain, a
    tool absent from it gets NULL (never enters a chatbot pool)."""
    from app.services import mcp_tool_domains, mcp_tool_registry_service as svc

    suffix = uuid.uuid4().hex[:8]
    tool_a = f"phase1_test_a_{suffix}"
    tool_b = f"phase1_test_b_{suffix}"
    tool_c = f"phase1_test_c_{suffix}"  # absent from the map
    cleanup_tool_names.extend([tool_a, tool_b, tool_c])

    monkeypatch.setattr(
        mcp_tool_domains,
        "CHATBOT_TOOL_DOMAINS",
        {tool_a: "zzt_domain_one", tool_b: "zzt_domain_two"},
    )
    monkeypatch.setattr(
        svc,
        "_load_specs",
        lambda: (
            _FakeSpec(name=tool_a, description="a", path="/a"),
            _FakeSpec(name=tool_b, description="b", path="/b"),
            _FakeSpec(name=tool_c, description="c", path="/c"),
        ),
    )

    svc.sync_catalog(db)
    db.commit()

    rows = {
        row.tool_name: row.chatbot_domain
        for row in db.query(McpTool).filter(McpTool.tool_name.in_([tool_a, tool_b, tool_c]))
    }
    assert rows[tool_a] == "zzt_domain_one"
    assert rows[tool_b] == "zzt_domain_two"
    assert rows[tool_c] is None
