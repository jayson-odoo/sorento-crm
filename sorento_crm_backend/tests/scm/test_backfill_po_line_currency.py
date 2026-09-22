"""AC-PLC-6: `scripts/backfill_po_line_currency_from_header.py` repoints an autocount
purchase-order LINE's currency at its own HEADER's, dry-run first.

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
    """1 autocount PO (MYR) with one mismatched (CNY) and one already-matched (MYR)
    line, 1 autocount PO (CNY) whose line already matches, and 1 non-autocount PO
    (MYR) whose line is a mismatched CNY the script must never touch."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    myr_po = _po(db, currency="MYR")
    mismatched = _line(db, po=myr_po, product_id=prod.id, currency="CNY")
    matched = _line(db, po=myr_po, product_id=prod.id, currency="MYR")

    cny_po = _po(db, currency="CNY")
    cny_line = _line(db, po=cny_po, product_id=prod.id, currency="CNY")

    other_po = _po(db, currency="MYR", source_system="scm_upload")
    other_line = _line(
        db, po=other_po, product_id=prod.id, currency="CNY", source_system="scm_upload"
    )
    return mismatched, matched, cny_line, other_line


def test_dry_run_reports_the_one_mismatch_and_writes_nothing(db):
    mismatched, matched, cny_line, other_line = _seed(db)

    report = backfill.run(db, apply=False)

    assert report["changed"] == 0
    assert sum(n for _h, _l, n in report["before"]) == 1
    assert ("MYR", "CNY", 1) in report["before"]

    db.refresh(mismatched)
    db.refresh(matched)
    db.refresh(cny_line)
    db.refresh(other_line)
    assert mismatched.currency == "CNY", "a dry run wrote a change"
    assert matched.currency == "MYR"
    assert cny_line.currency == "CNY"
    assert other_line.currency == "CNY", "a non-autocount line was reported/touched"


def test_apply_flips_only_the_one_autocount_mismatch(db):
    mismatched, matched, cny_line, other_line = _seed(db)

    report = backfill.run(db, apply=True)

    assert report["changed"] == 1
    assert report["after"] == []

    db.refresh(mismatched)
    db.refresh(matched)
    db.refresh(cny_line)
    db.refresh(other_line)
    assert mismatched.currency == "MYR", "the mismatched autocount line was not flipped"
    assert matched.currency == "MYR"
    assert cny_line.currency == "CNY", "a header already CNY should not have moved its line"
    assert other_line.currency == "CNY", "a non-autocount line was touched"


def test_a_second_apply_is_a_no_op(db):
    _seed(db)
    backfill.run(db, apply=True)

    second = backfill.run(db, apply=True)

    assert second["changed"] == 0
    assert second["before"] == []
