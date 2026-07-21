"""Tests for admin impersonation: routes, validation, and audit-actor swap."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite doesn't know JSONB. Tests run on in-memory SQLite, so map it to JSON.
@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_element, _compiler, **_kw):
    return "JSON"


from app.database import Base
from app.main import app  # registers all routers, dependencies, models
from app.audit_context import set_audit_context
from app.dependencies import get_current_user, get_db, get_real_user
from app.models.audit import AuditLog
from app.models.impersonation import ImpersonationSession
from app.models.lookup import LookupBinding
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.audit_service import _swap_actor_fields_during_impersonation


def _seed_role(db: Session, *, role_id: str, slug: str) -> UserRole:
    row = db.query(UserRole).filter(UserRole.id == role_id).first()
    if row:
        return row
    row = UserRole(id=role_id, slug=slug, name=slug.title(), is_protected=False, is_default=False)
    db.add(row)
    db.flush()
    return row


def _seed_user(
    db: Session,
    *,
    user_id: str,
    email: str,
    role_id: str,
    status: str = "ACTIVE",
) -> User:
    user = User(id=user_id, email=email, name=email.split("@")[0], status=status)
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
    db.commit()
    return user


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create only the tables this test actually exercises — full Base.metadata
    # has duplicate-index collisions and pg-only types that don't compile on SQLite.
    only = [
        User.__table__,
        UserRole.__table__,
        UserRoleAssignment.__table__,
        UserPermission.__table__,
        UserRolePermission.__table__,
        ImpersonationSession.__table__,
        AuditLog.__table__,
        LookupBinding.__table__,  # global write-listener queries this on every insert
    ]
    Base.metadata.create_all(engine, tables=only)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    admin_role = _seed_role(db, role_id="r_admin", slug="admin")
    member_role = _seed_role(db, role_id="r_member", slug="member")
    db.commit()

    admin = _seed_user(db, user_id="22f43cd5-cfe1-5bd1-9197-ed029698989d", email="admin1@test.com", role_id=admin_role.id)
    target = _seed_user(db, user_id="a1cb11f1-0c6e-5ec2-99aa-48ca3cc1a35e", email="user1@test.com", role_id=member_role.id)
    other_admin = _seed_user(db, user_id="5f796e60-982f-5377-92ea-6a1e43e1f82f", email="admin2@test.com", role_id=admin_role.id)
    inactive = _seed_user(
        db,
        user_id="234ff7d4-064f-5cda-90d5-48148bfc6954",
        email="user2@test.com",
        role_id=member_role.id,
        status="INACTIVE",
    )

    state = {"acting_as": admin.id}

    def _override_real_user():
        # Always returns whoever state["acting_as"] points at — represents the JWT principal.
        u = db.query(User).filter(User.id == state["acting_as"]).first()
        slug_row = (
            db.query(UserRole.slug)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == UserRole.id)
            .filter(UserRoleAssignment.user_id == u.id)
            .first()
        )
        return {
            "id": u.id,
            "email": u.email,
            "role_id": None,
            "name": u.name,
            "avatar": None,
            "status": u.status,
            "role_name": slug_row[0] if slug_row else None,
        }

    def _override_get_db():
        yield db

    app.dependency_overrides[get_real_user] = _override_real_user
    app.dependency_overrides[get_current_user] = _override_real_user
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
            "db": db,
            "admin": admin,
            "target": target,
            "other_admin": other_admin,
            "inactive": inactive,
            "state": state,
        }

    app.dependency_overrides.clear()
    db.close()


def test_start_requires_admin(api):
    api["state"]["acting_as"] = api["target"].id
    r = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["admin"].id},
    )
    assert r.status_code == 403


def test_start_blocks_self(api):
    r = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["admin"].id},
    )
    assert r.status_code == 400


def test_start_blocks_admin_target(api):
    r = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["other_admin"].id},
    )
    assert r.status_code == 403


def test_start_blocks_inactive_target(api):
    r = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["inactive"].id},
    )
    assert r.status_code == 400


def test_start_success_creates_session_and_audit(api):
    db = api["db"]
    r = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["target"].id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_user"]["id"] == api["target"].id
    assert body["session_id"]

    rows = (
        db.query(ImpersonationSession)
        .filter(ImpersonationSession.admin_user_id == api["admin"].id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].ended_at is None

    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "impersonation_session")
        .all()
    )
    assert any(
        a.action == "CREATE"
        and a.user_id == api["admin"].id
        and a.description == "impersonation_start"
        for a in audit_rows
    )


def test_current_returns_active(api):
    api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["target"].id},
    )
    r = api["client"].get("/api/v1/user-management/impersonation/current")
    assert r.status_code == 200
    body = r.json()
    assert body and body["target_user"]["id"] == api["target"].id


def test_stop_ends_session_and_idempotent(api):
    db = api["db"]
    api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["target"].id},
    )
    r1 = api["client"].post("/api/v1/user-management/impersonation/stop")
    assert r1.status_code == 200
    assert r1.json()["ended"] is True
    r2 = api["client"].post("/api/v1/user-management/impersonation/stop")
    assert r2.status_code == 200
    assert r2.json()["ended"] is False

    end_audits = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "impersonation_session",
            AuditLog.description == "impersonation_end",
        )
        .all()
    )
    assert len(end_audits) == 1


@pytest.mark.skip(
    reason="Partial unique index `WHERE ended_at IS NULL` is postgres-only; "
    "SQLite enforces full unique on admin_user_id and rejects the second insert "
    "before commit even though the prior row was ended. Verify on Postgres."
)
def test_starting_again_auto_ends_prior(api):
    db = api["db"]
    r1 = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["target"].id},
    )
    assert r1.status_code == 200
    # Start a second session targeting the same user — defensive cleanup must end the first.
    r2 = api["client"].post(
        "/api/v1/user-management/impersonation/start",
        json={"target_user_id": api["target"].id},
    )
    assert r2.status_code == 200
    active = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.admin_user_id == api["admin"].id,
            ImpersonationSession.ended_at.is_(None),
        )
        .all()
    )
    assert len(active) == 1


def test_actor_swap_during_impersonation():
    """Unit test the listener: created_by_user_id == effective gets rewritten to real."""

    class _Stub:
        def __init__(self):
            self.created_by_user_id = "EFFECTIVE_USER"
            self.updated_by_user_id = "EFFECTIVE_USER"

    set_audit_context("REAL_ADMIN", None, effective_user_id="EFFECTIVE_USER")

    class _Session:
        def __init__(self, new, dirty):
            self.new = new
            self.dirty = dirty

    new_obj = _Stub()
    dirty_obj = _Stub()
    _swap_actor_fields_during_impersonation(_Session([new_obj], [dirty_obj]))
    assert new_obj.created_by_user_id == "REAL_ADMIN"
    assert new_obj.updated_by_user_id == "REAL_ADMIN"
    assert dirty_obj.updated_by_user_id == "REAL_ADMIN"
    # created_by_user_id only swapped on inserts
    assert dirty_obj.created_by_user_id == "EFFECTIVE_USER"


def test_actor_swap_noop_outside_impersonation():
    class _Stub:
        def __init__(self):
            self.created_by_user_id = "SOMEONE"

    set_audit_context("USER_A", None)  # effective defaults to user_id, no impersonation

    class _Session:
        def __init__(self, new, dirty):
            self.new = new
            self.dirty = dirty

    obj = _Stub()
    _swap_actor_fields_during_impersonation(_Session([obj], []))
    assert obj.created_by_user_id == "SOMEONE"


def test_actor_swap_skips_unrelated_value():
    """If service explicitly set a non-effective user, leave alone."""

    class _Stub:
        def __init__(self):
            self.created_by_user_id = "DIFFERENT_USER"

    set_audit_context("REAL_ADMIN", None, effective_user_id="EFFECTIVE_USER")

    class _Session:
        def __init__(self, new, dirty):
            self.new = new
            self.dirty = dirty

    obj = _Stub()
    _swap_actor_fields_during_impersonation(_Session([obj], []))
    assert obj.created_by_user_id == "DIFFERENT_USER"
