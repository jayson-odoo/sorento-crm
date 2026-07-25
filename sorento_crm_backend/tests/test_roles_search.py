"""Roles search filter (UserRoleService.list_roles query=...).

CHANGE 9 (separate fix): GET /api/v1/user-management/roles/ + list_roles now
ILIKE-filter name + slug (case-insensitive partial). Endpoint is JWT-only, so this
is a service-level test against a blank Postgres schema.

ILIKE is the point of the change, and sqlite's LIKE is case-insensitive for
ASCII by accident -- so the old harness could not tell ILIKE from LIKE. Postgres
can.

Run:
    venv/bin/pytest tests/test_roles_search.py -q
"""
from __future__ import annotations

import uuid

import pytest

from app.models.user import UserRole
from app.services.user_service import UserRoleService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


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
