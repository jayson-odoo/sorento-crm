"""The HTTP contract for the Order Inquiry upload, and the link report.

Renamed from `test_purchase_history_routes.py` (ingest-parity-standardisation
S4, AC-P4-1): the purchase-history and sales-history routes this file used to
also cover were retired - closed history now arrives through the ESB's own
document ingest. What survives here is the Order Inquiry sheet, which Project
Sales still owns (ADR 0010) behind the same `/api/v1/scm/order-inquiry/*`
URLs the FE upload dialog already calls.

The service suite (`test_order_inquiry_import`, `test_order_link_both_ways`) already proves
the parsing, the write shape and the both-way linkage. Nothing here re-derives any of that.
What is proved here is only what the WIRE has to carry:

* preview writes nothing, and an unreadable file still comes back 200 so the screen can show
  WHICH part failed;
* apply QUEUES: 202, a job row carrying the company, the operator's own file retained, and
  the task that then writes the book (run here directly - an RQ worker is shared across
  worktrees, so a test must never start one);
* the operator permission is required, and the denial happens before the file is read;
* the accept list is the configured one.

The fixture is a real slice of the customer's own file, and the products it names are seeded
into the company this test creates, so the request resolves them under its own scope rather
than under whatever a prod-copy database happens to hold.
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
ORDER_INQUIRY = FIXTURES / "order_inquiry_sample.xlsx"

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Codes the fixture names. Seeded under this test's OWN company, so the per-company unique
#: index holds whether or not a production copy already carries them.
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


def _inquiry_file(name: str = "order_inquiry.xlsx"):
    return {"file": (name, ORDER_INQUIRY.read_bytes(), _XLSX)}


def _upload_result(db, captured, index: int = -1) -> dict:
    """The channel's own answer, off the job it landed on."""
    row = db.execute(text("SELECT status, result FROM import_jobs WHERE id = :id"),
                     {"id": queued_job_id(captured, index)}).first()
    assert row is not None, "the route created no job row"
    assert row.status == "finished", f"job did not finish: {row.status}"
    return row.result["upload"]


#: This channel's own job type, so a count of jobs is a count of ITS jobs. An unscoped
#: `count(*) FROM import_jobs` also counts whatever another suite is doing on the same
#: database at the same moment.
_JOB_TYPES = ("order_inquiry_import",)


def _jobs(db) -> int:
    return db.execute(text(
        "SELECT count(*) FROM import_jobs WHERE job_type = ANY(:t)"
    ), {"t": list(_JOB_TYPES)}).scalar()


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

def test_no_single_company_is_refused_before_any_job_row(scm_app, monkeypatch):
    """AC-4.3: this feed writes owned tables."""
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)
    captured = stub_queue(monkeypatch)
    before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    r = client.post("/api/v1/scm/order-inquiry/apply", files=_inquiry_file())
    assert r.status_code == 400, r.text
    assert "single company" in r.text

    assert captured["enqueued"] == []
    assert captured["retained"] == []
    assert _jobs(db) == before


def test_reading_is_refused_at_the_same_scope_the_job_would_run_at(scm_app, monkeypatch):
    """Preview and Test, at the scope the write would run at, or their answer is untrue.

    The reader resolves item codes, debtor codes and warehouses to ids through
    last-write-wins lookups, and 11,390 product codes are held by more than one company.
    Read across all of them, the counts on the answer are a sentence about rows the apply
    would never touch - and the operator confirms on the strength of it and gets a 400.
    Same refusal on both steps, as the customer importer does
    (`order_management/customers.py`).
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)
    captured = stub_queue(monkeypatch)
    claims_before = db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar()
    jobs_before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    for url, params, files in (
        ("/api/v1/scm/order-inquiry/preview", {}, _inquiry_file()),
        # The Test verdict is a read too, and it is the one the operator acts on.
        ("/api/v1/scm/order-inquiry/apply", {"validate_only": "true"}, _inquiry_file()),
    ):
        r = client.post(url, params=params, files=files)
        assert r.status_code == 400, f"{url}: {r.text}"
        assert "single company" in r.text, url

    assert db.execute(text("SELECT count(*) FROM scm.order_link_claim")).scalar() == \
        claims_before
    assert _jobs(db) == jobs_before, "a refused read creates no job"
    assert captured["retained"] == [], "and retains no file"


def test_a_user_without_the_operator_permission_is_denied(scm_app):
    """This file rewrites what the whole plan is computed from."""
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    client = TestClient(app)
    # Nothing seeded on purpose: the denial must happen before the file is read.
    for url, files in (
        ("/api/v1/scm/order-inquiry/preview", _inquiry_file()),
        ("/api/v1/scm/order-inquiry/apply", _inquiry_file()),
    ):
        assert client.post(url, files=files).status_code == 403, url
    assert client.get("/api/v1/scm/order-links/open").status_code == 403


# --------------------------------------------------------------------------- #
# the Test function, as a standard
# --------------------------------------------------------------------------- #

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
