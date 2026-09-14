"""S3 (PLAN-low-stock-report.md, low-stock-report-acceptance-criteria.md AC-30..AC-37,
issue #890) - the two-sheet low stock workbook and its export kind.

The client's own `Stock Balance 28 Aug 2026.xls` is two sheets per category: a "- Low"
sheet listing what is below its reorder level, and the full sheet beside it. Owner ruling
14 Sep: ONE workbook per run with exactly those two sheets, "Low stock" and "All", sixteen
columns on both, bounded by a reorder run so the Suggested qty comes from the engine.

WRITTEN BEFORE THE IMPLEMENTATION EXISTS (Phase 2 is test-first). Nothing below was read
off code: the module (`app/services/scm/low_stock_report_service.py`), its two constants,
its one function, the task and the route's third `format` value are all named by the plan.

Every import of a not-yet-existing name is made INSIDE the test (`_lsr()`, `_task()`), not
at module top: a top-level `from app.services.scm import low_stock_report_service` would
fail COLLECTION and take the whole file down with one error, hiding the other nine
failures. This way the file collects and each test fails on its own missing behaviour.

Seeding is direct `OrderSummaryRow` inserts rather than a real run: this slice is about
which frozen rows reach which sheet and what the master-data joins print, and hand-built
rows are the only way to put a product exactly AT its level, exactly one above it, and at
a NULL level in the same run. The engine's own arithmetic has its coverage elsewhere
(`test_reorder_committed_universe.py`, `test_order_summary_sheet.py`).

Postgres only, marker-prefixed, rolled back at teardown. Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import summary_order_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, seed_user
from tests.scm.test_m3_run import _client
from tests.scm.test_order_sheet_export_downloads import (  # noqa: F401
    _NoCloseSession,
    _savepoint_session,
    _seed_run,
)
from tests.scm.test_product_grain_summary import db  # noqa: F401

pytestmark = requires_pg

MARKER = "ZZTLSR"

#: The sixteen columns, in order, spelled out here rather than read off the module under
#: test (AC-31) - a test that asserts `LOW_STOCK_COLUMNS == LOW_STOCK_COLUMNS` pins
#: nothing. "Description" and "Category" lead because that is the order the client's own
#: sheet runs in; "Reorder qty" sits beside "Reorder level" for the same reason.
_EXPECTED_COLUMNS = (
    "Item code", "Description", "Category", "BRW on hand", "Reorder level",
    "Reorder qty", "Suggested qty", "Suggestion", "Order qty", "Dealer o/s",
    "Supplier", "BRW PO qty", "BRW incoming qty", "Last in qty", "Last in date",
    "Remarks",
)

_SUPPLIER_COLUMN = _EXPECTED_COLUMNS.index("Supplier")

_AS_OF = date(2026, 9, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".upper()


def _lsr():
    """The module the plan names: `app/services/scm/low_stock_report_service.py`.

    A sibling module, NOT more lines in the 3,085-line `summary_order_service.py`.
    Imported here, per test, so a missing module is one red test rather than a collection
    error that hides every other test in this file.
    """
    from app.services.scm import low_stock_report_service

    return low_stock_report_service


def _task():
    """`app.tasks.export_tasks.generate_low_stock_report` - fetched by name so its absence
    is an explicit, readable failure rather than an ImportError at collection."""
    from app.tasks import export_tasks

    fn = getattr(export_tasks, "generate_low_stock_report", None)
    assert fn is not None, (
        "app.tasks.export_tasks.generate_low_stock_report does not exist yet (AC-36)"
    )
    return export_tasks, fn


def _product(db, *, stem, description=None, category_code=None, reorder_quantity=None):
    """One product with its own category and uom - the three master-data facts the
    workbook joins at export time (AC-34) set explicitly, including the ones that must
    print BLANK.

    A NAMED `category_code` is looked up first: `product_categories.category_code` is
    unique, and the sort test deliberately puts two products in ONE category, so a
    blind insert of a second row with the same code is a constraint violation, not a
    second category.
    """
    code = (category_code or _code("CAT"))[:40]
    cat = (
        db.query(ProductCategory)
        .filter(ProductCategory.category_code == code)
        .one_or_none()
    )
    if cat is None:
        cat = ProductCategory(
            id=_u(), category_code=code, category_name=f"{MARKER} category",
        )
        db.add(cat)
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} uom")
    db.add(uom)
    db.flush()
    product = Product(
        id=_u(), product_code=_code(stem), product_name=f"{MARKER} {stem} product",
        description=description, category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False, reorder_quantity=reorder_quantity,
    )
    db.add(product)
    db.flush()
    return product


def _run(db, *, company_id=None) -> ReorderRun:
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        source_system="scm", source_ref=_code("RUN"),
        decision_grain="product", front_planning_contract_version=1,
    )
    if company_id:
        run.company_id = company_id
    db.add(run)
    db.flush()
    return run


def _summary_row(db, run, product, *, pool_on_hand, reorder_level,
                 suggested_qty=0, supplier_name=None, as_of=_AS_OF) -> OrderSummaryRow:
    """One frozen book row. `pool_on_hand` / `reorder_level` are the two figures the Low
    sheet's membership rule reads, and both are deliberately settable to None - a run
    frozen before migration 504 carries a NULL `pool_on_hand`, and a product nobody has
    set a level for carries a NULL `reorder_level`."""
    row = OrderSummaryRow(
        id=_u(), run_id=run.id, product_id=product.id, as_of=as_of,
        # NOT NULL with no server default - `write_rows` always stamps it, so a
        # hand-built row has to as well or the insert dies before the test starts.
        computed_at=datetime(2026, 9, 10, 6, 0, 0),
        pool_on_hand=pool_on_hand, reorder_level=reorder_level,
        suggested_qty=suggested_qty, supplier_name=supplier_name,
    )
    db.add(row)
    db.flush()
    return row


def _hide(db, run, product) -> None:
    """Mark the product hidden-by-default on this run, the way the list and the Decisions
    tile read it (`hidden_by_default` on the PRODUCT-grain rec, `warehouse_id IS NULL`).
    The order sheet export drops these rows; the low stock workbook must not (AC-32/33)."""
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="covered", product_id=product.id,
        warehouse_id=None, status="proposed", hidden_by_default=True,
    ))
    db.flush()


def _sheets(blob: bytes):
    from openpyxl import load_workbook

    return load_workbook(BytesIO(blob))


def _rows_of(ws) -> list[tuple]:
    """Data rows only, header excluded."""
    return [tuple(c.value for c in row) for row in ws.iter_rows(min_row=2)]


def _codes_of(ws) -> list:
    return [r[0] for r in _rows_of(ws)]


# =========================================================================== #
# AC-30: the route learns a third format
# =========================================================================== #

def test_export_route_accepts_low_stock_xlsx_and_enqueues(scm_app, monkeypatch):
    """AC-30: `POST /api/v1/scm/order-summary/export` takes `format: "low_stock_xlsx"`
    beside `pdf` and `xlsx` - the SAME endpoint, because the buyer's click is the same
    kind of act and the My Downloads pipeline is already there (AC-2 has the frontend
    posting to it). It creates a `user_downloads` row of kind `low_stock_xlsx`, named
    `low-stock-<as_of ddmmyyyy>.xlsx`, pointed at the run, and enqueues
    `generate_low_stock_report(download_id, run_id, user_id)` on `imports` with the
    600 s timeout the order sheet uses.

    RED today: the route's guard is `if fmt not in ("pdf", "xlsx")`, so this is a 422.
    """
    from app.services import queue_service

    _export_tasks, task_fn = _task()
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    _summary_row(db, run, _product(db, stem="ROUTE"), pool_on_hand=40, reorder_level=100)
    db.flush()

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})
        return type("J", (), {"id": "fake-job-id"})()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "low_stock_xlsx"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "low_stock_xlsx", body

    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id, "
        "       filename, user_id FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "low_stock_xlsx"
    assert row["source_entity_type"] == "reorder_run"
    assert row["source_entity_id"] == run_id
    assert row["filename"] == "low-stock-10092026.xlsx", (
        f"the file is named for the run's as_of, not today: {row['filename']}"
    )

    assert len(calls) == 1, f"expected exactly one enqueue, got {calls}"
    call = calls[0]
    assert call["func"] is task_fn, call["func"]
    assert call["args"][:3] == (body["id"], run_id, row["user_id"]), call["args"]
    assert call["kwargs"]["queue_name"] == "imports", call["kwargs"]
    assert call["kwargs"]["job_timeout"] == 600, call["kwargs"]


def test_export_route_409_while_low_stock_in_flight(scm_app, monkeypatch):
    """AC-30: one in flight per user per run per kind, the same rule the order sheet
    already applies per format - and per KIND means an in-flight order sheet must NOT
    block a low stock report for the same run. They are different documents; a buyer who
    asked for both should get both.

    RED today: the first low_stock_xlsx POST is a 422, so there is nothing in flight.
    """
    from app.services import queue_service

    _task()
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    _summary_row(db, run, _product(db, stem="FLIGHT"), pool_on_hand=40, reorder_level=100)
    db.flush()

    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        sheet = c.post("/api/v1/scm/order-summary/export",
                       json={"run_id": run_id, "format": "xlsx"})
        assert sheet.status_code == 200, sheet.text

        first = c.post("/api/v1/scm/order-summary/export",
                       json={"run_id": run_id, "format": "low_stock_xlsx"})
        second = c.post("/api/v1/scm/order-summary/export",
                        json={"run_id": run_id, "format": "low_stock_xlsx"})

    assert first.status_code == 200, (
        f"a pending order sheet must not block the low stock report: {first.text}"
    )
    assert second.status_code == 409, second.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads "
        "WHERE source_entity_id = :r AND kind = 'low_stock_xlsx'"
    ), {"r": run_id}).scalar()
    assert count == 1, f"the guard let a second low stock row through: {count}"


# =========================================================================== #
# AC-31: the workbook's shape
# =========================================================================== #

def test_workbook_has_two_sheets_in_order_with_16_columns(db):
    """AC-31: exactly two sheets, "Low stock" FIRST (so `wb.active` is the sheet a buyer
    opens the file for, and so existing `wb.active` readers keep working), then "All".
    The same sixteen columns on both, in the client's own order. Header frozen at A2 and
    styled like the order sheet's - dark fill, bold white text - because this is the same
    document family, not a second visual language.
    """
    lsr = _lsr()
    run = _run(db)
    _summary_row(db, run, _product(db, stem="SHAPE"), pool_on_hand=40, reorder_level=100)

    blob, content_type, filename = lsr.export_low_stock(db, run_id=str(run.id))

    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert filename == "low-stock-10092026.xlsx", filename

    wb = _sheets(blob)
    assert wb.sheetnames == ["Low stock", "All"], wb.sheetnames
    assert tuple(lsr.LOW_STOCK_COLUMNS) == _EXPECTED_COLUMNS

    for name in ("Low stock", "All"):
        ws = wb[name]
        header = tuple(c.value for c in ws[1])
        assert header == _EXPECTED_COLUMNS, f"{name} header: {header}"
        assert ws.freeze_panes == "A2", f"{name} is not frozen at A2"
        assert ws["A1"].fill.fgColor.rgb == "FF404040", f"{name} header is not styled"


# =========================================================================== #
# AC-32: which rows the Low sheet holds
# =========================================================================== #

def test_low_sheet_membership(db):
    """AC-32: a row is LOW when both figures are known and on hand is strictly below the
    level. The client's own rule, applied to the raw pool figure - not to a net, and not
    to anything the engine decided.

    Five products either side of it, plus the case the owner called out explicitly: a row
    HIDDEN BY DEFAULT (the plan judged it comfortably covered) that is nonetheless below
    its raw level is IN. That is the whole point of the sheet - the covered judgement is
    about the net, and the buyer asked to see the raw shortfall.

    At the level is NOT below it: 100 of 100 is the level being held, which is what a
    reorder level is for.
    """
    lsr = _lsr()
    run = _run(db)
    below = _product(db, stem="BELOW")
    at = _product(db, stem="ATLEVEL")
    above = _product(db, stem="ABOVE")
    no_level = _product(db, stem="NOLEVEL")
    no_stock_figure = _product(db, stem="NOPOOL")
    hidden_below = _product(db, stem="HIDDENBELOW")

    _summary_row(db, run, below, pool_on_hand=40, reorder_level=100)
    _summary_row(db, run, at, pool_on_hand=100, reorder_level=100)
    _summary_row(db, run, above, pool_on_hand=150, reorder_level=100)
    _summary_row(db, run, no_level, pool_on_hand=40, reorder_level=None)
    _summary_row(db, run, no_stock_figure, pool_on_hand=None, reorder_level=100)
    _summary_row(db, run, hidden_below, pool_on_hand=40, reorder_level=100)
    _hide(db, run, hidden_below)

    blob, _ct, _fn = lsr.export_low_stock(db, run_id=str(run.id))
    low_codes = set(_codes_of(_sheets(blob)["Low stock"]))

    assert below.product_code in low_codes, "40 of 100 is below level"
    assert hidden_below.product_code in low_codes, (
        "a hidden-by-default row can still be below its RAW level - that is the report"
    )
    assert at.product_code not in low_codes, "at the level is not below it"
    assert above.product_code not in low_codes
    assert no_level.product_code not in low_codes, "no level, nothing to be below"
    assert no_stock_figure.product_code not in low_codes, (
        "a NULL pool_on_hand is 'nobody measured', not 'zero on hand'"
    )
    assert low_codes == {below.product_code, hidden_below.product_code}, low_codes


def test_sheets_sorted_by_category_then_item_code(db):
    """AC-32: both sheets sort by Category then Item code - the client's file is filed by
    category ("Water Tap", "Shower", ...) and a buyer walks it category by category.

    The three products are seeded so that CATEGORY order and ITEM CODE order disagree: if
    the sheet sorted on the code alone the AAA-category product would not come first.
    """
    lsr = _lsr()
    run = _run(db)
    z_code_a_cat = _product(db, stem="ZZZ", category_code=f"{MARKER}-AAA")
    a_code_z_cat = _product(db, stem="AAA", category_code=f"{MARKER}-ZZZ")
    m_code_m_cat_1 = _product(db, stem="MMM1", category_code=f"{MARKER}-MMM")
    m_code_m_cat_2 = _product(db, stem="MMM2", category_code=f"{MARKER}-MMM")
    for p in (z_code_a_cat, a_code_z_cat, m_code_m_cat_1, m_code_m_cat_2):
        _summary_row(db, run, p, pool_on_hand=40, reorder_level=100)

    blob, _ct, _fn = lsr.export_low_stock(db, run_id=str(run.id))
    wb = _sheets(blob)
    expected = [
        z_code_a_cat.product_code,
        m_code_m_cat_1.product_code,
        m_code_m_cat_2.product_code,
        a_code_z_cat.product_code,
    ]
    assert _codes_of(wb["Low stock"]) == expected, "Low stock: category, then item code"
    assert _codes_of(wb["All"]) == expected, "All: the same order"


# =========================================================================== #
# AC-33: which rows the All sheet holds
# =========================================================================== #

def test_all_sheet_lists_every_planned_product_hidden_included(db):
    """AC-33: "All" is every row `report()` returns for the run, the hidden-by-default
    ones included - the sheet is the buyer's whole plan, and a row the plan judged covered
    is exactly the row they want to eyeball beside the low ones.

    The ORDER SHEET export is unchanged and still drops them (its own AC-3 rule, S7 of
    PLAN-plan-list-tile-sheet-one-scope.md) - asserted here on the SAME run, so the two
    exports cannot quietly converge on one population.
    """
    lsr = _lsr()
    run = _run(db)
    visible = _product(db, stem="VISIBLE")
    hidden = _product(db, stem="HIDDEN")
    _summary_row(db, run, visible, pool_on_hand=40, reorder_level=100)
    _summary_row(db, run, hidden, pool_on_hand=150, reorder_level=100)
    _hide(db, run, hidden)

    report_codes = {r["product_code"] for r in svc.report(db, run_id=str(run.id))["rows"]}
    assert report_codes == {visible.product_code, hidden.product_code}

    blob, _ct, _fn = lsr.export_low_stock(db, run_id=str(run.id))
    all_codes = set(_codes_of(_sheets(blob)["All"]))
    assert all_codes == report_codes, (
        f"All must be every row report() returns, hidden included: {all_codes}"
    )

    sheet_bytes, _ct2, _fn2 = svc.export_report(db, run_id=str(run.id), fmt="xlsx")
    order_sheet_codes = set(_codes_of(_sheets(sheet_bytes).active))
    assert order_sheet_codes == {visible.product_code}, (
        "the order sheet export keeps dropping hidden rows - unchanged by this slice"
    )


# =========================================================================== #
# AC-34: the three new columns come from master data
# =========================================================================== #

def test_description_category_reorder_qty_come_from_master_data(db):
    """AC-34: Description is `products.description`, NOT `product_name` - the owner's
    measurement on the lavish page is that `product_name` holds the code repeated, so
    printing it would give the buyer the Item code twice and no description at all.
    Category is the product's `product_categories.category_code`. Reorder qty is
    `products.reorder_quantity` as a NUMBER, and BLANK when it is NULL or 0 (a 0 there
    reads as "order none", which is not what an unset field means).

    All three are joined at EXPORT time, off master data - unlike every other column,
    which reads the frozen row. A buyer who fixes a description today wants it right on
    the sheet they pull today, and a description is not a planning figure that has to be
    pinned to the run's moment.
    """
    lsr = _lsr()
    run = _run(db)
    full = _product(db, stem="FULL", description="Wall hung WC, matt black",
                    category_code=f"{MARKER}-WTAP", reorder_quantity=250)
    zero = _product(db, stem="ZEROQTY", description="Shower mixer",
                    category_code=f"{MARKER}-SHWR", reorder_quantity=0)
    unset = _product(db, stem="NULLQTY", description=None,
                     category_code=f"{MARKER}-XTRA", reorder_quantity=None)
    for p in (full, zero, unset):
        _summary_row(db, run, p, pool_on_hand=40, reorder_level=100)

    blob, _ct, _fn = lsr.export_low_stock(db, run_id=str(run.id))
    by_code = {r[0]: r for r in _rows_of(_sheets(blob)["Low stock"])}

    assert by_code[full.product_code][1] == "Wall hung WC, matt black", (
        "Description is products.description, never product_name"
    )
    assert by_code[full.product_code][1] != full.product_name
    assert by_code[full.product_code][2] == f"{MARKER}-WTAP"
    assert by_code[full.product_code][5] == 250, "Reorder qty is a number, not text"

    assert by_code[zero.product_code][5] in (None, ""), (
        "a reorder quantity of 0 prints blank - 0 is not a quantity to order"
    )
    assert by_code[unset.product_code][5] in (None, ""), "NULL prints blank"
    assert by_code[unset.product_code][1] in (None, ""), "no description prints blank"
    assert by_code[unset.product_code][2] == f"{MARKER}-XTRA"


# =========================================================================== #
# AC-35: the row cap is its OWN constant
# =========================================================================== #

def test_all_sheet_over_5000_rows_refuses_422(db, monkeypatch):
    """AC-35: the low stock workbook's cap is `MAX_LOW_STOCK_ROWS = 5000`, applied to the
    "All" sheet, and the order sheet's `MAX_EXPORT_ROWS = 2000` is UNTOUCHED. Two
    documents, two sizes: the order sheet is a thing a buyer prints and walks down, the
    low stock report is a thing they filter in Excel.

    The constant is monkeypatched to 2 rather than seeding 5,001 rows - the assertion is
    about the cap being read and enforced, not about Postgres's insert rate.
    """
    lsr = _lsr()
    run = _run(db)
    for stem in ("CAP1", "CAP2", "CAP3"):
        _summary_row(db, run, _product(db, stem=stem), pool_on_hand=40, reorder_level=100)

    assert lsr.MAX_LOW_STOCK_ROWS == 5000, "the documented cap for this kind"
    assert svc.MAX_EXPORT_ROWS == 2000, "the order sheet's own cap must not move"

    monkeypatch.setattr(lsr, "MAX_LOW_STOCK_ROWS", 2)
    with pytest.raises(AppException) as excinfo:
        lsr.export_low_stock(db, run_id=str(run.id))
    assert excinfo.value.status_code == 422
    assert "Narrow the plan first" in str(excinfo.value.detail)


def test_export_route_refuses_over_the_cap_before_creating_a_row(scm_app, monkeypatch):
    """AC-35: the ROUTE refuses with the same 422, synchronously - before any
    `user_downloads` row exists, the way every other guard on this endpoint already does
    (AC-16). A refused request must not leave a row behind for the drawer to show.

    Both the service module's constant and the route module's own attribute are patched,
    so this holds whether the coder reads `low_stock_report_service.MAX_LOW_STOCK_ROWS`
    at call time or imports the value into the route at module load.
    """
    from app.api.v1.scm import order_summary as route_mod
    from app.services import queue_service

    lsr = _lsr()
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    for stem in ("RCAP1", "RCAP2", "RCAP3"):
        _summary_row(db, run, _product(db, stem=stem), pool_on_hand=40, reorder_level=100)
    db.flush()
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())
    monkeypatch.setattr(lsr, "MAX_LOW_STOCK_ROWS", 2)
    monkeypatch.setattr(route_mod, "MAX_LOW_STOCK_ROWS", 2, raising=False)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "low_stock_xlsx"})

    assert resp.status_code == 422, resp.text
    assert "Narrow the plan first" in resp.text
    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a refused export left a download row behind"


# =========================================================================== #
# AC-36: the task
# =========================================================================== #

def test_generate_low_stock_report_marks_ready_with_row_counts(scm_app, monkeypatch):
    """AC-36: the task mirrors `generate_order_sheet` - read the run under no scope, adopt
    its company, `mark_processing`, render, upload to
    `exports/low-stock/{download_id}/{filename}`, `mark_ready`.

    It ALSO writes `row_count_low` / `row_count_all` onto the download row, which is what
    lets S5's chat route answer "Low: 12 of 340 planned products" without opening the
    workbook on the request thread (AC-43). Those two columns arrive in S5's migration, so
    this test is red TWICE over today: the task does not exist, and once it does the
    columns still will not until S5 lands. They are read through `getattr` so the failure
    reads as "the count was not written" rather than an opaque ORM AttributeError.
    """
    from app.services.download_service import DownloadService

    export_tasks, task_fn = _task()
    lsr = _lsr()

    _app, db, _gcu, _gcuak = scm_app
    run_id = _seed_run(db)
    user_id = seed_user(db, "purchasing")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="low_stock_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="low-stock-10092026.xlsx",
    )

    uploads: list[dict] = []

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            uploads.append({"path": file_path, "content_type": content_type})
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())
    monkeypatch.setattr(
        lsr, "export_low_stock",
        lambda db_, *, run_id, include_supplier=True: (
            b"fake-workbook",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "low-stock-10092026.xlsx",
        ),
    )

    result = task_fn(str(dl.id), run_id, user_id)

    assert result["status"] == "ready", result
    assert uploads and uploads[0]["path"] == (
        f"exports/low-stock/{dl.id}/low-stock-10092026.xlsx"
    ), uploads

    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"
    assert getattr(row, "row_count_low", None) is not None, (
        "row_count_low must be written at mark_ready so the chat route never opens the file"
    )
    assert getattr(row, "row_count_all", None) is not None, "row_count_all likewise"


def test_generate_low_stock_report_marks_failed_when_render_raises(monkeypatch):
    """AC-36: `_record_failure` on any exception, and NOTHING raised into RQ - a poisoned
    job retries forever and the buyer's row sits `processing` until it goes stale.

    `_savepoint_session` rather than the `scm_app` fixture for the same reason the order
    sheet's twin test uses it: `_record_failure` calls `db.rollback()` first, which against
    `scm_app` cascades past every nested savepoint to the fixture's own transaction and
    expires the download row (see that test's docstring for the full reasoning).
    """
    from app.services.download_service import DownloadService

    export_tasks, task_fn = _task()
    lsr = _lsr()

    with _savepoint_session() as db:
        run_id = _seed_run(db)
        user_id = seed_user(db, "purchasing")
        db.flush()
        dl = DownloadService(db).create(
            user_id=user_id, kind="low_stock_xlsx", source_entity_type="reorder_run",
            source_entity_id=run_id, filename="low-stock-10092026.xlsx",
        )

        def _boom(db_, *, run_id, include_supplier=True):
            raise RuntimeError("render exploded")

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        monkeypatch.setattr(lsr, "export_low_stock", _boom)

        result = task_fn(str(dl.id), run_id, user_id)

        assert result["status"] == "failed", result
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "failed", row.status
        assert "render exploded" in (row.error or ""), row.error


# =========================================================================== #
# AC-37 / AC-47: the Supplier column is optional
# =========================================================================== #

def test_include_supplier_false_drops_the_supplier_column_on_both_sheets(db):
    """AC-47 (and plan S3, step 5): `include_supplier=False` drops the Supplier column
    from BOTH sheets - header and cells alike, so the workbook is fifteen columns wide,
    not sixteen with a blank one. S5's chat route passes it when the contact lacks the
    `purchase_orders.supplier` reveal key; the plan-view export always includes it, so the
    default is True.

    A blanked column would still tell the reader a supplier exists and is being withheld,
    which is the leak the reveal key exists to prevent.
    """
    lsr = _lsr()
    run = _run(db)
    product = _product(db, stem="SUPPLIER")
    _summary_row(db, run, product, pool_on_hand=40, reorder_level=100,
                 supplier_name="Guangdong SW")

    with_supplier, _ct, _fn = lsr.export_low_stock(db, run_id=str(run.id))
    wb_with = _sheets(with_supplier)
    assert wb_with["Low stock"][1][_SUPPLIER_COLUMN].value == "Supplier"
    assert "Guangdong SW" in _rows_of(wb_with["Low stock"])[0]

    without, _ct2, _fn2 = lsr.export_low_stock(
        db, run_id=str(run.id), include_supplier=False
    )
    wb_without = _sheets(without)
    expected = tuple(c for c in _EXPECTED_COLUMNS if c != "Supplier")
    for name in ("Low stock", "All"):
        ws = wb_without[name]
        assert tuple(c.value for c in ws[1]) == expected, (
            f"{name} still carries a Supplier column"
        )
        assert "Guangdong SW" not in _rows_of(ws)[0], (
            f"{name} still prints the supplier name in another cell"
        )
