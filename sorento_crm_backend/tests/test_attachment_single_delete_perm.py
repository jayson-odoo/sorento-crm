"""Single attachment delete takes `resource.attachments.delete` (ATTACH-DELETE-PERM).

`DELETE /api/v1/resource-management/attachments/{id}` hard-deletes a library file
(`entity_attachment_links` cascade with it), and took only `get_current_user`. It now takes
the `_crud("resource", "attachments", ...)` delete slug through the shared
`require_permission`, the same gate the bulk archive route on that router uses.

Dependency-override + `allow`-set monkeypatch pattern copied from
tests/test_teams_write_gates.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.base import set_company_scope
from app.models.resources import Attachment
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code

ATTACHMENTS_DELETE = "resource.attachments.delete"

BASE = "/api/v1/resource-management/attachments"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    """A signed-in caller whose permission set is exactly the returned `allow` set."""
    from app.services import queue_service
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()
    caller = {"id": str(uuid.uuid4()), "email": "attach-delete-caller@zzt.test"}

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    # The router's module guard resolves the caller through this one.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    # The storage delete is a background job; nothing here reaches a queue.
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    try:
        yield TestClient(app), allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def _seed_attachment(db) -> str:
    name = f"{unique_code('att')}.pdf"
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=name,
        stored_filename=name,
        file_path=f"https://cdn.example.test/resource/{name}",
        storage_provider="s3",
    )
    db.add(att)
    db.flush()
    return str(att.id)


def _exists(db, attachment_id: str) -> bool:
    db.expire_all()
    return db.query(Attachment).filter(Attachment.id == attachment_id).first() is not None


def test_single_delete_without_permission_is_refused_and_file_stays(db, api):
    client, _allow = api
    attachment_id = _seed_attachment(db)

    res = client.delete(f"{BASE}/{attachment_id}")

    assert res.status_code == 403, res.text
    assert ATTACHMENTS_DELETE in res.text
    assert _exists(db, attachment_id)


def test_single_delete_with_permission_deletes_the_file(db, api):
    client, allow = api
    allow.add(ATTACHMENTS_DELETE)
    attachment_id = _seed_attachment(db)

    res = client.delete(f"{BASE}/{attachment_id}")

    assert res.status_code == 200, res.text
    assert not _exists(db, attachment_id)
