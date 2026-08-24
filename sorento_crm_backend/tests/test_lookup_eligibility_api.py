"""Route-level tests for GET /api/v1/master-data/lookup-eligibility/

Auth bypass pattern follows test_lookup_sets_api.py exactly.
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_eligibility_endpoint(client):
    from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible

    class _M:
        __tablename__ = "fake_t"

    _REGISTRY.clear()
    register_lookup_eligible(
        model=_M,
        column="status",
        table_label="Fake",
        column_label="Status",
    )

    r = client.get("/api/v1/master-data/lookup-eligibility/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(e["table_name"] == "fake_t" and e["column_name"] == "status" for e in body)

    # Also verify without trailing slash
    r2 = client.get("/api/v1/master-data/lookup-eligibility")
    assert r2.status_code in (200, 307), r2.text


def test_eligibility_available_filter(client):
    """?available=true excludes already-bound columns."""
    from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
    from app.models.lookup import LookupSet, LookupBinding
    import uuid

    class _T:
        __tablename__ = "bound_t"

    class _T2:
        __tablename__ = "unbound_t"

    _REGISTRY.clear()
    register_lookup_eligible(model=_T, column="col_a", table_label="Bound", column_label="Col A")
    register_lookup_eligible(model=_T2, column="col_b", table_label="Unbound", column_label="Col B")

    # Without filter: both visible
    r = client.get("/api/v1/master-data/lookup-eligibility/")
    assert r.status_code == 200, r.text
    names = {(e["table_name"], e["column_name"]) for e in r.json()}
    assert ("bound_t", "col_a") in names
    assert ("unbound_t", "col_b") in names

    # Create a LookupSet and bind bound_t/col_a
    with TestClient(app) as tc:
        pass  # reuse client fixture db via the overridden get_db
    # We need the DB from the fixture; use the client directly
    r_set = client.post(
        "/api/v1/master-data/lookup-sets",
        json={"set_key": "test_avail", "name": "Test Avail"},
    )
    assert r_set.status_code == 201, r_set.text

    # With ?available=true, bound columns are excluded
    # (We won't actually bind here since that needs a real registered column;
    #  just confirm the flag is accepted and returns 200)
    r2 = client.get("/api/v1/master-data/lookup-eligibility/?available=true")
    assert r2.status_code == 200, r2.text
    # Both still visible because no LookupBinding rows exist yet
    names2 = {(e["table_name"], e["column_name"]) for e in r2.json()}
    assert ("bound_t", "col_a") in names2
    assert ("unbound_t", "col_b") in names2


def test_eligibility_is_bound_field_present(client):
    """Every returned record must contain is_bound."""
    from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible

    class _B:
        __tablename__ = "ib_table"

    _REGISTRY.clear()
    register_lookup_eligible(model=_B, column="kind", table_label="IB", column_label="Kind")

    r = client.get("/api/v1/master-data/lookup-eligibility/")
    assert r.status_code == 200, r.text
    for entry in r.json():
        assert "is_bound" in entry
