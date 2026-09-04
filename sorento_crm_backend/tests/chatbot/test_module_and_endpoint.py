"""S0 scaffold: the module, the slug, the module guard and the settings flag.

AC-001 (the module declares itself and the manifest carries it), AC-006 (403 naming the
slug without the grant, 403 naming the module under strict mode) and the R1 gate the
router's stock-denial predicate hangs on.

The endpoint tests build a small FastAPI app around the REAL guards rather than the whole
`app.main` router tree, the same shape `tests/test_external_permission_guard.py` uses: the
thing under test is the guard pair, and mounting 400 unrelated routes to exercise two
dependencies would only add ways for an unrelated module to fail this file.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip  - registers every model before create_all

from app.api.v1.external.permissions import (
    EXTERNAL_ENDPOINT_PERMISSIONS,
    NEW_INTEGRATION_PERMISSIONS,
    require_external_permission,
)
from app.config import settings as app_settings
from app.dependencies import get_db
from app.models.app_modules import AppModuleCatalog, TenantModule
from app.models.integration import Integration, IntegrationApiKey
from app.models.user import (
    SystemSetting,
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.modules.chatbot.bootstrap import MODULE_KEY
from app.modules.runtime.guards import require_module_enabled_with_api_key
from app.modules.runtime.module_manifest import MODULE_MANIFEST, manifest_dependency_graph
from app.modules.runtime.resolver import resolve_install_plan
from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services.integration_key_service import IntegrationKeyService
from tests._pg_fixture import pg_empty_schema

SLUG = "integration.chat_turn.submit"

_TABLES = [
    User.__table__,
    UserRole.__table__,
    UserRoleAssignment.__table__,
    UserPermission.__table__,
    UserRolePermission.__table__,
    Integration.__table__,
    IntegrationApiKey.__table__,
    AppModuleCatalog.__table__,
    TenantModule.__table__,
]


class TestModuleDeclaration:
    def test_the_bootstrap_declares_the_module_key(self) -> None:
        assert MODULE_KEY == "chatbot"

    def test_the_manifest_carries_the_module_and_its_dependencies(self) -> None:
        """AC-001. The dependency list is every domain a business-query turn can answer."""
        manifest = MODULE_MANIFEST["chatbot"]
        assert manifest.dependencies == frozenset(
            {
                "base",
                "product",
                "inventory",
                "order",
                "marketing",
                "procurement",
                "resources",
                "sla",
            }
        )

    def test_installing_it_resolves_a_dependency_ordered_plan(self) -> None:
        plan = resolve_install_plan(manifest_dependency_graph(), ["chatbot"])
        assert "chatbot" in plan
        for dependency in MODULE_MANIFEST["chatbot"].dependencies:
            assert plan.index(dependency) < plan.index("chatbot")


class TestPermissionSlug:
    def test_the_router_prefix_maps_to_the_slug(self) -> None:
        assert EXTERNAL_ENDPOINT_PERMISSIONS["chat"] == SLUG

    def test_the_slug_is_registered_so_a_grant_can_exist(self) -> None:
        """A slug with no registry row can never be granted, so the route 403s forever."""
        assert any(entry["slug"] == SLUG for entry in PERMISSION_REGISTRY)

    def test_the_slug_is_documented_on_the_external_surface(self) -> None:
        assert any(entry["slug"] == SLUG for entry in NEW_INTEGRATION_PERMISSIONS)


@pytest.fixture()
def db():
    with pg_empty_schema(_TABLES) as session:
        yield session


@pytest.fixture()
def key(db):
    """An integration whose role holds NOTHING, so each test grants what it needs."""
    user = User(
        email="chatbot@integrations.local",
        name="Integration: chatbot",
        status="ACTIVE",
        is_integration=True,
    )
    db.add(user)
    db.flush()
    role = UserRole(slug="integration_chatbot", name="Integration: chatbot")
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    permission = UserPermission(slug=SLUG, name="Submit chatbot turns")
    db.add(permission)
    db.flush()
    integration = Integration(
        name="n8n-chatbot", type="n8n", act_as_user_id=user.id, is_active=True
    )
    db.add(integration)
    db.flush()
    issued = IntegrationKeyService(db).issue_key(integration)
    return {"key": issued, "role_id": role.id, "permission_id": permission.id}


def _grant(db, key) -> None:
    db.add(UserRolePermission(role_id=key["role_id"], permission_id=key["permission_id"]))
    db.flush()


@pytest.fixture()
def client(db):
    api = FastAPI()

    @api.post("/turn")
    def turn(
        _perm: dict = Depends(require_external_permission(SLUG)),
        _mod: None = Depends(require_module_enabled_with_api_key("chatbot")),
    ):
        return {"ok": True}

    def _override_db():
        yield db

    api.dependency_overrides[get_db] = _override_db
    return TestClient(api, raise_server_exceptions=False)


class TestGuards:
    def test_without_the_slug_it_is_403_naming_the_slug(self, client, key) -> None:
        """AC-006. An operator seeing this needs to know which grant to add."""
        res = client.post("/turn", headers={"X-API-Key": key["key"]})
        assert res.status_code == 403
        assert SLUG in res.text
        assert "permission_denied" in res.text

    def test_no_key_is_401_not_403(self, client, key) -> None:
        assert client.post("/turn").status_code == 401

    def test_with_the_slug_and_no_module_rows_it_passes(self, client, db, key) -> None:
        """A legacy tenant has no module rows at all, which reads as full suite."""
        _grant(db, key)
        assert client.post("/turn", headers={"X-API-Key": key["key"]}).status_code == 200

    def test_strict_mode_with_the_module_disabled_is_403_naming_the_module(
        self, client, db, key, monkeypatch
    ) -> None:
        """AC-006, second half."""
        from app.modules.runtime.installer import DEFAULT_TENANT_ID

        _grant(db, key)
        db.add(AppModuleCatalog(module_key="chatbot", display_name="Chatbot turn engine"))
        db.add(AppModuleCatalog(module_key="base", display_name="Base"))
        db.flush()
        db.add(TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="base", enabled=True))
        db.add(TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="chatbot", enabled=False))
        db.flush()
        monkeypatch.setattr(app_settings, "module_guard_strict", True, raising=False)

        res = client.post("/turn", headers={"X-API-Key": key["key"]})
        assert res.status_code == 403
        assert "Module not enabled: chatbot" in res.text


class TestStockDenialSetting:
    def test_it_defaults_to_off(self, db) -> None:
        """R1: the corrected vocabulary wakes two lanes, so turning them on is a data
        change with a test. The default keeps them exactly as dead as they are today."""
        row = SystemSetting()
        assert row.chatbot_stock_denial_enabled in (False, None)

    def test_the_settings_get_dict_builder_carries_it(self) -> None:
        """A column missing from the manual dict builder never reaches the frontend."""
        import inspect

        from app.api.v1.user_management import settings as settings_module

        source = inspect.getsource(settings_module.get_settings)
        assert "chatbot_stock_denial_enabled" in source

    def test_the_update_schema_accepts_it(self) -> None:
        from app.api.v1.user_management.settings import SystemSettingUpdate

        assert "chatbot_stock_denial_enabled" in SystemSettingUpdate.model_fields
        parsed = SystemSettingUpdate(chatbot_stock_denial_enabled=True)
        assert parsed.chatbot_stock_denial_enabled is True
