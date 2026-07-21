"""Slice 7 of AutoCount Group A — permission enforcement on /external.

  AC-AC-05 every external endpoint enforces the caller's permissions

Until now ``get_external_api_user`` applied no permission check at all: any
holder of the shared key could reach every /external endpoint. This adds the
check, against the integration's principal, using the same RBAC the rest of the
application uses.
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  isort:skip  (see test_integration_auth_dependencies)

from app.database import Base
from app.dependencies import get_db
from app.models.integration import Integration, IntegrationApiKey
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.integration_key_service import IntegrationKeyService
from app.api.v1.external.permissions import require_external_permission
from tests._sqlite_compat import create_all_sqlite_safe

_TABLES = [
    User.__table__,
    UserRole.__table__,
    UserRoleAssignment.__table__,
    UserPermission.__table__,
    UserRolePermission.__table__,
    Integration.__table__,
    IntegrationApiKey.__table__,
]

_GRANTED = "procurement.grn.add"
_WITHHELD = "master_data.products.delete"


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    create_all_sqlite_safe(Base.metadata, engine, tables=_TABLES)
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    app = FastAPI()

    @app.get("/allowed")
    def allowed(_: dict = Depends(require_external_permission(_GRANTED))):
        return {"ok": True}

    @app.get("/forbidden")
    def forbidden(_: dict = Depends(require_external_permission(_WITHHELD))):
        return {"ok": True}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def key(db):
    """An integration whose role holds _GRANTED but not _WITHHELD."""
    user = User(
        email="esb@integrations.local", name="Integration: ESB", status="ACTIVE", is_integration=True
    )
    db.add(user)
    db.flush()

    role = UserRole(slug="integration_esb", name="Integration: ESB")
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))

    for slug in (_GRANTED, _WITHHELD):
        perm = UserPermission(slug=slug, name=slug)
        db.add(perm)
        db.flush()
        if slug == _GRANTED:
            db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))

    integration = Integration(
        name="foundryx-esb", type="autocount_esb", act_as_user_id=user.id, is_active=True
    )
    db.add(integration)
    db.flush()
    return IntegrationKeyService(db).issue_key(integration)


class TestEnforcement:
    def test_granted_permission_passes(self, client, key):
        assert client.get("/allowed", headers={"X-API-Key": key}).status_code == 200

    def test_withheld_permission_is_403(self, client, key):
        # The behaviour that did not exist before: holding a valid key is no
        # longer sufficient on its own.
        res = client.get("/forbidden", headers={"X-API-Key": key})
        assert res.status_code == 403

    def test_no_key_is_401_not_403(self, client, key):
        # Unauthenticated and unauthorised are different answers; collapsing
        # them makes a misconfigured integration undiagnosable.
        assert client.get("/allowed").status_code == 401

    def test_invalid_key_is_401(self, client, key):
        assert client.get("/allowed", headers={"X-API-Key": "sk_bogus"}).status_code == 401

    def test_403_body_does_not_leak_the_key(self, client, key):
        res = client.get("/forbidden", headers={"X-API-Key": key})
        assert key not in res.text

    def test_403_names_the_permission_so_the_gap_is_diagnosable(self, client, key):
        # An operator seeing a 403 needs to know which grant is missing;
        # otherwise fixing an integration role is guesswork.
        res = client.get("/forbidden", headers={"X-API-Key": key})
        assert _WITHHELD in res.text


class TestPrincipalStillResolved:
    def test_the_guard_returns_the_principal_for_downstream_use(self, db, key):
        # Endpoints read current_user for created_by; the guard must pass the
        # resolved principal through, not just gate access.
        app = FastAPI()

        @app.get("/who")
        def who(user: dict = Depends(require_external_permission(_GRANTED))):
            return user

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app, raise_server_exceptions=False)

        body = client.get("/who", headers={"X-API-Key": key}).json()
        assert body["email"] == "esb@integrations.local"
        assert body["id"] != "system"
        assert body["integration_name"] == "foundryx-esb"
