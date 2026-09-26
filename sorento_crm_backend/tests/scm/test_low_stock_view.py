"""S1 of PLAN-excel-preview-26sep.md (UAC excel-preview-26sep-acceptance-criteria.md AC-1..AC-9b):
the low stock report as an in-app view, and the filters it shares with the export.

The page previews a workbook that does not exist yet (the user is still choosing the split and
the filters), so the view is built by the SAME function that builds the file. The central test
here is `test_view_and_workbook_agree`: for one `(run, split, suppliers, categories)` the sheet
titles, their order and every cell must be the same on screen and in the file.

Written before the implementation (tests red first). Every name under test is fetched inside
the test (`_lsr()`), so a missing function is one red test, not a collection error.

Postgres only, marker-prefixed rows, rolled back at teardown.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.scm import ReorderRun
from app.services.error_handler import AppException
from tests.scm.conftest import requires_pg
from tests.scm.test_low_stock_report import (
    MARKER,
    _blank_category,
    _code,
    _lsr,
    _product,
    _product_in_category,
    _rows_of,
    _run,
    _sheets,
    _summary_row,
    _task,
    _u,
)
from tests.scm.test_m3_run import _client
from tests.scm.test_order_sheet_export_downloads import (  # noqa: F401
    _NoCloseSession,
    _seed_run,
)
from tests.scm.test_product_grain_summary import db  # noqa: F401

pytestmark = requires_pg

VIEW_URL = "/api/v1/scm/order-summary/low-stock-view"
EXPORT_URL = "/api/v1/scm/order-summary/export"


def _norm(value):
    """A blank cell reads back from openpyxl as None; the view sends it as "". Both mean
    "nothing printed here"."""
    return "" if value is None else value


def _seed_mixed(db, run):
    """Two suppliers x two categories, one row with no supplier and one with no category,
    some low, some not. Enough to give every split more than one group and each filter
    something to remove."""
    tag = uuid.uuid4().hex[:4].upper()
    cat_a = f"{MARKER}A{tag}"
    cat_b = f"{MARKER}B{tag}"
    sup_x = f"{MARKER} Xylo {tag}"
    sup_y = f"{MARKER} Yarrow {tag}"
    specs = [
        ("AX1", cat_a, sup_x, 10, 100),   # low
        ("AX2", cat_a, sup_x, 150, 100),
        ("AY1", cat_a, sup_y, 5, 50),     # low
        ("BX1", cat_b, sup_x, 70, 60),
        ("BY1", cat_b, sup_y, 1, 60),     # low
        ("BY2", cat_b, sup_y, 90, 60),
        ("BN1", cat_b, None, 2, 60),      # low, no supplier
    ]
    for stem, cat, sup, on_hand, level in specs:
        product = _product(db, stem=stem, category_code=cat, description=f"{stem} desc")
        _summary_row(db, run, product, pool_on_hand=on_hand, reorder_level=level,
                     supplier_name=sup)
    blank = _blank_category(db)
    _summary_row(db, run, _product_in_category(db, stem="NC1", cat=blank),
                 pool_on_hand=3, reorder_level=30, supplier_name=sup_x)   # low, no category
    db.flush()
    return {"cat_a": cat_a, "cat_b": cat_b, "sup_x": sup_x, "sup_y": sup_y}


# =========================================================================== #
# AC-2: one builder, the view and the file agree
# =========================================================================== #

@pytest.mark.parametrize(
    "split,filtered",
    [
        ("none", False),
        ("supplier", False),
        ("category", False),
        ("supplier_category", False),
        ("supplier_category", True),
        ("none", True),
    ],
)
def test_view_and_workbook_agree(db, split, filtered):
    lsr = _lsr()
    run = _run(db)
    keys = _seed_mixed(db, run)
    suppliers = [keys["sup_y"], "No supplier"] if filtered else None
    categories = [keys["cat_b"]] if filtered else None

    view = lsr.build_low_stock_view(
        db, run_id=str(run.id), split=split, suppliers=suppliers, categories=categories,
    )
    blob, _ct, filename, counts = lsr.export_low_stock(
        db, run_id=str(run.id), split=split, suppliers=suppliers, categories=categories,
    )
    wb = _sheets(blob)

    assert [s["title"] for s in view["sheets"]] == wb.sheetnames
    assert view["filename"] == filename
    assert view["counts"]["sheets"] == counts["sheets"] == len(wb.sheetnames)
    assert view["counts"]["rows"] == counts["all"]
    assert view["counts"]["low"] == counts["low"]
    for sheet in view["sheets"]:
        ws = wb[sheet["title"]]
        header = [c.value for c in ws[1]]
        assert header == view["columns"], sheet["title"]
        on_screen = [tuple(_norm(v) for v in view["rows"][i]) for i in sheet["row_indexes"]]
        in_file = [tuple(_norm(v) for v in row) for row in _rows_of(ws)]
        assert on_screen == in_file, sheet["title"]


# =========================================================================== #
# AC-3 / AC-4 / AC-5: default split, filters before the split, whole-run facets
# =========================================================================== #

def test_view_default_split_is_supplier_category(db):
    lsr = _lsr()
    run = _run(db)
    keys = _seed_mixed(db, run)

    view = lsr.build_low_stock_view(db, run_id=str(run.id))

    assert view["split"] == "supplier_category"
    titles = [s["title"] for s in view["sheets"]]
    # Six supplier x category pairs hold a row (X-A, Y-A, X-B, Y-B, none-B, X-none): a
    # "<pair> - Low" and a "<pair>" sheet each.
    assert view["counts"]["sheets"] == len(titles) == 12, titles
    assert f"{keys['sup_x']} - No category - Low"[:31] in titles or any(
        t.startswith(f"{keys['sup_x']} - No") for t in titles
    ), titles


def test_view_filters_apply_before_split_blank_buckets_selectable(db):
    lsr = _lsr()
    run = _run(db)
    keys = _seed_mixed(db, run)

    only_blank_supplier = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="supplier", suppliers=["No supplier"],
    )
    assert [s["title"] for s in only_blank_supplier["sheets"]] == [
        "No supplier - Low", "No supplier",
    ]
    assert only_blank_supplier["counts"]["rows"] == 1

    only_blank_category = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="none", categories=["No category"],
    )
    assert only_blank_category["counts"]["rows"] == 1
    assert only_blank_category["counts"]["low"] == 1

    both = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="none",
        suppliers=[keys["sup_x"]], categories=[keys["cat_a"]],
    )
    # AX1 and AX2 only: supplier X AND category A.
    assert both["counts"]["rows"] == 2
    assert both["counts"]["low"] == 1

    unknown = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="none", suppliers=["Nobody at all"],
    )
    assert unknown["counts"]["rows"] == 0
    assert unknown["sheets"][0]["title"] == "Low stock"


def test_view_facets_are_whole_run_with_counts(db):
    lsr = _lsr()
    run = _run(db)
    keys = _seed_mixed(db, run)

    view = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="none", suppliers=[keys["sup_y"]],
    )

    suppliers = {f["key"]: (f["rows"], f["low"]) for f in view["facets"]["suppliers"]}
    assert suppliers == {
        keys["sup_x"]: (4, 2),
        keys["sup_y"]: (3, 2),
        "No supplier": (1, 1),
    }
    categories = {f["key"]: (f["rows"], f["low"]) for f in view["facets"]["categories"]}
    assert categories == {
        keys["cat_a"]: (3, 2),
        keys["cat_b"]: (4, 2),
        "No category": (1, 1),
    }
    ordered = [f["key"] for f in view["facets"]["suppliers"]]
    assert ordered == sorted(ordered, key=str.lower)


# =========================================================================== #
# AC-7: the cap is on the filtered rows, in the view and in the export
# =========================================================================== #

def test_view_over_cap_answers_counts_without_rows(db, monkeypatch):
    lsr = _lsr()
    monkeypatch.setattr(lsr, "MAX_LOW_STOCK_ROWS", 3)
    run = _run(db)
    keys = _seed_mixed(db, run)

    over = lsr.build_low_stock_view(db, run_id=str(run.id))
    assert over["over_cap"] is True
    assert over["rows"] == []
    assert over["counts"]["rows"] == 8
    assert over["max_rows"] == 3

    narrowed = lsr.build_low_stock_view(
        db, run_id=str(run.id), split="none", suppliers=[keys["sup_y"]],
    )
    assert narrowed["over_cap"] is False
    assert len(narrowed["rows"]) == 3


def test_cap_checked_on_filtered_rows(db, monkeypatch):
    lsr = _lsr()
    monkeypatch.setattr(lsr, "MAX_LOW_STOCK_ROWS", 3)
    run = _run(db)
    keys = _seed_mixed(db, run)

    with pytest.raises(AppException) as err:
        lsr.export_low_stock(db, run_id=str(run.id))
    assert err.value.status_code == 422

    blob, _ct, _fn, counts = lsr.export_low_stock(
        db, run_id=str(run.id), suppliers=[keys["sup_y"]],
    )
    assert counts["all"] == 3
    assert _sheets(blob).sheetnames == ["Low stock", "All"]


def test_view_payload_rows_travel_once(db):
    lsr = _lsr()
    run = _run(db)
    _seed_mixed(db, run)

    view = lsr.build_low_stock_view(db, run_id=str(run.id), split="supplier_category")

    assert len(view["rows"]) == view["counts"]["rows"] == 8
    for sheet in view["sheets"]:
        assert all(isinstance(i, int) for i in sheet["row_indexes"])
        assert "rows" not in sheet


# =========================================================================== #
# AC-9b: the faster writer keeps the look
# =========================================================================== #

def test_workbook_style_unchanged(db):
    lsr = _lsr()
    run = _run(db)
    _seed_mixed(db, run)

    blob, _ct, _fn, _counts = lsr.export_low_stock(db, run_id=str(run.id))
    ws = _sheets(blob)["All"]

    header = ws["A1"]
    assert header.font.bold is True
    assert header.font.color.rgb == "FFFFFFFF"
    assert header.fill.fgColor.rgb == "FF404040"
    body = ws["B2"]
    assert body.border.left.style == "thin"
    assert body.border.bottom.style == "thin"
    assert body.alignment.wrap_text is True
    assert body.alignment.vertical == "top"
    assert ws.freeze_panes == "A2"
    assert ws.column_dimensions["A"].width == 16
    assert ws.column_dimensions["B"].width == 42
    assert ws.column_dimensions["N"].width == 34
    assert ws["D2"].data_type == "n", "quantities stay numbers"


# =========================================================================== #
# AC-1: the route
# =========================================================================== #

def test_view_route_404_invisible_run_fields_declared(scm_app):
    from app.models.company import Company

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    keys = _seed_mixed(db, run)
    other_company = Company(id=_u(), code=_code("OTHERCO")[:20], name=f"{MARKER} other")
    db.add(other_company)
    db.flush()
    other_run_id = _seed_run(db, company_id=other_company.id)
    db.flush()

    with TestClient(app) as c:
        ok = c.get(VIEW_URL, params=[
            ("run_id", run_id), ("split", "supplier"),
            ("supplier", keys["sup_x"]), ("supplier", "No supplier"),
        ])
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert set(body) >= {
            "run", "split", "columns", "rows", "sheets", "facets", "counts",
            "over_cap", "max_rows", "filename",
        }, body.keys()
        assert set(body["run"]) >= {"run_id", "as_of"}
        assert body["run"]["run_id"] == run_id
        assert body["split"] == "supplier"
        assert set(body["sheets"][0]) >= {"title", "row_indexes", "low"}
        assert set(body["facets"]) == {"suppliers", "categories"}
        assert set(body["facets"]["suppliers"][0]) == {"key", "rows", "low"}
        assert set(body["counts"]) == {"rows", "low", "sheets"}
        assert [s["title"] for s in body["sheets"]] == [
            "No supplier - Low", "No supplier",
            f"{keys['sup_x']} - Low", keys["sup_x"],
        ]
        assert body["counts"]["rows"] == 5

        default = c.get(VIEW_URL, params={"run_id": run_id})
        assert default.json()["split"] == "supplier_category"

        assert c.get(VIEW_URL, params={"run_id": "not-a-uuid"}).status_code == 404
        assert c.get(VIEW_URL, params={"run_id": str(uuid.uuid4())}).status_code == 404
        assert c.get(VIEW_URL, params={"run_id": other_run_id}).status_code == 404
        assert c.get(VIEW_URL, params={"run_id": run_id, "split": "bogus"}).status_code == 422


def test_view_route_run_id_omitted_uses_newest_completed_run(scm_app):
    app, db = _client(scm_app, "purchasing")
    older_id = _seed_run(db)
    newer_id = _seed_run(db)
    db.execute(text("UPDATE scm.reorder_run SET started_at = :t WHERE id = :id"),
               {"t": datetime(2026, 9, 1, 8, 0, 0), "id": older_id})
    db.execute(text("UPDATE scm.reorder_run SET started_at = :t WHERE id = :id"),
               {"t": datetime(2026, 9, 10, 8, 0, 0), "id": newer_id})
    older = db.get(ReorderRun, older_id)
    newer = db.get(ReorderRun, newer_id)
    for stem in ("OLDA", "OLDB", "OLDC"):
        _summary_row(db, older, _product(db, stem=stem), pool_on_hand=10, reorder_level=100)
    _summary_row(db, newer, _product(db, stem="NEWA"), pool_on_hand=10, reorder_level=100)
    db.flush()

    with TestClient(app) as c:
        resp = c.get(VIEW_URL)

    assert resp.status_code == 200, resp.text
    assert resp.json()["run"]["run_id"] == newer_id
    assert resp.json()["counts"]["rows"] == 1


def test_low_stock_preview_route_is_gone(scm_app):
    """The split dialog's courtesy read went with the dialog (AC-16): the page shows the same
    counts from the view."""
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.flush()
    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/low-stock-preview", params={"run_id": run_id})
    assert resp.status_code in (404, 405), resp.text
    assert not hasattr(_lsr(), "low_stock_preview")


# =========================================================================== #
# AC-6: the export carries the filters
# =========================================================================== #

def test_export_route_forwards_filters_to_task(scm_app, monkeypatch):
    from app.services import queue_service

    _task()
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    keys = _seed_mixed(db, run)

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append(kwargs)
        return type("J", (), {"id": "fake-job-id"})()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    with TestClient(app) as c:
        resp = c.post(EXPORT_URL, json={
            "run_id": run_id, "format": "low_stock_xlsx", "split": "supplier_category",
            "suppliers": [keys["sup_x"]], "categories": [keys["cat_a"], "No category"],
        })

    assert resp.status_code == 200, resp.text
    assert calls[-1]["split"] == "supplier_category"
    assert calls[-1]["suppliers"] == [keys["sup_x"]]
    assert calls[-1]["categories"] == [keys["cat_a"], "No category"]


def test_export_route_rejects_filters_on_other_formats(scm_app, monkeypatch):
    from app.services import queue_service

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    _summary_row(db, run, _product(db, stem="FILTFMT"), pool_on_hand=40, reorder_level=100)
    db.flush()
    calls: list = []
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: calls.append(k) or type("J", (), {"id": "x"})())
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        for body in (
            {"format": "xlsx", "suppliers": ["A"]},
            {"format": "pdf", "categories": ["B"]},
        ):
            resp = c.post(EXPORT_URL, json={"run_id": run_id, **body})
            assert resp.status_code == 422, resp.text
            assert "filters apply to the low stock report only" in resp.text

    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before
    assert calls == []


def test_export_route_cap_counts_filtered_rows(scm_app, monkeypatch):
    """A run over the cap is refused unfiltered and accepted once a filter brings it under
    (AC-7), and the refusal still leaves no download row."""
    from app.services import queue_service
    from app.services.scm import low_stock_report_service

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    run = db.get(ReorderRun, run_id)
    keys = _seed_mixed(db, run)
    monkeypatch.setattr(low_stock_report_service, "MAX_LOW_STOCK_ROWS", 3)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        refused = c.post(EXPORT_URL, json={"run_id": run_id, "format": "low_stock_xlsx"})
        assert refused.status_code == 422, refused.text
        assert db.execute(text("SELECT count(*) FROM user_downloads")).scalar() == before

        narrowed = c.post(EXPORT_URL, json={
            "run_id": run_id, "format": "low_stock_xlsx", "suppliers": [keys["sup_y"]],
        })
        assert narrowed.status_code == 200, narrowed.text


def test_generate_low_stock_report_forwards_filters(scm_app, monkeypatch):
    from app.services.download_service import DownloadService
    from tests.scm.conftest import seed_user

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

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    seen: dict = {}

    def _fake_export(db_, *, run_id, include_supplier=True, split="none",
                     suppliers=None, categories=None):
        seen.update(split=split, suppliers=suppliers, categories=categories)
        return (b"x", "application/octet-stream", "low-stock.xlsx",
                {"low": 1, "all": 2, "sheets": 2})

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())
    monkeypatch.setattr(lsr, "export_low_stock", _fake_export)

    result = task_fn(str(dl.id), run_id, user_id, split="supplier",
                     suppliers=["S1"], categories=["C1"])

    assert result["status"] == "ready", result
    assert seen == {"split": "supplier", "suppliers": ["S1"], "categories": ["C1"]}
