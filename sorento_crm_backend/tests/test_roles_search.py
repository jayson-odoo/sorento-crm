"""Roles search filter (UserRoleService.list_roles query=...).

CHANGE 9 (separate fix): GET /api/v1/user-management/roles/ + list_roles now
ILIKE-filter name + slug (case-insensitive partial). Endpoint is JWT-only, so this
is a service-level test against the sqlite harness.

Run:
    venv/bin/pytest tests/test_roles_search.py -q
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.lookup import LookupBinding  # validator listener checks this table
from app.models.user import UserPermission, UserRole, UserRolePermission
from app.services.user_service import UserRoleService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            UserRole.__table__,
            UserPermission.__table__,
            UserRolePermission.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_role(db, slug, name):
    db.add(UserRole(id=str(uuid.uuid4()), slug=slug, name=name))
    db.commit()


@pytest.fixture
def roles(db):
    _seed_role(db, "admin", "Administrator")
    _seed_role(db, "sales_manager", "Sales Manager")
    _seed_role(db, "warehouse", "Warehouse Operator")
    return db


def test_query_filters_by_name_case_insensitive_partial(roles):
    out = UserRoleService(roles).list_roles(query="manager")
    names = sorted(r.name for r in out["data"])
    assert names == ["Sales Manager"]
    assert out["pagination"]["total"] == 1
    assert out["empty"] is False


def test_query_filters_by_slug(roles):
    out = UserRoleService(roles).list_roles(query="warehouse")
    slugs = sorted(r.slug for r in out["data"])
    assert slugs == ["warehouse"]
    assert out["pagination"]["total"] == 1


def test_query_is_case_insensitive(roles):
    out = UserRoleService(roles).list_roles(query="ADMIN")
    assert [r.slug for r in out["data"]] == ["admin"]


def test_query_matches_name_or_slug_partial(roles):
    # "sale" matches the slug 'sales_manager' AND the name 'Sales Manager' (same row).
    out = UserRoleService(roles).list_roles(query="sale")
    assert {r.slug for r in out["data"]} == {"sales_manager"}


def test_none_query_returns_all_unfiltered(roles):
    out = UserRoleService(roles).list_roles(query=None)
    assert out["pagination"]["total"] == 3
    assert len(out["data"]) == 3


def test_empty_query_returns_all_unfiltered(roles):
    out = UserRoleService(roles).list_roles(query="")
    assert out["pagination"]["total"] == 3


def test_no_match_returns_empty_set(roles):
    out = UserRoleService(roles).list_roles(query="zzz-nomatch")
    assert out["data"] == []
    assert out["pagination"]["total"] == 0
    assert out["empty"] is True


def test_filtered_total_reflects_filtered_set_not_all(roles):
    """The paginated total must be the filtered count, not the full table count."""
    _seed_role(roles, "another_manager", "Another Manager")
    out = UserRoleService(roles).list_roles(query="manager", page=1, limit=1)
    # Two roles match 'manager'; total reflects the filtered set even with limit=1.
    assert out["pagination"]["total"] == 2
    assert len(out["data"]) == 1
