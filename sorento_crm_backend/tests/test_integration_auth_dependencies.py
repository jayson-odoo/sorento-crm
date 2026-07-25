"""Slice 6 of AutoCount Group A — wiring the dependencies onto the resolver.

This is the change that touches live authentication. Per decision A6 there is
no env fallback to catch a mistake, so the behaviour is pinned at the dependency
level, exercised through a real FastAPI app rather than by calling the functions
directly.

  AC-AC-01  no identity or secret is read from environment variables at runtime
  AC-AC-02  each integration authenticates with its own key
  AC-AC-04  no ==/!= on a secret
  AC-AC-05a the principal is a real users row, never the string "system"
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# app.dependencies cannot be imported first -- doing so hits a pre-existing
# circular import (partially initialized app.dependencies). Importing app.main
# initialises the package fully, which is what the other TestClient suites do.
import app.main  # noqa: F401  isort:skip

from app.dependencies import get_db, get_external_api_user
from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.integration_key_service import IntegrationKeyService
from tests._pg_fixture import pg_empty_schema

_TABLES = [User.__table__, Integration.__table__, IntegrationApiKey.__table__]


@pytest.fixture()
def db():
    """An empty Postgres schema.

    Empty rather than the live database because these tests seed integrations
    under fixed names ("n8n") that the real table already holds, and Postgres
    enforces the unique constraint sqlite's throwaway engine never saw.
    """
    with pg_empty_schema(_TABLES) as session:
        yield session


@pytest.fixture()
def client(db):
    app = FastAPI()

    @app.get("/probe")
    def probe(current_user: dict = Depends(get_external_api_user)):
        return current_user

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=False)


def _integration(db, name="n8n"):
    user = User(
        email=f"{name}@integrations.local",
        name=f"Integration: {name}",
        status="ACTIVE",
        is_integration=True,
    )
    db.add(user)
    db.flush()
    row = Integration(name=name, type="automation", act_as_user_id=user.id, is_active=True)
    db.add(row)
    db.flush()
    return row


class TestExternalApiUserDependency:
    def test_valid_key_resolves_to_the_real_principal(self, client, db):
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)

        res = client.get("/probe", headers={"X-API-Key": key})

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == integration.act_as_user_id
        # The defect being fixed: this used to be the literal string "system".
        assert body["id"] != "system"
        assert body["integration_name"] == "n8n"

    def test_missing_key_is_401(self, client, db):
        _integration(db)
        assert client.get("/probe").status_code == 401

    def test_unknown_key_is_401(self, client, db):
        _integration(db)
        assert client.get("/probe", headers={"X-API-Key": "sk_nope"}).status_code == 401

    def test_revoked_key_is_401(self, client, db):
        integration = _integration(db)
        svc = IntegrationKeyService(db)
        key = svc.issue_key(integration)
        svc.revoke_key(db.query(IntegrationApiKey).filter_by(integration_id=integration.id).one())

        assert client.get("/probe", headers={"X-API-Key": key}).status_code == 401

    def test_revoking_one_integration_leaves_the_other_working(self, client, db):
        # AC-AC-02 -- impossible with a single shared env key.
        svc = IntegrationKeyService(db)
        n8n, esb = _integration(db, "n8n"), _integration(db, "esb")
        n8n_key, esb_key = svc.issue_key(n8n), svc.issue_key(esb)

        svc.revoke_key(
            db.query(IntegrationApiKey).filter_by(integration_id=n8n.id).one()
        )

        assert client.get("/probe", headers={"X-API-Key": n8n_key}).status_code == 401
        assert client.get("/probe", headers={"X-API-Key": esb_key}).status_code == 200

    def test_env_key_no_longer_authenticates(self, client, db, monkeypatch):
        # AC-AC-01 / A6: the env var must not be a runtime authentication path.
        # After cutover its value is only meaningful as a seeded hash.
        from app.config import settings

        monkeypatch.setattr(settings, "external_api_key", "env-secret-value", raising=False)
        _integration(db)

        res = client.get("/probe", headers={"X-API-Key": "env-secret-value"})
        assert res.status_code == 401

    def test_seeded_legacy_key_still_authenticates(self, client, db, monkeypatch):
        # The other half of AC-AC-09: the same value keeps working, but because
        # its hash was seeded, not because anything reads the env var.
        from app.config import settings
        from app.services.integration_key_crypto import hash_api_key, key_prefix

        monkeypatch.setattr(settings, "external_api_key", "env-secret-value", raising=False)
        legacy = _integration(db, "legacy-shared-key")
        db.add(
            IntegrationApiKey(
                integration_id=legacy.id,
                key_hash=hash_api_key("env-secret-value"),
                key_prefix=key_prefix("env-secret-value"),
            )
        )
        db.flush()

        res = client.get("/probe", headers={"X-API-Key": "env-secret-value"})
        assert res.status_code == 200
        assert res.json()["integration_name"] == "legacy-shared-key"

    def test_refusal_body_does_not_echo_the_key(self, client, db):
        _integration(db)
        secret = "sk_secret_that_must_not_appear"
        res = client.get("/probe", headers={"X-API-Key": secret})
        assert secret not in res.text
