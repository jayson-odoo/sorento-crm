# Per-Contact Portal Link Action — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-01-contact-portal-link-action-design.md`

**Goal:** Add an admin "Portal link" action on each contact (detail page, list row, SLA tracking detail) that opens a modal showing a reusable 7-day portal URL with copy / open / QR / send-via-Respond.io options.

**Architecture:**
- Backend: extend `PortalService` with `get_or_mint_token` (reuse latest live token) and `send_link_via_respond_io` (mints/reuses + sends through `RespondClient`). Add two JWT routes on `/api/v1/user-management/contacts/{id}` gated by new permission `user_management.contacts.portal_link`. Server resolves `space_id` from `RespondContact.workspace_id → respond_workspaces.space_id`.
- Frontend: shared `PortalLinkButton` + `PortalLinkDialog` (qrcode.react). Wired into contact detail toolbar, contacts list row actions, and SLA tracking detail gear menu. Permission-gated via `useHasPermission`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend); Next.js 15 / React 19 + react-query + sonner + qrcode.react (frontend); pytest + vitest.

---

## File Structure

**Backend (created/modified):**
- Modify `sorento_crm_backend/app/rbac/permission_registry.py` — append new permission slug
- Create `sorento_crm_backend/alembic/versions/160_contact_portal_link_permission.py` — sync new perm
- Modify `sorento_crm_backend/app/services/portal_service.py` — add `get_or_mint_token`, `send_link_via_respond_io`, `_build_send_message_text`
- Modify `sorento_crm_backend/app/api/v1/user_management/contacts.py` — add 2 routes
- Create `sorento_crm_backend/tests/test_portal_link_action.py` — service + endpoint tests
- Create `sorento_crm_backend/tests/test_contact_portal_link_permission.py` — registry test

**Frontend (created/modified):**
- Modify `sorento_crm_frontend/package.json` — add `qrcode.react`
- Create `sorento_crm_frontend/services/contactPortalLinkService.ts`
- Create `sorento_crm_frontend/hooks/useContactPortalLink.ts`
- Create `sorento_crm_frontend/components/contacts/PortalLinkDialog.tsx`
- Create `sorento_crm_frontend/components/contacts/PortalLinkButton.tsx`
- Create `sorento_crm_frontend/components/contacts/PortalLinkDialog.test.tsx`
- Modify `sorento_crm_frontend/app/(protected)/user-management/contacts/[id]/page.tsx` — add action in toolbar
- Modify `sorento_crm_frontend/app/(protected)/user-management/contacts/components/ContactsList.tsx` — add row action
- Modify `sorento_crm_frontend/app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx` — add menu item

---

## Task 1: Register new permission slug + Alembic migration

**Files:**
- Modify: `sorento_crm_backend/app/rbac/permission_registry.py`
- Create: `sorento_crm_backend/alembic/versions/160_contact_portal_link_permission.py`
- Create: `sorento_crm_backend/tests/test_contact_portal_link_permission.py`

- [ ] **Step 1.1: Write the failing registry test**

Create `sorento_crm_backend/tests/test_contact_portal_link_permission.py`:

```python
"""Verify the contact portal link permission slug is registered."""
from app.rbac.permission_registry import PERMISSION_REGISTRY


def test_contact_portal_link_permission_registered() -> None:
    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert "user_management.contacts.portal_link" in slugs


def test_contact_portal_link_permission_has_human_label() -> None:
    entry = next(
        (e for e in PERMISSION_REGISTRY if e["slug"] == "user_management.contacts.portal_link"),
        None,
    )
    assert entry is not None
    assert entry["name"] == "Get contact portal link"
    assert entry["description"]
```

- [ ] **Step 1.2: Run test — expect FAIL**

```bash
cd sorento_crm_backend && pytest tests/test_contact_portal_link_permission.py -q
```

Expected: 2 failures (`AssertionError` — slug not in registry).

- [ ] **Step 1.3: Add permission to registry**

In `sorento_crm_backend/app/rbac/permission_registry.py`, locate the `# User Management` block (the `PERMISSION_REGISTRY.extend([...])` for settings/logs/account around line 38-43). Immediately AFTER that `extend([...])` block, append:

```python
PERMISSION_REGISTRY.append({
    "slug": "user_management.contacts.portal_link",
    "name": "Get contact portal link",
    "description": "Generate or send a user-submission portal link for a respond contact.",
})
```

- [ ] **Step 1.4: Run test — expect PASS**

```bash
pytest tests/test_contact_portal_link_permission.py -q
```

Expected: 2 passed.

- [ ] **Step 1.5: Create Alembic migration**

Create `sorento_crm_backend/alembic/versions/160_contact_portal_link_permission.py`:

```python
"""Sync RBAC: user_management.contacts.portal_link permission.

Revision ID: 160_contact_portal_link
Revises: 159_user_submission_portal
Create Date: 2026-05-01
"""

from alembic import op
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "160_contact_portal_link"
down_revision = "159_user_submission_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    pass
```

- [ ] **Step 1.6: Verify migration parses (offline check)**

```bash
cd sorento_crm_backend && python -c "import importlib.util,sys; spec=importlib.util.spec_from_file_location('m','alembic/versions/160_contact_portal_link_permission.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print(mod.revision, mod.down_revision)"
```

Expected: `160_contact_portal_link 159_user_submission_portal`

- [ ] **Step 1.7: Apply migration locally**

```bash
cd sorento_crm_backend && source venv/bin/activate && alembic upgrade head
```

Expected: `Running upgrade 159_user_submission_portal -> 160_contact_portal_link, ...` and exit 0. (Skip if your environment already has all perms synced.)

- [ ] **Step 1.8: Commit**

```bash
git add sorento_crm_backend/app/rbac/permission_registry.py \
        sorento_crm_backend/alembic/versions/160_contact_portal_link_permission.py \
        sorento_crm_backend/tests/test_contact_portal_link_permission.py
git commit -m "feat(rbac): add user_management.contacts.portal_link permission"
```

---

## Task 2: PortalService.get_or_mint_token

**Files:**
- Modify: `sorento_crm_backend/app/services/portal_service.py`
- Create: `sorento_crm_backend/tests/test_portal_link_action.py`

- [ ] **Step 2.1: Write failing service tests**

Create `sorento_crm_backend/tests/test_portal_link_action.py`:

```python
"""Tests for PortalService reuse logic + send-link-via-respond-io flow."""
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.models.access import RespondContact, RespondWorkspace
from app.models.portal import PortalToken
from app.services.portal_service import PortalService, _utcnow


@pytest.fixture
def workspace(db_session):
    ws = RespondWorkspace(
        space_id="space-123",
        name="Test WS",
        api_key_ciphertext="x",
    )
    db_session.add(ws)
    db_session.commit()
    return ws


@pytest.fixture
def contact(db_session, workspace):
    c = RespondContact(
        id="contact-1",
        phone_number="+60123",
        name="Tester",
        respond_io_id="999",
        workspace_id=workspace.id,
    )
    db_session.add(c)
    db_session.commit()
    return c


def test_get_or_mint_token_mints_when_no_token(db_session, contact, workspace):
    svc = PortalService(db_session)
    token, reused = svc.get_or_mint_token(contact.id, workspace.space_id)
    assert reused is False
    assert token.contact_id == contact.id
    assert token.space_id == workspace.space_id


def test_get_or_mint_token_reuses_live_token(db_session, contact, workspace):
    svc = PortalService(db_session)
    first, _ = svc.get_or_mint_token(contact.id, workspace.space_id)
    second, reused = svc.get_or_mint_token(contact.id, workspace.space_id)
    assert reused is True
    assert second.token == first.token


def test_get_or_mint_token_mints_new_when_only_expired(db_session, contact, workspace):
    expired = PortalToken(
        token="expired-tok",
        contact_id=contact.id,
        space_id=workspace.space_id,
        expires_at=_utcnow() - timedelta(hours=1),
    )
    db_session.add(expired)
    db_session.commit()

    svc = PortalService(db_session)
    new_token, reused = svc.get_or_mint_token(contact.id, workspace.space_id)
    assert reused is False
    assert new_token.token != "expired-tok"


def test_get_or_mint_token_mints_new_when_revoked(db_session, contact, workspace):
    revoked = PortalToken(
        token="revoked-tok",
        contact_id=contact.id,
        space_id=workspace.space_id,
        expires_at=_utcnow() + timedelta(days=5),
        revoked_at=_utcnow(),
    )
    db_session.add(revoked)
    db_session.commit()

    svc = PortalService(db_session)
    new_token, reused = svc.get_or_mint_token(contact.id, workspace.space_id)
    assert reused is False
    assert new_token.token != "revoked-tok"
```

NOTE: this assumes the existing test suite provides a `db_session` fixture. If not, copy the fixture pattern from another existing test file (e.g. `tests/test_portal_service.py` if present, otherwise `tests/test_lookup_models.py`).

- [ ] **Step 2.2: Run tests — expect FAIL**

```bash
cd sorento_crm_backend && pytest tests/test_portal_link_action.py -q
```

Expected: 4 failures with `AttributeError: 'PortalService' object has no attribute 'get_or_mint_token'`.

- [ ] **Step 2.3: Implement `get_or_mint_token`**

In `sorento_crm_backend/app/services/portal_service.py`, locate the `mint_token` method. Immediately AFTER it, add:

```python
    def get_or_mint_token(self, contact_id: str, space_id: str) -> tuple[PortalToken, bool]:
        """Return latest live token for (contact_id, space_id) or mint a new one.

        Returns (token, reused). A token is "live" if revoked_at is null and expires_at > now.
        """
        contact_id = (contact_id or "").strip()
        space_id = (space_id or "").strip()
        if not contact_id or not space_id:
            raise handle_validation_error("contact_id and space_id are required.")
        live = (
            self.db.query(PortalToken)
            .filter(
                PortalToken.contact_id == contact_id,
                PortalToken.space_id == space_id,
                PortalToken.revoked_at.is_(None),
                PortalToken.expires_at > _utcnow(),
            )
            .order_by(PortalToken.expires_at.desc())
            .first()
        )
        if live is not None:
            return live, True
        return self.mint_token(contact_id, space_id), False
```

- [ ] **Step 2.4: Run tests — expect PASS**

```bash
pytest tests/test_portal_link_action.py -q
```

Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add sorento_crm_backend/app/services/portal_service.py \
        sorento_crm_backend/tests/test_portal_link_action.py
git commit -m "feat(portal): add get_or_mint_token reuse helper"
```

---

## Task 3: PortalService.send_link_via_respond_io

**Files:**
- Modify: `sorento_crm_backend/app/services/portal_service.py`
- Modify: `sorento_crm_backend/tests/test_portal_link_action.py`

- [ ] **Step 3.1: Append failing tests for send flow**

Append to `sorento_crm_backend/tests/test_portal_link_action.py`:

```python
def test_send_link_via_respond_io_success(db_session, contact, workspace, monkeypatch):
    captured = {}

    def fake_send(self, identifier, text):
        captured["identifier"] = identifier
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        fake_send,
    )
    svc = PortalService(db_session)
    result = svc.send_link_via_respond_io(contact.id, workspace.space_id)
    assert result["sent"] is True
    assert result["reused"] is False
    assert result["portal_url"]
    assert captured["identifier"] == contact.respond_io_id
    assert "portal" in captured["text"].lower()
    assert result["portal_url"] in captured["text"]


def test_send_link_via_respond_io_reuses_token(db_session, contact, workspace, monkeypatch):
    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        lambda self, identifier, text: {"ok": True},
    )
    svc = PortalService(db_session)
    first = svc.send_link_via_respond_io(contact.id, workspace.space_id)
    second = svc.send_link_via_respond_io(contact.id, workspace.space_id)
    assert first["portal_url"] == second["portal_url"]
    assert second["reused"] is True


def test_send_link_propagates_respond_io_failure(db_session, contact, workspace, monkeypatch):
    import httpx

    def boom(self, identifier, text):
        request = httpx.Request("POST", "https://api.respond.io/v2/contact/x/message")
        response = httpx.Response(500, request=request, text="upstream blew up")
        raise httpx.HTTPStatusError("500", request=request, response=response)

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", boom
    )
    svc = PortalService(db_session)
    with pytest.raises(httpx.HTTPStatusError):
        svc.send_link_via_respond_io(contact.id, workspace.space_id)

    # token still minted (so /portal-link itself remains usable)
    from app.models.portal import PortalToken as PT
    assert (
        db_session.query(PT)
        .filter(PT.contact_id == contact.id, PT.revoked_at.is_(None))
        .count()
        == 1
    )
```

- [ ] **Step 3.2: Run tests — expect FAIL**

```bash
cd sorento_crm_backend && pytest tests/test_portal_link_action.py -q -k send
```

Expected: 3 failures (`AttributeError: ... 'send_link_via_respond_io'`).

- [ ] **Step 3.3: Implement send method**

In `sorento_crm_backend/app/services/portal_service.py`, add the import near the top (add to existing imports if `IntegrationService`/`RespondClient` not already imported):

```python
from app.services.integration_service import RespondClient
```

Then, AFTER `get_or_mint_token`, add:

```python
    def _build_send_message_text(self, contact: RespondContact, portal_url: str, expires_at) -> str:
        name = (contact.name or contact.first_name or "").strip()
        greeting = f"Hi {name}," if name else "Hi,"
        expires_human = expires_at.strftime("%b %d, %Y")
        return (
            f"{greeting} here is your secure portal link:\n"
            f"{portal_url}\n\n"
            f"The link expires on {expires_human}. Reply if you need help."
        )

    def send_link_via_respond_io(
        self,
        contact_id: str,
        space_id: str,
        base_url: Optional[str] = None,
    ) -> dict:
        """Mint or reuse a portal token and deliver it via Respond.io chat.

        Raises httpx.HTTPStatusError on upstream failure (caller maps to 502).
        """
        contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if contact is None:
            raise handle_not_found("Contact", contact_id)
        respond_io_id = (contact.respond_io_id or "").strip()
        if not respond_io_id:
            raise handle_validation_error(
                "Contact has no Respond.io identifier; cannot send link."
            )
        token, reused = self.get_or_mint_token(contact_id, space_id)
        portal_url = self.build_portal_url(token.token, base_url)
        text = self._build_send_message_text(contact, portal_url, token.expires_at)
        RespondClient().send_message(respond_io_id, text)
        return {
            "token": token.token,
            "expires_at": token.expires_at.isoformat(),
            "portal_url": portal_url,
            "reused": reused,
            "sent": True,
        }
```

If `Optional` is not already imported in this file, add `from typing import Optional` to the imports.

- [ ] **Step 3.4: Run tests — expect PASS**

```bash
pytest tests/test_portal_link_action.py -q
```

Expected: 7 passed total.

- [ ] **Step 3.5: Commit**

```bash
git add sorento_crm_backend/app/services/portal_service.py \
        sorento_crm_backend/tests/test_portal_link_action.py
git commit -m "feat(portal): add send_link_via_respond_io"
```

---

## Task 4: POST /portal-link endpoint

**Files:**
- Modify: `sorento_crm_backend/app/api/v1/user_management/contacts.py`
- Modify: `sorento_crm_backend/tests/test_portal_link_action.py`

- [ ] **Step 4.1: Append failing endpoint tests**

Append to `sorento_crm_backend/tests/test_portal_link_action.py`:

```python
# ---------- HTTP endpoint tests ----------
# These assume the project provides a `client` fixture (FastAPI TestClient with auth helpers).
# If a different fixture name is used, adapt to match other tests under tests/.

def test_portal_link_endpoint_requires_permission(client, contact):
    res = client.as_user(permissions=[]).post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link"
    )
    assert res.status_code == 403


def test_portal_link_endpoint_returns_url(client, contact, workspace):
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert body["portal_url"].endswith(f"/portal?token={body['token']}")
    assert body["reused"] is False


def test_portal_link_endpoint_reuses_on_second_call(client, contact, workspace):
    auth = client.as_user(permissions=["user_management.contacts.portal_link"])
    first = auth.post(f"/api/v1/user-management/contacts/{contact.id}/portal-link").json()
    second = auth.post(f"/api/v1/user-management/contacts/{contact.id}/portal-link").json()
    assert first["token"] == second["token"]
    assert second["reused"] is True


def test_portal_link_endpoint_404_unknown_contact(client):
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        "/api/v1/user-management/contacts/does-not-exist/portal-link"
    )
    assert res.status_code == 404


def test_portal_link_endpoint_422_when_no_workspace(client, db_session):
    c = RespondContact(id="orphan", phone_number="+1", name="Orphan", workspace_id=None)
    db_session.add(c)
    db_session.commit()
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        f"/api/v1/user-management/contacts/{c.id}/portal-link"
    )
    assert res.status_code == 422
    assert "workspace" in res.json()["detail"].lower()
```

NOTE: If your test suite uses a different client/auth pattern, adapt to match (e.g. monkeypatch `get_current_user` and `UserPermissionService.check_user_has_permission`). Look at `tests/test_lookup_permissions.py` for the project's conventional pattern and mirror it.

- [ ] **Step 4.2: Run tests — expect FAIL**

```bash
cd sorento_crm_backend && pytest tests/test_portal_link_action.py -q -k portal_link_endpoint
```

Expected: 5 failures (404 from FastAPI: route not registered).

- [ ] **Step 4.3: Implement endpoint**

In `sorento_crm_backend/app/api/v1/user_management/contacts.py`, add imports near the existing imports:

```python
from app.dependencies import require_permission
from app.services.portal_service import PortalService
from app.services.error_handler import handle_validation_error, handle_not_found
from app.models.access import RespondContact, RespondWorkspace
```

Then add this Pydantic model near the existing `BulkDeleteContactsRequest`:

```python
class PortalLinkRequest(BaseModel):
    base_url: Optional[str] = None


class PortalLinkResponse(BaseModel):
    token: str
    expires_at: str
    portal_url: str
    reused: bool
```

(`Optional` is already imported in this file via `from typing import Optional`.)

Add a private helper at module scope (just below the imports):

```python
def _resolve_space_id(db: Session, contact_id: str) -> tuple[RespondContact, str]:
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)
    if not contact.workspace_id:
        raise handle_validation_error("Contact has no workspace; cannot mint portal link.")
    workspace = (
        db.query(RespondWorkspace)
        .filter(RespondWorkspace.id == contact.workspace_id)
        .first()
    )
    if workspace is None or not workspace.space_id:
        raise handle_validation_error("Contact has no workspace; cannot mint portal link.")
    return contact, workspace.space_id
```

Add the route at the bottom of the file:

```python
@router.post("/{contact_id}/portal-link", response_model=PortalLinkResponse)
async def get_contact_portal_link(
    contact_id: str,
    payload: PortalLinkRequest = Body(default_factory=PortalLinkRequest),
    current_user: dict = Depends(require_permission("user_management.contacts.portal_link")),
    db: Session = Depends(get_db),
):
    """Mint or reuse a 7-day user-submission portal token for the contact."""
    _, space_id = _resolve_space_id(db, contact_id)
    service = PortalService(db)
    token, reused = service.get_or_mint_token(contact_id, space_id)
    return PortalLinkResponse(
        token=token.token,
        expires_at=token.expires_at.isoformat(),
        portal_url=service.build_portal_url(token.token, payload.base_url),
        reused=reused,
    )
```

- [ ] **Step 4.4: Run tests — expect PASS**

```bash
pytest tests/test_portal_link_action.py -q -k portal_link_endpoint
```

Expected: 5 passed.

- [ ] **Step 4.5: Commit**

```bash
git add sorento_crm_backend/app/api/v1/user_management/contacts.py \
        sorento_crm_backend/tests/test_portal_link_action.py
git commit -m "feat(api): add POST /user-management/contacts/{id}/portal-link"
```

---

## Task 5: POST /portal-link/send endpoint

**Files:**
- Modify: `sorento_crm_backend/app/api/v1/user_management/contacts.py`
- Modify: `sorento_crm_backend/tests/test_portal_link_action.py`

- [ ] **Step 5.1: Append failing endpoint tests**

Append to `sorento_crm_backend/tests/test_portal_link_action.py`:

```python
def test_portal_link_send_endpoint_success(client, contact, workspace, monkeypatch):
    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        lambda self, identifier, text: {"ok": True},
    )
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["sent"] is True
    assert body["portal_url"]
    assert body["reused"] is False


def test_portal_link_send_endpoint_422_no_respond_io_id(client, db_session, workspace):
    c = RespondContact(
        id="no-rio", phone_number="+2", name="N", workspace_id=workspace.id, respond_io_id=None
    )
    db_session.add(c)
    db_session.commit()
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        f"/api/v1/user-management/contacts/{c.id}/portal-link/send"
    )
    assert res.status_code == 422
    assert "respond.io" in res.json()["detail"].lower()


def test_portal_link_send_endpoint_502_on_upstream_failure(client, contact, workspace, monkeypatch):
    import httpx

    def boom(self, identifier, text):
        request = httpx.Request("POST", "https://api.respond.io/x")
        response = httpx.Response(500, request=request, text="upstream blew up")
        raise httpx.HTTPStatusError("500", request=request, response=response)

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", boom
    )
    res = client.as_user(permissions=["user_management.contacts.portal_link"]).post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )
    assert res.status_code == 502
```

- [ ] **Step 5.2: Run tests — expect FAIL**

```bash
cd sorento_crm_backend && pytest tests/test_portal_link_action.py -q -k portal_link_send
```

Expected: 3 failures (404 — route not registered).

- [ ] **Step 5.3: Implement send endpoint**

In `sorento_crm_backend/app/api/v1/user_management/contacts.py`, add the import:

```python
import httpx
```

(if not already present). Add response schema near `PortalLinkResponse`:

```python
class PortalLinkSendResponse(BaseModel):
    token: str
    expires_at: str
    portal_url: str
    reused: bool
    sent: bool
```

Add the route below `get_contact_portal_link`:

```python
@router.post("/{contact_id}/portal-link/send", response_model=PortalLinkSendResponse)
async def send_contact_portal_link(
    contact_id: str,
    payload: PortalLinkRequest = Body(default_factory=PortalLinkRequest),
    current_user: dict = Depends(require_permission("user_management.contacts.portal_link")),
    db: Session = Depends(get_db),
):
    """Mint or reuse a portal token and send the link to the contact via Respond.io."""
    _, space_id = _resolve_space_id(db, contact_id)
    service = PortalService(db)
    try:
        result = service.send_link_via_respond_io(contact_id, space_id, payload.base_url)
    except httpx.HTTPStatusError as exc:
        upstream = ""
        try:
            upstream = exc.response.text[:500]
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail=f"Respond.io upstream failure: {upstream or str(exc)}",
        )
    return PortalLinkSendResponse(**result)
```

- [ ] **Step 5.4: Run tests — expect PASS**

```bash
pytest tests/test_portal_link_action.py -q
```

Expected: all tests pass (10+).

- [ ] **Step 5.5: Commit**

```bash
git add sorento_crm_backend/app/api/v1/user_management/contacts.py \
        sorento_crm_backend/tests/test_portal_link_action.py
git commit -m "feat(api): add POST /user-management/contacts/{id}/portal-link/send"
```

---

## Task 6: Frontend service + hooks + qrcode dep

**Files:**
- Modify: `sorento_crm_frontend/package.json`
- Create: `sorento_crm_frontend/services/contactPortalLinkService.ts`
- Create: `sorento_crm_frontend/hooks/useContactPortalLink.ts`

- [ ] **Step 6.1: Install qrcode.react**

```bash
cd sorento_crm_frontend && npm install --force qrcode.react
```

Expected: `qrcode.react` added to `dependencies` in `package.json`.

- [ ] **Step 6.2: Create service**

Create `sorento_crm_frontend/services/contactPortalLinkService.ts`:

```typescript
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface PortalLinkResponse {
  token: string;
  expires_at: string;
  portal_url: string;
  reused: boolean;
}

export interface PortalLinkSendResponse extends PortalLinkResponse {
  sent: true;
}

export async function getContactPortalLink(contactId: string): Promise<PortalLinkResponse> {
  const res = await apiFetch(`/api/v1/user-management/contacts/${contactId}/portal-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to get portal link'));
  return res.json();
}

export async function sendContactPortalLink(contactId: string): Promise<PortalLinkSendResponse> {
  const res = await apiFetch(`/api/v1/user-management/contacts/${contactId}/portal-link/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to send portal link'));
  return res.json();
}
```

- [ ] **Step 6.3: Create hooks**

Create `sorento_crm_frontend/hooks/useContactPortalLink.ts`:

```typescript
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getContactPortalLink,
  sendContactPortalLink,
  type PortalLinkResponse,
  type PortalLinkSendResponse,
} from '@/services/contactPortalLinkService';

export function useContactPortalLinkMutation() {
  return useMutation<PortalLinkResponse, Error, string>({
    mutationFn: getContactPortalLink,
    onError: (err) => toast.error(err.message),
  });
}

export function useSendContactPortalLinkMutation() {
  return useMutation<PortalLinkSendResponse, Error, string>({
    mutationFn: sendContactPortalLink,
    onError: (err) => toast.error(err.message),
  });
}
```

- [ ] **Step 6.4: Type-check**

```bash
cd sorento_crm_frontend && npx tsc --noEmit -p .
```

Expected: no errors related to the new files. (Pre-existing errors elsewhere are out of scope.)

- [ ] **Step 6.5: Commit**

```bash
git add sorento_crm_frontend/package.json sorento_crm_frontend/package-lock.json \
        sorento_crm_frontend/services/contactPortalLinkService.ts \
        sorento_crm_frontend/hooks/useContactPortalLink.ts
git commit -m "feat(fe): contact portal link service + hooks"
```

---

## Task 7: PortalLinkDialog component (with vitest)

**Files:**
- Create: `sorento_crm_frontend/components/contacts/PortalLinkDialog.tsx`
- Create: `sorento_crm_frontend/components/contacts/PortalLinkDialog.test.tsx`

- [ ] **Step 7.1: Write failing component test**

Create `sorento_crm_frontend/components/contacts/PortalLinkDialog.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortalLinkDialog from './PortalLinkDialog';

vi.mock('@/services/contactPortalLinkService', () => ({
  getContactPortalLink: vi.fn(),
  sendContactPortalLink: vi.fn(),
}));

import {
  getContactPortalLink,
  sendContactPortalLink,
} from '@/services/contactPortalLinkService';

function renderDialog(props: Partial<React.ComponentProps<typeof PortalLinkDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PortalLinkDialog
        open
        onOpenChange={() => {}}
        contactId="c1"
        contactLabel="Tester"
        canSendViaRespondIo
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe('PortalLinkDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('renders portal URL and expiry on success', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok123',
      portal_url: 'https://crm.example.com/portal?token=tok123',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog();
    await waitFor(() =>
      expect(
        screen.getByDisplayValue('https://crm.example.com/portal?token=tok123'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/Expires/i)).toBeInTheDocument();
    expect(screen.queryByText(/Reused existing link/i)).not.toBeInTheDocument();
  });

  it('shows reused badge when reused=true', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: true,
    });
    renderDialog();
    await waitFor(() => screen.getByText(/Reused existing link/i));
  });

  it('copies link to clipboard on Copy click', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog();
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    await userEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect((navigator.clipboard.writeText as any)).toHaveBeenCalledWith(
      'https://x/portal?token=tok',
    );
  });

  it('fires send mutation on Send via Respond.io click', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    (sendContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: true,
      sent: true,
    });
    renderDialog();
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    await userEvent.click(screen.getByRole('button', { name: /send via respond\.io/i }));
    await waitFor(() => expect(sendContactPortalLink).toHaveBeenCalledWith('c1'));
  });

  it('disables Send when canSendViaRespondIo is false', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog({ canSendViaRespondIo: false });
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    expect(screen.getByRole('button', { name: /send via respond\.io/i })).toBeDisabled();
  });
});
```

- [ ] **Step 7.2: Run tests — expect FAIL**

```bash
cd sorento_crm_frontend && npx vitest run components/contacts/PortalLinkDialog.test.tsx
```

Expected: failure — module not found.

- [ ] **Step 7.3: Implement dialog**

Create `sorento_crm_frontend/components/contacts/PortalLinkDialog.tsx`:

```typescript
'use client';

import { useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Loader2, Copy, ExternalLink, Send } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  useContactPortalLinkMutation,
  useSendContactPortalLinkMutation,
} from '@/hooks/useContactPortalLink';

export interface PortalLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId: string;
  contactLabel?: string;
  canSendViaRespondIo?: boolean;
}

function formatExpiry(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export default function PortalLinkDialog({
  open,
  onOpenChange,
  contactId,
  contactLabel,
  canSendViaRespondIo = true,
}: PortalLinkDialogProps) {
  const linkMutation = useContactPortalLinkMutation();
  const sendMutation = useSendContactPortalLinkMutation();

  useEffect(() => {
    if (open && contactId) {
      linkMutation.reset();
      sendMutation.reset();
      linkMutation.mutate(contactId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId]);

  const data = linkMutation.data;
  const portalUrl = data?.portal_url ?? '';

  async function handleCopy() {
    if (!portalUrl) return;
    try {
      await navigator.clipboard.writeText(portalUrl);
      toast.success('Copied');
    } catch {
      toast.error('Press Ctrl/Cmd+C to copy');
    }
  }

  async function handleSend() {
    try {
      await sendMutation.mutateAsync(contactId);
      toast.success(`Sent to ${contactLabel ?? 'contact'}`);
    } catch {
      // toast already handled in hook onError
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Portal link {contactLabel ? `— ${contactLabel}` : ''}</DialogTitle>
        </DialogHeader>

        {linkMutation.isPending && (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {linkMutation.isError && (
          <div className="space-y-2 text-sm">
            <p className="text-destructive">
              {(linkMutation.error as Error).message || 'Failed to fetch portal link.'}
            </p>
            <Button variant="outline" onClick={() => linkMutation.mutate(contactId)}>
              Retry
            </Button>
          </div>
        )}

        {data && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Expires {formatExpiry(data.expires_at)}</span>
              {data.reused && <Badge variant="secondary">Reused existing link</Badge>}
            </div>
            <div className="flex gap-2">
              <Input value={data.portal_url} readOnly onFocus={(e) => e.currentTarget.select()} />
              <Button type="button" variant="outline" onClick={handleCopy}>
                <Copy className="size-4 mr-1" /> Copy
              </Button>
            </div>
            <div className="flex justify-center">
              <QRCodeSVG value={data.portal_url} size={192} includeMargin />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
              <Button asChild variant="outline">
                <a href={data.portal_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4 mr-1" /> Open in new tab
                </a>
              </Button>
              <Button
                type="button"
                onClick={handleSend}
                disabled={!canSendViaRespondIo || sendMutation.isPending}
                title={
                  !canSendViaRespondIo ? 'Contact has no Respond.io ID' : undefined
                }
              >
                {sendMutation.isPending ? (
                  <Loader2 className="size-4 mr-1 animate-spin" />
                ) : (
                  <Send className="size-4 mr-1" />
                )}
                Send via Respond.io
              </Button>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 7.4: Run tests — expect PASS**

```bash
npx vitest run components/contacts/PortalLinkDialog.test.tsx
```

Expected: 5 passed.

- [ ] **Step 7.5: Commit**

```bash
git add sorento_crm_frontend/components/contacts/PortalLinkDialog.tsx \
        sorento_crm_frontend/components/contacts/PortalLinkDialog.test.tsx
git commit -m "feat(fe): PortalLinkDialog with copy/QR/send actions"
```

---

## Task 8: PortalLinkButton wrapper

**Files:**
- Create: `sorento_crm_frontend/components/contacts/PortalLinkButton.tsx`

- [ ] **Step 8.1: Implement button wrapper**

Create `sorento_crm_frontend/components/contacts/PortalLinkButton.tsx`:

```typescript
'use client';

import { useState, type ReactNode } from 'react';
import { LinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import PortalLinkDialog from './PortalLinkDialog';

export interface PortalLinkButtonProps {
  contactId: string;
  contactLabel?: string;
  canSendViaRespondIo?: boolean;
  variant?: 'button' | 'menu-item' | 'icon';
  disabled?: boolean;
  children?: ReactNode;
}

const PERMISSION_SLUG = 'user_management.contacts.portal_link';

export default function PortalLinkButton({
  contactId,
  contactLabel,
  canSendViaRespondIo,
  variant = 'button',
  disabled,
  children,
}: PortalLinkButtonProps) {
  const allowed = useHasPermission(PERMISSION_SLUG);
  const [open, setOpen] = useState(false);

  if (!allowed) return null;

  const trigger = (() => {
    if (variant === 'menu-item') {
      return (
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault();
            setOpen(true);
          }}
          disabled={disabled}
        >
          <LinkIcon className="size-4 mr-2" />
          {children ?? 'Portal link'}
        </DropdownMenuItem>
      );
    }
    if (variant === 'icon') {
      return (
        <Button
          variant="ghost"
          size="sm"
          title="Portal link"
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          <LinkIcon className="size-4" />
        </Button>
      );
    }
    return (
      <Button
        variant="outline"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <LinkIcon className="size-4 mr-2" />
        {children ?? 'Portal link'}
      </Button>
    );
  })();

  return (
    <>
      {trigger}
      <PortalLinkDialog
        open={open}
        onOpenChange={setOpen}
        contactId={contactId}
        contactLabel={contactLabel}
        canSendViaRespondIo={canSendViaRespondIo}
      />
    </>
  );
}
```

- [ ] **Step 8.2: Type-check**

```bash
cd sorento_crm_frontend && npx tsc --noEmit -p .
```

Expected: no errors in the new file.

- [ ] **Step 8.3: Commit**

```bash
git add sorento_crm_frontend/components/contacts/PortalLinkButton.tsx
git commit -m "feat(fe): PortalLinkButton wrapper with permission gate"
```

---

## Task 9: Wire into contact detail page

**Files:**
- Modify: `sorento_crm_frontend/app/(protected)/user-management/contacts/[id]/page.tsx`

- [ ] **Step 9.1: Add import**

In `sorento_crm_frontend/app/(protected)/user-management/contacts/[id]/page.tsx`, add this import alongside the other component imports near the top:

```typescript
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
```

- [ ] **Step 9.2: Add button in toolbar actions**

Locate the `ToolbarActions` block (the area containing the Delete contact and Back to contacts buttons — see lines around 162-175). Insert this BEFORE the Delete button:

```tsx
<PortalLinkButton
  contactId={id}
  contactLabel={contact?.name ?? contact?.phone_number ?? id}
  canSendViaRespondIo={!!contact?.respond_io_id}
/>
```

- [ ] **Step 9.3: Smoke test in dev**

```bash
cd sorento_crm_frontend && npm run dev
```

Open `/user-management/contacts/<some id>`. Verify:
- "Portal link" button shows in the toolbar (assuming user has the perm or is admin).
- Click → modal opens, shows URL + QR + Copy + Open + Send buttons.
- "Send via Respond.io" disabled with tooltip when contact has no `respond_io_id`.

Stop the dev server.

- [ ] **Step 9.4: Commit**

```bash
git add "sorento_crm_frontend/app/(protected)/user-management/contacts/[id]/page.tsx"
git commit -m "feat(fe): wire PortalLinkButton into contact detail toolbar"
```

---

## Task 10: Wire into contacts list row action

**Files:**
- Modify: `sorento_crm_frontend/app/(protected)/user-management/contacts/components/ContactsList.tsx`

- [ ] **Step 10.1: Add import**

In `sorento_crm_frontend/app/(protected)/user-management/contacts/components/ContactsList.tsx`, add this import near the existing component imports:

```typescript
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
```

- [ ] **Step 10.2: Add row action**

In the `actions` column cell (around line 247), insert as the FIRST child inside the `<div className="flex items-center gap-1" ...>` (before the Delete button):

```tsx
<PortalLinkButton
  contactId={row.original.id}
  contactLabel={row.original.name ?? row.original.phone_number ?? row.original.id}
  canSendViaRespondIo={!!row.original.respond_io_id}
  variant="icon"
/>
```

- [ ] **Step 10.3: Smoke test**

```bash
cd sorento_crm_frontend && npm run dev
```

Open `/user-management/contacts`. Verify the link icon appears in each row's action area, click opens the modal, dialog interactions work. Stop the dev server.

- [ ] **Step 10.4: Commit**

```bash
git add "sorento_crm_frontend/app/(protected)/user-management/contacts/components/ContactsList.tsx"
git commit -m "feat(fe): add PortalLink row action to contacts list"
```

---

## Task 11: Wire into SLA tracking detail gear menu

**Files:**
- Modify: `sorento_crm_frontend/app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx`

- [ ] **Step 11.1: Add import**

In `sorento_crm_frontend/app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx`, add the import:

```typescript
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
```

- [ ] **Step 11.2: Add menu item next to "Open conversation"**

Locate the `<DropdownMenuContent ...>` block (around line 340). After the "Open conversation" `<DropdownMenuItem>` (around line 354), insert:

```tsx
{tracking.contact?.id && (
  <PortalLinkButton
    contactId={tracking.contact.id}
    contactLabel={tracking.contact?.name ?? tracking.contact_phone ?? tracking.contact?.phone_number ?? tracking.contact.id}
    canSendViaRespondIo={!!(tracking.contact?.respond_io_id ?? respondIoId)}
    variant="menu-item"
  />
)}
```

If the tracking response shape exposes `tracking.contact_id` directly instead of `tracking.contact?.id`, use that instead — verify via the type at `types/conversationSLATracking.types.ts` and the data shape rendered around line 285.

- [ ] **Step 11.3: Type-check**

```bash
cd sorento_crm_frontend && npx tsc --noEmit -p .
```

Expected: no errors in the modified file.

- [ ] **Step 11.4: Smoke test**

```bash
cd sorento_crm_frontend && npm run dev
```

Open a conversation SLA tracking detail page (the page in the screenshot). Click the gear icon → confirm "Portal link" appears in the dropdown. Click it → modal opens with the contact's portal URL. Stop the dev server.

- [ ] **Step 11.5: Commit**

```bash
git add "sorento_crm_frontend/app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx"
git commit -m "feat(fe): add Portal link to SLA tracking detail gear menu"
```

---

## Task 12: Full verification + final commit

- [ ] **Step 12.1: Run full backend test suite**

```bash
cd sorento_crm_backend && pytest tests/test_portal_link_action.py tests/test_contact_portal_link_permission.py -q
```

Expected: all tests pass.

- [ ] **Step 12.2: Run full frontend test suite**

```bash
cd sorento_crm_frontend && npm run test -- --run components/contacts/PortalLinkDialog.test.tsx
```

Expected: 5 passed.

- [ ] **Step 12.3: End-to-end manual test**

```bash
cd sorento_crm_backend && source venv/bin/activate && uvicorn app.main:app --reload &
cd sorento_crm_frontend && npm run dev
```

In browser:
1. Log in as superadmin/admin.
2. Go to `/user-management/contacts`. Click the link-icon row action on a contact with a `respond_io_id`. Confirm modal renders URL + QR. Copy → paste in another tab → portal opens. Click "Send via Respond.io" → verify message arrives in Respond.io chat (staging) and toast shows "Sent to ...".
3. Go to that contact's detail page. Confirm toolbar "Portal link" button works.
4. Go to `/sla-management/conversation-sla-tracking/<id>`. Open gear menu → "Portal link" item present. Click → same modal.
5. As a non-admin user without `user_management.contacts.portal_link`, confirm the button does NOT render anywhere.

Stop both servers.

- [ ] **Step 12.4: Verify no leftover artifacts**

```bash
git status
```

Expected: clean working tree (all changes committed across previous tasks).

- [ ] **Step 12.5: Push branch**

```bash
git push -u origin claude/user-submission-portal-VSIDo
```

(Skip if user wants to inspect locally first.)

---

## Notes for executor

- The backend test suite's exact fixture names (`db_session`, `client`, `client.as_user`) may differ. Look at `tests/test_lookup_permissions.py` and adjacent files to find the project's actual conventions and adapt the test scaffolding accordingly. Do not invent fixtures.
- `qrcode.react` exports `QRCodeSVG`; if a different export is in use after install, prefer `QRCodeSVG` (named export from the v3+ package).
- The toolbar / row action insertions specify approximate line numbers from the snapshot; if line numbers have drifted, locate the same structural anchor (Toolbar actions block, actions column cell, gear DropdownMenuContent) by name rather than by line.
- The new permission auto-applies to superadmin/admin via the existing `require_permission` bypass — no role-grant code needed.
