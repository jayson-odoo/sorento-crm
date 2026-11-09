"""LOWSTOCK-LASTIN-LOCATION: the low stock report's per-location columns read ONLY the run's
own locations (owner ruling, 9 Nov 2026: "when I run BRW stock report it should take BRW
only"; the same for Reorder Planning and the daily low stock job).

Plan: `documentation/plans/scm/PLAN-lowstock-lastin-location-09nov.md`.

Every surface (the BRW low stock report and its Excel export, Reorder Planning's low stock
report, the daily job's report) prints the frozen rows `summary_order_service.write_rows`
writes for ONE reorder run, so the run's `warehouse_ids` is the one location scope. The
columns pinned here: BRW on hand, BRW PO qty, BRW incoming qty, Last in qty, Last in date.

Postgres, own seeded chain inside `pg_session`'s rolled-back transaction.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from io import BytesIO

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.services.scm import low_stock_report_service as low_stock
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session

MARKER = "ZZTLSL"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str, n: int = 30) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".upper()[:n]


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _warehouse(db, stem, *, segment=None):
    wh = Warehouse(
        id=_u(), warehouse_code=_code(stem), warehouse_name=stem,
        is_active=True, counts_as_available=True, segment=segment,
    )
    db.add(wh)
    db.flush()
    return wh


def _product(db, stem="SRTWT167-QT"):
    cat = ProductCategory(id=_u(), category_code=_code("CAT", 40), category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U", 20))
    db.add_all([cat, uom])
    db.flush()
    p = Product(
        id=_u(), product_code=_code(stem, 50), product_name=stem,
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p)
    db.flush()
    return p


def _run(db, warehouse_ids):
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        warehouse_ids=[str(w) for w in warehouse_ids] if warehouse_ids is not None else None,
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()
    return run


def _buy(db, run, product, wh, qty=10):
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=qty, status="proposed",
    ))
    db.flush()


def _spo(db, product, wh, qty, *, spo_number, container=None, expected=date(2026, 10, 25),
         received=0, created_at=None, location_code=None):
    a = SPOAllocation(
        id=_u(), spo_number=spo_number, product_id=product.id,
        warehouse_id=wh.id if wh is not None else None,
        location_code=location_code if location_code is not None else (
            wh.warehouse_code if wh is not None else None),
        allocated_quantity=qty, quantity_received=received,
        container_number=container, expected_date=expected,
    )
    if created_at is not None:
        a.created_at = created_at
    db.add(a)
    db.flush()
    return a


def _stock(db, product, wh, qty):
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=qty))
    db.flush()


def _po(db, product, wh, qty):
    s = Supplier(id=_u(), supplier_code=_code("S"), supplier_name="xiamen taiyang")
    db.add(s)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=_code("PO", 50), supplier_id=s.id, status="active",
                       issue_date=date(2026, 10, 1))
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_received=0, line_status="open",
    ))
    db.flush()
    return po


def _row(db, run, product) -> OrderSummaryRow:
    return db.query(OrderSummaryRow).filter(
        OrderSummaryRow.run_id == run.id, OrderSummaryRow.product_id == product.id,
    ).one()


def _srtwt167_qt(db):
    """The owner's case: ONE receipt (container KMTU9395907, 23/10 SPO, delivery 25/10)
    split into BRW 121, BRW-BB 180 and BRW-BB 99, the 99 the newest-created line."""
    brw = _warehouse(db, "BRW")
    brw_bb = _warehouse(db, "BRW-BB", segment="project")
    product = _product(db)
    spo = _code("SPO-2026/10", 50)
    _spo(db, product, brw, 121, spo_number=spo, container="KMTU9395907",
         created_at=datetime(2026, 10, 23, 9, 0, 0))
    _spo(db, product, brw_bb, 180, spo_number=spo, container="KMTU9395907",
         created_at=datetime(2026, 10, 23, 9, 0, 1))
    _spo(db, product, brw_bb, 99, spo_number=spo, container="KMTU9395907",
         created_at=datetime(2026, 10, 23, 9, 0, 2))
    return brw, brw_bb, product, spo


def test_brw_report_last_in_is_the_brw_line_of_a_split_receipt(db):
    """SRTWT167-QT: a BRW-only run's Last in is `KMTU9395907 - 121`, never the BRW-BB 99."""
    brw, _brw_bb, product, spo = _srtwt167_qt(db)
    run = _run(db, [brw.id])
    _buy(db, run, product, brw)

    assert svc.write_rows(db, run.id) == 1
    row = _row(db, run, product)
    assert float(row.last_receipt_qty) == 121.0
    assert row.last_receipt_spo_number == spo
    assert row.last_receipt_container_number == "KMTU9395907"
    assert row.last_receipt_date == date(2026, 10, 25)

    report_row = svc.report(db, run_id=run.id)["rows"][0]
    assert svc._last_in_text(report_row["last_receipt"]) == "KMTU9395907 - 121"


def test_a_project_bin_never_answers_last_in_even_on_a_run_that_covers_it(db):
    """The report's columns are BRW (site pool) columns: a run that also names the BRW-BB
    project bin still reads Last in from BRW only, the same rule BRW incoming qty has."""
    brw, brw_bb, product, _spo_number = _srtwt167_qt(db)
    run = _run(db, [brw.id, brw_bb.id])
    _buy(db, run, product, brw)

    svc.write_rows(db, run.id)
    assert float(_row(db, run, product).last_receipt_qty) == 121.0


def test_no_receipt_in_the_runs_locations_leaves_last_in_blank(db):
    """Never borrowed from another location: the only receipt is at a location the run
    did not select, so Last in qty and Last in date are blank."""
    brw = _warehouse(db, "BRW")
    other = _warehouse(db, "MWH")
    product = _product(db)
    _spo(db, product, other, 40, spo_number=_code("SPO", 50), container="TLLU0000001")
    run = _run(db, [brw.id])
    _buy(db, run, product, brw)

    svc.write_rows(db, run.id)
    row = _row(db, run, product)
    assert row.last_receipt_qty is None
    assert row.last_receipt_date is None
    assert row.last_receipt_spo_number is None
    assert row.last_receipt_container_number is None
    assert svc.report(db, run_id=run.id)["rows"][0]["last_receipt"] is None


def test_a_two_location_plan_reads_every_per_location_column_from_those_two_only(db):
    """Reorder Planning run over locations A and B; C is a third site-pool location the
    run did not select. On hand, PO qty, incoming qty and Last in all ignore C."""
    a = _warehouse(db, "LOCA")
    b = _warehouse(db, "LOCB")
    c = _warehouse(db, "LOCC")
    product = _product(db, "TWOLOC")
    _stock(db, product, a, 5)
    _stock(db, product, b, 7)
    _stock(db, product, c, 100)
    po_a = _po(db, product, a, 10)
    _po(db, product, c, 50)
    # Incoming: open, unreceived SPO lines.
    spo_b = _code("SPO-B", 50)
    _spo(db, product, b, 20, spo_number=spo_b, container="CONT-B", expected=date(2026, 9, 1))
    _spo(db, product, c, 30, spo_number=_code("SPO-C", 50), container="CONT-C",
         expected=date(2026, 11, 1))
    run = _run(db, [a.id, b.id])
    _buy(db, run, product, a)

    svc.write_rows(db, run.id)
    row = _row(db, run, product)
    assert float(row.pool_on_hand) == 12.0
    assert float(row.po_open_qty) == 10.0
    assert [d["number"] for d in row.po_open_docs] == [po_a.po_number]
    assert float(row.incoming_spo_qty) == 20.0
    assert [d.get("container") for d in row.incoming_spo_docs] == ["CONT-B"]
    # C's line is newer but outside the plan: B's line answers.
    assert row.last_receipt_spo_number == spo_b
    assert float(row.last_receipt_qty) == 20.0
    assert row.last_receipt_date == date(2026, 9, 1)


def test_a_line_known_only_by_its_location_code_still_counts_for_that_location(db):
    """An SPO line with no `warehouse_id` but the book's `location_code` of a selected
    location is that location's line (the chatbot's last-in tool reads it the same way,
    `purchase_order_service.spo_warehouse_predicate`)."""
    brw = _warehouse(db, "BRW")
    product = _product(db, "CODEONLY")
    spo = _code("SPO", 50)
    _spo(db, product, None, 64, spo_number=spo, location_code=brw.warehouse_code)
    run = _run(db, [brw.id])
    _buy(db, run, product, brw)

    svc.write_rows(db, run.id)
    assert _row(db, run, product).last_receipt_spo_number == spo


def test_the_daily_jobs_locations_bound_last_in(db):
    """The daily low stock job plans the `warehouse_codes` on its task config: the run
    `create_run` stamps for those codes is what bounds Last in, exactly as a manual plan."""
    from app.services.scm import reorder_run_service

    dealer_a = _warehouse(db, "DLRA")
    dealer_b = _warehouse(db, "DLRB")
    elsewhere = _warehouse(db, "ELSE")
    product = _product(db, "DAILY")
    spo_a = _code("SPO-A", 50)
    _spo(db, product, dealer_a, 11, spo_number=spo_a, expected=date(2026, 8, 1))
    _spo(db, product, dealer_b, 22, spo_number=_code("SPO-B", 50), expected=date(2026, 7, 1))
    _spo(db, product, elsewhere, 33, spo_number=_code("SPO-E", 50), expected=date(2026, 10, 1))

    created = reorder_run_service.create_run(
        db, [dealer_a.warehouse_code, dealer_b.warehouse_code], enqueue=False,
    )
    run = db.get(ReorderRun, created["run_id"])
    assert sorted(run.warehouse_ids) == sorted([dealer_a.id, dealer_b.id])
    run.status = "completed"
    run.decision_grain = "product"
    run.front_planning_contract_version = 1
    db.flush()
    _buy(db, run, product, dealer_a)

    svc.write_rows(db, run.id)
    row = _row(db, run, product)
    assert row.last_receipt_spo_number == spo_a
    assert float(row.last_receipt_qty) == 11.0


def test_excel_export_is_one_row_per_item_with_the_brw_last_in(db):
    """The Excel export of the BRW report: SRTWT167-QT's Last in reads `KMTU9395907 - 121`,
    and a product whose BRW PO qty cell lists two POs is still exactly ONE sheet row (the
    second PO stays inside that cell, never a row of its own)."""
    from openpyxl import load_workbook

    brw, _brw_bb, product, _spo_number = _srtwt167_qt(db)
    diy = _product(db, "SRTWT167-DIY")
    po1 = _po(db, diy, brw, 300)
    po2 = _po(db, diy, brw, 500)
    run = _run(db, [brw.id])
    _buy(db, run, product, brw)
    _buy(db, run, diy, brw)
    svc.write_rows(db, run.id)

    data, _ctype, _name, counts = low_stock.export_low_stock(db, run_id=run.id)
    assert counts["all"] == 2
    ws = load_workbook(BytesIO(data))["All"]
    header = [c.value for c in ws[1]]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert len(rows) == 2, rows
    by_code = {r[0]: dict(zip(header, r)) for r in rows}
    qt = by_code[product.product_code]
    assert qt["Last in qty"] == "KMTU9395907 - 121"
    assert qt["Last in date"] == "25/10/2026"
    po_cell = by_code[diy.product_code]["BRW PO qty"]
    assert po_cell.split("\n") == [
        "800",
        *sorted([f"{po1.po_number} - 300", f"{po2.po_number} - 500"]),
    ]
