"""Route-level tests for /api/v1/master-data/lookup-sets.

Auth bypass pattern:
- Import app.main FIRST (before app.dependencies) to break the circular-import
  that exists in this codebase (app.models.__init__ → app.modules.runtime.guards
  → app.dependencies during partial initialisation).
- Inside the fixture, import get_current_user / get_db lazily (after app.main is
  already in sys.modules), override them on app.dependency_overrides.
- Seed a real 'superadmin' role so
  UserPermissionService.check_user_has_permission always returns True, bypassing
  every permission slug check without touching the guard logic.
- Run against a blank Postgres schema holding the whole real DDL, so no table
  list has to be maintained and the types are the production ones.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import — resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session


_SUPERADMIN_USER_ID = "test-admin-user"
_SUPERADMIN_ROLE_ID = "role-superadmin"


def _seed_superadmin(db: Session) -> None:
    """Seed a superadmin role + user so all RBAC checks are bypassed.

    UserPermissionService.check_user_has_permission short-circuits to True
    whenever a user has a role with slug='superadmin'. We only need User,
    UserRole and UserRoleAssignment rows for that to work.
    """
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

    # User has no role_id column — roles are via UserRoleAssignment
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
    """TestClient over an empty Postgres schema + superadmin user seeded.

    Blank rather than the live database on two counts: the seeded superadmin
    role slug is unique, and test_list_with_query_filter asserts an absolute
    result count that only holds on an empty slate.
    """
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db  # safe: app.main already loaded

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


# ---------------------------------------------------------------------------
# Basic set CRUD
# ---------------------------------------------------------------------------

def test_create_list_get_update_delete(client):
    # Create
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "region", "name": "Region"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["set_key"] == "region"
    assert body["name"] == "Region"
    set_id = body["id"]

    # List
    r = client.get("/api/v1/master-data/lookup-sets")
    assert r.status_code == 200
    list_body = r.json()
    assert "data" in list_body
    assert any(d["id"] == set_id for d in list_body["data"])

    # Get
    r = client.get(f"/api/v1/master-data/lookup-sets/{set_id}")
    assert r.status_code == 200
    assert r.json()["id"] == set_id

    # Update (PATCH)
    r = client.patch(
        f"/api/v1/master-data/lookup-sets/{set_id}",
        json={"name": "Regions"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Regions"

    # Delete
    r = client.delete(f"/api/v1/master-data/lookup-sets/{set_id}")
    assert r.status_code == 200

    # Confirm gone
    r = client.get(f"/api/v1/master-data/lookup-sets/{set_id}")
    assert r.status_code == 404


def test_duplicate_set_key_returns_409(client):
    client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "priority", "name": "Priority"},
    )
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "priority", "name": "Priority 2"},
    )
    assert r.status_code == 409, r.text


def test_invalid_set_key_returns_422(client):
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "Has Spaces!", "name": "Bad key"},
    )
    assert r.status_code == 422


def test_list_with_query_filter(client):
    client.post("/api/v1/master-data/lookup-sets", json={"set_key": "apple", "name": "Apple"})
    client.post("/api/v1/master-data/lookup-sets", json={"set_key": "banana", "name": "Banana"})

    r = client.get("/api/v1/master-data/lookup-sets?query=banana")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["set_key"] == "banana"


# ---------------------------------------------------------------------------
# Nested options
# ---------------------------------------------------------------------------

def test_options_crud(client):
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "status", "name": "Status"},
    )
    assert r.status_code == 201, r.text
    set_id = r.json()["id"]

    # Create option
    r = client.post(
        f"/api/v1/master-data/lookup-sets/{set_id}/options",
        json={"value": "open", "label": "Open", "keywords": [{"keyword": "opened"}]},
    )
    assert r.status_code == 201, r.text
    opt = r.json()
    assert opt["value"] == "open"
    option_id = opt["id"]

    # List options
    r = client.get(f"/api/v1/master-data/lookup-sets/{set_id}/options")
    assert r.status_code == 200
    assert any(o["id"] == option_id for o in r.json()["data"])

    # Update option
    r = client.patch(
        f"/api/v1/master-data/lookup-sets/{set_id}/options/{option_id}",
        json={"label": "Open (updated)"},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Open (updated)"

    # Delete option
    r = client.delete(f"/api/v1/master-data/lookup-sets/{set_id}/options/{option_id}")
    assert r.status_code == 200


def test_duplicate_option_value_returns_409(client):
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "colour", "name": "Colour"},
    )
    set_id = r.json()["id"]
    client.post(
        f"/api/v1/master-data/lookup-sets/{set_id}/options",
        json={"value": "red", "label": "Red"},
    )
    r = client.post(
        f"/api/v1/master-data/lookup-sets/{set_id}/options",
        json={"value": "red", "label": "Red Again"},
    )
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# Bindings — list only (create requires eligibility registry entry)
# ---------------------------------------------------------------------------

def test_bindings_list_empty_for_new_set(client):
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "region_x", "name": "Region X"},
    )
    set_id = r.json()["id"]

    r = client.get(f"/api/v1/master-data/lookup-sets/{set_id}/bindings")
    assert r.status_code == 200
    assert r.json() == []


def test_binding_create_unregistered_column_returns_422(client):
    r = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "region_y", "name": "Region Y"},
    )
    set_id = r.json()["id"]

    r = client.post(
        f"/api/v1/master-data/lookup-sets/{set_id}/bindings",
        json={"table_name": "nonexistent_table", "column_name": "nonexistent_col"},
    )
    # Unregistered column → handle_validation_error → 400 (not 422; Pydantic schema is valid)
    assert r.status_code == 400, r.text
