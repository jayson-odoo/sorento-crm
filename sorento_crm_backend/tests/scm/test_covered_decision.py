"""Resolving a covered-by-stock row: use the stock, or buy anyway.

The engine emits these precisely so it does not decide. Buying anyway promotes the row into
an ordinary accepted buy rather than growing a parallel lifecycle, so it reaches the draft
PO through the path every other purchase uses - and starts counting as spend at the moment
somebody agreed to spend.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.error_handler import AppException
from app.services.scm import decision_service as dsvc
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _covered_row(db):
    wid = _mk_warehouse(db, "ZZTW-DEC")
    pid = _mk_product(db, f"ZZTP-DEC-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 500)
    _mk_demand(db, pid, wid, 0.0)
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, created_at, updated_at) "
        "VALUES (:id, :n, 'open', now(), now())"), {"id": soid, "n": f"ZZTSO-{soid[:8]}"})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:id, :so, :p, :w, 6, 6, 0, 'open', 'needs_purchase', now(), now())"
    ), {"id": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid})
    _link(db, pid, _mk_supplier(db, "ZZT Dec Supplier"), moq=None, mult=None, cost=20)
    db.flush()

    created = svc.create_run(db, ["ZZTW-DEC"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    row = db.execute(text(
        "SELECT id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'covered'"
    ), {"r": created["run_id"], "p": pid}).mappings().first()
    assert row is not None, "fixture must produce a covered row"
    return db, str(row["id"])


def _state(db, rec_id):
    return dict(db.execute(text(
        "SELECT rec_type, status FROM scm.reorder_recommendation WHERE id = :i"
    ), {"i": rec_id}).mappings().first())


def test_use_stock_resolves_the_row_without_a_purchase(scm_app):
    _, db, _, _ = scm_app
    db, rec_id = _covered_row(db)

    dsvc.decide_covered(db, rec_id, "use_stock")

    assert _state(db, rec_id) == {"rec_type": "covered", "status": "use_stock"}


def test_buy_anyway_turns_it_into_an_ordinary_accepted_buy(scm_app):
    # Not a parallel lifecycle: from here it is a purchase like any other and reaches the
    # draft PO through the path every other buy uses.
    _, db, _, _ = scm_app
    db, rec_id = _covered_row(db)

    dsvc.decide_covered(db, rec_id, "buy")

    assert _state(db, rec_id) == {"rec_type": "buy", "status": "accepted"}


def test_a_row_already_bought_cannot_be_walked_back_to_using_stock(scm_app):
    # It is a purchase now, possibly already on a draft PO. Silently reverting it would
    # leave the order and the plan disagreeing.
    _, db, _, _ = scm_app
    db, rec_id = _covered_row(db)
    dsvc.decide_covered(db, rec_id, "buy")

    with pytest.raises(AppException):
        dsvc.decide_covered(db, rec_id, "use_stock")


def test_an_unknown_choice_is_refused(scm_app):
    _, db, _, _ = scm_app
    db, rec_id = _covered_row(db)

    with pytest.raises(AppException):
        dsvc.decide_covered(db, rec_id, "maybe")
