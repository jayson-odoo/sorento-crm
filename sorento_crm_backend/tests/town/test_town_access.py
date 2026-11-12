"""TOWN-V2: only admins see the Town (owner, 10 Nov ~16:55). The gate is the dedicated permission
`dashboards.town.view`, granted to the `admin` and `superadmin` roles by migration and by the registry
seed, not a role-name check: any role the owner grants it to sees the Town too. Without it, the
snapshot endpoint answers 403, wallboard mode included.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.town.test_town_snapshot_endpoint import (  # noqa: F401  (fixtures)
    SLUG, TOWN, URL, _client, _real_rbac_client, _today, _user, _with_role, db, stored,
)

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "town_0001_view_perm.py"


def test_the_permission_is_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert TOWN in {p["slug"] for p in PERMISSION_REGISTRY}


def test_the_migration_grants_it_to_the_admin_roles_only():
    spec = importlib.util.spec_from_file_location("town_0001_view_perm", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert [slug for slug, *_ in mod._PERMS] == [TOWN]
    assert set(mod._GRANT_ROLES) == {"admin", "superadmin"}
    assert len(mod.revision) <= 32


@pytest.mark.parametrize("params", [{}, {"mode": "wallboard"}])
def test_a_staff_user_without_the_permission_gets_403(db, stored, params):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:  # sales reports, but no Town
        r = client.get(URL, params=params)
    assert r.status_code == 403
    assert "today" not in r.text


def test_a_staff_role_without_the_grant_gets_403_for_real(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 403


def test_a_role_granted_the_permission_sees_the_town(db, stored):
    import uuid

    from app.models.user import UserPermission, UserRole, UserRolePermission

    principal = _user(db, DEFAULT_COMPANY_ID)
    perm = db.query(UserPermission).filter(UserPermission.slug == TOWN).first()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=TOWN, name="View the Town")
        db.add(perm)
        db.flush()
    role = db.query(UserRole).filter(UserRole.slug == "zzt_staff_role").one()
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
    db.flush()
    from app.services.user_service import invalidate_rbac_cache

    invalidate_rbac_cache()
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert "amount" not in r.json()["today"]  # Town access is not sales-report access


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_admins_see_the_town_and_the_wallboard(db, stored, role):
    principal = _user(db, DEFAULT_COMPANY_ID)
    _with_role(db, principal, role)
    with _real_rbac_client(db, principal) as client:
        assert client.get(URL).status_code == 200
        assert client.get(URL, params={"mode": "wallboard"}).status_code == 200
