"""P8a: the pure comparison behind AC-N1, AC-N2 and AC-N3.

No database and no clock. Our document and AutoCount's go in, a per-row verdict comes out,
and every decision is an equality test on a quantized number, a date or a string. The
persistence, the match back and the resolution live in ``project_so_ingest_service.py`` and
``project_so_divergence_service.py``.

The golden cases are the shapes a CS editing the document in AutoCount actually produces:
nothing changed at all, a quantity corrected, a price corrected, a delivery pulled forward,
a line deleted, a line typed in, the same product sitting on two dates, and the document
reordered so line numbers no longer line up.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.project_so_divergence_engine import (
    PRESENCE_BOTH,
    PRESENCE_OURS_ONLY,
    PRESENCE_THEIRS_ONLY,
    SCOPE_HEADER,
    SCOPE_LINE,
    OurHeader,
    OurLine,
    TheirHeader,
    TheirLine,
    compare,
)

MAR = date(2026, 3, 10)
APR = date(2026, 4, 10)


def _our(
    line_no: int,
    code: str,
    qty: str,
    price: str,
    delivery: date | None = MAR,
    *,
    line_id: str | None = None,
) -> OurLine:
    return OurLine(
        so_line_id=line_id or f"line-{line_no}",
        line_no=line_no,
        product_code=code,
        description=f"{code} description",
        qty=Decimal(qty),
        unit_price=Decimal(price),
        uom="UNIT",
        delivery_date=delivery,
    )


def _their(
    line_no: int, code: str, qty: str, price: str, delivery: date | None = MAR
) -> TheirLine:
    return TheirLine(
        line_no=line_no,
        product_code=code,
        description=f"{code} description",
        qty=Decimal(qty),
        unit_price=Decimal(price),
        uom="UNIT",
        delivery_date=delivery,
    )


def _our_header(total: str = "1000.00") -> OurHeader:
    return OurHeader(
        customer_code="C-001",
        customer_po_no="PO-778",
        terms="*Net 60 days",
        total_amount=Decimal(total),
    )


def _their_header(
    total: str = "1000.00", terms: str = "*Net 60 days", po_no: str = "PO-778"
) -> TheirHeader:
    return TheirHeader(
        doc_no="SO397450",
        customer_code="C-001",
        customer_po_no=po_no,
        terms=terms,
        total_amount=Decimal(total),
    )


def _lines(report):
    return [row for row in report.rows if row.scope == SCOPE_LINE]


def _header_row(report):
    rows = [row for row in report.rows if row.scope == SCOPE_HEADER]
    assert len(rows) == 1
    return rows[0]


# --------------------------------------------------------------------------- #
# The document nobody touched                                                  #
# --------------------------------------------------------------------------- #


def test_an_identical_document_raises_no_difference():
    ours = [_our(1, "CB6633", "600", "12.50"), _our(2, "AB1200", "40", "300.00")]
    theirs = [_their(1, "CB6633", "600", "12.50"), _their(2, "AB1200", "40", "300.00")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    assert report.differing_count == 0
    assert report.agreeing_count == 3  # two lines and the header
    assert report.has_differences is False
    assert all(row.differing_fields == [] for row in report.rows)


def test_agreeing_lines_are_kept_rather_than_dropped():
    """AC-N3 collapses them on screen. A count nobody wrote down is not a count."""
    ours = [_our(1, "CB6633", "600", "12.50"), _our(2, "AB1200", "40", "300.00")]
    theirs = [_their(1, "CB6633", "601", "12.50"), _their(2, "AB1200", "40", "300.00")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    assert len(_lines(report)) == 2
    agreeing = [row for row in _lines(report) if not row.differing_fields]
    assert [row.product_code for row in agreeing] == ["AB1200"]


# --------------------------------------------------------------------------- #
# Field by field (AC-N1)                                                       #
# --------------------------------------------------------------------------- #


def test_a_corrected_quantity_is_a_difference_on_that_field_alone():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50")],
        _their_header(), [_their(1, "CB6633", "550", "12.50")],
    )

    row = _lines(report)[0]
    assert row.differing_fields == ["qty"]
    assert row.ours["qty"] == "600.0000"
    assert row.theirs["qty"] == "550.0000"
    assert row.presence == PRESENCE_BOTH
    assert report.differing_count == 1


def test_a_corrected_price_and_date_are_both_reported():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50", MAR)],
        _their_header(), [_their(1, "CB6633", "600", "11.00", APR)],
    )

    row = _lines(report)[0]
    assert row.differing_fields == ["unit_price", "delivery_date"]
    assert row.theirs["unit_price"] == "11.00000"
    assert row.theirs["delivery_date"] == "2026-04-10"


def test_a_delivery_date_only_one_side_carries_is_a_difference():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50", None)],
        _their_header(), [_their(1, "CB6633", "600", "12.50", MAR)],
    )

    row = _lines(report)[0]
    assert row.differing_fields == ["delivery_date"]
    assert row.ours["delivery_date"] is None


def test_equal_numbers_written_differently_are_not_a_difference():
    """`600` and `600.0000` are the same commitment. Only the value is compared."""
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.5")],
        _their_header(), [_their(1, "CB6633", "600.0000", "12.50000")],
    )

    assert report.differing_count == 0


def test_a_difference_below_the_stored_scale_is_not_invented():
    """Quantities store 4dp. A fifth decimal place cannot be represented, so it is not
    a difference somebody could act on."""
    report = compare(
        _our_header(), [_our(1, "CB6633", "600.00001", "12.50")],
        _their_header(), [_their(1, "CB6633", "600.00002", "12.50")],
    )

    assert report.differing_count == 0


def test_a_difference_at_the_stored_scale_is_reported():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600.0001", "12.50")],
        _their_header(), [_their(1, "CB6633", "600.0002", "12.50")],
    )

    assert _lines(report)[0].differing_fields == ["qty"]


# --------------------------------------------------------------------------- #
# Pairing                                                                      #
# --------------------------------------------------------------------------- #


def test_lines_pair_on_product_and_date_not_on_line_number():
    """AutoCount renumbers. Pairing by position would report every line as changed."""
    ours = [_our(1, "CB6633", "600", "12.50"), _our(2, "AB1200", "40", "300.00")]
    theirs = [_their(1, "AB1200", "40", "300.00"), _their(2, "CB6633", "600", "12.50")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    assert report.differing_count == 0
    assert {row.product_code for row in _lines(report)} == {"CB6633", "AB1200"}


def test_the_same_product_on_two_dates_stays_two_rows():
    ours = [_our(1, "CB6633", "600", "12.50", MAR), _our(2, "CB6633", "400", "12.50", APR)]
    theirs = [_their(1, "CB6633", "600", "12.50", MAR), _their(2, "CB6633", "350", "12.50", APR)]

    report = compare(_our_header(), ours, _their_header(), theirs)

    rows = sorted(_lines(report), key=lambda r: r.ours["delivery_date"])
    assert len(rows) == 2
    assert rows[0].differing_fields == []
    assert rows[1].differing_fields == ["qty"]
    assert rows[1].theirs["qty"] == "350.0000"


def test_a_moved_date_pairs_on_the_product_rather_than_reading_as_two_changes():
    """One line whose date moved, not a deletion plus an insertion."""
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50", MAR)],
        _their_header(), [_their(1, "CB6633", "600", "12.50", APR)],
    )

    rows = _lines(report)
    assert len(rows) == 1
    assert rows[0].presence == PRESENCE_BOTH
    assert rows[0].differing_fields == ["delivery_date"]


def test_two_of_the_same_product_and_date_pair_in_order_of_appearance():
    ours = [_our(1, "CB6633", "600", "12.50"), _our(2, "CB6633", "400", "12.50")]
    theirs = [_their(1, "CB6633", "600", "12.50"), _their(2, "CB6633", "450", "12.50")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    rows = sorted(_lines(report), key=lambda r: r.line_no or 0)
    assert [row.differing_fields for row in rows] == [[], ["qty"]]


# --------------------------------------------------------------------------- #
# Presence (a line only one side has)                                          #
# --------------------------------------------------------------------------- #


def test_a_line_autocount_dropped_is_ours_only():
    ours = [_our(1, "CB6633", "600", "12.50"), _our(2, "AB1200", "40", "300.00")]
    theirs = [_their(1, "CB6633", "600", "12.50")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    missing = [row for row in _lines(report) if row.presence == PRESENCE_OURS_ONLY]
    assert [row.product_code for row in missing] == ["AB1200"]
    assert missing[0].theirs == {}
    assert missing[0].so_line_id == "line-2"
    assert report.differing_count == 1


def test_a_line_somebody_typed_into_autocount_is_theirs_only():
    ours = [_our(1, "CB6633", "600", "12.50")]
    theirs = [_their(1, "CB6633", "600", "12.50"), _their(2, "ZZ9999", "5", "88.00")]

    report = compare(_our_header(), ours, _their_header(), theirs)

    extra = [row for row in _lines(report) if row.presence == PRESENCE_THEIRS_ONLY]
    assert [row.product_code for row in extra] == ["ZZ9999"]
    assert extra[0].ours == {}
    assert extra[0].so_line_id is None


def test_a_product_swapped_for_another_reads_as_a_removal_and_an_addition():
    """A model change is not a field edit: there is no honest way to say which of our
    lines a different product code corresponds to, so the reviewer is shown both."""
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50")],
        _their_header(), [_their(1, "CB6634", "600", "12.50")],
    )

    presences = {row.presence for row in _lines(report)}
    assert presences == {PRESENCE_OURS_ONLY, PRESENCE_THEIRS_ONLY}


# --------------------------------------------------------------------------- #
# Header (AC-N1 "plus header terms")                                           #
# --------------------------------------------------------------------------- #


def test_header_terms_and_total_are_compared():
    report = compare(
        _our_header(total="1000.00"), [_our(1, "CB6633", "600", "12.50")],
        _their_header(total="990.00", terms="*Net 30 days"), [_their(1, "CB6633", "600", "12.50")],
    )

    row = _header_row(report)
    assert row.differing_fields == ["terms", "total_amount"]
    assert row.ours["terms"] == "*Net 60 days"
    assert row.theirs["total_amount"] == "990.00"


def test_a_changed_customer_po_number_is_a_header_difference():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50")],
        _their_header(po_no="PO-779"), [_their(1, "CB6633", "600", "12.50")],
    )

    assert _header_row(report).differing_fields == ["customer_po_no"]


def test_the_header_row_carries_the_document_number_it_was_read_from():
    report = compare(
        _our_header(), [_our(1, "CB6633", "600", "12.50")],
        _their_header(), [_their(1, "CB6633", "600", "12.50")],
    )

    assert _header_row(report).theirs["doc_no"] == "SO397450"


# --------------------------------------------------------------------------- #
# Counting                                                                     #
# --------------------------------------------------------------------------- #


def test_the_counts_add_up_to_the_rows_compared():
    ours = [
        _our(1, "CB6633", "600", "12.50"),
        _our(2, "AB1200", "40", "300.00"),
        _our(3, "DD3000", "10", "50.00"),
    ]
    theirs = [
        _their(1, "CB6633", "550", "12.50"),
        _their(2, "AB1200", "40", "300.00"),
        _their(4, "ZZ9999", "5", "88.00"),
    ]

    report = compare(_our_header(), ours, _their_header(total="900.00"), theirs)

    assert report.compared_count == len(report.rows)
    assert report.agreeing_count + report.differing_count == report.compared_count
    # qty change, DD3000 dropped, ZZ9999 added, header total
    assert report.differing_count == 4
    assert report.has_differences is True


def test_a_fingerprint_of_the_same_lines_is_stable_whatever_the_order():
    """The match back's tie breaker (AC-F11a). Order of appearance must not change it."""
    from app.services.project_so_divergence_engine import line_fingerprint

    a = line_fingerprint([("CB6633", Decimal("600"), MAR), ("AB1200", Decimal("40"), APR)])
    b = line_fingerprint([("AB1200", Decimal("40.0000"), APR), ("CB6633", Decimal("600.00"), MAR)])
    c = line_fingerprint([("CB6633", Decimal("601"), MAR), ("AB1200", Decimal("40"), APR)])

    assert a == b
    assert a != c
