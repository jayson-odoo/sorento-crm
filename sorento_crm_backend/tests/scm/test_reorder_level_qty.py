"""R5 - the AutoCount reorder QUANTITY is the buyer's to set, beside the level.

`PUT /api/v1/scm/reorder-levels` (plan section 5.8). The panel shows Level and Reorder qty
side by side and one Save carries both, so the quantity travels on the same write and lands
on the same row - which is what puts it in the level-changes export.

The key that is ABSENT is not the same as the key that is null: the AutoCount level upload
writes `reorder_qty` too, so a level-only save must leave whatever the sheet last stated
exactly where it is rather than clearing it.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import _mk_product

pytestmark = requires_pg

MARKER = "ZZTRLQ"


def _client(scm_app, role_slug="admin"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return TestClient(app), db


def _level_row(db, product_id):
    return db.execute(text(
        "SELECT level, reorder_qty FROM scm.reorder_level "
        "WHERE product_id = CAST(:p AS uuid) AND warehouse_id IS NULL"
    ), {"p": product_id}).mappings().first()


def test_a_save_carries_the_level_and_the_quantity(scm_app):
    client, db = _client(scm_app)
    pid = _mk_product(db, f"{MARKER}-BOTH-{uuid.uuid4().hex[:6]}")

    res = client.put("/api/v1/scm/reorder-levels", json={
        "product_id": pid, "level": 30, "reorder_qty": 18,
    })

    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 30
    # Echoed back, so the panel can render what it just saved without a second read.
    assert body["reorder_qty"] == 18
    row = _level_row(db, pid)
    assert float(row["level"]) == 30
    assert float(row["reorder_qty"]) == 18


def test_a_level_only_save_leaves_the_uploaded_quantity_alone(scm_app):
    client, db = _client(scm_app)
    pid = _mk_product(db, f"{MARKER}-KEEP-{uuid.uuid4().hex[:6]}")
    client.put("/api/v1/scm/reorder-levels", json={
        "product_id": pid, "level": 30, "reorder_qty": 18,
    })

    client.put("/api/v1/scm/reorder-levels", json={"product_id": pid, "level": 40})

    row = _level_row(db, pid)
    assert float(row["level"]) == 40
    assert float(row["reorder_qty"]) == 18, "an absent key is not a clear"


def test_an_explicit_null_clears_the_quantity(scm_app):
    client, db = _client(scm_app)
    pid = _mk_product(db, f"{MARKER}-CLEAR-{uuid.uuid4().hex[:6]}")
    client.put("/api/v1/scm/reorder-levels", json={
        "product_id": pid, "level": 30, "reorder_qty": 18,
    })

    client.put("/api/v1/scm/reorder-levels", json={
        "product_id": pid, "level": 30, "reorder_qty": None,
    })

    assert _level_row(db, pid)["reorder_qty"] is None


def test_a_negative_quantity_is_refused(scm_app):
    client, db = _client(scm_app)
    pid = _mk_product(db, f"{MARKER}-NEG-{uuid.uuid4().hex[:6]}")

    res = client.put("/api/v1/scm/reorder-levels", json={
        "product_id": pid, "level": 30, "reorder_qty": -1,
    })

    assert res.status_code == 422
