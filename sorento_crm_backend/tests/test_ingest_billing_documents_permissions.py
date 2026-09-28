"""Finance S0-16: each billing-documents door takes its own finance slug (#1309).

The real guard (`require_external_permission_for_path`) over the real permission maps, on
an empty schema of its own, behind stub handlers mounted the way
`app/api/v1/external/__init__.py` mounts the real ones: ingest under the ingest map,
deletions under the ingest map AND the delete map, read under the read map. What is under
test is the gate; `test_ingest_billing_documents.py` covers what is behind it.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.api.v1.external import ingest as ingest_module
from app.api.v1.external.permissions import require_external_permission_for_path

MARKER = "zzfinperm"


def test_the_three_maps_name_the_finance_slugs():
    assert ingest_module.INGEST_PERMISSIONS["billing_documents"] == "finance.billing_documents.edit"
    assert ingest_module.READ_PERMISSIONS["billing_documents"] == "finance.billing_documents.view"
    assert (
        ingest_module.DELETE_PERMISSIONS["billing_documents"] == "finance.billing_documents.delete"
    )
    assert "billing_documents" in ingest_module.SUPPORTED_ENTITIES


@pytest.fixture()
def guard_db():
    from app.models.integration import Integration, IntegrationApiKey
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from tests._pg_fixture import pg_empty_schema

    with pg_empty_schema(
        [
            User.__table__,
            UserRole.__table__,
            UserRoleAssignment.__table__,
            UserPermission.__table__,
            UserRolePermission.__table__,
            Integration.__table__,
            IntegrationApiKey.__table__,
        ]
    ) as session:
        yield session


@pytest.fixture()
def client(guard_db):
    from app.dependencies import get_db as app_get_db

    api = FastAPI()
    ingest_guard = Depends(require_external_permission_for_path(ingest_module.INGEST_PERMISSIONS))

    @api.post("/ingest/{entity}", dependencies=[ingest_guard])
    def _ingest(entity: str):
        return {"ok": entity}

    @api.post(
        "/ingest/{entity}/deletions",
        dependencies=[
            ingest_guard,
            Depends(require_external_permission_for_path(ingest_module.DELETE_PERMISSIONS)),
        ],
    )
    def _delete(entity: str):
        return {"ok": entity}

    @api.post(
        "/read/{entity}",
        dependencies=[
            Depends(require_external_permission_for_path(ingest_module.READ_PERMISSIONS))
        ],
    )
    def _read(entity: str):
        return {"ok": entity}

    def _override_db():
        yield guard_db

    api.dependency_overrides[app_get_db] = _override_db
    return TestClient(api, raise_server_exceptions=False)


@pytest.fixture()
def keys(guard_db):
    from app.models.integration import Integration
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from app.services.integration_key_service import IntegrationKeyService

    slugs = [
        "scm.sales_orders.edit",
        "finance.billing_documents.view",
        "finance.billing_documents.export",
        "finance.billing_documents.edit",
        "finance.billing_documents.delete",
    ]
    perms = {}
    for slug in slugs:
        perm = UserPermission(slug=slug, name=slug)
        guard_db.add(perm)
        guard_db.flush()
        perms[slug] = perm

    holders = {
        "so_editor": ["scm.sales_orders.edit"],
        "viewer": ["finance.billing_documents.view"],
        "exporter": ["finance.billing_documents.export"],
        "feed": [
            "finance.billing_documents.view",
            "finance.billing_documents.edit",
            "finance.billing_documents.delete",
        ],
        "editor_only": ["finance.billing_documents.edit"],
    }
    issued = {}
    for label, held in holders.items():
        user = User(
            email=f"{MARKER}-{label}@integrations.local",
            name=f"Integration: {label}",
            status="ACTIVE",
            is_integration=True,
        )
        guard_db.add(user)
        guard_db.flush()
        role = UserRole(slug=f"{MARKER}_{label}", name=f"{MARKER} {label}")
        guard_db.add(role)
        guard_db.flush()
        guard_db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        for slug in held:
            guard_db.add(UserRolePermission(role_id=role.id, permission_id=perms[slug].id))
        guard_db.flush()
        integration = Integration(
            name=f"{MARKER}-{label}", type="autocount_esb", act_as_user_id=user.id, is_active=True
        )
        guard_db.add(integration)
        guard_db.flush()
        issued[label] = IntegrationKeyService(guard_db).issue_key(integration)
    return issued


def _post(client, path, key):
    return client.post(path, headers={"X-API-Key": key})


INGEST = "/ingest/billing_documents"
DELETE = "/ingest/billing_documents/deletions"
READ = "/read/billing_documents"


def test_sales_order_edit_alone_cannot_push_billing_documents(client, keys):
    res = _post(client, INGEST, keys["so_editor"])
    assert res.status_code == 403
    assert "finance.billing_documents.edit" in res.text
    assert _post(client, DELETE, keys["so_editor"]).status_code == 403
    assert _post(client, READ, keys["so_editor"]).status_code == 403


def test_view_alone_reads_but_never_pushes_or_deletes(client, keys):
    assert _post(client, INGEST, keys["viewer"]).status_code == 403
    assert _post(client, DELETE, keys["viewer"]).status_code == 403
    assert _post(client, READ, keys["viewer"]).status_code == 200


def test_export_alone_opens_no_door(client, keys):
    for path in (INGEST, DELETE, READ):
        assert _post(client, path, keys["exporter"]).status_code == 403, path


def test_deletions_need_the_delete_slug_on_top_of_edit(client, keys):
    res = _post(client, DELETE, keys["editor_only"])
    assert res.status_code == 403
    assert "finance.billing_documents.delete" in res.text
    assert _post(client, INGEST, keys["editor_only"]).status_code == 200
    assert _post(client, READ, keys["editor_only"]).status_code == 403


def test_the_feed_role_opens_all_three(client, keys):
    for path in (INGEST, DELETE, READ):
        assert _post(client, path, keys["feed"]).status_code == 200, path
