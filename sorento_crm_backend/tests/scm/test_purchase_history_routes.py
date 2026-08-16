"""The HTTP contract for the two new feeds, and the link report.

The service suites (`test_po_history_import`, `test_order_inquiry_import`,
`test_order_link_both_ways`) already prove the parsing, the write shape and the both-way
linkage. Nothing here re-derives any of that. What is proved here is only what the WIRE has
to carry:

* preview writes nothing, and an unreadable file still comes back 200 so the screen can show
  WHICH part failed;
* apply QUEUES: 202, a job row carrying the company, the operator's own file retained, and
  the task that then writes the book (run here directly - an RQ worker is shared across
  worktrees, so a test must never start one);
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
from tests.scm._queued_import import queued_job_id, run_enqueued, stub_queue
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTPHR"
FIXTURES = Path(__file__).parent / "fixtures"
PO_LISTING = FIXTURES / "po_listing_with_detail_sample.xls"
#: The other shape the same channel reads: the flat PO + SPO extract (S5).
PO_SPO_HISTORY = FIXTURES / "po_spo_history_sample.xlsx"
ORDER_INQUIRY = FIXTURES / "order_inquiry_sample.xlsx"

_XLS = "application/vnd.ms-excel"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Codes the fixtures name. Seeded under this test's OWN company, so the per-company unique
#: index holds whether or not a production copy already carries them.
PO_ITEMS = ("CBM1030", "SRTSCBD290A")
INQUIRY_ITEMS = ("CWB242", "C-FHSS14")
PO_SPO_ITEMS = (
    "BRBC22350W-1-SG", "BRC21131XUW-3AS-ENG", "CB4702", "CB4924-CR", "CB4932-BL",
    "CBF66403", "CBMC5865", "CGB3600WTR", "CGB3601WTR", "RPACC", "SRT373-8-NL",
    "SRTBF11705", "SRTSA625A-NL", "SRTWB247", "SRTWC287A-RL", "SRTWCY8605-PJ",
    "SRTWHBWP", "SRTWT9513", "SRTWT9802", "SRTWT9813", "WESERP10B",
)


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


def _po_spo_file(name: str = "po_spo_history.xlsx"):
    return {"file": (name, PO_SPO_HISTORY.read_bytes(), _XLSX)}


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


def test_apply_queues_the_book_and_the_job_writes_it_with_its_links(scm_app, monkeypatch):
    """202 from the route, the write from the job, and the link resolution on the result.

    The links are still reported - they may have been claimed by a file somebody else
    uploaded weeks ago and nothing else would say so - they just live on the job now,
    because the request answers before the resolve has run.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    captured = stub_queue(monkeypatch)

    before = _orders(db)
    r = TestClient(app).post("/api/v1/scm/purchase-history/apply", files=_po_file())

    assert r.status_code == 202, r.text
    assert captured["enqueued"][0]["name"] == "process_po_history_import"
    assert _orders(db) == before, "the request itself must write nothing"

    run_enqueued(captured, db, monkeypatch)

    row = db.execute(text(
        "SELECT status, result FROM import_jobs WHERE id = :id"
    ), {"id": queued_job_id(captured)}).first()
    assert row.status == "finished", row
    upload = row.result["upload"]
    assert upload["orders_created"] >= 1
    assert _orders(db) == before + upload["orders_created"]
    assert "resolved" in upload["links"]


def _upload_result(db, captured, index: int = -1) -> dict:
    """The channel's own answer, off the job it landed on."""
    row = db.execute(text("SELECT status, result FROM import_jobs WHERE id = :id"),
                     {"id": queued_job_id(captured, index)}).first()
    assert row is not None, "the route created no job row"
    assert row.status == "finished", f"job did not finish: {row.status}"
    return row.result["upload"]


def test_re_uploading_the_same_book_creates_nothing_further(scm_app, monkeypatch):
    """Re-exporting a wider date range and sending the whole book again is normal."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    captured = stub_queue(monkeypatch)
    client = TestClient(app)

    client.post("/api/v1/scm/purchase-history/apply", files=_po_file())
    run_enqueued(captured, db, monkeypatch)
    first = _upload_result(db, captured)
    after_first = _orders(db)

    client.post("/api/v1/scm/purchase-history/apply", files=_po_file())
    run_enqueued(captured, db, monkeypatch)
    second = _upload_result(db, captured)

    assert first["orders_created"] >= 1
    assert second["orders_created"] == 0
    assert _orders(db) == after_first


def test_the_structured_po_spo_export_goes_through_the_same_channel(scm_app, monkeypatch):
    """S5. One channel, two file shapes: which one arrived is read off the header row.

    Proved on the WIRE rather than only in the service, because detection resolves the
    header through `import_field_alias` on the request's own session - so this is also the
    test that fails if migration 358's seed is missing from a database.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_SPO_ITEMS)
    captured = stub_queue(monkeypatch)
    client = TestClient(app)

    preview = client.post("/api/v1/scm/purchase-history/preview", files=_po_spo_file())
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["ok"] is True
    assert body["unmapped_headers"] == [], "every one of the 27 columns must resolve"
    assert body["orders_po"] == 6 and body["orders_spo"] == 3

    r = client.post("/api/v1/scm/purchase-history/apply", files=_po_spo_file())
    assert r.status_code == 202, r.text
    run_enqueued(captured, db, monkeypatch)

    row = db.execute(text("SELECT status, total_rows, processed_rows FROM import_jobs "
                          "WHERE id = :id"),
                     {"id": queued_job_id(captured)}).first()
    assert row.status == "finished", row
    # The invariant every queued channel is held to: every source row carries an outcome,
    # the grand-total row at the foot of the export included.
    assert row.total_rows == 33
    assert row.processed_rows == row.total_rows

    upload = _upload_result(db, captured)
    assert upload["lines_po"] == 19 and upload["lines_spo"] == 12


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


def test_applying_an_unreadable_file_fails_the_job_with_the_reason(scm_app, monkeypatch):
    """The old 400 becomes a failed JOB carrying the problems.

    The file is read on the worker now, so the request cannot know. What must not happen is
    the other option: a job that finishes green having written nothing.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    captured = stub_queue(monkeypatch)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/apply",
        files={"file": ("nonsense.xlsx", b"PK\x03\x04not-a-workbook", _XLSX)},
    )
    assert r.status_code == 202, r.text

    run_enqueued(captured, db, monkeypatch)

    row = db.execute(text("SELECT status, error FROM import_jobs WHERE id = :id"),
                     {"id": queued_job_id(captured)}).first()
    assert row.status == "failed"
    assert row.error, "a failed import that does not say why is useless"


#: These channels' own job types, so a count of jobs is a count of THEIR jobs. An unscoped
#: `count(*) FROM import_jobs` also counts whatever another suite is doing on the same
#: database at the same moment.
_JOB_TYPES = ("po_history_import", "sales_history_import", "order_inquiry_import")


def _jobs(db) -> int:
    return db.execute(text(
        "SELECT count(*) FROM import_jobs WHERE job_type = ANY(:t)"
    ), {"t": list(_JOB_TYPES)}).scalar()


def test_no_single_company_is_refused_before_any_job_row(scm_app, monkeypatch):
    """AC-4.3, on the history channels too: these feeds write owned tables."""
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    captured = stub_queue(monkeypatch)
    before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    for url, files in (
        ("/api/v1/scm/purchase-history/apply", _po_file()),
        ("/api/v1/scm/sales-history/apply", _so_file()),
        ("/api/v1/scm/order-inquiry/apply", _inquiry_file()),
    ):
        r = client.post(url, files=files)
        assert r.status_code == 400, f"{url}: {r.text}"
        assert "single company" in r.text, url

    assert captured["enqueued"] == []
    assert captured["retained"] == []
    assert _jobs(db) == before


def test_reading_is_refused_at_the_same_scope_the_job_would_run_at(scm_app, monkeypatch):
    """Preview and Test, at the scope the write would run at, or their answer is untrue.

    Every one of these readers resolves item codes, debtor codes and warehouses to ids
    through last-write-wins lookups, and 11,390 product codes are held by more than one
    company. Read across all of them, "1,586 orders, 2 unknown items" is a sentence about
    rows the apply would never touch - and the operator confirms on the strength of it and
    gets a 400. Same refusal on both steps, as the customer importer does
    (`order_management/customers.py`).
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, PO_ITEMS)
    captured = stub_queue(monkeypatch)
    orders_before = _orders(db)
    claims_before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    jobs_before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    for url, params, files in (
        ("/api/v1/scm/purchase-history/preview", {}, _po_file()),
        ("/api/v1/scm/sales-history/preview", {}, _so_file()),
        ("/api/v1/scm/order-inquiry/preview", {}, _inquiry_file()),
        # The Test verdict is a read too, and it is the one the operator acts on.
        ("/api/v1/scm/purchase-history/apply", {"validate_only": "true"}, _po_file()),
        ("/api/v1/scm/order-inquiry/apply", {"validate_only": "true"}, _inquiry_file()),
    ):
        r = client.post(url, params=params, files=files)
        assert r.status_code == 400, f"{url}: {r.text}"
        assert "single company" in r.text, url

    assert _orders(db) == orders_before
    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() == \
        claims_before
    assert _jobs(db) == jobs_before, "a refused read creates no job"
    assert captured["retained"] == [], "and retains no file"


def test_a_file_type_outside_the_configured_list_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/purchase-history/preview",
        files={"file": ("book.csv", PO_LISTING.read_bytes(), "text/csv")},
    )
    assert r.status_code == 400
    assert ".xls" in r.json()["detail"], "the message must name what IS accepted"


def test_an_imported_order_reads_honestly_in_the_purchase_order_list(scm_app, monkeypatch):
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
    captured = stub_queue(monkeypatch)
    client = TestClient(app)

    client.post("/api/v1/scm/purchase-history/apply", files=_po_file())
    run_enqueued(captured, db, monkeypatch)
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


def test_order_inquiry_apply_claims_the_purchase_order_links(scm_app, monkeypatch):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)
    captured = stub_queue(monkeypatch)

    before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    r = TestClient(app).post("/api/v1/scm/order-inquiry/apply", files=_inquiry_file())

    assert r.status_code == 202, r.text
    assert captured["enqueued"][0]["name"] == "process_order_inquiry_import"

    run_enqueued(captured, db, monkeypatch)

    body = _upload_result(db, captured)
    assert body["claims_written"] >= 1
    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() > before
    assert "links" in body


def test_open_claims_are_reportable_over_http(scm_app, monkeypatch):
    """"34 sales orders name a purchase order we have not seen" is how somebody finds out the
    PO book is a month behind."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)
    captured = stub_queue(monkeypatch)
    client = TestClient(app)

    client.post("/api/v1/scm/order-inquiry/apply", files=_inquiry_file())
    run_enqueued(captured, db, monkeypatch)
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


# --------------------------------------------------------------------------- #
# sales history: the demand-side twin, over the wire
# --------------------------------------------------------------------------- #

SO_LISTING = FIXTURES / "autocount_so_detail_excerpt.xlsx"


def _so_file():
    return {"file": ("autocount_so_detail_excerpt.xlsx", SO_LISTING.read_bytes(), _XLSX)}


def test_sales_history_preview_reports_the_book_and_writes_nothing(scm_app):
    """The uploader's look-before-you-leap, on the client's genuine excerpt."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    before = db.execute(text("SELECT count(*) FROM sales_orders")).scalar()

    r = TestClient(app).post("/api/v1/scm/sales-history/preview", files=_so_file())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orders"] >= 1
    assert body["missing_columns"] == []
    # The figure that says which channel this file belongs to.
    assert body["outstanding_lines"] == 0
    assert db.execute(text("SELECT count(*) FROM sales_orders")).scalar() == before


def test_sales_history_apply_absorbs_the_book_without_creating_demand(scm_app, monkeypatch):
    """The claim the whole feed rests on, asserted end to end rather than in the service.

    `scm.committed_v` is measured across the WHOLE view: a line leaking into committed demand
    through some join this test does not name would still move the total.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    captured = stub_queue(monkeypatch)
    before = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())

    r = TestClient(app).post("/api/v1/scm/sales-history/apply", files=_so_file())

    assert r.status_code == 202, r.text
    assert captured["enqueued"][0]["name"] == "process_sales_history_import"

    run_enqueued(captured, db, monkeypatch)

    body = _upload_result(db, captured)
    assert body["orders_created"] >= 1
    after = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())
    assert after == before, "absorbing sales history created committed demand"
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines "
        "WHERE source_system = 'scm_so_history' AND line_status <> 'closed'"
    )).scalar() == 0


def test_sales_history_apply_needs_the_operator_permission(scm_app):
    """Reading the plan is one thing; rewriting what it is computed from is another."""
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post("/api/v1/scm/sales-history/apply", files=_so_file())

    assert r.status_code == 403, r.text
