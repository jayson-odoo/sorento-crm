"""Every skipped / failed import row must carry a reason.

The bug this pins: `delivery_order_detail_import` reported 4,231 rows as
203 successful / 4,028 skipped while listing only 10 reasons — the other 4,018
skips were the dedup path (`skipped += 1; continue`) which recorded nothing at
all. A green job that cannot say what it dropped is not observable.

Covers UAC AC-A1..A3 and AC-B1..B4
(documentation/plans/imports/import-job-row-outcomes-acceptance-criteria.md).

Runs against a throwaway Postgres schema (tests/_pg_fixture), not sqlite: the
importer and the outcome recorder use SEPARATE sessions that both commit, so
the substrate has to be the real one — and `import_jobs.result` is JSONB, which
sqlite cannot emit at all.

The schema is per-test and dropped afterwards rather than the run-wide
``blank_session``: nothing here can be rolled back (the importer commits on its
own session), and committed rows in the shared blank schema leak into every
later test that counts them — it broke test_product_discontinued_notify and
test_notification_dedup_key_split when tried that way.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine
from app.models.embeddings import EmbeddingQueue
from app.models.inventory import Warehouse
from app.models.job import ImportJob, ImportJobRow, JobStatus
from app.models.order import Order, OrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import _globally_required_tables, _with_dependencies

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


@dataclass(frozen=True)
class Fixture:
    """The unique identifiers one test's rows are tagged with."""

    doc_no: str
    warehouse_code: str
    known_products: tuple[str, str]
    unknown_product: str


def _build_workbook_bytes(fx: Fixture) -> bytes:
    """Three data rows: two resolvable, one with an unknown product code."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(HEADERS)
    ws.append([fx.doc_no, fx.known_products[0], fx.warehouse_code, 2, 100, None, 200, 0])
    ws.append([fx.doc_no, fx.known_products[1], fx.warehouse_code, 5, 50, None, 250, 0])
    ws.append([fx.doc_no, fx.unknown_product, fx.warehouse_code, 1, 10, None, 10, 0])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def session_factory():
    """A sessionmaker over a private, empty Postgres schema, dropped at teardown.

    A factory rather than a session because the code under test opens its own:
    the importer calls ``SessionLocal()`` and the outcome recorder opens a
    SECOND one, deliberately, so its rows survive an import that rolls back.
    """
    tables = _with_dependencies(
        [
            Order.__table__,
            OrderLine.__table__,
            Product.__table__,
            Warehouse.__table__,
            ImportJob.__table__,
            ImportJobRow.__table__,
            # Another test module registers the embedding change listener
            # globally; once it has, every Order insert here enqueues an event.
            # Absent in a single-file run, fatal in a full-suite one.
            EmbeddingQueue.__table__,
        ]
        + _globally_required_tables()
    )
    name = f"zzt_import_outcome_{uuid.uuid4().hex[:10]}"

    admin = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    admin.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    admin.close()

    scoped = engine.execution_options(schema_translate_map={None: name})
    with scoped.connect() as connection:
        Base.metadata.create_all(connection, tables=tables, checkfirst=False)
        connection.commit()

    try:
        yield sessionmaker(autocommit=False, autoflush=False, bind=scoped)
    finally:
        cleanup = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        cleanup.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cleanup.close()


@pytest.fixture
def seeded(session_factory):
    """One order, one warehouse, two products, all uniquely tagged."""
    tag = uuid.uuid4().hex[:8].upper()
    fx = Fixture(
        doc_no=f"ZZT-DO-{tag}",
        warehouse_code=f"ZZTWH-{tag}",
        known_products=(f"ZZT-{tag}-A", f"ZZT-{tag}-B"),
        unknown_product=f"ZZT-{tag}-MISSING",
    )

    db = session_factory()
    try:
        # Postgres enforces these foreign keys; the old sqlite fixture invented
        # loose UUIDs for category / uom and got away with it.
        category = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"ZZTCAT-{tag}", category_name="Test"
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"ZZTUOM-{tag}", uom_name="Each")
        db.add_all([category, uom])
        db.flush()

        db.add(Order(id=str(uuid.uuid4()), order_number=fx.doc_no, is_cancelled=False))
        db.add(
            Warehouse(
                id=str(uuid.uuid4()),
                warehouse_code=fx.warehouse_code,
                warehouse_name="Test warehouse",
                is_active=True,
            )
        )
        for code in fx.known_products:
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=f"Test {code}",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=0,
                )
            )
        db.commit()
    finally:
        db.close()
    return session_factory, fx


def _make_job(session_factory, user_id: str):
    """Returns the job's UUID."""
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
    factory, fx = seeded
    user_id = str(uuid.uuid4())
    job_id = _make_job(factory, user_id)

    job = _run_import(factory, job_id, _build_workbook_bytes(fx), user_id)

    assert job.successful_rows == 2
    assert job.skipped_rows == 1

    counts = _breakdown_counts(job)
    assert counts["successful"].get("created") == 2
    assert counts["skipped"].get("product_not_found") == 1


def test_reimport_attributes_every_duplicate_skip(seeded):
    """THE REGRESSION: re-importing the same file must name every skip.

    Before the fix the dedup branch bumped `skipped` with no code, so the
    reasons list was empty while `skipped_rows == 3` — exactly the reported job.
    """
    factory, fx = seeded
    user_id = str(uuid.uuid4())
    file_bytes = _build_workbook_bytes(fx)

    first = _run_import(factory, _make_job(factory, user_id), file_bytes, user_id)
    assert first.successful_rows == 2

    second = _run_import(factory, _make_job(factory, user_id), file_bytes, user_id)
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
    factory, fx = seeded
    user_id = str(uuid.uuid4())
    job_id = _make_job(factory, user_id)

    _run_import(factory, job_id, _build_workbook_bytes(fx), user_id)

    db = factory()
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
    assert missing[0].value == fx.unknown_product
    # Identity carries business keys the operator can act on, never UUIDs.
    assert missing[0].identity["doc_no"] == fx.doc_no
    assert missing[0].identity["item_code"] == fx.unknown_product


def test_counts_and_breakdown_always_reconcile(seeded):
    """AC-B4: every counted row is explained by exactly one breakdown entry."""
    factory, fx = seeded
    user_id = str(uuid.uuid4())
    job = _run_import(
        factory, _make_job(factory, user_id), _build_workbook_bytes(fx), user_id
    )

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
