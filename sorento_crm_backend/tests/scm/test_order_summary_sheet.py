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
    # S1 (Phase 3 ruling): the project half now reads the SAME core-SO-line source
    # `project_demand` sums, so the confirmed leg's own core line (required_date =
    # today + 14 days, `_confirmed_leg`'s own default) lands in the Delivery cell too -
    # in whichever month that happens to be, computed rather than assumed.
    db.refresh(leg["core_line"])
    project_month = leg["core_line"].required_date.isoformat()[:7]
    expected_sept = 30 + (5 if project_month == "2026-09" else 0)
    expected_oct = 20 + (5 if project_month == "2026-10" else 0)
    assert months.get("2026-09") == expected_sept
    assert months.get("2026-10") == expected_oct
    # The Delivery cell must tie to the row - nothing on it that the row's own Project
    # qty / Dealer o/s columns do not already account for.
    assert sum(m["qty"] for m in row["delivery_by_month"]) == (
        row["project_demand"] + row["dealer_outstanding"]
    )

    customers = row["project_customers"]
    assert len(customers) == 1
    # S4 (Phase 3 ruling): "<customer> / <project title>" when the SO is mirrored into a
    # project - `_confirmed_leg` always mirrors one, so the customer name alone is a
    # prefix rather than the whole label here.
    assert customers[0]["label"].startswith("OIB Construction / ")
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


# --- Phase 3 security review, M1/L1/L2 ----------------------------------------------

def test_export_answers_404_on_a_malformed_run_id(scm_app):
    """L2: a run_id that is not even a UUID is refused the same way a genuinely absent
    one is - never a 500 from a bad-format value reaching the database."""
    from tests.scm.test_m3_run import _client

    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": "not-a-uuid", "format": "pdf",
        })
    assert resp.status_code == 404, resp.text


def test_export_answers_404_when_the_run_is_not_visible(scm_app):
    """L1: a well-formed but non-existent (or another company's) run id is refused by
    the SAME `assert_run_visible` gate every other run-scoped route uses."""
    from tests.scm.test_m3_run import _client

    app, _db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": _u(), "format": "pdf",
        })
    assert resp.status_code == 404, resp.text


def test_export_refuses_above_2000_rows_to_order(scm_app):
    """M1: the sheet only lists products to order - a run with more than 2,000 such rows
    is refused rather than exported (a several-thousand-row PDF is not a printable sheet).
    Bulk-inserted so 2,001 products + rows cost two statements, not two thousand ORM ones.
    """
    from tests.scm.test_m3_run import _client

    from tests.scm.conftest import SORENTO_COMPANY_ID

    app, db_ = _client(scm_app, "purchasing")
    marker = f"ZZTEXPCAP{_u()[:6]}"
    cat_id = db_.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (gen_random_uuid(), :c, :c) RETURNING id"
    ), {"c": marker}).scalar()
    uom_id = db_.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) "
        "VALUES (gen_random_uuid(), :c, :c) RETURNING id"
    ), {"c": marker[:20]}).scalar()
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (gen_random_uuid(), 'completed', false, :co, now()) RETURNING id"
    ), {"co": SORENTO_COMPANY_ID}).scalar()
    db_.execute(text("""
        INSERT INTO products (id, product_code, product_name, category_id, base_uom_id,
                              list_price, company_id)
        SELECT gen_random_uuid(), :marker || '-' || s, :marker || ' ' || s, :cat, :uom, 0, :co
        FROM generate_series(1, 2001) AS s
    """), {"marker": marker, "cat": cat_id, "uom": uom_id, "co": SORENTO_COMPANY_ID})
    db_.execute(text("""
        INSERT INTO scm.order_summary_row (
            id, run_id, product_id, as_of, on_hand, project_demand, dealer_outstanding,
            qty_on_order, qty_in_transit, shortfall, suggested_qty, chosen_qty,
            project_demand_line_count, dealer_outstanding_line_count, computed_at,
            company_id
        )
        SELECT gen_random_uuid(), :run, p.id, CURRENT_DATE, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, now(),
               :co
        FROM products p WHERE p.product_code LIKE :like
    """), {"run": run_id, "like": f"{marker}-%", "co": SORENTO_COMPANY_ID})
    db_.commit()

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export", params={
            "run_id": run_id, "format": "pdf",
        })

    assert resp.status_code == 422, resp.text
    assert "Narrow the plan first" in resp.text


def test_a_supplier_named_as_a_formula_exports_as_a_string_cell(db, chain):
    """H1: a supplier name shaped like a spreadsheet formula must reach the workbook as
    inert text - never as something Excel evaluates on open."""
    from io import BytesIO

    from openpyxl import load_workbook

    f = chain
    _stock(db, f["product"], f["bin"], 5)
    sup = _supplier(db, '=HYPERLINK("http://evil.example","click")')
    _moq_link(db, f["product"], sup, moq=10)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    # Something to order, or M1's own row filter drops it from the export entirely.
    db.execute(text(
        "UPDATE scm.order_summary_row SET chosen_qty = 1 WHERE run_id = :r"
    ), {"r": f["run"].id})
    db.commit()

    payload, content_type, _filename = svc.export_report(db, run_id=f["run"].id, fmt="xlsx")
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(BytesIO(payload))
    ws = wb.active
    header = [c.value for c in ws[1]]
    supplier_col = header.index("Supplier") + 1
    cell = ws.cell(row=2, column=supplier_col)
    assert cell.data_type == "s", "a formula-shaped supplier name must load back as text"
    assert cell.value.startswith("'"), "the apostrophe prefix must survive into the cell"
