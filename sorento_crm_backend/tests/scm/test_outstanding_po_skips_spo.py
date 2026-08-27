"""The PURCHASE-ORDER book carries shipping orders too, and now it FILES them (R4).

AutoCount exports both families in one file - the captain's own "PO & SPO ..." books hold
`######-S####` purchase orders and `SPO-####/##-####` shipping orders side by side. This
channel writes `purchase_orders`, so an SPO row must never become a purchase order nobody
raised; that half of the rule is unchanged and is still pinned here.

What REVERSED (`PLAN-scm-oi-draft-links.md` R4, captain 27 Aug 2026) is what happens to the
row instead of nothing. It used to be counted and dropped, which left the Order Inquiries
page unable to link to a shipping order at all: the history book writes SPO rows CLOSED, so
they are never candidates, and nothing else in the system could create an OPEN one. The rows
are now upserted into `spo_allocations` as OPEN lines, on `(company, spo number, line
number)`, which is the same key the history channel writes on - so the two feeds share the
table and are told apart by `source_system`, exactly as the two purchase-order feeds are.

The family is read from the DOC NUMBER PREFIX, through the one authority that already exists
(`po_listing_reader.doc_family`), and never from AutoCount's own `Shipping Order` checkbox:
nine rows of the captain's 2023 book disagree with their own flag (measured 2026-08-14), so a
family taken from the flag files those nine on the wrong side. See
`tests/scm/test_po_spo_history_split.py`.

It applies to the purchase book ONLY. The sales book has no such family and must not acquire
the rule by accident: an SO that happens to be numbered like a shipping order is still a
sales order.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services.import_alias_service import AliasResolver
from app.services.import_outcome import ImportOutcome
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO, read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    PO_MINIMAL,
    Codes,
    make_codes,
    po_minimal_row,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
    workbook,
)

SO_MINIMAL = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE",
              "STOCK LOCATION")


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


def _spo_number() -> str:
    """A shipping order numbered the way every one of them is written."""
    return f"SPO-2026/01-{uuid.uuid4().hex[:6].upper()}"


def _book(codes: Codes, spo_number: str) -> bytes:
    """One purchase order and one shipping order, exactly as the export writes them."""
    return po_workbook([
        po_minimal_row(codes.main_po, codes.creditor_main, codes.item_rl, 100,
                       date(2026, 7, 1), codes.loc_project),
        po_minimal_row(spo_number, codes.creditor_main, codes.item_wt, 60,
                       date(2026, 8, 1), codes.loc_project),
    ], headers=PO_MINIMAL)


def _po_only_book(codes: Codes) -> bytes:
    """A purchase-order-only export: no shipping order anywhere in it."""
    return po_workbook([
        po_minimal_row(codes.main_po, codes.creditor_main, codes.item_rl, 100,
                       date(2026, 7, 1), codes.loc_project),
    ], headers=PO_MINIMAL)


def _later_book(codes: Codes, other_spo: str) -> bytes:
    """The same book re-exported a week later: the first shipping order has landed and a
    second one is still on the water."""
    return po_workbook([
        po_minimal_row(codes.main_po, codes.creditor_main, codes.item_rl, 100,
                       date(2026, 7, 1), codes.loc_project),
        po_minimal_row(other_spo, codes.creditor_main, codes.item_wt, 40,
                       date(2026, 9, 1), codes.loc_project),
    ], headers=PO_MINIMAL)


def _allocations(db, spo_number: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT a.spo_line_number, a.allocated_quantity, a.quantity_received, "
            "a.line_status, a.source_system, a.expected_date, a.location_code, "
            "w.warehouse_code "
            "FROM spo_allocations a "
            "LEFT JOIN warehouses w ON w.id = a.warehouse_id "
            "WHERE a.spo_number = :n ORDER BY a.spo_line_number"
        ),
        {"n": spo_number},
    ).mappings().all()
    return [dict(row) for row in rows]


# ----------------------------------------------------------------- the reader


def test_the_reader_keeps_a_shipping_order_apart_from_the_purchase_book(seeded, db):
    """Read, counted, and held in its own list: the purchase-order diff must never see it,
    because that diff writes `purchase_orders`."""
    codes = seeded
    spo = _spo_number()
    resolver = AliasResolver.for_doc_type(db, PO)

    read = read_workbook(_book(codes, spo), PO, resolver)

    assert [l.doc_number for l in read.lines] == [codes.main_po]
    assert [l.doc_number for l in read.spo_lines] == [spo]
    assert read.shipping_order_row_numbers == [3]
    assert read.total_rows == 2, "the row is still counted as read"


def test_no_purchase_order_is_created_for_a_shipping_order(seeded, db):
    codes = seeded
    spo = _spo_number()

    out = svc.apply(db, _book(codes, spo), PO)

    assert out["scope_documents"] == [codes.main_po]
    assert db.execute(text("SELECT count(*) FROM purchase_orders WHERE po_number = :n"),
                      {"n": spo}).scalar() == 0
    assert out["applied"]["added"] == 1


# ------------------------------------------------------------------ the write


def test_a_shipping_order_row_becomes_an_open_allocation(seeded, db):
    """R4. The whole reason the rule changed: nothing else in the system could create an
    OPEN shipping-order line, so the Order Inquiries page had nothing to link to."""
    codes = seeded
    spo = _spo_number()

    out = svc.apply(db, _book(codes, spo), PO)

    lines = _allocations(db, spo)
    assert len(lines) == 1
    line = lines[0]
    assert line["spo_line_number"] == 1
    assert float(line["allocated_quantity"]) == 60
    assert float(line["quantity_received"]) == 0
    assert line["line_status"] == "open"
    assert line["source_system"] == "scm_upload"
    assert line["expected_date"] == date(2026, 8, 1)
    assert line["warehouse_code"] == codes.loc_project
    assert line["location_code"] == codes.loc_project
    assert out["spo_documents"] == 1
    assert out["spo_lines"] == 1


def test_a_re_upload_restates_the_same_line_rather_than_doubling_it(seeded, db):
    """Upserted on `(company, spo number, line number)`, the key the history channel
    already writes on: a book re-exported over a wider range must refresh what it holds."""
    codes = seeded
    spo = _spo_number()

    svc.apply(db, _book(codes, spo), PO)
    svc.apply(db, _book(codes, spo), PO)

    assert len(_allocations(db, spo)) == 1


def test_a_second_book_that_no_longer_states_the_shipping_order_closes_it(seeded, db):
    """The book is the statement of what is still open. A line it stops stating is settled,
    and an open line nobody is expecting is supply the plan counts and never receives."""
    codes = seeded
    spo, other = _spo_number(), _spo_number()
    svc.apply(db, _book(codes, spo), PO)
    assert _allocations(db, spo)[0]["line_status"] == "open"

    out = svc.apply(db, _later_book(codes, other), PO)

    assert _allocations(db, spo)[0]["line_status"] == "closed"
    assert _allocations(db, other)[0]["line_status"] == "open"
    # `>= 1`, not `== 1`: this suite runs on the shared prod-copy database, which carries
    # open lines of this same channel that the fixture's book does not state either.
    assert out["spo_closed"] >= 1


def test_a_purchase_order_only_export_settles_no_shipping_order(seeded, db):
    """A file with no shipping order in it is not evidence about the shipping-order book.

    Read as one, a PO-only export would settle every open SPO line in the company - 715 on
    the dev copy - on an upload that never mentioned a single one. Silence is not a
    statement; a book that states SOME shipping orders is the SPO book, and only then does
    what it leaves out mean "landed".
    """
    codes = seeded
    spo = _spo_number()
    svc.apply(db, _book(codes, spo), PO)

    out = svc.apply(db, _po_only_book(codes), PO)

    assert _allocations(db, spo)[0]["line_status"] == "open"
    assert out["spo_closed"] == 0


def test_a_history_allocation_is_never_touched(seeded, db):
    """The two feeds share the table and are told apart by the stamp, exactly as the two
    purchase-order feeds are. Closing a history row would be harmless; REOPENING one would
    make a 2020 delivery read as stock on its way in, for ever."""
    codes = seeded
    spo = _spo_number()
    product_id = db.execute(
        text("SELECT id FROM products WHERE product_code = :c"), {"c": codes.item_wt}
    ).scalar()
    db.execute(
        text(
            "INSERT INTO spo_allocations (id, spo_number, spo_line_number, product_id, "
            "allocated_quantity, quantity_received, receipt_status, line_status, "
            "source_system) VALUES (:i, :n, 9, :p, 5, 5, 'fully_received', 'closed', "
            "'scm_spo_history')"
        ),
        {"i": str(uuid.uuid4()), "n": spo, "p": product_id},
    )
    db.flush()

    svc.apply(db, _book(codes, spo), PO)

    history = [l for l in _allocations(db, spo) if l["spo_line_number"] == 9][0]
    assert history["line_status"] == "closed"
    assert history["source_system"] == "scm_spo_history"
    assert float(history["quantity_received"]) == 5


def test_a_location_the_master_does_not_hold_keeps_the_line_and_is_reported(seeded, db):
    """The code as the book printed it is the only record of where the goods were meant to
    go. Dropping the line would lose the quantity as well, which is the fact that matters."""
    codes = seeded
    spo = _spo_number()
    book = po_workbook([
        po_minimal_row(spo, codes.creditor_main, codes.item_wt, 60,
                       date(2026, 8, 1), "ZZT-NOWHERE"),
    ], headers=PO_MINIMAL)

    out = svc.apply(db, book, PO)

    line = _allocations(db, spo)[0]
    assert line["warehouse_code"] is None
    assert line["location_code"] == "ZZT-NOWHERE"
    assert line["line_status"] == "open"
    assert out["spo_unknown_locations"] == 1


def test_the_preview_says_what_the_shipping_order_rows_will_do(seeded, db):
    """The operator reads the Test result before pressing Confirm upload, and "N rows are
    shipping orders, which this book does not carry" is no longer true of them."""
    codes = seeded

    result = svc.preview(db, _book(codes, _spo_number()), PO)

    assert result.ok is True
    assert result.shipping_order_rows == 1
    assert result.spo_documents == 1
    assert result.spo_lines == 1
    assert any("shipping order" in w.lower() for w in result.warnings), result.warnings


def test_the_job_breakdown_counts_the_shipping_order_rows_as_written(seeded, db):
    """The row is accounted for, and now as a line that landed rather than one left out."""
    codes = seeded
    outcome = ImportOutcome(None, persist=False)

    svc.apply(db, _book(codes, _spo_number()), PO, outcome=outcome)

    breakdown = outcome.breakdown()
    skipped = {e["code"]: e["count"] for e in breakdown["skipped"]}
    assert "shipping_order" not in skipped, breakdown
    assert breakdown["successful"], breakdown


def test_link_now_reaches_the_products_the_shipping_orders_named(seeded, db):
    """The page's next step after an upload is Link now, narrowed to what the book wrote.
    A product only an SPO row named must be in that list or its rows stay unlinked."""
    codes = seeded
    spo = _spo_number()

    out = svc.apply(db, _book(codes, spo), PO)

    wt_id = str(db.execute(
        text("SELECT id FROM products WHERE product_code = :c"), {"c": codes.item_wt}
    ).scalar())
    assert wt_id in out["product_ids"]


def test_the_sales_book_never_applies_the_rule(db):
    """A sales order is a sales order whatever it is numbered. The purchase book's family
    split must not leak onto a channel that has no families."""
    codes = make_codes()
    seed_catalogue(db, codes)
    so_number = f"SPO-{uuid.uuid4().hex[:8].upper()}"
    resolver = AliasResolver.for_doc_type(db, SO)

    read = read_workbook(workbook([
        (so_number, "300-T012", codes.item_rl, 10, date(2026, 7, 1), codes.loc_project),
    ], headers=SO_MINIMAL), SO, resolver)

    assert [l.doc_number for l in read.lines] == [so_number]
    assert read.spo_lines == []
    assert read.shipping_order_row_numbers == []


# ------------------------------------------- review round: identity, not file position


def _multi_line_book(codes: Codes, spo_number: str, items) -> bytes:
    """One shipping order stating several products, in the order the export wrote them."""
    return po_workbook(
        [
            po_minimal_row(spo_number, codes.creditor_main, item, qty,
                           date(2026, 8, 1), codes.loc_project)
            for item, qty in items
        ],
        headers=PO_MINIMAL,
    )


def _rows_by_product(db, spo_number: str) -> dict[str, dict]:
    rows = db.execute(
        text(
            "SELECT a.id, a.spo_line_number, a.line_status, p.product_code "
            "FROM spo_allocations a JOIN products p ON p.id = a.product_id "
            "WHERE a.spo_number = :n"
        ),
        {"n": spo_number},
    ).mappings().all()
    return {row["product_code"]: dict(row) for row in rows}


def test_a_re_export_that_drops_a_line_does_not_re_key_the_rest(seeded, db):
    """The line's identity was its POSITION IN THE FILE, so a re-export that no longer
    states a fully received line moved every line below it up one - and each of those rows
    kept its id while gaining a different product. Anything pointing at that row (an order
    inquiry link, its audit claim, a container tick) then described goods nobody ordered.

    Identity is `(shipping order, item, location, which occurrence of the three)` mapped
    onto a line number the row KEEPS.
    """
    codes = seeded
    spo = _spo_number()
    svc.apply(db, _multi_line_book(codes, spo, [
        (codes.item_rl, 100), (codes.item_wt, 60), (codes.item_blue, 40),
    ]), PO)
    before = _rows_by_product(db, spo)
    assert len(before) == 3

    svc.apply(db, _multi_line_book(codes, spo, [
        (codes.item_wt, 60), (codes.item_blue, 40),
    ]), PO)

    after = _rows_by_product(db, spo)
    assert after[codes.item_wt]["id"] == before[codes.item_wt]["id"]
    assert after[codes.item_blue]["id"] == before[codes.item_blue]["id"]
    assert after[codes.item_wt]["line_status"] == "open"
    assert after[codes.item_blue]["line_status"] == "open"
    assert after[codes.item_rl]["id"] == before[codes.item_rl]["id"]
    assert after[codes.item_rl]["line_status"] == "closed", (
        "the line the book stopped stating is the one that landed"
    )


def test_the_same_product_twice_on_one_document_keeps_both_rows(seeded, db):
    """The book states the same item twice on one shipping order and each is a real second
    container, so the identity counts the OCCURRENCE: two rows in, two rows back."""
    codes = seeded
    spo = _spo_number()

    svc.apply(db, _multi_line_book(codes, spo, [
        (codes.item_wt, 60), (codes.item_wt, 25),
    ]), PO)
    first = sorted(l["spo_line_number"] for l in _allocations(db, spo))

    svc.apply(db, _multi_line_book(codes, spo, [
        (codes.item_wt, 60), (codes.item_wt, 25),
    ]), PO)

    lines = _allocations(db, spo)
    assert len(lines) == 2, "a re-upload doubled the document"
    assert sorted(l["spo_line_number"] for l in lines) == first
    assert sorted(float(l["allocated_quantity"]) for l in lines) == [25.0, 60.0]


def test_the_preview_and_the_write_close_the_same_rows(seeded, db):
    """S3. `stated` was counted AFTER the product lookup on the write and BEFORE it on the
    preview, so a book carrying one SKU the master does not hold made the two disagree
    about which lines the book still states - and the operator confirmed one number while
    a different set of rows was settled."""
    codes = seeded
    spo, other = _spo_number(), _spo_number()
    svc.apply(db, _multi_line_book(codes, spo, [(codes.item_wt, 60)]), PO)
    book = _multi_line_book(codes, other, [("ZZTOS-NO-SUCH-ITEM", 5), (codes.item_rl, 10)])

    result = svc.preview(db, book, PO)
    out = svc.apply(db, book, PO)

    assert result.spo_closed == out["spo_closed"]
    assert result.spo_documents == out["spo_documents"]
    assert result.spo_lines == out["spo_lines"]


def test_a_fractional_quantity_lands_as_a_whole_number(seeded, db):
    """S8. `allocated_quantity` and `quantity_received` are INTEGER columns and the book's
    figures are floats, so `ordered = qty + received` handed Postgres 10.400000000000002 to
    round on its own while the line's own status was decided on the UNROUNDED remainder -
    a row reading 10 ordered, 10 received and still `open`, which `scm.on_order_v` counts
    as supply that is never coming. Both figures are rounded here, off the file's own
    stated order quantity when it has one, and the status follows the two integers.
    """
    codes = seeded
    spo = _spo_number()
    headers = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "QTY RECEIVED",
               "ETA", "STOCK LOCATION")
    book = po_workbook(
        [(spo, codes.creditor_main, codes.item_wt, 10.4, 10.0, date(2026, 8, 1),
          codes.loc_project)],
        headers=headers,
    )

    svc.apply(db, book, PO)

    line = _allocations(db, spo)[0]
    assert float(line["allocated_quantity"]) == 10
    assert float(line["quantity_received"]) == 10
    assert line["line_status"] == "closed"
