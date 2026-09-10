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

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PickingHeader, PickingLine, SPOAllocation
from app.models.project_so import INQUIRY_CANCELLED, INQUIRY_PLACED
from app.models.scm import ReorderRecommendation
from app.services.scm import summary_order_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_channel_read_model import _confirmed_leg
from tests.scm.test_product_grain_summary import _product as _pg_product
from tests.scm.test_product_grain_summary import _run as _pg_run
from tests.scm.test_product_grain_summary import _warehouse as _pg_warehouse
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

    # S14 (AC-S14.3): delivery_by_month/project_customers now read the Order Inquiry book
    # only - these two retail SO lines have no inquiry row behind them and must not reach
    # either cell.
    _dated_retail_so(db, f["product"], f["bin"], 30, required_date=date(2026, 9, 15))
    _dated_retail_so(db, f["product"], f["bin"], 20, required_date=date(2026, 10, 20))

    # One project customer (confirmed leg, named on its core line, an ACTIVE decision).
    leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id, buy_qty=5)
    leg["inquiry_row"].delivery_date = date(2026, 11, 1)
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

    # S14: the retail SO legs above must not appear - the confirmed leg's own Order
    # Inquiry row is the row's ENTIRE Delivery cell.
    months = {m["month"]: m["qty"] for m in row["delivery_by_month"]}
    assert months == {"2026-11": 5}

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


def test_retail_so_line_contributes_nothing_to_delivery(db, chain):
    """S14 (AC-S14.3) retired this test's premise: `delivery_by_month` reads the Order
    Inquiry book, not the SO book, so a retail SO line - dated or undated - contributes
    NOTHING to it. `test_s14_undated_order_inquiry_row_lands_under_the_null_month_last`
    pins the undated-INQUIRY-row case this test used to stand in for.
    """
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    _dated_retail_so(db, f["product"], f["bin"], 12, required_date=None)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    assert row["delivery_by_month"] == []


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
    inert text - never as something Excel evaluates on open.

    S15 (10 Sep 2026) moved the Supplier column off the `product_suppliers` link onto
    the product's last PURCHASE ORDER, so the formula-shaped name needs a PO behind it
    to reach the row at all - the link (`_moq_link`) alone now only supplies the MOQ.
    """
    from io import BytesIO

    from openpyxl import load_workbook

    f = chain
    _stock(db, f["product"], f["bin"], 5)
    sup = _supplier(db, '=HYPERLINK("http://evil.example","click")')
    _moq_link(db, f["product"], sup, moq=10)
    _po(db, f["product"], f["bin"], 5, supplier=sup)
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


# =====================================================================================
# issue #795 (PLAN-product-grain-project-buy-no-level.md Slice 2, AC-7 .. AC-9): the
# order sheet carries Suggested qty + Suggestion immediately left of Order qty, and no
# row is dropped for a suggested quantity of 0.
# =====================================================================================

def test_export_xlsx_prints_suggested_and_suggestion_next_to_order_qty(db):
    """Plan Slice 2 test 7. The new columns sit between Dealer o/s and Order qty, in that
    order; Suggested qty is the engine figure printed as a NUMBER (0 stays 0, unlike the
    blank rule for Order qty); Suggestion is the engine's own reason text; Order qty stays
    the pen column, blank until chosen. A covered product with nothing to order still
    prints, with Suggested qty 0 and its own suggestion (AC-9)."""
    from io import BytesIO

    from openpyxl import load_workbook

    run = _pg_run(db, decision_grain="product", contract_version=1)
    wh = _pg_warehouse(db)
    buy_p = _pg_product(db, stem="S795XBUY")
    covered_p = _pg_product(db, stem="S795XCOV")

    buy_reason = "project buy: 12 confirmed unplaced Buy"
    covered_reason = "40 available across every location covers 12 committed"
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=buy_p.id,
        warehouse_id=wh.id, rounded_qty=12, status="proposed",
        triggered_reason=buy_reason,
    ))
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="covered", product_id=covered_p.id,
        warehouse_id=wh.id, rounded_qty=0, status="proposed",
        triggered_reason=covered_reason,
    ))
    db.flush()

    assert svc.write_rows(db, run.id) == 2, "both products are on the book"

    payload, content_type, _filename = svc.export_report(db, run_id=run.id, fmt="xlsx")
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(BytesIO(payload))
    ws = wb.active

    header = tuple(c.value for c in ws[1])
    assert header == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "BRW PO qty", "BRW incoming qty", "Last in qty", "Last in date",
        "Remarks",
    )

    rows_by_code = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert buy_p.product_code in rows_by_code
    assert covered_p.product_code in rows_by_code, "no row is dropped for suggested 0"

    buy_row = rows_by_code[buy_p.product_code]
    assert buy_row[5] == 12.0, "Suggested qty is a number, left of Suggestion"
    assert buy_row[6] == buy_reason
    # A blank cell round-trips as None through openpyxl load_workbook - it writes ""
    # and None identically, so this reload can never observe "" (the tuple-level ""
    # contract is pinned directly by the sibling `_export_xlsx_rows` test instead).
    assert buy_row[7] is None, "Order qty stays blank until the buyer chooses"

    covered_row = rows_by_code[covered_p.product_code]
    assert covered_row[5] == 0.0, "Suggested qty prints 0, not blank"
    assert covered_row[6] == covered_reason


def test_export_pdf_html_header_cells_are_the_16_columns_in_order():
    """Plan Slice 2 test 8: the PDF's own header row carries the same 16 columns, Suggested
    qty and Suggestion immediately left of Order qty, nothing else moved. Reads
    `_export_pdf_html` directly (as the existing S14 PDF tests do) - it only builds a
    string, so this needs no Chromium round trip and nothing to skip."""
    import re

    html = svc._export_pdf_html([], "2026-09-10")
    headers = re.findall(r"<th>(.*?)</th>", html)
    assert tuple(headers) == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "BRW PO qty", "BRW incoming qty", "Last in qty", "Last in date",
        "Remarks",
    )


# =====================================================================================
# S14 (PLAN-reorder-feedback-9sep.md Round 3, reorder-feedback-9sep-acceptance-criteria.md
# AC-S14.1 - S14.7) - "the sheet reads like the paper one".
#
# RED as of this commit: `OrderSummaryRow.pool_on_hand` / `.reorder_level` do not exist,
# `_incoming_spo_qty_map` is still network-wide, `delivery_by_month` / `project_customers`
# still read the SO book rather than the Order Inquiry, `_EXPORT_COLUMNS` is still the old
# nine, `_month_text` / `_customers_text` still render the old sentence shape, and
# `_export_pdf_html` does not exist yet (the coder splits it out of `_render_export_pdf`).
# =====================================================================================


def _project_bin(db, *, code_stem="PBIN"):
    """A SITE-EXCLUDED warehouse: active, counts as available, `segment='project'` -
    stock and PO/SPO lines here must never reach a "BRW" (site pool) column."""
    wh = Warehouse(
        id=_u(), warehouse_code=f"{MARKER}-{code_stem}-{_u()[:8]}"[:30],
        warehouse_name="project bin", is_active=True, counts_as_available=True,
        segment="project",
    )
    db.add(wh)
    db.flush()
    return wh


def _spo(db, product, wh, *, allocated, received=0):
    db.add(SPOAllocation(
        id=_u(), spo_number=f"{MARKER}-SPO-{_u()[:8]}"[:50],
        product_id=product.id, warehouse_id=(wh.id if wh else None),
        allocated_quantity=allocated, quantity_received=received,
    ))
    db.flush()


def _row_columns(db, run_id, product_id, *columns):
    cols = ", ".join(columns)
    return db.execute(text(
        f"SELECT {cols} FROM scm.order_summary_row WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": product_id}).fetchone()


# --- AC-S14.1: pool_on_hand + reorder_level frozen on write_rows --------------------

def test_s14_pool_on_hand_freezes_site_pool_stock_only(db, chain):
    """A product with 100 at the site-pool bin and 40 at a project bin freezes
    `pool_on_hand` = 100, while `on_hand` (network, unchanged) stays 140. A dealer
    warehouse flagged `counts_as_available=False` (a quarantine bin, for instance) is
    excluded too (captain's ruling, fix round 10 Sep) - it is active, site-pool-segmented,
    and holds stock, but that stock is not sellable, so it must not count as "BRW on
    hand" any more than it counts toward `on_hand` itself.
    """
    f = chain
    _stock(db, f["product"], f["bin"], 100)
    pbin = _project_bin(db)
    _stock(db, f["product"], pbin, 40)
    unavailable = Warehouse(
        id=_u(), warehouse_code=f"{MARKER}-UNAVAIL-{_u()[:8]}"[:30],
        warehouse_name="quarantine bin", is_active=True, counts_as_available=False,
    )
    db.add(unavailable)
    db.flush()
    _stock(db, f["product"], unavailable, 25)

    assert svc.write_rows(db, f["run"].id) == 1
    row = _row_columns(db, f["run"].id, f["product"].id, "pool_on_hand", "on_hand")
    assert float(row.pool_on_hand) == 100.0
    assert float(row.on_hand) == 140.0


def test_s14_reorder_level_freezes_the_first_rec_carrying_the_key(db, chain):
    """`reorder_level` is the run's own `inputs.reorder_level` for the product - the
    first recommendation that carries the key, even when an earlier one carries none."""
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    # The chain's own buy rec carries no `inputs` at all.
    db.add(ReorderRecommendation(
        id=_u(), run_id=f["run"].id, rec_type="buy", product_id=f["product"].id,
        warehouse_id=f["bin"].id, rounded_qty=0, status="proposed",
        inputs={"reorder_level": 300},
    ))
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = _row_columns(db, f["run"].id, f["product"].id, "reorder_level")
    assert float(row.reorder_level) == 300.0


def test_s14_reorder_level_is_null_when_no_rec_carries_one(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)

    assert svc.write_rows(db, f["run"].id) == 1
    row = _row_columns(db, f["run"].id, f["product"].id, "reorder_level")
    assert row.reorder_level is None


# --- AC-S14.2: incoming_spo_qty re-scoped to site pool warehouses -------------------

def test_s14_incoming_spo_qty_counts_site_pool_allocations_only(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    pbin = _project_bin(db)
    _spo(db, f["product"], f["bin"], allocated=50)      # site pool - counts
    _spo(db, f["product"], pbin, allocated=30)          # project bin - excluded
    _spo(db, f["product"], None, allocated=20)          # no warehouse - excluded

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    assert row["incoming_spo_qty"] == 50.0


# --- AC-S14.3: delivery_by_month / project_customers from Order Inquiry ORDER rows --

def test_s14_delivery_and_customers_source_from_order_inquiry_order_rows(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)

    def _named_leg(qty, *, delivery, inquiry_state=None, decision_state="active",
                   customer_name):
        leg = _confirmed_leg(
            db, product_id=f["product"].id, warehouse_id=f["bin"].id, buy_qty=qty,
            decision_state=decision_state, inquiry_state=inquiry_state,
        )
        leg["inquiry_row"].delivery_date = delivery
        core_so_id = db.execute(text(
            "SELECT sales_order_id FROM sales_order_lines WHERE id = :l"
        ), {"l": leg["core_line"].id}).scalar()
        cust = Customer(id=_u(), customer_code=f"{MARKER}-{_u()[:8]}",
                        customer_name=customer_name)
        db.add(cust)
        db.flush()
        db.execute(text("UPDATE sales_orders SET customer_id = :c WHERE id = :so"),
                   {"c": cust.id, "so": core_so_id})
        db.flush()
        return leg

    _named_leg(7, delivery=date(2026, 7, 10), customer_name="Acme Co")
    _named_leg(3, delivery=date(2026, 8, 5), inquiry_state=INQUIRY_PLACED,
              customer_name="Beta Co")
    # Cancelled: contributes NOTHING, even landing in the same month as the first leg.
    _named_leg(100, delivery=date(2026, 7, 10), inquiry_state=INQUIRY_CANCELLED,
              customer_name="Ghost Co")
    # A retail SO line with a required_date must not appear at all (S14.3).
    _dated_retail_so(db, f["product"], f["bin"], 500, required_date=date(2030, 1, 1))

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    months = {m["month"]: m["qty"] for m in row["delivery_by_month"]}
    assert months == {"2026-07": 7, "2026-08": 3}
    assert "2030-01" not in months

    customers = row["project_customers"]
    assert sum(c["qty"] for c in customers) == 10
    assert sum(m["qty"] for m in row["delivery_by_month"]) == sum(
        c["qty"] for c in customers
    )
    labels = {c["label"] for c in customers}
    assert any(label.startswith("Acme Co / ") for label in labels)
    assert any(label.startswith("Beta Co / ") for label in labels)
    assert not any(label.startswith("Ghost Co") for label in labels)


def test_s14_undated_order_inquiry_row_lands_under_the_null_month_last(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    leg_dated = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                               buy_qty=4)
    leg_dated["inquiry_row"].delivery_date = date(2026, 6, 1)
    leg_undated = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                                 buy_qty=6)
    # `delivery_date` left NULL (the default `_confirmed_leg` builds).
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    months = row["delivery_by_month"]
    assert months[-1]["month"] is None
    assert months[-1]["qty"] == 6
    assert months[0]["month"] == "2026-06"


def test_s14_a_superseded_decision_contributes_nothing_to_the_sheet(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                         buy_qty=9, decision_state="superseded")
    leg["inquiry_row"].delivery_date = date(2026, 9, 1)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    assert row["delivery_by_month"] == []
    assert row["project_customers"] == []


# --- AC-S14.4: export columns, in the paper sheet's order ---------------------------

def test_s14_export_columns_match_the_paper_sheet_order():
    # issue #795 (Slice 2 test 10): Suggested qty + Suggestion now sit between Dealer o/s
    # and Order qty; every other column keeps its old order (AC-7).
    assert svc._EXPORT_COLUMNS == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "BRW PO qty", "BRW incoming qty", "Last in qty", "Last in date",
        "Remarks",
    )


_FULL_ROW = {
    "product_code": "ZZTS14-SKU",
    "pool_on_hand": 100,
    "reorder_level": 250,
    # Deliberately DIFFERENT from the sum of project_customers, so a test that reads
    # `project_demand` here instead of the customers sum is caught red-handed.
    "project_demand": 999,
    "project_customers": [
        {"label": "Acme Co / Tower A", "qty": 5},
        {"label": "Beta Co", "qty": 3},
    ],
    "dealer_outstanding": 12,
    # issue #795: the engine's own figure and reason, distinct from `chosen_qty` so a test
    # reading one instead of the other is caught red-handed too.
    "suggested_qty": 12,
    "suggestion": "below level: net 5 <= ROP 10",
    "chosen_qty": 20,
    "delivery_by_month": [{"month": "2026-07", "qty": 5}, {"month": "2026-08", "qty": 3}],
    "supplier_name": "Acme Supplier",
    "po_open_qty": 40,
    "incoming_spo_qty": 15,
    "last_receipt": {"date": "2026-07-21", "qty": 300},
    "moq": 1000,
}

_BLANK_ROW = {
    "product_code": "ZZTS14-BLANK",
    "pool_on_hand": 0,
    "reorder_level": None,
    "project_demand": 0,
    "project_customers": [],
    "dealer_outstanding": 0,
    # issue #795: Suggested qty is a MEASURED figure - 0 prints as 0, never blank (AC-8) -
    # unlike `chosen_qty`/Order qty, the pen column, which stays blank until chosen.
    "suggested_qty": 0,
    "suggestion": None,
    "chosen_qty": None,
    "delivery_by_month": [],
    "supplier_name": None,
    "po_open_qty": 0,
    "incoming_spo_qty": 0,
    "last_receipt": None,
    "moq": None,
}


def test_s14_export_rows_project_qty_is_the_customers_sum_not_project_demand():
    (row,) = svc._export_rows([_FULL_ROW])
    assert row == (
        "ZZTS14-SKU", "100", "250", "8", "12", "12", "below level: net 5 <= ROP 10", "20",
        "Jul - 5\nAug - 3", "Acme Co / Tower A - 5\nBeta Co - 3",
        "Acme Supplier", "40", "15", "300", "21/07/2026", "MOQ 1000",
    )


def test_s14_export_rows_blank_cells_when_the_row_has_nothing_to_show():
    (row,) = svc._export_rows([_BLANK_ROW])
    assert row == (
        "ZZTS14-BLANK", "0", "", "0", "0", "0", "", "",
        "", "", "", "0", "0", "", "", "",
    )


def test_s14_export_xlsx_rows_keep_quantities_as_numbers_and_blanks_as_empty_string():
    (full, blank) = svc._export_xlsx_rows([_FULL_ROW, _BLANK_ROW])
    # Item code / Suggestion / Delivery / Project-customer / Supplier / Remarks are text;
    # every other column is a NUMBER (H1) so summing a column in Excel keeps working.
    # issue #795: Suggested qty (5) joins the numeric set; Order qty moves to 7.
    for idx in (1, 2, 3, 4, 5, 7, 11, 12, 13):
        assert isinstance(full[idx], float), f"column {idx} must be numeric, got {full[idx]!r}"
    assert blank[2] == "", "a NULL reorder level must be a blank cell, not 0"
    assert blank[5] == 0.0, "Suggested qty prints 0, not blank, even on an empty row"
    assert blank[7] == "", "no chosen qty must be a blank cell, not 0"
    assert blank[14] == "", "no last-in date must be a blank cell"


def test_s14_null_pool_on_hand_exports_blank_not_zero():
    """A run frozen before migration 504 carries `pool_on_hand = NULL` (never re-run) -
    the export must print a blank BRW on hand, not a false zero stock count, in both the
    PDF's text shape and the workbook's numeric shape (reviewer fix round, 10 Sep)."""
    null_pool_row = {**_BLANK_ROW, "product_code": "ZZTS14-NULLPOOL", "pool_on_hand": None}

    (row,) = svc._export_rows([null_pool_row])
    assert row[1] == "", "a NULL pool_on_hand must be a blank PDF cell, not '0'"

    (xlsx_row,) = svc._export_xlsx_rows([null_pool_row])
    assert xlsx_row[1] == "", "a NULL pool_on_hand must be a blank workbook cell, not 0"


# --- AC-S14.5: one "Mon - qty" / "Name - qty" per line ------------------------------

def test_s14_month_text_renders_one_entry_per_line_undated_last():
    groups = [{"month": "2026-08", "qty": 1}, {"month": "2026-07", "qty": 1},
              {"month": None, "qty": 5}]
    assert svc._month_text(groups) == "Jul - 1\nAug - 1\nUndated - 5"


def test_s14_month_text_blank_when_no_entries():
    assert svc._month_text([]) == ""


def test_s14_customers_text_renders_one_entry_per_line():
    groups = [{"label": "Acme Co / Tower A", "qty": 5}, {"label": "Beta Co", "qty": 3}]
    assert svc._customers_text(groups) == "Acme Co / Tower A - 5\nBeta Co - 3"


def test_s14_customers_text_blank_when_no_entries():
    assert svc._customers_text([]) == ""


# --- AC-S14.6: xlsx header styling, borders, wrap, freeze panes, column widths ------

def test_s14_render_export_xlsx_styles_header_borders_wrap_and_freeze():
    from io import BytesIO

    from openpyxl import load_workbook

    rows = svc._export_xlsx_rows([_FULL_ROW, _BLANK_ROW])
    payload = svc._render_export_xlsx(rows)
    wb = load_workbook(BytesIO(payload))
    ws = wb.active

    for cell in ws[1]:
        assert cell.font.bold is True
        assert cell.font.color is not None and cell.font.color.rgb.endswith("FFFFFF")
        assert cell.fill.fill_type == "solid"

    for row in ws.iter_rows(min_row=1, max_row=3):
        for cell in row:
            assert cell.border.left.style == "thin"
            assert cell.border.top.style == "thin"
            assert cell.border.right.style == "thin"
            assert cell.border.bottom.style == "thin"
            assert cell.alignment.wrap_text is True

    assert ws.freeze_panes == "A2"
    # issue #795: Suggested qty + Suggestion push every later column two to the right -
    # "Project / customer" is now column J (1=Item code .. 6=Suggested qty, 7=Suggestion,
    # 8=Order qty, 9=Delivery, 10=Project/customer).
    assert ws.column_dimensions["J"].width > 30

    # A multi-month Delivery cell (now column I) carries a newline.
    delivery_cell = ws.cell(row=2, column=9)
    assert "\n" in delivery_cell.value

    # A quantity cell stays numeric.
    assert isinstance(ws.cell(row=2, column=2).value, (int, float))


# --- AC-S14.7: PDF html - styled header, borders, pre-line, repeating thead ---------

def test_s14_export_pdf_html_has_styled_header_borders_and_prewrap():
    rows = svc._export_rows([_FULL_ROW])
    html = svc._export_pdf_html(rows, "2026-09-10")

    for header in svc._EXPORT_COLUMNS:
        assert header in html
    assert "A4 landscape" in html
    assert "white-space: pre-line" in html
    assert "border: 1px solid" in html
    assert "display: table-header-group" in html
    assert "#fff" in html.lower() or "color: white" in html.lower() or (
        "color:#ffffff" in html.lower().replace(" ", "")
    )


def test_s14_export_pdf_html_renders_a_two_month_delivery_cell_with_a_line_break():
    rows = svc._export_rows([_FULL_ROW])
    html = svc._export_pdf_html(rows, "2026-09-10")
    assert "Jul - 5\nAug - 3" in html or "Jul - 5<br>Aug - 3" in html
