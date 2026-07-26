"""Startup seeder that grants external-ingest slugs to the integration roles.

Guards the automation that replaced the manual dev-time SQL grants: after
sync_permissions creates the rows, every /external ingest slug must land on the
integration roles (the /external guard has no admin bypass), and re-running must
be a no-op.

blank_session gives an isolated schema with the RBAC tables present but empty;
we seed one integration role + a couple of real ingest permission slugs.
"""
import uuid

import pytest
from sqlalchemy import text

from app.services.integration_ingest_grants import grant_ingest_permissions, _ingest_slugs
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _seed_role(db, slug: str) -> str:
    rid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) "
            "VALUES (:id, :s, :n, false, false, false)"
        ),
        {"id": rid, "s": slug, "n": slug},
    )
    return rid


def _seed_perm(db, slug: str) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO user_permissions (id, slug, name) VALUES (:id, :s, :n)"),
        {"id": pid, "s": slug, "n": slug},
    )
    return pid


def test_grants_new_slugs_to_integration_role(db):
    role_id = _seed_role(db, "integration_foundryx_esb")
    # Two real ingest slugs (must be values in the guard maps).
    slugs = ["order_management.quotations.edit", "scm.purchase_orders.edit"]
    assert set(slugs) <= _ingest_slugs()
    pids = {s: _seed_perm(db, s) for s in slugs}
    db.flush()

    added = grant_ingest_permissions(db)
    assert added >= 2

    granted = {
        r[0]
        for r in db.execute(
            text("SELECT permission_id FROM user_role_permissions WHERE role_id = :r"),
            {"r": role_id},
        ).fetchall()
    }
    for pid in pids.values():
        assert pid in granted


def test_idempotent_second_run_adds_nothing(db):
    _seed_role(db, "integration_n8n")
    _seed_perm(db, "procurement.request_quotations.edit")
    db.flush()

    first = grant_ingest_permissions(db)
    assert first >= 1
    second = grant_ingest_permissions(db)
    assert second == 0


def test_missing_role_is_not_fatal(db):
    # No integration role seeded — a fresh DB before integration_seed ran.
    _seed_perm(db, "inventory.stock_balance_snapshots.edit")
    db.flush()
    assert grant_ingest_permissions(db) == 0
