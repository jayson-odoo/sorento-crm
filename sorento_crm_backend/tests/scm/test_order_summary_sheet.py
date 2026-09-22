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
    # AC-48 (owner ruling, 15 Sep): last in is the newest VISIBLE `spo_allocations`
    # line - never a picking line. The 13 Sep prod copy has `qty_accepted` NULL on
    # 10,567 of 10,567 GR lines, which is why a picking-line seed here never caught it.
    db.add(SPOAllocation(
        id=_u(), spo_number="202608-S0084", container_number="TLLU8306312",
        product_id=f["product"].id, warehouse_id=f["bin"].id,
        allocated_quantity=300, quantity_received=300,
        expected_date=date.today() - timedelta(days=5),
    ))
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
    assert row["last_receipt"] == {
        "qty": 300,
        "date": (date.today() - timedelta(days=5)).isoformat(),
        "spo_number": "202608-S0084",
        "container": "TLLU8306312",
    }, row["last_receipt"]
    assert isinstance(row["po_open_qty"], (int, float))
    assert isinstance(row["incoming_spo_qty"], (int, float))

    # AC-49 (owner ruling, second round, 15 Sep - "even haven't GR we also show as
    # last in"): a NEWER line, still OPEN (`quantity_received=0`), WINS over the
    # received one above - exactly `spo_last_receipt_service.last_receipt_rows`'s own
    # pick for the same product.
    newer_open = SPOAllocation(
        id=_u(), spo_number=f"{MARKER}-SPO-OPEN-NEWER", product_id=f["product"].id,
        warehouse_id=f["bin"].id, allocated_quantity=45, quantity_received=0,
        expected_date=date.today() - timedelta(days=1),
    )
    db.add(newer_open)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1, "write_rows re-freezes idempotently"
    row2 = svc.report(db, run_id=f["run"].id)["rows"][0]

    from app.services.spo_last_receipt_service import last_receipt_rows

    reference = last_receipt_rows(db, product_ids=[str(f["product"].id)], top_n=1)
    assert reference[0]["spo_number"] == newer_open.spo_number, (
        "the fixture must be shaped so last_receipt_rows itself picks the newer open "
        f"line, or this assertion proves nothing: {reference}"
    )
    assert row2["last_receipt"]["spo_number"] == reference[0]["spo_number"], (
        row2["last_receipt"]
    )
    assert row2["last_receipt"]["qty"] == 45


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


# --- AC-S9.3: export ------------------------------------------------------------------
#
# S4 (PLAN-po-spo-site-pool-and-order-sheet-downloads, AC-15..AC-18) retired the
# synchronous `GET /order-summary/export` - a GET now answers 405
# (`test_order_sheet_export_downloads.py::test_export_get_is_gone`). The two content-type
# tests below are ported to call `svc.export_report` directly (the bytes are still
# produced by that function, only the transport moved off it). The three guard cases
# that were GET-only here (unknown format 422, malformed run 404, invisible run 404) are
# DROPPED rather than re-added as POST duplicates -
# `test_order_sheet_export_downloads.py::test_export_post_guards_run_before_a_row_exists`
# already covers all three through the real route. Only the row-count guard (M1, >2000
# rows) had no POST-level coverage yet, so it is ported in place.

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

    payload, content_type, filename = svc.export_report(db_, run_id=run_id, fmt="pdf")

    assert payload, "no bytes were rendered"
    assert content_type.startswith("application/pdf")
    assert filename


def test_export_xlsx_returns_the_right_content_type(scm_app):
    from tests.scm.conftest import SORENTO_COMPANY_ID
    from tests.scm.test_m3_run import _client

    app, db_ = _client(scm_app, "purchasing")
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now()) RETURNING id"
    ), {"id": _u(), "co": SORENTO_COMPANY_ID}).scalar()
    db_.flush()

    payload, content_type, filename = svc.export_report(db_, run_id=run_id, fmt="xlsx")

    assert payload, "no bytes were rendered"
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert filename


# --- Phase 3 security review, M1 -----------------------------------------------------

def test_export_refuses_above_2000_rows_to_order(scm_app, monkeypatch):
    """M1: the sheet only lists products to order - a run with more than 2,000 such rows
    is refused rather than exported (a several-thousand-row PDF is not a printable sheet).
    Bulk-inserted so 2,001 products + rows cost two statements, not two thousand ORM ones.

    Ported onto the POST route (AC-16): the guard must run BEFORE any `user_downloads`
    row is created, and `enqueue_job` is patched so a rejected request can never reach
    Redis even if the guard regresses.
    """
    from tests.scm.test_m3_run import _client

    from app.services import queue_service
    from tests.scm.conftest import SORENTO_COMPANY_ID

    app, db_ = _client(scm_app, "purchasing")
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not enqueue on a guard failure")))
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

    before = db_.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export", json={
            "run_id": str(run_id), "format": "pdf",
        })

    assert resp.status_code == 422, resp.text
    assert "Narrow the plan first" in resp.text
    after = db_.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a guard failure left a download row behind"


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
    """Plan Slice 2 test 7, extended (review round, owner ruling ~11 Sep): the new
    columns sit between Dealer o/s and Order qty, in that order; Suggested qty is the
    engine figure printed as a NUMBER (0 stays 0, unlike the blank rule for Order qty);
    Order qty stays the pen column, blank until chosen. A covered product with nothing
    to order still prints, with Suggested qty 0 (AC-9).

    Suggestion reads like the plan grid's Decision label now, never the engine's own
    triggered_reason prose ("reorder_level: net -1 <= level 50" was the owner's own
    complaint) - `"Stock: N"` / `"PO: N"` / `"Buy: N"`, one part per line (A3b), or
    "Nothing". Neither seeded product here has any free pool stock or an open PO, so
    the buy row's label is the bare "Buy: 12" and the covered row's is "Nothing" - do
    the arithmetic from the seed, `triggered_reason` no longer drives the cell at all.
    """
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
    # AC-A7: "Last cost" sits immediately right of Supplier now (Lane A), so the 16
    # columns this test used to pin are 17.
    assert header == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "Last cost", "BRW PO qty", "BRW incoming qty", "Last in qty",
        "Last in date", "Remarks",
    )

    rows_by_code = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert buy_p.product_code in rows_by_code
    assert covered_p.product_code in rows_by_code, "no row is dropped for suggested 0"

    buy_row = rows_by_code[buy_p.product_code]
    assert buy_row[5] == 12.0, "Suggested qty is a number, left of Suggestion"
    assert buy_row[6] == "Buy: 12", (
        "no free pool stock and no open PO were seeded, so the label is a bare Buy"
    )
    # A blank cell round-trips as None through openpyxl load_workbook - it writes ""
    # and None identically, so this reload can never observe "" (the tuple-level ""
    # contract is pinned directly by the sibling `_export_xlsx_rows` test instead).
    assert buy_row[7] is None, "Order qty stays blank until the buyer chooses"

    covered_row = rows_by_code[covered_p.product_code]
    assert covered_row[5] == 0.0, "Suggested qty prints 0, not blank"
    assert covered_row[6] == "Nothing", (
        "nothing to buy, no stock offered, no open PO - the label is Nothing"
    )


def test_export_pdf_html_header_cells_are_the_17_columns_in_order():
    """Plan Slice 2 test 8, extended by AC-A7 (Lane A): the PDF's own header row carries
    the same columns, Suggested qty and Suggestion immediately left of Order qty, "Last
    cost" immediately right of Supplier, nothing else moved. Reads `_export_pdf_html`
    directly (as the existing S14 PDF tests do) - it only builds a string, so this needs
    no Chromium round trip and nothing to skip."""
    import re

    html = svc._export_pdf_html([], "2026-09-10")
    headers = re.findall(r"<th>(.*?)</th>", html)
    assert tuple(headers) == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "Last cost", "BRW PO qty", "BRW incoming qty", "Last in qty",
        "Last in date", "Remarks",
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
    # A3 (fix round 2, item 1, captain ruling 23 Sep): PLACED is no longer counted - the
    # engine only buys against `raised`/`partly_linked` rows, so Beta Co's already-
    # sourced leg must NOT reach Project qty any more (superseded S14's own "raised and
    # placed both count" reading, which this leg used to pin the opposite of).
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
    assert months == {"2026-07": 7}, months
    assert "2026-08" not in months, "PLACED (Beta Co) must not reach Project qty"
    assert "2030-01" not in months

    customers = row["project_customers"]
    assert sum(c["qty"] for c in customers) == 7
    assert sum(m["qty"] for m in row["delivery_by_month"]) == sum(
        c["qty"] for c in customers
    )
    labels = {c["label"] for c in customers}
    assert any(label.startswith("Acme Co / ") for label in labels)
    assert not any(label.startswith("Beta Co") for label in labels)
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


def test_a3_a_superseded_decision_now_contributes_to_the_sheet(db, chain):
    """A3 (owner ruling 22 Sep - "read from OI, don't care about supply decision"):
    inverts and retires `test_s14_a_superseded_decision_contributes_nothing_to_the_sheet`
    - the `so_supply_decisions` join is gone, so a Buy row pointing at a SUPERSEDED
    decision is counted exactly like any other raised/placed row now. The decision's own
    state plays no part in the sheet any more."""
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                         buy_qty=9, decision_state="superseded")
    leg["inquiry_row"].delivery_date = date(2026, 9, 1)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    assert row["delivery_by_month"] == [{"month": "2026-09", "qty": 9}], row["delivery_by_month"]
    assert len(row["project_customers"]) == 1
    assert row["project_customers"][0]["qty"] == 9


# =====================================================================================
# A3/A5 (PLAN-order-sheet-oi-reports-22sep.md, AC-A4/AC-A5): `_project_inquiry_map` reads
# the OI rows the ENGINE would buy for, scoped to the RUN'S OWN Start Plan scope -
# `so_supply_decisions` plays no part. New signature:
# `_project_inquiry_map(db, product_ids, *, so_numbers=None, horizon_start=None, horizon=None)`.
#
# Predicate (captain ruling 23 Sep after review, superseding the plan's first cut):
# verb IN ('ORDER', 'ORDER_BACK'), state IN ('raised', 'partly_linked'), not redirected,
# ack_state IN ('acknowledged', 'changed'), owed (qty minus linked minus bundled) > 0,
# printed qty = owed. Product read off the CORE line (`sol.product_id`), not the project
# line's own copy. SO in `so_numbers` when the list is non-``None``, `delivery_date`
# inside `[horizon_start, horizon]` when given (a NULL delivery date is always included).
# =====================================================================================

def _scope_row(db, *, product, qty, delivery=None, verb=None, state=None, ack_state=None,
               so_number=None, customer_name="Scope customer", project_label=None,
               project_title=None, redirected=False, delivered=0, line_qty=None):
    """The A3/A5 "engine scope" shape (ruling 23 Sep): a project SO line reconciled to a
    REAL core `sales_order_lines` row - `run_scope_oi_rows` now reads product and the
    owed figure off that core line, `sol`, the same reconciled line the engine's own
    confirmed leg requires via `psl.core_sales_order_line_id` - with a Buy-verb Order
    Inquiry row pointing at it and NO `supply_decision_id` at all: the SRTWB248 case the
    plan's own "Measured" section names (a raised row nobody on the fulfilment board has
    confirmed yet, which the OLD `so_supply_decisions` INNER JOIN dropped). Deliberately
    skips `register_project`/`SOSupplyDecision` entirely - the new contract reads
    neither - so this stays a smaller chain than `test_channel_read_model._confirmed_leg`,
    not a copy of it; only the reconciled core line is shared machinery now.

    ``line_qty`` (default: `qty`) is the CORE line's own `qty_ordered` - the ceiling
    `_OWED_SQL`'s `LEAST(oir.qty, outstanding)` caps against; left at `qty` by default so
    a plain call's owed figure equals `qty` exactly, unless a test is deliberately proving
    the cap."""
    from app.models.project_so import (  # noqa: PLC0415
        ACK_ACKNOWLEDGED,
        INQUIRY_RAISED,
        IV_ORDER,
        OrderInquiry,
        OrderInquiryRow,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
    )
    from app.models.projects import Project  # noqa: PLC0415

    cust = Customer(id=_u(), customer_code=f"{MARKER}-{_u()[:8]}", customer_name=customer_name)
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=so_number or f"{MARKER}-SO-{_u()[:8]}", customer_id=cust.id,
        status="open", project_label=project_label,
    )
    db.add(so)
    db.flush()
    # The CORE line `run_scope_oi_rows` now reads product/owed off - the same reconciled
    # line the engine's confirmed leg requires.
    core_line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=None,
        qty_ordered=(line_qty if line_qty is not None else qty), qty_delivered=delivered,
        line_status="open",
    )
    db.add(core_line)
    db.flush()

    project_id = None
    if project_title:
        pid = _u()
        project = Project(
            id=pid, project_code=f"{MARKER}-{pid[:8]}", title=project_title,
            normalised_title=project_title.casefold(),
        )
        db.add(project)
        db.flush()
        project_id = project.id

    pso = ProjectSalesOrder(
        id=_u(), project_id=project_id, provisional_ref=f"{MARKER}-{_u()[:8]}", so_id=so.id,
    )
    db.add(pso)
    db.flush()
    psl = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=pso.id, line_no=1, product_id=product.id, qty=qty,
        core_sales_order_line_id=core_line.id,
    )
    db.add(psl)
    db.flush()
    inquiry = OrderInquiry(id=_u(), project_sales_order_id=pso.id)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), order_inquiry_id=inquiry.id, so_line_id=psl.id, qty=qty,
        verb=verb or IV_ORDER, state=state or INQUIRY_RAISED,
        ack_state=ack_state or ACK_ACKNOWLEDGED, delivery_date=delivery,
        supply_decision_id=None, redirected_to_pool=redirected,
    )
    db.add(row)
    db.flush()
    return {"so": so, "row": row, "psl": psl, "pso": pso, "customer": cust,
            "core_line": core_line}


def _link_po_line(db, product):
    """A bare open PO line, ONLY to give `OrderInquiryLink.po_line_id` somewhere real to
    point at - the FK is enforced, and the half/fully-linked tests below do not care
    about the PO's own content, only that a link with a real quantity exists."""
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine  # noqa: PLC0415

    sup = _supplier(db, f"{MARKER}-LINKSUP-{_u()[:8]}")
    po = PurchaseOrder(
        id=_u(), po_number=f"{MARKER}-LPO-{_u()[:8]}"[:50], supplier_id=sup.id,
        status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=None,
        qty_ordered=1, qty_received=0, line_status="open",
    )
    db.add(line)
    db.flush()
    return line.id


def test_a3_form_leg_row_with_no_supply_decision_counts_in_project_qty(db, chain):
    """AC-A5: a raised row with `supply_decision_id IS NULL` (the CS form leg, never
    confirmed on the fulfilment board) reaches Project qty / Delivery / Project-customer
    under the new run-scope read - the SRTWB248 case the plan's own "Measured" section
    names (SO418869, 67 units, delivery 01/10, OI row raised, no decision - engine bought
    67, the OLD sheet showed Project qty 0)."""
    f = chain
    _scope_row(db, product=f["product"], qty=67, delivery=date(2026, 10, 1))

    out = svc._project_inquiry_map(db, [f["product"].id])

    bucket = out.get(str(f["product"].id))
    assert bucket is not None, "a form-leg row with no supply decision must reach the map"
    assert bucket["months"].get("2026-10") == 67.0, bucket


def test_a3_row_on_an_unpicked_so_is_absent_when_so_numbers_is_set(db, chain):
    """AC-A5: 'SO in the run's picked orders when set' - a row on an SO NOT in the run's
    `so_numbers` is out, even though it is otherwise in scope. Tightened (fix round 2,
    item 5): an IN-SCOPE row on the picked SO is seeded alongside, so the map is proven
    to hold EXACTLY the picked row's qty, not merely "something or nothing"."""
    f = chain
    picked = f"{MARKER}-SO-PICKED"
    other = f"{MARKER}-SO-OTHER"
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              so_number=other)
    _scope_row(db, product=f["product"], qty=15, delivery=date(2026, 10, 1),
              so_number=picked)

    out = svc._project_inquiry_map(db, [f["product"].id], so_numbers=[picked])

    bucket = out[str(f["product"].id)]
    assert bucket["months"] == {"2026-10": 15.0}, bucket


def test_a3_row_dated_after_the_horizon_is_absent(db, chain):
    """AC-A5: 'delivery inside the run's window' - a row due after `plan_horizon_date` is
    out of scope. Tightened (fix round 2, item 5): an IN-SCOPE row inside the window is
    seeded alongside, so the map is proven to hold EXACTLY the in-window row's qty."""
    f = chain
    _scope_row(db, product=f["product"], qty=10, delivery=date(2027, 3, 1))
    _scope_row(db, product=f["product"], qty=20, delivery=date(2026, 6, 1))

    out = svc._project_inquiry_map(
        db, [f["product"].id], horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    bucket = out[str(f["product"].id)]
    assert bucket["months"] == {"2026-06": 20.0}, bucket


def test_a3_undated_row_lands_under_the_null_month_even_inside_a_horizon(db, chain):
    """AC-A5: 'undated included' - a row with no delivery date is always in scope,
    whatever the run's own window, and lands under the null month exactly like today."""
    f = chain
    _scope_row(db, product=f["product"], qty=8, delivery=None)

    out = svc._project_inquiry_map(
        db, [f["product"].id], horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    bucket = out[str(f["product"].id)]
    assert bucket["months"].get(None) == 8.0, bucket


def test_a3_cancelled_row_and_rejected_ack_row_are_absent(db, chain):
    """AC-A5: `state <> cancelled` and `ack_state <> rejected` both still gate the row,
    even though the retired `so_supply_decisions` join no longer does the gating for
    free. Both rows below carry an ACTIVE decision (`_confirmed_leg`, which the OLD
    `so_supply_decisions` INNER JOIN would happily reach) so this proves the state/ack
    predicates are enforced by `_project_inquiry_map` itself - in particular, the OLD
    query has NO `ack_state` predicate at all, so the rejected-ack row is red today for
    the right reason: it currently reaches the map."""
    from app.models.project_so import ACK_REJECTED, INQUIRY_CANCELLED  # noqa: PLC0415

    f = chain
    _stock(db, f["product"], f["bin"], 0)
    cancelled_leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                                   buy_qty=5, inquiry_state=INQUIRY_CANCELLED)
    cancelled_leg["inquiry_row"].delivery_date = date(2026, 10, 1)
    rejected_leg = _confirmed_leg(db, product_id=f["product"].id, warehouse_id=f["bin"].id,
                                  buy_qty=6, ack_state=ACK_REJECTED)
    rejected_leg["inquiry_row"].delivery_date = date(2026, 10, 1)
    db.flush()

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


# =====================================================================================
# Item 1 (fix round 2, 23 Sep review): the engine's OWN buying predicate, not the
# plan's first (looser) cut - a placed, actioned, awaiting-ack, redirected or fully
# linked row is absent; a half-linked row counts its owed half only.
# =====================================================================================

def test_a3_placed_row_is_absent(db, chain):
    """A PLACED row (already sourced against a document) is not something the engine
    buys for any more, so it is absent - `state IN ('raised', 'partly_linked')` excludes
    it."""
    from app.models.project_so import INQUIRY_PLACED  # noqa: PLC0415

    f = chain
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              state=INQUIRY_PLACED)

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


def test_a3_actioned_row_is_absent(db, chain):
    """An ACTIONED row (purchasing has already worked it) is absent for the same reason
    a placed one is."""
    from app.models.project_so import INQUIRY_ACTIONED  # noqa: PLC0415

    f = chain
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              state=INQUIRY_ACTIONED)

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


def test_a3_awaiting_ack_row_is_absent(db, chain):
    """The reorder plan buys only against ACKNOWLEDGED/CHANGED rows (`PLANNED_ACK_
    STATES`) - an AWAITING row is a count on the plan page, never something purchasing
    may buy against yet, so it is absent."""
    from app.models.project_so import ACK_AWAITING  # noqa: PLC0415

    f = chain
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              ack_state=ACK_AWAITING)

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


def test_a3_redirected_row_is_absent(db, chain):
    """A REDIRECTED row's document has already shipped to somebody else's order
    (`NOT_REDIRECTED_SQL`) - netting it again would count the same requirement twice, so
    it is absent even though every other predicate on it is satisfied."""
    f = chain
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              redirected=True)

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


def test_a3_fully_linked_row_is_absent(db, chain):
    """A row whose full quantity is already linked to a document owes nothing more -
    owed (qty minus linked) is 0, so it is absent whatever its state says. `state =
    partly_linked` here, deliberately in scope on every OTHER predicate, so this proves
    the OWED clause alone, not the state clause."""
    from app.models.project_so import INQUIRY_PARTLY_LINKED, OrderInquiryLink  # noqa: PLC0415

    f = chain
    scope = _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
                       state=INQUIRY_PARTLY_LINKED)
    po_line_id = _link_po_line(db, f["product"])
    db.add(OrderInquiryLink(id=_u(), row_id=scope["row"].id, po_line_id=po_line_id, qty=10))
    db.flush()

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


def test_a3_half_linked_row_counts_its_owed_half_only(db, chain):
    """A row half-linked to a document owes only its remaining half - `run_scope_oi_
    rows` prints the OWED figure (qty minus linked), never the row's raw `qty`."""
    from app.models.project_so import INQUIRY_PARTLY_LINKED, OrderInquiryLink  # noqa: PLC0415

    f = chain
    scope = _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
                       state=INQUIRY_PARTLY_LINKED)
    po_line_id = _link_po_line(db, f["product"])
    db.add(OrderInquiryLink(id=_u(), row_id=scope["row"].id, po_line_id=po_line_id, qty=4))
    db.flush()

    out = svc._project_inquiry_map(db, [f["product"].id])

    bucket = out[str(f["product"].id)]
    assert bucket["months"].get("2026-10") == 6.0, bucket


def test_a3_customer_label_uses_the_so_project_label_when_no_project_title(db, chain):
    """AC-A4: `project_customer_label(customer, coalesce(project title, SO project
    label))` - an adopted AutoCount SO with a project label but no `projects.projects`
    row prints `CUSTOMER / LABEL`, never the customer alone."""
    f = chain
    _scope_row(db, product=f["product"], qty=4, delivery=date(2026, 10, 1),
              customer_name="APEX CONNECTION", project_label="DNC / TITAN RITZ")

    out = svc._project_inquiry_map(db, [f["product"].id])

    labels = set(out[str(f["product"].id)]["customers"])
    assert labels == {"APEX CONNECTION / DNC / TITAN RITZ"}, labels


def test_a3_customer_label_prefers_the_registered_project_title_over_the_so_label(db, chain):
    """AC-A4: with a registered project title, the title wins over the SO's own label."""
    f = chain
    _scope_row(db, product=f["product"], qty=4, delivery=date(2026, 10, 1),
              customer_name="APEX CONNECTION", project_label="DNC / TITAN RITZ",
              project_title="Titan Ritz Tower")

    out = svc._project_inquiry_map(db, [f["product"].id])

    labels = set(out[str(f["product"].id)]["customers"])
    assert labels == {"APEX CONNECTION / Titan Ritz Tower"}, labels


def test_a5_write_rows_scopes_project_customers_to_the_runs_own_so_numbers(db, chain):
    """AC-A5/AC-A6 wiring: `write_rows` passes the run's OWN `so_numbers` through to
    `_project_inquiry_map` (the tests above call that function directly), so a row on an
    un-picked SO never reaches the frozen `project_customers` / `delivery_by_month` at
    all. Two OI rows on the SAME product, two different SOs - only the picked one's qty
    survives the freeze into `scm.order_summary_row`."""
    f = chain
    picked_so = f"{MARKER}-SO-PICKED"
    other_so = f"{MARKER}-SO-OTHER"
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              so_number=picked_so, customer_name="Picked customer")
    _scope_row(db, product=f["product"], qty=25, delivery=date(2026, 10, 1),
              so_number=other_so, customer_name="Other customer")
    f["run"].so_numbers = [picked_so]
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    customers = row["project_customers"]
    assert sum(c["qty"] for c in customers) == 10.0, customers
    assert not any("Other customer" in c["label"] for c in customers), customers
    months = {m["month"]: m["qty"] for m in row["delivery_by_month"]}
    assert months == {"2026-10": 10.0}, months


def test_a5b_write_rows_a_picked_so_row_after_the_horizon_is_absent(db, chain):
    """AC-A5b: a `write_rows`-level pin for the window - a picked-SO row dated AFTER the
    run's own `plan_horizon_date` is absent from the frozen `project_customers` /
    `delivery_by_month`, even though its SO is picked."""
    f = chain
    picked_so = f"{MARKER}-SO-PICKED"
    _scope_row(db, product=f["product"], qty=10, delivery=date(2027, 3, 1),
              so_number=picked_so, customer_name="Late customer")
    f["run"].so_numbers = [picked_so]
    f["run"].plan_horizon_start = date(2026, 1, 1)
    f["run"].plan_horizon_date = date(2026, 12, 31)
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    assert row["project_customers"] == [], row["project_customers"]
    assert row["delivery_by_month"] == [], row["delivery_by_month"]


# =====================================================================================
# AC-A9 regression pin: adding the Last cost lookup (A4) beside the Supplier column must
# not disturb it - Supplier still names the newest non-cancelled PO's supplier.
# =====================================================================================

def test_a9_supplier_still_names_the_last_purchase_supplier(db, chain):
    f = chain
    _stock(db, f["product"], f["bin"], 0)
    old_sup = _supplier(db, f"{MARKER} old supplier")
    new_sup = _supplier(db, f"{MARKER} new supplier")
    _po(db, f["product"], f["bin"], 10, supplier=old_sup, issued_days_ago=60)
    _po(db, f["product"], f["bin"], 5, supplier=new_sup, issued_days_ago=5)

    assert svc.write_rows(db, f["run"].id) == 1
    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    assert row["supplier_name"] == f"{MARKER} new supplier"


# =====================================================================================
# AC-A7/AC-A8: `_last_cost_map` - the newest non-cancelled PO line's unit cost, with the
# LINE's own currency when set, else the PO HEADER's - never a literal default.
#
# Cost figures below are deliberately picked to be unambiguous under `_qty_text`-style
# trimming: a whole number (15 -> "15", no trailing ".00") and a fraction with no
# trailing zero (8.25 -> "8.25") - "12.50" is avoided here because `_qty_text`'s own
# trimming would print it as "12.5", which a plain money example cannot disambiguate.
# =====================================================================================

def test_last_cost_map_reads_the_newest_non_cancelled_po_lines_cost_and_currency(db, chain):
    f = chain
    sup = _supplier(db, f"{MARKER} cost supplier")
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=99, currency="USD",
       issued_days_ago=60)
    _po(db, f["product"], f["bin"], 5, supplier=sup, cost=8.25, currency="CNY",
       issued_days_ago=5)

    out = svc._last_cost_map(db, [f["product"].product_code])

    assert out[f["product"].product_code] == "8.25 CNY", out


def test_last_cost_map_excludes_a_cancelled_po_even_when_it_is_the_newest(db, chain):
    f = chain
    sup = _supplier(db, f"{MARKER} cancel supplier")
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=15, currency="MYR",
       issued_days_ago=60)
    cancelled = _po(db, f["product"], f["bin"], 5, supplier=sup, cost=999, currency="USD",
                    issued_days_ago=1)
    db.execute(text("UPDATE purchase_orders SET status = 'cancelled' WHERE id = :id"),
              {"id": cancelled.id})
    db.flush()

    out = svc._last_cost_map(db, [f["product"].product_code])

    # AC-A8: money prints with TWO decimals ("15.00 MYR"), not `_qty_text`'s own
    # quantity-trimming ("15 MYR") - coder fix round, 23 Sep: the ONLY seam that pins a
    # bare whole-number cost is `test_last_cost_map_reads_the_newest_non_cancelled_po_
    # lines_cost_and_currency`'s "8.25 CNY", which already carries two decimals.
    assert out[f["product"].product_code] == "15.00 MYR", out


def test_last_cost_map_falls_back_to_the_po_headers_currency_when_the_line_carries_none(db, chain):
    """AC-A8b (fix round 2, 23 Sep): a NON-MYR header (USD here) with a NULL-currency
    line - a literal default (which would almost always print "MYR" and pass by
    coincidence) cannot pass this test."""
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    f = chain
    sup = _supplier(db, f"{MARKER} header currency supplier")
    po = PurchaseOrder(
        id=_u(), po_number=f"{MARKER}-PO-{_u()[:8]}"[:50], supplier_id=sup.id,
        status="active", issue_date=date.today(), currency="USD",
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=f["product"].id,
        warehouse_id=f["bin"].id, qty_ordered=5, qty_received=0, unit_cost=15,
        currency=None, line_status="open",
    ))
    db.flush()

    out = svc._last_cost_map(db, [f["product"].product_code])

    assert out[f["product"].product_code] == "15.00 USD", out


def test_last_cost_map_omits_a_product_with_no_po_line_carrying_a_cost(db, chain):
    """AC-A8: blank when the product has no PO line with a cost - never a false 0."""
    f = chain

    out = svc._last_cost_map(db, [f["product"].product_code])

    assert f["product"].product_code not in out


# =====================================================================================
# AC-A10 (fix round 2, item 7/8): company isolation. `products.product_code` is unique
# PER COMPANY (`uq_products_company_product_code`), so two companies can share one
# code - `_last_cost_map` must scope on the PRODUCT row's own company, not merely the
# PO line's, or a code collision lets another company's cost win the pick.
# =====================================================================================

def test_last_cost_map_excludes_a_second_companys_po_line_sharing_the_same_code(db, chain):
    """A second company's costed PO line for a product carrying the SAME code as this
    company's must not win `_last_cost_map`'s `DISTINCT ON (p.product_code)` slot."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product
    from tests.scm.conftest import SORENTO_COMPANY_ID

    f = chain
    set_company_scope(db, None)
    other = Company(id=_u(), code=f"{MARKER}-OTHCO"[:20], name=f"{MARKER} other company")
    db.add(other)
    db.flush()
    other_product = Product(
        id=_u(), company_id=other.id, product_code=f["product"].product_code,
        product_name="other company's copy", category_id=f["cat"].id,
        base_uom_id=f["uom"].id, list_price=0, is_active=True, is_discontinued=False,
    )
    db.add(other_product)
    db.flush()
    other_sup = Supplier(
        id=_u(), company_id=other.id, supplier_code=f"{MARKER}-OTHSUP"[:30],
        supplier_name="other supplier",
    )
    db.add(other_sup)
    db.flush()
    other_po = PurchaseOrder(
        id=_u(), company_id=other.id, po_number=f"{MARKER}-OTHPO"[:50],
        supplier_id=other_sup.id, status="active", issue_date=date.today(), currency="USD",
    )
    db.add(other_po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), company_id=other.id, purchase_order_id=other_po.id,
        product_id=other_product.id, warehouse_id=None, qty_ordered=5, qty_received=0,
        unit_cost=999, currency="USD", line_status="open",
    ))
    db.flush()
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    out = svc._last_cost_map(db, [f["product"].product_code])

    assert f["product"].product_code not in out, (
        "the OTHER company's costed line must not win this company's DISTINCT ON slot: "
        f"{out}"
    )


def test_project_inquiry_map_excludes_a_second_companys_oi_row(db, chain):
    """AC-A10: an OI chain belonging to ANOTHER company must not reach
    `_project_inquiry_map` - the company predicate on `so.company_id`
    (`run_scope_oi_rows`) is the backstop, even for a row that (implausibly) names
    THIS company's product id."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from tests.scm.conftest import SORENTO_COMPANY_ID

    f = chain
    set_company_scope(db, None)
    other = Company(id=_u(), code=f"{MARKER}-OTHCO2"[:20], name=f"{MARKER} other company 2")
    db.add(other)
    db.flush()
    set_company_scope(db, frozenset({str(other.id)}))
    _scope_row(db, product=f["product"], qty=10, delivery=date(2026, 10, 1),
              customer_name="Other company customer")
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    out = svc._project_inquiry_map(db, [f["product"].id])

    assert str(f["product"].id) not in out or out[str(f["product"].id)]["months"] == {}


# --- AC-S14.4: export columns, in the paper sheet's order ---------------------------

def test_s14_export_columns_match_the_paper_sheet_order():
    # issue #795 (Slice 2 test 10): Suggested qty + Suggestion now sit between Dealer o/s
    # and Order qty; every other column keeps its old order (AC-7). AC-A7 (Lane A): "Last
    # cost" now sits immediately right of Supplier, 17 columns total.
    assert svc._EXPORT_COLUMNS == (
        "Item code", "BRW on hand", "Reorder level", "Project qty", "Dealer o/s",
        "Suggested qty", "Suggestion", "Order qty", "Delivery", "Project / customer",
        "Supplier", "Last cost", "BRW PO qty", "BRW incoming qty", "Last in qty",
        "Last in date", "Remarks",
    )


def test_a4_pdf_list_and_num_columns_shift_by_one_for_last_cost():
    """AC-A7: every column after Supplier moves one to the right on the PDF's own class
    maps - Delivery/Project-customer (8, 9), then BRW PO qty/BRW incoming qty/Last in qty
    (12, 13, 14) in the list class; the numeric set (1..5, 7) is untouched, since Last
    cost (11) is a text cell, never right-aligned as a number. AC-A6b (fix round 2, 23
    Sep): Suggestion (6) joins the list class too, since it now prints one part per line."""
    assert svc._PDF_LIST_COLUMNS == (6, 8, 9, 12, 13, 14)
    assert svc._PDF_NUM_COLUMNS == (1, 2, 3, 4, 5, 7)
    assert 11 not in svc._PDF_LIST_COLUMNS and 11 not in svc._PDF_NUM_COLUMNS, (
        "Last cost is neither a wrapped list cell nor a right-aligned number"
    )


def test_a4_xlsx_column_widths_has_seventeen_keys():
    """AC-A7: the widths map grows one more key (Q) for the new column, A..Q."""
    assert set(svc._XLSX_COLUMN_WIDTHS) == set("ABCDEFGHIJKLMNOPQ")


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
    # AC-48/AC-55 (owner ruling, 15 Sep): last in carries the SPO/container beside the
    # date/qty - the "Last in qty" cell prints all three as ONE document-shaped TEXT
    # cell, like the PO/incoming cells' own shape.
    "last_receipt": {
        "date": "2026-07-21", "qty": 300,
        "spo_number": "202608-S0084", "container": "TLLU8306312",
    },
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
    # AC-A7/AC-A8: `_export_rows` now takes a second `last_cost` argument, keyed by
    # product code, so the row builder never re-derives the cost itself. AC-A2: "Last in
    # qty" drops the SPO number - the container and quantity are what survives.
    (row,) = svc._export_rows([_FULL_ROW], {"ZZTS14-SKU": "12.50 CNY"})
    assert row == (
        "ZZTS14-SKU", "100", "250", "8", "12", "12", "below level: net 5 <= ROP 10", "20",
        "Jul - 5\nAug - 3", "Acme Co / Tower A - 5\nBeta Co - 3",
        "Acme Supplier", "12.50 CNY", "40", "15", "TLLU8306312 - 300", "21/07/2026",
        "MOQ 1000",
    )


def test_s14_export_rows_blank_cells_when_the_row_has_nothing_to_show():
    (row,) = svc._export_rows([_BLANK_ROW], {})
    assert row == (
        "ZZTS14-BLANK", "0", "", "0", "0", "0", "", "",
        "", "", "", "", "0", "0", "", "", "",
    )


def test_s14_export_xlsx_rows_keep_quantities_as_numbers_and_blanks_as_empty_string():
    (full, blank) = svc._export_xlsx_rows([_FULL_ROW, _BLANK_ROW], {"ZZTS14-SKU": "12.50 CNY"})
    # Item code / Suggestion / Delivery / Project-customer / Supplier / Last cost / Remarks
    # are text; every other column is a NUMBER (H1) so summing a column in Excel keeps
    # working. issue #795: Suggested qty (5) joins the numeric set; Order qty moves to 7.
    # AC-A7 (Lane A): Last cost (11, new) shifts BRW PO qty/BRW incoming qty to 12/13.
    # AC-55 (owner ruling, 15 Sep): "Last in qty" (14) is the ONE exception among the
    # quantity columns - it is now a document-shaped TEXT cell, like the PO/incoming
    # cells beside it, never a bare number.
    for idx in (1, 2, 3, 4, 5, 7, 12, 13):
        assert isinstance(full[idx], float), f"column {idx} must be numeric, got {full[idx]!r}"
    assert full[11] == "12.50 CNY", full[11]
    assert full[14] == "TLLU8306312 - 300", full[14]
    assert blank[2] == "", "a NULL reorder level must be a blank cell, not 0"
    assert blank[5] == 0.0, "Suggested qty prints 0, not blank, even on an empty row"
    assert blank[7] == "", "no chosen qty must be a blank cell, not 0"
    assert blank[11] == "", "no PO cost line must be a blank Last cost cell"
    assert blank[14] == "", "no last-in receipt must be a blank Last in qty cell"
    assert blank[15] == "", "no last-in date must be a blank cell"


# --- AC-A1: BRW incoming qty drops the SPO number; BRW PO qty (AC-A3) is unchanged ----

def test_incoming_text_total_then_container_qty_lines_never_the_spo_number():
    """AC-A1: `_incoming_text` (the new sibling `_docs_text` keeps for BRW PO qty) prints
    the total, then one `<container> - <qty>` line per open SPO line, `<qty>` bare when
    the line names no container - the SPO number itself never appears in the cell."""
    text = svc._incoming_text(50, [
        {"number": "202608-S0084", "container": "TLLU8306312", "qty": 30},
        {"number": "202608-S0099", "container": None, "qty": 20},
    ])
    assert text == "50\nTLLU8306312 - 30\n20"
    assert "202608-S0084" not in text
    assert "202608-S0099" not in text


def test_incoming_text_bare_total_when_no_open_documents():
    assert svc._incoming_text(50, []) == "50"


def test_export_xlsx_and_pdf_rows_incoming_cell_drops_the_spo_number_po_cell_keeps_it():
    """AC-A1/AC-A3, on the real row builders: BRW PO qty (index 12 on the A4 17-column
    layout) keeps its PO-number lines, BRW incoming qty (index 13) never shows the SPO
    number beside it - same total, two different cell shapes."""
    row = {
        **_BLANK_ROW,
        "product_code": "ZZTS14-DOC",
        "po_open_qty": 5,
        "po_open_docs": [{"number": "PO-A", "qty": 5}],
        "incoming_spo_qty": 30,
        "incoming_spo_docs": [
            {"number": "202608-S0084", "container": "TLLU8306312", "qty": 30},
        ],
    }
    (xlsx_row,) = svc._export_xlsx_rows([row], {})
    assert xlsx_row[12] == "5\nPO-A - 5"
    assert xlsx_row[13] == "30\nTLLU8306312 - 30"
    assert "202608-S0084" not in xlsx_row[13]

    (pdf_row,) = svc._export_rows([row], {})
    assert pdf_row[12] == "5\nPO-A - 5"
    assert pdf_row[13] == "30\nTLLU8306312 - 30"
    assert "202608-S0084" not in pdf_row[13]


def test_low_stock_sheet_incoming_cell_drops_the_spo_number():
    """AC-A1: the low stock report shares the order sheet's cell builders - its own BRW
    incoming qty cell (index 12 of `LOW_STOCK_COLUMNS`, unaffected by AC-A7 since the low
    stock sheet does not get the new Last cost column) must drop the SPO number too."""
    from app.services.scm.low_stock_report_service import _sheet_row

    row = {
        "product_code": "X",
        "po_open_qty": 5, "po_open_docs": [{"number": "PO-A", "qty": 5}],
        "incoming_spo_qty": 30,
        "incoming_spo_docs": [
            {"number": "202608-S0084", "container": "TLLU8306312", "qty": 30},
        ],
    }
    cells = _sheet_row(row, {}, include_supplier=True)
    assert cells[11] == "5\nPO-A - 5"
    assert cells[12] == "30\nTLLU8306312 - 30"
    assert "202608-S0084" not in cells[12]


# --- AC-A2/AC-55/AC-57: "Last in qty" is a document-shaped TEXT cell (owner ruling,
# second round, 15 Sep - "same like our PO qty"), and (Lane A, AC-A2) drops the SPO
# number the way BRW incoming qty does - the container and quantity are what a buyer
# acts on. --------------------------------------------------------------------------

def test_last_in_text_full_receipt_with_container():
    assert svc._last_in_text({
        "spo_number": "202608-S0084", "container": "TLLU8306312", "qty": 300,
    }) == "TLLU8306312 - 300"


def test_last_in_text_no_container():
    """AC-A2: no container named, and the SPO number is dropped too - the bare quantity,
    the same shape the pre-518 fallback below already prints."""
    assert svc._last_in_text({
        "spo_number": "202608-S0084", "container": None, "qty": 300,
    }) == "300"


def test_last_in_text_pre_518_row_prints_the_bare_quantity():
    """AC-57: a run frozen before migration 518 carries qty/date but NULL spo/container -
    the cell prints the bare quantity, never an error and never a false SPO."""
    assert svc._last_in_text({
        "spo_number": None, "container": None, "qty": 300,
    }) == "300"


def test_low_stock_sheet_last_in_qty_pre_518_row_prints_the_bare_quantity():
    """Workbook-level AC-57: the low stock sheet's own cell builder gets the same
    pre-518 fallback, not just the order sheet's."""
    from app.services.scm.low_stock_report_service import _sheet_row

    row = {"product_code": "X", "last_receipt": {"qty": 300, "date": None,
                                                   "spo_number": None, "container": None}}
    assert _sheet_row(row, {}, include_supplier=True)[13] == "300"


def test_last_in_text_blank_when_no_receipt():
    assert svc._last_in_text(None) == ""


def test_last_in_text_container_without_spo_number_still_prints_the_container():
    """Item 6 (fix round 2, 23 Sep review): the bare-qty branch is gated on CONTAINER,
    never on the SPO number - a receipt naming a container but no SPO number must still
    print `"<container> - <qty>"`, not fall through to the bare quantity. AC-A2 only
    drops the SPO number itself; it never said a missing SPO number blanks the container
    too."""
    assert svc._last_in_text({
        "spo_number": None, "container": "TLLU8306312", "qty": 300,
    }) == "TLLU8306312 - 300"


def test_last_in_qty_pdf_cell_is_list_class_not_num():
    """AC-56: the PDF's "Last in qty" cell (index 14 on the AC-A7 17-column layout) takes
    the list/left-aligned class like the PO/incoming document cells beside it, never the
    right-aligned num class."""
    assert 14 not in svc._PDF_NUM_COLUMNS, (
        "Last in qty is a document-shaped TEXT cell now, not a right-aligned number"
    )
    assert 14 in svc._PDF_LIST_COLUMNS


def test_suggestion_pdf_cell_keeps_its_line_breaks():
    """AC-A6b (fix round 2, 23 Sep): Suggestion (index 6) now prints one part per line
    (`_suggestion_text`'s "\\n" join) - the PDF cell must wrap it the same way Delivery/
    Project-customer already do, not collapse a multi-part Suggestion onto one line."""
    row = {**_BLANK_ROW, "product_code": "ZZTS14-SUG", "suggestion": "Stock: 5\nBuy: 10"}
    (text_row,) = svc._export_rows([row], {})
    html = svc._export_pdf_html([text_row], "2026-09-10")

    assert 6 in svc._PDF_LIST_COLUMNS
    assert 6 not in svc._PDF_NUM_COLUMNS
    assert '<td class="list">Stock: 5\nBuy: 10</td>' in html, html


def test_s14_null_pool_on_hand_exports_blank_not_zero():
    """A run frozen before migration 504 carries `pool_on_hand = NULL` (never re-run) -
    the export must print a blank BRW on hand, not a false zero stock count, in both the
    PDF's text shape and the workbook's numeric shape (reviewer fix round, 10 Sep)."""
    null_pool_row = {**_BLANK_ROW, "product_code": "ZZTS14-NULLPOOL", "pool_on_hand": None}

    (row,) = svc._export_rows([null_pool_row], {})
    assert row[1] == "", "a NULL pool_on_hand must be a blank PDF cell, not '0'"

    (xlsx_row,) = svc._export_xlsx_rows([null_pool_row], {})
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

    rows = svc._export_xlsx_rows([_FULL_ROW, _BLANK_ROW], {})
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
    rows = svc._export_rows([_FULL_ROW], {})
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
    rows = svc._export_rows([_FULL_ROW], {})
    html = svc._export_pdf_html(rows, "2026-09-10")
    assert "Jul - 5\nAug - 3" in html or "Jul - 5<br>Aug - 3" in html


# --- PLAN-reorder-one-formula.md, S4/AC-4: the Suggestion is a DISPLAY of the net -------
#
# Hand-built `ReorderRecommendation` rows, the idiom `test_product_grain_summary.py`
# documents (`_rec`/`single_location_plan_basis`) for isolating `write_rows`/
# `_suggestion_text` arithmetic from the engine's own trigger/sizing behaviour, which
# `test_reorder_one_formula.py` covers with a real run. `decision_grain='product'` so
# `_belongs_on_the_book` admits every case, including the covered ("Nothing") one, which
# carries no `buy`/`exception` row at all.

def test_suggestion_parts_are_display_of_the_net():
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.models.scm import ReorderRecommendation, ReorderRun
    from tests.scm.conftest import single_location_plan_basis
    from tests.scm.test_product_grain_summary import _product as _pgs_product
    from tests.scm.test_product_grain_summary import _row as _pgs_row
    from tests.scm.test_product_grain_summary import _run as _pgs_run
    from tests.scm.test_product_grain_summary import _warehouse as _pgs_warehouse
    from tests.scm.test_summary_order_service import pg_session as _pg_session

    with _pg_session() as db:
        run = _pgs_run(db, decision_grain="product", contract_version=1)

        # Case 1: B2155-NL-BLUE's own figures. need = 493 + 170 - 0 = 663;
        # buy = 663 - 128 (on hand) - 339 (open PO) = 196.
        b2155 = _pgs_product(db, stem="B2155")
        wh1 = _pgs_warehouse(db, stem="W1")
        from app.models.inventory import Stock
        db.add(Stock(id=str(uuid.uuid4()), product_id=b2155.id, warehouse_id=wh1.id,
                     quantity_on_hand=128))
        sup1 = Supplier(id=str(uuid.uuid4()), supplier_code=f"{MARKER}-S1"[:30],
                        supplier_name=f"{MARKER} supplier 1")
        db.add(sup1)
        db.flush()
        po1 = PurchaseOrder(id=str(uuid.uuid4()), po_number=f"{MARKER}-PO1"[:50],
                           supplier_id=sup1.id, status="active",
                           issue_date=date.today() - timedelta(days=10))
        db.add(po1)
        db.flush()
        db.add(PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=po1.id, product_id=b2155.id,
            warehouse_id=wh1.id, qty_ordered=339, qty_received=0, line_status="open",
        ))
        b1_inputs = {"project_need": 493.0, "retail_need": 170.0,
                    "on_hand": 128.0, "po_ordered": 339.0, "reorder_level": None}
        b1_inputs["plan_basis"] = single_location_plan_basis(b1_inputs, wh1, rounded=196.0)
        db.add(ReorderRecommendation(
            id=str(uuid.uuid4()), run_id=run.id, rec_type="buy", product_id=b2155.id,
            warehouse_id=wh1.id, rounded_qty=196, inputs=b1_inputs, status="proposed",
        ))

        # Case 2: CSK2800-QT-shaped - pure confirmed project demand, no stock, no PO.
        csk = _pgs_product(db, stem="CSK")
        wh2 = _pgs_warehouse(db, stem="W2")
        c2_inputs = {"project_need": 914.0, "retail_need": 0.0,
                    "on_hand": 0.0, "po_ordered": 0.0, "reorder_level": None}
        c2_inputs["plan_basis"] = single_location_plan_basis(c2_inputs, wh2, rounded=914.0)
        db.add(ReorderRecommendation(
            id=str(uuid.uuid4()), run_id=run.id, rec_type="buy", product_id=csk.id,
            warehouse_id=wh2.id, rounded_qty=914, inputs=c2_inputs, status="proposed",
        ))

        # Case 3: covered - stock already meets the level, nothing to buy at all.
        cov = _pgs_product(db, stem="COV")
        wh3 = _pgs_warehouse(db, stem="W3")
        c3_inputs = {"project_need": 0.0, "retail_need": 0.0,
                    "on_hand": 135.0, "po_ordered": 0.0, "reorder_level": 120.0}
        c3_inputs["plan_basis"] = single_location_plan_basis(c3_inputs, wh3, rounded=0.0)
        db.add(ReorderRecommendation(
            id=str(uuid.uuid4()), run_id=run.id, rec_type="covered", product_id=cov.id,
            warehouse_id=wh3.id, rounded_qty=0, inputs=c3_inputs, status="proposed",
        ))
        # Case 4 (SF-4): ONE product, TWO independent sizing groups - two pools, sized
        # separately, 40 + 55. `_channel_freeze` sums them into `suggested_qty` 95, while
        # `_suggestion_text` used to read ONE recommendation's own `rounded_qty` - so the
        # sheet printed "Buy 40" beside a Suggested qty of 95.
        two = _pgs_product(db, stem="TWO")
        wh4 = _pgs_warehouse(db, stem="W4")
        wh5 = _pgs_warehouse(db, stem="W5")
        for wh, rounded in ((wh4, 40.0), (wh5, 55.0)):
            inp = {"project_need": 0.0, "retail_need": rounded,
                   "on_hand": 0.0, "po_ordered": 0.0, "reorder_level": 0.0}
            inp["plan_basis"] = single_location_plan_basis(inp, wh, rounded=rounded)
            db.add(ReorderRecommendation(
                id=str(uuid.uuid4()), run_id=run.id, rec_type="buy", product_id=two.id,
                warehouse_id=wh.id, rounded_qty=rounded, inputs=inp, status="proposed",
            ))
        # Case 5 (AC-A6b): a large on-hand figure, so the Stock part must still keep
        # `_fmt_int`'s own thousand-grouping ("12,345") once the parts move onto their
        # own lines with a colon - the owner: "the + + should be separated into lines so
        # it is easier to see".
        five = _pgs_product(db, stem="FIVE")
        wh6 = _pgs_warehouse(db, stem="W6")
        db.add(Stock(id=str(uuid.uuid4()), product_id=five.id, warehouse_id=wh6.id,
                     quantity_on_hand=12345))
        c5_inputs = {"project_need": 12400.0, "retail_need": 0.0,
                    "on_hand": 12345.0, "po_ordered": 0.0, "reorder_level": None}
        c5_inputs["plan_basis"] = single_location_plan_basis(c5_inputs, wh6, rounded=55.0)
        db.add(ReorderRecommendation(
            id=str(uuid.uuid4()), run_id=run.id, rec_type="buy", product_id=five.id,
            warehouse_id=wh6.id, rounded_qty=55, inputs=c5_inputs, status="proposed",
        ))
        db.flush()

        written = svc.write_rows(db, run.id)
        assert written == 5

        row1 = _pgs_row(db, run, b2155)
        assert float(row1.suggested_qty) == 196.0, (
            f"expected the rounded buy (196), got {row1.suggested_qty}"
        )
        # AC-A6b: one part per line, "Label: qty" (colon), not "Label qty" joined by " + ".
        assert row1.suggestion == "Stock: 128\nPO: 339\nBuy: 196", row1.suggestion

        row2 = _pgs_row(db, run, csk)
        assert float(row2.suggested_qty) == 914.0
        assert row2.suggestion == "Buy: 914", row2.suggestion

        row3 = _pgs_row(db, run, cov)
        assert float(row3.suggested_qty) == 0.0
        assert row3.suggestion == "Nothing", row3.suggestion

        # SF-4: one figure, printed twice - the Suggestion's Buy part IS the Suggested qty
        # column beside it, whatever the product's sizing groups summed to.
        row4 = _pgs_row(db, run, two)
        assert float(row4.suggested_qty) == 95.0, (
            f"two groups of 40 + 55 sum to 95, got {row4.suggested_qty}"
        )
        assert row4.suggestion == "Buy: 95", (
            f"the Suggestion's Buy part must equal the Suggested qty beside it, got "
            f"{row4.suggestion!r} against {row4.suggested_qty}"
        )

        row5 = _pgs_row(db, run, five)
        assert row5.suggestion == "Stock: 12,345\nBuy: 55", (
            f"the grouped Stock figure must survive the move to one-part-per-line: "
            f"{row5.suggestion!r}"
        )


def test_sheet_dealer_os_matches_grid_retail():
    """AC-10: the exported sheet's "Dealer o/s" column prints the SAME figure AC-9 pins
    on `OrderSummaryRow.dealer_outstanding` - the run's own horizoned retail, not the
    unfiltered SO book. Red for the same reason AC-9 is: `write_rows` has not yet learned
    to prefer the frozen `retail_committed` over `_demand_aggregates`'s SO-book read.
    """
    from app.models.inventory import Stock, Warehouse
    from app.models.order import Customer, SalesOrder, SalesOrderLine
    from app.models.procurement import ProductSupplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.scm import reorder_engine as eng
    from app.services.scm import reorder_run_service as rrs
    from tests.scm.test_summary_order_service import _supplier as _sos_supplier
    from tests.scm.test_summary_order_service import pg_session as _pg_session

    with _pg_session() as db:
        eng.ensure_reorder_policy_defaults(db)
        db.execute(text("UPDATE scm.reorder_policy SET policy_type = 'reorder_point'"))
        db.flush()

        cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT"[:40],
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} uom", uom_code=f"{MARKER}-U"[:20])
        db.add_all([cat, uom])
        db.flush()
        product = Product(
            id=_u(), product_code=f"{MARKER}-SHEET-{_u()[:8]}",
            product_name="ZZTOSHEET AC-10 product", category_id=cat.id, base_uom_id=uom.id,
            list_price=0, is_active=True, is_discontinued=False,
        )
        wh = Warehouse(
            id=_u(), warehouse_code=f"{MARKER}-SHW"[:30], warehouse_name="w",
            is_active=True, counts_as_available=True,
        )
        db.add_all([product, wh])
        db.flush()
        db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=0))
        sup = _sos_supplier(db, f"{MARKER} sheet supplier")
        db.add(ProductSupplier(
            id=_u(), product_id=product.id, supplier_id=sup.id,
            standard_lead_time_days=30, unit_cost=10, currency="MYR", is_primary_supplier=True,
        ))
        db.flush()

        def _line(qty, required_date):
            cust = Customer(id=_u(), customer_code=f"{MARKER}-C-{_u()[:8]}", customer_name="Dealer")
            db.add(cust)
            db.flush()
            so = SalesOrder(id=_u(), so_number=f"{MARKER}-SO-{_u()[:8]}", customer_id=cust.id,
                            status="open", order_type="dealer", demand_class="retail")
            db.add(so)
            db.flush()
            db.add(SalesOrderLine(
                id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
                qty_ordered=qty, qty_delivered=0, required_date=required_date,
                line_status="open",
            ))
            db.flush()

        _line(170, date(2026, 6, 1))
        _line(1211, date(2027, 3, 1))

        created = rrs.create_run(
            db, [wh.warehouse_code], product_codes=[product.product_code], enqueue=False,
            plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        )
        rrs.run_reorder(created["run_id"], db=db)
        svc.write_rows(db, created["run_id"])

        row = svc.report(db, run_id=created["run_id"])["rows"][0]
        assert row["dealer_outstanding"] == 170.0, (
            f"expected the run's horizoned retail (170), got {row['dealer_outstanding']}"
        )

        data, _content_type, _filename = svc.export_report(
            db, run_id=created["run_id"], fmt="xlsx"
        )
        import openpyxl
        from io import BytesIO
        wb = openpyxl.load_workbook(BytesIO(data))
        ws = wb.active
        header = [c.value for c in ws[1]]
        col = header.index("Dealer o/s") + 1
        assert ws.cell(row=2, column=col).value == 170.0, (
            f"the exported sheet's Dealer o/s must match the grid's 170: "
            f"{ws.cell(row=2, column=col).value}"
        )
