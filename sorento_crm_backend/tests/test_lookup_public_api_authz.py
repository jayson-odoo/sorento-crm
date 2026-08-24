"""Bug B - lookup read endpoints must be readable by any AUTHENTICATED user.

Plan: PLAN-fix-broken-creates-and-lookup403.md (Bug B). The 3 read endpoints
(/by-binding, /{set_key}/options, /resolve) drop the
`master_data.lookup_sets.view` gate → authenticated-only. The admin SETS screen
keeps its own gate (regression pin B-4).

Fixture seeds a NON-admin user with no permission grants and seeds lookup data
directly in the DB (the admin route would 403 for this user).
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_NONADMIN_USER_ID = "65206cac-d387-535e-9c20-9ad852f750f8"
_NONADMIN_ROLE_ID = "c7ff2740-4436-5b42-8823-27a576fc1fad"
_SET_KEY = "forms_form_type"


def _seed_nonadmin_and_data(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding

    # A role with ZERO permission grants (not superadmin/admin).
    role = UserRole(
        id=_NONADMIN_ROLE_ID,
        slug="forms_user",
        name="Forms User",
        description="",
        is_protected=False,
        is_default=False,
    )
    db.add(role)
    db.flush()

    user = User(id=_NONADMIN_USER_ID, email="user@test.com", name="User", status="ACTIVE")
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(user_id=_NONADMIN_USER_ID, role_id=_NONADMIN_ROLE_ID))

    # Seed lookup set + option + keyword + binding (forms.form_type) directly.
    set_id = str(uuid.uuid4())
    db.add(LookupSet(id=set_id, set_key=_SET_KEY, name="Form Type", is_active=True))
    db.flush()
    opt_id = str(uuid.uuid4())
    db.add(LookupOption(id=opt_id, set_id=set_id, value="enquiry", label="Enquiry", is_active=True))
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=opt_id, keyword="ask"))
    db.add(LookupBinding(id=str(uuid.uuid4()), set_id=set_id, table_name="forms", column_name="form_type"))
    db.commit()


@pytest.fixture
def nonadmin_client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    with blank_session() as db:
        _seed_nonadmin_and_data(db)

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": _NONADMIN_USER_ID, "email": "user@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


# ---- B-1 / B-2 / B-3 : non-admin can READ lookup options ----

def test_by_binding_200_for_nonadmin(nonadmin_client):
    r = nonadmin_client.get("/api/v1/lookup/by-binding?table=forms&column=form_type")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["set_key"] == _SET_KEY
    assert any(o["value"] == "enquiry" for o in body["options"])


def test_options_200_for_nonadmin(nonadmin_client):
    r = nonadmin_client.get(f"/api/v1/lookup/{_SET_KEY}/options")
    assert r.status_code == 200, r.text
    assert any(o["value"] == "enquiry" for o in r.json())


def test_resolve_200_for_nonadmin(nonadmin_client):
    r = nonadmin_client.post(
        "/api/v1/lookup/resolve", json={"set_key": _SET_KEY, "raw": "ask"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "enquiry"


# ---- B-4 : regression pin - admin SETS screen stays gated ----

def test_admin_sets_list_403_for_nonadmin(nonadmin_client):
    r = nonadmin_client.get("/api/v1/master-data/lookup-sets/")
    assert r.status_code == 403, r.text


# ---- B-5 : unauthenticated is rejected ----

def test_by_binding_401_unauthenticated():
    """No user override → real auth runs → no token → 401."""
    from app.dependencies import get_db

    with blank_session() as db:
        _seed_nonadmin_and_data(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                r = c.get("/api/v1/lookup/by-binding?table=forms&column=form_type")
                assert r.status_code == 401, r.text
        finally:
            app.dependency_overrides.clear()
