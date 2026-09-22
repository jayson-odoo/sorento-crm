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
    _sorento,
    _uid,
    _user,
    api,
)

__all__ = ["api"]  # re-exported fixture

HEADERS_BASE = f"{BASE}/order-inquiries"


def _grant_view_permission(db, user_id: str) -> None:
    """Give `user_id` a real role carrying `projects.projects.view` (AC-B7's own
    `VIEW`), seeded directly in the caller's scratch-schema session so an
    `X-API-Key`-only request that DID resolve to a real, permitted user would still
    succeed - proving the refusal the AC-B7 tests assert is about the AUTH METHOD,
    never a missing grant. Mirrors `tests/scm/test_order_sheet_export_downloads.py:
    288-292`'s own role assignment, adapted for `blank_session`'s isolated scratch
    schema: that sibling test looks up an ALREADY-seeded `purchasing` role by slug on
    the shared local Postgres (`scm_app`'s own substrate); a blank scratch schema has
    no seeded RBAC rows at all, so the role/permission/grant are built here instead of
    looked up."""
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment

    role = UserRole(id=_uid(), slug=f"{MARKER}-role-{_uid()[:8]}", name=f"{MARKER} role {_uid()[:8]}")
    permission = (
        db.query(UserPermission).filter(UserPermission.slug == "projects.projects.view").first()
    )
    if permission is None:
        permission = UserPermission(
            id=_uid(), slug="projects.projects.view", name="Projects: view",
        )
        db.add(permission)
        db.flush()
    db.add(role)
    db.flush()
    db.add(UserRolePermission(id=_uid(), role_id=role.id, permission_id=permission.id))
    db.add(UserRoleAssignment(id=_uid(), user_id=user_id, role_id=role.id))
    db.flush()


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


def test_detail_export_post_rejects_api_key_only_principal_AC_B7():
    """AC-B7 / security (matches the order sheet's own S4 rule and its own test,
    `tests/scm/test_order_sheet_export_downloads.py::
    test_export_post_rejects_api_key_only_principal`): a write endpoint is never
    reachable by `X-API-Key` alone - `require_permission` (JWT-only
    `get_current_user`) is what the route must gate on.

    Deliberately does NOT use the `api` fixture: its `_client` overrides BOTH
    `get_current_user` AND `get_current_user_or_api_key` unconditionally for the
    whole test body, which would make ANY dependency choice answer 200 regardless
    of the header sent - exactly the flaw the sibling test's own docstring calls
    out `as_user` for ("overrides both current-user dependencies unconditionally
    and would hide this"). Only `get_db` is overridden here; a REAL, resolvable
    integration key sent with NO Authorization header proves the refusal is about
    the AUTH METHOD, not a missing permission or an unresolvable key.

    Correctness review fix round 3, item 1 (BLOCKER): the integration user MUST
    carry the `VIEW` permission for real (`_grant_view_permission`) - without it the
    401/403 this test asserts is ambiguous between "wrong auth method" and "right
    auth method, no grant", and `require_permission_with_api_key` (the WRONG,
    api-key-accepting dependency) answers 403 here too, for want of a role, hiding
    exactly the defect this test exists to catch.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.models.integration import Integration  # noqa: F401
    from app.models.user import User
    from app.services import project_seed_service
    from app.services.integration_key_service import IntegrationKeyService

    from ._pg_fixture import blank_session

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        seeded = _header(db, company_id)
        inquiry_id = seeded["inquiry"].id

        user = User(
            id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} integration",
            status="ACTIVE", is_integration=True,
        )
        db.add(user)
        db.flush()
        _grant_view_permission(db, user.id)
        integration = Integration(
            id=_uid(), name=f"{MARKER}-{_uid()[:8]}", type="autocount_esb",
            act_as_user_id=user.id, is_active=True,
        )
        db.add(integration)
        db.flush()
        key = IntegrationKeyService(db).issue_key(integration)
        db.flush()

        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.post(
                    f"{HEADERS_BASE}/{inquiry_id}/export",
                    headers={"X-API-Key": key},
                )

            assert resp.status_code in (401, 403), resp.text
            count = db.execute(text(
                "SELECT count(*) FROM user_downloads WHERE source_entity_id = :id"
            ), {"id": inquiry_id}).scalar()
            assert count == 0, "an API-key-only caller was allowed to create a download row"
        finally:
            app.dependency_overrides.clear()


def test_worklist_export_post_rejects_api_key_only_principal_AC_B7():
    """AC-B7, the list-page POST's own version of the test above - same reasoning,
    same fixture shape (no unconditional override of both current-user
    dependencies), a different route (`POST /order-inquiries/export`, no source
    entity).

    Correctness review fix round 3, item 1: same real `VIEW` grant as the detail
    test above - see its docstring for why."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.models.integration import Integration  # noqa: F401
    from app.models.user import User
    from app.services import project_seed_service
    from app.services.integration_key_service import IntegrationKeyService

    from ._pg_fixture import blank_session

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _header(db, company_id)

        user = User(
            id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} integration",
            status="ACTIVE", is_integration=True,
        )
        db.add(user)
        db.flush()
        _grant_view_permission(db, user.id)
        integration = Integration(
            id=_uid(), name=f"{MARKER}-{_uid()[:8]}", type="autocount_esb",
            act_as_user_id=user.id, is_active=True,
        )
        db.add(integration)
        db.flush()
        key = IntegrationKeyService(db).issue_key(integration)
        db.flush()

        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.post(
                    f"{HEADERS_BASE}/export",
                    headers={"X-API-Key": key},
                    json={},
                )

            assert resp.status_code in (401, 403), resp.text
            count = db.execute(text(
                "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
            )).scalar()
            assert count == 0, "an API-key-only caller was allowed to create a download row"
        finally:
            app.dependency_overrides.clear()


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
    # filters dict, then user id - the route's own contract.
    assert call["args"][1] == {"state": "raised"}, call["args"]
    assert call["args"][-1] == row["user_id"], call["args"]
    # The requesting session's own single-company scope travels as an explicit
    # `company_id` kwarg (`generate_promotions_pdf`'s own shape) - the worklist export
    # names no single header a worker task could otherwise adopt a company from.
    assert call["kwargs"] == {
        "company_id": company_id, "queue_name": "imports", "job_timeout": 600,
    }, call["kwargs"]


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
# Security review fix round 2, item 1: the worklist POST's filters must be
# validated the SAME way the GET route's own query params are - a malformed
# `project_id`/`supplier_id`/`agent`, an over-long `query`, or a `state` outside the
# closed set answers 4xx IN-REQUEST, before any `user_downloads` row exists.
# =========================================================================== #


def test_worklist_export_post_rejects_bad_project_id_AC_B6_validation(api):
    client, db, company_id = api
    _header(db, company_id)

    resp = client.post(f"{HEADERS_BASE}/export", json={"project_id": "not-a-uuid"})

    assert resp.status_code in (400, 422), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 0, "a malformed filter must not create a download row"


def test_worklist_export_post_rejects_bad_supplier_id_AC_B6_validation(api):
    client, db, company_id = api
    _header(db, company_id)

    resp = client.post(f"{HEADERS_BASE}/export", json={"supplier_id": "not-a-uuid"})

    assert resp.status_code in (400, 422), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 0


def test_worklist_export_post_rejects_bad_agent_AC_B6_validation(api):
    client, db, company_id = api
    _header(db, company_id)

    resp = client.post(f"{HEADERS_BASE}/export", json={"agent": "not-a-uuid"})

    assert resp.status_code in (400, 422), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 0


def test_worklist_export_post_rejects_overlong_query_AC_B6_validation(api):
    client, db, company_id = api
    _header(db, company_id)

    resp = client.post(f"{HEADERS_BASE}/export", json={"query": "x" * 500})

    assert resp.status_code == 422, resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 0


def test_worklist_export_post_rejects_bad_state_AC_B6_validation(api):
    client, db, company_id = api
    _header(db, company_id)

    resp = client.post(f"{HEADERS_BASE}/export", json={"state": "bogus"})

    assert resp.status_code == 422, resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE kind = 'order_inquiry_worklist_xlsx'"
    )).scalar()
    assert count == 0


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


# =========================================================================== #
# Security review fix round 2, item 2 (mirrors `tests/scm/test_order_sheet_export_
# downloads.py::test_generate_order_sheet_fails_closed_when_the_run_has_no_company`,
# Lane A fix round 2, sha 002fd3d2e on `fix/order-sheet-cells`): a header with a NULL
# `company_id` must not export under the `None` (all-companies) scope the task starts
# under while it looks the header up - it fails closed, never silently.
# =========================================================================== #


def test_generate_order_inquiry_xlsx_fails_closed_when_the_header_has_no_company(
    api, monkeypatch,
):
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    client, db, company_id = api
    seeded = _header(db, company_id)
    inquiry_id = seeded["inquiry"].id
    db.execute(text(
        "UPDATE order_inquiries SET company_id = NULL WHERE id = :id"
    ), {"id": inquiry_id})
    user_id = _user(db, f"{MARKER} exporter-nocompany")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="OI-nocompany.xlsx",
    )

    calls: list[dict] = []

    def _spy_export(self, **filters):
        calls.append(filters)
        return ("OI-nocompany.xlsx", b"fake-bytes")

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _spy_export)

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id)

    assert result["status"] == "failed", result
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "failed", row.status
    assert not row.storage_key, "no bytes may be uploaded for a company-less header"
    assert calls == [], "the render must never run for a company-less header"


def test_generate_order_inquiry_xlsx_fails_closed_when_the_header_does_not_exist(
    monkeypatch,
):
    """The other half: an `inquiry_id` that names no row at all must also fail closed
    rather than export under `None` (all companies)."""
    from app.services.download_service import DownloadService
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
    from app.tasks import export_tasks

    from ._pg_fixture import blank_session

    with blank_session() as db:
        missing_inquiry_id = _uid()
        user_id = _user(db, f"{MARKER} exporter-missing")
        db.flush()

        dl = DownloadService(db).create(
            user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
            source_entity_id=missing_inquiry_id, filename="OI-missing.xlsx",
        )

        calls: list[dict] = []

        def _spy_export(self, **filters):
            calls.append(filters)
            return ("OI-missing.xlsx", b"fake-bytes")

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        monkeypatch.setattr(OrderInquiryWorklistService, "export_xlsx", _spy_export)

        result = export_tasks.generate_order_inquiry_xlsx(
            str(dl.id), missing_inquiry_id, user_id,
        )

        assert result["status"] == "failed", result
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "failed", row.status
        assert calls == [], "the render must never run for a missing header"


def test_generate_order_inquiry_xlsx_real_render_sees_the_headers_own_row(api, monkeypatch):
    """Correctness review fix round 3, item 2: the worker's company adoption exercised
    through a REAL `export_xlsx` render - no monkeypatch on it - so the assertion is
    that the ADOPTED SCOPE actually let the render see the seeded row, not merely that
    a mocked function was called with the right arguments. The negative half (a
    company-less header) is already covered, more strongly, by the two fail-closed
    tests above: since fix round 2 that header now REFUSES to render at all (raises,
    `export_xlsx` never called) rather than rendering an empty book, so there is no
    separate "renders empty" case left to prove for this task.

    Reviewer round 2, item 1 (should-fix): this task reads the header under the
    BROAD `None` scope first (deliberately, to find it regardless of caller scope)
    and only narrows afterward - the render is scoped to exactly this one
    `inquiry_id` regardless, so row VISIBILITY cannot tell "narrowed to the header's
    own company" apart from "still broad `None`" (both show the row; a different
    company's own, differently-`inquiry_id`'d row would never show either way, since
    the query is already narrowed by id). A spy on `set_company_scope` is what
    actually proves the narrowing call ran, with the right argument - genuinely red
    under the reviewer's `if False:` mutation around it (verified, reverted), where
    the row-visibility assertion alone was not.
    """
    import io

    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    import openpyxl

    client, db, company_id = api
    item_code = f"{MARKER}-REALITEM"
    seeded = _header(db, company_id, rows=[{"item_code": item_code}])
    inquiry_id = seeded["inquiry"].id
    user_id = _user(db, f"{MARKER} exporter-real")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_xlsx", source_entity_type="order_inquiry",
        source_entity_id=inquiry_id, filename="OI-real.xlsx",
    )

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            captured["bytes"] = file_content
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    scope_calls: list = []
    real_set_company_scope = export_tasks.set_company_scope

    def _spy_set_company_scope(db_, scope):
        scope_calls.append(scope)
        return real_set_company_scope(db_, scope)

    monkeypatch.setattr(export_tasks, "set_company_scope", _spy_set_company_scope)

    result = export_tasks.generate_order_inquiry_xlsx(str(dl.id), inquiry_id, user_id)

    assert result["status"] == "ready", result
    assert frozenset({str(company_id)}) in scope_calls, (
        "the task must narrow the scope to the header's own company"
    )
    wb = openpyxl.load_workbook(io.BytesIO(captured["bytes"]))
    values = [
        cell.value for sheet in wb.worksheets for row in sheet.iter_rows() for cell in row
    ]
    assert item_code in values, "the adopted company scope must let the render see the row"


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


def test_generate_order_inquiry_worklist_xlsx_real_render_with_company_id_kwarg(
    api, monkeypatch,
):
    """Correctness review fix round 3, item 2: a REAL `export_xlsx` render (no
    monkeypatch on it) with `company_id` set to the caller's own company - the
    seeded row's item code must be in the workbook bytes, proving the adopted scope
    actually let the render see it.

    Reviewer round 2, item 1 (should-fix): `set_company_scope(db, UNSET)` runs right
    before the task call, for the same reason the per-header test's own twin does -
    the `api` fixture already has `db` scoped to this company for the whole test, so
    without this the assertion would pass even if `company_id` were never adopted.
    """
    import io

    import openpyxl

    from app.models.base import UNSET, set_company_scope
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    client, db, company_id = api
    item_code = f"{MARKER}-WLREALITEM"
    _header(db, company_id, rows=[{"item_code": item_code}])
    user_id = _user(db, f"{MARKER} exporter-real-wl")
    db.flush()

    dl = DownloadService(db).create(
        user_id=user_id, kind="order_inquiry_worklist_xlsx",
        filename="order-inquiries-real.xlsx",
    )

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    captured: dict = {}

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            captured["bytes"] = file_content
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

    set_company_scope(db, UNSET)
    result = export_tasks.generate_order_inquiry_worklist_xlsx(
        str(dl.id), {}, user_id, company_id=str(company_id),
    )

    assert result["status"] == "ready", result
    wb = openpyxl.load_workbook(io.BytesIO(captured["bytes"]))
    values = [
        cell.value for sheet in wb.worksheets for row in sheet.iter_rows() for cell in row
    ]
    assert item_code in values, "the adopted company scope must let the render see the row"


def test_generate_order_inquiry_worklist_xlsx_real_render_with_no_company_id_sees_nothing(
    monkeypatch,
):
    """The other half: `company_id=None` (the default - a caller with no
    single-company scope) must render under the worker's fail-closed UNSET default,
    never a broader one - the seeded row must NOT appear. Uses a fresh
    `blank_session()` rather than the `api` fixture, whose own `company_scope`
    context manager would otherwise leave the session scoped to that fixture's
    company even though this call passes no `company_id` at all - a false pass.

    `set_company_scope(db, UNSET)` runs right before the task call, after every
    seed: `tests/conftest.py`'s own `after_begin` listener defaults an UNTOUCHED
    session's scope to Sorento for legacy-test convenience (`session.info.
    setdefault(...)`, never production's real default), so without this the test
    would inherit that convenience scope - which happens to be the SAME company
    the row was seeded under - and pass for the wrong reason, exactly the gap this
    test exists to close. A real, untouched `SessionLocal()` in production starts
    with no such default.
    """
    import io

    import openpyxl

    from app.models.base import UNSET, set_company_scope
    from app.services import project_seed_service
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    from ._pg_fixture import blank_session

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        item_code = f"{MARKER}-WLNOCOMPANY"
        _header(db, company_id, rows=[{"item_code": item_code}])
        user_id = _user(db, f"{MARKER} exporter-nocompany-wl")
        db.flush()

        dl = DownloadService(db).create(
            user_id=user_id, kind="order_inquiry_worklist_xlsx",
            filename="order-inquiries-nocompany.xlsx",
        )
        set_company_scope(db, UNSET)

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        captured: dict = {}

        class _FakeBackend:
            def upload_file(self, *, file_content, file_path, content_type):
                captured["bytes"] = file_content
                return (file_path, None)

        monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
        monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())

        result = export_tasks.generate_order_inquiry_worklist_xlsx(
            str(dl.id), {}, user_id,
        )

        assert result["status"] == "ready", result
        wb = openpyxl.load_workbook(io.BytesIO(captured["bytes"]))
        values = [
            cell.value for sheet in wb.worksheets for row in sheet.iter_rows() for cell in row
        ]
        assert item_code not in values, "a company-less caller must not see any company's rows"


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
