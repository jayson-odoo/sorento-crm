"""PLAN-po-spo-site-pool-and-order-sheet-downloads.md - S4-BE (AC-15..AC-18).

The order sheet export moves off a synchronous GET onto the My Downloads pipeline every
other export already uses (`complaints.py::export_complaint_pdf` /
`export_tasks.generate_complaint_pdf`): `POST /api/v1/scm/order-summary/export` creates a
`user_downloads` row and enqueues `app.tasks.export_tasks.generate_order_sheet` on the
`imports` queue; the GET route is removed.

Every call into `export_tasks.generate_order_sheet` / a POST on this path is deliberate: the
function and the route do not exist yet, so the right-reason failure is an AttributeError /
404 / 405, not a fixture bug.

Postgres only, marker-prefixed seeding, nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user
from tests.scm.test_m3_run import _client

pytestmark = requires_pg

MARKER = "ZZTOSD"


def _u() -> str:
    return str(uuid.uuid4())


class _NoCloseSession:
    """Lets a background-task function's own ``SessionLocal()`` reuse the test's
    rolled-back savepoint session instead of opening a real, separate connection that
    cannot see the test's uncommitted seed data."""

    def __init__(self, inner):
        self._inner = inner

    def close(self):  # noqa: D401 - the test owns the session's lifetime
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _seed_run(db, *, status: str = "completed") -> str:
    """`scm.reorder_run.company_id` has NO column default (unlike `products` /
    `warehouses`) - it must be stamped explicitly or `assert_run_visible`'s company-scope
    gate (`shared=False`) reads the row as another company's and answers 404."""
    return str(db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, :s, false, :co, now()) RETURNING id"
    ), {"id": _u(), "s": status, "co": SORENTO_COMPANY_ID}).scalar())


# =========================================================================== #
# AC-15 / AC-16: the POST route
# =========================================================================== #

def test_export_post_creates_download_row_and_enqueues(scm_app, monkeypatch):
    from app.services import queue_service

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.flush()

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})

        class _Job:
            id = "fake-job-id"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "xlsx"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending", body
    assert body["kind"] == "order_sheet_xlsx", body

    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id, "
        "       filename, status "
        "FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "order_sheet_xlsx"
    assert row["source_entity_type"] == "reorder_run"
    assert row["source_entity_id"] == run_id
    assert row["filename"], "no filename was stamped"
    assert row["filename"].startswith("order-sheet-"), row["filename"]
    assert row["filename"].endswith(".xlsx"), row["filename"]

    assert len(calls) == 1, f"expected exactly one enqueue, got {calls}"
    assert calls[0]["kwargs"].get("queue_name") == "imports", calls[0]


def test_export_post_guards_run_before_a_row_exists(scm_app):
    """AC-16: format/run guards run SYNCHRONOUSLY, before any `user_downloads` row is
    written - unknown format 422, malformed run id 404, an invisible/absent run 404."""
    app, db = _client(scm_app, "purchasing")
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        resp_fmt = c.post("/api/v1/scm/order-summary/export",
                          json={"run_id": _u(), "format": "csv"})
        resp_malformed = c.post("/api/v1/scm/order-summary/export",
                                json={"run_id": "not-a-uuid", "format": "pdf"})
        resp_absent = c.post("/api/v1/scm/order-summary/export",
                             json={"run_id": _u(), "format": "pdf"})

    assert resp_fmt.status_code == 422, resp_fmt.text
    assert resp_malformed.status_code == 404, resp_malformed.text
    assert resp_absent.status_code == 404, resp_absent.text

    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a guard failure left a download row behind"


# =========================================================================== #
# AC-17: the task
# =========================================================================== #

def test_generate_order_sheet_marks_ready(scm_app, monkeypatch):
    from app.services.download_service import DownloadService
    from app.services.scm import summary_order_service
    from app.tasks import export_tasks

    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    user_id = seed_user(db, "purchasing")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_sheet_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="order-sheet-10092026.xlsx",
    )

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(
        summary_order_service, "export_report",
        lambda db_, *, run_id, fmt: (
            b"fake-bytes",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "order-sheet-10092026.xlsx",
        ),
    )

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    result = export_tasks.generate_order_sheet(str(dl.id), run_id, "xlsx", user_id)

    assert result["status"] == "ready", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"
    assert row.filename == "order-sheet-10092026.xlsx"


def test_generate_order_sheet_marks_failed_when_render_raises(scm_app, monkeypatch):
    from app.services.download_service import DownloadService
    from app.services.scm import summary_order_service
    from app.tasks import export_tasks

    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    user_id = seed_user(db, "purchasing")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_sheet_pdf", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="order-sheet-10092026.pdf",
    )

    def _boom(db_, *, run_id, fmt):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(summary_order_service, "export_report", _boom)

    result = export_tasks.generate_order_sheet(str(dl.id), run_id, "pdf", user_id)

    assert result["status"] == "failed", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "failed", row.status
    assert "render exploded" in (row.error or ""), row.error


# =========================================================================== #
# AC-18: the GET route is gone
# =========================================================================== #

def test_export_get_is_gone(scm_app):
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.flush()

    with TestClient(app) as c:
        resp = c.get("/api/v1/scm/order-summary/export",
                     params={"run_id": run_id, "format": "xlsx"})

    assert resp.status_code == 405, resp.status_code
