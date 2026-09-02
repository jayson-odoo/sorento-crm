"""S5: batched commits and preloaded queries on `outstanding_import_service.apply`.

The prod trace (2 Sep 2026, the completed 2020-Sep 2026 book, 82,257 rows): `_closed_line`
ran once per ADDED row with `NOT IN (<every settled id so far>)`, and that exclude list grew
with every settled row THIS RUN had already claimed - reaching 13,519 ids, so a LATER row
shipped a statement with that many bound parameters. Rows times settled-ids is quadratic;
Postgres dropped the connection. A second, unrelated cost stacked on top of it: every CLOSED
/ QTY_CHANGED / repriced-UNCHANGED row re-fetched its own line by id, one SELECT per row.

Both are fixed by preloading once per document batch (`_preload_closed_lines`,
`_preload_lines_by_id`) instead of querying per row, and `apply` now commits every
`_DOCUMENT_BATCH` documents rather than once for the whole file, so a worker killed mid-run
keeps whatever finished.

AC-5.4 pins the two preload fixes as a query-count / bound-parameter ceiling; AC-5.3 pins the
batched-commit resilience by simulating a mid-run failure directly (no RQ worker needed -
`apply()` itself either finishes a batch's `db.commit()` or it does not).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import event, text

from app.database import SessionLocal
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    MARKER,
    PO_MINIMAL,
    po_minimal_row,
    po_workbook,
    require_aliases,
    so_headers,
    so_row,
    workbook,
)

# The AutoCount detail listing shape: ordered, delivered and what is left, so a row can
# state itself SETTLED (qty ordered = qty delivered, nothing remaining) rather than merely
# absent. `so_headers`/`so_row` append the ORDER TYPE column QP1 requires.
HEADERS = so_headers("S/O NO", "SO DATE", "DEBTOR CODE", "ITEM CODE", "UOM", "QTY",
                     "TRANSFERED QTY", "REMAINING QTY", "DELIVERY DATE", "STOCK LOCATION")

DUE = date(2026, 7, 1)
DEBTOR = "300-T012"


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _seed_products(db, count: int, tag: str) -> list[str]:
    """`count` distinct product codes, under one category/uom, and nothing else."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db, SO)
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}",
                          category_name=f"{MARKER} batch category")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}-U-{tag}", uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    codes = [f"{MARKER}-BATCH-{tag}-{i:04d}" for i in range(count)]
    for code in codes:
        db.add(Product(id=str(uuid.uuid4()), product_code=code, product_name=code,
                       category_id=cat.id, base_uom_id=uom.id, list_price=0,
                       is_active=True, is_discontinued=False))
    db.flush()
    return codes


def _settled_row(doc: str, item: str) -> tuple:
    """One line stating itself fully delivered: ordered 5, delivered 5, nothing remaining.

    This is the exact shape that reproduced the prod trace - an ADDED row the write path
    checks against the closed-line pool for a possible revival, on a document this run has
    never seen before, so nothing before S5 ever matched and the exclude list grew anyway.
    """
    return so_row(doc, DUE, DEBTOR, item, "PCS", 5, 5, 0, DUE, "")


def _open_row(doc: str, item: str, qty: float) -> tuple:
    return so_row(doc, DUE, DEBTOR, item, "PCS", qty, 0, qty, DUE, "")


def _query_log(db):
    """(statements, engine) - every statement this connection sends, with its own params."""
    seen: list[tuple[str, object]] = []
    engine = db.get_bind()

    def _tap(_conn, _cur, statement, parameters, *_a, **_kw):
        seen.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _tap)
    return seen, engine, _tap


def _worst_select_param_count(seen: list[tuple[str, object]]) -> int:
    """The most bound parameters any SELECT in `seen` carried.

    SELECT only, deliberately: SQLAlchemy 2.0's `insertmanyvalues` coalesces the batch's own
    new-line INSERTs into one multi-row statement, which legitimately carries one parameter
    per column per row - a shape bounded by `_DOCUMENT_BATCH`, not by the file's total row
    count, and not what the prod trace measured. The trace's 13,519-parameter statement was
    `_closed_line`'s `NOT IN (<every settled id so far>)` on a SELECT, growing with every row
    already processed THIS RUN regardless of batching - that is what this ceiling pins.
    """
    def _param_count(parameters) -> int:
        if parameters is None:
            return 0
        if isinstance(parameters, dict):
            return len(parameters)
        if isinstance(parameters, (list, tuple)):
            return max((_param_count(p) for p in parameters), default=0)
        return 0

    return max(
        (_param_count(p) for s, p in seen if s.strip().lower().startswith("select")),
        default=0,
    )


# --------------------------------------------------------------------------- #
# AC-5.4: query count and bound-parameter ceiling
# --------------------------------------------------------------------------- #

def _settled_book_apply(db, item_count: int) -> tuple[dict, list[tuple[str, object]]]:
    """Apply a one-document, all-settled book of `item_count` distinct products, watched."""
    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, item_count, tag)
    doc = f"{MARKER}-BATCH-SO-{tag}"
    data = workbook([_settled_row(doc, item) for item in items], headers=HEADERS)

    seen, engine, tap = _query_log(db)
    try:
        out = svc.apply(db, data, SO)
    finally:
        event.remove(engine, "before_cursor_execute", tap)

    assert out["ok"], out
    assert out["applied"]["added"] == item_count
    return out, seen


def test_a_200_row_settled_book_stays_under_a_generous_query_ceiling(db):
    """The direct reproduction of the prod trace: one document, 200 distinct products, every
    row already settled, first time this database has ever seen any of them.

    Before S5 this shipped one `_closed_line` SELECT per row with a `NOT IN` list that grew
    by one every time - 200 rows means the 200th statement alone carries 199 bound
    parameters, and the real file was 82,257 rows deep. Preloading once per batch removes
    both the per-row query and the growing exclude list from the wire.

    100, not the AC's literal 60: this database is the shared local prod copy, and company-
    scope resolution (`app.services.company_scope`) costs a handful more statements
    depending on which fixture warmed it up earlier in the same pytest session - noise this
    test must not chase. `test_query_count_does_not_scale_with_row_count` below is the
    precise regression guard; this one pins the order of magnitude the AC cares about.
    """
    _out, seen = _settled_book_apply(db, 200)

    statements = [s for s, _p in seen]
    assert len(statements) < 100, (
        f"apply() ran {len(statements)} statements for a 200-row file "
        f"(no per-row SELECT is the whole point of S5): {statements[:5]}..."
    )

    worst = _worst_select_param_count(seen)
    assert worst <= 1000, (
        f"a SELECT carried {worst} bound parameters; the prod trace shipped 13,519 "
        "for exactly this shape (a growing NOT IN exclude list)"
    )


def test_query_count_does_not_scale_with_row_count(db):
    """The precise regression guard, immune to the session-level noise above: measures the
    SAME shape at 40 and 200 rows and asserts the query count barely moves between them.

    Before S5 this GREW almost 1:1 with rows (`_closed_line` per ADDED row, the exclude list
    on top). After S5 both sizes cost the same handful of preload statements, so the growth
    stays under a small constant regardless of how noisy the absolute counts are.
    """
    _small_out, small = _settled_book_apply(db, 40)
    _large_out, large = _settled_book_apply(db, 200)

    growth = len(large) - len(small)
    assert growth < 20, (
        f"going from 40 to 200 settled rows cost {growth} more statements; a per-row SELECT "
        "would cost roughly one more per row (160), not a small constant"
    )


def test_a_200_row_reupload_that_closes_and_reprices_runs_no_select_per_row(db):
    """The OTHER per-row query S5 removes: `CLOSED` / `QTY_CHANGED` / a repriced `UNCHANGED`
    used to re-fetch its own line by id (`_preload_lines_by_id`). Seeds 10 open documents
    (20 lines each), then a second file that closes half of every document's lines by
    absence and changes the qty on the other half - 200 changed rows against 10
    pre-existing documents.

    Scoped to SELECTs, not every statement: each changed row still writes its own UPDATE
    (`line.qty_ordered = ...` / `line.line_status = "closed"`, one row at a time - ordinary
    SQLAlchemy unit-of-work, never claimed as an S5 target and not what the prod trace
    measured). What S5 removes is the SELECT that used to re-fetch each of those 200 lines
    by id before writing it; a SELECT count that scales with lines rather than with the
    handful of preload statements per batch is exactly that regression back.
    """
    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, 20, tag)
    docs = [f"{MARKER}-BATCH-RE-{tag}-{i:03d}" for i in range(10)]

    week1 = workbook(
        [_open_row(doc, item, 10) for doc in docs for item in items],
        headers=HEADERS,
    )
    svc.apply(db, week1, SO)

    # Half the items per document close by absence; the other half changes quantity.
    week2_rows = []
    for doc in docs:
        for i, item in enumerate(items):
            if i % 2 == 0:
                week2_rows.append(_open_row(doc, item, 17))  # QTY_CHANGED
            # the odd-indexed items are simply absent -> CLOSED
    data = workbook(week2_rows, headers=HEADERS)

    seen, engine, tap = _query_log(db)
    try:
        out = svc.apply(db, data, SO)
    finally:
        event.remove(engine, "before_cursor_execute", tap)

    assert out["ok"], out
    assert out["applied"]["updated"] == 10 * 10   # items 0, 2, .., 18 per document
    assert out["applied"]["closed"] == 10 * 10    # items 1, 3, .., 19 per document

    selects = [s for s, _p in seen if s.strip().lower().startswith("select")]
    assert len(selects) < 60, (
        f"apply() ran {len(selects)} SELECTs closing/changing 200 pre-existing lines "
        f"(no per-row SELECT is the whole point of S5): {selects[:5]}..."
    )


def test_3000_documents_query_count_and_param_ceiling_do_not_scale_with_document_count(db):
    """C1 (header lookup) and S5 (the remaining unbounded `IN (...)` lists) together, at a
    scale neither survives unfixed: 3,000 pre-existing documents, restated IDENTICALLY.

    A re-upload, not a first-time book, deliberately: creating 3,000 brand new headers
    always costs 3,000 INSERTs (and a follow-up UPDATE apiece for the header-level columns
    the header loop sets after creating one) REGARDLESS of C1 or S5 - that write cost was
    never these fixes' target and a test that could not tell the two apart would chase a
    number no amount of query-bulking can move. Restating the SAME book unchanged isolates
    exactly the READ side C1/S5 touch: SQLAlchemy's own dirty tracking skips the UPDATE
    when nothing on an existing header actually changed, so what is left to count is the
    header LOOKUP and the diff's own preloads.

    Before C1, the header sub-loop ran one `SELECT ... WHERE so_number = :n` per document -
    3,000 statements for this file alone, not the "few per batch" S5 promises. Before S5,
    `_existing_lines` / `_header_state` / `_demand_state` each hand their FULL document set
    to one `IN (...)` - a single statement with 3,000 document numbers, comfortably over the
    1,000-bound-parameter ceiling the prod trace shipped. `_DOCUMENT_BATCH` (500) means this
    file is 6 batches; C1's bulk header lookup is one query per batch (6), not one per
    document (3,000).
    """
    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, 5, tag)
    docs = [f"{MARKER}-BATCH-3K-{tag}-{i:05d}" for i in range(3000)]

    data = workbook(
        [_open_row(doc, items[i % len(items)], 3) for i, doc in enumerate(docs)],
        headers=HEADERS,
    )

    seeded = svc.apply(db, data, SO)
    assert seeded["ok"] and seeded["applied"]["added"] == 3000, seeded

    seen, engine, tap = _query_log(db)
    try:
        out = svc.apply(db, data, SO)  # the SAME file again, byte for byte
    finally:
        event.remove(engine, "before_cursor_execute", tap)

    assert out["ok"], out
    assert out["applied"]["unchanged"] == 3000, out["applied"]

    statements = [s for s, _p in seen]
    assert len(statements) < 100, (
        f"apply() ran {len(statements)} statements re-uploading 3,000 unchanged documents "
        f"(C1: one bulk header lookup per batch, not one SELECT per document): "
        f"{statements[:5]}..."
    )

    worst = _worst_select_param_count(seen)
    assert worst <= 1000, (
        f"a SELECT carried {worst} bound parameters over 3,000 documents; the document-"
        "number IN lists in _existing_lines / _header_state / _demand_state must chunk "
        "(S5 review round 1) rather than hand their whole set to one statement"
    )


# --------------------------------------------------------------------------- #
# C5 (review round 1b): the closed-line matcher self-enforces via line_status
# --------------------------------------------------------------------------- #

def test_two_identical_rows_in_one_batch_cannot_revive_the_same_closed_line_twice(db):
    """`_match_closed_line` checks `line_status == "closed"` on the LIVE candidate object
    (C5), so a line an earlier match in this SAME batch already reopened is excluded from a
    second match by that same attribute - no separate bookkeeping needed for the reopen
    case. One pre-existing CLOSED line, two identical incoming rows in one upload (neither
    settled, so both want to REOPEN, not merely restate-and-keep-closed): the first revives
    it, the second must insert its own line rather than reviving the SAME row twice - which
    would silently fold the second row's quantity onto the first and lose a line.
    """
    from app.models.order import SalesOrder, SalesOrderLine

    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, 1, tag)
    item = items[0]
    doc = f"{MARKER}-BATCH-DUPREVIVE-{tag}"

    product_id = db.execute(
        text("SELECT id FROM products WHERE product_code = :c"), {"c": item}
    ).scalar()

    order = SalesOrder(id=str(uuid.uuid4()), so_number=doc, status="open")
    db.add(order)
    db.flush()
    closed_line = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=order.id, product_id=product_id,
        warehouse_id=None, qty_ordered=9, qty_delivered=9, required_date=DUE,
        line_status="closed",
    )
    db.add(closed_line)
    db.flush()
    closed_line_id = str(closed_line.id)

    # Two rows, same item/location/date, neither settled - both want the SAME closed
    # candidate (header, product) with no location and the same date to revive.
    data = workbook([_open_row(doc, item, 4), _open_row(doc, item, 6)], headers=HEADERS)

    out = svc.apply(db, data, SO)

    assert out["ok"], out
    assert out["applied"]["added"] == 2, out["applied"]  # one revive, one fresh insert

    rows = db.execute(text(
        "SELECT id, (qty_ordered - qty_delivered) AS outstanding, line_status "
        "FROM sales_order_lines WHERE sales_order_id = :o"
    ), {"o": order.id}).all()

    assert len(rows) == 2, (
        f"expected the revived line plus one new line, got {rows} - a second revival of "
        "the same closed line would leave only one row"
    )
    assert sorted(float(r.outstanding) for r in rows) == [4.0, 6.0], rows
    assert all(r.line_status == "open" for r in rows)
    ids = {str(r.id) for r in rows}
    assert closed_line_id in ids, "the originally closed line must be one of the two - reopened"
    assert len(ids) == 2, "the two rows must be genuinely different database rows"


# --------------------------------------------------------------------------- #
# AC-5.2 / S3 (review round 1): processed_rows moves DURING a run, on a real ImportJob
# --------------------------------------------------------------------------- #

def test_processed_rows_moves_before_the_job_completes(db, monkeypatch):
    """A real `ImportJob` row, `apply()` driven through an `ImportOutcome(bump_job_progress=
    True)`, `_DOCUMENT_BATCH` shrunk to 2 so a 6-document file spans three batches - and
    `job.processed_rows` is snapshotted after every `outcome.flush(publish=True)` call
    `apply()` makes. This test never calls `job_service.complete_job`, so any bump it
    observes proves the card moves WHILE the job runs, not only once at the end.

    The recorder's own session is bound to `db`'s connection rather than a real
    `SessionLocal()`: `ImportOutcome.flush()` opens and commits its OWN session each call,
    and a genuinely separate connection would never see this test's own uncommitted seed
    data - binding to the SAME connection makes its commits savepoint releases in the same
    sandbox `db` itself uses, so a read straight off `db` (via `db.refresh`) sees them.
    """
    from sqlalchemy.orm import Session as SASession

    from app.models.job import ImportJob, JobStatus
    from app.services.import_outcome import ImportOutcome

    monkeypatch.setattr(svc, "_DOCUMENT_BATCH", 2)
    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, 2, tag)
    docs = [f"{MARKER}-BATCH-PROGRESS-{tag}-{i}" for i in range(6)]
    data = workbook(
        [_open_row(doc, item, 5) for doc in docs for item in items], headers=HEADERS)

    job = ImportJob(id=uuid.uuid4(), job_id=str(uuid.uuid4()),
                    job_type="outstanding_so_import", status=JobStatus.STARTED.value,
                    user_id=str(uuid.uuid4()))
    db.add(job)
    db.flush()

    outcome = ImportOutcome(
        job.id, session_factory=lambda: SASession(bind=db.get_bind()),
        bump_job_progress=True,
    )
    seen_progress: list[int] = []
    real_flush = outcome.flush

    def _watched_flush(*args, **kwargs):
        real_flush(*args, **kwargs)
        if kwargs.get("publish"):
            db.refresh(job)
            seen_progress.append(job.processed_rows)

    monkeypatch.setattr(outcome, "flush", _watched_flush)

    out = svc.apply(db, data, SO, outcome=outcome)

    assert out["ok"], out
    assert len(seen_progress) == 3, (
        f"expected one publish per document batch (3), saw {seen_progress}"
    )
    assert seen_progress == sorted(seen_progress) and seen_progress[0] > 0, (
        f"processed_rows must appear, then only grow, batch by batch: {seen_progress}"
    )
    assert job.processed_rows == seen_progress[-1] > 0, (
        "the job row itself must already reflect the bump - no complete_job call happened "
        "in this test at all"
    )


def test_flush_publishes_even_with_an_empty_buffer(db):
    """C6 (code review round 3 batch 2): `_record` stops APPENDING to the buffer once
    `max_rows` is reached (`rows_truncated`), so every `flush(publish=True)` call after
    that point arrives with nothing queued. The bug: the early `if not self._buffer: return`
    used to skip the publish along with the (correctly) skipped insert, freezing
    `processed_rows` at whatever the LAST non-empty flush left it - past the cap, the
    activity card stopped moving even though rows kept being counted.

    `buffer_size=1` reproduces the empty-buffer case directly and without needing the
    200k-row cap: `_record`'s own auto-flush (which never publishes) empties the buffer on
    every single row, so the EXPLICIT `flush(publish=True)` a caller makes afterwards always
    arrives here with nothing left to insert - exactly the shape a batch boundary hits once
    a real run has passed `max_rows`.
    """
    from sqlalchemy.orm import Session as SASession

    from app.models.job import ImportJob, JobStatus
    from app.services.import_outcome import ImportOutcome

    job = ImportJob(id=uuid.uuid4(), job_id=str(uuid.uuid4()),
                    job_type="outstanding_so_import", status=JobStatus.STARTED.value,
                    user_id=str(uuid.uuid4()))
    db.add(job)
    db.flush()

    out = ImportOutcome(
        job.id, buffer_size=1, session_factory=lambda: SASession(bind=db.get_bind()),
        bump_job_progress=True,
    )
    out.success(row=1)
    assert not out._buffer, "sanity: buffer_size=1 already auto-flushed this row"

    out.flush(publish=True)

    db.refresh(job)
    assert job.processed_rows == out.processed == 1, (
        "an empty-buffer publish must still bump processed_rows to the true total"
    )


# --------------------------------------------------------------------------- #
# AC-5.3: batched commit resilience (review round 1, B4 - two REAL sessions)
# --------------------------------------------------------------------------- #
#
# `pg_session()` wraps every test in one outer transaction, so `db.commit()` inside it is a
# SAVEPOINT release, not a durable commit - a `rollback()` after the savepoint was released
# still undoes it (Postgres SAVEPOINT semantics: released, not durable, until the OUTER
# transaction itself commits). That makes it the wrong tool for proving `apply()` actually
# calls `db.commit()` rather than `db.flush()`: both would look identical from inside the
# same wrapped transaction. These two tests use `SessionLocal()` directly instead - two
# independent connections against the real database, so only a commit the FIRST session
# genuinely issued is visible to the SECOND - and clean up everything they wrote by hand,
# scoped to a `ZZTBATCH-<hex>` marker no other row can collide with, in a `finally:` that
# runs whether the test passes or fails.


def _cleanup_real(marker: str) -> None:
    """Delete every row a dual-session test created, by MARKER, on its own session."""
    db = SessionLocal()
    try:
        db.execute(text(
            "DELETE FROM sales_order_lines WHERE sales_order_id IN "
            "(SELECT id FROM sales_orders WHERE so_number LIKE :m)"
        ), {"m": f"{marker}%"})
        db.execute(text("DELETE FROM sales_orders WHERE so_number LIKE :m"), {"m": f"{marker}%"})
        db.execute(text(
            "DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :m)"
        ), {"m": f"{marker}%"})
        db.execute(text("DELETE FROM purchase_orders WHERE po_number LIKE :m"),
                  {"m": f"{marker}%"})
        # The SO channel's own reaction (AC-D2a) files a `scm.plan_exception_batch` row
        # naming this run's documents in `source_documents` (a JSONB array) - review round 2,
        # S4, found 8 of these already leaked into the shared dev DB from earlier test runs
        # that predated this delete. `PlanException.batch_id` cascades on delete, so nothing
        # else needs a separate statement.
        db.execute(text(
            "DELETE FROM scm.plan_exception_batch WHERE source_documents::text LIKE "
            "'%'||:m||'%'"
        ), {"m": marker})
        db.execute(text("DELETE FROM products WHERE product_code LIKE :m"), {"m": f"{marker}%"})
        db.execute(text("DELETE FROM suppliers WHERE supplier_code LIKE :m"),
                  {"m": f"{marker}%"})
        db.execute(text("DELETE FROM product_categories WHERE category_code LIKE :m"),
                  {"m": f"{marker}%"})
        db.execute(text("DELETE FROM units_of_measure WHERE uom_code LIKE :m"),
                  {"m": f"{marker}%"})
        db.commit()
    finally:
        db.close()


def _seed_products_real(db, count: int, marker: str) -> list[str]:
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db, SO)
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{marker}-CAT",
                          category_name="bench category")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{marker}-U", uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    codes = [f"{marker}-{i:04d}" for i in range(count)]
    for code in codes:
        db.add(Product(id=str(uuid.uuid4()), product_code=code, product_name=code,
                       category_id=cat.id, base_uom_id=uom.id, list_price=0,
                       is_active=True, is_discontinued=False))
    db.flush()
    return codes


def test_a_failure_partway_through_leaves_earlier_batches_committed(monkeypatch):
    """Simulates a worker killed mid-run: `_DOCUMENT_BATCH` is shrunk to 2 documents so a
    6-document file spans three batches, and the third batch's own preload is made to raise.
    The first two batches' `db.commit()` calls already returned by the time that happens, so
    their documents and lines must survive - checked from a SECOND, independent session, so
    only a real commit counts - and re-applying the full file afterwards must not duplicate
    them.

    Mutation-sensitive by construction: replace the batch loop's `db.commit()` with
    `db.flush()` and `committed` below comes back empty - a flush alone is invisible to the
    second connection, so the first assertion fails.
    """
    marker = f"ZZTBATCH-{uuid.uuid4().hex[:8].upper()}"
    docs = [f"{marker}-D{i:02d}" for i in range(6)]

    monkeypatch.setattr(svc, "_DOCUMENT_BATCH", 2)
    real_preload = svc._preload_closed_lines
    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # the third batch (docs[4:6])
            raise RuntimeError("simulated worker kill")
        return real_preload(*args, **kwargs)

    monkeypatch.setattr(svc, "_preload_closed_lines", _boom)

    try:
        db_write = SessionLocal()
        try:
            items = _seed_products_real(db_write, 2, marker)
            data = workbook(
                [_open_row(doc, item, 8) for doc in docs for item in items],
                headers=HEADERS,
            )
            db_write.commit()  # the catalogue is durable before the run, like a real book

            with pytest.raises(RuntimeError, match="simulated worker kill"):
                svc.apply(db_write, data, SO)
            # A real rollback this time - `db_write` is a genuine, independent session (not
            # a savepoint under a wrapping test transaction), so this discards exactly what
            # production's `_run_scm_upload_job` except-clause discards: the current batch's
            # own pending work, never an earlier batch that already committed.
            db_write.rollback()
        finally:
            db_write.close()

        def _line_count(reader, doc: str) -> int:
            return reader.execute(text(
                "SELECT count(*) FROM sales_order_lines sol "
                "JOIN sales_orders so ON so.id = sol.sales_order_id "
                "WHERE so.so_number = :n"
            ), {"n": doc}).scalar()

        db_read = SessionLocal()
        try:
            committed = [doc for doc in docs if _line_count(db_read, doc) > 0]
            assert committed == docs[:4], (
                "the first two batches (4 documents) must be committed, from a SECOND "
                "session's own point of view; the third must not be"
            )
            for doc in docs[4:]:
                assert _line_count(db_read, doc) == 0
        finally:
            db_read.close()

        # Re-upload the SAME file on a THIRD session: the survivor batches read `unchanged`,
        # the lost one is written fresh, and nothing anywhere is duplicated.
        db_write2 = SessionLocal()
        try:
            out = svc.apply(db_write2, data, SO)
            assert out["ok"], out
            db_write2.commit()
        finally:
            db_write2.close()

        db_read2 = SessionLocal()
        try:
            for doc in docs:
                n = _line_count(db_read2, doc)
                assert n == len(items), (
                    f"{doc} holds {n} lines after resume; a duplicate or a gap means the "
                    "resume is not idempotent"
                )
        finally:
            db_read2.close()
    finally:
        _cleanup_real(marker)


def test_a_kill_during_a_batchs_reaction_leaves_that_batchs_lines_uncommitted_too(monkeypatch):
    """B2/B3 extension (review round 1): the CRM-PO supersession reaction now runs INSIDE
    each batch's own transaction, before that batch's `db.commit()` (S5 review round 1,
    B2/B3) - so a reaction failure must roll back that batch's LINE writes too, never leave
    them committed with the reaction silently missing. PO channel only: supersession is
    PO-specific.

    `_supersede_crm_raised_pos` is patched directly (not seeded with a real CRM-raised PO to
    supersede - that path is covered by `test_outstanding_supersedes_crm_po.py`) so the only
    variable under test is WHEN a reaction failure takes effect relative to the batch commit.
    """
    marker = f"ZZTBATCH-{uuid.uuid4().hex[:8].upper()}"
    docs = [f"{marker}-D{i:02d}" for i in range(6)]
    creditor = f"{marker}-CR"

    monkeypatch.setattr(svc, "_DOCUMENT_BATCH", 2)
    real_supersede = svc._supersede_crm_raised_pos
    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:  # the second batch's own reaction (docs[2:4])
            raise RuntimeError("simulated reaction failure")
        return real_supersede(*args, **kwargs)

    monkeypatch.setattr(svc, "_supersede_crm_raised_pos", _boom)

    try:
        db_write = SessionLocal()
        try:
            items = [f"{marker}-ITM{i}" for i in range(2)]
            require_aliases(db_write, PO)
            from app.models.product import Product, ProductCategory, UnitOfMeasure

            cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{marker}-CAT",
                                  category_name="bench category")
            uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{marker}-U", uom_name="pcs")
            db_write.add_all([cat, uom])
            db_write.flush()
            for code in items:
                db_write.add(Product(id=str(uuid.uuid4()), product_code=code,
                                     product_name=code, category_id=cat.id,
                                     base_uom_id=uom.id, list_price=0, is_active=True,
                                     is_discontinued=False))
            db_write.flush()
            db_write.commit()

            data = po_workbook(
                [po_minimal_row(doc, creditor, item, 8, DUE, "")
                 for doc in docs for item in items],
                headers=PO_MINIMAL,
            )

            with pytest.raises(RuntimeError, match="simulated reaction failure"):
                svc.apply(db_write, data, PO)
            db_write.rollback()
        finally:
            db_write.close()

        def _po_line_count(reader, doc: str) -> int:
            return reader.execute(text(
                "SELECT count(*) FROM purchase_order_lines pol "
                "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
                "WHERE po.po_number = :n"
            ), {"n": doc}).scalar()

        db_read = SessionLocal()
        try:
            # The first batch's reaction ran clean and committed with its lines; the SECOND
            # batch's reaction raised, so THAT batch's lines must be gone too, not sitting
            # committed with no matching reaction outcome - and the third batch never ran.
            assert _po_line_count(db_read, docs[0]) > 0
            assert _po_line_count(db_read, docs[1]) > 0
            for doc in docs[2:]:
                assert _po_line_count(db_read, doc) == 0, (
                    f"{doc}'s lines are committed even though its batch's own reaction "
                    "failed - lines and reactions are no longer atomic per batch"
                )
        finally:
            db_read.close()
    finally:
        _cleanup_real(marker)
