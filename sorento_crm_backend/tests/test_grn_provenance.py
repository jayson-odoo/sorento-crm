"""A GRN says who created it, and a re-import does not steal the credit.

The reported problem: a Mocha GRN existed as a Sorento row and nobody could say
who put it there. Two reasons, both fixed here.

1. `picking_headers` recorded no author. The only trace was `import_jobs`, which
   had to be matched by bracketing `created_at` - and that fails outright for the
   external (n8n / AutoCount) path, which writes no job and no audit row.
2. The importer reported EVERY success as `created`, so the last person to re-run
   a spreadsheet looked like the author of every GRN in it. `import_job_rows` then
   confidently named the wrong person: the real creation was days earlier by
   somebody else.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import openpyxl
import pytest

from app.models.base import set_company_scope
from app.models.job import ImportJob, JobStatus
from app.models.procurement import PickingHeader
from app.models.user import User
from app.services.procurement_service import PickingHeaderService
from app.tasks.import_tasks import _run_grn_listing_import_core

from ._pg_fixture import blank_session, unique_code

HEADERS = ["Doc Number", "Date", "Transfer From"]


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _user(db, *, name: str) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{unique_code('u').lower()}@example.test",
            name=name,
            password="x",
        )
    )
    db.flush()
    return uid


def _job(db, *, user_id: str, filename: str) -> str:
    jid = str(uuid.uuid4())
    db.add(
        ImportJob(
            id=jid,
            job_id=unique_code("rq"),
            job_type="grn_listing_import",
            status=JobStatus.FINISHED.value,
            user_id=user_id,
            filename=filename,
        )
    )
    db.flush()
    return jid


def _codes(result) -> list[str]:
    """The success codes a run reported, e.g. ["created"] or ["updated"]."""
    return sorted(e["code"] for e in result["outcome"].breakdown()["successful"])


def _header(db, picking_number: str) -> PickingHeader:
    return (
        db.query(PickingHeader)
        .filter(PickingHeader.picking_number == picking_number)
        .one()
    )


def test_an_imported_grn_records_its_uploader_and_file(db):
    uploader = _user(db, name="Datun")
    job = _job(db, user_id=uploader, filename="GRN Listing 06.08.2026 am.xlsx")
    grn = unique_code("GR")[:50]

    _run_grn_listing_import_core(
        db,
        _workbook([[grn, "2026-06-25", "SPO-2026/06-0020"]]),
        created_by=uploader,
        import_job_db_id=job,
    )

    row = _header(db, grn)
    assert row.created_by == uploader
    assert row.import_job_id == job
    assert row.source_system == "import"


def test_a_re_import_does_not_rewrite_authorship(db):
    """The bug that named the wrong person: whoever re-runs the file last must not
    become the author of a GRN somebody else created."""
    first = _user(db, name="Datun")
    second = _user(db, name="Jayson")
    first_job = _job(db, user_id=first, filename="original.xlsx")
    second_job = _job(db, user_id=second, filename="re-run.xlsx")
    grn = unique_code("GR")[:50]

    _run_grn_listing_import_core(
        db,
        _workbook([[grn, "2026-06-25", "SPO-2026/06-0020"]]),
        created_by=first,
        import_job_db_id=first_job,
    )
    _run_grn_listing_import_core(
        db,
        _workbook([[grn, "2026-06-26", "SPO-2026/06-0021"]]),
        created_by=second,
        import_job_db_id=second_job,
    )

    row = _header(db, grn)
    assert row.created_by == first, "the re-import stole authorship"
    assert row.import_job_id == first_job
    # The mutable fields DO follow the latest import - only provenance is frozen.
    assert row.spo_number == "SPO-2026/06-0021"


def test_the_importer_reports_created_then_updated(db):
    grn = unique_code("GR")[:50]

    first = _run_grn_listing_import_core(
        db, _workbook([[grn, "2026-06-25", "SPO-2026/06-0020"]])
    )
    second = _run_grn_listing_import_core(
        db, _workbook([[grn, "2026-06-26", "SPO-2026/06-0020"]])
    )

    assert first["successful"] == 1 and second["successful"] == 1
    # `breakdown()` is the public reason report - the same codes that land in
    # import_job_rows and in the job result the UI shows.
    assert _codes(first) == ["created"]
    assert _codes(second) == ["updated"], (
        "a re-import reported itself as a creation, which is what made "
        "import_job_rows name the wrong author"
    )


def test_the_row_outcome_records_the_grn_it_wrote(db):
    """So "which GRNs did this job create?" is answerable from the job rows, with
    the created GRN's own number as the tracked value."""
    grn = unique_code("GR")[:50]

    result = _run_grn_listing_import_core(
        db, _workbook([[grn, "2026-06-25", "SPO-2026/06-0020"]])
    )

    created = [
        entry
        for entry in result["outcome"].breakdown()["successful"]
        if entry["code"] == "created"
    ]
    assert created, "nothing reported as created"
    assert [v["value"] for v in created[0]["top_values"]] == [grn]


def test_a_staff_create_and_an_integration_create_are_distinguishable(db):
    """The external path leaves no import job, so `source_system` is the only thing
    that separates "a person made this" from "n8n made this"."""
    from app.schemas.procurement import PickingHeaderCreate

    staff = _user(db, name="Office")
    service = PickingHeaderService(db)

    ui_number, api_number = unique_code("GR")[:50], unique_code("GR")[:50]
    service.create_grn(
        PickingHeaderCreate(
            picking_number=ui_number,
            picking_type="goods_received",
            picking_date=date.today(),
        ),
        created_by=staff,
    )
    service.create_grn(
        PickingHeaderCreate(
            picking_number=api_number,
            picking_type="goods_received",
            picking_date=date.today(),
        ),
        created_by=staff,
        source_system="external_api",
    )

    assert _header(db, ui_number).source_system == "ui"
    assert _header(db, api_number).source_system == "external_api"


def test_the_detail_read_resolves_provenance_to_names(db):
    """The UI must never print a UUID, so the read resolves the uploader and the
    file it came from."""
    uploader = _user(db, name="Datun")
    job = _job(db, user_id=uploader, filename="GRN Listing 06.08.2026 am.xlsx")
    grn = unique_code("GR")[:50]
    _run_grn_listing_import_core(
        db,
        _workbook([[grn, "2026-06-25", "SPO-2026/06-0020"]]),
        created_by=uploader,
        import_job_db_id=job,
    )

    fetched = PickingHeaderService(db).get_grn(grn)

    assert fetched.created_by_label == "Datun"
    assert fetched.import_filename == "GRN Listing 06.08.2026 am.xlsx"
    assert fetched.source_system == "import"
