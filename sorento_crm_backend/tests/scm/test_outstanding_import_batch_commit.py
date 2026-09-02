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

from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    MARKER,
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


# --------------------------------------------------------------------------- #
# AC-5.3: batched commit resilience
# --------------------------------------------------------------------------- #

def test_a_failure_partway_through_leaves_earlier_batches_committed(db, monkeypatch):
    """Simulates a worker killed mid-run: `_DOCUMENT_BATCH` is shrunk to 2 documents so a
    6-document file spans three batches, and the third batch's own preload is made to raise.
    The first two batches' `db.commit()` calls already returned by the time that happens, so
    their documents and lines must survive - re-applying the full file afterwards must not
    duplicate them.
    """
    tag = uuid.uuid4().hex[:8].upper()
    items = _seed_products(db, 2, tag)
    docs = [f"{MARKER}-BATCH-KILL-{tag}-{i:02d}" for i in range(6)]

    data = workbook(
        [_open_row(doc, item, 8) for doc in docs for item in items],
        headers=HEADERS,
    )

    monkeypatch.setattr(svc, "_DOCUMENT_BATCH", 2)
    real_preload = svc._preload_closed_lines
    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # the third batch (docs[4:6])
            raise RuntimeError("simulated worker kill")
        return real_preload(*args, **kwargs)

    monkeypatch.setattr(svc, "_preload_closed_lines", _boom)

    with pytest.raises(RuntimeError, match="simulated worker kill"):
        svc.apply(db, data, SO)
    # No `db.rollback()` here: `_boom` raises before touching the database at all, so the
    # session's transaction is not in an aborted state - exactly like production, where
    # `_run_scm_upload_job`'s `except: db.rollback()` only ever discards a batch that never
    # reached its own commit. Calling `rollback()` on this SAVEPOINT-backed test session
    # would undo the earlier batches' ALREADY-RELEASED savepoints too (Postgres SAVEPOINT
    # semantics: released, not durable, until the outer transaction itself commits) - a
    # property of the test harness's isolation trick, not of `apply()`.

    def _line_count(doc: str) -> int:
        return db.execute(text(
            "SELECT count(*) FROM sales_order_lines sol "
            "JOIN sales_orders so ON so.id = sol.sales_order_id "
            "WHERE so.so_number = :n"
        ), {"n": doc}).scalar()

    committed = [doc for doc in docs if _line_count(doc) > 0]
    assert committed == docs[:4], (
        "the first two batches (4 documents) must be committed; the third must not be"
    )
    for doc in docs[4:]:
        assert _line_count(doc) == 0

    # Re-upload the SAME file: the survivor batches read `unchanged`, the lost one is
    # written fresh, and nothing anywhere is duplicated.
    out = svc.apply(db, data, SO)
    assert out["ok"], out

    for doc in docs:
        assert _line_count(doc) == len(items), (
            f"{doc} holds {_line_count(doc)} lines after resume; a duplicate or a gap "
            "means the resume is not idempotent"
        )
