"""USER-ROLES-STABLE: Edit user must not re-create role/company rows; primary role is deterministic.

UAC: documentation/plans/identity/user-roles-stable-08nov-acceptance-criteria.md

Every row in one test transaction shares ``now()``, so seeds set ``assigned_at`` / ``created_at``
explicitly wherever ordering is under test.

Run: SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest tests/test_user_roles_stable.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.company import Company, UserCompany
from app.models.user import User, UserRole, UserRoleAssignment
from app.services.user_service import UserService

T0 = datetime(2026, 1, 1, 9, 0, 0)


@pytest.fixture
def db():
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


def _role(db, slug: str) -> UserRole:
    r = UserRole(id=str(uuid.uuid4()), slug=f"zzt-{slug}-{uuid.uuid4().hex[:6]}", name=f"ZZT {slug} {uuid.uuid4().hex[:6]}")
    db.add(r)
    db.flush()
    return r


def _user(db) -> User:
    u = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@t.com", name="ZZT", status="ACTIVE")
    db.add(u)
    db.flush()
    return u


def _assign(db, user, role, at, row_id=None) -> UserRoleAssignment:
    a = UserRoleAssignment(id=row_id or str(uuid.uuid4()), user_id=user.id, role_id=role.id, assigned_at=at)
    db.add(a)
    db.flush()
    return a


def _rows(db, user_id) -> dict[str, tuple[str, datetime]]:
    db.expire_all()
    return {
        str(a.role_id): (str(a.id), a.assigned_at)
        for a in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).all()
    }


def _primary_role_id(db, user_id) -> str | None:
    from app.dependencies import _load_user_dict_from_db

    db.expire_all()
    d = _load_user_dict_from_db(db, user_id)
    return str(d["role_id"]) if d and d["role_id"] else None


@pytest.fixture
def sales_then_admin(db):
    """Salesperson assigned first, Admin a day later: Salesperson is primary."""
    sales, admin = _role(db, "sales"), _role(db, "admin")
    user = _user(db)
    _assign(db, user, sales, T0)
    _assign(db, user, admin, T0 + timedelta(days=1))
    db.commit()
    return SimpleNamespace(user=user, sales=sales, admin=admin)


# AC-1
def test_saving_same_roles_keeps_rows_and_primary(db, sales_then_admin):
    s = sales_then_admin
    before = _rows(db, s.user.id)
    assert _primary_role_id(db, s.user.id) == s.sales.id

    # The FE sends every role id, in whatever order the multi-select holds them.
    UserService(db).set_user_roles(s.user.id, [s.admin.id, s.sales.id])

    assert _rows(db, s.user.id) == before
    assert _primary_role_id(db, s.user.id) == s.sales.id


# AC-2
def test_adding_role_keeps_existing_rows_and_primary(db, sales_then_admin):
    s = sales_then_admin
    extra = _role(db, "extra")
    db.commit()
    before = _rows(db, s.user.id)

    UserService(db).set_user_roles(s.user.id, [extra.id, s.admin.id, s.sales.id])

    after = _rows(db, s.user.id)
    assert set(after) == {s.sales.id, s.admin.id, extra.id}
    assert after[s.sales.id] == before[s.sales.id]
    assert after[s.admin.id] == before[s.admin.id]
    assert _primary_role_id(db, s.user.id) == s.sales.id


# AC-3
def test_removing_primary_picks_next_oldest(db, sales_then_admin):
    s = sales_then_admin
    extra = _role(db, "extra")
    _assign(db, s.user, extra, T0 + timedelta(days=2))
    db.commit()
    before = _rows(db, s.user.id)

    UserService(db).set_user_roles(s.user.id, [extra.id, s.admin.id])

    after = _rows(db, s.user.id)
    assert set(after) == {s.admin.id, extra.id}
    assert after[s.admin.id] == before[s.admin.id]
    assert after[extra.id] == before[extra.id]
    assert _primary_role_id(db, s.user.id) == s.admin.id


def test_set_user_roles_skips_unknown_and_duplicate_ids(db, sales_then_admin):
    s = sales_then_admin
    UserService(db).set_user_roles(s.user.id, [s.sales.id, s.sales.id, str(uuid.uuid4())])
    assert set(_rows(db, s.user.id)) == {s.sales.id}


def test_set_user_roles_empty_clears(db, sales_then_admin):
    s = sales_then_admin
    UserService(db).set_user_roles(s.user.id, [])
    assert _rows(db, s.user.id) == {}


# AC-4: a tie on assigned_at resolves by assignment id ascending, in every lookup.
@pytest.fixture
def tied(db):
    """Two assignments at the same instant. The row with the HIGHER id is inserted first, so a
    lookup without the id tie-break tends to return it (heap order)."""
    low, high = _role(db, "low"), _role(db, "high")
    user = _user(db)
    _assign(db, user, high, T0, row_id="ffffffff-0000-0000-0000-000000000000")
    _assign(db, user, low, T0, row_id="00000000-0000-0000-0000-000000000000")
    db.commit()
    return SimpleNamespace(user=user, low=low, high=high)


def test_tie_break_dependencies(db, tied):
    from app.dependencies import _load_user_dict_from_db

    d = _load_user_dict_from_db(db, tied.user.id)
    assert str(d["role_id"]) == tied.low.id
    assert d["role_name"] == tied.low.slug


def test_tie_break_login_response(db, tied, monkeypatch):
    from app.services import phone_signin_service

    monkeypatch.setattr(phone_signin_service, "home_path_for_user", lambda db, user: "/")
    resp = phone_signin_service.build_login_response(db, tied.user, SimpleNamespace(token="t"))
    assert resp.role_id == tied.low.id
    assert resp.role_name == tied.low.name
    assert resp.role_ids == [tied.low.id, tied.high.id]


def test_tie_break_impersonation_target(db, tied):
    from app.api.v1.user_management.impersonation import _serialize_target

    assert _serialize_target(db, tied.user).role_name == tied.low.slug


def test_tie_break_dev_login(db, tied):
    from app.api.v1.dev_login import _role_name

    assert _role_name(db, tied.user.id) == tied.low.name


def test_primary_order_helper_is_assigned_at_then_id():
    cols = [str(c) for c in UserRoleAssignment.primary_order()]
    assert cols == [
        "user_role_assignments.assigned_at ASC",
        "user_role_assignments.id ASC",
    ]


# AC-5: companies
@pytest.fixture
def two_companies(db):
    srt = Company(id=str(uuid.uuid4()), name="ZZT Sorento", code=f"ZZS{uuid.uuid4().hex[:4]}")
    mch = Company(id=str(uuid.uuid4()), name="ZZT Mocha", code=f"ZZM{uuid.uuid4().hex[:4]}")
    db.add_all([srt, mch])
    user = _user(db)
    db.add(UserCompany(user_id=user.id, company_id=srt.id, created_at=T0))
    db.add(UserCompany(user_id=user.id, company_id=mch.id, created_at=T0 + timedelta(days=1)))
    user.last_active_company_id = mch.id
    db.commit()
    return SimpleNamespace(user=user, srt=srt, mch=mch)


def _grants(db, user_id) -> dict[str, tuple[str, datetime]]:
    db.expire_all()
    return {
        str(g.company_id): (str(g.id), g.created_at)
        for g in db.query(UserCompany).filter(UserCompany.user_id == user_id).all()
    }


def test_saving_same_companies_keeps_rows(db, two_companies):
    c = two_companies
    before = _grants(db, c.user.id)
    UserService(db).set_user_companies(c.user.id, [c.mch.id, c.srt.id])
    assert _grants(db, c.user.id) == before
    db.refresh(c.user)
    assert str(c.user.last_active_company_id) == c.mch.id


def test_adding_and_removing_company_touches_only_those_rows(db, two_companies):
    c = two_companies
    third = Company(id=str(uuid.uuid4()), name="ZZT Third", code=f"ZZX{uuid.uuid4().hex[:4]}")
    db.add(third)
    db.commit()
    before = _grants(db, c.user.id)

    UserService(db).set_user_companies(c.user.id, [c.srt.id, third.id, str(uuid.uuid4())])

    after = _grants(db, c.user.id)
    assert set(after) == {c.srt.id, third.id}
    assert after[c.srt.id] == before[c.srt.id]
    db.refresh(c.user)
    # The active grant (MCH) was revoked: repoint to the first remaining id sent.
    assert str(c.user.last_active_company_id) == c.srt.id
