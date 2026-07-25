"""GET /system/jobs/{id}/rows and /rows/export.

Covers UAC AC-D1..D5: filtering, paging, CSV of the FILTERED set, 404 on an
unknown job, 403 for a non-owner, and an empty list (not an error) for a job
whose rows were never captured or have aged out.
"""
from __future__ import annotations

import csv
import io
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.system.jobs import router as jobs_router
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models.job import ImportJob, ImportJobRow, JobStatus

OWNER_ID = str(uuid.uuid4())
OTHER_ID = str(uuid.uuid4())


@pytest.fixture
def client_and_job():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[ImportJob.__table__, ImportJobRow.__table__]
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    job = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type="delivery_order_detail_import",
        status=JobStatus.FINISHED.value,
        user_id=OWNER_ID,
        total_rows=6,
    )
    db.add(job)
    db.flush()

    seeds = [
        ("created", "created", "Order line created", None, 2),
        ("created", "created", "Order line created", None, 3),
        ("skipped", "duplicate_line", "Identical line already exists", "DO-1", 4),
        ("skipped", "product_not_found", "Product not found: ABC-1", "ABC-1", 5),
        ("skipped", "product_not_found", "Product not found: ABC-2", "ABC-2", 6),
        ("failed", "row_error", "numeric field overflow", "DO-9", 7),
    ]
    for outcome, code, message, value, row_number in seeds:
        db.add(
            ImportJobRow(
                id=uuid.uuid4(),
                import_job_id=job.id,
                row_number=row_number,
                outcome=outcome,
                code=code,
                message=message,
                value=value,
                identity={"doc_no": value or "DO-0", "item_code": value},
            )
        )
    db.commit()
    job_key = job.job_id
    db.close()

    app = FastAPI()
    app.include_router(jobs_router, prefix="/api/v1/system")

    def _override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": OWNER_ID}

    return TestClient(app), job_key, app


def test_lists_every_captured_row(client_and_job):
    client, job_key, _ = client_and_job
    res = client.get(f"/api/v1/system/jobs/{job_key}/rows")
    assert res.status_code == 200
    body = res.json()
    assert body["pagination"]["total"] == 6
    assert body["empty"] is False
    # The label is resolved server-side from the shared taxonomy.
    codes = {r["code"]: r["label"] for r in body["data"]}
    assert codes["product_not_found"] == "Product not found"


def test_filters_by_outcome_and_code(client_and_job):
    client, job_key, _ = client_and_job

    res = client.get(f"/api/v1/system/jobs/{job_key}/rows", params={"outcome": "skipped"})
    assert res.json()["pagination"]["total"] == 3

    res = client.get(
        f"/api/v1/system/jobs/{job_key}/rows", params={"code": "product_not_found"}
    )
    body = res.json()
    assert body["pagination"]["total"] == 2
    assert {r["value"] for r in body["data"]} == {"ABC-1", "ABC-2"}


def test_free_text_search_covers_detail_and_identity(client_and_job):
    client, job_key, _ = client_and_job
    res = client.get(f"/api/v1/system/jobs/{job_key}/rows", params={"query": "ABC-2"})
    body = res.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["value"] == "ABC-2"


def test_pagination_reports_the_full_total(client_and_job):
    client, job_key, _ = client_and_job
    res = client.get(f"/api/v1/system/jobs/{job_key}/rows", params={"page": 1, "limit": 2})
    body = res.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 6, "total is the filtered set, not the page"


def test_export_streams_the_filtered_set_as_csv(client_and_job):
    client, job_key, _ = client_and_job
    res = client.get(
        f"/api/v1/system/jobs/{job_key}/rows/export", params={"code": "product_not_found"}
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert f"import-job-{job_key}-rows.csv" in res.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0] == [
        "row", "outcome", "code", "reason", "detail", "value", "identity", "entity_id",
    ]
    data_rows = rows[1:]
    assert len(data_rows) == 2, "export honours the filter, and is not paginated"
    assert {r[5] for r in data_rows} == {"ABC-1", "ABC-2"}
    assert all(r[3] == "Product not found" for r in data_rows)


def test_unknown_job_is_404(client_and_job):
    client, _job_key, _ = client_and_job
    res = client.get(f"/api/v1/system/jobs/{uuid.uuid4()}/rows")
    assert res.status_code == 404


def test_non_owner_is_denied(client_and_job):
    client, job_key, app = client_and_job
    app.dependency_overrides[get_current_user] = lambda: {"id": OTHER_ID}
    assert client.get(f"/api/v1/system/jobs/{job_key}/rows").status_code == 403
    assert client.get(f"/api/v1/system/jobs/{job_key}/rows/export").status_code == 403


def test_job_without_captured_rows_returns_empty_not_error():
    """A legacy job, or one whose detail has been pruned, still renders."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[ImportJob.__table__, ImportJobRow.__table__])
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    job = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type="stock_import",
        status=JobStatus.FINISHED.value,
        user_id=OWNER_ID,
    )
    db.add(job)
    db.commit()
    job_key = job.job_id
    db.close()

    app = FastAPI()
    app.include_router(jobs_router, prefix="/api/v1/system")

    def _override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": OWNER_ID}

    res = TestClient(app).get(f"/api/v1/system/jobs/{job_key}/rows")
    assert res.status_code == 200
    assert res.json()["pagination"]["total"] == 0
    assert res.json()["empty"] is True
