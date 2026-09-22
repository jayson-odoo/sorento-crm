"""Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C2/AC-C3): the RQ task
`app.tasks.export_tasks.generate_oi_worksheet(download_id, run_id, user_id)` - mirrors
`generate_order_sheet` line for line (`mark_processing`, adopt the run's own company
scope, build the row ids via `run_scope_oi_rows`, call `OrderInquiryWorklistService.
export_xlsx(row_ids=..., columns=...)`, upload, `mark_ready`; `_record_failure` on any
exception, never raising into RQ).

The function does not exist yet, so every case here is red for an `AttributeError`
(`module 'app.tasks.export_tasks' has no attribute 'generate_oi_worksheet'`), not a
fixture bug, until C4 lands. Harness copied from
`test_order_sheet_export_downloads.py`'s own task section (`_NoCloseSession`,
`_savepoint_session`, `_seed_run`).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.download_service import DownloadService
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_order_sheet_export_downloads import (
    _NoCloseSession,
    _savepoint_session,
    _seed_run,
)

pytestmark = requires_pg


def test_c4_generate_oi_worksheet_marks_ready(scm_app, monkeypatch):
    from app.models.inventory import Warehouse
    from app.models.product import Product
    from app.services.order_inquiry_worklist_service import (
        EXPORT_HEADINGS,
        OrderInquiryWorklistService,
    )
    from app.tasks import export_tasks
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse
    from tests.scm.test_oi_worksheet_row_scope import _engine_row

    _, db, _, _ = scm_app
    marker = f"ZZTOIWST-{uuid.uuid4().hex[:8]}"
    pid = _mk_product(db, marker)
    wid = _mk_warehouse(db, marker)
    db.flush()
    product = db.get(Product, pid)
    wh = db.get(Warehouse, wid)
    # S1 (fix round 2): a REAL engine-scoped OI row, so `row_ids` can be pinned to
    # exactly what `run_scope_oi_rows` returns for this run rather than asserted as
    # merely present.
    leg = _engine_row(db, product=product, wh=wh, qty=6, delivery=date(2026, 10, 1))
    run_id = _seed_run(db, product_ids=[pid])
    user_id = seed_user(db, "purchasing")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="oi-worksheet-10092026.xlsx",
    )

    captured: dict = {}

    def _fake_export_xlsx(self, **filters):
        captured.update(filters)
        return ("oi-worksheet-10092026.xlsx", b"fake-bytes")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _fake_export_xlsx)

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    result = export_tasks.generate_oi_worksheet(str(dl.id), run_id, user_id)

    assert result["status"] == "ready", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"
    assert row.filename == "oi-worksheet-10092026.xlsx"

    # S1: the writer was called with the worksheet's own 10-column slice and the EXACT
    # row ids `run_scope_oi_rows` returns for this run - not "some row_ids", this run's.
    assert captured.get("columns") == EXPORT_HEADINGS[:10], captured.get("columns")
    assert captured.get("row_ids") == [leg["row"].id], captured.get("row_ids")


def test_c4_generate_oi_worksheet_marks_failed_when_the_writer_raises(monkeypatch):
    """`_record_failure` always calls `db.rollback()` first - `_savepoint_session` is the
    session shape that survives it (see the twin comment on
    `test_generate_order_sheet_marks_failed_when_render_raises`)."""
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    with _savepoint_session() as db:
        run_id = _seed_run(db)
        user_id = seed_user(db, "purchasing")
        db.flush()

        dl = DownloadService(db).create(
            user_id=user_id, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
            source_entity_id=run_id, filename="oi-worksheet-10092026.xlsx",
        )

        def _boom(self, **filters):
            raise RuntimeError("writer exploded")

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _boom)

        result = export_tasks.generate_oi_worksheet(str(dl.id), run_id, user_id)

        assert result["status"] == "failed", result
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "failed", row.status
        assert "writer exploded" in (row.error or ""), row.error


# =========================================================================== #
# S2 (fix round 2): a missing/company-less run must not render a "ready"
# workbook with nothing wrong - it fails closed, the same 404
# `generate_order_sheet`'s path raises via `_run_for` under UNSET scope.
# =========================================================================== #

def test_c4_generate_oi_worksheet_fails_closed_when_the_run_is_missing(monkeypatch):
    from app.tasks import export_tasks

    with _savepoint_session() as db:
        run_id = str(uuid.uuid4())  # never inserted
        user_id = seed_user(db, "purchasing")
        db.flush()

        dl = DownloadService(db).create(
            user_id=user_id, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
            source_entity_id=run_id, filename="oi-worksheet-10092026.xlsx",
        )
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        result = export_tasks.generate_oi_worksheet(str(dl.id), run_id, user_id)

        assert result["status"] == "failed", (
            f"a missing run must not render a ready workbook: {result}"
        )
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "failed", row.status
        assert "That plan does not exist." in (row.error or ""), row.error


def test_c4_generate_oi_worksheet_fails_closed_when_the_run_has_no_company(monkeypatch):
    """A legacy run row (`company_id IS NULL`) must not export under the `None`
    (all-companies) scope the task starts under while it looks the run up - the SAME
    fail-closed twin `test_generate_order_sheet_fails_closed_when_the_run_has_no_company`
    pins for the order sheet."""
    from app.tasks import export_tasks

    with _savepoint_session() as db:
        run_id = str(db.execute(text(
            "INSERT INTO scm.reorder_run (id, status, include_market, company_id, "
            "created_at) VALUES (:id, 'completed', false, NULL, now()) RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar())
        user_id = seed_user(db, "purchasing")
        db.flush()

        dl = DownloadService(db).create(
            user_id=user_id, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
            source_entity_id=run_id, filename="oi-worksheet-10092026.xlsx",
        )
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        result = export_tasks.generate_oi_worksheet(str(dl.id), run_id, user_id)

        assert result["status"] == "failed", (
            f"a company-less run must not render a ready workbook: {result}"
        )
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "failed", row.status
        assert "That plan does not exist." in (row.error or ""), row.error
