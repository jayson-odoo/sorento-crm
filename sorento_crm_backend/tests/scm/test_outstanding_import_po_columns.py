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


def test_the_reader_names_the_row_a_duplicate_collides_with_and_drops_neither(db, seeded):
    """The report has to be actionable: "row 3 repeats row 2" is a cell someone can go and fix.

    Both rows are still carried. Silently dropping the second would leave the file and the
    import disagreeing about how many lines were read, which is the same class of problem as
    the duplicate itself.
    """
    row = po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                         date(2026, 7, 1), seeded.loc_project)
    resolver = AliasResolver.for_doc_type(db, PO)

    read = read_workbook(po_workbook([row, row], headers=PO_MINIMAL), PO, resolver)

    assert read.ok is True, "a duplicated row does not make the file unreadable"
    assert len(read.lines) == 2, "a row was dropped rather than reported"
    assert [p.row_number for p in read.problems] == [3]
    reason = read.problems[0].reason
    assert "row 2" in reason, f"the report does not say which row it repeats: {reason}"
    assert seeded.main_po in reason and seeded.item_rl in reason
