"""Tests for the complaint PDF export pipeline (My Downloads).

Covers the DownloadService state machine (deterministic, no native deps) and the
WeasyPrint render (skipped if native libs are missing on the host).
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from tests._pg_fixture import pg_session
from app.models.complaints import Complaint
from app.models.download import DownloadStatus
from app.services.complaint_pdf_service import ComplaintPDFService, PDFRenderingUnavailable
from app.services.download_service import DownloadService


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        for sql in (
            "DELETE FROM user_downloads WHERE kind = 'complaint_pdf' AND user_id LIKE 'pdftest-%'",
            "DELETE FROM complaints WHERE complaint_number LIKE 'CMPPDF-%'",
        ):
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with pg_session() as s:
        yield s


def _seed_complaint(db: Session) -> Complaint:
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"CMPPDF-{uuid.uuid4().hex[:6]}",
        status="approved",
        customer_name="ACME Sdn Bhd",
        defect_description="Hairline crack on the basin rim.",
        technical_team_response="Inspected; replacement scheduled.",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_download_lifecycle(db: Session) -> None:
    svc = DownloadService(db)
    uid = f"pdftest-{uuid.uuid4().hex[:6]}"
    row = svc.create(user_id=uid, kind="complaint_pdf", source_entity_type="complaint", source_entity_id="f3e951bb-a80b-5e6c-a038-a56ee0caa25d")
    assert row.status == DownloadStatus.PENDING.value

    svc.mark_processing(row.id)
    assert svc.get(row.id).status == DownloadStatus.PROCESSING.value

    svc.mark_ready(row.id, storage_provider="s3", storage_key="exports/complaint-pdf/x/complaint-x.pdf")
    ready = svc.get(row.id)
    assert ready.status == DownloadStatus.READY.value
    assert ready.storage_key.endswith(".pdf")
    assert ready.ready_at is not None

    # list_for_user returns the row, scoped to the user.
    rows = svc.list_for_user(uid)
    assert any(r.id == row.id for r in rows)


def test_download_mark_failed(db: Session) -> None:
    svc = DownloadService(db)
    uid = f"pdftest-{uuid.uuid4().hex[:6]}"
    row = svc.create(user_id=uid, kind="complaint_pdf")
    svc.mark_failed(row.id, "boom")
    failed = svc.get(row.id)
    assert failed.status == DownloadStatus.FAILED.value
    assert failed.error == "boom"


def test_render_pdf_produces_pdf_bytes(db: Session) -> None:
    c = _seed_complaint(db)
    try:
        pdf_bytes, filename = ComplaintPDFService(db).render_pdf(c.id)
    except PDFRenderingUnavailable as e:
        pytest.skip(f"WeasyPrint native libs unavailable on host: {e}")
        return
    assert pdf_bytes[:5] == b"%PDF-"
    assert filename.startswith("complaint-") and filename.endswith(".pdf")
    assert len(pdf_bytes) > 1000


def test_build_filename_sanitizes(db: Session) -> None:
    c = _seed_complaint(db)
    name = ComplaintPDFService(db).build_filename(c)
    assert name.startswith("complaint-CMPPDF-")
    assert name.endswith(".pdf")
