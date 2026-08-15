"""The two endpoints: preview writes nothing, apply writes and commits, RBAC holds.

Uses the suite's savepoint-backed `scm_app` fixture, so everything the route commits is
rolled back on teardown.

Like the service tests, the upload is GENERATED from codes this test owns
(`tests/scm/_outstanding_workbooks.py`) rather than read from the committed xlsx that names
the real extract's `BRW-BB` / `SRTWC8613-RL` / `SO397450`. Two things were wrong with the old
shape and both made the result depend on which database the test met:

* it seeded those literal codes (guarded by "insert only if absent", which is what made the
  collision survivable rather than fixed), and
* it scoped the request to `SELECT id FROM companies ORDER BY name LIMIT 1` while the
  catalogue it seeded was stamped with the test-default company. One company on an empty
  database, so they agreed; two on a prod copy, so the importer resolved nothing.

Now the principal comes first, carrying a company the test created, and everything is seeded
into that company.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm._outstanding_workbooks import (
    MARKER,
    make_codes,
    po_week1,
    require_aliases,
    seed_catalogue,
    seed_suppliers,
    week1,
    workbook,
)
from tests.scm._queued_import import queued_job_id, run_enqueued, stub_queue
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def as_company_user(app, db, gcu, gcuk, role="purchasing"):
    """Authenticate AND give the session an active company of this test's own making.

    Owned tables are company-scoped and fail closed: with no active company the ORM refuses
    to stamp `company_id` and every insert is rejected. In a real request
    `apply_company_scope` resolves that from the caller's bearer token, which these tests
    replace with a dependency override - so the override has to supply the company too, or
    the route under test cannot write anything and the failure looks like a bug in the
    importer rather than a missing test principal.

    The company is CREATED here rather than borrowed with `ORDER BY name LIMIT 1`. Borrowing
    picks a different row depending on which companies the database happens to hold, and when
    that is not the company the catalogue was stamped with, the importer resolves nothing.
    The scope is also set on the session immediately, so rows seeded after this call land in
    the same company the route will read under.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    as_user(app, gcu, gcuk, seed_user(db, role))

    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=f"{MARKER} route company {company_id[:8]}",
                   code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True))
    db.flush()
    scope = frozenset({company_id})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return scope


def _seed(db):
    """This test's own codes, plus the products and warehouses its upload names."""
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


def _seed_po(db):
    """The same codes plus the suppliers the purchase-order book's creditor codes name."""
    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


def _upload(data: bytes, name: str = "outstanding_so.xlsx"):
    return {"file": (name, data, _XLSX)}


def _missing_column_file(codes) -> bytes:
    """A file with no delivery-date column: a different report, which would wipe every date
    in scope if it were accepted."""
    return workbook([[codes.project_so, codes.item_rl, 10]],
                    headers=("S/O NO", "ITEM CODE", "QTY"))


def test_preview_returns_the_diff_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload(week1(codes)))
    after = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["added"] == 5
    assert body["scope_documents"] == list(codes.documents)
    assert before == after, "preview must not write"


def test_apply_queues_a_job_and_the_job_writes_the_lines(scm_app, monkeypatch):
    """The route hands the book to the queue; the worker writes it.

    Both halves in one test on purpose: a 202 that enqueues nothing is a silent no-op, and a
    task that writes correctly behind a route nobody can reach is worth nothing either.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)
    captured = stub_queue(monkeypatch)

    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/apply",
                             files=_upload(week1(codes)))

    assert r.status_code == 202, r.text
    assert r.json()["job_id"], "the response must name the job to watch"
    assert captured["enqueued"][0]["name"] == "process_outstanding_import"
    assert captured["enqueued"][0]["kwargs"]["queue_name"] == "imports"
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :so"
    ), {"so": codes.project_so}).scalar() == 0, "the request itself must write nothing"

    run_enqueued(captured, db, monkeypatch)

    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :so"
    ), {"so": codes.project_so}).scalar() == 3


def test_preview_of_the_purchase_order_book_returns_the_diff(scm_app):
    """The read half of the PO channel, which has always been safe and correct."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed_po(db)

    r = TestClient(app).post("/api/v1/scm/outstanding/purchase-orders/preview",
                             files=_upload(po_week1(codes), "outstanding_po.xlsx"))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["added"] == 5
    assert body["scope_documents"] == list(codes.po_documents)
    assert body["resolution_issues"] == []


def test_apply_of_the_purchase_order_book_writes_purchase_orders(scm_app, monkeypatch):
    """The endpoint that was corrupting: it accepted the supply book and wrote sales demand.

    Asserted on the tables rather than on the response, because the broken version answered
    200 with `applied.added == 5` while every one of those five rows was a sales order line -
    and now the response carries no counts at all.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed_po(db)
    captured = stub_queue(monkeypatch)

    r = TestClient(app).post("/api/v1/scm/outstanding/purchase-orders/apply",
                             files=_upload(po_week1(codes), "outstanding_po.xlsx"))
    assert r.status_code == 202, r.text
    run_enqueued(captured, db, monkeypatch)

    assert db.execute(text(
        "SELECT count(*) FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = :po"
    ), {"po": codes.main_po}).scalar() == 3
    assert db.execute(text(
        "SELECT count(*) FROM sales_orders WHERE so_number IN (:a, :b)"
    ), {"a": codes.main_po, "b": codes.alt_po}).scalar() == 0, \
        "the endpoint wrote the purchase order book into sales_orders"


def test_a_file_missing_a_required_column_explains_which_one(scm_app):
    """A 200 carrying ok:false, so the screen can name the column to add."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files=_upload(_missing_column_file(codes), "bad.xlsx"),
    )

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "required_date" in r.json()["missing_columns"]


def test_a_file_missing_a_required_column_fails_the_job_not_the_request(scm_app, monkeypatch):
    """The unreadable-file 400 moved onto the job, and had to move somewhere.

    Reading happens on the worker now, so the request cannot say whether the file is usable
    without parsing the whole book twice. The operator still gets the answer, and gets it
    where the rest of the outcome lives: the JOB fails, naming the column to add.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)
    captured = stub_queue(monkeypatch)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/apply",
        files=_upload(_missing_column_file(codes), "bad.xlsx"),
    )
    assert r.status_code == 202, r.text

    run_enqueued(captured, db, monkeypatch)

    job = db.execute(text(
        "SELECT status, error FROM import_jobs WHERE id = :id"
    ), {"id": queued_job_id(captured)}).first()
    assert job.status == "failed"
    assert "required date" in (job.error or "").lower()


#: This channel's own job types, so a count of jobs is a count of THIS channel's jobs. An
#: unscoped `count(*) FROM import_jobs` also counts whatever another suite is doing on the
#: same database at the same time.
_JOB_TYPES = ("outstanding_so_import", "outstanding_po_import")


def _jobs(db) -> int:
    return db.execute(text(
        "SELECT count(*) FROM import_jobs WHERE job_type = ANY(:t)"
    ), {"t": list(_JOB_TYPES)}).scalar()


def test_no_single_company_is_refused_before_any_job_row(scm_app, monkeypatch):
    """Owned tables (AC-4.3): with no single company the worker would either fail closed
    part-way through or write across the partition, and by then the operator has been told
    the upload was queued. Refused at the route, leaving nothing behind.

    Both kinds, because they are two write paths into two different tables and a guard on
    one of them is a guard on neither.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)
    seed_suppliers(db, codes)
    captured = stub_queue(monkeypatch)
    before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    for kind, files in (
        ("sales-orders", _upload(week1(codes))),
        ("purchase-orders", _upload(po_week1(codes), "outstanding_po.xlsx")),
    ):
        r = client.post(f"/api/v1/scm/outstanding/{kind}/apply", files=files)
        assert r.status_code == 400, f"{kind}: {r.text}"
        assert "single company" in r.text, kind

    assert captured["enqueued"] == []
    assert captured["retained"] == []
    assert _jobs(db) == before


def test_preview_is_refused_at_the_same_scope_the_job_would_run_at(scm_app, monkeypatch):
    """A preview read across every company is a diff about somebody else's rows.

    `_resolve` builds its product lookup last-write-wins over `products.product_code`, and
    11,390 codes are held by more than one company - so an all-companies read binds a line to
    whichever company's product came out of the query last, and the counts on screen are not
    the counts apply would produce. Refused for BOTH steps, exactly as the customer importer
    refuses both: a preview that cannot be trusted is worse than no preview.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)
    seed_suppliers(db, codes)
    captured = stub_queue(monkeypatch)
    lines_before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    jobs_before = _jobs(db)

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    client = TestClient(app)

    for kind, files in (
        ("sales-orders", _upload(week1(codes))),
        ("purchase-orders", _upload(po_week1(codes), "outstanding_po.xlsx")),
    ):
        r = client.post(f"/api/v1/scm/outstanding/{kind}/preview", files=files)
        assert r.status_code == 400, f"{kind}: {r.text}"
        assert "single company" in r.text, kind

    assert db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar() == lines_before
    assert _jobs(db) == jobs_before, "a preview creates no job"
    assert captured["retained"] == [], "and retains no file"


def test_the_job_snapshots_the_company_and_retains_the_operators_own_file(scm_app,
                                                                         monkeypatch):
    """The worker re-establishes exactly this company, and the retained bytes are the ones
    that arrived - not the macro-stripped copy the reader parses."""
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)
    captured = stub_queue(monkeypatch)
    payload = week1(codes)

    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/apply",
                             files=_upload(payload, "the operators book.xlsx"))

    assert r.status_code == 202, r.text
    company_id = db.execute(text(
        "SELECT company_id FROM import_jobs WHERE id = :id"
    ), {"id": queued_job_id(captured)}).scalar()
    assert str(company_id) == next(iter(scope))
    assert captured["retained"][0]["bytes"] == payload
    assert captured["retained"][0]["name"] == "the operators book.xlsx"


def test_a_non_excel_upload_is_rejected(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_an_unknown_document_type_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post("/api/v1/scm/outstanding/invoices/preview",
                             files=_upload(week1(codes)))
    assert r.status_code == 404


def test_a_user_without_the_operator_permission_is_denied(scm_app):
    """Uploading the open order book rewrites what the whole plan is computed from."""
    app, db, gcu, gcuk = scm_app
    require_aliases(db)
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    # No catalogue seeded on purpose: the denial must happen before the file is read.
    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload(week1(make_codes())))
    assert r.status_code == 403
