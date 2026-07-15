# MCP Tool Catalog — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins assign MCP tools to access agents (N:1 ownership). Backend exposes a tools-picker endpoint and per-agent GET/PUT routes; the AccessAgentForm grows an "MCP Tools" multi-select card that reassigns ownership in one transaction. **No MCP-side enforcement yet** — that's Phase 3.

**Architecture:** Phase 2 of `documentation/superpowers/specs/2026-05-01-mcp-tool-access-guard-design.md` (§9, §10). Single transaction PUT semantics: claim selected tools (`UPDATE mcp_tools SET agent_id=:id WHERE id IN :tool_ids`) and release deselected (`UPDATE ... SET agent_id=NULL WHERE agent_id=:id AND id NOT IN :tool_ids`). UI exposes `current_agent_*` fields on the picker so admins see ownership conflicts before saving.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic, pytest (backend). Next.js 15, React 19, TanStack Query, react-hook-form, Radix Popover + cmdk, Tailwind v4 (frontend).

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `sorento_crm_backend/app/schemas/user.py` | Add `McpToolOut`, `McpToolForAgentOut`, `AccessAgentMcpToolsUpdate` Pydantic schemas |
| Create | `sorento_crm_backend/app/services/access_agent_mcp_tool_service.py` | `list_tools_for_agent`, `set_tools_for_agent` (single-transaction reassign + release), `list_picker_tools` |
| Create | `sorento_crm_backend/app/api/v1/system/mcp_tools.py` | `GET /api/v1/system/mcp-tools` picker endpoint |
| Modify | `sorento_crm_backend/app/api/v1/system/__init__.py` | Mount `mcp_tools.router` alongside other system routers |
| Modify | `sorento_crm_backend/app/api/v1/user_management/access_agents.py` | `GET/PUT /access-agents/{agent_id}/mcp-tools` |
| Create | `sorento_crm_backend/tests/test_mcp_tools_picker.py` | Picker endpoint tests |
| Create | `sorento_crm_backend/tests/test_access_agent_mcp_tools.py` | GET / PUT ownership endpoint tests (incl. reassignment + release) |
| Create | `sorento_crm_frontend/components/common/SearchableMultiSelect.tsx` | Reusable multi-value variant of `SearchableSelect` (cmdk + Popover, checkbox indicator, chip display) |
| Modify | `sorento_crm_frontend/app/(protected)/user-management/access-agents/services/accessAgentService.ts` | Add `getAgentMcpTools`, `setAgentMcpTools`, `getMcpToolsForPicker` |
| Modify | `sorento_crm_frontend/app/(protected)/user-management/access-agents/hooks/useAccessAgents.ts` | Add `useAgentMcpTools`, `useMcpToolsForPicker` query hooks |
| Create | `sorento_crm_frontend/app/(protected)/user-management/access-agents/components/McpToolSelector.tsx` | Wraps `SearchableMultiSelect`, groups by `module_key`, surfaces `currently owned by …` warnings |
| Modify | `sorento_crm_frontend/app/(protected)/user-management/access-agents/components/AccessAgentForm.tsx` | Render new "MCP Tools" card after the Team Assignments card; integrate selector state and submit-time `setAgentMcpTools` call |

Notes:
- Backend additions live alongside existing access-agent code (no new module).
- Frontend additions live alongside existing access-agent components.
- We intentionally add `SearchableMultiSelect` as a reusable primitive (other features will need it; Phase 2 just happens to be the first consumer).

---

## Task 1: Backend schemas

**Files:**
- Modify: `sorento_crm_backend/app/schemas/user.py`

- [ ] **Step 1: Add Pydantic schemas at the end of `app/schemas/user.py`.**

```python
# ---------------------------------------------------------------------------
# MCP tool catalog (Phase 2 — AccessAgent ↔ Tool ownership)
# ---------------------------------------------------------------------------

class McpToolOut(BaseModel):
    """Picker row. `current_agent_*` populated when a tool is owned by some
    OTHER access agent so the UI can warn before reassignment."""
    id: str
    tool_name: str
    description: str | None = None
    module_key: str = ""
    current_agent_id: str | None = None
    current_agent_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class McpToolForAgentOut(BaseModel):
    """A row in `GET /access-agents/{id}/mcp-tools` (tools owned by THIS agent)."""
    id: str
    tool_name: str
    description: str | None = None
    module_key: str = ""

    model_config = ConfigDict(from_attributes=True)


class AccessAgentMcpToolsUpdate(BaseModel):
    """PUT /access-agents/{id}/mcp-tools body."""
    tool_ids: list[str]
```

If `ConfigDict` is not already imported at the top of the file, add it to the existing pydantic import.

- [ ] **Step 2: Smoke-import.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
python -c "from app.schemas.user import McpToolOut, McpToolForAgentOut, AccessAgentMcpToolsUpdate; print('schemas OK')"
```

Expected: prints `schemas OK`.

- [ ] **Step 3: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_backend/app/schemas/user.py
git commit -m "feat(schemas): add McpTool* Pydantic schemas for Phase 2"
```

---

## Task 2: Backend service — `access_agent_mcp_tool_service`

**Files:**
- Create: `sorento_crm_backend/app/services/access_agent_mcp_tool_service.py`
- Create: `sorento_crm_backend/tests/test_access_agent_mcp_tool_service.py`

- [ ] **Step 1: Write the failing tests.**

Create `sorento_crm_backend/tests/test_access_agent_mcp_tool_service.py`:

```python
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
    owned_by_b = _new_tool(db, agent_id=b.id)   # will be reassigned to a
    owned_by_a = _new_tool(db, agent_id=a.id)   # already owned, stays
    unowned = _new_tool(db, agent_id=None)      # claim
    will_release = _new_tool(db, agent_id=a.id) # NOT in new set, must release
    db.commit()

    set_tools_for_agent(db, a.id, [owned_by_b.id, owned_by_a.id, unowned.id])
    db.commit()

    db.refresh(owned_by_b)
    db.refresh(owned_by_a)
    db.refresh(unowned)
    db.refresh(will_release)
    assert owned_by_b.agent_id == a.id      # reassigned from b
    assert owned_by_a.agent_id == a.id      # unchanged
    assert unowned.agent_id == a.id         # claimed
    assert will_release.agent_id is None    # released


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
```

- [ ] **Step 2: Run them and confirm they fail with ImportError.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
pytest tests/test_access_agent_mcp_tool_service.py -v
```

Expected: import error / `cannot import name 'list_tools_for_agent'`.

- [ ] **Step 3: Write the service.**

Create `sorento_crm_backend/app/services/access_agent_mcp_tool_service.py`:

```python
"""AccessAgent ↔ McpTool ownership service (Phase 2).

Tools are N:1 to access agents — each `mcp_tools.agent_id` either points at
exactly one agent or is NULL.

`set_tools_for_agent` is replace-semantics in a single transaction:
1. Claim every tool in `tool_ids` for `agent_id` (overwrites any prior owner).
2. Release every tool currently owned by `agent_id` that's NOT in `tool_ids`.

Reassignment of a tool from one agent to another is logged with structured
fields (tool_id, from_agent_id, to_agent_id) so audits can reconstruct
ownership history.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.access import AccessAgent, McpTool

logger = logging.getLogger(__name__)


def list_tools_for_agent(db: Session, agent_id: str) -> list[McpTool]:
    """Return every active McpTool owned by `agent_id`, ordered by tool_name."""
    return (
        db.query(McpTool)
        .filter(McpTool.agent_id == agent_id, McpTool.is_active.is_(True))
        .order_by(McpTool.tool_name.asc())
        .all()
    )


def list_picker_tools(
    db: Session, *, only_active: bool = True, limit: int = 500
) -> list[dict[str, Any]]:
    """Return tools for the AccessAgentForm picker.

    Joins to `access_agents` so the UI can render "currently owned by X"
    warnings before the admin reassigns. Active tools only by default —
    inactive tools (deactivated by sync) are normally hidden.
    """
    q = (
        db.query(McpTool, AccessAgent.name)
        .outerjoin(AccessAgent, AccessAgent.id == McpTool.agent_id)
    )
    if only_active:
        q = q.filter(McpTool.is_active.is_(True))
    q = q.order_by(McpTool.module_key.asc(), McpTool.tool_name.asc()).limit(limit)

    rows: list[dict[str, Any]] = []
    for tool, agent_name in q.all():
        rows.append(
            {
                "id": tool.id,
                "tool_name": tool.tool_name,
                "description": tool.description,
                "module_key": tool.module_key or "",
                "current_agent_id": tool.agent_id,
                "current_agent_name": agent_name,
            }
        )
    return rows


def set_tools_for_agent(db: Session, agent_id: str, tool_ids: list[str]) -> None:
    """Replace `agent_id`'s tool ownership set.

    Single transaction:
    - Tools in `tool_ids` get `agent_id = :agent_id` (claim / reassign).
    - Tools currently owned by `:agent_id` not in `tool_ids` get `agent_id = NULL`.
    """
    # Snapshot prior owners for the tools we're about to claim, so we can log
    # reassignments. Read with the same session before the UPDATE.
    if tool_ids:
        prior = {
            t.id: t.agent_id
            for t in db.query(McpTool).filter(McpTool.id.in_(tool_ids)).all()
        }
    else:
        prior = {}

    # 1) Claim selected tools.
    if tool_ids:
        db.query(McpTool).filter(McpTool.id.in_(tool_ids)).update(
            {"agent_id": agent_id}, synchronize_session=False
        )

    # 2) Release tools previously owned by this agent that are no longer selected.
    release_q = db.query(McpTool).filter(McpTool.agent_id == agent_id)
    if tool_ids:
        release_q = release_q.filter(~McpTool.id.in_(tool_ids))
    release_q.update({"agent_id": None}, synchronize_session=False)

    # Structured log for reassignments (tool changed owner, not just claimed-from-NULL).
    for tid, old in prior.items():
        if old is not None and old != agent_id:
            logger.info(
                "mcp_tool_reassigned",
                extra={
                    "tool_id": tid,
                    "from_agent_id": old,
                    "to_agent_id": agent_id,
                },
            )
```

- [ ] **Step 4: Re-run tests.**

```bash
pytest tests/test_access_agent_mcp_tool_service.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_backend/app/services/access_agent_mcp_tool_service.py sorento_crm_backend/tests/test_access_agent_mcp_tool_service.py
git commit -m "feat(services): add access_agent_mcp_tool_service"
```

---

## Task 3: Backend picker endpoint `GET /api/v1/system/mcp-tools`

**Files:**
- Create: `sorento_crm_backend/app/api/v1/system/mcp_tools.py`
- Modify: `sorento_crm_backend/app/api/v1/system/__init__.py`
- Create: `sorento_crm_backend/tests/test_mcp_tools_picker.py`

- [ ] **Step 1: Write the failing test.**

Create `sorento_crm_backend/tests/test_mcp_tools_picker.py`:

```python
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
```

- [ ] **Step 2: Run.** Should fail (404 — endpoint doesn't exist).

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
pytest tests/test_mcp_tools_picker.py -v
```

- [ ] **Step 3: Implement the endpoint.**

Create `sorento_crm_backend/app/api/v1/system/mcp_tools.py`:

```python
"""System-level MCP tool catalog read endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import McpToolOut
from app.services.access_agent_mcp_tool_service import list_picker_tools

router = APIRouter(prefix="/mcp-tools", tags=["mcp-tools"])


@router.get("", response_model=list[McpToolOut])
def list_mcp_tools(
    is_active: bool = Query(True, description="When true, exclude tools removed from the code catalog."),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[McpToolOut]:
    rows = list_picker_tools(db, only_active=is_active, limit=limit)
    return [McpToolOut(**r) for r in rows]
```

- [ ] **Step 4: Mount the router.**

Open `sorento_crm_backend/app/api/v1/system/__init__.py`. Find the imports block at the top (lines 3-14):

```python
from app.api.v1.system import (
    import_logs,
    jobs,
    calendar,
    outgoing_mails,
    scheduled_tasks,
    numbering_rules,
    embeddings,
    ai_assistant,
    references,
    tool_capabilities,
)
```

Append `mcp_tools,` to the list. Then near the bottom of the file (after the existing `router.include_router(tool_capabilities.router, tags=["tool-capabilities"])` line), add:

```python
router.include_router(mcp_tools.router, tags=["mcp-tools"])
```

- [ ] **Step 5: Re-run the tests.**

```bash
pytest tests/test_mcp_tools_picker.py -v
```

Expected: 2 passed (or 1 passed + 1 skipped if `EXTERNAL_API_KEY` is unset in your shell — we keep that test guarded).

- [ ] **Step 6: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_backend/app/api/v1/system/mcp_tools.py sorento_crm_backend/app/api/v1/system/__init__.py sorento_crm_backend/tests/test_mcp_tools_picker.py
git commit -m "feat(api): GET /api/v1/system/mcp-tools picker endpoint"
```

---

## Task 4: Per-agent ownership endpoints (`GET / PUT`)

**Files:**
- Modify: `sorento_crm_backend/app/api/v1/user_management/access_agents.py`
- Create: `sorento_crm_backend/tests/test_access_agent_mcp_tools_routes.py`

- [ ] **Step 1: Write the failing tests.**

Create `sorento_crm_backend/tests/test_access_agent_mcp_tools_routes.py`:

```python
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
```

- [ ] **Step 2: Run.** Should fail with 404.

```bash
pytest tests/test_access_agent_mcp_tools_routes.py -v
```

- [ ] **Step 3: Implement the endpoints.**

Open `sorento_crm_backend/app/api/v1/user_management/access_agents.py`. Add new imports near the existing imports at the top (do NOT remove or reorder existing imports — only add):

```python
from app.schemas.user import (  # add to existing schemas import OR a new line
    AccessAgentMcpToolsUpdate,
    McpToolForAgentOut,
)
from app.services.access_agent_mcp_tool_service import (
    list_tools_for_agent,
    set_tools_for_agent,
)
```

Then append the two new routes at the end of the file (after the last existing route handler — currently the contact-access DELETE handler around line 245):

```python
@router.get("/{agent_id}/mcp-tools", response_model=list[McpToolForAgentOut])
def get_access_agent_mcp_tools(
    agent_id: str,
    db: Session = Depends(get_db),
) -> list[McpToolForAgentOut]:
    """Return active MCP tools owned by this access agent (Phase 2)."""
    rows = list_tools_for_agent(db, agent_id)
    return [McpToolForAgentOut.model_validate(r) for r in rows]


@router.put("/{agent_id}/mcp-tools", response_model=list[McpToolForAgentOut])
def set_access_agent_mcp_tools(
    agent_id: str,
    payload: AccessAgentMcpToolsUpdate,
    db: Session = Depends(get_db),
) -> list[McpToolForAgentOut]:
    """Replace this agent's MCP tool ownership set in one transaction.

    Tools in `payload.tool_ids` are claimed for this agent (overwriting any
    prior owner). Tools currently owned by this agent that are NOT in the
    new set get `agent_id = NULL` (released).
    """
    set_tools_for_agent(db, agent_id, list(payload.tool_ids))
    db.commit()
    rows = list_tools_for_agent(db, agent_id)
    return [McpToolForAgentOut.model_validate(r) for r in rows]
```

- [ ] **Step 4: Re-run tests.**

```bash
pytest tests/test_access_agent_mcp_tools_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_backend/app/api/v1/user_management/access_agents.py sorento_crm_backend/tests/test_access_agent_mcp_tools_routes.py
git commit -m "feat(api): GET/PUT /access-agents/{id}/mcp-tools"
```

---

## Task 5: Frontend `SearchableMultiSelect` primitive

**File:**
- Create: `sorento_crm_frontend/components/common/SearchableMultiSelect.tsx`

A reusable multi-value variant of `SearchableSelect`. Same Radix Popover + cmdk Command pattern; selection state is a `string[]` rather than a single `string`; trigger renders comma-joined chip count.

- [ ] **Step 1: Write the component.**

Create `sorento_crm_frontend/components/common/SearchableMultiSelect.tsx`:

```tsx
'use client';

import * as React from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

export type SearchableMultiSelectOption = {
  value: string;
  label: string;
  /** Optional grouping header (renders one CommandGroup per distinct group). */
  group?: string;
  /** Free-text used by the fuzzy filter; falls back to label. */
  searchText?: string;
  /** Optional secondary line under the label. */
  description?: string;
  /** When set, render a small badge after the label (e.g. "owned by X"). */
  badgeText?: string;
};

export type SearchableMultiSelectProps = {
  value: string[];
  onChange: (value: string[]) => void;
  options: SearchableMultiSelectOption[];
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Format the trigger label given the current selection. Defaults to "{count} selected". */
  renderTriggerLabel?: (selected: SearchableMultiSelectOption[]) => React.ReactNode;
};

export function SearchableMultiSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  triggerClassName,
  renderTriggerLabel,
}: SearchableMultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const selectedSet = React.useMemo(() => new Set(value), [value]);
  const selectedOptions = React.useMemo(
    () => options.filter((o) => selectedSet.has(o.value)),
    [options, selectedSet],
  );

  const grouped = React.useMemo(() => {
    const map = new Map<string, SearchableMultiSelectOption[]>();
    for (const opt of options) {
      const key = opt.group ?? '';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(opt);
    }
    return Array.from(map.entries());
  }, [options]);

  const toggle = (v: string) => {
    if (selectedSet.has(v)) {
      onChange(value.filter((x) => x !== v));
    } else {
      onChange([...value, v]);
    }
  };

  const triggerLabel = renderTriggerLabel
    ? renderTriggerLabel(selectedOptions)
    : selectedOptions.length === 0
      ? placeholder
      : `${selectedOptions.length} selected`;

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none',
            'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
            'data-[state=open]:border-ring',
            disabled && 'cursor-not-allowed opacity-50',
            triggerClassName,
          )}
        >
          <span className={cn('truncate', selectedOptions.length === 0 && 'text-muted-foreground')}>
            {triggerLabel}
          </span>
          <ChevronDown className="size-4 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className={cn('w-[--radix-popover-trigger-width] p-0', className)} align="start">
        <Command shouldFilter>
          <CommandInput placeholder="Search..." />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            {grouped.map(([groupKey, opts]) => (
              <CommandGroup key={groupKey || '__ungrouped__'} heading={groupKey || undefined}>
                {opts.map((opt) => {
                  const isSelected = selectedSet.has(opt.value);
                  return (
                    <CommandItem
                      key={opt.value}
                      value={opt.searchText ?? `${opt.label} ${opt.description ?? ''}`}
                      onSelect={() => toggle(opt.value)}
                      className="flex items-start gap-2"
                    >
                      <div className="mt-0.5 flex size-4 items-center justify-center rounded-sm border border-input">
                        {isSelected ? <Check className="size-3" /> : null}
                      </div>
                      <div className="flex flex-1 flex-col">
                        <div className="flex items-center gap-2">
                          <span>{opt.label}</span>
                          {opt.badgeText ? (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                              {opt.badgeText}
                            </span>
                          ) : null}
                        </div>
                        {opt.description ? (
                          <span className="truncate text-xs text-muted-foreground" title={opt.description}>
                            {opt.description}
                          </span>
                        ) : null}
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
```

- [ ] **Step 2: Smoke-build with TypeScript to confirm types compile.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

Expected: no errors that mention `SearchableMultiSelect.tsx`. Pre-existing project errors, if any, are unchanged.

- [ ] **Step 3: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_frontend/components/common/SearchableMultiSelect.tsx
git commit -m "feat(ui): add SearchableMultiSelect primitive"
```

---

## Task 6: Frontend service + hooks

**Files:**
- Modify: `sorento_crm_frontend/app/(protected)/user-management/access-agents/services/accessAgentService.ts`
- Modify: `sorento_crm_frontend/app/(protected)/user-management/access-agents/hooks/useAccessAgents.ts`

- [ ] **Step 1: Add service functions.**

Append to `accessAgentService.ts` (after the existing `setAgentTeams` function):

```ts
export interface McpToolForAgent {
  id: string;
  tool_name: string;
  description: string | null;
  module_key: string;
}

export interface McpToolPickerRow extends McpToolForAgent {
  current_agent_id: string | null;
  current_agent_name: string | null;
}

export async function getMcpToolsForPicker(): Promise<McpToolPickerRow[]> {
  const response = await apiFetch(
    '/api/system/mcp-tools?is_active=true&limit=500',
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch MCP tools'));
  }
  return response.json();
}

export async function getAgentMcpTools(agentId: string): Promise<McpToolForAgent[]> {
  const response = await apiFetch(
    `/api/user-management/access-agents/${agentId}/mcp-tools`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch agent MCP tools'));
  }
  return response.json();
}

export async function setAgentMcpTools(
  agentId: string,
  toolIds: string[],
): Promise<McpToolForAgent[]> {
  const response = await apiFetch(
    `/api/user-management/access-agents/${agentId}/mcp-tools`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_ids: toolIds }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to set agent MCP tools'));
  }
  return response.json();
}
```

- [ ] **Step 2: Add hooks.**

Append to `hooks/useAccessAgents.ts` (after the existing `useTeams` hook):

```ts
import {
  getAgentMcpTools,
  getMcpToolsForPicker,
  setAgentMcpTools,
} from '../services/accessAgentService';

export function useAgentMcpTools(agentId: string | null) {
  return useQuery({
    queryKey: ['agent-mcp-tools', agentId],
    queryFn: () => {
      if (!agentId) throw new Error('Agent ID is required');
      return getAgentMcpTools(agentId);
    },
    enabled: !!agentId,
    retry: 1,
  });
}

export function useMcpToolsForPicker() {
  return useQuery({
    queryKey: ['mcp-tools-picker'],
    queryFn: () => getMcpToolsForPicker(),
    staleTime: 1000 * 60 * 2,
    retry: 1,
  });
}

export function useSetAgentMcpTools() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, toolIds }: { agentId: string; toolIds: string[] }) =>
      setAgentMcpTools(agentId, toolIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent-mcp-tools', variables.agentId] });
      queryClient.invalidateQueries({ queryKey: ['mcp-tools-picker'] });
      toast.success('MCP tools updated');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to set MCP tools'),
  });
}
```

If the file already imports from `../services/accessAgentService` near the top, **merge** the new imports into the existing import block instead of adding a second one. Verify by reading the top of the file.

- [ ] **Step 3: Smoke-build.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

Expected: no new errors.

- [ ] **Step 4: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_frontend/app/\(protected\)/user-management/access-agents/services/accessAgentService.ts sorento_crm_frontend/app/\(protected\)/user-management/access-agents/hooks/useAccessAgents.ts
git commit -m "feat(fe): MCP tools service + hooks for AccessAgent"
```

---

## Task 7: `McpToolSelector` component + AccessAgentForm card

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/user-management/access-agents/components/McpToolSelector.tsx`
- Modify: `sorento_crm_frontend/app/(protected)/user-management/access-agents/components/AccessAgentForm.tsx`

- [ ] **Step 1: Write the selector.**

Create `McpToolSelector.tsx`:

```tsx
'use client';

import * as React from 'react';
import {
  SearchableMultiSelect,
  SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { useMcpToolsForPicker } from '../hooks/useAccessAgents';

export interface McpToolSelectorProps {
  /** Currently selected tool ids. */
  value: string[];
  onChange: (next: string[]) => void;
  /** Agent currently being edited; tools owned by this agent are NOT badged
   *  (only tools owned by some OTHER agent show the "currently owned" warning). */
  currentAgentId?: string;
  disabled?: boolean;
}

export function McpToolSelector({
  value,
  onChange,
  currentAgentId,
  disabled,
}: McpToolSelectorProps) {
  const { data, isLoading } = useMcpToolsForPicker();
  const rows = data ?? [];

  const options: SearchableMultiSelectOption[] = React.useMemo(() => {
    return rows.map((r) => {
      const ownedElsewhere =
        r.current_agent_id != null && r.current_agent_id !== currentAgentId;
      return {
        value: r.id,
        label: r.tool_name,
        group: r.module_key || 'Unbound',
        searchText: `${r.tool_name} ${r.module_key} ${r.description ?? ''}`,
        description: r.description ?? undefined,
        badgeText: ownedElsewhere
          ? `currently owned by ${r.current_agent_name ?? 'another agent'} — selecting will reassign`
          : undefined,
      };
    });
  }, [rows, currentAgentId]);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading MCP tools...</p>;
  }
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No MCP tools registered yet — modules with{' '}
        <code className="font-mono text-xs">mcp/tools.json</code> populate this list on upload.
      </p>
    );
  }
  return (
    <SearchableMultiSelect
      value={value}
      onChange={onChange}
      options={options}
      placeholder="Select MCP tools..."
      emptyMessage="No MCP tools match."
      disabled={disabled}
    />
  );
}
```

- [ ] **Step 2: Wire into AccessAgentForm.**

Open `AccessAgentForm.tsx`. Add new imports next to the existing hooks import (line 31):

```tsx
import { useAgentMcpTools, useSetAgentMcpTools } from '../hooks/useAccessAgents';
import { McpToolSelector } from './McpToolSelector';
```

Inside the `AccessAgentForm` function body (after the existing `assignmentGroups` state around line 66), add MCP tools state:

```tsx
const { data: agentMcpToolsData } = useAgentMcpTools(isEditMode ? accessAgentId ?? null : null);
const setAgentMcpToolsMutation = useSetAgentMcpTools();
const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
const [initialToolIds, setInitialToolIds] = useState<string[]>([]);

useEffect(() => {
  if (agentMcpToolsData) {
    const ids = agentMcpToolsData.map((t) => t.id);
    setSelectedToolIds(ids);
    setInitialToolIds(ids);
  }
}, [agentMcpToolsData]);
```

In the `onSubmit` handler (around line 132), after the existing `await setAgentTeams(...)` call inside the edit branch, append:

```tsx
        // Persist MCP tool ownership changes. Confirm reassignment if any
        // selected tool is currently owned by a different agent (the picker's
        // badge already showed which ones).
        const removedIds = initialToolIds.filter((id) => !selectedToolIds.includes(id));
        const addedIds = selectedToolIds.filter((id) => !initialToolIds.includes(id));
        if (addedIds.length > 0 || removedIds.length > 0) {
          await setAgentMcpToolsMutation.mutateAsync({
            agentId: accessAgentId,
            toolIds: selectedToolIds,
          });
          setInitialToolIds(selectedToolIds);
        }
```

Render the new card. After the existing `Team Assignments` card's closing `</Card>` (around line 451), insert (still inside the parent fragment, before the cancel/submit buttons):

```tsx
        {isEditMode && accessAgentId && (
          <Card>
            <CardHeader>
              <CardTitle>MCP Tools</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Tools selected here will require an authorised contact under this access agent
                before they can be invoked.
              </p>
              <McpToolSelector
                value={selectedToolIds}
                onChange={setSelectedToolIds}
                currentAgentId={accessAgentId}
                disabled={isLoading}
              />
            </CardContent>
          </Card>
        )}
```

Update the `isLoading` declaration (around line 180) to include the new mutation:

```tsx
const isLoading =
  createMutation.isPending ||
  updateMutation.isPending ||
  setAgentMcpToolsMutation.isPending;
```

- [ ] **Step 3: Smoke-build.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

Expected: no new errors. If new errors point at unrelated files, leave them — only ensure the new files don't introduce errors.

- [ ] **Step 4: Manual UI sanity check.**

Run the frontend dev server (only if a backend is reachable — port 3000 must be free):

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npm run dev
```

Open `http://localhost:3000/user-management/access-agents`, edit any access agent, scroll past the Team Assignments card. Expected: a new "MCP Tools" card with a multi-select. Selecting / deselecting + Save should hit the PUT route (verify via browser devtools network tab) and toast "MCP tools updated".

If the dev server can't be started in your environment (port in use, backend unreachable), skip this step and rely on the type-check + earlier integration tests.

- [ ] **Step 5: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_frontend/app/\(protected\)/user-management/access-agents/components/McpToolSelector.tsx \
        sorento_crm_frontend/app/\(protected\)/user-management/access-agents/components/AccessAgentForm.tsx
git commit -m "feat(fe): add MCP Tools card to AccessAgentForm"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run all Phase 2 backend tests together.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
pytest \
  tests/test_access_agent_mcp_tool_service.py \
  tests/test_mcp_tools_picker.py \
  tests/test_access_agent_mcp_tools_routes.py \
  -v
```

Expected: 9 passed (4 service + 2 picker + 3 route). The two picker / 3 route tests may emit `SKIPPED` if `EXTERNAL_API_KEY` is unset — that's acceptable but mention it in the report.

- [ ] **Step 2: Confirm Phase 1 tests still pass.**

```bash
pytest tests/test_mcp_models.py tests/test_mcp_tool_registry_service.py -v
```

Expected: 7 passed (no regression from Phase 2 changes).

- [ ] **Step 3: Confirm DB invariants hold.**

```bash
python - <<'PY'
from app.database import SessionLocal
from app.models.access import McpTool
db = SessionLocal()
try:
    total = db.query(McpTool).count()
    active = db.query(McpTool).filter(McpTool.is_active.is_(True)).count()
    owned = db.query(McpTool).filter(McpTool.agent_id.isnot(None)).count()
    print(f"total={total} active={active} owned={owned}")
finally:
    db.close()
PY
```

Expected: prints the totals. `owned` should reflect any test-leftover ownership that wasn't cleaned up — if non-zero and surprising, investigate (test fixtures may have leaked).

- [ ] **Step 4: Branch summary.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git log --oneline main..HEAD
```

Expected: 7 commits — one per task (1-7), Task 8 is verification-only.

---

## Phase boundary

After Task 8 ships:

- Admins can assign / reassign / release MCP tools per access agent through the UI.
- `mcp_tools.agent_id` is populated for every selected (tool, agent) pair.
- Reassignment from one agent to another is logged with structured fields.
- **No enforcement on MCP traffic yet.** The MCP server still runs every tool for any caller with the X-API-Key.
- `mcp_access_log` is still empty (Phase 3 is the only writer).

**Phase 3** wires the MCP server guard: `_compile_tool` injects `contact_id` + `space_id`, calls `POST /api/v1/system/mcp-access/check`, returns the verbatim deny payloads on failure. Each phase is its own plan.
