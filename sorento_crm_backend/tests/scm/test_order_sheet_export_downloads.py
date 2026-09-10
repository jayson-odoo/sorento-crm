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
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
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


@contextmanager
def _savepoint_session():
    """A Postgres session whose OWN `.commit()`/`.rollback()` operate on a SAVEPOINT,
    never on the outer connection-level transaction - unlike `tests._pg_fixture.
    pg_session()`, which binds a plain `Session(bind=connection)` with no
    `join_transaction_mode` and (proven below, not merely suspected) lets a mid-test
    `.rollback()` cascade straight through to the connection, deassociating it from the
    transaction `finally` tries to roll back (`SAWarning: transaction already
    deassociated from connection`) and expiring every row the test created
    (`ObjectDeletedError` on the very next read).

    `_record_failure` (`app/tasks/export_tasks.py`) always calls `db.rollback()` first -
    correct against a real session, where the query that failed may have left the
    transaction aborted - so a task-failure test needs a session that survives one.
    `join_transaction_mode="create_savepoint"` (the same explicit choice
    `tests._pg_fixture.blank_session()` makes, for the identical reason) is what makes
    that true: the Session's transaction is a SAVEPOINT inside the connection's, so its
    commit/rollback releases or undoes that savepoint alone.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


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
    """`enqueue_job` is patched at its source (`app.services.queue_service`) BEFORE the
    request fires - `app.api.v1.scm.order_summary.export_order_summary` imports it
    function-locally (`from app.services.queue_service import enqueue_job`, resolved
    fresh on every call), so patching the module attribute here is what the route
    actually calls. This is load-bearing, not decorative: a real job reached the lane's
    shared Redis `imports` queue and was picked up by the lane worker during an earlier
    (unpatched) run - the full call-args assertion below is what would have caught that
    the enqueue was in fact the REAL `enqueue_job`, not this fake."""
    from app.services import queue_service
    from app.tasks.export_tasks import generate_order_sheet

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
        "       filename, status, user_id "
        "FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "order_sheet_xlsx"
    assert row["source_entity_type"] == "reorder_run"
    assert row["source_entity_id"] == run_id
    assert row["filename"], "no filename was stamped"
    assert row["filename"].startswith("order-sheet-"), row["filename"]
    assert row["filename"].endswith(".xlsx"), row["filename"]

    # The FULL call, not just the queue name - the row's own id, the run id, the format
    # and the actor all travel through to the task exactly as `generate_order_sheet`'s
    # signature expects them.
    assert len(calls) == 1, f"expected exactly one enqueue, got {calls}"
    call = calls[0]
    assert call["func"] is generate_order_sheet, call["func"]
    assert call["args"] == (body["id"], run_id, "xlsx", row["user_id"]), call["args"]
    assert call["kwargs"] == {"queue_name": "imports", "job_timeout": 600}, call["kwargs"]


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


def test_export_post_answers_409_while_a_sheet_is_in_flight(scm_app, monkeypatch):
    """AC-16b (security S5, Phase 3 fix round): a second POST for the SAME run while the
    caller already has an `order_sheet_*` download `pending`/`processing` for that run is
    refused with 409 and creates no second row - one in-flight sheet per user per run, no
    queue machinery needed to enforce it."""
    from app.services import queue_service

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.flush()

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        first = c.post("/api/v1/scm/order-summary/export",
                       json={"run_id": run_id, "format": "xlsx"})
        assert first.status_code == 200, first.text

        second = c.post("/api/v1/scm/order-summary/export",
                        json={"run_id": run_id, "format": "pdf"})

    assert second.status_code == 409, second.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).scalar()
    assert count == 1, f"the in-flight guard let a second row through: {count}"


def test_export_post_rejects_api_key_only_principal(scm_app):
    """AC-16c (security S4, `app/dependencies.py` rule): a write endpoint is never
    reachable by `X-API-Key` alone - the route must gate on `require_permission`
    (JWT-only `get_current_user`), not `require_permission_with_api_key`
    (`get_current_user_or_api_key`, which the route still uses today). Builds a REAL,
    resolvable integration key (not `as_user`, which overrides both current-user
    dependencies unconditionally and would hide this) so the refusal is proven to be
    about the AUTH METHOD, not a missing permission."""
    from app.models.integration import Integration, IntegrationApiKey  # noqa: F401
    from app.models.user import User, UserRoleAssignment
    from app.services.integration_key_service import IntegrationKeyService

    app, db, _gcu, _gcuak = scm_app
    run_id = _seed_run(db)

    user = User(email=f"{_u()}@integrations.local", name="ZZTOSD integration",
               status="ACTIVE", is_integration=True)
    db.add(user)
    db.flush()
    role_id = db.execute(text(
        "SELECT id FROM user_roles WHERE slug = 'purchasing'"
    )).scalar()
    assert role_id, "role 'purchasing' not seeded"
    db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
    integration = Integration(name=f"ZZTOSD-{_u()[:8]}", type="autocount_esb",
                              act_as_user_id=user.id, is_active=True)
    db.add(integration)
    db.flush()
    key = IntegrationKeyService(db).issue_key(integration)
    db.flush()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      headers={"X-API-Key": key},
                      json={"run_id": run_id, "format": "xlsx"})

    assert resp.status_code in (401, 403), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).scalar()
    assert count == 0, "an API-key-only caller was allowed to create a download row"


def test_export_post_marks_failed_and_503_when_enqueue_raises(scm_app, monkeypatch):
    """AC-16d (reviewer S4 / security N3): when `enqueue_job` raises, the already-created
    row is marked failed and the route answers 503 - the buyer sees the sheet failed
    rather than a row stuck in `pending` forever."""
    from app.services import queue_service

    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.flush()

    def _boom(*a, **k):
        raise RuntimeError("redis is away")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "xlsx"})

    assert resp.status_code == 503, resp.text
    row = db.execute(text(
        "SELECT status, error FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).mappings().first()
    assert row is not None, "no download row was created before the enqueue attempt"
    assert row["status"] == "failed", row["status"]
    assert row["error"], "no error message was recorded"


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


def test_generate_order_sheet_marks_failed_when_render_raises(monkeypatch):
    """`_record_failure` always calls `db.rollback()` first - correct against a real
    session, where the query that failed may have left the transaction aborted. Against
    `scm_app`'s fixture, though, that same `.rollback()` cascades past every nested
    savepoint its `after_transaction_end` listener auto-restarts, straight to the
    fixture's own outer transaction - deassociating it and expiring the just-created
    download row (`ObjectDeletedError` on the very next read, independent of this
    slice's own code; reproduced and reported by the coder). `tests._pg_fixture.
    pg_session()` reproduces the SAME failure (proven, not assumed - it binds a plain
    `Session(bind=connection)` with no `join_transaction_mode`, so its OWN `.rollback()`
    also lands on the connection rather than a savepoint of its own).
    `_savepoint_session()` is the one shape that survives it: see its own docstring.
    """
    from app.services.download_service import DownloadService
    from app.services.scm import summary_order_service
    from app.tasks import export_tasks

    with _savepoint_session() as db:
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
        # A FRESH read, off the same session but a new query - not the stale, possibly
        # expired ORM instance `create()` returned.
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
