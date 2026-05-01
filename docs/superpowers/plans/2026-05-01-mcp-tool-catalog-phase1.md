# MCP Tool Catalog — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the MCP tool catalog into a `mcp_tools` table that auto-syncs from the code catalog (`sorento_crm_mcp.catalog.CATALOG` + `merged_catalog` per-module overlay) on backend startup and after every module upload. Add a `mcp_access_log` table that later phases will write to.

**Architecture:** Phase 1 of the design in `docs/superpowers/specs/2026-05-01-mcp-tool-access-guard-design.md`. Two new tables in the platform `base` module (alongside `access_agents` in `app/models/access.py`). One new service `mcp_tool_registry_service.sync_catalog(db)` is the single sync entry point — wired from `app/main.py::startup_event` and from `app/services/module_upload_service.py::install_uploaded_zip` after migrations run. **No enforcement, no admin UI, no access-check endpoint** — those are Phase 2 and 3.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Postgres, pytest. Backend imports `sorento_crm_mcp.catalog` directly (already available — confirmed: `python -c "from sorento_crm_mcp.catalog import CATALOG; ..."` returns 105 tools).

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `sorento_crm_backend/alembic/versions/158_mcp_tools_catalog.py` | DDL for `mcp_tools` + `mcp_access_log` |
| Modify | `sorento_crm_backend/app/models/access.py` | Add `McpTool`, `McpAccessLog` ORM models + `AccessAgent.mcp_tools` reverse relationship |
| Create | `sorento_crm_backend/app/services/mcp_tool_registry_service.py` | `sync_catalog(db) -> SyncReport`: idempotent upsert, deactivate stragglers, preserve `agent_id` |
| Modify | `sorento_crm_backend/app/main.py` (lines 96-117) | Add a try/except block in `startup_event` calling `sync_catalog` |
| Modify | `sorento_crm_backend/app/services/module_upload_service.py` | Call `sync_catalog` after `_run_alembic_upgrade` in `install_uploaded_zip` |
| Create | `sorento_crm_backend/tests/test_mcp_tool_registry_service.py` | Unit tests for `sync_catalog` |
| Create | `sorento_crm_backend/tests/test_mcp_models.py` | ORM model smoke test (insert + relationship roundtrip) |

Notes:
- Migration revision 157 is the latest (`157_lookup_sets`). New revision is `158_mcp_tools_catalog`, `down_revision = "157_lookup_sets"`.
- The Phase 1 schema includes the `agent_id` column even though Phase 2 is what populates it. This avoids a second migration in Phase 2 and keeps the `mcp_tools` shape stable across phases.

---

## Task 1: Alembic migration for `mcp_tools` and `mcp_access_log`

**Files:**
- Create: `sorento_crm_backend/alembic/versions/158_mcp_tools_catalog.py`

- [ ] **Step 1: Write the migration file**

```python
"""MCP tool catalog + per-call access log.

Revision ID: 158_mcp_tools_catalog
Revises: 157_lookup_sets
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "158_mcp_tools_catalog"
down_revision = "157_lookup_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tools",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("module_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("http_path", sa.Text(), nullable=False),
        sa.Column("http_method", sa.Text(), nullable=False, server_default="GET"),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("access_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tool_name", name="uq_mcp_tools_tool_name"),
    )
    op.create_index("ix_mcp_tools_module_key", "mcp_tools", ["module_key"])
    op.create_index("ix_mcp_tools_is_active", "mcp_tools", ["is_active"])
    op.create_index("ix_mcp_tools_agent_id", "mcp_tools", ["agent_id"])

    op.create_table(
        "mcp_access_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("contact_external_id", sa.Text(), nullable=True),
        sa.Column("respond_contact_id", sa.Text(), nullable=True),
        sa.Column("respond_workspace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("matched_agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mcp_access_log_ts", "mcp_access_log", ["ts"])
    op.create_index("ix_mcp_access_log_tool_name", "mcp_access_log", ["tool_name"])


def downgrade() -> None:
    op.drop_index("ix_mcp_access_log_tool_name", table_name="mcp_access_log")
    op.drop_index("ix_mcp_access_log_ts", table_name="mcp_access_log")
    op.drop_table("mcp_access_log")

    op.drop_index("ix_mcp_tools_agent_id", table_name="mcp_tools")
    op.drop_index("ix_mcp_tools_is_active", table_name="mcp_tools")
    op.drop_index("ix_mcp_tools_module_key", table_name="mcp_tools")
    op.drop_table("mcp_tools")
```

- [ ] **Step 2: Run migration up**

```bash
cd sorento_crm_backend
source venv/bin/activate
alembic upgrade head
```

Expected output line: `Running upgrade 157_lookup_sets -> 158_mcp_tools_catalog, MCP tool catalog + per-call access log.`

- [ ] **Step 3: Verify tables exist**

```bash
psql "$DATABASE_URL" -c '\d mcp_tools'
psql "$DATABASE_URL" -c '\d mcp_access_log'
```

Expected: both tables print with the columns from Step 1. Confirm `mcp_tools.agent_id` shows `references access_agents(id) on delete set null`.

- [ ] **Step 4: Round-trip verify down + up**

```bash
alembic downgrade -1
alembic upgrade head
```

Expected: clean down + up, no errors. `mcp_tools` and `mcp_access_log` are gone after `downgrade -1`, recreated after `upgrade head`.

- [ ] **Step 5: Commit**

```bash
git add sorento_crm_backend/alembic/versions/158_mcp_tools_catalog.py
git commit -m "feat(db): add mcp_tools + mcp_access_log tables"
```

---

## Task 2: ORM models — `McpTool`, `McpAccessLog`, `AccessAgent.mcp_tools`

**Files:**
- Modify: `sorento_crm_backend/app/models/access.py` (append after the existing `AgentTeamRoundRobinCursor` class around line 228)
- Create: `sorento_crm_backend/tests/test_mcp_models.py`

- [ ] **Step 1: Write the failing test**

Create `sorento_crm_backend/tests/test_mcp_models.py`:

```python
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


def test_mcp_tool_inserts_with_nullable_agent(db: Session):
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
    assert tool.agent_id is None
    assert tool.is_active is True


def test_access_agent_mcp_tools_relationship(db: Session):
    agent = _new_agent(db, code=f"REL-{uuid.uuid4().hex[:6]}")
    tool = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"rel_tool_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/rel",
        http_method="GET",
        agent_id=agent.id,
        last_seen_at=datetime.utcnow(),
    )
    db.add(tool)
    db.flush()
    db.refresh(agent)
    assert tool in agent.mcp_tools


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_models.py -v
```

Expected: ImportError — `cannot import name 'McpTool' from 'app.models.access'`.

- [ ] **Step 3: Add the ORM models**

Open `sorento_crm_backend/app/models/access.py`. After the last class (`AgentTeamRoundRobinCursor`, ends ~line 227), append:

```python
class McpTool(Base):
    """Persisted catalog row for one MCP tool. Synced from code catalog by
    `app.services.mcp_tool_registry_service.sync_catalog`.

    Ownership is N:1 — a tool belongs to at most one access agent (`agent_id`
    nullable). Sync NEVER overwrites `agent_id`; only admins do.
    """

    __tablename__ = "mcp_tools"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    module_key = Column(Text, nullable=False, default="", server_default="")
    http_path = Column(Text, nullable=False)
    http_method = Column(Text, nullable=False, default="GET", server_default="GET")
    agent_id = Column(
        UUID(as_uuid=False),
        ForeignKey("access_agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime(timezone=False), nullable=False)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    agent = relationship("AccessAgent", back_populates="mcp_tools")

    __table_args__ = (
        Index("ix_mcp_tools_module_key", "module_key"),
        Index("ix_mcp_tools_is_active", "is_active"),
        Index("ix_mcp_tools_agent_id", "agent_id"),
    )


class McpAccessLog(Base):
    """One row per MCP access decision. Phase 1 defines the table; Phase 3's
    access-check endpoint is the only writer.
    """

    __tablename__ = "mcp_access_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name = Column(Text, nullable=False)
    contact_external_id = Column(Text, nullable=True)
    respond_contact_id = Column(Text, nullable=True)
    respond_workspace_id = Column(UUID(as_uuid=False), nullable=True)
    decision = Column(Text, nullable=False)
    matched_agent_id = Column(UUID(as_uuid=False), nullable=True)
    ts = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_mcp_access_log_ts", "ts"),
        Index("ix_mcp_access_log_tool_name", "tool_name"),
    )
```

Then add the reverse relationship to `AccessAgent`. In the existing `AccessAgent` class (line 89), find:

```python
    contact_accesses = relationship("ContactAgentAccess", back_populates="agent")
    agent_teams = relationship("AgentTeam", back_populates="agent", cascade="all, delete-orphan")
```

and append (no cascade — the FK uses `ON DELETE SET NULL`, so deleting an agent releases its tools rather than deleting them):

```python
    mcp_tools = relationship("McpTool", back_populates="agent")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add sorento_crm_backend/app/models/access.py sorento_crm_backend/tests/test_mcp_models.py
git commit -m "feat(models): add McpTool + McpAccessLog ORM models"
```

---

## Task 3: `sync_catalog` service — happy-path insert

**Files:**
- Create: `sorento_crm_backend/app/services/mcp_tool_registry_service.py`
- Create: `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`

This task implements the simplest sync behavior: every `ToolSpec` in the live code catalog becomes a `mcp_tools` row with `is_active=true`. Tasks 4–6 layer on update, deactivate, and `agent_id` preservation behavior.

- [ ] **Step 1: Write the failing test**

Create `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_tool_registry_service.py::test_sync_catalog_inserts_new_tools -v
```

Expected: ImportError — `app.services.mcp_tool_registry_service` does not exist.

- [ ] **Step 3: Write the minimal service**

Create `sorento_crm_backend/app/services/mcp_tool_registry_service.py`:

```python
"""Sync the persisted MCP tool catalog (`mcp_tools` table) from the code
catalog (`sorento_crm_mcp.catalog.CATALOG` + `merged_catalog` per-module
overlay).

Contract:
- Idempotent. Re-running with the same code catalog leaves rows untouched
  except for `last_seen_at`.
- Sync NEVER touches `agent_id`. Admin-set ownership survives every sync.
- Tools that disappear from the code catalog are flipped to `is_active=false`,
  not deleted. They come back to `is_active=true` if re-introduced.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.access import McpTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncReport:
    added: int
    updated: int
    deactivated: int


def _load_specs() -> Iterable:
    """Return every `ToolSpec` from the code catalog (base + per-module overlay).

    Isolated as a function so tests can monkeypatch it without importing the
    real MCP catalog.
    """
    from sorento_crm_mcp.catalog import CATALOG
    from sorento_crm_mcp.module_loader import merged_catalog

    return tuple(merged_catalog(CATALOG))


def sync_catalog(db: Session) -> SyncReport:
    sync_started_at = datetime.utcnow()
    specs = list(_load_specs())

    added = 0
    updated = 0

    for spec in specs:
        existing = (
            db.query(McpTool).filter(McpTool.tool_name == spec.name).one_or_none()
        )
        if existing is None:
            db.add(
                McpTool(
                    id=str(uuid.uuid4()),
                    tool_name=spec.name,
                    description=spec.description,
                    module_key=getattr(spec, "module", "") or "",
                    http_path=spec.path,
                    http_method=spec.method,
                    is_active=True,
                    last_seen_at=sync_started_at,
                )
            )
            added += 1
            continue

        # Update mutable fields only. agent_id and id are NEVER touched.
        existing.description = spec.description
        existing.module_key = getattr(spec, "module", "") or ""
        existing.http_path = spec.path
        existing.http_method = spec.method
        existing.is_active = True
        existing.last_seen_at = sync_started_at
        updated += 1

    db.flush()

    deactivated = (
        db.query(McpTool)
        .filter(McpTool.last_seen_at < sync_started_at, McpTool.is_active.is_(True))
        .update({"is_active": False}, synchronize_session=False)
    )

    logger.info(
        "MCP tool catalog sync: added=%d updated=%d deactivated=%d",
        added,
        updated,
        deactivated,
    )
    return SyncReport(added=added, updated=updated, deactivated=deactivated)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_tool_registry_service.py::test_sync_catalog_inserts_new_tools -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add sorento_crm_backend/app/services/mcp_tool_registry_service.py sorento_crm_backend/tests/test_mcp_tool_registry_service.py
git commit -m "feat(services): add sync_catalog (insert path)"
```

---

## Task 4: `sync_catalog` — update path

**Files:**
- Modify: `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`

The service already implements update (Task 3 wrote it). This task adds the test that exercises the update path so regressions are caught.

- [ ] **Step 1: Write the failing test**

Append to `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_tool_registry_service.py::test_sync_catalog_updates_existing_tool -v
```

Expected: 1 passed (the update branch was already implemented in Task 3).

- [ ] **Step 3: Commit**

```bash
git add sorento_crm_backend/tests/test_mcp_tool_registry_service.py
git commit -m "test(services): cover sync_catalog update path"
```

---

## Task 5: `sync_catalog` — deactivate stragglers

**Files:**
- Modify: `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`

- [ ] **Step 1: Write the failing test**

Append to `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_tool_registry_service.py::test_sync_catalog_deactivates_removed_tools -v
```

Expected: 1 passed (already implemented in Task 3).

- [ ] **Step 3: Commit**

```bash
git add sorento_crm_backend/tests/test_mcp_tool_registry_service.py
git commit -m "test(services): cover sync_catalog deactivate + revive"
```

---

## Task 6: `sync_catalog` — preserve `agent_id` across syncs

**Files:**
- Modify: `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`

This guards the most important contract in the spec: admin-set ownership must survive every sync.

- [ ] **Step 1: Write the failing test**

Append to `sorento_crm_backend/tests/test_mcp_tool_registry_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_tool_registry_service.py::test_sync_catalog_preserves_agent_id -v
```

Expected: 1 passed (Task 3 explicitly never touches `agent_id`).

- [ ] **Step 3: Run full registry-service test file to confirm no regressions**

```bash
pytest tests/test_mcp_tool_registry_service.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add sorento_crm_backend/tests/test_mcp_tool_registry_service.py
git commit -m "test(services): cover sync_catalog preserves agent_id"
```

---

## Task 7: Wire `sync_catalog` into backend startup

**Files:**
- Modify: `sorento_crm_backend/app/main.py` (lines 96-117 — the `startup_event` function)

- [ ] **Step 1: Add the startup hook**

Open `sorento_crm_backend/app/main.py`. The current `startup_event` (line 96) ends with a try/except for the scheduler at line 117. Insert a new try/except **after** the scheduler block, before line 119's `@app.on_event("shutdown")`:

```python
    try:
        from app.database import SessionLocal
        from app.services.mcp_tool_registry_service import sync_catalog
        _db = SessionLocal()
        try:
            report = sync_catalog(_db)
            _db.commit()
            logging.info(
                "MCP tool catalog synced at startup: added=%d updated=%d deactivated=%d",
                report.added,
                report.updated,
                report.deactivated,
            )
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"Failed to sync MCP tool catalog at startup: {str(e)}", exc_info=True)
```

- [ ] **Step 2: Boot the server and verify the log line appears**

```bash
cd sorento_crm_backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
sleep 5
```

Then check the running server's log output. Expected line in stderr:

```
INFO:root:MCP tool catalog synced at startup: added=105 updated=0 deactivated=0
```

(Numbers differ on subsequent boots — `added=0 updated=105` after first run.) Stop the server:

```bash
kill %1
```

- [ ] **Step 3: Verify rows exist**

```bash
psql "$DATABASE_URL" -c "SELECT count(*) FROM mcp_tools WHERE is_active = true;"
```

Expected: count matches `len(merged_catalog(CATALOG))` (105 at the time of writing).

- [ ] **Step 4: Commit**

```bash
git add sorento_crm_backend/app/main.py
git commit -m "feat(main): sync MCP tool catalog on startup"
```

---

## Task 8: Wire `sync_catalog` into module upload pipeline

**Files:**
- Modify: `sorento_crm_backend/app/services/module_upload_service.py` (the `install_uploaded_zip` function around line 161)

The newly-extracted module's `mcp/tools.json` is on disk by the time `_run_alembic_upgrade` returns. We re-run sync so `merged_catalog` picks up the new slice and `mcp_tools` rows appear immediately, without waiting for the next backend restart.

- [ ] **Step 1: Locate the post-migration call site**

Read `sorento_crm_backend/app/services/module_upload_service.py` lines 247-260 (the section starting with `# 4) migrations`). The flow is:

```python
        # 4) migrations
        if run_migrations:
            mig_dir = backend_dest / "migrations"
            if mig_dir.is_dir():
                _run_alembic_upgrade()

        # 5) verify the new module's mappers actually configure.
        ...
        _verify_module_mappers(module_key, backend_dest)
```

The catalog sync goes **after** `_verify_module_mappers` returns successfully — we want to sync only if the module is fully importable, otherwise the next startup re-runs sync anyway.

- [ ] **Step 2: Add the sync call**

Find the line (currently around line 259):

```python
        _verify_module_mappers(module_key, backend_dest)
```

Append immediately below it (still inside the `try:` block, before any `return`):

```python
        # Re-sync the persisted MCP tool catalog so newly-extracted module
        # tools.json slices appear in `mcp_tools` without a backend restart.
        try:
            from app.database import SessionLocal
            from app.services.mcp_tool_registry_service import sync_catalog
            _sync_db = SessionLocal()
            try:
                sync_catalog(_sync_db)
                _sync_db.commit()
            finally:
                _sync_db.close()
        except Exception:
            logger.exception(
                "Module %s installed but MCP tool catalog sync failed; "
                "next backend restart will retry.",
                module_key,
            )
```

The wrapping try/except is intentional — sync failure must not roll back the upload (the next backend boot retries automatically).

- [ ] **Step 3: Manual smoke verification**

```bash
cd sorento_crm_backend
source venv/bin/activate

# Pre-count
psql "$DATABASE_URL" -c "SELECT count(*) FROM mcp_tools WHERE is_active = true;"

# Upload a module zip via the existing endpoint (curl example — adjust auth):
# curl -X POST http://localhost:8000/api/v1/system/modules/upload \
#   -H "X-API-Key: $EXTERNAL_API_KEY" \
#   -F "zip_file=@/tmp/example_module.zip"

# Post-count (rerun)
psql "$DATABASE_URL" -c "SELECT count(*) FROM mcp_tools WHERE is_active = true;"
```

Expected: post-count ≥ pre-count by the number of tools in the uploaded module's `mcp/tools.json` (zero if the module ships none).

This step is verification-only; it does not block the commit if no module zip is handy. In that case, defer to Phase 2 / Phase 3 integration tests for end-to-end coverage and rely on the inline log line emitted by `sync_catalog`.

- [ ] **Step 4: Commit**

```bash
git add sorento_crm_backend/app/services/module_upload_service.py
git commit -m "feat(modules): re-sync MCP tool catalog after module upload"
```

---

## Task 9: Final verification + integration commit

- [ ] **Step 1: Run the full Phase 1 test suite**

```bash
cd sorento_crm_backend
pytest tests/test_mcp_models.py tests/test_mcp_tool_registry_service.py -v
```

Expected: 7 passed (3 from Task 2 + 4 from Tasks 3–6). No skipped, no errors.

- [ ] **Step 2: Confirm Alembic head is `158_mcp_tools_catalog`**

```bash
alembic current
```

Expected output ends with `158_mcp_tools_catalog (head)`.

- [ ] **Step 3: Confirm catalog row count matches code catalog**

```bash
python - <<'PY'
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.module_loader import merged_catalog
print("code_catalog =", len(merged_catalog(CATALOG)))
PY

psql "$DATABASE_URL" -c "SELECT count(*) FROM mcp_tools WHERE is_active = true;"
```

Expected: both numbers equal.

- [ ] **Step 4: Confirm there are no `is_active=false` rows whose `tool_name` actually exists in the live code catalog (would indicate a sync bug)**

```bash
python - <<'PY'
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.module_loader import merged_catalog
from app.database import SessionLocal
from app.models.access import McpTool

names = {s.name for s in merged_catalog(CATALOG)}
db = SessionLocal()
inactive_but_present = (
    db.query(McpTool.tool_name)
    .filter(McpTool.is_active.is_(False), McpTool.tool_name.in_(names))
    .all()
)
db.close()
print("conflict_rows =", inactive_but_present)
assert not inactive_but_present, inactive_but_present
print("OK")
PY
```

Expected: `conflict_rows = []` then `OK`.

---

## Phase boundary

After Task 9 ships:

- `mcp_tools` populates on backend start and after every module upload.
- `mcp_access_log` exists but has no writer yet.
- `agent_id` is always NULL — no UI to set it.
- No enforcement on MCP tool calls.

**Phase 2** adds the `/api/v1/access-agents/{id}/mcp-tools` GET/PUT endpoints, the `/api/v1/system/mcp-tools` picker endpoint, and the AccessAgentForm UI card. **Phase 3** wires the MCP server guard. Each phase is its own plan.
