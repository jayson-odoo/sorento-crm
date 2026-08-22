"""Preview and apply, through the database, over a two-week upload.

The two properties worth the most here:

* preview writes NOTHING, and
* apply writes exactly what preview promised.

A preview computed differently from the commit is a preview that lies, so both are asserted
against the same file rather than trusted because they share a function name.

Every product, warehouse, order and line is seeded by the test, under codes the test
generates (`tests/scm/_outstanding_workbooks.py`), and the upload is generated from the SAME
codes so the file and the rows cannot drift apart. This file used to seed the real extract's
literal codes - `BRW-BB`, `SRTWC8613-RL`, `SO397450` - and read the committed xlsx that names
them. That passes on an empty database and dies on any database that already holds them:

    duplicate key value violates unique constraint "uq_warehouses_company_warehouse_code"

which is the "borrowed row" failure in reverse. The committed fixtures stay where they belong,
in `test_outstanding_reader.py`, which tests parsing a real-shaped file and touches no
database.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    MARKER,
    Codes,
    make_codes,
    seed_catalogue,
    week1,
    week2,
    workbook,
)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    return make_codes()


@pytest.fixture()
def seeded(db, codes):
    """Products and warehouses under the exact codes this test's upload names."""
    seed_catalogue(db, codes)
    return codes


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


def _line_ids(db, so_number, item):
    return {str(r[0]) for r in db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = :so AND p.product_code = :item"
    ), {"so": so_number, "item": item}).fetchall()}


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #

def test_preview_on_an_empty_system_reports_every_line_as_new(db, seeded):
    res = svc.preview(db, week1(seeded), SO)

    assert res.ok
    assert res.counts["added"] == 5
    assert res.scope_documents == seeded.documents
    assert res.resolution_issues == []


def test_preview_writes_nothing(db, seeded):
    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    svc.preview(db, week1(seeded), SO)
    after = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    assert before == after


def test_an_unknown_item_is_reported_with_its_row_and_never_invented(db, seeded):
    """A typo must not become a SKU that then gets planned and purchased."""
    typo = f"{MARKER}-TYPO-{uuid.uuid4().hex[:8]}".upper()
    file = workbook(
        [
            [seeded.project_so, seeded.item_rl, 10, date(2026, 7, 1), seeded.loc_project],
            [seeded.project_so, typo, 10, date(2026, 7, 1), seeded.loc_project],
        ],
        headers=("S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION"),
    )

    res = svc.preview(db, file, SO)

    assert [i.value for i in res.resolution_issues] == [typo]
    assert res.counts["added"] == 1
    assert db.execute(text("SELECT count(*) FROM products WHERE product_code = :c"),
                      {"c": typo}).scalar() == 0


def test_preview_carries_sample_rows_not_only_counts(db, seeded):
    """The confirm screen has to show evidence; a bare count is not checkable."""
    svc.apply(db, week1(seeded), SO)
    res = svc.preview(db, week2(seeded), SO)

    assert "date_moved" in res.samples
    moved = res.samples["date_moved"][0]
    assert moved["item_code"] == seeded.item_rl
    assert moved["days_moved"] == 14
    assert moved["label"] == "TUJU RESIDENCE"


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #

def test_apply_creates_the_orders_and_lines(db, seeded):
    out = svc.apply(db, week1(seeded), SO)

    assert out["ok"] and out["applied"]["added"] == 5
    rows = _outstanding(db, seeded.project_so, seeded.item_rl)
    assert [(float(q), d) for q, d, _ in rows] == [
        (135.0, date(2026, 7, 1)), (72.0, date(2026, 8, 3))
    ]


def test_apply_matches_what_preview_promised(db, seeded):
    """A preview computed differently from the commit is a preview that lies."""
    svc.apply(db, week1(seeded), SO)

    promised = svc.preview(db, week2(seeded), SO).counts
    actual = svc.apply(db, week2(seeded), SO)["counts"]

    assert promised == actual


def test_the_second_upload_moves_a_date_in_place_rather_than_replacing_the_line(db, seeded):
    svc.apply(db, week1(seeded), SO)
    line_ids_before = _line_ids(db, seeded.project_so, seeded.item_rl)

    svc.apply(db, week2(seeded), SO)

    rows = _outstanding(db, seeded.project_so, seeded.item_rl)
    assert [(float(q), d) for q, d, _ in rows] == [
        (135.0, date(2026, 7, 15)),   # slipped two weeks, same row
        (90.0, date(2026, 8, 3)),     # grew 72 -> 90, did not move
    ]
    assert _line_ids(db, seeded.project_so, seeded.item_rl) == line_ids_before, \
        "the line was replaced instead of updated"


def test_a_delivered_line_is_closed_not_deleted(db, seeded):
    """The line was planned against; erasing it makes last week's plan unexplainable."""
    svc.apply(db, week1(seeded), SO)
    svc.apply(db, week2(seeded), SO)

    rows = db.execute(text(
        "SELECT sol.line_status FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = :so AND p.product_code = :item"
    ), {"so": seeded.project_so, "item": seeded.item_wt}).fetchall()
    assert [r[0] for r in rows] == ["closed"]


def test_a_closed_line_leaves_committed_demand(db, seeded):
    """The point of closing: scm.committed_v must stop counting it (migration 311)."""
    svc.apply(db, week1(seeded), SO)
    before = db.execute(text(
        "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
        "JOIN products p ON p.id = cv.product_id WHERE p.product_code = :item"
    ), {"item": seeded.item_wt}).scalar()

    svc.apply(db, week2(seeded), SO)
    after = db.execute(text(
        "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
        "JOIN products p ON p.id = cv.product_id WHERE p.product_code = :item"
    ), {"item": seeded.item_wt}).scalar()

    assert float(before) == 67.0     # 60 on the project + 7 on the dealer order
    assert float(after) == 7.0       # the project line closed, the dealer line remains


def test_reapplying_the_same_file_changes_nothing(db, seeded):
    """Uploading twice by accident must be a no-op, not a doubling."""
    svc.apply(db, week1(seeded), SO)
    second = svc.apply(db, week1(seeded), SO)

    assert second["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 5}
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number IN (:a, :b)"
    ), {"a": seeded.project_so, "b": seeded.dealer_so}).scalar() == 5


def test_an_order_outside_the_file_is_untouched(db, seeded):
    """A single-project export must not read as every other project being delivered."""
    svc.apply(db, week1(seeded), SO)

    unrelated = f"{MARKER}-SOX-{uuid.uuid4().hex[:8]}".upper()
    other = SalesOrder(id=_u(), so_number=unrelated, status="open")
    db.add(other)
    db.flush()
    pid = db.execute(text("SELECT id FROM products WHERE product_code = :c"),
                     {"c": seeded.item_new}).scalar()
    db.add(SalesOrderLine(id=_u(), sales_order_id=other.id, product_id=str(pid),
                          qty_ordered=500, qty_delivered=0, line_status="open",
                          required_date=date(2026, 12, 1)))
    db.flush()

    svc.apply(db, week2(seeded), SO)

    assert [r[2] for r in _outstanding(db, unrelated, seeded.item_new)] == ["open"]


def test_a_part_delivered_line_is_not_silently_undelivered(db, seeded):
    """The extract states OUTSTANDING quantity. Writing it straight into qty_ordered would
    resurrect quantity that has already gone out of the door."""
    svc.apply(db, week1(seeded), SO)
    line = db.execute(text(
        "SELECT sol.id FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = :so AND p.product_code = :item "
        "  AND sol.required_date = '2026-08-03'"
    ), {"so": seeded.project_so, "item": seeded.item_rl}).scalar()
    db.execute(text("UPDATE sales_order_lines SET qty_delivered = 20 WHERE id = :i"),
               {"i": str(line)})
    db.flush()

    # Week 2 states 90 still outstanding on that line.
    svc.apply(db, week2(seeded), SO)

    ordered, delivered = db.execute(text(
        "SELECT qty_ordered, qty_delivered FROM sales_order_lines WHERE id = :i"
    ), {"i": str(line)}).fetchone()
    assert float(delivered) == 20.0, "delivered quantity must never be rewritten"
    assert float(ordered) == 110.0, "ordered = already delivered 20 + still outstanding 90"


# --------------------------------------------------------------------------- #
# an unreadable date must never null a date the database already holds
# (19 Aug 2026 incident: 14,128 open lines lost their `required_date` this way)
# --------------------------------------------------------------------------- #

def test_apply_never_nulls_a_date_the_reader_could_not_read(db, seeded):
    svc.apply(db, week1(seeded), SO)  # the 1 Jul / 3 Aug lines exist, dated, from week 1

    file_data = workbook(
        [
            # Same line as week 1's 1 Jul row, quantity bumped, date cell unreadable.
            [seeded.project_so, seeded.item_rl, 150, "not-a-date", seeded.loc_project],
            [seeded.project_so, seeded.item_rl, 72, date(2026, 8, 3), seeded.loc_project],
        ],
        headers=("S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION"),
    )

    preview = svc.preview(db, file_data, SO)
    assert preview.counts["qty_changed"] == 1
    assert preview.counts["date_moved"] == 0
    assert any("could not read the date" in p.reason for p in preview.row_problems)
    assert preview.warnings
    assert "date the reader could not read" in preview.warnings[0]

    out = svc.apply(db, file_data, SO)
    assert out["ok"]
    assert out["counts"]["qty_changed"] == 1

    rows = _outstanding(db, seeded.project_so, seeded.item_rl)
    by_date = {d: float(q) for q, d, _status in rows}
    # The 1 Jul line's date SURVIVES untouched; its quantity is still allowed to change.
    assert by_date[date(2026, 7, 1)] == 150.0
    assert by_date[date(2026, 8, 3)] == 72.0
