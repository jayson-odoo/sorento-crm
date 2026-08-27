"""F12 / R19-R20 - both readers bind a set, and a person can pick one from the queue.

TEST-FIRST: `supplier_code_alias_service` still refuses anything but a product id when this
file is written, so every test here is expected to be red until slot A lands.

The stock list and the proforma invoice go through the same ladder, so a code spelled as one
of our set codes has to reach `product_set_id` on both of them - and a code a person answers
with a SET has to re-bind the rows already uploaded under it, for the same reason a product
pick does: the loading plan is read off those rows, and an answer that only takes effect on
the next upload is an answer nobody gets to use today.
"""
from __future__ import annotations

import pytest

from app.models.scm import SupplierInventory, SupplierProductCodeAlias
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as pi_svc
from app.services.scm import supplier_code_alias_service as alias_svc
from app.services.scm import supplier_inventory_service as stock_svc
from tests._pg_fixture import pg_session
from tests.scm.test_supplier_code_alias_binding import (
    _held,
    _pi_lines,
    _pi_workbook,
    _stock_workbook,
)
from tests.scm.test_supplier_code_matcher import World


def _wc(w: World):
    pedestal = w.product("CWCX605-RL")
    cistern = w.product("CWCY605")
    return pedestal, cistern, w.product_set("CWC605-RL", [(pedestal, 1, 0), (cistern, 1, 1)])


# --------------------------------------------------------------------------------- #
# The upload paths
# --------------------------------------------------------------------------------- #


def test_a_stock_list_binds_a_set_code_to_the_set():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")

        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )

        rows = _held(db, str(w.supplier.id))
        assert [str(r.product_set_id) for r in rows] == [str(product_set.id)]
        assert [r.product_id for r in rows] == [None]


def test_a_proforma_invoice_binds_a_set_code_to_the_set():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")

        pi_svc.apply(
            db,
            _pi_workbook(code),
            supplier_id=str(w.supplier.id),
            currency="CNY",
            source_ref="jinbaichuan.xlsx",
            actor="Ms Tee",
        )

        lines = _pi_lines(db, str(w.supplier.id))
        assert [str(l.product_set_id) for l in lines] == [str(product_set.id)]
        assert [l.product_id for l in lines] == [None]


def test_a_set_bound_stock_row_is_not_in_the_unmatched_queue():
    """The queue is a to-do list. A row that binds - to a product or to a set - is done."""
    with pg_session() as db:
        w = World(db)
        _wc(w)
        code = w.supplier_code("CWC605-RL")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )

        assert alias_svc.unmatched_for_supplier(db, str(w.supplier.id)) == []


# --------------------------------------------------------------------------------- #
# A person picks a set from the queue
# --------------------------------------------------------------------------------- #


def test_picking_a_set_binds_the_rows_already_uploaded():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL-180")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )
        pi_svc.apply(
            db,
            _pi_workbook(code),
            supplier_id=str(w.supplier.id),
            currency="CNY",
            source_ref="jinbaichuan.xlsx",
            actor="Ms Tee",
        )
        assert [r.product_set_id for r in _held(db, str(w.supplier.id))] == [None]

        out = alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )

        assert out["rebound_stock_rows"] == 1
        assert out["rebound_invoice_lines"] == 1
        assert out["product_set_id"] == str(product_set.id)
        assert out["set_code"] == product_set.set_code
        assert [str(r.product_set_id) for r in _held(db, str(w.supplier.id))] == [
            str(product_set.id)
        ]
        assert [str(l.product_set_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product_set.id)
        ]


def test_picking_a_product_after_a_set_clears_the_set_binding():
    """One code means one thing. A row still pointing at the set would go on offering the
    whole WC to the plan under a code somebody has just said is the pedestal."""
    with pg_session() as db:
        w = World(db)
        pedestal, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL-180")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )

        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_id=str(pedestal.id),
            actor="Ms Tee",
        )

        rows = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).all()
        assert len(rows) == 1
        assert str(rows[0].product_id) == str(pedestal.id)
        assert rows[0].product_set_id is None
        held = _held(db, str(w.supplier.id))
        assert [str(r.product_id) for r in held] == [str(pedestal.id)]
        assert [r.product_set_id for r in held] == [None]


def test_dismissing_a_set_bound_code_unbinds_the_set_too():
    with pg_session() as db:
        w = World(db)
        _wc(w)
        code = w.supplier_code("CWC605-RL")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )

        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        held = _held(db, str(w.supplier.id))
        assert [r.product_set_id for r in held] == [None]
        assert [r.product_id for r in held] == [None]


def test_naming_a_product_and_a_set_at_once_is_refused():
    with pg_session() as db:
        w = World(db)
        pedestal, _, product_set = _wc(w)
        with pytest.raises(AppException):
            alias_svc.create(
                db,
                supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("CWC605-RL"),
                product_id=str(pedestal.id),
                product_set_id=str(product_set.id),
                actor="Ms Tee",
            )


def test_naming_neither_a_product_nor_a_set_is_refused():
    with pg_session() as db:
        w = World(db)
        _wc(w)
        with pytest.raises(AppException):
            alias_svc.create(
                db,
                supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("CWC605-RL"),
                actor="Ms Tee",
            )


def test_a_set_ruling_reads_back_in_names_not_ids():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL-180")
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )

        listed = alias_svc.list_for_supplier(db, str(w.supplier.id))

        row = next(r for r in listed if r["supplier_code"] == code)
        assert row["set_code"] == product_set.set_code
        assert row["set_name"] == product_set.name
        assert row["product_code"] is None


# --------------------------------------------------------------------------------- #
# Refresh matching (R18) walks the same ladder, so it answers set codes too
# --------------------------------------------------------------------------------- #


def test_refresh_matching_binds_a_set_authored_after_the_upload():
    with pg_session() as db:
        w = World(db)
        pedestal = w.product("CWCX605-RL")
        cistern = w.product("CWCY605")
        code = w.supplier_code("CWC605-RL")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )
        assert [r.product_set_id for r in _held(db, str(w.supplier.id))] == [None]

        product_set = w.product_set("CWC605-RL", [(pedestal, 1, 0), (cistern, 1, 1)])
        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out["inventory_bound"] == 1
        assert out["still_unmatched"] == 0
        assert [str(r.product_set_id) for r in _held(db, str(w.supplier.id))] == [
            str(product_set.id)
        ]


def test_a_set_bound_row_is_left_alone_by_refresh_matching():
    """Re-deriving a settled binding is a chance to disagree with it."""
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")
        stock_svc.apply(
            db,
            _stock_workbook([[code, "close-coupled WC", 40, 0, 0.19, None]]),
            supplier_id=str(w.supplier.id),
            actor="Ms Tee",
        )

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out["inventory_bound"] == 0
        assert (
            db.query(SupplierInventory)
            .filter(SupplierInventory.supplier_id == w.supplier.id)
            .one()
            .product_set_id
            == str(product_set.id)
        )
