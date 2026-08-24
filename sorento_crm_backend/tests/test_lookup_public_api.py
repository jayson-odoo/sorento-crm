"""Route-level tests for /api/v1/lookup (public lookup endpoints).

Auth bypass pattern copied from test_lookup_sets_api.py.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session


_SUPERADMIN_USER_ID = "49e0b157-c9a7-5c2c-8dfc-f8cbf4175087"
_SUPERADMIN_ROLE_ID = "7c50d6db-8dce-555a-85a2-86cf7756f33f"
def _seed_superadmin(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    role = UserRole(
        id=_SUPERADMIN_ROLE_ID,
        slug="superadmin",
        name="Superadmin",
        description="",
        is_protected=True,
        is_default=False,
    )
    db.add(role)
    db.flush()

    user = User(
        id=_SUPERADMIN_USER_ID,
        email="admin@test.com",
        name="Admin",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()

    db.add(UserRoleAssignment(user_id=_SUPERADMIN_USER_ID, role_id=_SUPERADMIN_ROLE_ID))
    db.commit()


@pytest.fixture
def client():
    """TestClient over an empty Postgres schema carrying the full real DDL.

    Was in-memory SQLite with a hand-listed subset of tables. That list had to
    name every table the request path touches, which is brittle once app-wide
    flush listeners join in; the blank schema has all of them. Empty rather
    than the live database because this file seeds its own superadmin, whose
    role slug is unique.
    """
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    with blank_session() as db:
        _seed_superadmin(db)

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": _SUPERADMIN_USER_ID, "email": "admin@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user

        try:
            with TestClient(app) as c:
                yield c
        finally:
            app.dependency_overrides.clear()


def test_options_then_resolve(client):
    # Create a lookup set via the master-data admin route
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "region", "name": "Region"},
    )
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    # Add an option with a keyword
    client.post(
        f"/api/v1/master-data/lookup-sets/{set_id}/options",
        json={"value": "north", "label": "North", "keywords": [{"keyword": "up north"}]},
    )

    # /options endpoint returns the option with its keywords
    r = client.get("/api/v1/lookup/region/options")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["value"] == "north"
    assert "up north" in body[0]["keywords"]

    # /resolve - keyword match
    r = client.post(
        "/api/v1/lookup/resolve",
        json={"set_key": "region", "raw": "Up North"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "north"

    # /resolve - unresolvable input returns 404
    r = client.post(
        "/api/v1/lookup/resolve",
        json={"set_key": "region", "raw": "moon"},
    )
    assert r.status_code == 404, r.text
