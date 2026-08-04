"""POST /api/v1/procurement/packing-lists/container-status-import (slice 3, part 3).

Happy path, dry run, auth denial and input validation, plus the two things about
this endpoint that are easy to get wrong:

* **The dry run must not enqueue.** A `validate_only` call that queued a job would
  import the file the operator was only asking about.
* **The retained bytes are the ORIGINAL ones**, before macro-stripping. The cost
  block this importer deliberately skips (D9) survives only in that file, and the
  assistant serves the same workbook back to a contact who asks for it.

The queue and the source-file store are stubbed - what is under test is the route's
own decisions, not RQ or object storage.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.services.user_service import UserPermissionService


ENDPOINT = "/api/v1/procurement/packing-lists/container-status-import"
PERMISSION = "procurement.packing_lists.import_container_status"


def _workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fitting"
    ws.append(["FITTING CONTAINER 2026"])
    ws.append(["NO", "CONTAINER", "LINER", "ETA DELAY"])
    ws.append([1, "GXYU5106903", "CMA", date(2026, 7, 8)])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def granted(monkeypatch):
    """A caller who holds the import permission."""
    user = {"id": str(uuid.uuid4())}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: True,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def stub_queue(monkeypatch):
    """Capture what the route would enqueue and retain, without doing either."""
    captured: dict = {"enqueued": [], "retained": [], "jobs": []}

    class _Job:
        def __init__(self):
            self.id = uuid.uuid4()
            self.job_id = f"rq-{self.id}"

    class _JobService:
        def __init__(self, db):
            pass

        def create_job(self, **kwargs):
            job = _Job()
            captured["jobs"].append(kwargs)
            return job

        def update_job_with_rq_id(self, job, rq_id):
            captured.setdefault("rq_ids", []).append(rq_id)

    def _enqueue(func, *args, **kwargs):
        captured["enqueued"].append({"func": func.__name__, "args": args, "kwargs": kwargs})
        return MagicMock(id=str(uuid.uuid4()))

    def _store(job, data, name, ctype):
        captured["retained"].append({"bytes": data, "name": name, "content_type": ctype})

    monkeypatch.setattr("app.services.job_service.JobService", _JobService)
    monkeypatch.setattr("app.services.queue_service.enqueue_job", _enqueue)
    monkeypatch.setattr(
        "app.services.import_source_store.store_import_source_file", _store
    )
    return captured


# ------------------------------------------------------------------ happy path


def test_queues_an_import_job_and_returns_202(granted, stub_queue):
    response = granted.post(
        ENDPOINT,
        files={
            "file": (
                "Container Status 2026.xlsx",
                _workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["queued"] is True
    assert body["job_id"]

    assert len(stub_queue["enqueued"]) == 1
    enqueued = stub_queue["enqueued"][0]
    assert enqueued["func"] == "process_container_status_import"
    assert enqueued["kwargs"]["queue_name"] == "imports"
    assert stub_queue["jobs"][0]["job_type"] == "container_status_import"


def test_retains_the_original_bytes_for_the_assistant_to_serve_back(granted, stub_queue):
    """A7 / D10: the uploaded workbook is what a contact receives, so the file the
    route keeps must be the file that arrived."""
    payload = _workbook_bytes()
    granted.post(
        ENDPOINT,
        files={"file": ("Container Status 2026.xlsx", payload, "application/vnd.ms-excel")},
    )

    assert len(stub_queue["retained"]) == 1
    retained = stub_queue["retained"][0]
    assert retained["bytes"] == payload
    assert retained["name"] == "Container Status 2026.xlsx"


# --------------------------------------------------------------------- dry run


def test_the_dry_run_returns_the_summary_and_queues_nothing(granted, stub_queue, monkeypatch):
    # Patched on the task module, not on the route: the route imports it inside the
    # function body, so the lookup happens at call time.
    monkeypatch.setattr(
        "app.tasks.import_tasks.validate_container_status_import",
        lambda data, name: {
            "valid": True,
            "errors": [],
            "warnings": ["Header matched by alias: LINER <- \"RL\" on Ceramic."],
            "summary": {
                "total_rows": 407,
                "would_update": 111,
                "would_create": 296,
                "error_count": 0,
            },
        },
    )

    response = granted.post(
        f"{ENDPOINT}?validate_only=true",
        files={"file": ("Container Status 2026.xlsx", _workbook_bytes(), "application/vnd.ms-excel")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    # Exactly the keys the shared upload dialog renders.
    assert set(body["summary"]) == {
        "total_rows",
        "would_update",
        "would_create",
        "error_count",
    }
    assert stub_queue["enqueued"] == [], "a dry run must not queue an import"
    assert stub_queue["retained"] == [], "a dry run must not retain a source file"


# ------------------------------------------------------------------ validation


def test_rejects_a_non_excel_file(granted, stub_queue):
    response = granted.post(
        ENDPOINT, files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 400
    assert "Invalid file type" in response.text
    assert stub_queue["enqueued"] == []


def test_rejects_an_empty_upload(granted, stub_queue):
    response = granted.post(
        ENDPOINT, files={"file": ("Container Status 2026.xlsx", b"", "application/vnd.ms-excel")}
    )

    assert response.status_code == 400
    assert "empty" in response.text.lower()
    assert stub_queue["enqueued"] == []


def test_a_missing_file_is_a_422(granted, stub_queue):
    response = granted.post(ENDPOINT)

    assert response.status_code == 422
    assert stub_queue["enqueued"] == []


# ---------------------------------------------------------------- auth denial


def test_a_caller_without_the_permission_is_refused(monkeypatch, stub_queue):
    user = {"id": str(uuid.uuid4())}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: False,
    )
    try:
        client = TestClient(app)
        response = client.post(
            ENDPOINT,
            files={
                "file": (
                    "Container Status 2026.xlsx",
                    _workbook_bytes(),
                    "application/vnd.ms-excel",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert stub_queue["enqueued"] == [], "a refused caller must not queue anything"


def test_the_permission_is_registered_so_it_can_be_granted():
    """A permission that exists only in a route decorator is ungrantable, which
    is indistinguishable from a broken feature."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert PERMISSION in slugs
