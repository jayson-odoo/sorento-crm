"""Asynchronous quotation exports (PDF / Excel) landing in My Downloads.

The client's complaint was about the WAIT: pressing Download PDF held the browser while
WeasyPrint rendered a 50-page quotation, and a slow render read as a broken button. So the
export becomes a queued job, exactly as the complaint PDF already is - the route creates a
``user_downloads`` row and returns it, the worker renders and uploads, and the user picks the
file up from the printer chip on the document.

What is worth pinning here, and why:

- **The route returns a row, not bytes.** That is the whole change. A route that still
  rendered inline would pass a "did it 200" assertion and reintroduce the wait.
- **A queue failure lands as a FAILED row, not a 500.** Redis being down must leave a
  readable trace in the drawer rather than a stack trace the user cannot act on.
- **A render failure marks the row failed and never raises.** Raising would poison RQ's
  failed registry and leave the row stuck on 'processing' forever, which is indistinguishable
  from a slow render.
- **The row is findable by its source issue**, because the printer chip on the document is a
  per-entity query and nothing else makes it appear there.
- **Permission and cross-document scoping match the synchronous routes**, which are still
  mounted: a quotation export is the full price list either way, so making it async must not
  quietly widen who can ask for one.

Postgres only, via ``blank_session``. Every row carries the ``zzt-qdownload`` marker so
nothing here can be confused with the real data the dev database holds.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.download import DownloadStatus, UserDownload
from app.models.numbering import DocumentNumberingRule
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-qdownload"

BASE = "/api/v1/project-sales"

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"

ALL_SLUGS = [
    VIEW,
    "projects.projects.create",
    EDIT,
    DELETE,
    "projects.projects.manage",
    "projects.types.view",
    "projects.types.edit",
]

PRICED_RATE = "250.00"


# ------------------------------------------------------------------------ seed


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _category(db, name: str) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str) -> Product:
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} WC Suite",
        description="Close-coupled WC suite, white",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _party(db, company_id: str) -> ProjectParty:
    row = ProjectParty(
        id=_uid(),
        company_id=company_id,
        party_type="developer",
        name=f"{MARKER} Nadi Cergas {_uid()[:6]}",
        address=f"{MARKER} Level 8, Menara Lama, Kuala Lumpur",
        phone="03-1111 1111",
    )
    db.add(row)
    db.flush()
    return row


def _numbering_rule(db, company_id: str) -> DocumentNumberingRule:
    """Seed the `project_quotation` rule rather than borrowing one: CI's database is empty."""
    scoped = hasattr(DocumentNumberingRule, "company_id")

    query = db.query(DocumentNumberingRule).filter(
        DocumentNumberingRule.doc_type == "project_quotation"
    )
    if scoped:
        query = query.filter(DocumentNumberingRule.company_id == company_id)
    rule = query.first()

    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type="project_quotation")
        if scoped:
            rule.company_id = company_id
        db.add(rule)

    rule.enabled = True
    rule.prefix_template = f"{MARKER}/Q/"
    rule.number_digits = 4
    rule.next_value = 1
    rule.start_value = 1
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()
    return rule


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(ALL_SLUGS)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@contextmanager
def _without_permission(slug: str):
    from app.services.user_service import UserPermissionService

    granted = [s for s in ALL_SLUGS if s != slug]
    original_check = UserPermissionService.check_user_has_permission
    original_slugs = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, wanted, _denied=slug: wanted != _denied
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    try:
        yield
    finally:
        UserPermissionService.check_user_has_permission = original_check
        UserPermissionService.get_user_permission_slugs = original_slugs


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        user_id = _user(db, f"{MARKER} Baser")
        party = _party(db, company_id)
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=user_id,
            developer_party_id=party.id,
            title=f"{MARKER} Cabana Elmina {_uid()[:12]}",
        )
        db.commit()
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, user_id, project
        finally:
            _restore(originals)


# --------------------------------------------------------------------- helpers


def _create_document(client, project_id: str) -> dict:
    response = client.post(f"{BASE}/projects/{project_id}/quotation-documents", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _add_scope(client, project_id: str, document_id: str, label: str) -> dict:
    response = client.post(
        f"{BASE}/projects/{project_id}/quotation-documents/{document_id}/scopes",
        json={"scope_label": label},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _current_version_id(db, quotation_id: str) -> str:
    from app.services import project_quotation_service as quotes

    return quotes.current_version(db, quotation_id).id


def _sign(client, root: str, document_id: str) -> None:
    response = client.post(
        f"{root}/{document_id}/sign",
        json={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": "data:image/png;base64,zzt",
        },
    )
    assert response.status_code == 201, response.text


def _issue_one(client, db, project) -> tuple:
    """A signed, issued document with one priced line. Returns ``(root, document, issue)``."""
    uom = _uom(db)
    category = _category(db, "Sanitary Ware")
    product = _product(db, category.id, uom, "300.00")
    db.commit()

    root = f"{BASE}/projects/{project.id}/quotation-documents"
    document = _create_document(client, project.id)
    scope = _add_scope(client, project.id, document["id"], f"{MARKER} Townhouse")
    added = client.post(
        f"{BASE}/quotation-versions/{_current_version_id(db, scope['id'])}/lines",
        json={"product_id": product.id, "unit_price": PRICED_RATE, "quantity": "4"},
    )
    assert added.status_code == 201, added.text
    _sign(client, root, document["id"])
    issued = client.post(f"{root}/{document['id']}/issue")
    assert issued.status_code == 201, issued.text
    return root, document, issued.json()


class _RecordingQueue:
    """Stand-in for ``enqueue_job`` that records the call instead of touching Redis.

    A test that let the real one run would need a Redis and would then race a worker for the
    row it is asserting on. What the route owes is the enqueue itself, with the right task and
    the right arguments; the task's own behaviour is proved separately below.
    """

    def __init__(self, explode: bool = False):
        self.calls: list[tuple] = []
        self.explode = explode

    def __call__(self, func, *args, **kwargs):
        self.calls.append((func, args, kwargs))
        if self.explode:
            raise RuntimeError("Error 111 connecting to redis:6379. Connection refused.")
        return type("_Job", (), {"id": "zzt-job"})()


@pytest.fixture()
def queued(monkeypatch):
    recorder = _RecordingQueue()
    monkeypatch.setattr("app.services.queue_service.enqueue_job", recorder)
    return recorder


def _downloads(db, user_id: str) -> list[UserDownload]:
    from app.services.download_service import DownloadService

    return DownloadService(db).list_for_user(user_id)


# ------------------------------------------------------- the trigger routes


def test_the_pdf_export_route_answers_with_a_pending_row_rather_than_bytes(api, queued):
    """The point of the whole change: the caller is handed a receipt, not a rendered file.

    A 50-page quotation takes WeasyPrint long enough that the old inline route read as a dead
    button, so the contract is now "queued, look in My Downloads". The row has to come back
    already persisted and already `pending`, because the printer chip renders from it
    immediately and an unsaved row would show nothing until the worker got round to it.
    """
    client, db, _company_id, user_id, project = api
    root, document, issue = _issue_one(client, db, project)

    response = client.post(
        f"{root}/{document['id']}/issues/{issue['id']}/export/pdf"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == DownloadStatus.PENDING.value
    assert body["kind"] == "quotation_pdf"
    assert body["source_entity_type"] == "quotation_issue"
    assert body["source_entity_id"] == issue["id"]
    assert body["filename"].endswith(".pdf")
    # Not application/pdf: nothing rendered in the request path.
    assert response.headers["content-type"].startswith("application/json")

    rows = _downloads(db, user_id)
    assert [r.id for r in rows] == [body["id"]]

    (func, args, kwargs) = queued.calls[0]
    assert func.__name__ == "generate_quotation_issue_pdf"
    assert args[0] == body["id"]
    assert args[1] == issue["id"]
    assert args[2] == user_id
    assert kwargs["queue_name"] == "imports"


def test_the_excel_export_route_answers_with_its_own_pending_row(api, queued):
    """Two artifacts, two rows, two kinds. One row reused for both would make the drawer
    unable to say which format is ready, and the second request would overwrite the first
    file under the same storage key."""
    client, db, _company_id, user_id, project = api
    root, document, issue = _issue_one(client, db, project)

    response = client.post(
        f"{root}/{document['id']}/issues/{issue['id']}/export/xlsx"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == DownloadStatus.PENDING.value
    assert body["kind"] == "quotation_xlsx"
    assert body["source_entity_type"] == "quotation_issue"
    assert body["source_entity_id"] == issue["id"]
    assert body["filename"].endswith(".xlsx")

    (func, args, _kwargs) = queued.calls[0]
    assert func.__name__ == "generate_quotation_issue_xlsx"
    assert args[1] == issue["id"]

    # Asking for both leaves two distinct rows, not one row mutated twice.
    again = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf")
    assert again.status_code == 200, again.text
    kinds = sorted(r.kind for r in _downloads(db, user_id))
    assert kinds == ["quotation_pdf", "quotation_xlsx"]


def test_a_queue_that_cannot_be_reached_leaves_a_failed_row_not_a_stuck_pending_one(
    api, monkeypatch
):
    """Redis down is the realistic failure and it must be legible in the drawer.

    Left `pending`, it is indistinguishable from a slow render and the user waits forever for
    a job nobody holds. The row is marked failed carrying the reason, and the route still
    answers with an error so the click is not silently swallowed either.
    """
    client, db, _company_id, user_id, project = api
    root, document, issue = _issue_one(client, db, project)

    monkeypatch.setattr(
        "app.services.queue_service.enqueue_job", _RecordingQueue(explode=True)
    )

    response = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf")
    assert response.status_code >= 400, response.text

    rows = _downloads(db, user_id)
    assert len(rows) == 1
    assert rows[0].status == DownloadStatus.FAILED.value
    assert "queue" in (rows[0].error or "").lower()


def test_a_revision_from_another_document_cannot_be_queued_through_this_one(api, queued):
    """The URL names a project, a document AND an issue, so the issue is checked against the
    document rather than merely fetched by id. Async does not relax that: a queued export of
    somebody else's price list is the same leak, just delivered later."""
    client, db, _company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    other = _create_document(client, project.id)

    stranger = client.post(f"{root}/{other['id']}/issues/{issue['id']}/export/pdf")
    assert stranger.status_code == 404, stranger.text
    assert stranger.json()["code"] == "quotation_issue_not_found"

    unknown = client.post(f"{root}/{document['id']}/issues/{_uid()}/export/xlsx")
    assert unknown.status_code == 404, unknown.text

    malformed = client.post(f"{root}/{document['id']}/issues/not-a-uuid/export/pdf")
    assert malformed.status_code in (400, 404, 422), malformed.text

    assert queued.calls == []


def test_someone_who_may_not_view_the_project_cannot_queue_its_quotation_export(api, queued):
    """Same gate as the synchronous route. A quotation export is the full price list whether
    it arrives in the response or in a drawer ten seconds later."""
    client, db, _company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)

    with _without_permission(VIEW):
        denied_pdf = client.post(
            f"{root}/{document['id']}/issues/{issue['id']}/export/pdf"
        )
        denied_xlsx = client.post(
            f"{root}/{document['id']}/issues/{issue['id']}/export/xlsx"
        )
    assert denied_pdf.status_code in (401, 403), denied_pdf.text
    assert denied_xlsx.status_code in (401, 403), denied_xlsx.text
    assert queued.calls == []


def test_the_queued_export_is_findable_by_the_revision_it_belongs_to(api, queued):
    """The printer chip on the quotation is a per-source query, and this is the only thing
    that puts a row behind it. Asserted through the endpoint the chip actually calls, not
    just through the service, because the filter lives in the route's query parameters."""
    client, db, _company_id, user_id, project = api
    root, document, issue = _issue_one(client, db, project)

    pdf = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf").json()
    xlsx = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/xlsx").json()

    listed = client.get(
        "/api/v1/downloads",
        params={
            "source_entity_type": "quotation_issue",
            "source_entity_id": issue["id"],
        },
    )
    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["downloads"]}
    assert ids == {pdf["id"], xlsx["id"]}

    # And the service-level lookup the drawer's count map shares agrees.
    from app.services.download_service import DownloadService

    by_source = DownloadService(db).list_for_user_by_source(
        user_id, "quotation_issue", issue["id"]
    )
    assert len(by_source) == 2

    # A different revision's chip stays empty rather than showing this one's exports.
    other_issue = client.get(
        "/api/v1/downloads",
        params={"source_entity_type": "quotation_issue", "source_entity_id": _uid()},
    )
    assert other_issue.json()["downloads"] == []


# ------------------------------------------------------------------- the tasks


class _FakeBackend:
    """Records what was uploaded so the task can be asserted without a bucket."""

    def __init__(self):
        self.uploads: list[tuple[str, bytes, str | None]] = []

    def upload_file(self, file_content, file_path, content_type=None, **_kwargs):
        self.uploads.append((file_path, file_content, content_type))
        return file_path, f"https://cdn.zzt.test/{file_path}"


@contextmanager
def _task_env(db, backend):
    """Run an export task against the test session and a fake bucket.

    The task deliberately opens its OWN ``SessionLocal`` (it runs in the worker, not in a
    request), so the session is swapped for this one and its ``close`` neutered - closing it
    would take the surrounding test's transaction with it.
    """
    from unittest.mock import patch

    from app.tasks import export_tasks

    with patch.object(export_tasks, "SessionLocal", lambda: db), patch.object(
        export_tasks, "get_backend", lambda _provider: backend
    ), patch.object(export_tasks, "default_provider", lambda: "s3"), patch.object(
        db, "close", lambda: None
    ):
        yield export_tasks


def test_the_pdf_task_renders_uploads_and_marks_the_download_ready(api, queued):
    """End of the chain: bytes in a bucket and a row the drawer will offer.

    The uploaded key is namespaced by the download id rather than by the reference, because
    two exports of the SAME revision must not overwrite each other - the second one would
    silently replace a file the first download row still points at.
    """
    client, db, company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf").json()

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        result = tasks.generate_quotation_issue_pdf(
            row["id"], issue["id"], "unused", company_id=company_id
        )

    if result["status"] == "failed" and "PDF rendering" in (result.get("error") or ""):
        pytest.skip(f"WeasyPrint unavailable on this host: {result['error']}")

    assert result["status"] == "ready", result
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    assert stored.status == DownloadStatus.READY.value
    assert stored.ready_at is not None
    assert stored.error is None
    assert stored.storage_provider == "s3"

    (key, content, content_type) = backend.uploads[0]
    assert key.startswith(f"exports/quotation-pdf/{row['id']}/")
    assert key == stored.storage_key
    assert content[:5] == b"%PDF-"
    assert content_type == "application/pdf"
    assert stored.filename.endswith(".pdf")


def test_the_excel_task_renders_uploads_and_marks_the_download_ready(api, queued):
    """The workbook takes the same path under its own prefix and its own mime type. An xlsx
    served as application/pdf downloads as a file Excel refuses to open."""
    client, db, company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/xlsx").json()

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        result = tasks.generate_quotation_issue_xlsx(
            row["id"], issue["id"], "unused", company_id=company_id
        )

    assert result["status"] == "ready", result
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    assert stored.status == DownloadStatus.READY.value

    (key, content, content_type) = backend.uploads[0]
    assert key.startswith(f"exports/quotation-xlsx/{row['id']}/")
    # A zip container, which is what an xlsx is. Anything else is not a workbook.
    assert content[:2] == b"PK"
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert stored.filename.endswith(".xlsx")


def test_a_render_that_blows_up_marks_the_row_failed_and_never_raises(api, queued):
    """Raising out of the task poisons RQ's failed registry and, worse, leaves the row on
    'processing' forever - which the drawer shows as "Preparing", indistinguishable from a
    slow render. The failure has to land ON the row, with its reason."""
    client, db, company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf").json()

    def _explode(_db, _issue):
        raise RuntimeError(f"{MARKER} libpango not found")

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        from app.services import project_quotation_pdf_service as pdf_service

        original = pdf_service.render_issue_pdf
        pdf_service.render_issue_pdf = _explode
        try:
            result = tasks.generate_quotation_issue_pdf(
                row["id"], issue["id"], "unused", company_id=company_id
            )
        finally:
            pdf_service.render_issue_pdf = original

    assert result["status"] == "failed", result
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    assert stored.status == DownloadStatus.FAILED.value
    assert f"{MARKER} libpango not found" in (stored.error or "")
    assert stored.storage_key is None
    assert backend.uploads == []


def test_a_revision_that_no_longer_exists_fails_the_row_instead_of_crashing_the_worker(
    api, queued
):
    """The row outlives what it points at: a document can be deleted between the queue and
    the render. A missing issue is a failed download with a readable reason, not a worker
    traceback nobody sees."""
    client, db, company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf").json()

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        result = tasks.generate_quotation_issue_pdf(
            row["id"], _uid(), "unused", company_id=company_id
        )

    assert result["status"] == "failed", result
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    assert stored.status == DownloadStatus.FAILED.value
    assert backend.uploads == []


def test_a_database_failure_still_lands_on_the_row_rather_than_stranding_it(api, queued):
    """The failure that CANNOT be reported is the one that broke the reporting channel.

    When what blows up is the database - a query against a column the running code expects and
    the schema does not have yet, which is exactly what a half-applied migration looks like -
    psycopg2 leaves the transaction aborted and every later statement on that session raises
    `InFailedSqlTransaction`. Marking the download failed is a later statement on that session.
    So the handler that exists to record failures fails too, and the row is stranded on
    'processing': the drawer says "Preparing" forever, its sweeper only reaps 'sent', and the
    user is never told anything went wrong. Rolling back first is what makes the report land.

    Seen for real: an in-flight migration left `project_quotation_documents.approval_status_id`
    in the model and not in the database, and the download row sat on 'processing'.
    """
    client, db, company_id, _user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/pdf").json()

    def _abort_the_transaction(inner_db, _issue):
        # Any statement Postgres refuses will do: what matters is that the transaction is left
        # aborted afterwards, the way a missing column leaves it.
        inner_db.execute(text(f'SELECT "{MARKER}_no_such_column"'))

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        from app.services import project_quotation_pdf_service as pdf_service

        original = pdf_service.render_issue_pdf
        pdf_service.render_issue_pdf = _abort_the_transaction
        try:
            result = tasks.generate_quotation_issue_pdf(
                row["id"], issue["id"], "unused", company_id=company_id
            )
        finally:
            pdf_service.render_issue_pdf = original

    assert result["status"] == "failed", result
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    assert stored.status == DownloadStatus.FAILED.value, (
        "a database-level failure left the row stranded on 'processing'"
    )
    assert stored.error
    assert backend.uploads == []


# ------------------------------------------------------- serving the artifact


def test_the_ready_export_streams_back_same_origin_for_its_owner_only(api, queued, monkeypatch):
    """The preview modal reads xlsx bytes and saves files through an authenticated
    same-origin route, because a bucket's presigned URL sends no CORS headers and an
    `<img>`/`fetch` against it fails. So the download has a `/file` endpoint - scoped to the
    row's owner, and refusing anything not yet ready rather than streaming zero bytes."""
    client, db, company_id, user_id, project = api
    root, document, issue = _issue_one(client, db, project)
    row = client.post(f"{root}/{document['id']}/issues/{issue['id']}/export/xlsx").json()

    # Not ready yet: a 409 the FE can render, never an empty 200.
    early = client.get(f"/api/v1/downloads/{row['id']}/file")
    assert early.status_code == 409, early.text

    backend = _FakeBackend()
    with _task_env(db, backend) as tasks:
        tasks.generate_quotation_issue_xlsx(
            row["id"], issue["id"], "unused", company_id=company_id
        )
    stored = db.query(UserDownload).filter(UserDownload.id == row["id"]).one()
    payload = backend.uploads[0][1]

    class _Reader:
        def download_file(self, key):
            assert key == stored.storage_key
            return payload

    monkeypatch.setattr(
        "app.api.v1.downloads.downloads.get_backend", lambda _provider: _Reader()
    )

    served = client.get(f"/api/v1/downloads/{row['id']}/file")
    assert served.status_code == 200, served.text
    assert served.content[:2] == b"PK"
    assert served.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert stored.filename in served.headers["content-disposition"]

    # Somebody else's download is not theirs to read, even with the id in hand.
    from app.dependencies import get_current_user
    from app.main import app

    other_id = _user(db, f"{MARKER} Stranger")
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": other_id,
        "email": f"{other_id}@zzt.test",
        "role": "superadmin",
    }
    try:
        stranger = client.get(f"/api/v1/downloads/{row['id']}/file")
    finally:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id,
            "email": f"{user_id}@zzt.test",
            "role": "superadmin",
        }
    assert stranger.status_code == 404, stranger.text
