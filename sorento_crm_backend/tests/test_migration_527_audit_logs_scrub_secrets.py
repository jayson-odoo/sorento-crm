"""Migration `527_audit_logs_scrub_secrets` (issue #1281): stored secrets are stripped.

Rows are seeded and the migration's `upgrade()` runs through a real alembic
`Operations` context on one connection, inside a transaction that is rolled back.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine
from app.services import audit_service

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
NAME = "527_audit_logs_scrub_secrets"


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{NAME}", VERSIONS / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_fits_alembic_version():
    module = _load()
    assert len(module.revision) <= 32
    assert module.down_revision == "sales_0002_team_leader"


def test_key_list_matches_the_listener_deny_list():
    assert set(_load().SECRET_KEYS) == set(getattr(audit_service, "AUDIT_SECRET_KEYS", ()))


def _insert(conn, old, new):
    row_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO audit_logs (id, entity_type, entity_id, action, changed_at, old_values, new_values) "
            "VALUES (:id, 'users', :eid, 'UPDATE', now(), CAST(:old AS jsonb), CAST(:new AS jsonb))"
        ),
        {"id": row_id, "eid": str(uuid.uuid4()),
         "old": None if old is None else json.dumps(old),
         "new": None if new is None else json.dumps(new)},
    )
    return row_id


def _values(conn, row_id):
    return conn.execute(
        sa.text("SELECT old_values, new_values FROM audit_logs WHERE id = :id"), {"id": row_id}
    ).one()


def test_upgrade_strips_password_and_sign_token_and_keeps_the_rest():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            leaked = _insert(
                conn,
                {"name": "Before", "password": "$2b$12$oldhash"},
                {"name": "After", "password": "$2b$12$newhash"},
            )
            token = _insert(conn, None, {"status": "issued", "sign_token": "bearer-abc"})
            clean = _insert(conn, {"status": "a"}, {"status": "b"})
            scalar = _insert(conn, None, ["password"])  # non-object JSON is left alone

            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                module.upgrade()

            assert tuple(_values(conn, leaked)) == ({"name": "Before"}, {"name": "After"})
            assert tuple(_values(conn, token)) == (None, {"status": "issued"})
            assert tuple(_values(conn, clean)) == ({"status": "a"}, {"status": "b"})
            assert tuple(_values(conn, scalar)) == (None, ["password"])
        finally:
            outer.rollback()
