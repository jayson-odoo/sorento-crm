# MCP Tool Catalog — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the runtime MCP guard. Every MCP tool call must supply `contact_id` and `space_id`; the MCP server calls `POST /api/v1/system/mcp-access/check` (60 s TTL cache) and either forwards the request or returns a verbatim deny payload. Admins get two new read-only system pages: the MCP tool catalog (tool-centric, owner column) and the access log (recent decisions).

**Architecture:** Phase 3 of `docs/superpowers/specs/2026-05-01-mcp-tool-access-guard-design.md` (§7, §8) plus admin UI for configuration visibility. Decision logic from §8: `tool→owner agent→ON owner.is_active→contact lookup→ContactAgentAccess match`. Five decision branches all log to `mcp_access_log`. MCP server uses an asyncio-locked TTL dict keyed on `(tool_name, contact_id, space_id)`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest (backend). FastMCP, httpx, pytest (MCP). Next.js 15, TanStack Query, Tailwind v4, DataGrid (frontend).

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `sorento_crm_backend/app/schemas/user.py` | Add `McpAccessCheckIn`, `McpAccessCheckOut`, `McpAccessLogOut` |
| Create | `sorento_crm_backend/app/services/mcp_access_service.py` | `evaluate(...)` decision logic + audit-log write |
| Create | `sorento_crm_backend/app/api/v1/system/mcp_access.py` | `POST /api/v1/system/mcp-access/check`, `GET /api/v1/system/mcp-access/log` |
| Modify | `sorento_crm_backend/app/api/v1/system/__init__.py` | Mount `mcp_access.router` |
| Modify | `sorento_crm_backend/app/api/v1/system/mcp_tools.py` | Already exists — extend with admin list endpoint that includes `is_active=false` rows when caller asks (`include_inactive=true`) |
| Create | `sorento_crm_backend/tests/test_mcp_access_service.py` | 5 decision branches (allow + 4 deny variants) |
| Create | `sorento_crm_backend/tests/test_mcp_access_endpoint.py` | POST `/check` + GET `/log` integration |
| Create | `sorento_crm_mcp/sorento_crm_mcp/access_guard.py` | TTL cache + httpx call to backend |
| Modify | `sorento_crm_mcp/sorento_crm_mcp/server.py` | `_compile_tool` injects `contact_id`/`space_id`, calls guard, returns verbatim deny payload |
| Create | `sorento_crm_mcp/tests/test_access_guard.py` | Cache hit/miss; verbatim deny payloads; missing required params |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/page.tsx` | Admin catalog list (DataGrid) |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/components/McpToolsList.tsx` | Catalog list component |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/page.tsx` | Access-log read-only page |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/components/McpAccessLogList.tsx` | Log list component |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/services/mcpAdminService.ts` | API calls for the two admin pages |
| Create | `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/hooks/useMcpAdmin.ts` | TanStack Query hooks |

---

## Task 1: Backend schemas

**File:** `sorento_crm_backend/app/schemas/user.py`

- [ ] **Step 1:** Append at the end of `app/schemas/user.py`:

```python
# ---------------------------------------------------------------------------
# MCP guard (Phase 3)
# ---------------------------------------------------------------------------

class McpAccessCheckIn(BaseModel):
    tool_name: str
    contact_id: str        # respond_io_id
    space_id: str          # respond_workspace_id (UUID-as-str)


class McpAccessCheckOut(BaseModel):
    allowed: bool
    decision: str          # "allow" | "deny_no_access" | "deny_tool_unlinked"
                           # | "deny_unknown_tool" | "deny_unknown_contact"
    agent_name: str | None = None


class McpAccessLogOut(BaseModel):
    id: str
    tool_name: str
    contact_external_id: str | None = None
    respond_contact_id: str | None = None
    respond_workspace_id: str | None = None
    decision: str
    matched_agent_id: str | None = None
    ts: datetime

    model_config = ConfigDict(from_attributes=True)
```

If `datetime` is not imported at the top of `user.py`, add `from datetime import datetime`.

- [ ] **Step 2:** Smoke-import:

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
python -c "from app.schemas.user import McpAccessCheckIn, McpAccessCheckOut, McpAccessLogOut; print('schemas OK')"
```

- [ ] **Step 3:** Commit:

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_backend/app/schemas/user.py
git commit -m "feat(schemas): add McpAccess* Phase 3 schemas"
```

---

## Task 2: Access decision service

**Files:**
- Create: `sorento_crm_backend/app/services/mcp_access_service.py`
- Create: `sorento_crm_backend/tests/test_mcp_access_service.py`

- [ ] **Step 1: Write failing tests.** Create `sorento_crm_backend/tests/test_mcp_access_service.py`:

```python
"""Unit tests for app.services.mcp_access_service.evaluate (Phase 3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
)


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup(db):
    state = {"agents": [], "tools": [], "contacts": [], "links": [], "logs": []}
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
    db.commit()


def _agent(db, cleanup, name="Owner") -> AccessAgent:
    a = AccessAgent(
        id=str(uuid.uuid4()),
        code=f"AG-{uuid.uuid4().hex[:6]}",
        name=name,
        is_active=True,
    )
    db.add(a); db.flush()
    cleanup["agents"].append(a.id)
    return a


def _tool(db, cleanup, agent_id=None, is_active=True) -> McpTool:
    t = McpTool(
        id=str(uuid.uuid4()),
        tool_name=f"phase3_{uuid.uuid4().hex[:8]}",
        http_path="/api/v1/x",
        http_method="GET",
        is_active=is_active,
        last_seen_at=datetime.utcnow(),
        agent_id=agent_id,
    )
    db.add(t); db.flush()
    cleanup["tools"].append(t.id)
    return t


def _contact(db, cleanup, *, respond_io_id=None, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        respond_io_id=respond_io_id or f"rio_{uuid.uuid4().hex[:6]}",
        respond_workspace_id=workspace_id or str(uuid.uuid4()),
    )
    db.add(c); db.flush()
    cleanup["contacts"].append(c.id)
    return c


def _grant(db, cleanup, contact, agent, *, is_allowed=True) -> ContactAgentAccess:
    g = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=contact.id,
        respond_contact_phone=f"+60{uuid.uuid4().hex[:9]}",
        agent_id=agent.id,
        is_allowed=is_allowed,
    )
    db.add(g); db.flush()
    cleanup["links"].append(g.id)
    return g


def test_evaluate_allow(db, cleanup):
    from app.services.mcp_access_service import evaluate

    agent = _agent(db, cleanup, "Sales")
    tool = _tool(db, cleanup, agent_id=agent.id)
    contact = _contact(db, cleanup)
    _grant(db, cleanup, contact, agent)
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id=contact.respond_io_id, space_id=contact.respond_workspace_id)
    assert out.allowed is True
    assert out.decision == "allow"
    assert out.agent_name == "Sales"

    # Audit row written
    log = db.query(McpAccessLog).filter(McpAccessLog.tool_name == tool.tool_name).order_by(McpAccessLog.ts.desc()).first()
    assert log is not None
    cleanup["logs"].append(log.id)
    assert log.decision == "allow"
    assert log.matched_agent_id == agent.id


def test_evaluate_deny_unknown_tool(db, cleanup):
    from app.services.mcp_access_service import evaluate
    out = evaluate(db, tool_name=f"missing_{uuid.uuid4().hex[:6]}", contact_id="x", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_unknown_tool"
    assert out.agent_name is None


def test_evaluate_deny_tool_unlinked(db, cleanup):
    from app.services.mcp_access_service import evaluate
    tool = _tool(db, cleanup, agent_id=None)
    db.commit()
    out = evaluate(db, tool_name=tool.tool_name, contact_id="x", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_tool_unlinked"
    assert out.agent_name is None


def test_evaluate_deny_unknown_contact(db, cleanup):
    from app.services.mcp_access_service import evaluate
    agent = _agent(db, cleanup)
    tool = _tool(db, cleanup, agent_id=agent.id)
    db.commit()
    out = evaluate(db, tool_name=tool.tool_name, contact_id=f"missing_{uuid.uuid4().hex[:6]}", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_unknown_contact"
    assert out.agent_name == agent.name  # owner returned for UI message


def test_evaluate_deny_no_access(db, cleanup):
    from app.services.mcp_access_service import evaluate

    owner = _agent(db, cleanup, "Sales")
    other = _agent(db, cleanup, "Support")
    tool = _tool(db, cleanup, agent_id=owner.id)
    contact = _contact(db, cleanup)
    _grant(db, cleanup, contact, other)  # contact under Support, not Sales
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id=contact.respond_io_id, space_id=contact.respond_workspace_id)
    assert out.allowed is False
    assert out.decision == "deny_no_access"
    assert out.agent_name == "Sales"


def test_evaluate_deny_when_owner_agent_inactive(db, cleanup):
    from app.services.mcp_access_service import evaluate

    owner = _agent(db, cleanup)
    owner.is_active = False
    db.flush()
    tool = _tool(db, cleanup, agent_id=owner.id)
    db.commit()

    out = evaluate(db, tool_name=tool.tool_name, contact_id="anything", space_id=str(uuid.uuid4()))
    assert out.allowed is False
    assert out.decision == "deny_tool_unlinked"
```

- [ ] **Step 2: Run.** Should fail with ImportError.

```bash
pytest tests/test_mcp_access_service.py -v
```

- [ ] **Step 3: Implement service.** Create `sorento_crm_backend/app/services/mcp_access_service.py`:

```python
"""MCP guard decision service (Phase 3).

Single entry point: ``evaluate(db, tool_name, contact_id, space_id)``.
Writes one ``mcp_access_log`` row per call (every branch).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    McpAccessLog,
    McpTool,
    RespondContact,
)

logger = logging.getLogger(__name__)

Decision = Literal[
    "allow",
    "deny_no_access",
    "deny_tool_unlinked",
    "deny_unknown_tool",
    "deny_unknown_contact",
]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    decision: Decision
    agent_name: str | None


def _record_log(
    db: Session,
    *,
    tool_name: str,
    contact_external_id: str | None,
    respond_contact_id: str | None,
    respond_workspace_id: str | None,
    decision: Decision,
    matched_agent_id: str | None,
) -> None:
    db.add(
        McpAccessLog(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            contact_external_id=contact_external_id,
            respond_contact_id=respond_contact_id,
            respond_workspace_id=respond_workspace_id,
            decision=decision,
            matched_agent_id=matched_agent_id,
        )
    )
    db.flush()


def evaluate(
    db: Session, *, tool_name: str, contact_id: str, space_id: str
) -> AccessDecision:
    """Decide whether `(tool_name, contact_id, space_id)` may proceed.

    `contact_id` is the respond.io contact id (`respond_contacts.respond_io_id`).
    `space_id` is the respond workspace id (`respond_contacts.respond_workspace_id`).
    """
    tool = (
        db.query(McpTool)
        .filter(McpTool.tool_name == tool_name, McpTool.is_active.is_(True))
        .one_or_none()
    )
    if tool is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_unknown_tool",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_tool", agent_name=None)

    if tool.agent_id is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_tool_unlinked",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None)

    owner = (
        db.query(AccessAgent)
        .filter(AccessAgent.id == tool.agent_id, AccessAgent.is_active.is_(True))
        .one_or_none()
    )
    if owner is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_tool_unlinked",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None)

    contact = (
        db.query(RespondContact)
        .filter(
            RespondContact.respond_io_id == contact_id,
            RespondContact.respond_workspace_id == space_id,
        )
        .one_or_none()
    )
    if contact is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=None,
            respond_workspace_id=space_id,
            decision="deny_unknown_contact",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_unknown_contact", agent_name=owner.name)

    now = datetime.utcnow()
    granted = (
        db.query(ContactAgentAccess.id)
        .filter(
            ContactAgentAccess.respond_contact_id == contact.id,
            ContactAgentAccess.agent_id == owner.id,
            ContactAgentAccess.is_allowed.is_(True),
            or_(ContactAgentAccess.valid_to.is_(None), ContactAgentAccess.valid_to > now),
            or_(ContactAgentAccess.valid_from.is_(None), ContactAgentAccess.valid_from <= now),
        )
        .first()
    )
    if granted is None:
        _record_log(
            db,
            tool_name=tool_name,
            contact_external_id=contact_id,
            respond_contact_id=contact.id,
            respond_workspace_id=space_id,
            decision="deny_no_access",
            matched_agent_id=None,
        )
        return AccessDecision(allowed=False, decision="deny_no_access", agent_name=owner.name)

    _record_log(
        db,
        tool_name=tool_name,
        contact_external_id=contact_id,
        respond_contact_id=contact.id,
        respond_workspace_id=space_id,
        decision="allow",
        matched_agent_id=owner.id,
    )
    return AccessDecision(allowed=True, decision="allow", agent_name=owner.name)
```

- [ ] **Step 4: Re-run.** Expected: 6 passed.

```bash
pytest tests/test_mcp_access_service.py -v
```

- [ ] **Step 5: Commit.**

```bash
git add sorento_crm_backend/app/services/mcp_access_service.py sorento_crm_backend/tests/test_mcp_access_service.py
git commit -m "feat(services): add mcp_access_service.evaluate"
```

---

## Task 3: Access-check + log endpoints

**Files:**
- Create: `sorento_crm_backend/app/api/v1/system/mcp_access.py`
- Modify: `sorento_crm_backend/app/api/v1/system/__init__.py`
- Create: `sorento_crm_backend/tests/test_mcp_access_endpoint.py`

- [ ] **Step 1: Write failing tests.** Create `sorento_crm_backend/tests/test_mcp_access_endpoint.py`:

```python
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
    state = {"agents": [], "tools": [], "contacts": [], "links": [], "logs": []}
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
    db.commit()


def test_check_endpoint_allow(client, db, cleanup):
    if not API_KEY:
        pytest.skip("EXTERNAL_API_KEY not configured")
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
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        respond_workspace_id=str(uuid.uuid4()),
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
            "space_id": contact.respond_workspace_id,
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
```

- [ ] **Step 2: Run.** Should fail (404).

```bash
pytest tests/test_mcp_access_endpoint.py -v
```

- [ ] **Step 3: Implement endpoint.** Create `sorento_crm_backend/app/api/v1/system/mcp_access.py`:

```python
"""MCP access guard endpoints (Phase 3)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.access import McpAccessLog
from app.schemas.user import McpAccessCheckIn, McpAccessCheckOut, McpAccessLogOut
from app.services.mcp_access_service import evaluate

router = APIRouter(prefix="/mcp-access", tags=["mcp-access"])


@router.post("/check", response_model=McpAccessCheckOut)
def check_access(
    payload: McpAccessCheckIn,
    db: Session = Depends(get_db),
) -> McpAccessCheckOut:
    decision = evaluate(
        db,
        tool_name=payload.tool_name,
        contact_id=payload.contact_id,
        space_id=payload.space_id,
    )
    db.commit()
    return McpAccessCheckOut(
        allowed=decision.allowed,
        decision=decision.decision,
        agent_name=decision.agent_name,
    )


@router.get("/log", response_model=list[McpAccessLogOut])
def list_access_log(
    limit: int = Query(100, ge=1, le=1000),
    decision: Optional[str] = Query(None),
    tool_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[McpAccessLogOut]:
    q = db.query(McpAccessLog).order_by(McpAccessLog.ts.desc())
    if decision:
        q = q.filter(McpAccessLog.decision == decision)
    if tool_name:
        q = q.filter(McpAccessLog.tool_name == tool_name)
    rows = q.limit(limit).all()
    return [McpAccessLogOut.model_validate(r) for r in rows]
```

- [ ] **Step 4: Mount.** In `sorento_crm_backend/app/api/v1/system/__init__.py`, add `mcp_access,` to the imports tuple at the top, and `router.include_router(mcp_access.router, tags=["mcp-access"])` after the `mcp_tools` include.

- [ ] **Step 5: Re-run tests.** Expected: 4 passed (or 1 + 3 skipped if API key unset; source `.env` first).

```bash
export $(grep -v '^#' .env | xargs)
pytest tests/test_mcp_access_endpoint.py -v
```

- [ ] **Step 6: Commit.**

```bash
git add sorento_crm_backend/app/api/v1/system/mcp_access.py sorento_crm_backend/app/api/v1/system/__init__.py sorento_crm_backend/tests/test_mcp_access_endpoint.py
git commit -m "feat(api): POST /system/mcp-access/check + GET /log"
```

---

## Task 4: MCP server access guard

**Files:**
- Create: `sorento_crm_mcp/sorento_crm_mcp/access_guard.py`
- Modify: `sorento_crm_mcp/sorento_crm_mcp/server.py`
- Create: `sorento_crm_mcp/tests/test_access_guard.py`

- [ ] **Step 1: Write failing tests.** Create `sorento_crm_mcp/tests/test_access_guard.py`:

```python
"""Tests for sorento_crm_mcp.access_guard."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest


class _FakeClient:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, *, json: dict[str, Any]) -> "_FakeClient":
        self.calls.append((url, json))
        return self

    def raise_for_status(self):  # pragma: no cover
        return None

    def json(self) -> dict[str, Any]:
        return self.response


@pytest.mark.asyncio
async def test_check_access_caches_within_ttl(monkeypatch):
    from sorento_crm_mcp import access_guard

    fake = _FakeClient({"allowed": True, "decision": "allow", "agent_name": "Sales"})

    async def fake_post(self, url, *, json):  # noqa: A002
        fake.calls.append((url, json))
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: fake.response})()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    access_guard._cache.clear()  # type: ignore[attr-defined]

    g1 = await access_guard.check_access("tool_x", "rio_1", "ws_1", api_url="http://x", api_key="k")
    g2 = await access_guard.check_access("tool_x", "rio_1", "ws_1", api_url="http://x", api_key="k")
    assert g1.allowed is True
    assert g2.allowed is True
    assert len(fake.calls) == 1  # second call was cache hit


@pytest.mark.asyncio
async def test_check_access_deny_passes_through(monkeypatch):
    from sorento_crm_mcp import access_guard

    deny_response = {"allowed": False, "decision": "deny_no_access", "agent_name": "Sales"}

    async def fake_post(self, url, *, json):  # noqa: A002
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: deny_response})()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    access_guard._cache.clear()  # type: ignore[attr-defined]

    out = await access_guard.check_access("tool_y", "rio_2", "ws_2", api_url="http://x", api_key="k")
    assert out.allowed is False
    assert out.decision == "deny_no_access"
    assert out.agent_name == "Sales"


def test_deny_payload_for_no_access():
    from sorento_crm_mcp.access_guard import deny_payload, AccessDecision

    out = deny_payload(AccessDecision(allowed=False, decision="deny_no_access", agent_name="Sales"))
    parsed = json.loads(out)
    assert parsed["error"] == "ACCESS_DENIED"
    assert parsed["code"] == "CONTACT_NOT_AUTHORIZED"
    assert parsed["message"] == "you are not allowed to access this function: Sales"
    assert parsed["agent_name"] == "Sales"


def test_deny_payload_for_tool_unlinked():
    from sorento_crm_mcp.access_guard import deny_payload, AccessDecision

    out = deny_payload(AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None))
    parsed = json.loads(out)
    assert parsed["code"] == "TOOL_NOT_LINKED"
    assert parsed["message"] == "the required tools are not linked to any supported agents in the system"
    assert parsed["agent_name"] is None
```

Add `pytest-asyncio` to `sorento_crm_mcp/pyproject.toml` dev deps if not already present, and register the marker. (Verify before assuming.)

- [ ] **Step 2: Run.** Expected: 4 failures (module missing).

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_mcp
source .venv/bin/activate
pytest tests/test_access_guard.py -v
```

- [ ] **Step 3: Implement guard module.** Create `sorento_crm_mcp/sorento_crm_mcp/access_guard.py`:

```python
"""MCP access guard: backend round-trip + 60 s TTL cache.

Used by `_compile_tool` to validate (tool_name, contact_id, space_id) before
forwarding the underlying CRM request. Failed checks return a verbatim
JSON deny payload that the LLM caller surfaces to the end user.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx

CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    decision: str
    agent_name: Optional[str]


_cache: dict[tuple[str, str, str], tuple[float, AccessDecision]] = {}
_cache_lock = asyncio.Lock()


async def check_access(
    tool_name: str,
    contact_id: str,
    space_id: str,
    *,
    api_url: str,
    api_key: str,
    timeout: float = 5.0,
) -> AccessDecision:
    """Look up access decision for `(tool, contact, space)` against backend.

    Cache hits (within `CACHE_TTL_SECONDS`) skip the network call.
    """
    key = (tool_name, contact_id, space_id)
    now = time.monotonic()

    async with _cache_lock:
        entry = _cache.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{api_url.rstrip('/')}/api/v1/system/mcp-access/check",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"tool_name": tool_name, "contact_id": contact_id, "space_id": space_id},
        )
        resp.raise_for_status()
        body = resp.json()
    decision = AccessDecision(
        allowed=bool(body.get("allowed")),
        decision=str(body.get("decision", "deny_unknown_tool")),
        agent_name=body.get("agent_name"),
    )

    async with _cache_lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, decision)

    return decision


def deny_payload(decision: AccessDecision) -> str:
    """Build the verbatim JSON deny payload for a non-allowed decision."""
    if decision.decision == "deny_no_access" or decision.decision == "deny_unknown_contact":
        agent = decision.agent_name or "this agent"
        body = {
            "error": "ACCESS_DENIED",
            "code": "CONTACT_NOT_AUTHORIZED",
            "message": f"you are not allowed to access this function: {agent}",
            "agent_name": decision.agent_name,
        }
    elif decision.decision == "deny_tool_unlinked":
        body = {
            "error": "ACCESS_DENIED",
            "code": "TOOL_NOT_LINKED",
            "message": "the required tools are not linked to any supported agents in the system",
            "agent_name": None,
        }
    else:  # deny_unknown_tool
        body = {
            "error": "ACCESS_DENIED",
            "code": "UNKNOWN_TOOL",
            "message": "the required tools are not linked to any supported agents in the system",
            "agent_name": None,
        }
    return json.dumps(body)
```

- [ ] **Step 4: Re-run tests.** Expected: 4 passed.

```bash
pytest tests/test_access_guard.py -v
```

If `pytest-asyncio` is missing: install via `pip install pytest-asyncio` and add `asyncio_mode = "auto"` to `[tool.pytest.ini_options]` in `pyproject.toml`.

- [ ] **Step 5: Modify `_compile_tool` in `sorento_crm_mcp/sorento_crm_mcp/server.py`.**

In the `_compile_tool` function (around line 353), update the generated tool signature to include `contact_id` and `space_id` as required first parameters, and call `check_access` before the existing required-params check.

Add at the top of `server.py` (alongside other imports):

```python
from sorento_crm_mcp.access_guard import check_access, deny_payload
```

Inside `_compile_tool`, modify the signature construction. Locate the section (around line 364-373):

```python
    if pp_sig and qp_sig:
        sig = f"{pp_sig}, {qp_sig}"
    elif pp_sig:
        sig = pp_sig
    elif qp_sig:
        sig = qp_sig
    else:
        sig = ""
    if bp_sig:
        sig = f"{sig}, {bp_sig}" if sig else bp_sig
```

and prepend `contact_id` + `space_id` so every generated tool requires them:

```python
    guard_sig = "contact_id: str, space_id: str"
    if pp_sig and qp_sig:
        sig = f"{guard_sig}, {pp_sig}, {qp_sig}"
    elif pp_sig:
        sig = f"{guard_sig}, {pp_sig}"
    elif qp_sig:
        sig = f"{guard_sig}, {qp_sig}"
    else:
        sig = guard_sig
    if bp_sig:
        sig = f"{sig}, {bp_sig}"
```

Then locate the generated `code` template (the multi-line `code = (...)` block around line 384). Insert the guard call at the top of the generated function body, immediately after the `client = ctx.request_context.lifespan_context['client']` line. Replace the body opener:

```python
    code = (
        f"async def {fname}(ctx: Context, {sig}):\n"
        f"    client = ctx.request_context.lifespan_context['client']\n"
        f"    _settings = ctx.request_context.lifespan_context['settings']\n"
        f"    _decision = await _check_access(_spec.name, contact_id, space_id, api_url=_settings.crm_base_url, api_key=_settings.external_api_key)\n"
        f"    if not _decision.allowed:\n"
        f"        return _deny_payload(_decision)\n"
        f"    _pp = {pp_dict}\n"
        ...
    )
```

(Keep the rest of the body unchanged.) Add `_check_access`, `_deny_payload`, and `_settings` access to the `ns` dict that gets passed to `exec`:

```python
    ns: dict[str, Any] = {
        "Context": Context,
        "_normalize_query_value": _normalize_query_value,
        "_execute_tool_request": _execute_tool_request,
        "_execute_tool_request_with_body": _execute_tool_request_with_body,
        "_check_access": check_access,
        "_deny_payload": deny_payload,
        "json": json,
        "_spec": spec,
    }
```

Finally, in `create_mcp_app`'s `lifespan`, expose `settings` so the generated tool can read `crm_base_url` and `external_api_key`:

```python
    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
        c = CRMClient(settings)
        try:
            yield {"client": c, "settings": settings}
        finally:
            await c.aclose()
```

(Settings already lives in scope via the closure — just stash it in the lifespan dict.)

Verify `Settings` defines `crm_base_url`. If not, find the equivalent base-URL field name and substitute in the generated code. (Check `sorento_crm_mcp/settings.py`.)

- [ ] **Step 6: Smoke-import server.py.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_mcp
source .venv/bin/activate
python -c "from sorento_crm_mcp.server import create_mcp_app; print('server import OK')"
```

- [ ] **Step 7: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add sorento_crm_mcp/sorento_crm_mcp/access_guard.py sorento_crm_mcp/sorento_crm_mcp/server.py sorento_crm_mcp/tests/test_access_guard.py
git commit -m "feat(mcp): require contact_id+space_id and call access guard on every tool"
```

---

## Task 5: Admin UI — service + hooks

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/services/mcpAdminService.ts`
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/hooks/useMcpAdmin.ts`

- [ ] **Step 1: Write the service.** Create `mcpAdminService.ts`:

```ts
import { apiFetch, extractApiError } from '@/lib/api-client';

export interface McpToolCatalogRow {
  id: string;
  tool_name: string;
  description: string | null;
  module_key: string;
  current_agent_id: string | null;
  current_agent_name: string | null;
}

export interface McpAccessLogRow {
  id: string;
  tool_name: string;
  contact_external_id: string | null;
  respond_contact_id: string | null;
  respond_workspace_id: string | null;
  decision: string;
  matched_agent_id: string | null;
  ts: string;
}

export async function listMcpToolsCatalog(params: {
  is_active?: boolean;
  limit?: number;
} = {}): Promise<McpToolCatalogRow[]> {
  const usp = new URLSearchParams();
  usp.set('is_active', String(params.is_active ?? true));
  usp.set('limit', String(params.limit ?? 500));
  const response = await apiFetch(`/api/system/mcp-tools?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch MCP tools'));
  }
  return response.json();
}

export async function listMcpAccessLog(params: {
  decision?: string;
  tool_name?: string;
  limit?: number;
} = {}): Promise<McpAccessLogRow[]> {
  const usp = new URLSearchParams();
  if (params.decision) usp.set('decision', params.decision);
  if (params.tool_name) usp.set('tool_name', params.tool_name);
  usp.set('limit', String(params.limit ?? 200));
  const response = await apiFetch(`/api/system/mcp-access/log?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch MCP access log'));
  }
  return response.json();
}
```

- [ ] **Step 2: Write the hooks.** Create `useMcpAdmin.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { listMcpAccessLog, listMcpToolsCatalog } from '../services/mcpAdminService';

export function useMcpToolsCatalog(params: { is_active?: boolean } = {}) {
  return useQuery({
    queryKey: ['mcp-tools-catalog', params.is_active ?? true],
    queryFn: () => listMcpToolsCatalog({ is_active: params.is_active ?? true, limit: 500 }),
    staleTime: 1000 * 60,
  });
}

export function useMcpAccessLog(params: { decision?: string; tool_name?: string } = {}) {
  return useQuery({
    queryKey: ['mcp-access-log', params.decision ?? null, params.tool_name ?? null],
    queryFn: () => listMcpAccessLog({ ...params, limit: 200 }),
    staleTime: 1000 * 30,
  });
}
```

- [ ] **Step 3: Type-check.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

- [ ] **Step 4: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/services/mcpAdminService.ts' 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/hooks/useMcpAdmin.ts'
git commit -m "feat(fe): MCP admin service + hooks"
```

---

## Task 6: Admin UI — catalog list page

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/page.tsx`
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/components/McpToolsList.tsx`

- [ ] **Step 1:** Create `McpToolsList.tsx`:

```tsx
'use client';

import * as React from 'react';
import { useMcpToolsCatalog } from '../hooks/useMcpAdmin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusPill } from '@/components/common/StatusPill';

export function McpToolsList() {
  const [includeInactive, setIncludeInactive] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const { data, isLoading } = useMcpToolsCatalog({ is_active: !includeInactive });
  const rows = (data ?? []).filter((r) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      r.tool_name.toLowerCase().includes(q) ||
      r.module_key.toLowerCase().includes(q) ||
      (r.current_agent_name ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>MCP Tools Catalog</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <Input
            placeholder="Search tool / module / owner..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={includeInactive} onCheckedChange={(v) => setIncludeInactive(v)} />
            Show deactivated
          </label>
          <span className="ml-auto text-sm text-muted-foreground">{rows.length} tools</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[280px]">Tool</TableHead>
              <TableHead className="w-[140px]">Module</TableHead>
              <TableHead className="w-[200px]">Owner agent</TableHead>
              <TableHead className="w-[100px]">Status</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No tools match.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.tool_name}</TableCell>
                  <TableCell>{r.module_key || '—'}</TableCell>
                  <TableCell>
                    {r.current_agent_name ? (
                      r.current_agent_name
                    ) : (
                      <span className="text-amber-700">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusPill
                      label={r.current_agent_id ? 'Linked' : 'Orphan'}
                      colorHex={r.current_agent_id ? '#16a34a' : '#d97706'}
                    />
                  </TableCell>
                  <TableCell className="truncate" title={r.description ?? ''}>
                    {r.description ?? '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <p className="text-xs text-muted-foreground">
          To assign a tool to an access agent, edit the agent under{' '}
          <code className="font-mono">User Management → Access Agents</code> and select tools in
          the &quot;MCP Tools&quot; card.
        </p>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2:** Create `page.tsx`:

```tsx
import { McpToolsList } from './components/McpToolsList';

export default function McpToolsPage() {
  return (
    <div className="space-y-4 p-6">
      <McpToolsList />
    </div>
  );
}
```

- [ ] **Step 3: Type-check.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

- [ ] **Step 4: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/page.tsx' 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/components/McpToolsList.tsx'
git commit -m "feat(fe): admin MCP Tools catalog page"
```

---

## Task 7: Admin UI — access log page

**Files:**
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/page.tsx`
- Create: `sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/components/McpAccessLogList.tsx`

- [ ] **Step 1:** Create `McpAccessLogList.tsx`:

```tsx
'use client';

import * as React from 'react';
import { useMcpAccessLog } from '../../hooks/useMcpAdmin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusPill } from '@/components/common/StatusPill';

const DECISIONS = [
  { value: '__all__', label: 'All decisions' },
  { value: 'allow', label: 'Allow' },
  { value: 'deny_no_access', label: 'Deny — no access' },
  { value: 'deny_tool_unlinked', label: 'Deny — tool unlinked' },
  { value: 'deny_unknown_tool', label: 'Deny — unknown tool' },
  { value: 'deny_unknown_contact', label: 'Deny — unknown contact' },
];

const COLOR_BY_DECISION: Record<string, string> = {
  allow: '#16a34a',
  deny_no_access: '#dc2626',
  deny_tool_unlinked: '#d97706',
  deny_unknown_tool: '#6b7280',
  deny_unknown_contact: '#dc2626',
};

export function McpAccessLogList() {
  const [decision, setDecision] = React.useState<string>('__all__');
  const [toolName, setToolName] = React.useState('');
  const { data, isLoading } = useMcpAccessLog({
    decision: decision === '__all__' ? undefined : decision,
    tool_name: toolName.trim() || undefined,
  });
  const rows = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>MCP Access Log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={decision} onValueChange={setDecision}>
            <SelectTrigger className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DECISIONS.map((d) => (
                <SelectItem key={d.value} value={d.value}>
                  {d.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="Filter by exact tool_name..."
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
            className="max-w-sm"
          />
          <span className="ml-auto text-sm text-muted-foreground">{rows.length} entries</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[180px]">When</TableHead>
              <TableHead className="w-[260px]">Tool</TableHead>
              <TableHead className="w-[160px]">Decision</TableHead>
              <TableHead className="w-[200px]">Contact</TableHead>
              <TableHead>Workspace</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No log entries.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{new Date(r.ts).toLocaleString()}</TableCell>
                  <TableCell className="font-mono text-xs">{r.tool_name}</TableCell>
                  <TableCell>
                    <StatusPill
                      label={r.decision}
                      colorHex={COLOR_BY_DECISION[r.decision] ?? '#6b7280'}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.contact_external_id ?? '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.respond_workspace_id ?? '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2:** Create `page.tsx`:

```tsx
import { McpAccessLogList } from './components/McpAccessLogList';

export default function McpAccessLogPage() {
  return (
    <div className="space-y-4 p-6">
      <McpAccessLogList />
    </div>
  );
}
```

- [ ] **Step 3: Type-check.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend
npx tsc --noEmit -p .
```

- [ ] **Step 4: Commit.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git add 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/page.tsx' 'sorento_crm_frontend/app/(protected)/system-management/mcp-tools/access-log/components/McpAccessLogList.tsx'
git commit -m "feat(fe): admin MCP Access Log page"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run combined backend tests.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
pytest \
  tests/test_mcp_models.py \
  tests/test_mcp_tool_registry_service.py \
  tests/test_access_agent_mcp_tool_service.py \
  tests/test_mcp_tools_picker.py \
  tests/test_access_agent_mcp_tools_routes.py \
  tests/test_mcp_access_service.py \
  tests/test_mcp_access_endpoint.py \
  -v
```

Expected: 26 passed (16 from Phase 1+2 + 6 service + 4 endpoint). Note any SKIPs.

- [ ] **Step 2: Run MCP-side tests.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_mcp
source .venv/bin/activate
pytest tests/test_access_guard.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Branch summary.**

```bash
cd /Users/tehjayson/Documents/foundryx/sorento_crm
git log --oneline main..HEAD
```

Expected: 7 feature commits + 1 plan commit = 8 commits ahead.

- [ ] **Step 4: Confirm AccessAgent UI still works (no regression).** Open `http://localhost:3000/user-management/access-agents`, edit any agent, confirm the "MCP Tools" card from Phase 2 still loads and saves.

---

## Phase boundary

After Task 8 ships:

- Every MCP tool call requires `contact_id` + `space_id`.
- Backend enforces ownership and writes one audit row per call.
- 60 s in-memory cache on the MCP server reduces DB load.
- Admins have two read-only pages under System Management → MCP Tools (catalog + access log).
- Phase 2's AccessAgent UI is unchanged — it's still the only place to ASSIGN tools.

The MCP guard is live. End-to-end: respond.io → contact → access agent → tool → backend.

Future phases (out of scope here):
- Cache-bust endpoint for instant access revocation.
- Per-tool overrides (e.g. allow tool X to run unguarded for system contacts).
- Time-of-day / IP scoping.
