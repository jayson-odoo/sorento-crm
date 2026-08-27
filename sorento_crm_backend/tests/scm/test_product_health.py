"""AC-R12 / AC-R15 - product health read off MOVEMENT, and nothing borrowed across books.

> "costs are often CNY and selling prices MYR, and no exchange rate is trusted" - so no
> margin. Sold = delivery-order lines in the last 3 months; bought = GRN RECEIPTS
> (`picking_lines.qty_accepted` by `picking_headers.picking_date`) in the last 6 months.

    Fast moving  - sold AND bought
    Slow moving  - sold, nothing bought
    Dead         - neither, stock on hand > 0  -> "consider discontinuing"
    No history   - neither, nothing on hand

A purchase order ISSUED is a promise, not stock in: it never makes a product "bought".
And the movement books never reduce the outstanding books (AC-R15) - a GRN matched to
no PO line still counts as bought while `scm.on_order_v` keeps reporting the full open
quantity.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.scm import product_economics_service as svc
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTPHL"
AS_OF = date(2026, 8, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _world(db, *, sold_day: date | None = date(2026, 7, 10),
           received_day: date | None = date(2026, 4, 10),
           on_hand: float = 0.0, po_open: float = 0.0,
           receipt_names_a_po_line: bool = False):
    """One product on a run, with the movements the health class is drawn from."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=100,
                      is_active=True, is_discontinued=False)
    db.add(product)
    db.flush()
    pid = str(product.id)

    wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available) VALUES (:id, :c, :c, true, true)"),
        {"id": wid, "c": unique_code("W")[:20]})

    if sold_day is not None:
        oid = _u()
        db.execute(text(
            "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
            "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
            "created_at, updated_at) "
            "VALUES (:id, :n, :d, false, false, 0, 0, 0, 0, false, now(), now())"),
            {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": sold_day})
        db.execute(text(
            "INSERT INTO order_lines (id, line_sequence, order_id, product_id, "
            "warehouse_id, quantity, unit_price, total_excluding_tax, created_at, "
            "updated_at) VALUES (:id, 1, :o, :p, :w, 50, 20, 1000, now(), now())"),
            {"id": _u(), "o": oid, "p": pid, "w": wid})

    po_line_id = None
    if po_open:
        sid = _u()
        db.execute(text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active) "
            "VALUES (:id, :c, :n, true)"),
            {"id": sid, "c": unique_code("S")[:20], "n": f"{MARKER} supplier"})
        poid = _u()
        db.execute(text(
            "INSERT INTO purchase_orders (id, po_number, supplier_id, status, issue_date, "
            "created_at, updated_at) "
            "VALUES (:id, :n, :s, 'active', :d, now(), now())"),
            {"id": poid, "n": f"{MARKER}-{poid[:8]}", "s": sid, "d": date(2026, 6, 1)})
        po_line_id = _u()
        db.execute(text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, line_status, created_at) "
            "VALUES (:id, :po, :p, :w, :q, 0, 'open', now())"),
            {"id": po_line_id, "po": poid, "p": pid, "w": wid, "q": po_open})

    if received_day is not None:
        hid = _u()
        db.execute(text(
            "INSERT INTO picking_headers (id, picking_number, picking_type, picking_date, "
            "inspection_status, picking_status, created_at, updated_at) "
            "VALUES (:id, :n, 'goods_received', :d, 'passed', 'posted', now(), now())"),
            {"id": hid, "n": f"{MARKER}-{hid[:8]}", "d": received_day})
        db.execute(text(
            "INSERT INTO picking_lines (id, picking_header_id, product_id, po_line_id, "
            "quantity_expected, quantity_picked, qty_accepted, created_at) "
            "VALUES (:id, :h, :p, :pol, 30, 30, 30, now())"),
            {"id": _u(), "h": hid, "p": pid,
             "pol": po_line_id if receipt_names_a_po_line else None})

    if on_hand:
        db.execute(text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel) VALUES (:id, :p, :w, :q, false)"),
            {"id": _u(), "p": pid, "w": wid, "q": on_hand})

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now())"), {"id": run_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed')"),
        {"id": _u(), "r": run_id, "p": pid, "w": wid})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_id": wid}


def _health(db, w) -> dict:
    return svc.economics_for_run(db, w["run_id"], as_of=AS_OF)["products"][w["product_id"]]


# --- the four classes ---------------------------------------------------------------

def test_sold_and_bought_is_fast_moving():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db))

        assert e["movement_class"] == "fast_moving"
        assert e["sold_recent_qty"] == 50.0
        assert e["bought_recent_qty"] == 30.0


def test_sold_with_nothing_bought_is_slow_moving():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, received_day=None))

        assert e["movement_class"] == "slow_moving"
        assert e["bought_recent_qty"] == 0.0


def test_neither_with_stock_on_hand_is_dead():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, sold_day=None, received_day=None, on_hand=40))

        assert e["movement_class"] == "dead"
        assert e["on_hand"] == 40.0


def test_neither_and_nothing_on_hand_is_no_history():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, sold_day=None, received_day=None, on_hand=0))

        assert e["movement_class"] == "no_history"


# --- the windows --------------------------------------------------------------------

def test_a_sale_older_than_three_months_does_not_count_as_sold():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        # February is inside the 12-month economics window but outside the 3-month
        # movement window: the product has not sold LATELY, which is the question.
        e = _health(db, _world(db, sold_day=date(2026, 2, 10), received_day=None,
                               on_hand=40))

        assert e["sold_recent_qty"] == 0.0
        assert e["movement_class"] == "dead"


def test_a_receipt_older_than_six_months_does_not_count_as_bought():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, received_day=date(2025, 12, 1)))

        assert e["bought_recent_qty"] == 0.0
        assert e["movement_class"] == "slow_moving"


def test_a_receipt_five_months_back_still_counts_because_a_long_lead_hides_it():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, received_day=date(2026, 3, 20)))

        assert e["bought_recent_qty"] == 30.0
        assert e["movement_class"] == "fast_moving"


# --- a purchase order is a promise, not stock in -------------------------------------

def test_a_purchase_order_with_no_receipt_is_not_bought():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        e = _health(db, _world(db, received_day=None, po_open=200))

        assert e["bought_recent_qty"] == 0.0
        assert e["movement_class"] == "slow_moving"


# --- AC-R15: movement counts movement, the books say what is outstanding -------------

def test_a_receipt_matched_to_no_po_line_still_counts_as_bought():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, po_open=200, receipt_names_a_po_line=False)

        e = _health(db, w)
        assert e["bought_recent_qty"] == 30.0
        assert e["movement_class"] == "fast_moving"


def test_the_receipt_never_reduces_the_open_purchase_order_book():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, po_open=200, receipt_names_a_po_line=False)
        _health(db, w)

        open_qty = db.execute(text(
            "SELECT SUM(qty_ordered - qty_received) FROM purchase_order_lines "
            "WHERE product_id::text = :p"), {"p": w["product_id"]}).scalar()

        # 200 ordered, 0 received on the LINE: the outstanding figure stands whole,
        # unreduced by a GRN the "Our PO No." matcher never tied to it.
        assert float(open_qty) == 200.0


def test_a_delivery_order_naming_no_sales_order_line_still_counts_as_sold():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, received_day=None)  # the DO names no sales-order line at all

        e = _health(db, w)
        assert e["sold_recent_qty"] == 50.0

        committed = db.execute(text(
            "SELECT COALESCE(SUM(committed), 0) FROM scm.committed_v "
            "WHERE product_id::text = :p"), {"p": w["product_id"]}).scalar()
        assert float(committed) == 0.0, "the DO must not invent or consume a commitment"


# --- no margin anywhere --------------------------------------------------------------

def test_the_payload_names_the_movement_windows_it_judged_on():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        out = svc.economics_for_run(db, _world(db)["run_id"], as_of=AS_OF)

        assert out["sold_window_months"] == 3
        assert out["bought_window_months"] == 6
