"""AC-PLC-6: `scripts/backfill_po_line_currency_from_header.py` repoints a
purchase-order LINE's currency at its own HEADER's, dry-run first - any line,
whatever feed wrote it (fix round 1: the first cut of this script and this test both
scoped the sweep to `source_system = 'autocount'`; the review measured 636 real
`scm_po_history` rows the filter left mis-stamped, so it was dropped from both).

`PLAN-po-line-currency-follows-header-22sep.md`,
`po-line-currency-follows-header-22sep-acceptance-criteria.md`.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session, unique_code

import scripts.backfill_po_line_currency_from_header as backfill


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _po(db, *, currency, source_system="autocount"):
    row = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=unique_code("PO")[:50],
        status="active",
        currency=currency,
        source_system=source_system,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _line(db, *, po, product_id, currency, source_system="autocount"):
    row = PurchaseOrderLine(
        id=str(uuid.uuid4()),
        purchase_order_id=po.id,
        product_id=product_id,
        qty_ordered=1,
        qty_received=0,
        currency=currency,
        source_system=source_system,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _seed(db):
    """1 autocount PO (MYR) with one mismatched (CNY, flips) and one already-matched
    (MYR, stays - header == line) line; 1 PO with NO header currency at all and a CNY
    line (stays - nothing to fall back to); 1 non-autocount (`scm_po_history`) PO
    (MYR) whose line is a mismatched CNY - fix round 1: this used to be excluded by a
    `source_system = 'autocount'` filter, and now flips too, since the mismatch is the
    same bug whatever feed wrote it."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    myr_po = _po(db, currency="MYR")
    mismatched = _line(db, po=myr_po, product_id=prod.id, currency="CNY")
    matched = _line(db, po=myr_po, product_id=prod.id, currency="MYR")

    no_header_currency_po = _po(db, currency=None)
    untouched_no_header_currency = _line(
        db, po=no_header_currency_po, product_id=prod.id, currency="CNY"
    )

    other_po = _po(db, currency="MYR", source_system="scm_po_history")
    other_line = _line(
        db, po=other_po, product_id=prod.id, currency="CNY", source_system="scm_po_history"
    )
    return mismatched, matched, untouched_no_header_currency, other_line


def test_dry_run_reports_both_mismatches_and_writes_nothing(db):
    mismatched, matched, untouched_no_header_currency, other_line = _seed(db)

    report = backfill.run(db, apply=False)

    assert report["changed"] == 0
    assert sum(n for _h, _l, n in report["before"]) == 2
    assert ("MYR", "CNY", 2) in report["before"]

    db.refresh(mismatched)
    db.refresh(matched)
    db.refresh(untouched_no_header_currency)
    db.refresh(other_line)
    assert mismatched.currency == "CNY", "a dry run wrote a change"
    assert matched.currency == "MYR"
    assert untouched_no_header_currency.currency == "CNY"
    assert other_line.currency == "CNY", "a dry run wrote a change"


def test_apply_flips_every_mismatch_whatever_the_feed(db):
    mismatched, matched, untouched_no_header_currency, other_line = _seed(db)

    report = backfill.run(db, apply=True)

    assert report["changed"] == 2
    assert report["after"] == []

    db.refresh(mismatched)
    db.refresh(matched)
    db.refresh(untouched_no_header_currency)
    db.refresh(other_line)
    assert mismatched.currency == "MYR", "the autocount mismatch was not flipped"
    assert matched.currency == "MYR"
    assert untouched_no_header_currency.currency == "CNY", \
        "a header with no currency of its own must never fill a line"
    assert other_line.currency == "MYR", \
        "a non-autocount line with the same mismatch was left behind"


def test_a_second_apply_is_a_no_op(db):
    _seed(db)
    backfill.run(db, apply=True)

    second = backfill.run(db, apply=True)

    assert second["changed"] == 0
    assert second["before"] == []
