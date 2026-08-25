"""The PURCHASE-ORDER book carries shipping orders too, and they are not purchase orders.

AutoCount exports both families in one file - the captain's own "PO & SPO ..." books hold
`######-S####` purchase orders and `SPO-####/##-####` shipping orders side by side - and this
channel writes `purchase_orders`. A shipping order imported here becomes a purchase order
that nobody raised, counts as on-order supply, and is invisible as a mistake because it looks
exactly like every other imported row.

The family is read from the DOC NUMBER PREFIX, through the one authority that already exists
(`po_listing_reader.doc_family`), and never from AutoCount's own `Shipping Order` checkbox:
nine rows of the captain's 2023 book disagree with their own flag (measured 2026-08-14), so a
family taken from the flag files those nine on the wrong side. See
`tests/scm/test_po_spo_history_split.py`.

The skip is REPORTED, never silent - its own reason so the job breakdown counts it and the
verdict can say how many rows the file spent on the other family - and it applies to the
purchase book ONLY. The sales book has no such family and must not acquire the rule by
accident: an SO that happens to be numbered like a shipping order is still a sales order.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services import import_outcome_codes as oc
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


def test_the_reader_leaves_a_shipping_order_out_of_the_purchase_book(seeded, db):
    """Read, counted, and not turned into a line."""
    codes = seeded
    spo = _spo_number()
    resolver = AliasResolver.for_doc_type(db, PO)

    read = read_workbook(_book(codes, spo), PO, resolver)

    assert [l.doc_number for l in read.lines] == [codes.main_po]
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


def test_the_preview_says_how_many_rows_went_to_the_other_family(seeded, db):
    """The operator uploaded a file half of which this channel will not use. Saying so once,
    in plain language, is the difference between a quiet loss and an informed one."""
    codes = seeded

    result = svc.preview(db, _book(codes, _spo_number()), PO)

    assert result.ok is True
    assert result.shipping_order_rows == 1
    assert any("shipping order" in w.lower() for w in result.warnings), result.warnings


def test_the_job_breakdown_counts_the_shipping_order_rows(seeded, db):
    """Its own code, so the row is accounted for rather than vanishing between the file's
    row count and the lines written."""
    codes = seeded
    outcome = ImportOutcome(None, persist=False)

    svc.apply(db, _book(codes, _spo_number()), PO, outcome=outcome)

    skipped = {e["code"]: e["count"] for e in outcome.breakdown()["skipped"]}
    assert skipped.get(oc.SHIPPING_ORDER) == 1, outcome.breakdown()


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
    assert read.shipping_order_row_numbers == []
