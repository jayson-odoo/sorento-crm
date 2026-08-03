"""Preview and apply, through the database, using the committed xlsx fixtures.

The two properties worth the most here:

* preview writes NOTHING, and
* apply writes exactly what preview promised.

A preview computed differently from the commit is a preview that lies, so both are asserted
against the same file rather than trusted because they share a function name.

Every product, warehouse and customer is seeded by the test. CI's database has no data, and
borrowing a row is how a suite passes locally and dies in CI.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session

_FIX = Path(__file__).parent / "fixtures"

# Every code the fixtures reference. Seeded so the import resolves instead of reporting
# everything as unknown.
_ITEMS = ("SRTWC8613-RL", "SRTWT7408", "B2155-NL-BLUE", "C-FH24")
_LOCATIONS = ("BRW-BB", "BRW-SMC", "BRW-IB")


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db):
    """Products and warehouses under the exact codes the fixtures use."""
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = 'outstanding_so' LIMIT 1")).scalar():
        pytest.skip("no outstanding_so aliases seeded in this database")

    cat = ProductCategory(id=_u(), category_code=f"ZZIMP-{uuid.uuid4().hex[:6]}",
                          category_name="import test")
    uom = UnitOfMeasure(id=_u(), uom_code=f"ZZ{uuid.uuid4().hex[:4]}", uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()

    for code in _ITEMS:
        db.add(Product(id=_u(), product_code=code, product_name=code,
                       category_id=cat.id, base_uom_id=uom.id, list_price=0,
                       is_active=True, is_discontinued=False))
    for code in _LOCATIONS:
        db.add(Warehouse(id=_u(), warehouse_code=code, warehouse_name=code, is_active=True))
    db.flush()
    return True


def _bytes(name):
    return (_FIX / name).read_bytes()


def _outstanding(db, so_number, item):
    return db.execute(text(
        """
        SELECT (sol.qty_ordered - sol.qty_delivered), sol.required_date, sol.line_status
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        JOIN products p ON p.id = sol.product_id
        WHERE so.so_number = :so AND p.product_code = :item
        ORDER BY sol.required_date NULLS LAST
        """
    ), {"so": so_number, "item": item}).fetchall()


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #

def test_preview_on_an_empty_system_reports_every_line_as_new(db, seeded):
    res = svc.preview(db, _bytes("outstanding_so_sample.xlsx"), SO)

    assert res.ok
    assert res.counts["added"] == 5
    assert res.scope_documents == ("SO397450", "SO397512")
    assert res.resolution_issues == []


def test_preview_writes_nothing(db, seeded):
    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    svc.preview(db, _bytes("outstanding_so_sample.xlsx"), SO)
    after = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    assert before == after


def test_an_unknown_item_is_reported_with_its_row_and_never_invented(db, seeded):
    """A typo must not become a SKU that then gets planned and purchased."""
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION"])
    ws.append(["SO397450", "SRTWC8613-RL", 10, date(2026, 7, 1), "BRW-BB"])
    ws.append(["SO397450", "TYPOED-CODE", 10, date(2026, 7, 1), "BRW-BB"])
    buf = BytesIO()
    wb.save(buf)

    res = svc.preview(db, buf.getvalue(), SO)

    assert [i.value for i in res.resolution_issues] == ["TYPOED-CODE"]
    assert res.counts["added"] == 1
    assert db.execute(text("SELECT count(*) FROM products WHERE product_code = :c"),
                      {"c": "TYPOED-CODE"}).scalar() == 0


def test_preview_carries_sample_rows_not_only_counts(db, seeded):
    """The confirm screen has to show evidence; a bare count is not checkable."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    res = svc.preview(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)

    assert "date_moved" in res.samples
    moved = res.samples["date_moved"][0]
    assert moved["item_code"] == "SRTWC8613-RL"
    assert moved["days_moved"] == 14
    assert moved["label"] == "TUJU RESIDENCE"


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #

def test_apply_creates_the_orders_and_lines(db, seeded):
    out = svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)

    assert out["ok"] and out["applied"]["added"] == 5
    rows = _outstanding(db, "SO397450", "SRTWC8613-RL")
    assert [(float(q), d) for q, d, _ in rows] == [
        (135.0, date(2026, 7, 1)), (72.0, date(2026, 8, 3))
    ]


def test_apply_matches_what_preview_promised(db, seeded):
    """A preview computed differently from the commit is a preview that lies."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)

    promised = svc.preview(db, _bytes("outstanding_so_sample_week2.xlsx"), SO).counts
    actual = svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)["counts"]

    assert promised == actual


def test_the_second_upload_moves_a_date_in_place_rather_than_replacing_the_line(db, seeded):
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    line_ids_before = {str(r[0]) for r in db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = 'SO397450' AND p.product_code = 'SRTWC8613-RL'"
    )).fetchall()}

    svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)

    rows = _outstanding(db, "SO397450", "SRTWC8613-RL")
    assert [(float(q), d) for q, d, _ in rows] == [
        (135.0, date(2026, 7, 15)),   # slipped two weeks, same row
        (90.0, date(2026, 8, 3)),     # grew 72 -> 90, did not move
    ]
    line_ids_after = {str(r[0]) for r in db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = 'SO397450' AND p.product_code = 'SRTWC8613-RL'"
    )).fetchall()}
    assert line_ids_before == line_ids_after, "the line was replaced instead of updated"


def test_a_delivered_line_is_closed_not_deleted(db, seeded):
    """The line was planned against; erasing it makes last week's plan unexplainable."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)

    rows = db.execute(text(
        "SELECT sol.line_status FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = 'SO397450' AND p.product_code = 'SRTWT7408'"
    )).fetchall()
    assert [r[0] for r in rows] == ["closed"]


def test_a_closed_line_leaves_committed_demand(db, seeded):
    """The point of closing: scm.committed_v must stop counting it (migration 311)."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    before = db.execute(text(
        "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
        "JOIN products p ON p.id = cv.product_id WHERE p.product_code = 'SRTWT7408'"
    )).scalar()

    svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)
    after = db.execute(text(
        "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
        "JOIN products p ON p.id = cv.product_id WHERE p.product_code = 'SRTWT7408'"
    )).scalar()

    assert float(before) == 67.0     # 60 on the project + 7 on the dealer order
    assert float(after) == 7.0       # the project line closed, the dealer line remains


def test_reapplying_the_same_file_changes_nothing(db, seeded):
    """Uploading twice by accident must be a no-op, not a doubling."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    second = svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)

    assert second["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 5}
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number IN ('SO397450', 'SO397512')"
    )).scalar() == 5


def test_an_order_outside_the_file_is_untouched(db, seeded):
    """A single-project export must not read as every other project being delivered."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)

    other = SalesOrder(id=_u(), so_number="SO-UNRELATED", status="open")
    db.add(other)
    db.flush()
    pid = db.execute(text("SELECT id FROM products WHERE product_code = 'C-FH24'")).scalar()
    db.add(SalesOrderLine(id=_u(), sales_order_id=other.id, product_id=str(pid),
                          qty_ordered=500, qty_delivered=0, line_status="open",
                          required_date=date(2026, 12, 1)))
    db.flush()

    svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)

    assert [r[2] for r in _outstanding(db, "SO-UNRELATED", "C-FH24")] == ["open"]


def test_a_part_delivered_line_is_not_silently_undelivered(db, seeded):
    """The extract states OUTSTANDING quantity. Writing it straight into qty_ordered would
    resurrect quantity that has already gone out of the door."""
    svc.apply(db, _bytes("outstanding_so_sample.xlsx"), SO)
    line = db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = 'SO397450' AND p.product_code = 'SRTWC8613-RL' "
        "  AND sol.required_date = '2026-08-03'"
    )).scalar()
    db.execute(text("UPDATE sales_order_lines SET qty_delivered = 20 WHERE id = :i"),
               {"i": str(line)})
    db.flush()

    # Week 2 states 90 still outstanding on that line.
    svc.apply(db, _bytes("outstanding_so_sample_week2.xlsx"), SO)

    ordered, delivered = db.execute(text(
        "SELECT qty_ordered, qty_delivered FROM sales_order_lines WHERE id = :i"
    ), {"i": str(line)}).fetchone()
    assert float(delivered) == 20.0, "delivered quantity must never be rewritten"
    assert float(ordered) == 110.0, "ordered = already delivered 20 + still outstanding 90"
