"""Migration `sat_0001_stock_ask_done` (lane SALES-ASKS-TODO): AC-ST101, AC-ST102, AC-ST201.

Runs inside one outer transaction that is rolled back (shape of
`test_migration_sa2_0005_stock_ask_source.py`); the columns are dropped first so the
"before" state is real whatever the shared schema already holds.
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
NAME = "sat_0001_stock_ask_done"
SORENTO = "00000000-0000-0000-0000-000000000001"
SLUGS = (
    "sales.customer_asks.view",
    "sales.customer_asks.add",
    "sales.customer_asks.edit",
    "sales.customer_asks.delete",
    "sales.customer_asks.view_all",
)


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{NAME}", VERSIONS / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _drop_columns(conn):
    conn.execute(
        sa.text(
            "ALTER TABLE stock_asks DROP COLUMN IF EXISTS done_at, "
            "DROP COLUMN IF EXISTS done_by_user_id, DROP COLUMN IF EXISTS done_by_contact_id"
        )
    )


def _fk(conn, column: str):
    """(referred table, ON DELETE action) of the FK on stock_asks.<column>, by constraint lookup."""
    row = conn.execute(
        sa.text(
            "SELECT c.confrelid::regclass::text, c.confdeltype FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
            "WHERE c.contype = 'f' AND c.conrelid = 'stock_asks'::regclass AND a.attname = :col"
        ),
        {"col": column},
    ).first()
    return None if row is None else (row[0], row[1])


def _columns(conn) -> dict:
    return {c["name"]: c for c in sa.inspect(conn).get_columns("stock_asks")}


def _insert_ask(conn, state: str) -> str:
    ask_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO stock_asks (id, company_id, product_code, quantity, branch, answer_summary, state, "
            "created_at, updated_at) VALUES (:id, :co, 'ZZT-SRT', 1, 'in_stock', 'a', :state, "
            "TIMESTAMP '2026-09-20 01:00:00', TIMESTAMP '2026-09-21 02:03:04')"
        ),
        {"id": ask_id, "co": SORENTO, "state": state},
    )
    return ask_id


def test_revision_fits_alembic_version_and_sits_on_merge_29sep_batch6():
    module = _load()
    assert module.revision == NAME
    assert len(module.revision) <= 32
    assert module.down_revision == "merge_29sep_batch6"


def test_columns_exist_and_rerun_is_noop():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            _drop_columns(conn)
            assert "done_at" not in _columns(conn)
            _run(conn, module.upgrade)
            _run(conn, module.upgrade)  # re-runnable
            cols = _columns(conn)
            assert cols["done_at"]["nullable"] is True
            assert isinstance(cols["done_at"]["type"], sa.TIMESTAMP)
            assert cols["done_at"]["type"].timezone is False
            assert "done_by" not in cols  # a name is a label, never a column
            assert cols["done_by_user_id"]["nullable"] is True
            assert isinstance(cols["done_by_user_id"]["type"], sa.String)
            assert cols["done_by_contact_id"]["nullable"] is True
            assert isinstance(cols["done_by_contact_id"]["type"], sa.Text)
            assert _fk(conn, "done_by_user_id") == ("users", "n")  # ON DELETE SET NULL
            assert _fk(conn, "done_by_contact_id") == ("respond_contacts", "n")
        finally:
            outer.rollback()


def test_backfill_stamps_done_rows():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            _drop_columns(conn)
            done_id = _insert_ask(conn, "done")
            open_id = _insert_ask(conn, "open")
            _run(conn, module.upgrade)
            rows = {
                r.id: r
                for r in conn.execute(
                    sa.text("SELECT id::text AS id, done_at, done_by_user_id, done_by_contact_id, updated_at FROM stock_asks WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": [done_id, open_id]},
                )
            }
            done, opened = rows[done_id], rows[open_id]
            assert done.done_at == done.updated_at
            assert done.done_by_user_id is None and done.done_by_contact_id is None
            assert opened.done_at is None
            assert opened.done_by_user_id is None and opened.done_by_contact_id is None
        finally:
            outer.rollback()


def _role(conn, slug: str) -> str:
    existing = conn.execute(sa.text("SELECT id FROM user_roles WHERE slug = :s"), {"s": slug}).scalar()
    if existing:
        return existing
    rid = str(uuid.uuid4())
    conn.execute(
        sa.text("INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) VALUES (:id, :s, :n, false, false, false)"),
        {"id": rid, "s": slug, "n": f"{slug}-{rid[:6]}"},
    )
    return rid


def _grant(conn, role_id: str, slug: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "SELECT gen_random_uuid()::text, :s, :s, :s, now() WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :s)"
        ),
        {"s": slug},
    )
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
                "WHERE rp.role_id = :r AND p.slug LIKE 'sales.customer_asks.%'"
            ),
            {"r": role_id},
        )
    }


def test_permissions_seeded_and_swept():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.execute(sa.text("DELETE FROM user_permissions WHERE slug LIKE 'sales.customer_asks.%'"))
            admin = _role(conn, "admin")
            superadmin = _role(conn, "superadmin")
            sales_role = _role(conn, f"zzt_sales_{uuid.uuid4().hex[:6]}")
            integration = _role(conn, f"integration_zzt_{uuid.uuid4().hex[:6]}")
            plain = _role(conn, f"zzt_plain_{uuid.uuid4().hex[:6]}")
            _grant(conn, sales_role, "sales.opportunities.view")
            _grant(conn, integration, "sales.opportunities.view")
            _grant(conn, plain, "sales.targets.view")

            _run(conn, module.upgrade)
            _run(conn, module.upgrade)  # the sweep is re-runnable

            existing = {
                r[0] for r in conn.execute(sa.text("SELECT slug FROM user_permissions WHERE slug LIKE 'sales.customer_asks.%'"))
            }
            assert set(SLUGS) <= existing
            # AC-ST201 (security review B1): a salesperson sees their own list and a leader their
            # team, so the opportunities sweep grants view and edit, never view_all.
            assert _held(conn, admin) == set(SLUGS)
            assert _held(conn, superadmin) == set(SLUGS)
            assert _held(conn, sales_role) == {"sales.customer_asks.view", "sales.customer_asks.edit"}
            assert "sales.customer_asks.view_all" not in _held(conn, sales_role)
            assert _held(conn, integration) == set()
            assert _held(conn, plain) == set()
        finally:
            outer.rollback()
