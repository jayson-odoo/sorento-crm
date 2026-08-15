"""`apply` must refuse a book it can read but cannot write, and write the ones it can.

The defect this pins: `apply` branched on `doc_type` only to pick a READER, then went on to
construct `SalesOrder(so_number=...)` / `SalesOrderLine(...)` unconditionally. So uploading
the purchase order book created SALES orders whose `so_number` was the PO number, and the
lines landed in `sales_order_lines`. Nothing failed, nothing warned; the PO book simply
turned into fictional customer demand that the reorder plan then bought against. A doc_type
check at the reader was no protection at all, because the reader was already the only part
that was doc_type aware.

The PO write path now exists, so `outstanding_po` is writable and the corruption assertion
moved to what it should have been all along: applying the PO book writes PURCHASE orders and
leaves `sales_orders` alone (`test_applying_the_purchase_order_book_writes_purchase_orders`).

The GATE stays, and is tested as a mechanism rather than through whichever type happens to be
unimplemented today: the writability tests below close it by patching
`_WRITABLE_DOC_TYPES`, which is exactly the situation the next readable-but-unwritable book
will be in. Testing the gate only via "PO is not implemented" would have deleted the whole
guard the day PO landed, which is the day it stops being obvious.

Postgres, inside the suite's rolled-back savepoint (`scm_app`), with a principal and a
company of this test's own making (`as_company_user`). The upload is the shared generated
PO book (`_outstanding_workbooks.po_week1`) over codes the test owns, never a committed
file naming real documents.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.scm import outstanding_import as route_mod
from app.services.scm.outstanding_reader import SO
from tests.scm._outstanding_workbooks import (
    make_codes,
    po_week1,
    seed_catalogue,
    seed_suppliers,
    week1,
)
from tests.scm._queued_import import run_enqueued, stub_queue
from tests.scm.conftest import requires_pg
# Imported rather than copied. `as_company_user` creates the principal AND the company the
# seeded rows are stamped with; a second copy is exactly how the two drifted apart before
# (see that module's docstring: a borrowed company meant the importer resolved nothing).
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PO_APPLY = "/api/v1/scm/outstanding/purchase-orders/apply"
PO_PREVIEW = "/api/v1/scm/outstanding/purchase-orders/preview"
SO_APPLY = "/api/v1/scm/outstanding/sales-orders/apply"


def _upload(data: bytes, name: str = "outstanding_po.xlsx"):
    return {"file": (name, data, _XLSX)}


@pytest.fixture()
def po_book(scm_app):
    """(client, db, codes) with everything the PO book names already seeded."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes, "outstanding_po")
    seed_suppliers(db, codes)
    return TestClient(app), db, codes


@pytest.fixture()
def gate_closed(monkeypatch):
    """The purchase-order book made unwritable, standing in for the next such book.

    Patched rather than pinned to a type that is genuinely unimplemented, because there is no
    longer one: both books write. The gate still has to work for the next one.
    """
    monkeypatch.setattr(route_mod, "_WRITABLE_DOC_TYPES", {SO})


def _sales_orders_named(db, *numbers: str) -> int:
    """Sales orders carrying a PO number. Must always be zero: this is the corruption."""
    return db.execute(
        text("SELECT count(*) FROM sales_orders WHERE so_number = ANY(:n)"),
        {"n": list(numbers)},
    ).scalar()


def _purchase_orders_named(db, *numbers: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM purchase_orders WHERE po_number = ANY(:n)"),
        {"n": list(numbers)},
    ).scalar()


# =========================================================================== #
# The corruption that started this file
# =========================================================================== #
def test_applying_the_purchase_order_book_writes_purchase_orders(po_book, monkeypatch):
    """Both tables asserted, not just the purchase-order one: the damage was a SALES order
    carrying the PO number, so a count of only `purchase_orders` would have stayed green.

    The write happens on the queued job now, so the job is run here. That is not incidental
    to this test: the corruption it pins would be committed by the worker, and a route test
    that stopped at the 202 would never see either table.
    """
    client, db, codes = po_book
    so_before = db.execute(text("SELECT count(*) FROM sales_orders")).scalar()
    sol_before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    captured = stub_queue(monkeypatch)

    r = client.post(PO_APPLY, files=_upload(po_week1(codes)))

    assert r.status_code == 202, r.text
    run_enqueued(captured, db, monkeypatch)

    assert _purchase_orders_named(db, *codes.po_documents) == 2
    assert _sales_orders_named(db, *codes.po_documents) == 0, \
        "a PO number reached sales_orders - this is the cross-table corruption"
    assert db.execute(text("SELECT count(*) FROM sales_orders")).scalar() == so_before
    assert db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar() == sol_before


# =========================================================================== #
# The gate, exercised with a book made unwritable
# =========================================================================== #
def test_an_unwritable_book_is_refused(po_book, gate_closed):
    client, _db, codes = po_book

    r = client.post(PO_APPLY, files=_upload(po_week1(codes)))

    assert r.status_code == 501, r.text


def test_the_refusal_says_which_book_and_what_to_do_instead(po_book, gate_closed):
    """An operator reading this must not go hunting for a fault in their export.

    501 rather than 400 for the same reason: this route's other 400s all mean "your file is
    wrong", and the file here may be perfectly good.
    """
    client, _db, codes = po_book

    r = client.post(PO_APPLY, files=_upload(po_week1(codes)))
    detail = r.json()["detail"]

    assert "purchase orders" in detail
    assert "not implemented" in detail
    # And it points at the two things that DO work: previewing this book, and applying the
    # other one.
    assert "Preview" in detail
    assert "sales orders" in detail


def test_the_refusal_writes_nothing(po_book, gate_closed):
    client, db, codes = po_book
    so_before = db.execute(text("SELECT count(*) FROM sales_orders")).scalar()
    po_before = db.execute(text("SELECT count(*) FROM purchase_orders")).scalar()

    r = client.post(PO_APPLY, files=_upload(po_week1(codes)))

    # The side effects are asserted BEFORE the status code on purpose. If the gate is ever
    # removed, the failure this file should print is the write, not "expected 501".
    assert _sales_orders_named(db, *codes.po_documents) == 0
    assert _purchase_orders_named(db, *codes.po_documents) == 0
    assert db.execute(text("SELECT count(*) FROM sales_orders")).scalar() == so_before
    assert db.execute(text("SELECT count(*) FROM purchase_orders")).scalar() == po_before
    assert r.status_code == 501, r.text


def test_the_refusal_happens_before_the_file_is_read(po_book, gate_closed):
    """Order of checks, pinned: an unwritable type is refused without buffering the upload.

    Not a micro-optimisation - it is the same principle as the RBAC test ("the denial must
    happen before the file is read"), and it keeps the answer to "can I apply this book"
    independent of whatever the operator happened to attach. A 400 here would mean the
    file was read first.
    """
    client, _db, _codes = po_book

    r = client.post(PO_APPLY, files={"file": ("notes.txt", b"not a workbook", "text/plain")})

    assert r.status_code == 501, r.text


# =========================================================================== #
# What the gate must NOT break
# =========================================================================== #
def test_previewing_the_purchase_order_book_still_works(po_book, gate_closed):
    """Preview reads and writes nothing, so it stays available even for a book that cannot be
    applied: the file is checkable long before it is applyable."""
    client, db, codes = po_book
    sol_before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()

    r = client.post(PO_PREVIEW, files=_upload(po_week1(codes)))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    assert body["doc_type"] == "outstanding_po"
    assert body["missing_columns"] == []
    assert body["total_rows"] == 5
    assert sorted(body["scope_documents"]) == sorted(codes.po_documents)
    assert body["counts"]["added"] == 5
    assert db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar() == sol_before


def test_the_preview_nets_off_what_has_already_been_received(po_book):
    """135, not 150. A straight-through read of QTY ORDERED would over-buy by the receipt,
    and the preview is the number the operator signs off on.

    Collected as a LIST per (document, item): that pair is not unique in the file, because the
    main PO carries two containers of the same SKU at two dates. Keyed by the pair alone the
    second row silently overwrites the first, and the assertion then reads whichever one came
    last - which is how this test first passed while asserting nothing.
    """
    client, _db, codes = po_book

    r = client.post(PO_PREVIEW, files=_upload(po_week1(codes)))

    quantities: dict[tuple[str, str], list[float]] = {}
    for rows in r.json()["samples"].values():
        for row in rows:
            quantities.setdefault((row["doc_number"], row["item_code"]), []).append(
                row["qty_after"])

    assert sorted(quantities[(codes.main_po, codes.item_rl)]) == [72, 135]


def test_applying_the_sales_order_book_is_unaffected(po_book, gate_closed, monkeypatch):
    """The control. Without it, a broken fixture would make the refusal look correct."""
    client, db, codes = po_book
    captured = stub_queue(monkeypatch)

    r = client.post(SO_APPLY, files=_upload(week1(codes), "outstanding_so.xlsx"))

    assert r.status_code == 202, r.text
    run_enqueued(captured, db, monkeypatch)

    assert db.execute(
        text("SELECT count(*) FROM sales_orders WHERE so_number = :so"),
        {"so": codes.project_so},
    ).scalar() == 1


def test_an_unknown_book_is_still_a_404_on_apply(po_book, gate_closed):
    """404 before 501: an unknown `kind` is a wrong URL, not an unimplemented feature."""
    client, _db, codes = po_book

    r = client.post("/api/v1/scm/outstanding/invoices/apply", files=_upload(po_week1(codes)))

    assert r.status_code == 404, r.text
