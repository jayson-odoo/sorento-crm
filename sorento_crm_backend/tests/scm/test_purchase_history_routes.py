"""The HTTP contract for the two new feeds, and the link report.

The service suites (`test_po_history_import`, `test_order_inquiry_import`,
`test_order_link_both_ways`) already prove the parsing, the write shape and the both-way
linkage. Nothing here re-derives any of that. What is proved here is only what the WIRE has
to carry:

* preview writes nothing, and an unreadable file still comes back 200 so the screen can show
  WHICH part failed;
* apply writes, commits, and reports the link resolution it triggered;
* the operator permission is required, and the denial happens before the file is read;
* the accept list is the configured one, so the `.xls` the customer actually holds gets in.

Both fixtures are real slices of the customer's own files, and the products they name are
seeded into the company this test creates, so the request resolves them under its own scope
rather than under whatever a prod-copy database happens to hold.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTPHR"
FIXTURES = Path(__file__).parent / "fixtures"
PO_LISTING = FIXTURES / "po_listing_with_detail_sample.xls"
ORDER_INQUIRY = FIXTURES / "order_inquiry_sample.xlsx"

_XLS = "application/vnd.ms-excel"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Codes the fixtures name. Seeded under this test's OWN company, so the per-company unique
#: index holds whether or not a production copy already carries them.
PO_ITEMS = ("CBM1030", "SRTSCBD290A")
INQUIRY_ITEMS = ("CWB242", "C-FHSS14")


def _u() -> str:
    return str(uuid.uuid4())


def _seed_products(db, codes) -> None:
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
        category_name=f"{MARKER} cat",
    )
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} unit",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    for code in codes:
        db.add(Product(
            id=_u(), product_code=code, product_name=f"{MARKER} {code}",
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        ))
    db.flush()


def _po_file(name: str = "po_listing.xls"):
    return {"file": (name, PO_LISTING.read_bytes(), _XLS)}


def _inquiry_file(name: str = "order_inquiry.xlsx"):
    return {"file": (name, ORDER_INQUIRY.read_bytes(), _XLSX)}


def _orders(db) -> int:
    return db.execute(text("SELECT count(*) FROM purchase_orders")).scalar()


# --------------------------------------------------------------------------- #
# purchase history
# --------------------------------------------------------------------------- #

def test_preview_reports_the_book_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)

    before = _orders(db)
    r = TestClient(app).post("/api/v1/scm/purchase-history/preview", files=_po_file())
    assert _orders(db) == before, "preview wrote purchase orders"

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["orders"] >= 1
    assert body["lines"] >= 1
    # The dates come back as strings, because a preview is a screen and not a calculation.
    assert isinstance(body["date_from"], str)


def test_apply_writes_the_book_and_reports_the_links_it_resolved(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)

    before = _orders(db)
    r = TestClient(app).post("/api/v1/scm/purchase-history/apply", files=_po_file())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orders_created"] >= 1
    assert _orders(db) == before + body["orders_created"]
    # Reported on the upload result, because the pairing may have been claimed by a file
    # somebody else uploaded weeks ago and nothing else would say so.
    assert "links" in body and "resolved" in body["links"]


def test_re_uploading_the_same_book_creates_nothing_further(scm_app):
    """Re-exporting a wider date range and sending the whole book again is normal."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    client = TestClient(app)

    first = client.post("/api/v1/scm/purchase-history/apply", files=_po_file()).json()
    after_first = _orders(db)
    second = client.post("/api/v1/scm/purchase-history/apply", files=_po_file()).json()

    assert first["orders_created"] >= 1
    assert second["orders_created"] == 0
    assert _orders(db) == after_first


def test_an_unreadable_file_previews_as_ok_false_rather_than_an_error(scm_app):
    """The screen has to render WHICH part failed, and an exception body would lose it."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/preview",
        files={"file": ("nonsense.xlsx", b"PK\x03\x04not-a-workbook", _XLSX)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["problems"], "a file that could not be read must say why"


def test_applying_an_unreadable_file_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/apply",
        files={"file": ("nonsense.xlsx", b"PK\x03\x04not-a-workbook", _XLSX)},
    )
    assert r.status_code == 400, r.text


def test_a_file_type_outside_the_configured_list_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/preview",
        files={"file": ("book.csv", PO_LISTING.read_bytes(), "text/csv")},
    )
    assert r.status_code == 400
    assert ".xls" in r.json()["detail"], "the message must name what IS accepted"


def test_an_imported_order_reads_honestly_in_the_purchase_order_list(scm_app):
    """"It should appear in PO list also" - and appear as what it is.

    Three things a buyer looking up a 2020 order is owed, each of which was wrong when the
    real file first went in:

    * the quantity the ORDER says, not the quantity still incoming. `Total qty` counted open
      lines only, so all 1,586 historical orders rendered as empty orders.
    * `open_qty` alongside it, still zero, because a closed order is not incoming supply and
      the two questions need two numbers.
    * a source of `import` rather than `manual` - nobody keyed these by hand.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    client = TestClient(app)

    client.post("/api/v1/scm/purchase-history/apply", files=_po_file())
    r = client.get("/api/v1/scm/purchase-orders", params={"query": "202001-S0001", "limit": 5})

    assert r.status_code == 200, r.text
    rows = [p for p in r.json()["data"] if p["po_number"] == "202001-S0001"]
    assert rows, "the imported order is not in the list at all"
    po = rows[0]

    assert po["status"] == "closed"
    assert po["line_count"] >= 1, "an order with lines must not read as empty"
    assert po["total_qty"] > 0, "Total qty must be what the order says"
    assert po["open_qty"] == 0, "history is not incoming supply"
    assert po["open_line_count"] == 0
    assert po["is_on_order"] is False
    assert po["source"] == "import"
    assert po["supplier_name"], "the creditor on the order is the supplier"


# --------------------------------------------------------------------------- #
# order inquiry
# --------------------------------------------------------------------------- #

def test_order_inquiry_preview_reports_the_rows_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)

    before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    r = TestClient(app).post("/api/v1/scm/order-inquiry/preview", files=_inquiry_file())
    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() == before

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["rows"] >= 1
    assert body["po_claims"] >= 1


def test_order_inquiry_apply_claims_the_purchase_order_links(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)

    before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    r = TestClient(app).post("/api/v1/scm/order-inquiry/apply", files=_inquiry_file())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claims_written"] >= 1
    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() > before
    assert "links" in body


def test_open_claims_are_reportable_over_http(scm_app):
    """"34 sales orders name a purchase order we have not seen" is how somebody finds out the
    PO book is a month behind."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)
    client = TestClient(app)

    client.post("/api/v1/scm/order-inquiry/apply", files=_inquiry_file())
    r = client.get("/api/v1/scm/order-links/open")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] >= 1
    assert body["waiting_for_purchase_order"] >= 1
    assert body["purchase_orders"], "the numbers are named, not only counted"


# --------------------------------------------------------------------------- #
# who may do this
# --------------------------------------------------------------------------- #

def test_a_user_without_the_operator_permission_is_denied(scm_app):
    """These files rewrite what the whole plan is computed from."""
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    client = TestClient(app)
    # Nothing seeded on purpose: the denial must happen before the file is read.
    for url, files in (
        ("/api/v1/scm/purchase-history/preview", _po_file()),
        ("/api/v1/scm/purchase-history/apply", _po_file()),
        ("/api/v1/scm/order-inquiry/preview", _inquiry_file()),
        ("/api/v1/scm/order-inquiry/apply", _inquiry_file()),
    ):
        assert client.post(url, files=files).status_code == 403, url
    assert client.get("/api/v1/scm/order-links/open").status_code == 403


# --------------------------------------------------------------------------- #
# the Test function, as a standard
# --------------------------------------------------------------------------- #

def test_testing_the_book_writes_nothing_and_returns_the_standard_verdict(scm_app):
    """`?validate_only=true` is the same Test the order-tracking and GRN imports have.

    Same query parameter, same `{valid, errors, warnings, summary}` shape, so a Test means
    the same thing wherever somebody presses it. The SCM uploads were the odd ones out.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)

    before = _orders(db)
    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/apply",
        params={"validate_only": "true"},
        files=_po_file(),
    )
    assert _orders(db) == before, "a Test that writes is not a test"

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"valid", "errors", "warnings", "summary"}
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["summary"]["would_create"] >= 1


def test_a_warning_names_what_it_is_about_and_does_not_block(scm_app):
    """The charge lines and the unknown item codes are warnings, not errors.

    Refusing 1,586 orders because two product codes are missing would be the wrong call to
    force on the operator - and a warning they read before pressing Confirm is a decision
    rather than an accident. It has to NAME the codes, though: a bare count tells them there
    is a problem without telling them which.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    # No products seeded on purpose: every stock code in the file is unknown.

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/apply",
        params={"validate_only": "true"},
        files=_po_file(),
    )
    body = r.json()

    assert body["valid"] is True, "an unknown item does not make the file unusable"
    assert body["warnings"], "the operator must be told the lines will be skipped"
    joined = " ".join(body["warnings"])
    assert "item code" in joined and "skipped" in joined
    assert any(ch.isdigit() for ch in joined), "the warning names codes, not just a count"


def test_an_unreadable_file_tests_as_invalid_with_the_reason(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/apply",
        params={"validate_only": "true"},
        files={"file": ("nonsense.xlsx", b"PK\x03\x04not-a-workbook", _XLSX)},
    )
    assert r.status_code == 200, "a verdict, not an exception - the screen renders it"
    body = r.json()
    assert body["valid"] is False
    assert body["errors"], "an invalid verdict with no reason is useless"


def test_the_inquiry_sheet_tests_the_same_way(scm_app):
    """One contract across the feeds, or the button means something different per screen."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)

    before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    r = TestClient(app).post(
        "/api/v1/scm/order-inquiry/apply",
        params={"validate_only": "true"},
        files=_inquiry_file(),
    )
    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() == before

    body = r.json()
    assert set(body) >= {"valid", "errors", "warnings", "summary"}
    assert body["valid"] is True
    assert body["summary"]["total_rows"] >= 1
