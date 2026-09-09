"""S9 (PLAN-reorder-feedback-9sep.md, G6 ruling 9 Sep 2026) - Order summary grows into the
paper sheet: delivery-by-month, project customers, supplier, PO/SPO/last-receipt/MOQ
remarks, and a PDF/Excel export.

AC-S9.1, S9.3, S9.5. Harness reused wholesale from `tests/scm/test_summary_order_service.py`
(the `chain`/`db` fixtures + `_stock`/`_po`/`_supplier` builders already exercise
`svc.write_rows` / `svc.report`) and `tests/scm/test_channel_read_model.py`'s
`_confirmed_leg` for the project-customer half (a real confirmed Order Inquiry row with a
named customer on its core line).

Scope note: `po_open_qty` / `incoming_spo_qty` are pinned as PRESENT NUMERIC keys here
(the arithmetic behind them - `po_book_service` / `spo_supply` - has its own coverage
elsewhere); the four remaining new fields (`delivery_by_month`, `project_customers`,
`supplier_name`, `last_receipt`, `moq`) are pinned on their actual values.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PickingHeader, PickingLine
from app.services.scm import summary_order_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_channel_read_model import _confirmed_leg
from tests.scm.test_summary_order_service import _link as _summary_link  # noqa: F401
from tests.scm.test_summary_order_service import (  # noqa: F401
    _po,
    _stock,
    _supplier,
    chain,
    db,
)

pytestmark = requires_pg

MARKER = "ZZTOSHEET"


def _u() -> str:
    return str(uuid.uuid4())


def _dated_retail_so(db, product, wh, qty, *, required_date):
    cust = Customer(id=_u(), customer_code=f"{MARKER}-{_u()[:8]}", customer_name="Dealer co")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=f"{MARKER}-SO-{_u()[:8]}", customer_id=cust.id, status="open",
        order_type="dealer", demand_class="retail",
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_delivered=0, required_date=required_date, line_status="open",
    ))
    db.flush()


def _moq_link(db, product, supplier, *, moq):
    from app.models.procurement import ProductSupplier
    db.add(ProductSupplier(
        id=_u(), product_id=product.id, supplier_id=supplier.id,
        standard_lead_time_days=30, moq=moq, order_multiple=1, unit_cost=10,
        currency="MYR", is_primary_supplier=True,
    ))
    db.flush()


def _goods_received(db, product, wh, *, qty_accepted, days_ago):
    header = PickingHeader(
        id=_u(), picking_number=f"{MARKER}-GRN-{_u()[:8]}", picking_type="goods_received",
        picking_date=date.today() - timedelta(days=days_ago),
    )
    db.add(header)
    db.flush()
    db.add(PickingLine(
        id=_u(), picking_header_id=header.id, product_id=product.id,
        quantity_expected=qty_accepted, quantity_picked=qty_accepted,
        qty_accepted=qty_accepted, destination_warehouse_id=wh.id,
    ))
    db.flush()


def test_report_row_carries_the_sheet_fields(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 40)

    # Two delivery months (AC-S9.1/S9.5: "two delivery months").
    _dated_retail_so(db, f["product"], f["bin"], 30, required_date=date(2026, 9, 15))
    _dated_retail_so(db, f["product"], f["bin"], 20, required_date=date(2026, 10, 20))

    # One project customer (confirmed leg, named on its core line).
    leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id, buy_qty=5)
    core_so_id = db.execute(text(
        "SELECT sales_order_id FROM sales_order_lines WHERE id = :l"
    ), {"l": leg["core_line"].id}).scalar()
    cust = Customer(id=_u(), customer_code=f"{MARKER}-PJC", customer_name="OIB Construction")
    db.add(cust)
    db.flush()
    db.execute(text(
        "UPDATE sales_orders SET customer_id = :c WHERE id = :so"
    ), {"c": cust.id, "so": core_so_id})

    sup = _supplier(db, f"{MARKER} supplier")
    _po(db, f["product"], f["bin"], 25, supplier=sup)
    _moq_link(db, f["product"], sup, moq=1000)
    _goods_received(db, f["product"], f["bin"], qty_accepted=300, days_ago=5)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    months = {m["month"]: m["qty"] for m in row["delivery_by_month"]}
    assert months.get("2026-09") == 30
    assert months.get("2026-10") == 20

    customers = row["project_customers"]
    assert len(customers) == 1
    assert customers[0]["label"] == "OIB Construction"
    assert customers[0]["qty"] == 5

    assert row["supplier_name"] == f"{MARKER} supplier"
    assert row["moq"] == 1000
    assert row["last_receipt"]["qty"] == 300
    assert row["last_receipt"]["date"] == (date.today() - timedelta(days=5)).isoformat()
    assert isinstance(row["po_open_qty"], (int, float))
    assert isinstance(row["incoming_spo_qty"], (int, float))


def test_undated_delivery_lands_under_a_null_month(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    _dated_retail_so(db, f["product"], f["bin"], 12, required_date=None)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    months = {m["month"]: m["qty"] for m in row["delivery_by_month"]}
    assert months.get(None) == 12


# --- AC-S9.3: export ----------------------------------------------------------------

@pytest.fixture()
def api_app(scm_app):
    app, db_, _, _ = scm_app
    return app


def test_export_pdf_returns_the_right_content_type(scm_app):
    from tests.scm.conftest import SORENTO_COMPANY_ID
    from tests.scm.test_m3_run import _client

    app, db_ = _client(scm_app, "purchasing")
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar()
    db_.flush()

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": run_id, "format": "pdf",
        })

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type", "").startswith("application/pdf")


def test_export_xlsx_returns_the_right_content_type(scm_app):
    from tests.scm.conftest import SORENTO_COMPANY_ID
    from tests.scm.test_m3_run import _client

    app, db_ = _client(scm_app, "purchasing")
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar()
    db_.flush()

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": run_id, "format": "xlsx",
        })

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type", "") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_export_unknown_format_answers_422(scm_app):
    from tests.scm.test_m3_run import _client

    app, db_ = _client(scm_app, "purchasing")
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now()) RETURNING id"
    ), {"id": _u()}).scalar()
    db_.flush()

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": run_id, "format": "csv",
        })

    assert resp.status_code == 422, resp.text
