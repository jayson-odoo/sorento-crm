"""What the queued SCM imports record, per source row, on the job.

The route tests next door prove the wire (202, a job row, the company snapshot, the retained
file). This file is about the other half: the worker task, and specifically the thing an
operator opens the job page to find out - what happened to each row of their spreadsheet.

Four claims, each one a way an import can look successful while being useless:

* **every row is accounted for, and the total is everything the job accounted for.** Processed
  equals total: captions, rows that state nothing outstanding, rows that could not be read and
  rows that were written all carry a code, so a 4,349-row file never finishes reporting 4,290 -
  and the total INCLUDES the lines closed (or instalments withdrawn) by absence, which have an
  outcome and no source row, so it never finishes reporting 6 of 5 either.
* **closures are recorded.** A line we hold that the file no longer carries is closed, and
  closing is the destructive half of an outstanding upload - "12 updated" would hide it.
* **the total is published before the first write**, or the upload drawer shows 0/0 for the
  whole run and reads as stuck.
* **an unreadable file fails the JOB**, carrying its reason, rather than finishing green with
  nothing written (the old routes' 400, moved to where the work moved).

All five channels are exercised, not only the outstanding book: the per-row outcome is the
same promise on each, and the three that were added last (purchase history, sales history, the
inquiry sheet) are the ones whose files are mostly NOT lines.

The tasks are CALLED here, never enqueued: RQ queues are shared across worktrees, so starting
a worker in a test invites a sibling to steal the job (or this suite to steal theirs).
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services import import_outcome_codes as oc
from tests.scm._outstanding_workbooks import (
    MARKER,
    make_codes,
    seed_catalogue,
    week1,
    week2,
    workbook,
)
from tests.scm._queued_import import queued_job_id, run_enqueued, stub_queue
from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_purchase_history_routes import (
    INQUIRY_ITEMS,
    ORDER_INQUIRY,
    PO_ITEMS,
    PO_LISTING,
    SO_LISTING,
    _seed_products,
)

pytestmark = requires_pg

_XLS = "application/vnd.ms-excel"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: The captain's shape, minus the columns these tests do not exercise. `AGENT` is here because
#: an agent nobody holds is the one thing an upload creates without being asked to.
AGENT_HEADERS = ("S/O NO", "DEBTOR CODE", "AGENT", "ITEM CODE", "QTY", "DELIVERY DATE",
                 "STOCK LOCATION")

#: The Order Inquiry sheet's own spelling, from the customer's file.
INQUIRY_HEADERS = ("SO NO", "ITEM CODE", "QTY", "DELIVERY DATE", "PROJECT", "PO NO")


def _upload(data: bytes, name: str = "outstanding_so.xlsx"):
    return {"file": (name, data, _XLSX)}


def _inquiry_workbook(sheets: dict) -> bytes:
    """An Order Inquiry book: `{tab name: [rows]}`, header row per tab.

    Generated rather than committed for the tests that need a SECOND upload of a CHANGED
    sheet - a withdrawal is reached by the sheet's silence, so it can only be produced by
    two files that disagree, and no single committed fixture can carry that.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        ws.append(list(INQUIRY_HEADERS))
        for row in rows:
            ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _codes(db, count: int = 2) -> tuple[str, ...]:
    """Product codes this test owns, seeded into the company the request runs under."""
    codes = tuple(f"{MARKER}-INQ{i}-{uuid.uuid4().hex[:6]}".upper() for i in range(count))
    _seed_products(db, codes)
    return codes


def _rows(db, job_db_id: str) -> list:
    return db.execute(text(
        "SELECT row_number, outcome, code, identity FROM import_job_rows "
        "WHERE import_job_id = :id ORDER BY row_number NULLS LAST"
    ), {"id": job_db_id}).fetchall()


def _job(db, job_db_id: str):
    return db.execute(text(
        "SELECT status, error, total_rows, processed_rows, successful_rows, skipped_rows, "
        "failed_rows, result FROM import_jobs WHERE id = :id"
    ), {"id": job_db_id}).first()


def _queue_and_run(app, db, monkeypatch, url: str, files: dict) -> tuple[dict, str]:
    captured = stub_queue(monkeypatch)
    response = TestClient(app).post(url, files=files)
    assert response.status_code == 202, response.text
    run_enqueued(captured, db, monkeypatch)
    return captured, queued_job_id(captured)


# --------------------------------------------------------------------------- #
# outstanding sales orders
# --------------------------------------------------------------------------- #

def test_every_source_row_is_recorded_with_its_own_outcome(scm_app, monkeypatch):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply",
        _upload(week1(codes)),
    )

    job = _job(db, job_id)
    assert job.status == "finished"
    assert job.total_rows == 5, "the file's own row count"
    assert job.processed_rows == 5, "a row with no outcome is a row nobody can account for"
    assert job.successful_rows == 5
    rows = _rows(db, job_id)
    assert [r.code for r in rows] == [oc.CREATED] * 5
    assert [r.row_number for r in rows] == [2, 3, 4, 5, 6], "the spreadsheet's own numbering"
    assert rows[0].identity["doc_no"] == codes.project_so, "named by document, never by id"


def test_a_closed_line_is_recorded_even_though_no_row_states_it(scm_app, monkeypatch):
    """The destructive half. A line we hold that the file has dropped is CLOSED, and the only
    place that fact can be found afterwards is the job."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    client = TestClient(app)

    captured = stub_queue(monkeypatch)
    client.post("/api/v1/scm/outstanding/sales-orders/apply", files=_upload(week1(codes)))
    run_enqueued(captured, db, monkeypatch)
    client.post("/api/v1/scm/outstanding/sales-orders/apply", files=_upload(week2(codes)))
    run_enqueued(captured, db, monkeypatch)

    job_id = queued_job_id(captured)
    rows = _rows(db, job_id)
    closed = [r for r in rows if r.code == oc.LINE_CLOSED]
    assert len(closed) == 1, [r.code for r in rows]
    assert closed[0].identity["item_code"] == codes.item_wt
    assert closed[0].row_number is None, "a closure is reached by ABSENCE - there is no row"
    assert closed[0].outcome == oc.OUTCOME_UPDATED, "the line WAS written; it is not a skip"
    job = _job(db, job_id)
    assert job.result["upload"]["applied"]["closed"] == 1
    # The closure has an outcome and no source row, so the FILE's row count is not what this
    # job accounted for: with it as the total the page read "6 / 5" and drew a progress bar
    # past 100%. The total is what the job accounted for, and processed reaches it exactly.
    assert job.total_rows == 6, "5 rows in the file, plus the line it closed by absence"
    assert job.result["upload"]["file_rows"] == 5, "the operator's own row count is kept"
    assert job.processed_rows == job.total_rows, "processed may never exceed the total"


def test_a_row_naming_an_unknown_product_is_skipped_with_the_reason(scm_app, monkeypatch):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    ghost = f"{MARKER}-GHOST-{uuid.uuid4().hex[:6]}".upper()
    data = workbook(
        [(codes.project_so, "300-T012", "", codes.item_rl, 10, date(2026, 7, 1),
          codes.loc_project),
         (codes.project_so, "300-T012", "", ghost, 4, date(2026, 7, 1), codes.loc_project)],
        headers=AGENT_HEADERS,
    )

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply", _upload(data),
    )

    job = _job(db, job_id)
    assert job.skipped_rows == 1
    assert job.successful_rows == 1
    skipped = [r for r in _rows(db, job_id) if r.outcome == oc.OUTCOME_SKIPPED]
    assert [r.code for r in skipped] == [oc.PRODUCT_NOT_FOUND]
    assert skipped[0].row_number == 3


def test_a_caption_row_is_not_a_line_and_says_so(scm_app, monkeypatch):
    """9,144 of these in the client's own export. Counted with their own code, so they can
    never bury the handful of rows that really did fail."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    data = workbook(
        [("ITEM PACKAGE : KITCHEN", "", "", "", None, None, ""),
         (codes.project_so, "300-T012", "", codes.item_rl, 10, date(2026, 7, 1),
          codes.loc_project)],
        headers=AGENT_HEADERS,
    )

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply", _upload(data),
    )

    job = _job(db, job_id)
    assert job.total_rows == 2
    assert job.processed_rows == 2
    codes_seen = {r.code for r in _rows(db, job_id)}
    assert oc.NOT_A_LINE in codes_seen


def test_a_row_with_nothing_left_outstanding_says_so_rather_than_failing(scm_app, monkeypatch):
    """Its own code, not a failure: on an outstanding book a settled line is reached by its
    ABSENCE, so a row that nets to zero states nothing and skips nothing that matters."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    data = workbook(
        [(codes.project_so, "300-T012", "", codes.item_rl, 10, date(2026, 7, 1),
          codes.loc_project),
         (codes.project_so, "300-T012", "", codes.item_wt, 0, date(2026, 7, 1),
          codes.loc_project)],
        headers=AGENT_HEADERS,
    )

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply", _upload(data),
    )

    job = _job(db, job_id)
    assert job.total_rows == 2
    assert job.processed_rows == 2
    settled = [r for r in _rows(db, job_id) if r.code == oc.NOTHING_OUTSTANDING]
    assert [r.row_number for r in settled] == [3]
    assert settled[0].outcome == oc.OUTCOME_SKIPPED, "nothing was written for that row"


def test_an_agent_nobody_holds_is_reported_on_the_job(scm_app, monkeypatch):
    """AC-6.4. The upload creates the master row, and the operator has to be told: it is the
    only way anybody learns that one of the 38 codes still carries no demand class."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    agent = f"{MARKER}-SEAN-{uuid.uuid4().hex[:6]} III".upper()
    data = workbook(
        [(codes.project_so, "300-T012", agent, codes.item_rl, 10, date(2026, 7, 1),
          codes.loc_project)],
        headers=AGENT_HEADERS,
    )

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply", _upload(data),
    )

    notices = _job(db, job_id).result["upload"]["unmapped_agents"]
    assert [n["code"] for n in notices] == [agent]
    assert notices[0]["is_new"] is True
    assert "unclassified" in notices[0]["reason"]
    assert db.execute(text("SELECT count(*) FROM sales_agents WHERE sales_agent = :c"),
                      {"c": agent}).scalar() == 1


def test_the_row_total_is_published_before_the_first_write(scm_app, monkeypatch):
    """Without it `total_rows` first appears when the job completes, and the drawer shows
    0/0 for the whole run - which reads as stuck."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    seen: list[tuple] = []

    from app.services.job_service import JobService

    original = JobService.update_job_progress

    def _spy(self, job_id, **kwargs):
        seen.append((kwargs.get("total_rows"), kwargs.get("processed_rows")))
        return original(self, job_id, **kwargs)

    monkeypatch.setattr(JobService, "update_job_progress", _spy)

    _queue_and_run(app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply",
                   _upload(week1(codes)))

    assert seen and seen[0] == (5, 0), seen


def test_an_unreadable_file_fails_the_job_and_writes_nothing(scm_app, monkeypatch):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)
    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    data = workbook([[codes.project_so, codes.item_rl, 10]],
                    headers=("S/O NO", "ITEM CODE", "QTY"))

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply", _upload(data),
    )

    job = _job(db, job_id)
    assert job.status == "failed"
    assert "required date" in (job.error or "").lower()
    assert db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar() == before


def test_a_broken_audit_row_count_cannot_fail_a_job_that_already_finished(scm_app,
                                                                          monkeypatch):
    """The audit row is a post-commit side effect, and so is COMPUTING its figure.

    `written_rows(result)` used to be evaluated at the call site, outside the audit writer's
    own guard, and by then `complete_job` has committed. A result shaped differently from
    what that lambda expects therefore raised into the task's handler, which called
    `fail_job` on a job whose rows are in the database - the operator reads "failed" about an
    upload that is fully applied, and re-uploads it.
    """
    from app.tasks import import_tasks

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)

    original = import_tasks._run_scm_upload_job

    def _with_a_broken_counter(*args, **kwargs):
        kwargs["written_rows"] = lambda _result: 1 // 0
        return original(*args, **kwargs)

    monkeypatch.setattr(import_tasks, "_run_scm_upload_job", _with_a_broken_counter)

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply",
        _upload(week1(codes)),
    )

    job = _job(db, job_id)
    assert job.status == "finished", "a committed success must not be reported as a failure"
    assert job.error is None
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id WHERE so.so_number = :so"
    ), {"so": codes.project_so}).scalar() == 3, "the rows it claims to have written are there"


def test_the_worker_writes_under_the_company_the_job_snapshotted(scm_app, monkeypatch):
    """The worker session starts UNSET and fails closed, so the job's company snapshot is
    what makes an owned insert stamp at all."""
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    codes = make_codes()
    seed_catalogue(db, codes)

    _c, _job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/outstanding/sales-orders/apply",
        _upload(week1(codes)),
    )

    company_id = db.execute(text("SELECT company_id FROM sales_orders WHERE so_number = :n"),
                            {"n": codes.project_so}).scalar()
    assert str(company_id) == next(iter(scope))


# --------------------------------------------------------------------------- #
# purchase history - a banded report, most of whose rows were never lines
# --------------------------------------------------------------------------- #

def test_the_purchase_book_records_an_outcome_for_every_row_it_read(scm_app, monkeypatch):
    """The customer's own export, which is four purchase lines inside twelve rows.

    The other eight are the report preamble, the two band label rows, the order headers and
    the `**SO:174830**` notes. Counting only the lines set a total of 4 for a file somebody
    can see has twelve rows in it; counting the rows without recording them left eight rows
    with no outcome at all. Both halves are asserted here, on one upload.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    # ONE of the two stock codes, so the other lands as an unmatched item on its own row.
    _seed_products(db, PO_ITEMS[:1])

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/purchase-history/apply",
        {"file": ("po_listing.xls", PO_LISTING.read_bytes(), _XLS)},
    )

    job = _job(db, job_id)
    assert job.status == "finished"
    rows = _rows(db, job_id)
    by_code: dict = {}
    for row in rows:
        by_code.setdefault(row.code, []).append(row)

    assert job.total_rows == 12, "every non-blank row above the Doc Count marker"
    assert job.processed_rows == job.total_rows, "a row with no outcome is unaccounted for"
    assert len(by_code[oc.NOT_A_LINE]) == 8, {k: len(v) for k, v in by_code.items()}
    # Real money on the order with no product behind it. Its own code, or the codes sit in
    # the unmatched list for ever telling somebody to create a product that must never exist.
    assert len(by_code[oc.CHARGE_LINE]) == 2
    assert by_code[oc.PRODUCT_NOT_FOUND][0].identity["item_code"] == PO_ITEMS[1]
    assert by_code[oc.CREATED][0].identity["item_code"] == PO_ITEMS[0]


# --------------------------------------------------------------------------- #
# sales history - the channel that timed the gateway out
# --------------------------------------------------------------------------- #

SO_STOCK_ITEM = "SRTWB243"


def test_the_sales_book_records_an_outcome_for_every_row_it_read(scm_app, monkeypatch):
    """The client's own excerpt: seven lines, one package caption, two unreadable rows.

    The caption is the case the shared `not_a_line` code was written for - there are 9,144 of
    them in the full export - and until now this channel counted them out of the total and
    never recorded them, so the same file reconciled on one channel and not on another.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, (SO_STOCK_ITEM,))

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/sales-history/apply",
        {"file": ("so_detail.xlsx", SO_LISTING.read_bytes(), _XLSX)},
    )

    job = _job(db, job_id)
    assert job.status == "finished"
    codes_seen = [r.code for r in _rows(db, job_id)]

    assert job.total_rows == 10, "every non-blank row, the package caption included"
    assert job.processed_rows == job.total_rows
    assert codes_seen.count(oc.NOT_A_LINE) == 1
    # `MISC` and `IP`: the order's cost, not any item's demand.
    assert codes_seen.count(oc.CHARGE_LINE) == 2
    assert oc.PRODUCT_NOT_FOUND in codes_seen, "an item we do not hold is named, never created"
    assert oc.CREATED in codes_seen, "the one item we DO hold is written"
    assert codes_seen.count(oc.MISSING_REQUIRED_FIELD) == 2, "the rows that are not lines"


# --------------------------------------------------------------------------- #
# order inquiry - the sheet, its restatements, and what it stops saying
# --------------------------------------------------------------------------- #

def test_the_inquiry_sheet_records_an_outcome_for_every_row(scm_app, monkeypatch):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_products(db, INQUIRY_ITEMS)

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/order-inquiry/apply",
        {"file": ("order_inquiry.xlsx", ORDER_INQUIRY.read_bytes(), _XLSX)},
    )

    job = _job(db, job_id)
    assert job.status == "finished"
    assert job.total_rows == 9
    assert job.processed_rows == job.total_rows
    codes_seen = [r.code for r in _rows(db, job_id)]
    assert oc.CREATED in codes_seen
    assert oc.PRODUCT_NOT_FOUND in codes_seen, "a code we do not hold is never invented"


def test_a_row_restating_an_instalment_is_counted_not_lost(scm_app, monkeypatch):
    """A book of 15,797 rows describes 8,272 deliveries, and the difference is restatement.

    Nothing is skipped - the row's quantity is inside the instalment - so it rides on
    `unchanged` with its own code. Reported as loss, the operator reads a working import as a
    broken one.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    (item,) = _codes(db, 1)
    so = f"{MARKER}-SO-{uuid.uuid4().hex[:6]}".upper()
    book = _inquiry_workbook({"JAN 26": [
        (so, item, 80, date(2026, 1, 20), "TUJU RESIDENCE", ""),
        (so, item, 40, date(2026, 1, 20), "TUJU RESIDENCE", ""),
    ]})

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/order-inquiry/apply",
        {"file": ("inquiry.xlsx", book, _XLSX)},
    )

    job = _job(db, job_id)
    assert job.total_rows == 2
    assert job.processed_rows == 2
    rows = _rows(db, job_id)
    restating = [r for r in rows if r.code == oc.RESTATES_AN_INSTALMENT]
    assert len(restating) == 1, [r.code for r in rows]
    assert restating[0].outcome == oc.OUTCOME_UNCHANGED, "its quantity is in the instalment"
    # Row numbers restart on every tab, so an outcome that names only "row 2" points at one
    # row per sheet in a book of monthly tabs. The identity carries the tab.
    written = next(r for r in rows if r.code == oc.CREATED)
    assert written.identity["sheet"] == "JAN 26"
    # One line for 120, not two lines and not one for 40.
    assert db.execute(text(
        "SELECT sol.qty_ordered FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id WHERE so.so_number = :n"
    ), {"n": so}).scalars().all() == [120]


def test_a_withdrawn_instalment_is_recorded_and_counted_into_the_total(scm_app, monkeypatch):
    """The destructive half of this channel, and the second way processed could exceed total.

    A withdrawal is reached by the sheet's SILENCE, so it carries an outcome and no source
    row. With the sheet's row count as the total the job reports more rows processed than the
    file has, which is how a page comes to show a progress bar past 100%.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    kept, dropped = _codes(db, 2)
    so = f"{MARKER}-SO-{uuid.uuid4().hex[:6]}".upper()
    client = TestClient(app)
    captured = stub_queue(monkeypatch)

    first = _inquiry_workbook({"JAN 26": [
        (so, kept, 10, date(2026, 1, 20), "TUJU RESIDENCE", ""),
        (so, dropped, 5, date(2026, 1, 20), "TUJU RESIDENCE", ""),
    ]})
    client.post("/api/v1/scm/order-inquiry/apply",
                files={"file": ("inquiry.xlsx", first, _XLSX)})
    run_enqueued(captured, db, monkeypatch)

    # The same book with one instalment gone: the feed owns the line, so it withdraws it.
    second = _inquiry_workbook({"JAN 26": [
        (so, kept, 10, date(2026, 1, 20), "TUJU RESIDENCE", ""),
    ]})
    client.post("/api/v1/scm/order-inquiry/apply",
                files={"file": ("inquiry.xlsx", second, _XLSX)})
    run_enqueued(captured, db, monkeypatch)

    job_id = queued_job_id(captured)
    job = _job(db, job_id)
    rows = _rows(db, job_id)
    withdrawn = [r for r in rows if r.code == oc.LINE_WITHDRAWN]
    assert len(withdrawn) == 1, [r.code for r in rows]
    assert withdrawn[0].row_number is None, "a withdrawal is reached by SILENCE - no row"
    assert withdrawn[0].outcome == oc.OUTCOME_UPDATED, "the line WAS written away"
    assert job.total_rows == 2, "1 row in the sheet, plus the instalment it withdrew"
    assert job.processed_rows == job.total_rows, "processed may never exceed the total"
    assert job.result["upload"]["rows"] == 1, "the sheet's own row count is kept"


def test_a_document_another_feed_owns_is_left_alone_and_every_row_says_so(scm_app,
                                                                          monkeypatch):
    """Two feeds, one document: the sheet annotates it and touches no figure on it.

    Recorded per ROW rather than per document, because the job's counts are counts of source
    rows - a document skipped whole means every one of its rows was skipped, and a single
    outcome would leave the rest unaccounted for.
    """
    from app.models.order import SalesOrder

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    (item,) = _codes(db, 1)
    so = f"{MARKER}-SO-{uuid.uuid4().hex[:6]}".upper()
    db.add(SalesOrder(id=str(uuid.uuid4()), so_number=so, status="open",
                      source_system="scm_upload", source_ref="outstanding_so"))
    db.flush()
    book = _inquiry_workbook({"JAN 26": [
        (so, item, 10, date(2026, 1, 20), "TUJU RESIDENCE", ""),
        (so, item, 4, date(2026, 2, 20), "TUJU RESIDENCE", ""),
    ]})

    _c, job_id = _queue_and_run(
        app, db, monkeypatch, "/api/v1/scm/order-inquiry/apply",
        {"file": ("inquiry.xlsx", book, _XLSX)},
    )

    job = _job(db, job_id)
    rows = _rows(db, job_id)
    assert [r.code for r in rows] == [oc.DOCUMENT_OWNED_ELSEWHERE] * 2
    assert job.processed_rows == job.total_rows == 2
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id WHERE so.so_number = :n"
    ), {"n": so}).scalar() == 0, "not one figure on somebody else's document was touched"
