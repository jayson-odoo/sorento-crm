"""Lane B - OI detail Export Excel goes async, tied to the OI; the OI LIST page's Export
Excel also goes async (`PLAN-order-sheet-oi-reports-22sep.md` Lane B,
`order-sheet-oi-reports-22sep-acceptance-criteria.md` AC-B1..AC-B7).

TEST-FIRST (Phase 2): written against the UAC + the plan's Lane B contract + the Phase 1
contract doc, with NO implementation to look at. None of `POST /order-inquiries/{id}/
export`, `POST /order-inquiries/export`, `app.tasks.export_tasks.
generate_order_inquiry_xlsx` or `generate_order_inquiry_worklist_xlsx` exist yet - every
test below must fail today for a REAL reason (404 - the route is not mounted -,
AttributeError - the task does not exist -, or a fixture that itself proves the point,
never an import typo).

Pattern copied from `tests/scm/test_order_sheet_export_downloads.py` (the order sheet's
own async-download slice) and `tests/test_oi_header_list.py` / `tests/
test_oi_header_detail_and_actions.py` (OI seeding + the override-based `_client`).

Postgres only (`tests/_pg_fixture.py::blank_session` - an EMPTY scratch schema), never
sqlite. Every test seeds its own OI header + rows; nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

from sqlalchemy import text

from .test_oi_header_list import (
    BASE,
    MARKER,
    _header,
    _uid,
    _user,
    api,
)

__all__ = ["api"]  # re-exported fixture

HEADERS_BASE = f"{BASE}/order-inquiries"


class _NoCloseSession:
    """Lets a task function's own ``SessionLocal()`` reuse the test's rolled-back
    savepoint session instead of opening a real, separate connection that cannot see
    the test's uncommitted seed data. Copied from `tests/scm/test_order_sheet_export_
    downloads.py` (its own docstring explains why this shape is required)."""

    def __init__(self, inner):
        self._inner = inner

    def close(self):  # noqa: D401 - the test owns the session's lifetime
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


# =========================================================================== #
# AC-B1 / AC-B7: POST /order-inquiries/{inquiry_id}/export
# =========================================================================== #


def test_detail_export_post_creates_download_row_and_enqueues_AC_B1(api, monkeypatch):
    """A `user_downloads` row is created (`kind=order_inquiry_xlsx`,
    `source_entity_type=order_inquiry`, `source_entity_id=<inquiry id>`, filename
    `<inquiry_no>.xlsx`) and `generate_order_inquiry_xlsx` is enqueued on the `imports`
    queue with a 600s timeout, exactly the OI id + actor the task's signature expects."""
    from app.services import queue_service
    from fastapi.testclient import TestClient

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id
    inquiry_no = seeded["inquiry"].inquiry_no

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})

        class _Job:
            id = "fake-job-id"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    resp = client.post(f"{HEADERS_BASE}/{inquiry_id}/export")

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["kind"] == "order_inquiry_xlsx", body
    assert body["status"] == "pending", body

    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id, "
        "       filename, status, user_id "
        "FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "order_inquiry_xlsx"
    assert row["source_entity_type"] == "order_inquiry"
    assert row["source_entity_id"] == inquiry_id
    assert row["filename"] == f"{inquiry_no}.xlsx", row["filename"]

    assert len(calls) == 1, f"expected exactly one enqueue, got {calls}"
    call = calls[0]
    from app.tasks.export_tasks import generate_order_inquiry_xlsx

    assert call["func"] is generate_order_inquiry_xlsx, call["func"]
    assert call["args"] == (body["id"], inquiry_id, row["user_id"]), call["args"]
    assert call["kwargs"] == {"queue_name": "imports", "job_timeout": 600}, call["kwargs"]


def test_detail_export_post_404_for_unknown_inquiry_creates_no_row_AC_B1(api):
    client, db, _company_id = api
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    resp = client.post(f"{HEADERS_BASE}/{_uid()}/export")

    assert resp.status_code == 404, resp.text
    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a 404 guard left a download row behind"


def test_detail_export_post_409_while_one_is_in_flight_AC_B3(api, monkeypatch):
    """A second click while the SAME OI's export is pending/processing starts nothing -
    409, and the message names "My Downloads" (matches the order sheet's own wording)."""
    from app.services import queue_service

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id

    monkeypatch.setattr(
        queue_service, "enqueue_job",
        lambda *a, **k: type("J", (), {"id": "x"})(),
    )

    first = client.post(f"{HEADERS_BASE}/{inquiry_id}/export")
    assert first.status_code in (200, 201), first.text

    second = client.post(f"{HEADERS_BASE}/{inquiry_id}/export")
    assert second.status_code == 409, second.text
    assert "my downloads" in second.text.lower(), second.text

    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :id "
        "AND kind = 'order_inquiry_xlsx'"
    ), {"id": inquiry_id}).scalar()
    assert count == 1, f"a second export must not create a second row: {count}"


def test_detail_export_post_marks_failed_and_503_when_enqueue_raises_AC_B4(api, monkeypatch):
    from app.services import queue_service

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id

    def _boom(*a, **k):
        raise RuntimeError("redis is away")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    resp = client.post(f"{HEADERS_BASE}/{inquiry_id}/export")

    assert resp.status_code == 503, resp.text
    row = db.execute(text(
        "SELECT status, error FROM user_downloads WHERE source_entity_id = :id"
    ), {"id": inquiry_id}).mappings().first()
    assert row is not None, "no download row was created before the enqueue attempt"
    assert row["status"] == "failed", row["status"]
    assert row["error"], "no error message was recorded"


def test_detail_export_post_rejects_api_key_only_principal_AC_B7(api):
    """AC-B7 / security (matches the order sheet's own S4 rule): a write endpoint is
    never reachable by `X-API-Key` alone. `require_permission` (JWT-only
    `get_current_user`) is what the route must gate on - a real, resolvable integration
    key sent with NO Authorization header proves the refusal is about the AUTH METHOD,
    not a missing permission, because `check_user_has_permission` is stubbed to always
    grant it (the SAME override `api`'s own `_client` installs) - a route that DID
    accept an api-key principal would sail straight through it and answer 200."""
    from app.models.integration import Integration  # noqa: F401
    from app.models.user import User, UserRoleAssignment
    from app.services.integration_key_service import IntegrationKeyService

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id

    user = User(
        id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} integration",
        status="ACTIVE", is_integration=True,
    )
    db.add(user)
    db.flush()
    integration = Integration(
        id=_uid(), name=f"{MARKER}-{_uid()[:8]}", type="autocount_esb",
        act_as_user_id=user.id, is_active=True,
    )
    db.add(integration)
    db.flush()
    key = IntegrationKeyService(db).issue_key(integration)
    db.flush()

    resp = client.post(
        f"{HEADERS_BASE}/{inquiry_id}/export",
        headers={"X-API-Key": key},
    )

    assert resp.status_code in (401, 403), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :id"
    ), {"id": inquiry_id}).scalar()
    assert count == 0, "an API-key-only caller was allowed to create a download row"


# =========================================================================== #
# AC-B6: POST /order-inquiries/export (list page, no source entity)
# =========================================================================== #


def test_worklist_export_post_creates_download_row_and_enqueues_AC_B6(api, monkeypatch):
    from app.services import queue_service

    client, db, company_id = api
    _header(db, company_id)

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})

        class _Job:
            id = "fake-job-id"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    resp = client.post(f"{HEADERS_BASE}/export", json={"state": "raised"})

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["kind"] == "order_inquiry_worklist_xlsx", body

    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id, filename, user_id "
        "FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None
    assert row["kind"] == "order_inquiry_worklist_xlsx"
    assert row["source_entity_type"] is None, row["source_entity_type"]
    assert row["source_entity_id"] is None, row["source_entity_id"]
    import re
    assert re.match(r"^order-inquiries-\d{8}\.xlsx$", row["filename"] or ""), row["filename"]

    assert len(calls) == 1, calls
    call = calls[0]
    from app.tasks.export_tasks import generate_order_inquiry_worklist_xlsx

    assert call["func"] is generate_order_inquiry_worklist_xlsx, call["func"]
    assert call["args"][0] == body["id"], call["args"]
    # filters dict, then user id - the route's own contract (brief: "filters: dict").
    assert call["args"][1] == {"state": "raised"} or (
        isinstance(call["args"][1], dict) and call["args"][1].get("state") == "raised"
    ), call["args"]
    assert call["args"][-1] == row["user_id"], call["args"]
    assert call["kwargs"] == {"queue_name": "imports", "job_timeout": 600}, call["kwargs"]


def test_worklist_export_post_409_while_one_is_in_flight_no_source_entity_AC_B3(
    api, monkeypatch,
):
    """The in-flight guard applies with NO source entity too - a second click while one
    worklist export is queued must start nothing, even though `source_entity_type`/
    `source_entity_id` are both NULL for this kind."""
    from app.services import queue_service

    client, db, company_id = api
    _header(db, company_id)

    monkeypatch.setattr(
        queue_service, "enqueue_job",
        lambda *a, **k: type("J", (), {"id": "x"})(),
    )

    first = client.post(f"{HEADERS_BASE}/export", json={})
    assert first.status_code in (200, 201), first.text

    second = client.post(f"{HEADERS_BASE}/export", json={})
    assert second.status_code == 409, second.text

    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 1, f"a second worklist export must not create a second row: {count}"


def test_worklist_export_post_marks_failed_and_503_when_enqueue_raises_AC_B4(
    api, monkeypatch,
):
    from app.services import queue_service

    client, db, company_id = api
    _header(db, company_id)

    def _boom(*a, **k):
        raise RuntimeError("redis is away")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    resp = client.post(f"{HEADERS_BASE}/export", json={})

    assert resp.status_code == 503, resp.text
    row = db.execute(text(
        "SELECT status, error FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).mappings().first()
    assert row is not None
    assert row["status"] == "failed", row["status"]
    assert row["error"], "no error message was recorded"


def test_worklist_get_export_route_still_answers_AC_B6_transitional(api):
    """B1b, R4: the old sync `GET /order-inquiries/export` stays for one release (MCP /
    other callers) - it must still answer 200 with an xlsx body, not be retired by the
    same change that adds the async POST."""
    client, db, company_id = api
    _header(db, company_id)

    resp = client.get(f"{HEADERS_BASE}/export")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ), resp.headers["content-type"]


# =========================================================================== #
# AC-B2: the tasks
# =========================================================================== #


def test_generate_order_inquiry_xlsx_marks_ready_AC_B2(api, monkeypatch):
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id
    user_id = _user(db, f"{MARKER} exporter")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="OI-2609-0001.xlsx",
    )

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(
        OrderInquiryWorklistService, "export_xlsx",
        lambda self, **filters: ("OI-2609-0001.xlsx", b"fake-bytes"),
    )

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id)

    assert result["status"] == "ready", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"
    assert f"exports/order-inquiry/{dl.id}/" in row.storage_key, row.storage_key
    assert row.filename == "OI-2609-0001.xlsx"


def test_generate_order_inquiry_xlsx_marks_failed_when_export_raises_AC_B2(api, monkeypatch):
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id
    user_id = _user(db, f"{MARKER} exporter2")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="OI-2609-0001.xlsx",
    )

    def _boom(self, **filters):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _boom)

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id)

    assert result["status"] == "failed", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "failed", row.status
    assert "render exploded" in (row.error or ""), row.error


def test_generate_order_inquiry_worklist_xlsx_marks_ready_AC_B2(api, monkeypatch):
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    client, db, company_id = api
    _header(db, company_id)
    user_id = _user(db, f"{MARKER} exporter3")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_worklist_xlsx",
        filename="order-inquiries-23092026.xlsx",
    )

    seen_filters: list[dict] = []

    def _fake_export(self, **filters):
        seen_filters.append(filters)
        return ("order-inquiries-23092026.xlsx", b"fake-bytes")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _fake_export)

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    result = export_tasks.generate_order_inquiry_worklist_xlsx(
        str(dl.id), {"state": "raised"}, user_id,
    )

    assert result["status"] == "ready", result
    assert seen_filters and seen_filters[0].get("state") == "raised", seen_filters
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"


def test_generate_order_inquiry_worklist_xlsx_marks_failed_when_export_raises_AC_B2(
    api, monkeypatch,
):
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    client, db, company_id = api
    _header(db, company_id)
    user_id = _user(db, f"{MARKER} exporter4")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_worklist_xlsx",
        filename="order-inquiries-23092026.xlsx",
    )

    def _boom(self, **filters):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _boom)

    result = export_tasks.generate_order_inquiry_worklist_xlsx(
        str(dl.id), {}, user_id,
    )

    assert result["status"] == "failed", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "failed", row.status
    assert "render exploded" in (row.error or ""), row.error


# =========================================================================== #
# AC-B5: My Downloads scoped to one OI (this route already exists generically -
# pinning behaviour, expected to pass once B1 exists to create real rows of this kind)
# =========================================================================== #


def test_downloads_list_scoped_to_one_order_inquiry_AC_B5(api):
    from app.services.download_service import DownloadService

    client, db, company_id = api
    one = _header(db, company_id)
    other = _header(db, company_id)
    user_id = _user(db, f"{MARKER} downloads-viewer")
    db.flush()

    svc = DownloadService(db)
    row_one = svc.create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=one["inquiry"].id, filename=f"{one['inquiry'].inquiry_no}.xlsx",
    )
    svc.create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=other["inquiry"].id, filename=f"{other['inquiry'].inquiry_no}.xlsx",
    )

    # This route reads `current_user["id"]`, not the `api` fixture's own actor - so
    # authenticate AS the row owner for this one assertion.
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "x@zzt.test"}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": user_id, "email": "x@zzt.test",
    }
    resp = client.get(
        "/api/v1/downloads",
        params={
            "source_entity_type": "order_inquiry",
            "source_entity_id": one["inquiry"].id,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [d["id"] for d in body["downloads"]]
    assert row_one.id in ids
    assert all(d["source_entity_id"] == one["inquiry"].id for d in body["downloads"]), body
