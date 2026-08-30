"""What a LATER extract may and may not erase, plus the duplicate report at its source.

The defect suite pins that a repriced line is repriced and that a header carries the file's PO
DATE. Neither says what happens when the next file is SILENT about a column, and "refresh from
the file" implemented as a straight assignment quietly answers "blank it" - which is worse than
never having refreshed: the cash co-pilot ranks a line with no cost as if it were free, and
`scm.receipt_lead_v` measures nothing without `po.issue_date`. A value we know is never given
up because a later export left the cell empty.

The duplicate report is asserted at the READER, where it is produced: the service-level test
proves a human is told, this one proves what they are told (which row it collides with) and
that neither row was quietly dropped to make the problem go away.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.services.import_alias_service import AliasResolver
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    PO_MINIMAL,
    SUPPLIER_MAIN_LABEL,
    Codes,
    make_codes,
    po_minimal_row,
    po_row,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
)


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


def _line(db, po_number, item):
    return db.execute(text(
        "SELECT pol.unit_cost, pol.currency, pol.qty_ordered FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "JOIN products p ON p.id = pol.product_id "
        "WHERE po.po_number = :po AND p.product_code = :item"
    ), {"po": po_number, "item": item}).mappings().fetchone()


def _header(db, po_number):
    return db.execute(text(
        "SELECT issue_date, currency FROM purchase_orders WHERE po_number = :po"
    ), {"po": po_number}).mappings().fetchone()


def test_a_later_extract_with_an_empty_cost_cell_does_not_blank_the_price(db, seeded):
    """A blank cell is "not stated", not "free".

    The refresh exists so the co-pilot ranks on this week's price; implemented as an
    unconditional assignment it would also let one export with an empty UNIT COST column wipe
    every cost in scope, and a line with no cost ranks ahead of every real one.
    """
    def _file(qty, cost, ccy):
        return po_workbook([
            po_row(SUPPLIER_MAIN_LABEL, seeded.main_po, date(2026, 4, 6), seeded.creditor_main,
                   seeded.item_rl, qty, 0, date(2026, 7, 1), seeded.loc_project, cost, ccy),
        ])

    svc.apply(db, _file(100, 12.5, "MYR"), PO)
    # A week later the quantity moved and the money columns came through empty.
    svc.apply(db, _file(120, None, None), PO)

    row = _line(db, seeded.main_po, seeded.item_rl)
    assert (float(row["unit_cost"]), row["currency"]) == (12.5, "MYR"), \
        "an empty cost cell erased a price we already knew"
    assert float(row["qty_ordered"]) == 120.0, "the quantity still updated"


def test_a_file_without_a_po_date_column_does_not_blank_the_issue_date(db, seeded):
    """Lead time is measured from `po.issue_date`, so losing it costs every observation.

    `PO_MINIMAL` is a real shape: the shortest header set the aliases resolve, and it carries
    no PO DATE and no CURRENCY at all. Applying one must leave what an earlier, fuller extract
    established.
    """
    svc.apply(db, po_workbook([
        po_row(SUPPLIER_MAIN_LABEL, seeded.main_po, date(2026, 4, 6), seeded.creditor_main,
               seeded.item_rl, 100, 0, date(2026, 7, 1), seeded.loc_project, 12.5, "MYR"),
    ]), PO)
    assert _header(db, seeded.main_po)["issue_date"] == date(2026, 4, 6)

    svc.apply(db, po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 120,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL), PO)

    header = _header(db, seeded.main_po)
    assert header["issue_date"] == date(2026, 4, 6), \
        "a file with no PO DATE column blanked the order date"
    assert header["currency"] == "MYR"


def test_a_purchase_book_stating_no_currency_is_cny_and_a_stated_one_wins(db, seeded):
    """Captain, 28 Aug 2026: the AutoCount purchase export carries no currency column and
    the book is Chinese, so a purchase document that states no currency is CNY - header and
    lines. A file that DOES state one is believed, and a later file stating none leaves that
    stated value alone (the existing fill rule). The sales book gets no such default."""
    def _file(cost, ccy):
        return po_workbook([
            po_row(SUPPLIER_MAIN_LABEL, seeded.main_po, date(2026, 4, 6), seeded.creditor_main,
                   seeded.item_rl, 100, 0, date(2026, 7, 1), seeded.loc_project, cost, ccy),
        ])

    svc.apply(db, _file(12.5, None), PO)
    assert _header(db, seeded.main_po)["currency"] == "CNY"
    assert _line(db, seeded.main_po, seeded.item_rl)["currency"] == "CNY"

    svc.apply(db, _file(12.5, "MYR"), PO)
    assert _header(db, seeded.main_po)["currency"] == "MYR", "a stated currency wins"
    assert _line(db, seeded.main_po, seeded.item_rl)["currency"] == "MYR"

    svc.apply(db, _file(12.5, None), PO)
    assert _header(db, seeded.main_po)["currency"] == "MYR", "a blank never overwrites"
    assert _line(db, seeded.main_po, seeded.item_rl)["currency"] == "MYR"


def test_the_reader_carries_a_repeated_row_and_no_longer_calls_it_a_problem(db, seeded):
    """Both rows are carried, and neither is complained about (AC-2.1).

    This test used to assert the opposite half - that the second row was REPORTED as "the
    same line stated twice". It was measured wrong: on the client's real 4,349-row export 605
    groups share a document, item and location, 567 of them differ in quantity (one order
    asking for two deliveries) and the other 38 are byte-identical and legitimate. So the
    complaint fired 605 times on a file with nothing wrong with it, on the same list that
    carries the rows which really did fail.

    What it was protecting against - the second copy pairing with nothing and doubling the
    supply - is prevented in `outstanding_diff`, which pairs within the group, so a re-upload
    reads `unchanged`. Pinned in `test_outstanding_duplicate_lines.py`.
    """
    row = po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                         date(2026, 7, 1), seeded.loc_project)
    resolver = AliasResolver.for_doc_type(db, PO)

    read = read_workbook(po_workbook([row, row], headers=PO_MINIMAL), PO, resolver)

    assert read.ok is True
    assert len(read.lines) == 2, "a row was dropped"
    assert read.problems == [], (
        f"a legitimately repeated line was reported as a problem: "
        f"{[p.reason for p in read.problems]}")
