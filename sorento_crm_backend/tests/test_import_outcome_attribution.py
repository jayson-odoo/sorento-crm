"""Every skipped / failed import row must carry a reason.

The bug this pins: `delivery_order_detail_import` reported 4,231 rows as
203 successful / 4,028 skipped while listing only 10 reasons — the other 4,018
skips were the dedup path (`skipped += 1; continue`) which recorded nothing at
all. A green job that cannot say what it dropped is not observable.

Covers UAC AC-A1..A3 and AC-B1..B4
(documentation/plans/imports/import-job-row-outcomes-acceptance-criteria.md).
"""
from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.inventory import Warehouse
from app.models.job import ImportJob, ImportJobRow, JobStatus
from app.models.order import Order, OrderLine
from app.models.product import Product

WAREHOUSE_CODE = "BRW"
KNOWN_PRODUCTS = ["SRTWC-TEST-A", "SRTWC-TEST-B"]
UNKNOWN_PRODUCT = "SRTWC-TEST-MISSING"
DOC_NO = "DO-OUTCOME-TEST-1"

HEADERS = [
    "Doc No",
    "Item Code",
    "Location",
    "Qty",
    "Unit Price",
    "Discount",
    "Total",
    "Tax",
]


def _build_workbook_bytes() -> bytes:
    """Three data rows: two resolvable, one with an unknown product code."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(HEADERS)
    ws.append([DOC_NO, KNOWN_PRODUCTS[0], WAREHOUSE_CODE, 2, 100, None, 200, 0])
    ws.append([DOC_NO, KNOWN_PRODUCTS[1], WAREHOUSE_CODE, 5, 50, None, 250, 0])
    ws.append([DOC_NO, UNKNOWN_PRODUCT, WAREHOUSE_CODE, 1, 10, None, 10, 0])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Order.__table__,
            OrderLine.__table__,
            Product.__table__,
            Warehouse.__table__,
            ImportJob.__table__,
            ImportJobRow.__table__,
        ],
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def seeded(session_factory):
    """One order, one warehouse, two products — and the ImportJob rows to run."""
    db = session_factory()
    try:
        db.add(Order(id=str(uuid.uuid4()), order_number=DOC_NO, is_cancelled=False))
        db.add(
            Warehouse(
                id=str(uuid.uuid4()),
                warehouse_code=WAREHOUSE_CODE,
                warehouse_name="Test warehouse",
                is_active=True,
            )
        )
        for code in KNOWN_PRODUCTS:
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=f"Test {code}",
                    category_id=str(uuid.uuid4()),
                    base_uom_id=str(uuid.uuid4()),
                    list_price=0,
                )
            )
        db.commit()
    finally:
        db.close()
    return session_factory


def _make_job(session_factory, user_id: str):
    """Returns the job's UUID. ImportJob.id is a real UUID column, so sqlite needs a
    uuid object (the psycopg2 dialect coerces strings, the generic one does not)."""
    db = session_factory()
    try:
        job = ImportJob(
            id=uuid.uuid4(),
            job_id=str(uuid.uuid4()),
            job_type="delivery_order_detail_import",
            status=JobStatus.PENDING.value,
            user_id=user_id,
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _run_import(session_factory, db_job_id, file_bytes: bytes, user_id: str):
    from app.tasks import import_tasks

    with patch.object(import_tasks, "SessionLocal", session_factory):
        import_tasks.process_delivery_order_detail_import(
            db_job_id, file_bytes, "outcome-test.xlsx", user_id
        )
    db = session_factory()
    try:
        return db.query(ImportJob).filter(ImportJob.id == db_job_id).first()
    finally:
        db.close()


def _breakdown_counts(job: ImportJob) -> dict[str, dict[str, int]]:
    result = job.result or {}
    breakdown = result.get("breakdown") or {}
    return {
        group: {e["code"]: e["count"] for e in (breakdown.get(group) or [])}
        for group in ("successful", "skipped", "failed")
    }


def test_first_import_attributes_every_row(seeded):
    """Two rows create lines, one is skipped with a named reason."""
    user_id = str(uuid.uuid4())
    file_bytes = _build_workbook_bytes()
    job_id = _make_job(seeded, user_id)

    job = _run_import(seeded, job_id, file_bytes, user_id)

    assert job.successful_rows == 2
    assert job.skipped_rows == 1

    counts = _breakdown_counts(job)
    assert counts["successful"].get("created") == 2
    assert counts["skipped"].get("product_not_found") == 1


def test_reimport_attributes_every_duplicate_skip(seeded):
    """THE REGRESSION: re-importing the same file must name every skip.

    Today the dedup branch bumps `skipped` with no code, so the reasons list is
    empty while `skipped_rows == 3` — exactly the reported job.
    """
    user_id = str(uuid.uuid4())
    file_bytes = _build_workbook_bytes()

    first = _run_import(seeded, _make_job(seeded, user_id), file_bytes, user_id)
    assert first.successful_rows == 2

    second = _run_import(seeded, _make_job(seeded, user_id), file_bytes, user_id)
    assert second.successful_rows == 0
    assert second.skipped_rows == 3

    counts = _breakdown_counts(second)
    # The two previously-created lines are now duplicates...
    assert counts["skipped"].get("duplicate_line") == 2
    # ...and the unknown product is still its own, separate reason.
    assert counts["skipped"].get("product_not_found") == 1

    # No unattributed skips: the reasons must account for the counter exactly.
    assert sum(counts["skipped"].values()) == second.skipped_rows


def test_every_row_is_persisted_for_drill_down(seeded):
    """AC-A1: the breakdown is not enough - each row must be individually retrievable."""
    user_id = str(uuid.uuid4())
    file_bytes = _build_workbook_bytes()
    job_id = _make_job(seeded, user_id)

    _run_import(seeded, job_id, file_bytes, user_id)

    db = seeded()
    try:
        rows = (
            db.query(ImportJobRow)
            .filter(ImportJobRow.import_job_id == job_id)
            .order_by(ImportJobRow.row_number)
            .all()
        )
    finally:
        db.close()

    assert len(rows) == 3, "one captured row per source row"
    assert {r.outcome for r in rows} == {"created", "skipped"}
    assert all(r.code for r in rows), "every captured row carries a reason code"
    assert all(r.row_number is not None for r in rows)

    missing = [r for r in rows if r.code == "product_not_found"]
    assert len(missing) == 1
    assert missing[0].value == UNKNOWN_PRODUCT
    # Identity carries business keys the operator can act on, never UUIDs.
    assert missing[0].identity["doc_no"] == DOC_NO
    assert missing[0].identity["item_code"] == UNKNOWN_PRODUCT


def test_counts_and_breakdown_always_reconcile(seeded):
    """AC-B4: every counted row is explained by exactly one breakdown entry."""
    user_id = str(uuid.uuid4())
    file_bytes = _build_workbook_bytes()
    job = _run_import(seeded, _make_job(seeded, user_id), file_bytes, user_id)

    result = job.result or {}
    counts = result.get("counts") or {}
    assert counts, "job result must carry a counts block"

    breakdown = _breakdown_counts(job)
    assert sum(breakdown["successful"].values()) == counts["successful"]
    assert sum(breakdown["skipped"].values()) == counts["skipped"]
    assert sum(breakdown["failed"].values()) == counts["failed"]
    assert (
        counts["successful"] + counts["skipped"] + counts["failed"]
        == counts["processed"]
    )
