"""Migration `pp3_0001_salesperson_grants` (lane PORTAL-P3-ROLE-MENU): P3-01, P3-02.

CI builds the schema with create_all + stamp head, so this data migration never runs there:
the test executes upgrade/downgrade itself inside one rolled-back transaction (shape of
`test_migration_sat_0001.py`).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
NAME = "pp3_0001_salesperson_grants"
GRANTED = {"projects.projects.view_own", "sla_management.conversations.view_own"}
PRIOR = "sales.customer_asks.view"


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{NAME}", VERSIONS / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def _role(conn, slug: str) -> str:
    existing = conn.execute(sa.text("SELECT id FROM user_roles WHERE slug = :s"), {"s": slug}).scalar()
    if existing:
        return existing
    rid = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) "
            "VALUES (:id, :s, :n, false, false, false)"
        ),
        {"id": rid, "s": slug, "n": f"{slug}-{rid[:6]}"},
    )
    return rid


def _perm(conn, slug: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "SELECT gen_random_uuid()::text, :s, :s, :s, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :s)"
        ),
        {"s": slug},
    )


def _grant(conn, role_id: str, slug: str) -> None:
    _perm(conn, slug)
    conn.execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, :r, p.id, now() FROM user_permissions p WHERE p.slug = :s "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"r": role_id, "s": slug},
    )


def _held(conn, role_id: str) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT p.slug FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r"
            ),
            {"r": role_id},
        )
    }


def _count(conn, role_id: str) -> int:
    return conn.execute(
        sa.text("SELECT count(*) FROM user_role_permissions WHERE role_id = :r"), {"r": role_id}
    ).scalar()


def _clean(conn, sales_id: str) -> None:
    conn.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE role_id = :r AND permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:s))"
        ),
        {"r": sales_id, "s": list(GRANTED)},
    )


def test_revision_fits_alembic_version_and_sits_on_main_head():
    module = _load()
    assert module.revision == NAME
    assert len(module.revision) <= 32
    assert module.down_revision == "cim_0001_catalogue_photos"


def test_p3_01_p3_02_grants_exactly_two_slugs_to_salesperson_only_and_is_rerunnable():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            for slug in GRANTED | {PRIOR}:
                _perm(conn, slug)
            sales = _role(conn, "salesperson")
            admin = _role(conn, "admin")
            other = _role(conn, f"zzt_other_{uuid.uuid4().hex[:6]}")
            _clean(conn, sales)
            _grant(conn, sales, PRIOR)
            _grant(conn, other, PRIOR)
            before_admin, before_other = _held(conn, admin), _held(conn, other)
            before_sales_count = _count(conn, sales)

            _run(conn, module.upgrade)
            after_once = _count(conn, sales)
            _run(conn, module.upgrade)  # idempotent

            assert _held(conn, sales) == GRANTED | {PRIOR}
            assert _count(conn, sales) == after_once == before_sales_count + 2
            assert _held(conn, admin) == before_admin
            assert _held(conn, other) == before_other
        finally:
            outer.rollback()


def test_p3_02_downgrade_removes_exactly_those_two_pairs():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            for slug in GRANTED | {PRIOR}:
                _perm(conn, slug)
            sales = _role(conn, "salesperson")
            other = _role(conn, f"zzt_other_{uuid.uuid4().hex[:6]}")
            _clean(conn, sales)
            _grant(conn, sales, PRIOR)
            _grant(conn, other, "projects.projects.view_own")  # another role's pair must survive
            _run(conn, module.upgrade)
            assert _held(conn, sales) >= GRANTED

            _run(conn, module.downgrade)

            assert _held(conn, sales) & GRANTED == set()
            assert PRIOR in _held(conn, sales)
            assert "projects.projects.view_own" in _held(conn, other)
        finally:
            outer.rollback()
