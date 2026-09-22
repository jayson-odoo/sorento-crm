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

from app.services.download_service import DownloadService
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_order_sheet_export_downloads import (
    _NoCloseSession,
    _savepoint_session,
    _seed_run,
)

pytestmark = requires_pg


def test_c4_generate_oi_worksheet_marks_ready(scm_app, monkeypatch):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    user_id = seed_user(db, "purchasing")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="oi-worksheet-10092026.xlsx",
    )

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(
        OrderInquiryWorklistService, "export_xlsx",
        lambda self, **filters: ("oi-worksheet-10092026.xlsx", b"fake-bytes"),
    )

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
