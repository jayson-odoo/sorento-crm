"""
RBAC tests: multi-role aggregation, superadmin bypass, deny-by-default, role-permission persistence.
Run with: pytest tests/test_rbac.py -v
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.user import User, UserRole, UserRoleAssignment, UserPermission, UserRolePermission
from app.services.user_service import UserPermissionService


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for unit tests. Requires DB schema to be created."""
    from app.database import Base
    from app import models  # noqa: F401 - register all model tables
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def rbac_data(db_session: Session):
    """Create minimal RBAC data: 2 roles, 2 permissions, 1 user with both roles."""
    perm1 = UserPermission(id="p1", slug="test.a.view", name="View A", description="")
    perm2 = UserPermission(id="p2", slug="test.b.view", name="View B", description="")
    db_session.add_all([perm1, perm2])
    role1 = UserRole(id="r1", slug="role1", name="Role 1", description="", is_protected=False, is_default=False)
    role2 = UserRole(id="r2", slug="superadmin", name="Superadmin", description="", is_protected=False, is_default=False)
    db_session.add_all([role1, role2])
    db_session.flush()
    db_session.add(UserRolePermission(role_id=role1.id, permission_id=perm1.id))
    db_session.add(UserRolePermission(role_id=role2.id, permission_id=perm2.id))
    user = User(
        id="u1",
        email="u1@test.com",
        name="User 1",
        role_id=role1.id,
        status="ACTIVE",
    )
    db_session.add(user)
    db_session.add(UserRoleAssignment(user_id=user.id, role_id=role1.id))
    db_session.add(UserRoleAssignment(user_id=user.id, role_id=role2.id))
    db_session.commit()
    return {"user_id": user.id, "role1_id": role1.id, "role2_id": role2.id, "perm1_id": perm1.id, "perm2_id": perm2.id}


def test_get_user_role_ids_multi_role(db_session: Session, rbac_data: dict):
    """User with two assignments has two role IDs."""
    svc = UserPermissionService(db_session)
    role_ids = svc.get_user_role_ids(rbac_data["user_id"])
    assert len(role_ids) == 2
    assert set(role_ids) == {rbac_data["role1_id"], rbac_data["role2_id"]}


def test_get_user_permission_slugs_aggregation(db_session: Session, rbac_data: dict):
    """Effective permissions are union of all roles (user has perm from role1 and role2)."""
    svc = UserPermissionService(db_session)
    slugs = svc.get_user_permission_slugs(rbac_data["user_id"])
    assert "test.a.view" in slugs
    assert "test.b.view" in slugs


def test_superadmin_bypass(db_session: Session, rbac_data: dict):
    """User with superadmin role has any permission."""
    svc = UserPermissionService(db_session)
    assert svc.check_user_has_permission(rbac_data["user_id"], "any.perm.here") is True
    assert svc.check_user_has_permission(rbac_data["user_id"], "test.a.view") is True


def test_deny_without_permission(db_session: Session, rbac_data: dict):
    """User with only role1 is denied permissions they don't have (deny-by-default)."""
    svc = UserPermissionService(db_session)
    u3_id = "u3"
    u_only_r1 = User(
        id=u3_id,
        email="u3@test.com",
        name="User 3",
        role_id=rbac_data["role1_id"],
        status="ACTIVE",
    )
    db_session.add(u_only_r1)
    db_session.add(UserRoleAssignment(user_id=u3_id, role_id=rbac_data["role1_id"]))
    db_session.commit()
    assert svc.check_user_has_permission(u3_id, "test.a.view") is True
    assert svc.check_user_has_permission(u3_id, "test.b.view") is False
    assert svc.check_user_has_permission(u3_id, "other.perm") is False
