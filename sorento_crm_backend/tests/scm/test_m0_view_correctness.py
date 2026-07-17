"""SCM M0 — view-correctness regressions (found in review).

#1 on_order_v must NOT count draft POs as supply (M4-D5: drafts are not on_order).
#2 net_position_v must surface a (product,warehouse) that has committed/on_order
   demand even when there is NO stock row (the stockout-with-committed case).
Both tested with savepoint inserts that roll back, so the DB is untouched.
"""
from __future__ import annotations

import os
import re
import uuid

import pytest
from sqlalchemy import create_engine, text


def _pg_url() -> str | None:
    # DATABASE_URL env wins (CI/container); .env is a local fallback and is NOT
    # shipped in the CI image, so its absence must skip these tests, not crash.
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if not os.path.exists(env):
            return None
        with open(env) as fh:
            for line in fh:
                if line.startswith("DATABASE_URL"):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not raw:
        return None
    return re.sub(r"^postgresql\+\w+", "postgresql", raw)


URL = _pg_url()
pytestmark = pytest.mark.skipif(
    not URL or not URL.startswith("postgresql"),
    reason="view-correctness tests require a live Postgres DATABASE_URL",
)


@pytest.fixture()
def conn():
    eng = create_engine(URL)
    with eng.connect() as c:
        yield c
    eng.dispose()


def _a_product_warehouse_without_stock(conn):
    """A (product, warehouse) pair that currently has NO stock row."""
    row = conn.execute(text(
        "select p.id, w.id from products p cross join warehouses w "
        "where not exists (select 1 from stock s where s.product_id=p.id and s.warehouse_id=w.id) "
        "limit 1"
    )).fetchone()
    return (str(row[0]), str(row[1])) if row else (None, None)


def test_on_order_v_excludes_draft_po(conn):
    """#1 — a draft PO line must NOT show up as on_order."""
    pid = conn.execute(text("select id from products limit 1")).scalar()
    wid = conn.execute(text("select id from warehouses limit 1")).scalar()
    sp = conn.begin_nested()
    try:
        po = str(uuid.uuid4())
        conn.execute(text(
            "insert into purchase_orders (id, po_number, status, source_system) "
            "values (:id, :num, 'draft', 'test')"
        ), {"id": po, "num": f"TEST-DRAFT-{po[:8]}"})
        conn.execute(text(
            "insert into purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_received, line_status, source_system) "
            "values (:id, :po, :pid, :wid, 500, 0, 'open', 'test')"
        ), {"id": str(uuid.uuid4()), "po": po, "pid": pid, "wid": wid})
        on_order = conn.execute(text(
            "select coalesce(sum(on_order),0) from scm.on_order_v "
            "where product_id=:pid and warehouse_id=:wid"
        ), {"pid": pid, "wid": wid}).scalar()
        assert float(on_order) == 0.0, "draft PO leaked into on_order_v"
    finally:
        sp.rollback()


def test_net_position_v_surfaces_demand_without_stock_row(conn):
    """#2 — an open SO on a (product,warehouse) with no stock row must appear."""
    pid, wid = _a_product_warehouse_without_stock(conn)
    if pid is None:
        pytest.skip("no product/warehouse pair without a stock row")
    sp = conn.begin_nested()
    try:
        so = str(uuid.uuid4())
        conn.execute(text(
            "insert into sales_orders (id, so_number, status, source_system) "
            "values (:id, :num, 'open', 'test')"
        ), {"id": so, "num": f"TEST-SO-{so[:8]}"})
        conn.execute(text(
            "insert into sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_delivered, line_status, source_system) "
            "values (:id, :so, :pid, :wid, 30, 0, 'open', 'test')"
        ), {"id": str(uuid.uuid4()), "so": so, "pid": pid, "wid": wid})
        row = conn.execute(text(
            "select quantity_on_hand, committed, net_position from scm.net_position_v "
            "where product_id=:pid and warehouse_id=:wid"
        ), {"pid": pid, "wid": wid}).fetchone()
        assert row is not None, "committed demand with no stock row vanished from net_position_v"
        on_hand, committed, net = row
        assert float(committed) == 30.0
        assert float(net) == float(on_hand or 0) - 30.0  # on_hand 0 → net -30
    finally:
        sp.rollback()
